/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * M3.T7.pre — WebGPU shader-interface mapping (standalone, drop-in for
 * `source/blender/gpu/webgpu/wgpu_shader_interface.cc`).
 *
 * PURE mapping logic: it takes a backend-neutral description of the resources a
 * `GPUShaderCreateInfo` provides (the list of {resource class, dense set-0
 * binding N, texel/dim qualifier, using stages}) and computes, per the NORMATIVE
 * spec `notes/gpu-binding-map-spec.md`:
 *
 *   1. `sampler_mappings` — the Tint `spirv::reader::Options::sampler_mappings`
 *      table. For every combined sampler at Blender binding N, the SAMPLER HALF
 *      is steered to (0, SAMPLER_BASE + N); the texture half and every
 *      non-sampler resource keep their Blender binding N (spec §4.1). Exposed as
 *      backend-neutral (group,binding) pairs so this header pulls in NO Tint
 *      dependency; `wgpu_shader_compiler` converts them to `tint::BindingPoint`.
 *
 *   2. `entries` — the `wgpu::BindGroupLayoutEntry` list for the single group-0
 *      bind-group layout (spec §5), including SamplerBindingType /
 *      TextureSampleType inference from Blender's sampler qualifiers
 *      (open-question-3). One combined sampler yields TWO entries: the texture
 *      half at N and the sampler half at SAMPLER_BASE + N.
 *
 * No Dawn device is required to build the map — it is unit-testable in isolation.
 * The only external type surface is `wgpu::BindGroupLayoutEntry` and the WGSL
 * binding-type enums (webgpu_cpp.h), exactly as the real backend file uses. */

#pragma once

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include "webgpu/webgpu_cpp.h"

namespace blender::gpu::webgpu {

/* ---- Input: create-info resource description (backend-neutral) ------------- */

/** Bitmask of the shader stages that reference a resource -> WGSL `visibility`
 * (the OR of the using stages; a shared binding gets Vertex|Fragment). Values
 * match `wgpu::ShaderStage` for a trivial conversion. */
enum ShaderStageMask : uint32_t {
  STAGE_NONE = 0u,
  STAGE_VERTEX = 1u,
  STAGE_FRAGMENT = 2u,
  STAGE_COMPUTE = 4u,
};

/** create-info resource class (mirrors `ShaderCreateInfo::Resource::BindType`
 * plus the push-constant fallback UBO, which is just a UNIFORM_BUFFER). */
enum class ResourceKind : uint8_t {
  UniformBuffer,  /* UBO, incl. push-constant fallback UBO (spec §1). */
  StorageBuffer,  /* SSBO (read-only or read-write). */
  Sampler,        /* combined sampler2D/usampler.../samplerShadow (split in WGSL). */
  StorageImage,   /* image2D / imageLoad|Store. */
};

/** Texel class of a sampler/image resource. Enumerates upstream `ImageType`'s
 * texel families (`gpu_shader_create_info.hh:517-555`, read-only):
 *   Float{n}   -> sampler{n}        (filterable float)
 *   Uint{n}    -> usampler{n}       (unfilterable uint)
 *   Int{n}     -> isampler{n}       (unfilterable sint)
 *   Depth{n}   -> sampler{n}Depth   (depth, sampled non-compare)
 *   Shadow{n}  -> sampler{n}Shadow  (depth, compare -> sampler_comparison)
 *   Atomic*{n} -> usampler/isampler{n}Atomic (storage image r32ui/r32i; see
 *                 ResourceKind::StorageImage — atomics live on images, not samplers) */
enum class TexelClass : uint8_t { Float, Uint, Int, Depth, Shadow };

/** Sampler/image dimensionality (upstream `ImageType` `TYPES_EXPAND` list). */
enum class TexDim : uint8_t { e1D, e1DArray, e2D, e2DArray, e3D, Cube, CubeArray, Buffer };

/** One create-info resource. `binding` is Blender's DENSE set-0 binding N (the
 * value emitted in `layout(binding = N)` by the shader_interface, NOT the
 * create-info slot — see spec §1). */
struct ResourceDesc {
  ResourceKind kind = ResourceKind::UniformBuffer;
  uint32_t binding = 0;         /* dense set-0 N */
  uint32_t stages = STAGE_NONE; /* ShaderStageMask */

  /* sampler / storage-image only: */
  TexelClass texel = TexelClass::Float;
  TexDim dim = TexDim::e2D;
  bool filtering = true;        /* GPUSamplerState LINEAR -> Filtering sampler */
  uint32_t array_size = 1;      /* sampler2D tex[array_size]; 1 == scalar */

  /* storage buffer only: */
  bool storage_readonly = true;

  /* storage image only: */
  wgpu::StorageTextureAccess image_access = wgpu::StorageTextureAccess::WriteOnly;
  wgpu::TextureFormat image_format = wgpu::TextureFormat::RGBA8Unorm;

  const char *name = "";        /* diagnostics only */
};

/* ---- Output: the computed interface map ----------------------------------- */

/** A backend-neutral (group, binding) point — avoids leaking Tint into this
 * header. `wgpu_shader_compiler` converts these to `tint::BindingPoint`. */
struct BindPoint {
  uint32_t group = 0;
  uint32_t binding = 0;
};

/** One combined-sampler remap: sampler half key (0,N) -> value (0,BASE+N). */
struct SamplerRemap {
  BindPoint from; /* the combined sampler's ORIGINAL (set,binding) = Blender N */
  BindPoint to;   /* reserved-range sampler location */
};

struct InterfaceMap {
  bool ok = true;
  std::string error;

  uint32_t sampler_base = 0; /* SAMPLER_BASE actually used */

  /* Feeds Tint's spirv::reader::Options::sampler_mappings. One entry per
   * combined sampler ELEMENT (arrays expand — see wgpu_shader_interface_map.cc
   * and notes/gpu-t7pre-findings.md §sampler-array). */
  std::vector<SamplerRemap> sampler_mappings;

  /* The single group-0 bind-group layout (spec §5). */
  std::vector<wgpu::BindGroupLayoutEntry> entries;
};

/* ---- The mapping function -------------------------------------------------- */

/** SAMPLER_BASE policy. Fixed 256 (spec §4.1 / open-question-2): simplest and
 * provably safe at the pin (Blender set-0 resource count << 256 <
 * maxBindingsPerBindGroup=1000). `build_interface_map` still asserts the bound
 * so a pathological input fails loudly rather than mis-binding. */
constexpr uint32_t kSamplerBindingBaseFixed = 256u;

/** Compute the interface map from a create-info resource list.
 * `sampler_base` == 0 selects the fixed policy (kSamplerBindingBaseFixed);
 * a non-zero value pins a caller-chosen base (asserted collision-free). */
InterfaceMap build_interface_map(const std::vector<ResourceDesc> &resources,
                                 uint32_t sampler_base = 0);

/** Infer the WGSL texture sample type Tint will emit for a texel class, so the
 * BGL agrees with the module (open-question-3). Exposed for tests/report. */
wgpu::TextureSampleType infer_sample_type(TexelClass texel, bool filtering);

/** Infer the WGSL sampler binding type from the qualifier (open-question-3). */
wgpu::SamplerBindingType infer_sampler_type(TexelClass texel, bool filtering);

/** Map upstream `ImageType` dimensionality to a WGSL view dimension. */
wgpu::TextureViewDimension infer_view_dimension(TexDim dim);

}  // namespace blender::gpu::webgpu
