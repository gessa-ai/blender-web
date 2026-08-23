/* SPDX-FileCopyrightText: 2022-2023 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from intern/ghost/intern/GHOST_ContextWGPU.cc (native Dawn,
 * patch 0011) @ fbe6228777e7. */

/** \file
 * \ingroup GHOST-web
 * Implementation of GHOST_ContextWGPUWeb (emdawnwebgpu + HTML canvas surface). */

#include "GHOST_ContextWGPUWeb.hh"
#include "GHOST_WGPUTransaction.hh"

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <utility>

#include <emscripten/emscripten.h>
#include <emscripten/html5.h>

#include "GHOST_WebDisplayState.hh"

/* --- Present counter (ghost-keepalive) --------------------------------------- */
/* One monotonically increasing counter of end-of-frame presents (surface submits). It is
 * the ground truth for "is the app actually drawing": GHOST_SystemWeb::processEvents reads
 * it to keep the idle keepalive fast while frames are being produced (interaction, playback,
 * notifier redraws) and to let it back off when nothing is drawn, and the shell reads it via
 * bw_present_count() to PROVE the idle loop submits no frames (flat counter) while the WM
 * tick counter keeps rising. A plain relaxed atomic - the only writer is this worker's
 * presentBackbuffer, readers just need a coherent recent value. */
namespace {
std::atomic<uint64_t> g_present_count{0};
}  // namespace

namespace ghost_web {
uint64_t present_count()
{
  return g_present_count.load(std::memory_order_relaxed);
}
void note_present()
{
  g_present_count.fetch_add(1u, std::memory_order_relaxed);
}
}  // namespace ghost_web

/* Total presents since boot, as double (avoids a BigInt hop under -sWASM_BIGINT). Exported
 * for the ghost-keepalive no-idle-burn proof: the shell polls this across an idle window and
 * shows the delta is ~0 (no GPU submits at idle) while bw_wm_tick_count keeps climbing. */
extern "C" EMSCRIPTEN_KEEPALIVE double bw_present_count(void)
{
  return double(ghost_web::present_count());
}

/* --- M4.T11 (ADR-007) worker-side device delivery ---------------------------- */
/* The WebGPU device cannot be acquired synchronously here (emdawnwebgpu needs an
 * event-loop turn or asyncify) and cannot cross realms, so it is acquired
 * ASYNCHRONOUSLY on THIS (WM/proxied-main) worker pre-main and stashed in
 * Module.preinitializedWebGPUDevice by platform_web/shell/wgpu-preinit-worker.js.
 * See the "M4.T11 — emdawnwebgpu port probe" section of notes/m4-integration.md. */
EM_JS(int, ghost_web_has_preinit_device, (), {
  return (typeof Module !== "undefined" && Module["preinitializedWebGPUDevice"]) ? 1 : 0;
});

/* Whether the canvas selector resolves on THIS thread, mirroring emdawnwebgpu's
 * findCanvasEventTarget lookup ORDER exactly (built JS: findCanvasEventTarget). On the
 * WM worker the DOM `#canvas` is transferred as an OffscreenCanvas (OFFSCREENCANVAS_
 * SUPPORT + OFFSCREENCANVASES_TO_PTHREAD, M4.T12) and lands in GL.offscreenCanvases
 * keyed by the BARE element id (selector minus a leading '#') — NOT in
 * specialHTMLTargets — which is why the earlier specialHTMLTargets/document-only check
 * missed it and left the surface deferred. Check GL.offscreenCanvases first, then the
 * browser-main-thread paths. */
EM_JS(int, ghost_web_canvas_resolvable, (const char *selector), {
  var s = UTF8ToString(selector);
  try {
    if (typeof GL !== "undefined" && GL.offscreenCanvases &&
        GL.offscreenCanvases[s.replace(/^#/, "")]) {
      return 1;
    }
    if (typeof specialHTMLTargets !== "undefined" && specialHTMLTargets[s]) {
      return 1;
    }
    if (typeof document !== "undefined" && document && document.querySelector(s)) {
      return 1;
    }
  } catch (e) {}
  return 0;
});

GHOST_ContextWGPUWeb::GHOST_ContextWGPUWeb(const GHOST_ContextParams &context_params,
                                           const char *canvas_selector)
    : GHOST_Context(context_params),
      canvas_selector_(canvas_selector ? canvas_selector : "#canvas")
{
}

GHOST_ContextWGPUWeb::~GHOST_ContextWGPUWeb() = default;

/* --- GHOST_Context surface --------------------------------------------------- */

GHOST_TSuccess GHOST_ContextWGPUWeb::initializeDrawingContext()
{
  /* If a prior initAsync() already acquired the device (callback path, e.g. the
   * standalone harness), we are done. */
  if (ready_) {
    return GHOST_kSuccess;
  }

  /* Windowed (GHOST) path under ADR-006/ADR-007. This runs straight-line on the
   * PROXY_TO_PTHREAD WM worker during WM_init, before any event-loop pump exists. The
   * emdawnwebgpu port cannot acquire a device synchronously here: a TimedWaitAny
   * instance needs asyncify/JSPI (webgpu.cpp:1643 → CreateInstance returns null), and a
   * blocking WaitAny would deadlock the worker (it cannot resolve its own promise while
   * Atomics-blocked). So the device was acquired ASYNCHRONOUSLY on THIS worker pre-main
   * (platform_web/shell/wgpu-preinit-worker.js) and stashed in
   * Module.preinitializedWebGPUDevice; here we just import it synchronously. The device
   * handle is per-thread (emdawnwebgpu jsObjects table) — importing on the WM worker is
   * correct because this worker will own all GPU work (M4.T11 probe (i)/(iii)). */
  if (!ghost_web_has_preinit_device()) {
    std::printf("WGPUWeb: no pre-acquired device on the WM worker "
                "(wgpu-preinit-worker.js did not run or acquisition failed)\n");
    return GHOST_kFailure;
  }

  /* A featureless instance is valid without asyncify (unlike a TimedWaitAny one). */
  instance_ = wgpu::CreateInstance(nullptr);
  if (instance_ == nullptr) {
    std::printf("WGPUWeb: CreateInstance failed\n");
    return GHOST_kFailure;
  }

  /* Import Module.preinitializedWebGPUDevice into THIS thread's object table. */
  WGPUDevice raw_device = emscripten_webgpu_get_device();
  if (raw_device == nullptr) {
    std::printf("WGPUWeb: emscripten_webgpu_get_device returned null\n");
    return GHOST_kFailure;
  }
  device_ = wgpu::Device::Acquire(raw_device);
  /* NB: the uncaptured-error callback can only be set via DeviceDescriptor at device
   * creation; an imported device inherits the one set where it was created (none here),
   * so Dawn logs uncaptured errors to the browser console instead. */
  queue_ = device_.GetQueue();

  /* Canvas size: emscripten_get_canvas_element_size only resolves on a worker once the
   * canvas is transferred as an OffscreenCanvas (surface step below, not wired this
   * round); fall back to a sane default so a later surface configure has extents. */
  int cw = 0, ch = 0;
  emscripten_get_canvas_element_size(canvas_selector_.c_str(), &cw, &ch);
  if (cw > 0) {
    width_ = uint32_t(cw);
  }
  if (ch > 0) {
    height_ = uint32_t(ch);
  }
  if (width_ == 0) {
    width_ = 1280;
  }
  if (height_ == 0) {
    height_ = 720;
  }

  /* Surface is BEST-EFFORT this round. A live device already satisfies
   * GPU_context_create / GPU_init — WGPUContext reads instance/device/queue + device
   * limits, never the surface (wgpu_context.cc). The WM worker has no DOM canvas until
   * OffscreenCanvas is wired, and emdawnwebgpu's CreateSurface would ABORT (not return
   * null) on an unresolvable selector (library_webgpu.js:1998-2002), so guard it. Skip
   * → device stays live, ready_=true, and the boot advances past drawing-context
   * creation into GPU_init + the main loop; the surface is the next characterized
   * blocker (needs OFFSCREENCANVAS_SUPPORT + OFFSCREENCANVASES_TO_PTHREAD). */
  if (ghost_web_canvas_resolvable(canvas_selector_.c_str())) {
    finishSetup(); /* creates + configures the surface, sets ready_ + on_ready_ */
  }
  else {
    std::printf("WGPUWeb: surface deferred — canvas '%s' not resolvable on the WM worker "
                "(no OffscreenCanvas yet); device is live, continuing\n",
                canvas_selector_.c_str());
  }

  ready_ = true;
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::releaseNativeHandles()
{
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::swapBufferAcquire()
{
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::swapBufferRelease()
{
  /* End-of-frame present (M4.T21): the backend renders every pass into the PERSISTENT
   * offscreen back-buffer; here — the last op of the frame, still inside the WM's rAF
   * tick (wm_draw.cc:1692 wm_window_swap_buffer_release) — we blit it onto the surface's
   * current texture and submit once. The browser then auto-presents that texture on
   * event-loop yield. Because acquire+copy+submit all happen in-tick and nothing else
   * ever references the surface, the per-frame "Destroyed texture … WebgpuSwapChainTexture
   * used in a submit" family (725x/boot pre-M4.T21) cannot occur. */
  presentBackbuffer();
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::activateDrawingContext()
{
  return GHOST_kSuccess;
}

GHOST_TSuccess GHOST_ContextWGPUWeb::releaseDrawingContext()
{
  return GHOST_kSuccess;
}

void GHOST_ContextWGPUWeb::initAsync(uint32_t width, uint32_t height, ReadyCallback on_ready)
{
  width_ = width;
  height_ = height;
  on_ready_ = std::move(on_ready);

  /* No TimedWaitAny feature here: the browser drives callbacks off the event loop
   * (AllowSpontaneous), so we never block-wait. */
  instance_ = wgpu::CreateInstance(nullptr);
  if (instance_ == nullptr) {
    std::printf("WGPUWeb: CreateInstance failed\n");
    if (on_ready_) {
      on_ready_(false);
    }
    return;
  }
  requestAdapter();
}

void GHOST_ContextWGPUWeb::requestAdapter()
{
  wgpu::RequestAdapterOptions opts = {};
  opts.powerPreference = wgpu::PowerPreference::HighPerformance;

  instance_.RequestAdapter(
      &opts,
      wgpu::CallbackMode::AllowSpontaneous,
      [this](wgpu::RequestAdapterStatus status, wgpu::Adapter a, wgpu::StringView msg) {
        if (status != wgpu::RequestAdapterStatus::Success || a == nullptr) {
          std::printf("WGPUWeb: RequestAdapter failed: %.*s\n", int(msg.length), msg.data);
          if (on_ready_) {
            on_ready_(false);
          }
          return;
        }
        adapter_ = std::move(a);
        requestDevice();
      });
}

void GHOST_ContextWGPUWeb::requestDevice()
{
  wgpu::DeviceDescriptor desc = {};
  desc.SetUncapturedErrorCallback(
      [](const wgpu::Device & /*d*/, wgpu::ErrorType type, wgpu::StringView msg) {
        std::printf("WGPUWeb: uncaptured error (%d): %.*s\n", int(type), int(msg.length), msg.data);
      });

  adapter_.RequestDevice(
      &desc,
      wgpu::CallbackMode::AllowSpontaneous,
      [this](wgpu::RequestDeviceStatus status, wgpu::Device d, wgpu::StringView msg) {
        if (status != wgpu::RequestDeviceStatus::Success || d == nullptr) {
          std::printf("WGPUWeb: RequestDevice failed: %.*s\n", int(msg.length), msg.data);
          if (on_ready_) {
            on_ready_(false);
          }
          return;
        }
        device_ = std::move(d);
        queue_ = device_.GetQueue();
        finishSetup();
      });
}

void GHOST_ContextWGPUWeb::finishSetup()
{
  /* The canvas-surface source is the key emdawnwebgpu-specific struct: native Dawn
   * spells it `SurfaceSourceCanvasHTMLSelector` (or platform SurfaceSource*), whereas
   * emdawnwebgpu uses `EmscriptenSurfaceSourceCanvasHTMLSelector`. See notes. */
  wgpu::EmscriptenSurfaceSourceCanvasHTMLSelector canvas_src = {};
  canvas_src.selector = canvas_selector_.c_str();

  wgpu::SurfaceDescriptor surf_desc = {};
  surf_desc.nextInChain = &canvas_src;
  surface_ = instance_.CreateSurface(&surf_desc);

  if (surface_ == nullptr) {
    std::printf("WGPUWeb: CreateSurface failed for '%s'\n", canvas_selector_.c_str());
    if (on_ready_) {
      on_ready_(false);
    }
    return;
  }

  /* BGRA8Unorm is the universally-supported browser canvas format; keep it fixed so
   * one render pipeline serves the surface. (GetCapabilities().formats[0] would be the
   * more general query — noted as a follow-up in the design doc.) */
  surface_format_ = wgpu::TextureFormat::BGRA8Unorm;
  configureSurface(width_, height_);

  /* NB (M4.T21): the M4.T12 "surface-proof" teal clear that used to live here was removed.
   * Now that the backend renders into the persistent offscreen back-buffer and
   * swapBufferRelease -> presentBackbuffer blits it onto the surface every frame, an
   * unconditional teal clear at setup would stomp the first presented frame(s) whenever
   * finishSetup re-runs (it can fire more than once during boot), leaving the canvas teal
   * instead of the Blender UI. The whole OffscreenCanvas -> device -> surface path is now
   * proven by the live UI compositing, not by a debug clear. */

  ready_ = true;
  if (on_ready_) {
    on_ready_(true);
  }
}

void GHOST_ContextWGPUWeb::configureSurface(uint32_t width, uint32_t height)
{
  if (surface_ == nullptr || device_ == nullptr) {
    return;
  }

  /* DETERMINISM: the WebGPU surface must match the canvas element's drawing-buffer
   * extent EXACTLY. GetCurrentTexture returns a texture sized to the live canvas, so a
   * surface configured to a stale/other size (the GHOST window's logical size, which the
   * shell or browser pane can diverge the canvas from — the r19 1800x1169-surface vs
   * 1280x720-canvas mismatch that blocked golden capture) mis-presents. Query the real
   * canvas extent HERE and prefer it; the caller's width/height is only a fallback for
   * when the canvas does not resolve (a worker without an OffscreenCanvas). */
  int cw = 0, ch = 0;
  emscripten_get_canvas_element_size(canvas_selector_.c_str(), &cw, &ch);
  const uint32_t w = (cw > 0) ? uint32_t(cw) : width;
  const uint32_t h = (ch > 0) ? uint32_t(ch) : height;
  if (w == 0 || h == 0) {
    return;
  }
  /* Idempotent: skip a redundant Configure when the extent is unchanged (repeated
   * resize events commonly report the same size). */
  if (configured_ && w == width_ && h == height_) {
    /* A transient resize allocation failure leaves the prior texture and extent
     * intact. Retry that one missing publication without redundantly configuring
     * the already-current surface. */
    ensureBackbuffer();
    return;
  }
  width_ = w;
  height_ = h;

  wgpu::SurfaceConfiguration config = {};
  config.device = device_;
  config.format = surface_format_;
  /* RenderAttachment is what the compositor draws into; CopySrc additionally lets the
   * frame be read back — OffscreenCanvas.convertToBlob() (the worker-side M4 capture path,
   * platform_web/shell/wgpu-preinit-worker.js) otherwise fails with "Readback of the source
   * image has failed" because a RenderAttachment-only canvas texture cannot be copied out.
   * The per-frame present (presentBackbuffer) is a RENDER PASS into the surface, NOT a
   * CopyTextureToTexture, so CopyDst is deliberately NOT requested: emdawnwebgpu rejects a
   * CopyDst canvas surface (the copy silently fails validation and the canvas stays stuck on
   * its last render-pass content). Both requested usages are universally supported. */
  config.usage = wgpu::TextureUsage::RenderAttachment | wgpu::TextureUsage::CopySrc;
  config.width = width_;
  config.height = height_;
  config.presentMode = wgpu::PresentMode::Fifo;
  config.alphaMode = wgpu::CompositeAlphaMode::Opaque;
  surface_.Configure(&config);
  configured_ = true;

  /* Match the persistent offscreen back-buffer to the new surface extent. */
  ensureBackbuffer();
}

/* --- Persistent offscreen back-buffer + present (M4.T21) --------------------- */

void GHOST_ContextWGPUWeb::ensureBackbuffer()
{
  if (device_ == nullptr || width_ == 0 || height_ == 0) {
    return;
  }
  if (backbuffer_ != nullptr && backbuffer_w_ == width_ && backbuffer_h_ == height_) {
    return; /* already the right size */
  }
  wgpu::TextureDescriptor td = {};
  td.label = "wgpu_web_backbuffer";
  td.dimension = wgpu::TextureDimension::e2D;
  td.size = {width_, height_, 1};
  td.format = surface_format_; /* BGRA8Unorm — same format the surface presents */
  td.mipLevelCount = 1;
  td.sampleCount = 1;
  /* RenderAttachment: the backend draws/composites here. TextureBinding: the present blit
   * textureLoad()s it into the surface (presentBackbuffer). CopySrc: the in-app
   * WM_window_pixels_read path can read it back (it now reads a LIVE persistent texture
   * instead of the destroyed transient surface). */
  td.usage = wgpu::TextureUsage::RenderAttachment | wgpu::TextureUsage::TextureBinding |
             wgpu::TextureUsage::CopySrc;
  if (!ghost_web::texture_replace_if_valid(
          [&]() { return device_.CreateTexture(&td); },
          backbuffer_,
          width_,
          height_,
          backbuffer_w_,
          backbuffer_h_))
  {
    std::printf("WGPUWeb: CreateTexture failed for %ux%u backbuffer\n", width_, height_);
  }
}

void GHOST_ContextWGPUWeb::ensurePresentPipeline()
{
  if (present_pipeline_ != nullptr) {
    return;
  }
  /* Fullscreen-triangle blit. The fragment shader textureLoad()s the offscreen at the
   * render target's integer pixel coordinate (@builtin(position)), so surface(x,y) =
   * backbuffer(x,y) EXACTLY: a 1:1 upright copy with no UV/clip flip to reason about and
   * no sampler needed. BGRA8Unorm textureLoad returns the un-swizzled RGBA vec4 and the
   * BGRA8Unorm target re-swizzles on store, so the colour round-trips correctly. */
  const char *wgsl =
      "@vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4<f32> {\n"
      "  var p = array<vec2<f32>, 3>(vec2<f32>(-1.0, -1.0), vec2<f32>(3.0, -1.0),\n"
      "                              vec2<f32>(-1.0, 3.0));\n"
      "  return vec4<f32>(p[i], 0.0, 1.0);\n"
      "}\n"
      "@group(0) @binding(0) var src: texture_2d<f32>;\n"
      "@fragment fn fs(@builtin(position) c: vec4<f32>) -> @location(0) vec4<f32> {\n"
      "  return textureLoad(src, vec2<i32>(i32(c.x), i32(c.y)), 0);\n"
      "}\n";
  if (!ghost_web::present_pipeline_create_if_valid(
          [&]() {
            wgpu::ShaderSourceWGSL wgsl_src = {};
            wgsl_src.code = wgsl;
            wgpu::ShaderModuleDescriptor sm_desc = {};
            sm_desc.nextInChain = &wgsl_src;
            return device_.CreateShaderModule(&sm_desc);
          },
          [&]() {
            wgpu::BindGroupLayoutEntry bgl_entry = {};
            bgl_entry.binding = 0;
            bgl_entry.visibility = wgpu::ShaderStage::Fragment;
            bgl_entry.texture.sampleType = wgpu::TextureSampleType::UnfilterableFloat;
            bgl_entry.texture.viewDimension = wgpu::TextureViewDimension::e2D;
            wgpu::BindGroupLayoutDescriptor bgl_desc = {};
            bgl_desc.entryCount = 1;
            bgl_desc.entries = &bgl_entry;
            return device_.CreateBindGroupLayout(&bgl_desc);
          },
          [&](const wgpu::BindGroupLayout &bind_group_layout) {
            wgpu::PipelineLayoutDescriptor pl_desc = {};
            pl_desc.bindGroupLayoutCount = 1;
            pl_desc.bindGroupLayouts = &bind_group_layout;
            return device_.CreatePipelineLayout(&pl_desc);
          },
          [&](const wgpu::ShaderModule &module, const wgpu::PipelineLayout &pipeline_layout) {
            wgpu::ColorTargetState color_target = {};
            color_target.format = surface_format_;
            wgpu::FragmentState frag = {};
            frag.module = module;
            frag.entryPoint = "fs";
            frag.targetCount = 1;
            frag.targets = &color_target;

            wgpu::RenderPipelineDescriptor rp_desc = {};
            rp_desc.layout = pipeline_layout;
            rp_desc.vertex.module = module;
            rp_desc.vertex.entryPoint = "vs";
            rp_desc.primitive.topology = wgpu::PrimitiveTopology::TriangleList;
            rp_desc.fragment = &frag;
            return device_.CreateRenderPipeline(&rp_desc);
          },
          present_bgl_,
          present_pipeline_))
  {
    return;
  }
}

void GHOST_ContextWGPUWeb::presentBackbuffer()
{
  if (surface_ == nullptr || device_ == nullptr || backbuffer_ == nullptr) {
    return;
  }
  wgpu::SurfaceTexture st = {};
  surface_.GetCurrentTexture(&st);
  if (st.texture == nullptr) {
    return;
  }
  ensurePresentPipeline();
  if (present_pipeline_ == nullptr) {
    return;
  }

  if (!ghost_web::present_frame_encode_submit_if_valid(
          [&]() { return backbuffer_.CreateView(); },
          [&]() { return st.texture.CreateView(); },
          [&](const wgpu::TextureView &source_view) {
            wgpu::BindGroupEntry bg_entry = {};
            bg_entry.binding = 0;
            bg_entry.textureView = source_view;
            wgpu::BindGroupDescriptor bg_desc = {};
            bg_desc.layout = present_bgl_;
            bg_desc.entryCount = 1;
            bg_desc.entries = &bg_entry;
            return device_.CreateBindGroup(&bg_desc);
          },
          [&]() { return device_.CreateCommandEncoder(); },
          [&](wgpu::CommandEncoder &encoder, const wgpu::TextureView &target_view) {
            wgpu::RenderPassColorAttachment ca = {};
            ca.view = target_view;
            ca.loadOp = wgpu::LoadOp::Clear;
            ca.storeOp = wgpu::StoreOp::Store;
            ca.clearValue = {0.0, 0.0, 0.0, 1.0};
            wgpu::RenderPassDescriptor rp = {};
            rp.colorAttachmentCount = 1;
            rp.colorAttachments = &ca;
            return encoder.BeginRenderPass(&rp);
          },
          [&](wgpu::RenderPassEncoder &pass, const wgpu::BindGroup &bind_group) {
            pass.SetPipeline(present_pipeline_);
            pass.SetBindGroup(0, bind_group);
            pass.Draw(3);
          },
          [&](const wgpu::CommandBuffer &command_buffer) {
            queue_.Submit(1, &command_buffer);
          }))
  {
    return;
  }

  /* Bounded "present path live" marker (first 2 frames only): confirms a complete
   * command buffer reached the queue. Capped so 120 fps cannot flood. */
  static int present_log_count = 0;
  if (present_log_count < 2) {
    std::printf("WGPUWeb: presentBackbuffer frame %d — surface %ux%u -> canvas (offscreen blit)\n",
                present_log_count,
                st.texture.GetWidth(),
                st.texture.GetHeight());
    present_log_count++;
  }
  /* ghost-keepalive: record the present so the idle keepalive can tell frames are being
   * produced and the no-idle-burn proof can show they are NOT at idle. */
  ghost_web::note_present();
  /* The browser auto-presents `st.texture` when this rAF tick yields — one acquire, one
   * render pass, one submit, all in-tick, so nothing references the surface after it is
   * destroyed. */
}
