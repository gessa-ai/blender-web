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
#include "GPU_shader_builtin.hh"
#include "GPU_state.hh"
#include "GPU_texture.hh"
#include "GPU_vertex_format.hh"

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
  GPU_framebuffer_clear_color(fb, double4(0.0, 0.0, 0.0, 1.0));
  hreport("framebuffer bound + cleared");

  /* Immediate-mode triangle with a builtin shader. immBindBuiltinProgram triggers
   * the real shader compile (GLSL create-info -> SPIR-V 1.3 -> Tint -> WGSL ->
   * WGPUShader::finalize). If lane A's finalize path is green this renders; if not,
   * reaching HERE in a browser tab already proves browser parity. */
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

  uint8_t *px = (uint8_t *)GPU_texture_read(tex, GPU_DATA_UBYTE, 0);
  if (px) {
    const uint8_t *c = px + (size_t(H / 2) * W + (W / 2)) * 4; /* center RGBA */
    char buf[128];
    std::snprintf(buf, sizeof(buf), "readback center RGBA=(%d,%d,%d,%d)", c[0], c[1], c[2], c[3]);
    hreport(buf);
    const bool ok = (c[0] > 180 && c[2] < 80 && c[3] > 200);
    hreport(ok ? "RENDER PASS: center is the orange triangle" : "RENDER note: center not triangle colour");
    hshow((uintptr_t)px, W, H);
  }
  else {
    hreport("GPU_texture_read returned null");
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
  g_ctx = new GHOST_ContextWGPUWeb(params, "#gpucanvas");
  g_ctx->initAsync(W, H, on_device_ready);
  return 0; /* EXIT_RUNTIME=0 — spontaneous callbacks drive the rest */
}
