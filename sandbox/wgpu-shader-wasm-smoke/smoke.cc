/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * M2.x link-smoke: prove shaderc + Tint link and run TOGETHER in one binary,
 * for BOTH the native reference chain and the cross-compiled wasm chain.
 *
 * Chain: GLSL vert -> shaderc(SPIR-V 1.3, env vulkan_1_1) -> Tint(ReadIR ->
 * ProgramFromIR -> Generate) -> WGSL. Writes the WGSL verbatim to stdout so the
 * native and wasm outputs can be byte-compared (build.sh). Identical source on
 * both sides; the only variable is which shaderc/Tint archives the linker sees.
 *
 * env vulkan_1_1 (SPIR-V 1.3) is mandatory: Tint's IR SPIR-V reader hardcodes
 * SPV_ENV_VULKAN_1_1 and rejects >1.3 (notes/gpu-dawn-probe.md §4a). */

#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

#include <shaderc/shaderc.hpp>

#include "src/tint/lang/core/ir/module.h"
#include "src/tint/lang/spirv/reader/reader.h"
#include "src/tint/lang/wgsl/program/program.h"
#include "src/tint/lang/wgsl/writer/writer.h"

/* One GLSL vertex shader with a uniform block -> the WGSL must carry a
 * @group(0) @binding(0) uniform, giving the smoke an @binding to assert on. */
static const char *kVert =
    "#version 450\n"
    "layout(binding = 0) uniform UBO { mat4 mvp; } ubo;\n"
    "layout(location = 0) in vec3 pos;\n"
    "void main() { gl_Position = ubo.mvp * vec4(pos, 1.0); }\n";

int main()
{
  shaderc::Compiler compiler;
  shaderc::CompileOptions opts;
  opts.SetTargetEnvironment(shaderc_target_env_vulkan, shaderc_env_version_vulkan_1_1);
  opts.SetSourceLanguage(shaderc_source_language_glsl);
  opts.SetOptimizationLevel(shaderc_optimization_level_zero);

  shaderc::SpvCompilationResult res = compiler.CompileGlslToSpv(
      kVert, shaderc_vertex_shader, "smoke.vert", "main", opts);
  if (res.GetCompilationStatus() != shaderc_compilation_status_success) {
    std::fprintf(stderr, "shaderc: %s\n", res.GetErrorMessage().c_str());
    return 2;
  }
  std::vector<uint32_t> spirv(res.cbegin(), res.cend());

  tint::spirv::reader::Options reader_opts;
  auto ir = tint::spirv::reader::ReadIR(spirv, reader_opts);
  if (ir != tint::Success) {
    std::fprintf(stderr, "tint ReadIR failed\n");
    return 3;
  }
  tint::wgsl::writer::Options writer_opts;
  auto prog = tint::wgsl::writer::ProgramFromIR(ir.Get(), writer_opts);
  if (prog != tint::Success) {
    std::fprintf(stderr, "tint ProgramFromIR failed\n");
    return 4;
  }
  tint::Program program = prog.Move();
  auto gen = tint::wgsl::writer::Generate(program, writer_opts);
  if (gen != tint::Success) {
    std::fprintf(stderr, "tint Generate failed\n");
    return 5;
  }
  std::fputs(gen.Get().wgsl.c_str(), stdout);
  return 0;
}
