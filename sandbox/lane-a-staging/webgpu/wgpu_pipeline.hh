/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_pipeline.hh @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * WebGPU render-pipeline assembly + cache. A `wgpu::RenderPipeline` bakes together
 * everything the draw path needs that WebGPU makes immutable: the compiled WGSL
 * modules (lane A's WGPUShader), the fixed-function state (B2's wgpu_state_table),
 * the vertex-buffer layout (GPUVertFormat + the shader's input locations), and the
 * render-target formats (the bound framebuffer's attachments). wgpu_batch opens a
 * render pass and calls get_render_pipeline() to select/build the pipeline for the
 * current (shader, geometry, state, targets, primitive) tuple. Pipelines are cached
 * on a hash of that tuple. */

#pragma once

#include <cstdint>
#include <unordered_map>

#include "webgpu/webgpu_cpp.h"

#include "GPU_primitive.hh"
#include "GPU_vertex_format.hh"

#include "gpu_state_private.hh" /* GPUState / GPUStateMutable */

namespace blender::gpu {

class WGPUShader;

namespace webgpu {

/** The state that selects a render pipeline (its cache key). Framebuffer target
 * formats + primitive + fixed-function state + the shader + the vertex signature. */
struct PipelineInfo {
  WGPUShader *shader = nullptr;
  const GPUVertFormat *vertex_format = nullptr; /* null = procedural (no vbo). */
  GPUState state = {};
  GPUStateMutable mutable_state = {};
  wgpu::TextureFormat color_formats[8] = {};
  int color_count = 0;
  wgpu::TextureFormat depth_format = wgpu::TextureFormat::Undefined;
  GPUPrimType prim_type = GPU_PRIM_TRIS;
  /* Apply the ADR-005 clip-space Y-flip + winding swap (true = offscreen, the default).
   * false only for the surface-backed window backbuffer, which composites upright
   * without them (M4.T14a). Part of the cache key. */
  bool flip_y = true;
};

/** Per-context cache of `wgpu::RenderPipeline`s keyed by a PipelineInfo hash. */
class WGPUPipelinePool {
 public:
  wgpu::RenderPipeline get(const wgpu::Device &device, const PipelineInfo &info);

 private:
  std::unordered_map<uint64_t, wgpu::RenderPipeline> cache_;
};

/* --- Pure enum mappings (exposed for tests) -------------------------------- */

wgpu::PrimitiveTopology to_wgpu_topology(GPUPrimType prim);
wgpu::VertexFormat to_wgpu_vertex_format(GPUVertCompType comp_type,
                                         int comp_len,
                                         GPUVertFetchMode fetch);

}  // namespace webgpu
}  // namespace blender::gpu
