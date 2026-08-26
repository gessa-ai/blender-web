/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * \ingroup GHOST-web
 *
 * Standalone harness for GHOST_ContextWGPUWeb: proves OUR GHOST context pattern
 * against the BROWSER's WebGPU (emdawnwebgpu). Two paths:
 *   1. onscreen  — render a triangle to the canvas surface and present it;
 *   2. offscreen — render the same triangle to an RGBA texture, copy to a buffer,
 *      MapAsync-read it back, assert the center pixel is the triangle colour, and
 *      hand the pixels to JS to display as an <img> (the cycle-6 render->readback->
 *      display shape).
 *
 * Everything is callback-chained off the event loop (device request, device request,
 * buffer map) — NO JSPI, NO blocking WaitAny. This is the "boring" wait shape that
 * respects ADR-003's suspend-topology rule; see notes/ghost-web-wgpu-context.md.
 */

#include <cstdint>
#include <cstdio>

#include <emscripten/emscripten.h>

#include "GHOST_ContextWGPUWeb.hh"

/* Hardcoded triangle (the shader chain is proven elsewhere). Orange on black:
 * center pixel is inside the triangle, so readback asserts a rendered pixel. */
static const char *kWGSL = R"(
@vertex fn vs(@builtin(vertex_index) i : u32) -> @builtin(position) vec4f {
  var p = array<vec2f, 3>(vec2f(0.0, 0.5), vec2f(-0.5, -0.5), vec2f(0.5, -0.5));
  return vec4f(p[i], 0.0, 1.0);
}
@fragment fn fs() -> @location(0) vec4f { return vec4f(1.0, 0.3, 0.1, 1.0); }
)";

/* Report a line to the page + console. */
EM_JS(void, wgpu_report, (const char *msg), {
  const s = UTF8ToString(msg);
  if (typeof globalThis.wgpuReport === 'function') globalThis.wgpuReport(s);
  else console.log(s);
});

/* Turn the mapped BGRA8 readback (with 256-aligned row stride) into an <img>. */
EM_JS(void, wgpu_show_readback, (uintptr_t ptr, int w, int h, int bpr), {
  const img = new ImageData(w, h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const s = ptr + y * bpr + x * 4;   // BGRA
      const d = (y * w + x) * 4;         // RGBA
      img.data[d + 0] = HEAPU8[s + 2];
      img.data[d + 1] = HEAPU8[s + 1];
      img.data[d + 2] = HEAPU8[s + 0];
      img.data[d + 3] = HEAPU8[s + 3];
    }
  }
  const cv = document.createElement('canvas');
  cv.width = w; cv.height = h;
  cv.getContext('2d').putImageData(img, 0, 0);
  const el = document.getElementById('readback-img');
  if (el) el.src = cv.toDataURL('image/png');
});

static GHOST_ContextWGPUWeb *g_ctx = nullptr;
static wgpu::Buffer g_readback; /* outlives the async map */

static constexpr uint32_t OFF = 256;      /* offscreen size */
static constexpr uint32_t BPR = OFF * 4;  /* 1024, already 256-aligned */

static wgpu::RenderPipeline make_pipeline(wgpu::Device dev, wgpu::TextureFormat fmt)
{
  wgpu::ShaderSourceWGSL wgsl = {};
  wgsl.code = kWGSL;
  wgpu::ShaderModuleDescriptor sm_desc = {};
  sm_desc.nextInChain = &wgsl;
  wgpu::ShaderModule sm = dev.CreateShaderModule(&sm_desc);

  wgpu::ColorTargetState color = {};
  color.format = fmt;
  wgpu::FragmentState frag = {};
  frag.module = sm;
  frag.entryPoint = "fs";
  frag.targetCount = 1;
  frag.targets = &color;

  wgpu::RenderPipelineDescriptor rp = {};
  rp.vertex.module = sm;
  rp.vertex.entryPoint = "vs";
  rp.primitive.topology = wgpu::PrimitiveTopology::TriangleList;
  rp.multisample.count = 1;
  rp.multisample.mask = 0xFFFFFFFF;
  rp.fragment = &frag;
  return dev.CreateRenderPipeline(&rp);
}

static void draw_triangle(wgpu::CommandEncoder enc,
                          wgpu::TextureView view,
                          wgpu::RenderPipeline pipe)
{
  wgpu::RenderPassColorAttachment ca = {};
  ca.view = view;
  ca.loadOp = wgpu::LoadOp::Clear;
  ca.storeOp = wgpu::StoreOp::Store;
  ca.clearValue = {0.0, 0.0, 0.0, 1.0}; /* black -> any non-black pixel is rendered */

  wgpu::RenderPassDescriptor rpd = {};
  rpd.colorAttachmentCount = 1;
  rpd.colorAttachments = &ca;

  wgpu::RenderPassEncoder pass = enc.BeginRenderPass(&rpd);
  pass.SetPipeline(pipe);
  pass.Draw(3);
  pass.End();
}

static void render_offscreen_and_readback(wgpu::Device dev, wgpu::Queue queue)
{
  wgpu::TextureDescriptor td = {};
  td.size = {OFF, OFF, 1};
  td.format = wgpu::TextureFormat::BGRA8Unorm;
  td.usage = wgpu::TextureUsage::RenderAttachment | wgpu::TextureUsage::CopySrc;
  td.dimension = wgpu::TextureDimension::e2D;
  td.mipLevelCount = 1;
  td.sampleCount = 1;
  wgpu::Texture tex = dev.CreateTexture(&td);

  wgpu::BufferDescriptor bd = {};
  bd.size = size_t(BPR) * OFF;
  bd.usage = wgpu::BufferUsage::CopyDst | wgpu::BufferUsage::MapRead;
  g_readback = dev.CreateBuffer(&bd);

  wgpu::RenderPipeline pipe = make_pipeline(dev, wgpu::TextureFormat::BGRA8Unorm);
  wgpu::CommandEncoder enc = dev.CreateCommandEncoder();
  draw_triangle(enc, tex.CreateView(), pipe);

  wgpu::TexelCopyTextureInfo src = {};
  src.texture = tex;
  src.origin = {0, 0, 0};
  src.aspect = wgpu::TextureAspect::All;
  wgpu::TexelCopyBufferInfo dst = {};
  dst.buffer = g_readback;
  dst.layout.offset = 0;
  dst.layout.bytesPerRow = BPR;
  dst.layout.rowsPerImage = OFF;
  wgpu::Extent3D ext = {OFF, OFF, 1};
  enc.CopyTextureToBuffer(&src, &dst, &ext);

  wgpu::CommandBuffer cb = enc.Finish();
  queue.Submit(1, &cb);

  const size_t size = size_t(BPR) * OFF;
  g_readback.MapAsync(
      wgpu::MapMode::Read, 0, size, wgpu::CallbackMode::AllowSpontaneous,
      [size](wgpu::MapAsyncStatus status, wgpu::StringView msg) {
        if (status != wgpu::MapAsyncStatus::Success) {
          std::printf("readback map failed: %.*s\n", int(msg.length), msg.data);
          wgpu_report("READBACK FAIL: map error");
          return;
        }
        const uint8_t *data = (const uint8_t *)g_readback.GetConstMappedRange(0, size);
        const uint8_t *px = data + size_t(OFF / 2) * BPR + (OFF / 2) * 4; /* center, BGRA */
        const int B = px[0], G = px[1], R = px[2], A = px[3];
        char buf[128];
        std::snprintf(buf, sizeof(buf), "readback center BGRA=(%d,%d,%d,%d)", B, G, R, A);
        wgpu_report(buf);
        wgpu_show_readback((uintptr_t)data, OFF, OFF, BPR);
        const bool pass = (R > 180 && B < 80 && A > 200); /* the orange triangle */
        wgpu_report(pass ? "READBACK PASS: triangle rendered (center is orange)"
                         : "READBACK FAIL: center not triangle colour");
        g_readback.Unmap();
      });
}

static void on_device_ready(bool ok)
{
  if (!ok) {
    wgpu_report("CONTEXT FAIL: no WebGPU device/surface");
    return;
  }
  wgpu_report("CONTEXT OK: emdawnwebgpu device + canvas surface acquired");
  wgpu::Device dev = g_ctx->getDevice();
  wgpu::Queue queue = g_ctx->getQueue();

  /* 1. Onscreen: render + present to the canvas surface. */
  wgpu::SurfaceTexture st = {};
  g_ctx->getSurface().GetCurrentTexture(&st);
  const bool surface_ready =
      (st.status == wgpu::SurfaceGetCurrentTextureStatus::SuccessOptimal ||
       st.status == wgpu::SurfaceGetCurrentTextureStatus::SuccessSuboptimal) &&
      st.texture != nullptr;
  if (surface_ready) {
    wgpu::RenderPipeline pipe = make_pipeline(dev, g_ctx->getSurfaceFormat());
    wgpu::CommandEncoder enc = dev.CreateCommandEncoder();
    draw_triangle(enc, st.texture.CreateView(), pipe);
    wgpu::CommandBuffer cb = enc.Finish();
    queue.Submit(1, &cb);
    /* API DELTA: emdawnwebgpu does NOT support wgpuSurfacePresent (it aborts with
     * "use requestAnimationFrame instead"). Unlike native Dawn, the browser
     * auto-presents the configured canvas when control returns to the event loop.
     * So we do NOT call Present() here — returning from this callback presents it. */
    wgpu_report("ONSCREEN OK: triangle submitted (browser auto-presents on yield)");
  }
  else {
    wgpu_report("ONSCREEN FAIL: no surface texture");
  }

  /* 2. Offscreen render -> readback -> display. */
  render_offscreen_and_readback(dev, queue);
}

int main()
{
  wgpu_report("[harness] creating GHOST_ContextWGPUWeb on '#gpucanvas'");
  GHOST_ContextParams params = {}; /* GHOST_Context base params (unused by the web ctx) */
  g_ctx = new GHOST_ContextWGPUWeb(
      params, "#gpucanvas", ghost_web::DrawingContextMode::PresentableWindow);
  g_ctx->initAsync(320, 240, on_device_ready);
  /* EXIT_RUNTIME=0: keep the runtime alive for the spontaneous callbacks. */
  return 0;
}
