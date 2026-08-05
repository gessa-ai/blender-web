/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_shader.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 */

#include "wgpu_shader.hh"

namespace blender::gpu {

WGPUShader::WGPUShader(const char *name) : Shader(name) {}

WGPUShader::~WGPUShader() {}

void WGPUShader::init(const shader::ShaderCreateInfo & /*info*/, bool /*is_codegen_only*/) {}

const shader::ShaderCreateInfo &WGPUShader::patch_create_info(
    const shader::ShaderCreateInfo &original_info)
{
  /* No create-info patching yet. WebGPU has no geometry stage, so the Vulkan
   * geometry-injection path (LAYER/VIEWPORT_INDEX/BARYCENTRIC emulation) has no
   * WebGPU analog — flagged for the render milestones; return the info unchanged. */
  return original_info;
}

/* The base ShaderCompiler::compile() assembles the full per-stage GLSL (defines +
 * resources + interface + resolved source) and hands it here. Storing + compiling
 * that GLSL (shaderc → Tint → WGSL module) is the next step; for now these are
 * no-ops and finalize() reports failure so the async warm-up stays non-fatal. */
void WGPUShader::vertex_shader_from_glsl(const shader::ShaderCreateInfo & /*info*/,
                                         MutableSpan<StringRefNull> /*sources*/)
{
}
void WGPUShader::geometry_shader_from_glsl(const shader::ShaderCreateInfo & /*info*/,
                                           MutableSpan<StringRefNull> /*sources*/)
{
}
void WGPUShader::fragment_shader_from_glsl(const shader::ShaderCreateInfo & /*info*/,
                                           MutableSpan<StringRefNull> /*sources*/)
{
}
void WGPUShader::compute_shader_from_glsl(const shader::ShaderCreateInfo & /*info*/,
                                          MutableSpan<StringRefNull> /*sources*/)
{
}

bool WGPUShader::finalize(const shader::ShaderCreateInfo * /*info*/)
{
  /* The shaderc→Tint→WGSL compile + WGPUShaderModule + ShaderInterface build is
   * the next step (the compiler module is already in-tree). Reporting failure here
   * is honest (no module was produced) and non-fatal: the base compiler treats a
   * false return as a failed compile (deletes the shader), which the async builtin
   * warm-up in GPU_init tolerates without aborting. */
  return false;
}

void WGPUShader::warm_cache(int /*limit*/) {}

/* Draw-time binding + uniform upload run through the pipeline / bind-group
 * assembly (lane B); no-ops here. */
void WGPUShader::bind(const shader::SpecializationConstants * /*constants_state*/) {}
void WGPUShader::unbind() {}
void WGPUShader::uniform_float(int /*location*/,
                               int /*comp_len*/,
                               int /*array_size*/,
                               const float * /*data*/)
{
}
void WGPUShader::uniform_int(int /*location*/,
                             int /*comp_len*/,
                             int /*array_size*/,
                             const int * /*data*/)
{
}

/* Create-info → GLSL codegen — stubs until the port (returns empty declarations). */
std::string WGPUShader::resources_declare(const shader::ShaderCreateInfo & /*info*/) const
{
  return "";
}
std::string WGPUShader::vertex_interface_declare(const shader::ShaderCreateInfo & /*info*/) const
{
  return "";
}
std::string WGPUShader::fragment_interface_declare(const shader::ShaderCreateInfo & /*info*/) const
{
  return "";
}
std::string WGPUShader::geometry_interface_declare(const shader::ShaderCreateInfo & /*info*/) const
{
  return "";
}
std::string WGPUShader::geometry_layout_declare(const shader::ShaderCreateInfo & /*info*/) const
{
  return "";
}
std::string WGPUShader::compute_layout_declare(const shader::ShaderCreateInfo & /*info*/) const
{
  return "";
}

}  // namespace blender::gpu
