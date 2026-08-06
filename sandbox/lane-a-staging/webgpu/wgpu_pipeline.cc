/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_pipeline.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * WebGPU render-pipeline assembly + cache. See wgpu_pipeline.hh. Fixed-function
 * state is mapped by B2's wgpu_state_table (pure functions); the pipeline layout is
 * inferred by Dawn from the WGSL modules (auto layout) so it matches the Tint output
 * exactly — wgpu_batch obtains the bind-group layout via GetBindGroupLayout(). */

#include "wgpu_pipeline.hh"

#include "wgpu_shader.hh"
#include "wgpu_state_table.hh"

#include "gpu_shader_interface.hh"

#include <cstring>
#include <vector>

namespace blender::gpu::webgpu {

wgpu::PrimitiveTopology to_wgpu_topology(GPUPrimType prim)
{
  switch (prim) {
    case GPU_PRIM_POINTS:
      return wgpu::PrimitiveTopology::PointList;
    case GPU_PRIM_LINES:
      return wgpu::PrimitiveTopology::LineList;
    case GPU_PRIM_LINE_STRIP:
    case GPU_PRIM_LINE_LOOP: /* WebGPU has no loop; strip is the closest (batch closes it). */
      return wgpu::PrimitiveTopology::LineStrip;
    case GPU_PRIM_TRI_STRIP:
    case GPU_PRIM_TRI_FAN: /* WebGPU has no fan; emulated as strip upstream when needed. */
      return wgpu::PrimitiveTopology::TriangleStrip;
    case GPU_PRIM_TRIS:
    default:
      return wgpu::PrimitiveTopology::TriangleList;
  }
}

/** Map a Blender vertex component (type, count, fetch) to the WGSL vertex format.
 * WebGPU allows only x2/x4 for 8-/16-bit and scalar…x4 for 32-bit. */
wgpu::VertexFormat to_wgpu_vertex_format(GPUVertCompType comp_type,
                                         int comp_len,
                                         GPUVertFetchMode fetch)
{
  using VF = wgpu::VertexFormat;
  const bool norm = (fetch == GPU_FETCH_INT_TO_FLOAT_UNIT);
  const int n = comp_len;
  switch (comp_type) {
    case GPU_COMP_F32:
      return (n == 1) ? VF::Float32 : (n == 2) ? VF::Float32x2 : (n == 3) ? VF::Float32x3 :
                                                                            VF::Float32x4;
    case GPU_COMP_I32:
      return (n == 1) ? VF::Sint32 : (n == 2) ? VF::Sint32x2 : (n == 3) ? VF::Sint32x3 :
                                                                          VF::Sint32x4;
    case GPU_COMP_U32:
      return (n == 1) ? VF::Uint32 : (n == 2) ? VF::Uint32x2 : (n == 3) ? VF::Uint32x3 :
                                                                          VF::Uint32x4;
    case GPU_COMP_I16:
      if (norm) {
        return (n <= 2) ? VF::Snorm16x2 : VF::Snorm16x4;
      }
      return (n <= 2) ? VF::Sint16x2 : VF::Sint16x4;
    case GPU_COMP_U16:
      if (norm) {
        return (n <= 2) ? VF::Unorm16x2 : VF::Unorm16x4;
      }
      return (n <= 2) ? VF::Uint16x2 : VF::Uint16x4;
    case GPU_COMP_I8:
      if (norm) {
        return (n <= 2) ? VF::Snorm8x2 : VF::Snorm8x4;
      }
      return (n <= 2) ? VF::Sint8x2 : VF::Sint8x4;
    case GPU_COMP_U8:
      if (norm) {
        return (n <= 2) ? VF::Unorm8x2 : VF::Unorm8x4;
      }
      return (n <= 2) ? VF::Uint8x2 : VF::Uint8x4;
    case GPU_COMP_I10:
      return VF::Unorm10_10_10_2;
    default:
      return VF::Float32x4;
  }
}

/* --- Cache key -------------------------------------------------------------- */

static void hash_bytes(uint64_t &h, const void *data, size_t len)
{
  const uint8_t *p = static_cast<const uint8_t *>(data);
  for (size_t i = 0; i < len; i++) {
    h ^= p[i];
    h *= 1099511628211ull; /* FNV-1a prime */
  }
}

static uint64_t pipeline_hash(const PipelineInfo &info)
{
  uint64_t h = 1469598103934665603ull; /* FNV offset basis */
  const void *sh = info.shader;
  hash_bytes(h, &sh, sizeof(sh));
  hash_bytes(h, &info.state.data, sizeof(info.state.data));
  hash_bytes(h, info.mutable_state.data, sizeof(info.mutable_state.data));
  hash_bytes(h, info.color_formats, sizeof(wgpu::TextureFormat) * info.color_count);
  hash_bytes(h, &info.color_count, sizeof(info.color_count));
  hash_bytes(h, &info.depth_format, sizeof(info.depth_format));
  hash_bytes(h, &info.prim_type, sizeof(info.prim_type));
  hash_bytes(h, &info.flip_y, sizeof(info.flip_y));
  if (info.vertex_format != nullptr) {
    const GPUVertFormat *f = info.vertex_format;
    uint32_t stride = f->stride;
    uint32_t attr_len = f->attr_len;
    hash_bytes(h, &stride, sizeof(stride));
    hash_bytes(h, &attr_len, sizeof(attr_len));
    for (uint i = 0; i < f->attr_len; i++) {
      const GPUVertAttr &a = f->attrs[i];
      uint8_t sig[4] = {uint8_t(a.type.comp_type()), uint8_t(a.type.comp_len()),
                        uint8_t(a.type.fetch_mode()), a.offset};
      hash_bytes(h, sig, sizeof(sig));
    }
  }
  return h;
}

/* --- Build ------------------------------------------------------------------ */

static wgpu::RenderPipeline build_pipeline(const wgpu::Device &device, const PipelineInfo &info)
{
  WGPUShader *shader = info.shader;

  /* Vertex buffer layout (single interleaved buffer). Attributes the shader does
   * not read (attr_get == null) are skipped. */
  std::vector<wgpu::VertexAttribute> attributes;
  wgpu::VertexBufferLayout vbo_layout = {};
  if (info.vertex_format != nullptr && info.vertex_format->attr_len > 0 &&
      shader->interface != nullptr)
  {
    const GPUVertFormat *f = info.vertex_format;
    for (uint i = 0; i < f->attr_len; i++) {
      const GPUVertAttr &a = f->attrs[i];
      const char *name = GPU_vertformat_attr_name_get(f, &a, 0);
      const ShaderInput *input = shader->interface->attr_get(name);
      if (input == nullptr || input->location < 0) {
        continue;
      }
      wgpu::VertexAttribute va = {};
      va.format = to_wgpu_vertex_format(a.type.comp_type(), a.type.comp_len(), a.type.fetch_mode());
      va.offset = a.offset;
      va.shaderLocation = uint32_t(input->location);
      attributes.push_back(va);
    }
    vbo_layout.arrayStride = f->stride;
    vbo_layout.stepMode = wgpu::VertexStepMode::Vertex;
    vbo_layout.attributeCount = attributes.size();
    vbo_layout.attributes = attributes.data();
  }

  wgpu::VertexState vertex = {};
  vertex.module = shader->vertex_module();
  vertex.bufferCount = attributes.empty() ? 0 : 1;
  vertex.buffers = attributes.empty() ? nullptr : &vbo_layout;

  /* Present-path Y-flip (M4.T14a): render the surface backbuffer upright by overriding
   * the vertex clip-space Y sign to +1.0f (constant_id 1000, uint bit pattern). Offscreen
   * pipelines leave the override unset so it keeps its -1.0f default, byte-identical to
   * before this change. `y_sign_override` must outlive CreateRenderPipeline below. */
  wgpu::ConstantEntry y_sign_override = {};
  if (!info.flip_y) {
    y_sign_override.key = "1000";
    y_sign_override.value = double(0x3F800000u); /* +1.0f bit pattern (uint override) */
    vertex.constantCount = 1;
    vertex.constants = &y_sign_override;
  }

  /* Colour targets: one per bound colour attachment; blend + write mask from B2. */
  const BlendMapping bm = to_blend(GPUBlend(info.state.blend));
  wgpu::BlendState blend = {};
  blend.color = bm.color;
  blend.alpha = bm.alpha;
  const wgpu::ColorWriteMask write_mask = to_color_write_mask(GPUWriteMask(info.state.write_mask));

  std::vector<wgpu::ColorTargetState> targets(info.color_count);
  for (int i = 0; i < info.color_count; i++) {
    targets[i].format = info.color_formats[i];
    targets[i].blend = bm.enabled ? &blend : nullptr;
    targets[i].writeMask = write_mask;
  }

  wgpu::FragmentState fragment = {};
  fragment.module = shader->fragment_module();
  fragment.targetCount = targets.size();
  fragment.targets = targets.empty() ? nullptr : targets.data();

  /* Primitive. */
  wgpu::PrimitiveState primitive = {};
  primitive.topology = to_wgpu_topology(info.prim_type);
  /* ADR-005 decision 2 (winding compensation): lane A's vertex-shader clip-space
   * Y-flip (decision 1) inverts effective triangle winding in framebuffer space, so
   * swap the front-face (CW<->CCW) here to keep Blender's GL-convention facing. The
   * base mapping (to_front_face: GL CCW default, invert_facing -> CW) is negated. */
  const wgpu::FrontFace base_front = to_front_face(info.state.invert_facing);
  const wgpu::FrontFace swapped_front = (base_front == wgpu::FrontFace::CCW) ?
                                            wgpu::FrontFace::CW :
                                            wgpu::FrontFace::CCW;
  /* The winding swap is paired with the clip-space Y-flip: apply it only when the flip is
   * active (offscreen). The window backbuffer renders un-flipped (M4.T14a), so its winding
   * is not inverted and the base facing is correct. */
  primitive.frontFace = info.flip_y ? swapped_front : base_front;
  primitive.cullMode = to_cull_mode(GPUFaceCullTest(info.state.culling_test));

  /* Depth / stencil (only when a depth attachment is bound). */
  wgpu::DepthStencilState depth_stencil = {};
  const bool has_depth = info.depth_format != wgpu::TextureFormat::Undefined;
  if (has_depth) {
    const DepthMapping dm = to_depth(GPUDepthTest(info.state.depth_test));
    const StencilMapping sm = to_stencil(GPUStencilTest(info.state.stencil_test),
                                         GPUStencilOp(info.state.stencil_op));
    depth_stencil.format = info.depth_format;
    depth_stencil.depthCompare = dm.compare;
    /* Per B2's contract: depthWriteEnabled follows the WRITE mask, not the test. */
    depth_stencil.depthWriteEnabled = (info.state.write_mask & GPU_WRITE_DEPTH) ?
                                          wgpu::OptionalBool::True :
                                          wgpu::OptionalBool::False;
    if (sm.enabled) {
      depth_stencil.stencilFront = sm.front;
      depth_stencil.stencilBack = sm.back;
      depth_stencil.stencilReadMask = info.mutable_state.stencil_compare_mask;
      depth_stencil.stencilWriteMask = info.mutable_state.stencil_write_mask;
    }
  }

  wgpu::RenderPipelineDescriptor desc = {};
  desc.layout = nullptr; /* auto layout — inferred from the WGSL modules (Tint output). */
  desc.vertex = vertex;
  desc.primitive = primitive;
  desc.depthStencil = has_depth ? &depth_stencil : nullptr;
  desc.fragment = &fragment;

  return device.CreateRenderPipeline(&desc);
}

wgpu::RenderPipeline WGPUPipelinePool::get(const wgpu::Device &device, const PipelineInfo &info)
{
  const uint64_t key = pipeline_hash(info);
  auto it = cache_.find(key);
  if (it != cache_.end()) {
    return it->second;
  }
  wgpu::RenderPipeline pipeline = build_pipeline(device, info);
  cache_.emplace(key, pipeline);
  return pipeline;
}

}  // namespace blender::gpu::webgpu
