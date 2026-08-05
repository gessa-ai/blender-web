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

  /* Create-info → GLSL codegen. These emit the same GLSL as the Vulkan backend
   * (the WGSL-target divergences — push-constant UBO fallback, combined-sampler
   * split — are handled downstream by shaderc env + Tint, not here). Round-4
   * stubs (empty) until the codegen port; see the .cc. */
  std::string resources_declare(const shader::ShaderCreateInfo &info) const override;
  std::string vertex_interface_declare(const shader::ShaderCreateInfo &info) const override;
  std::string fragment_interface_declare(const shader::ShaderCreateInfo &info) const override;
  std::string geometry_interface_declare(const shader::ShaderCreateInfo &info) const override;
  std::string geometry_layout_declare(const shader::ShaderCreateInfo &info) const override;
  std::string compute_layout_declare(const shader::ShaderCreateInfo &info) const override;

 private:
  MEM_CXX_CLASS_ALLOC_FUNCS("WGPUShader")
};

}  // namespace blender::gpu
