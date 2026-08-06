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
#include <vector>

#include "webgpu/webgpu_cpp.h"

#include "GPU_batch.hh" /* GPU_BATCH_VBO_MAX_LEN */
#include "GPU_primitive.hh"
#include "GPU_vertex_format.hh"

#include "gpu_state_private.hh" /* GPUState / GPUStateMutable */

namespace blender::gpu {

class WGPUShader;

namespace webgpu {

/** The state that selects a render pipeline (its cache key). Framebuffer target
 * formats + primitive + fixed-function state + the shader + the vertex signature. */
/** One WebGPU vertex-buffer slot: a source (a batch VBO index, or the dummy buffer),
 * its stride/step-mode, and the attributes it feeds. Blender batches spread a shader's
 * vertex inputs across SEVERAL VBOs (verts[0..15]); a WebGPU pipeline's VertexState must
 * carry a slot for every @location the vertex module consumes, so the plan groups the
 * matched attributes per source buffer and fills the shader-required-but-absent locations
 * with a zero-stepping dummy slot (GL's "disabled array reads a constant"). Both the
 * pipeline layout (build_pipeline) and the per-draw SetVertexBuffer binding are derived
 * from the SAME plan so slot indices agree. */
struct VertexBinding {
  int vbo_index = -1;   /* index into PipelineInfo.vertex_formats; -1 = dummy buffer. */
  uint64_t buffer_offset = 0;
  uint32_t array_stride = 0;
  wgpu::VertexStepMode step_mode = wgpu::VertexStepMode::Vertex;
  bool is_dummy = false;
  std::vector<wgpu::VertexAttribute> attributes;
};
using VertexPlan = std::vector<VertexBinding>;

struct PipelineInfo {
  WGPUShader *shader = nullptr;
  /* Every bound vertex buffer, indexed by its batch verts[] slot (entries may be null);
   * a single interleaved format lives at [0]. Empty set => procedural (no vbo). */
  const GPUVertFormat *vertex_formats[GPU_BATCH_VBO_MAX_LEN] = {};
  int64_t vertex_lens[GPU_BATCH_VBO_MAX_LEN] = {};
  int vertex_formats_len = 0;
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

/** Resolve the shader's vertex inputs against the bound vertex buffers, producing one
 * VertexBinding per WebGPU slot (matched attributes grouped by source VBO, plus a dummy
 * slot for each shader-required location no VBO provides). Pure function of (shader
 * interface, formats) — the buffer_offset uses vertex_lens only for deinterleaved VBOs. */
VertexPlan build_vertex_plan(const GPUVertFormat *const *formats,
                             const int64_t *vertex_lens,
                             int formats_len,
                             WGPUShader &shader);

}  // namespace webgpu
}  // namespace blender::gpu
