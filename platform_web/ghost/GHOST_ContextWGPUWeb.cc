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

#include <cstdint>
#include <cstdio>
#include <utility>

#include <emscripten/emscripten.h>
#include <emscripten/html5.h>

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
  /* Browser auto-presents the configured canvas on event-loop yield — no Present(). */
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

  /* M4.T12 surface-proof: clear the freshly-configured surface to a recognizable
   * colour and let the browser auto-present it, proving the whole OffscreenCanvas ->
   * device -> surface -> configure -> present path is live end-to-end IN THE TAB. This
   * is the GHOST surface layer ONLY: Blender's window compositor renders into its own
   * default frame-buffer (Context::back_left), which the WebGPU backend does not yet
   * point at this surface (there is no WGPUContext::sync_backbuffer equivalent — the
   * Vulkan backend sets back_left's colour attachment from the swap image in
   * vk_context.cc:67). Until that backend seam lands, every window draw hits Dawn
   * "Render pass has no attachments" and the canvas shows THIS clear, not the UI. A
   * distinct teal so it is unmistakably the surface proof, not a Blender theme colour. */
  {
    wgpu::SurfaceTexture st = {};
    surface_.GetCurrentTexture(&st);
    if (st.texture != nullptr) {
      wgpu::RenderPassColorAttachment ca = {};
      ca.view = st.texture.CreateView();
      ca.loadOp = wgpu::LoadOp::Clear;
      ca.storeOp = wgpu::StoreOp::Store;
      ca.clearValue = {0.05, 0.35, 0.42, 1.0};
      wgpu::RenderPassDescriptor rp = {};
      rp.colorAttachmentCount = 1;
      rp.colorAttachments = &ca;
      wgpu::CommandEncoder enc = device_.CreateCommandEncoder();
      wgpu::RenderPassEncoder pass = enc.BeginRenderPass(&rp);
      pass.End();
      wgpu::CommandBuffer cb = enc.Finish();
      queue_.Submit(1, &cb);
      std::printf("WGPUWeb: surface-proof cleared '%s' (%ux%u) — GHOST surface path live "
                  "end-to-end (UI pending backend sync_backbuffer)\n",
                  canvas_selector_.c_str(), width_, height_);
    }
    else {
      std::printf("WGPUWeb: surface-proof GetCurrentTexture returned null (status=%d)\n",
                  int(st.status));
    }
  }

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
   * Both usages are universally supported for a browser canvas surface. */
  config.usage = wgpu::TextureUsage::RenderAttachment | wgpu::TextureUsage::CopySrc;
  config.width = width_;
  config.height = height_;
  config.presentMode = wgpu::PresentMode::Fifo;
  config.alphaMode = wgpu::CompositeAlphaMode::Opaque;
  surface_.Configure(&config);
  configured_ = true;
}
