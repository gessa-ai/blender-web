/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm parity probe for the normative M3.T2 combined-
 * sampler binding map.
 *
 * The exact shaderc v2025.4 + Dawn/Tint 36cf1fae chain translates the same
 * Blender-shaped vertex/fragment pair twice: first with Tint's default empty
 * sampler map, then with every combined sampler mapped from {0,N} to
 * {0,256+N}. The program fails unless the complete resource-binding census
 * matches notes/gpu-binding-map-spec.md. build.sh additionally requires the
 * native and Wasm WGSL bytes to be identical. No Dawn device is created. */

#include <cstdint>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

#include <shaderc/shaderc.hpp>

#include "src/tint/api/common/binding_point.h"
#include "src/tint/lang/core/ir/module.h"
#include "src/tint/lang/spirv/reader/reader.h"
#include "src/tint/lang/wgsl/program/program.h"
#include "src/tint/lang/wgsl/writer/writer.h"

#include "../wgpu-shader-compiler/tests/test_shaders.hh"

namespace {

using ExpectedBinding = std::pair<const char *, uint32_t>;
namespace shaders = blender::gpu::webgpu::test_shaders;

bool compile_glsl(const char *source,
                  shaderc_shader_kind kind,
                  const char *name,
                  std::vector<uint32_t> &spirv)
{
  shaderc::Compiler compiler;
  shaderc::CompileOptions options;
  options.SetTargetEnvironment(shaderc_target_env_vulkan, shaderc_env_version_vulkan_1_1);
  options.SetSourceLanguage(shaderc_source_language_glsl);
  options.SetOptimizationLevel(shaderc_optimization_level_zero);

  shaderc::SpvCompilationResult result = compiler.CompileGlslToSpv(
      source, kind, name, "main", options);
  if (result.GetCompilationStatus() != shaderc_compilation_status_success) {
    std::cerr << "shaderc " << name << ": " << result.GetErrorMessage() << "\n";
    return false;
  }
  spirv.assign(result.cbegin(), result.cend());
  return true;
}

bool translate(const std::vector<uint32_t> &spirv, bool mapped, std::string &wgsl)
{
  tint::spirv::reader::Options reader_options;
  if (mapped) {
    reader_options.sampler_mappings[tint::BindingPoint{0u, 1u}] =
        tint::BindingPoint{0u, 257u};
    reader_options.sampler_mappings[tint::BindingPoint{0u, 2u}] =
        tint::BindingPoint{0u, 258u};
  }

  auto ir = tint::spirv::reader::ReadIR(spirv, reader_options);
  if (ir != tint::Success) {
    std::cerr << "Tint ReadIR failed\n";
    return false;
  }
  tint::wgsl::writer::Options writer_options;
  auto program_result = tint::wgsl::writer::ProgramFromIR(ir.Get(), writer_options);
  if (program_result != tint::Success) {
    std::cerr << "Tint ProgramFromIR failed\n";
    return false;
  }
  tint::Program program = program_result.Move();
  auto generate_result = tint::wgsl::writer::Generate(program, writer_options);
  if (generate_result != tint::Success) {
    std::cerr << "Tint Generate failed\n";
    return false;
  }
  wgsl = generate_result.Get().wgsl;
  return true;
}

bool check_bindings(const char *label,
                    const std::string &wgsl,
                    const std::vector<ExpectedBinding> &expected)
{
  size_t binding_line_count = 0;
  size_t begin = 0;
  while (begin < wgsl.size()) {
    const size_t end = wgsl.find('\n', begin);
    const std::string line = wgsl.substr(
        begin, end == std::string::npos ? std::string::npos : end - begin);
    if (line.find("@group(") != std::string::npos &&
        line.find("@binding(") != std::string::npos &&
        line.find(" var") != std::string::npos) {
      binding_line_count++;
    }
    if (end == std::string::npos) {
      break;
    }
    begin = end + 1;
  }
  if (binding_line_count != expected.size()) {
    std::cerr << label << ": expected " << expected.size() << " resource declarations, got "
              << binding_line_count << "\n";
    return false;
  }

  for (const ExpectedBinding &item : expected) {
    const std::string variable_marker = std::string(" ") + item.first + " :";
    const std::string binding_marker = "@group(0u) @binding(" +
                                       std::to_string(item.second) + "u)";
    size_t matches = 0;
    begin = 0;
    while (begin < wgsl.size()) {
      const size_t end = wgsl.find('\n', begin);
      const std::string line = wgsl.substr(
          begin, end == std::string::npos ? std::string::npos : end - begin);
      if (line.find(" var") != std::string::npos &&
          line.find(variable_marker) != std::string::npos) {
        matches++;
        if (line.find(binding_marker) == std::string::npos) {
          std::cerr << label << ": " << item.first << " is not at group 0 binding "
                    << item.second << "\n";
          return false;
        }
      }
      if (end == std::string::npos) {
        break;
      }
      begin = end + 1;
    }
    if (matches != 1) {
      std::cerr << label << ": expected exactly one declaration for " << item.first
                << ", got " << matches << "\n";
      return false;
    }
  }
  return true;
}

void write_section(const char *label, const std::string &wgsl)
{
  std::cout << "===== " << label << " =====\n" << wgsl;
  if (wgsl.empty() || wgsl.back() != '\n') {
    std::cout << '\n';
  }
}

}  // namespace

int main()
{
  std::vector<uint32_t> vertex_spirv;
  std::vector<uint32_t> fragment_spirv;
  if (!compile_glsl(shaders::kBindmapVert,
                    shaderc_vertex_shader,
                    "bindmap.vert",
                    vertex_spirv) ||
      !compile_glsl(shaders::kBindmapFrag,
                    shaderc_fragment_shader,
                    "bindmap.frag",
                    fragment_spirv)) {
    return 2;
  }

  std::string default_vertex;
  std::string default_fragment;
  std::string mapped_vertex;
  std::string mapped_fragment;
  if (!translate(vertex_spirv, false, default_vertex) ||
      !translate(fragment_spirv, false, default_fragment) ||
      !translate(vertex_spirv, true, mapped_vertex) ||
      !translate(fragment_spirv, true, mapped_fragment)) {
    return 3;
  }

  const std::vector<ExpectedBinding> vertex_bindings = {
      {"globals", 0u},
      {"constants", 5u},
  };
  const std::vector<ExpectedBinding> default_fragment_bindings = {
      {"globals", 0u},
      {"color_tex_image", 1u},
      {"color_tex_sampler", 2u},
      {"normal_tex_image", 3u},
      {"normal_tex_sampler", 4u},
      {"material", 5u},
      {"light_data", 6u},
      {"constants", 7u},
  };
  const std::vector<ExpectedBinding> mapped_fragment_bindings = {
      {"globals", 0u},
      {"color_tex_image", 1u},
      {"color_tex_sampler", 257u},
      {"normal_tex_image", 2u},
      {"normal_tex_sampler", 258u},
      {"material", 3u},
      {"light_data", 4u},
      {"constants", 5u},
  };

  if (!check_bindings("default vertex", default_vertex, vertex_bindings) ||
      !check_bindings(
          "default fragment", default_fragment, default_fragment_bindings) ||
      !check_bindings("mapped vertex", mapped_vertex, vertex_bindings) ||
      !check_bindings("mapped fragment", mapped_fragment, mapped_fragment_bindings)) {
    return 4;
  }
  if (default_fragment == mapped_fragment || default_vertex != mapped_vertex) {
    std::cerr << "binding-map phase relation is not the pinned T2 contract\n";
    return 5;
  }

  std::cout << "BINDMAP_SEMANTICS_PASS\n";
  write_section("DEFAULT_VERTEX", default_vertex);
  write_section("DEFAULT_FRAGMENT", default_fragment);
  write_section("MAPPED_VERTEX", mapped_vertex);
  write_section("MAPPED_FRAGMENT", mapped_fragment);
  return 0;
}
