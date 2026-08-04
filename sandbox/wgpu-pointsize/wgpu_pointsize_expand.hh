/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * M3.pointsize.pre — gl_PointSize → instanced-quad expansion prototype.
 *
 * WebGPU points are always 1px and WGSL has NO point-size builtin (the one raster
 * gap left by T10.pre). Metal/Vulkan keep the `gl_PointSize`/`[[point_size]]`
 * builtin; WGSL does not, so every `GPU_PRIM_POINTS` shader that writes
 * `gl_PointSize` must be rewritten to draw an instanced quad per point, sizing it
 * in the vertex shader and replacing `gl_PointCoord` with an interpolated UV.
 *
 * This module encodes that mechanical rewrite for the REPRESENTATIVE shader —
 * `gpu_shader_3D_point_uniform_size_aa` (uniform size, GPU_PRIM_POINTS, circular
 * AA via gl_PointCoord; upstream vert/frag read at the pin) — as drop-in GLSL that
 * compiles through the T7.pre chain (shaderc→Tint→WGSL) and renders on Dawn. The
 * `PointExpansion` struct documents the transform so the 8-shader conversion is
 * rote. See notes/gpu-pointsize-prototype.md. */

#pragma once

#include <cstdint>
#include <vector>

#include "wgpu_shader_interface_map.hh"  // T7.pre ResourceDesc

namespace blender::gpu::webgpu {

/** The rewritten vertex shader: instanced-quad expansion. `pos` is a PER-INSTANCE
 * attribute (one per point); `gl_VertexIndex` (0..3) selects the quad corner. */
const char *rewritten_point_vert();

/** The rewritten fragment shader: identical AA math, `gl_PointCoord` replaced by
 * the interpolated `v_uv` output of the vertex shader. */
const char *rewritten_point_frag();

/** Resource layout (create-info shaped) for the rewritten pair: one UBO at
 * binding 0 (mvp, color, viewport, size) visible to both stages. */
std::vector<ResourceDesc> point_resources();

/** std140 layout of the Globals UBO the shaders read (96 bytes). */
struct alignas(16) PointGlobals {
  float mvp[16];       /* offset 0  */
  float color[4];      /* offset 64 */
  float viewport[2];   /* offset 80 (pixels) */
  float size;          /* offset 88 (point size in pixels) */
  float pad_;          /* offset 92 */
};                     /* size 96 */

/** The four triangle-strip quad corners in [-0.5, 0.5]^2 (matches the vertex
 * shader's `corners[]`). Exposed for documentation / cross-check. */
const float *quad_corners(uint32_t &count);

}  // namespace blender::gpu::webgpu
