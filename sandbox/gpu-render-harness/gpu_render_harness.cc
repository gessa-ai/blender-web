/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * cycle-6 step 2 — BROWSER RENDER HARNESS (the pixels-in-the-link vehicle).
 *
 * Boots the REAL Blender WebGPU backend (libbf_gpu.a) in a browser tab and drives
 * the gpu-module API to render a triangle offscreen:
 *   GPU_backend_type_selection_set(WEBGPU)
 *   -> GHOST_ContextWGPUWeb (the proven emdawnwebgpu web context) initAsync
 *   -> [ready callback] GPU_context_create(borrow device) -> GPU_init
 *   -> offscreen GPUFrameBuffer + GPUTexture, clear, immBindBuiltinProgram
 *      (GPU_SHADER_3D_UNIFORM_COLOR — this triggers the real GLSL->SPIR-V->WGSL
 *       shader compile -> WGPUShader::finalize)
 *   -> immBegin/immEnd a triangle -> GPU_texture_read -> assert pixels -> PNG to page.
 *
 * Async bootstrap: the web context acquires the device off the event loop, so ALL
 * gpu-module work runs inside on_device_ready (EXIT_RUNTIME=0, no JSPI — ADR-003).
 *
 * Model: source/blender/gpu/tests/gpu_testing.cc (bootstrap, minus gtest) +
 * platform_web/ghost/harness-wgpu/test_wgpu_web.cc (async boot + readback->PNG). */

#include <cstdint>
#include <cstdio>

#include <emscripten/emscripten.h>

#include "GHOST_ContextWGPUWeb.hh"

#include "CLG_log.h"

#include "GPU_context.hh"
#include "GPU_framebuffer.hh"
#include "GPU_immediate.hh"
#include "GPU_init_exit.hh"
#include "GPU_platform.hh"
#include "GPU_shader_builtin.hh"
#include "GPU_state.hh"
#include "GPU_texture.hh"
#include "GPU_vertex_format.hh"

#include "gpu_capabilities_private.hh"
#include "gpu_platform_private.hh"

EM_JS(void, hreport, (const char *msg), {
  const s = UTF8ToString(msg);
  if (typeof globalThis.wgpuReport === 'function') globalThis.wgpuReport(s);
  else console.log(s);
});

EM_JS(void, hshow, (uintptr_t ptr, int w, int h), {
  const img = new ImageData(w, h);
  for (let i = 0; i < w * h * 4; i++) img.data[i] = HEAPU8[ptr + i]; /* RGBA8 */
  const cv = document.createElement('canvas');
  cv.width = w; cv.height = h;
  cv.getContext('2d').putImageData(img, 0, 0);
  const el = document.getElementById('readback-img');
  if (el) el.src = cv.toDataURL('image/png');
  console.log('PNG_DATA_URL:' + (el ? el.src.length : 0));
});

using namespace blender;

static GHOST_ContextWGPUWeb *g_ctx = nullptr;
static constexpr int W = 256, H = 256;

static void render_with_gpu_module()
{
  gpu::Texture *tex = GPU_texture_create_2d(
      "harness_color", W, H, 1, gpu::TextureFormat::UNORM_8_8_8_8,
      GPU_TEXTURE_USAGE_ATTACHMENT | GPU_TEXTURE_USAGE_HOST_READ, nullptr);
  hreport("GPU_texture_create_2d OK");

  gpu::FrameBuffer *fb = GPU_framebuffer_create("harness_fb");
  GPU_framebuffer_texture_attach(fb, tex, 0, 0);
  GPU_framebuffer_bind(fb);
  GPU_framebuffer_clear_color(fb, double4(0.10, 0.45, 0.85, 1.0));
  hreport("framebuffer bound + cleared to (0.10, 0.45, 0.85, 1.0)");

  /* FIRST IN-TAB PIXELS — read back the CLEARED framebuffer through the real WebGPU
   * backend (render-pass clear -> texture->buffer copy -> map-read -> row-flip) and show
   * it as a PNG. This is a genuine GPU-produced frame from the real Blender WebGPU
   * backend running in a browser tab, independent of the immediate-mode draw below. */
  GPU_finish();
  {
    uint8_t *px = (uint8_t *)GPU_texture_read(tex, GPU_DATA_UBYTE, 0);
    if (px) {
      const uint8_t *c = px + (size_t(H / 2) * W + (W / 2)) * 4; /* center RGBA */
      char buf[160];
      std::snprintf(buf, sizeof(buf),
                    "FIRST PIXELS (clear readback) center RGBA=(%d,%d,%d,%d) — expect ~(26,115,217,255)",
                    c[0], c[1], c[2], c[3]);
      hreport(buf);
      const bool ok = (c[2] > 180 && c[0] < 80 && c[3] > 200);
      hreport(ok ? "RENDER PASS: cleared framebuffer read back correctly in-tab"
                 : "RENDER note: clear colour unexpected");
      hshow((uintptr_t)px, W, H);
    }
    else {
      hreport("GPU_texture_read returned null (clear readback)");
    }
  }

  /* Now attempt the immediate-mode triangle (exercises the just-compiled builtin shader
   * through the draw path). The clear-readback PNG above is already captured, so if the
   * WGPUImmediate path aborts, first pixels are unaffected. */
  GPUVertFormat *format = immVertexFormat();
  const uint pos = GPU_vertformat_attr_add_legacy(format, "pos", GPU_COMP_F32, 2, GPU_FETCH_FLOAT);
  hreport("binding GPU_SHADER_3D_UNIFORM_COLOR (-> shader finalize)");
  immBindBuiltinProgram(GPU_SHADER_3D_UNIFORM_COLOR);
  hreport("SHADER FINALIZE OK — builtin program bound");

  immUniformColor4f(1.0f, 0.3f, 0.1f, 1.0f);
  immBegin(GPU_PRIM_TRIS, 3);
  immVertex2f(pos, 0.0f, 0.5f);
  immVertex2f(pos, -0.5f, -0.5f);
  immVertex2f(pos, 0.5f, -0.5f);
  immEnd();
  immUnbindProgram();
  hreport("DRAW OK — triangle submitted via imm");

  GPU_finish();
  {
    uint8_t *px = (uint8_t *)GPU_texture_read(tex, GPU_DATA_UBYTE, 0);
    if (px) {
      const uint8_t *c = px + (size_t(H / 2) * W + (W / 2)) * 4; /* center RGBA */
      char buf[160];
      std::snprintf(buf, sizeof(buf), "TRIANGLE readback center RGBA=(%d,%d,%d,%d)", c[0], c[1], c[2], c[3]);
      hreport(buf);
      const bool ok = (c[0] > 180 && c[2] < 80 && c[3] > 200);
      hreport(ok ? "RENDER PASS: center is the orange triangle" : "RENDER note: center not triangle colour");
      hshow((uintptr_t)px, W, H);
    }
    else {
      hreport("GPU_texture_read returned null (triangle readback)");
    }
  }

  GPU_framebuffer_free(fb);
  GPU_texture_free(tex);
}

static void on_device_ready(bool ok)
{
  if (!ok) {
    hreport("CONTEXT FAIL: no WebGPU device");
    return;
  }
  hreport("CONTEXT OK: emdawnwebgpu device acquired");

  GPUContext *ctx = GPU_context_create(nullptr, g_ctx);
  GPU_context_active_set(ctx);
  hreport("GPU_context_create OK (WGPUContext borrowed the device)");

  /* HARNESS WORKAROUND — cross-thread WebGPU-object gap (routed to lane A / ghost-web):
   * emdawnwebgpu keeps its WebGPU objects (Device/Queue) in the MAIN thread's per-thread
   * JS object table, so a ShaderCompiler worker thread cannot see the device —
   * wgpuDeviceCreateShaderModule() aborts in getJsObject() on the worker. Setting the
   * main-context-workaround capability makes ShaderCompiler create no worker and compile
   * on the calling (main) thread, where the device is valid. Must be set before
   * GPU_init(), which is where WGPUBackend::init_resources() builds the ShaderCompiler.
   * The real backend needs a cross-thread device strategy (proxy-to-main or per-worker
   * device) — flagged for lane A. */
  blender::gpu::GCaps.use_main_context_workaround = true;

  /* HARNESS WORKAROUND — WebGPU-backend gap (routed to lane A): unlike VKBackend, the
   * WebGPU backend never calls platform_init(), so the GPUPlatformGlobal (GPG) stays
   * uninitialised and GPU_type_matches() — called from standard_defines() during the
   * shader compile — asserts GPG.initialized (gpu_platform.cc:179). Mirror what
   * VKBackend::platform_init does, with WebGPU identity, so the compile can proceed.
   * Must be set BEFORE GPU_init(): with the main-context workaround GPU_init warms up the
   * builtin shaders synchronously (on this thread) and would otherwise hit the assert.
   * The real fix belongs in WGPUBackend (webgpu/, lane A). */
  blender::gpu::GPG.init(GPU_DEVICE_ANY,
                         GPU_OS_ANY,
                         GPU_DRIVER_ANY,
                         GPU_SUPPORT_LEVEL_SUPPORTED,
                         GPU_BACKEND_WEBGPU,
                         "emdawnwebgpu",
                         "WebGPU",
                         "1.0",
                         GPU_ARCHITECTURE_IMR);
  hreport("GPG.init + main-context-workaround set (harness workarounds for WebGPU-backend gaps)");

  GPU_init();
  hreport("GPU_init OK");

  GPU_render_begin();
  render_with_gpu_module();
  GPU_render_end();
}

int main()
{
  CLG_init();
  hreport("[gpu-harness] backend = WEBGPU; creating GHOST_ContextWGPUWeb on '#gpucanvas'");
  GPU_backend_type_selection_set(GPU_BACKEND_WEBGPU);

  GHOST_ContextParams params = {};
  g_ctx = new GHOST_ContextWGPUWeb(
      params, "#gpucanvas", ghost_web::DrawingContextMode::PresentableWindow);
  g_ctx->initAsync(W, H, on_device_ready);
  return 0; /* EXIT_RUNTIME=0 — spontaneous callbacks drive the rest */
}
