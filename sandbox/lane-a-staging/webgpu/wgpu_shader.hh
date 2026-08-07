/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_shader.hh @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * `Shader` on the WebGPU backend. Round-4 scope is the GPU_init unblock: a real
 * `shader_alloc` returning a `WGPUShader` so the base `ShaderCompiler`'s async
 * builtin warm-up (GPU_init) has an object to drive. The create-info → GLSL
 * codegen reuse + the shaderc→Tint→WGSL compile (wgpu_shader_compiler, already
 * in-tree) + the WGSL `WGPUShaderModule`s + `ShaderInterface` build land next;
 * until then `finalize()` reports failure gracefully (non-fatal on the async
 * compile worker), which is enough for GPU_init to complete and for the buffer
 * suite to run. Draw-time hooks (bind/uniform) are no-ops (lane B).
 */

#pragma once

#include "gpu_shader_private.hh"

#include "BLI_map.hh"

#include "wgpu_buffer.hh"
#include "wgpu_shader_compiler.hh"

#include <cstdint>
#include <vector>
#include <webgpu/webgpu_cpp.h>

#include "MEM_guardedalloc.h"

namespace blender::gpu {

class WGPUShader : public Shader {
 public:
  WGPUShader(const char *name);
  ~WGPUShader() override;

  void init(const shader::ShaderCreateInfo &info, bool is_codegen_only) override;
  const shader::ShaderCreateInfo &patch_create_info(
      const shader::ShaderCreateInfo &original_info) override;

  void vertex_shader_from_glsl(const shader::ShaderCreateInfo &info,
                               MutableSpan<StringRefNull> sources) override;
  void geometry_shader_from_glsl(const shader::ShaderCreateInfo &info,
                                 MutableSpan<StringRefNull> sources) override;
  void fragment_shader_from_glsl(const shader::ShaderCreateInfo &info,
                                 MutableSpan<StringRefNull> sources) override;
  void compute_shader_from_glsl(const shader::ShaderCreateInfo &info,
                                MutableSpan<StringRefNull> sources) override;
  bool finalize(const shader::ShaderCreateInfo *info = nullptr) override;
  void warm_cache(int limit) override;

  void bind(const shader::SpecializationConstants *constants_state) override;
  void unbind() override;

  void uniform_float(int location, int comp_len, int array_size, const float *data) override;
  void uniform_int(int location, int comp_len, int array_size, const int *data) override;

  /* Create-info → GLSL codegen. Emits GLSL 450 with dense set-0 `layout(binding=N)`
   * resources + `layout(location=N)` interfaces (ported from the Vulkan backend;
   * the WGSL-target divergences — combined-sampler split, push-constant UBO — are
   * handled downstream by the shaderc env + Tint sampler_mappings). */
  std::string resources_declare(const shader::ShaderCreateInfo &info) const override;
  std::string vertex_interface_declare(const shader::ShaderCreateInfo &info) const override;
  std::string fragment_interface_declare(const shader::ShaderCreateInfo &info) const override;
  std::string geometry_interface_declare(const shader::ShaderCreateInfo &info) const override;
  std::string geometry_layout_declare(const shader::ShaderCreateInfo &info) const override;
  std::string compute_layout_declare(const shader::ShaderCreateInfo &info) const override;

  const wgpu::ShaderModule &vertex_module() const
  {
    return vertex_module_;
  }
  const wgpu::ShaderModule &fragment_module() const
  {
    return fragment_module_;
  }
  const wgpu::ShaderModule &compute_module() const
  {
    return compute_module_;
  }
  /** The compute pipeline for this shader, built lazily from the compute module on
   * first dispatch and cached for the shader's lifetime. WebGPU compute uses an auto
   * layout inferred from the WGSL, so the bind group the backend assembles via
   * GetBindGroupLayout(0) matches the Tint output. Caching HERE (not in a global
   * pointer-keyed pool) is deliberate: a freed-then-reallocated WGPUShader address
   * could otherwise return another shader's stale pipeline. Null if no compute stage
   * or the compile failed. */
  wgpu::ComputePipeline compute_pipeline(const wgpu::Device &device);
  const webgpu::InterfaceMap &interface_map() const
  {
    return interface_map_;
  }

  /* ---- Explicit pipeline layout (M4.T17) ----------------------------------
   * Dawn's auto layout infers a WGSL resource's binding type purely from the WGSL
   * (e.g. `texture_2d<f32>` -> filterable Float), which is WRONG for the depth
   * textures Blender reads through a plain `sampler2D` (they are unfilterable) and
   * cannot express the sampler/view-dimension distinctions the interface map knows.
   * finalize() builds an EXPLICIT group-0 bind-group layout from the interface map,
   * restricted to the bindings that actually survive Tint's pruning (scanned from the
   * emitted WGSL) so the layout is binding-set- and visibility-identical to the auto
   * layout, differing only where the auto layout is wrong. has_explicit_layout() is
   * false (and the draw/compute paths fall back to the auto layout) if any surviving
   * WGSL binding is not covered by the interface map — never a silent mix. */
  bool has_explicit_layout() const
  {
    return explicit_layout_ok_;
  }
  const wgpu::BindGroupLayout &explicit_bind_group_layout() const
  {
    return explicit_bgl_;
  }
  const wgpu::PipelineLayout &explicit_pipeline_layout() const
  {
    return explicit_pipeline_layout_;
  }

  /* ---- Push-constant UBO surface (for lane B's bind-group assembly) --------
   * WebGPU has no push constants; the create-info push-constant block is emulated
   * as a std140 UBO whose binding is `push_constants_binding()`. uniform_float /
   * uniform_int fill a CPU shadow; lane B calls `push_constants_flush()` before a
   * draw to upload the dirty shadow, then binds `push_constants_buffer()` at that
   * binding. If the shader has no push constants, has_push_constants() is false and
   * the buffer is invalid. */
  bool has_push_constants() const
  {
    return push_constants_size_ > 0;
  }
  uint32_t push_constants_binding() const
  {
    return push_constants_binding_;
  }
  const webgpu::Buffer &push_constants_buffer() const
  {
    return push_constants_buffer_;
  }
  /** Upload the CPU shadow to the UBO if dirty (creates the buffer on first use).
   * Call before a draw that binds the push-constant UBO. */
  void push_constants_flush();

  /* ---- Multi-viewport / layered emulation surface (M3.F7) ------------------
   * A VIEWPORT_INDEX shader carries gpu_Layer / gpu_ViewportIndex to the fragment as
   * flat varyings and discards primitives whose routing target != the pass's
   * (layer, viewport), which the backend supplies in a small std140 UBO at
   * multi_viewport_binding(). wgpu_batch.cc drives one pass per (layer, viewport). */
  bool has_multi_viewport() const
  {
    return has_multi_viewport_;
  }
  uint32_t multi_viewport_binding() const
  {
    return multi_viewport_binding_;
  }

  /* Remap a frontend resource bind slot (the per-resource-type create-info slot
   * Blender binds at) to the dense group-0 binding the generated WGSL declares. The
   * WGPU backend flattens all resource classes into one bind group, so a texture at
   * sampler-slot 0 and an SSBO at storage-slot 0 get distinct dense bindings (0 and,
   * say, 1). `lookup_default` returns the slot unchanged when it already equals the
   * dense binding, so a bind that already passes the dense value is unaffected.
   * Consumed by WGPUContext::append_resource_bind_entries. */
  int remap_ssbo_binding(int slot) const;
  int remap_ubo_binding(int slot) const;
  /** True when `slot` is a create-info slot in the dense map (flavor (a) —
   * needs remapping); false for name-resolved/already-dense binds (flavor (b),
   * identity). The builder gives mapped binds precedence over identity ones. */
  bool slot_is_mapped(shader::ShaderCreateInfo::Resource::BindType type, int slot) const;
  int remap_sampler_binding(int slot) const;
  int remap_image_binding(int slot) const;

 private:
  /* Run the BSL preprocessor on a combined stage source (unless skip_preprocessor). */
  std::string preprocess(const std::string &combined) const;

  /* Combined per-stage GLSL captured from the base compiler's *_from_glsl calls
   * (version patch + defines + resources + interface + user source), compiled in
   * finalize(). Empty string = stage absent. */
  std::string vertex_glsl_;
  std::string fragment_glsl_;
  std::string compute_glsl_;

  /* Compiled WGSL modules (produced by finalize via the shaderc→Tint chain). */
  wgpu::ShaderModule vertex_module_;
  wgpu::ShaderModule fragment_module_;
  wgpu::ShaderModule compute_module_;

  /* Compute pipelines built lazily from compute_module_ and cached PER
   * specialization-constant value set (see compute_pipeline()). WebGPU applies
   * `override` constants at pipeline creation, so distinct spec-constant values need
   * distinct pipeline variants; the key is the raw override bit patterns. Value sets
   * per shader are few, so a linear-searched vector is enough (and sidesteps hashing
   * a Vector key). */
  struct ComputePipelineVariant {
    std::vector<uint32_t> key;
    wgpu::ComputePipeline pipeline;
  };
  std::vector<ComputePipelineVariant> compute_pipelines_;
  /* Specialization constants captured by the most recent bind(); consumed by
   * compute_pipeline() to select/create the matching variant. Null = defaults. The
   * pointee is owned by the caller and stays valid across the bind()->dispatch call
   * chain (GPU_compute_dispatch). */
  const shader::SpecializationConstants *bound_constants_ = nullptr;

  /* Binding reflection: sampler_mappings + the group-0 bind-group layout. */
  webgpu::InterfaceMap interface_map_;

  /* Explicit group-0 layout built from interface_map_ post-compile, pruned to the
   * WGSL-surviving binding set (see has_explicit_layout()). Created in finalize() on
   * the async compile worker via the shared backend device; read at draw/dispatch. */
  std::vector<wgpu::BindGroupLayoutEntry> explicit_entries_;
  wgpu::BindGroupLayout explicit_bgl_;
  wgpu::PipelineLayout explicit_pipeline_layout_;
  bool explicit_layout_ok_ = false;

  /* Push-constant emulation. `push_constants_` maps a uniform location (base
   * 1024 + i, as the interface assigns) to its std140 byte offset + size; the CPU
   * shadow is `push_constants_data_`, uploaded to `push_constants_buffer_`. */
  struct PushConstantSlot {
    int32_t location;
    uint32_t offset;
    uint32_t size;
  };
  std::vector<PushConstantSlot> push_constants_;
  std::vector<uint8_t> push_constants_data_;
  webgpu::Buffer push_constants_buffer_;
  uint32_t push_constants_size_ = 0;
  uint32_t push_constants_binding_ = 0;
  bool push_constants_dirty_ = false;
  /* (bind_type<<24 | create-info slot) -> dense group-0 binding (build_dense_bindings),
   * kept for remap_*_binding. */
  blender::Map<uint32_t, uint32_t> dense_bindings_;

  /* Multi-viewport emulation (M3.F7): whether this shader declares VIEWPORT_INDEX and the
   * binding of its per-pass (layer, viewport) UBO. Set in build_interface(). */
  bool has_multi_viewport_ = false;
  uint32_t multi_viewport_binding_ = 0;

  /** Write `comp_len * array_size` scalars into the push-constant shadow at the
   * offset for `location`. Shared by uniform_float / uniform_int. */
  void push_constant_set(int location, int comp_len, int array_size, const void *data);
  /** Build the interface + push-constant layout from the create-info. */
  void build_interface(const shader::ShaderCreateInfo &info);

  /** Build explicit_entries_ / explicit_bgl_ / explicit_pipeline_layout_ from
   * interface_map_, restricted to the @group(0) @binding(N) that survive Tint's
   * pruning across the emitted WGSL stages. Sets explicit_layout_ok_. */
  void build_explicit_layout(const wgpu::Device &device,
                             const std::string &vertex_wgsl,
                             const std::string &fragment_wgsl,
                             const std::string &compute_wgsl);

  MEM_CXX_CLASS_ALLOC_FUNCS("WGPUShader")
};

}  // namespace blender::gpu
