/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Implements the NORMATIVE binding map of `notes/gpu-binding-map-spec.md` §4-§5.
 * See wgpu_shader_interface_map.hh for the API contract. */

#include "wgpu_shader_interface_map.hh"

namespace blender::gpu::webgpu {

/* WebGPU guaranteed limit; both native Dawn (native/Limits.cpp:133) and the
 * emdawnwebgpu port expose maxBindingsPerBindGroup = 1000 (spec §4.1). */
static constexpr uint32_t kMaxBindingsPerBindGroup = 1000u;

wgpu::TextureSampleType infer_sample_type(TexelClass texel, bool filtering)
{
  switch (texel) {
    case TexelClass::Float:
      /* Tint emits texture_2d<f32>. A non-filtering float sampler (data
       * textures, GPUSamplerState without LINEAR) must pair with the
       * UnfilterableFloat sample type; a filtering one with Float. */
      return filtering ? wgpu::TextureSampleType::Float
                       : wgpu::TextureSampleType::UnfilterableFloat;
    case TexelClass::Uint:
      /* Tint emits texture_2d<u32>. Integer textures are never filterable. */
      return wgpu::TextureSampleType::Uint;
    case TexelClass::Int:
      return wgpu::TextureSampleType::Sint;
    case TexelClass::Depth:
    case TexelClass::Shadow:
      /* Tint emits texture_depth_2d for both; the sampler type distinguishes
       * plain fetch (NonFiltering/Filtering) from compare (Comparison). */
      return wgpu::TextureSampleType::Depth;
  }
  return wgpu::TextureSampleType::Float;
}

wgpu::SamplerBindingType infer_sampler_type(TexelClass texel, bool filtering)
{
  switch (texel) {
    case TexelClass::Float:
      return filtering ? wgpu::SamplerBindingType::Filtering
                       : wgpu::SamplerBindingType::NonFiltering;
    case TexelClass::Uint:
    case TexelClass::Int:
      /* Integer textures cannot be filtered; only textureLoad (no sampler) is
       * valid on them in WGSL, so any declared sampler half is NonFiltering. */
      return wgpu::SamplerBindingType::NonFiltering;
    case TexelClass::Depth:
      /* Plain depth fetch: NonFiltering is always valid. */
      return wgpu::SamplerBindingType::NonFiltering;
    case TexelClass::Shadow:
      /* Compare sampling -> Tint emits sampler_comparison. */
      return wgpu::SamplerBindingType::Comparison;
  }
  return wgpu::SamplerBindingType::Filtering;
}

wgpu::TextureViewDimension infer_view_dimension(TexDim dim)
{
  switch (dim) {
    case TexDim::e1D:
      return wgpu::TextureViewDimension::e1D;
    case TexDim::e1DArray:
      /* WGSL has no 1D-array sampled texture; callers should not hit this. */
      return wgpu::TextureViewDimension::e2DArray;
    case TexDim::e2D:
      return wgpu::TextureViewDimension::e2D;
    case TexDim::e2DArray:
      return wgpu::TextureViewDimension::e2DArray;
    case TexDim::e3D:
      return wgpu::TextureViewDimension::e3D;
    case TexDim::Cube:
      return wgpu::TextureViewDimension::Cube;
    case TexDim::CubeArray:
      return wgpu::TextureViewDimension::CubeArray;
    case TexDim::Buffer:
      /* texture buffers are a distinct WGSL type with no view dimension; caller
       * should route these to textureLoad-only handling. */
      return wgpu::TextureViewDimension::e1D;
  }
  return wgpu::TextureViewDimension::e2D;
}

static wgpu::ShaderStage to_wgpu_visibility(uint32_t stages)
{
  wgpu::ShaderStage v = wgpu::ShaderStage::None;
  if (stages & STAGE_VERTEX) {
    v |= wgpu::ShaderStage::Vertex;
  }
  if (stages & STAGE_FRAGMENT) {
    v |= wgpu::ShaderStage::Fragment;
  }
  if (stages & STAGE_COMPUTE) {
    v |= wgpu::ShaderStage::Compute;
  }
  return v;
}

static wgpu::BindGroupLayoutEntry make_buffer_entry(uint32_t binding,
                                                    wgpu::ShaderStage vis,
                                                    wgpu::BufferBindingType type)
{
  wgpu::BindGroupLayoutEntry e = {};
  e.binding = binding;
  e.visibility = vis;
  e.buffer.type = type;
  return e;
}

static wgpu::BindGroupLayoutEntry make_texture_entry(uint32_t binding,
                                                     wgpu::ShaderStage vis,
                                                     const ResourceDesc &r)
{
  wgpu::BindGroupLayoutEntry e = {};
  e.binding = binding;
  e.visibility = vis;
  e.texture.sampleType = infer_sample_type(r.texel, r.filtering);
  e.texture.viewDimension = infer_view_dimension(r.dim);
  e.texture.multisampled = false;
  return e;
}

static wgpu::BindGroupLayoutEntry make_sampler_entry(uint32_t binding,
                                                     wgpu::ShaderStage vis,
                                                     const ResourceDesc &r)
{
  wgpu::BindGroupLayoutEntry e = {};
  e.binding = binding;
  e.visibility = vis;
  e.sampler.type = infer_sampler_type(r.texel, r.filtering);
  return e;
}

static wgpu::BindGroupLayoutEntry make_storage_image_entry(uint32_t binding,
                                                           wgpu::ShaderStage vis,
                                                           const ResourceDesc &r)
{
  wgpu::BindGroupLayoutEntry e = {};
  e.binding = binding;
  e.visibility = vis;
  e.storageTexture.access = r.image_access;
  e.storageTexture.format = r.image_format;
  e.storageTexture.viewDimension = infer_view_dimension(r.dim);
  return e;
}

InterfaceMap build_interface_map(const std::vector<ResourceDesc> &resources,
                                 uint32_t sampler_base)
{
  InterfaceMap map;

  /* Bound the resource-binding space and choose SAMPLER_BASE (spec §4.1). */
  uint32_t max_resource_binding = 0;
  uint32_t max_sampler_binding = 0;
  bool have_sampler = false;
  for (const ResourceDesc &r : resources) {
    /* An array sampler occupies bindings [N, N+array_size); count the top. */
    const uint32_t top = r.binding + (r.array_size > 0 ? r.array_size - 1 : 0);
    if (top > max_resource_binding) {
      max_resource_binding = top;
    }
    if (r.kind == ResourceKind::Sampler) {
      have_sampler = true;
      if (top > max_sampler_binding) {
        max_sampler_binding = top;
      }
    }
  }

  map.sampler_base = sampler_base != 0 ? sampler_base : kSamplerBindingBaseFixed;

  /* HARD invariants (spec §4.1): resources sit below the reserved base, and the
   * top reserved sampler binding stays under the device limit. */
  if (have_sampler && map.sampler_base <= max_resource_binding) {
    map.ok = false;
    map.error = "SAMPLER_BASE (" + std::to_string(map.sampler_base) +
                ") must exceed max resource binding (" +
                std::to_string(max_resource_binding) + ")";
    return map;
  }
  if (have_sampler && map.sampler_base + max_sampler_binding >= kMaxBindingsPerBindGroup) {
    map.ok = false;
    map.error = "SAMPLER_BASE + max sampler binding (" +
                std::to_string(map.sampler_base + max_sampler_binding) +
                ") exceeds maxBindingsPerBindGroup=" +
                std::to_string(kMaxBindingsPerBindGroup);
    return map;
  }

  for (const ResourceDesc &r : resources) {
    const wgpu::ShaderStage vis = to_wgpu_visibility(r.stages);
    switch (r.kind) {
      case ResourceKind::UniformBuffer:
        map.entries.push_back(
            make_buffer_entry(r.binding, vis, wgpu::BufferBindingType::Uniform));
        break;
      case ResourceKind::StorageBuffer:
        map.entries.push_back(make_buffer_entry(
            r.binding, vis,
            r.storage_readonly ? wgpu::BufferBindingType::ReadOnlyStorage
                               : wgpu::BufferBindingType::Storage));
        break;
      case ResourceKind::StorageImage:
        map.entries.push_back(make_storage_image_entry(r.binding, vis, r));
        break;
      case ResourceKind::Sampler: {
        /* Per array element: one combined sampler at binding N+i splits into a
         * texture half (kept at N+i) and a sampler half (reserved BASE+N+i).
         * A scalar sampler is just array_size == 1. Every element gets its own
         * sampler_mappings key (see findings §sampler-array). */
        const uint32_t count = r.array_size > 0 ? r.array_size : 1;
        for (uint32_t i = 0; i < count; i++) {
          const uint32_t n = r.binding + i;
          /* texture half stays at N (spec §4.1). */
          map.entries.push_back(make_texture_entry(n, vis, r));
          /* sampler half -> reserved BASE + N. */
          map.entries.push_back(
              make_sampler_entry(map.sampler_base + n, vis, r));
          map.sampler_mappings.push_back(
              {BindPoint{0u, n}, BindPoint{0u, map.sampler_base + n}});
        }
        break;
      }
    }
  }

  return map;
}

}  // namespace blender::gpu::webgpu
