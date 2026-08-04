/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * M3.T10.pre — WebGPU state-table mapping (standalone, drop-in for
 * `source/blender/gpu/webgpu/wgpu_state.cc` / `wgpu_pipeline.cc`).
 *
 * The complete mechanical mapping from Blender's fixed-function state model
 * (GPU_state.hh) to WebGPU pipeline descriptor structs:
 *   - GPUBlend (16 arms)   → wgpu::BlendState {color, alpha} (X-macro table)
 *   - GPUDepthTest         → depthCompare + depthWriteEnabled
 *   - GPUStencilTest/Op    → wgpu::StencilFaceState front/back (incl. shadow-volume
 *                            increment/decrement-wrap counting)
 *   - GPUFaceCullTest      → wgpu::CullMode ; front-face winding
 *   - GPUWriteMask         → wgpu::ColorWriteMask
 *   - GPUProvokingVertex   → NO WebGPU control (documented; emulate in-shader)
 *
 * SOURCE OF TRUTH (read-only recon, cited in notes/gpu-t6-t10pre-findings.md):
 * `opengl/gl_state.cc::set_blend` (blend factors, :324-451) — verified IDENTICAL
 * in the Vulkan (`vk_graphics_pipeline.hh:603-724`) and Metal
 * (`mtl_state.mm:394+`) backends — plus set_depth_test/set_stencil_op/
 * set_backface_culling/set_provoking_vert in the same file. */

#pragma once

#include <cstdint>

#include "webgpu/webgpu_cpp.h"

namespace blender::gpu::webgpu {

/* ---- Blender state enums (mirror GPU_state.hh, same order) ----------------- */

enum class GPUBlend : uint8_t {
  NONE = 0, ALPHA, ALPHA_PREMULT, ADDITIVE, ADDITIVE_PREMULT, MULTIPLY, SUBTRACT,
  INVERT, MIN, MAX, OIT, BACKGROUND, CUSTOM, ALPHA_UNDER_PREMUL,
  OVERLAY_MASK_FROM_ALPHA, TRANSPARENCY,
};
enum class GPUDepthTest : uint8_t {
  NONE = 0, ALWAYS, LESS, LESS_EQUAL, EQUAL, GREATER, GREATER_EQUAL,
};
enum class GPUStencilTest : uint8_t { NONE = 0, ALWAYS, EQUAL, NEQUAL };
enum class GPUStencilOp : uint8_t { NONE = 0, REPLACE, COUNT_DEPTH_PASS, COUNT_DEPTH_FAIL };
enum class GPUFaceCullTest : uint8_t { NONE = 0, FRONT, BACK };
enum class GPUProvokingVertex : uint8_t { LAST = 0, FIRST = 1 };
enum GPUWriteMask : uint32_t {
  GPU_WRITE_NONE = 0, GPU_WRITE_RED = 1u << 0, GPU_WRITE_GREEN = 1u << 1,
  GPU_WRITE_BLUE = 1u << 2, GPU_WRITE_ALPHA = 1u << 3, GPU_WRITE_DEPTH = 1u << 4,
  GPU_WRITE_STENCIL = 1u << 5,
  GPU_WRITE_COLOR = GPU_WRITE_RED | GPU_WRITE_GREEN | GPU_WRITE_BLUE | GPU_WRITE_ALPHA,
};

/* ---- Mapping results ------------------------------------------------------- */

struct BlendMapping {
  GPUBlend blend;
  const char *name;
  bool enabled;        /* false for GPU_BLEND_NONE → omit the BlendState */
  bool dual_source;    /* true for GPU_BLEND_CUSTOM → needs DualSourceBlending feature + @blend_src */
  wgpu::BlendComponent color;
  wgpu::BlendComponent alpha;
};

struct DepthMapping {
  bool test_enabled;               /* false → depthWrite off, compare Always */
  wgpu::CompareFunction compare;
};

struct StencilMapping {
  bool enabled;                    /* false for GPU_STENCIL_NONE */
  wgpu::StencilFaceState front;
  wgpu::StencilFaceState back;
};

/* ---- The mapping API ------------------------------------------------------- */

BlendMapping to_blend(GPUBlend blend);
DepthMapping to_depth(GPUDepthTest test);
StencilMapping to_stencil(GPUStencilTest test, GPUStencilOp op);
wgpu::CullMode to_cull_mode(GPUFaceCullTest cull);
wgpu::FrontFace to_front_face(bool invert);          /* GL default CCW; invert → CW */
wgpu::ColorWriteMask to_color_write_mask(uint32_t gpu_write_mask);

/** WebGPU has NO provoking-vertex control (flat interpolation samples the FIRST
 * vertex); Blender defaults to LAST. Returns true iff the requested convention is
 * native to WebGPU (i.e. FIRST). LAST must be emulated in-shader (Metal precedent:
 * mtl_state.mm:384-391). No pipeline knob exists — this is a shader-codegen task. */
bool provoking_vertex_is_native(GPUProvokingVertex vert);

/* Whole-table iteration for the harness / reflection. */
const BlendMapping *blend_table(size_t &count);
const char *to_string(GPUBlend b);

}  // namespace blender::gpu::webgpu
