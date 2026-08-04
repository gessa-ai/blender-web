/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * M3.T7.pre — WebGPU shader compiler (standalone, drop-in for
 * `source/blender/gpu/webgpu/wgpu_shader_compiler.cc`).
 *
 * Drives the full M3 shader chain in-process, exactly as the real backend will:
 *
 *   GLSL (per stage)
 *     -> shaderc CompileGlslToSpv, env vulkan_1_1 => SPIR-V 1.3   [HARD constraint]
 *     -> tint::spirv::reader::ReadIR  (sampler_mappings from the interface map)
 *     -> tint::wgsl::writer::ProgramFromIR -> Generate            => WGSL text
 *
 * The SPIR-V 1.3 target is load-bearing: Tint's IR SPIR-V reader HARDCODES
 * SPV_ENV_VULKAN_1_1 (`src/tint/lang/spirv/reader/parser/parser.cc:95`), so a
 * Vulkan-1.2 / SPIR-V-1.5 module (what Blender's Vulkan backend emits) is
 * rejected. See notes/gpu-dawn-probe.md §4a.
 *
 * The compiler couples the interface map (binding numbers + BGL entries) to the
 * translation so the WGSL Tint emits binds identically to the layout the backend
 * builds — the whole point of the normative spec. */

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "wgpu_shader_interface_map.hh"

namespace blender::gpu::webgpu {

/** GLSL source per stage. An empty string means the stage is absent. A shader is
 * either graphics (vertex [+ fragment]) or compute; the compiler compiles
 * whichever are non-empty. */
struct ShaderStageSources {
  std::string vertex;
  std::string fragment;
  std::string compute;
  std::string name = "shader"; /* diagnostics / shaderc file tag */
};

struct CompileResult {
  bool ok = false;
  std::string error;

  /* Empty if the corresponding stage was absent. */
  std::string vertex_wgsl;
  std::string fragment_wgsl;
  std::string compute_wgsl;

  /* Binding numbers + the single group-0 bind-group layout. */
  InterfaceMap interface;
};

struct CompileOptions {
  /* SAMPLER_BASE override (0 = fixed policy, spec open-question-2). */
  uint32_t sampler_base = 0;
  /* Optimize the SPIR-V before Tint. Off by default to keep the reflection /
   * binding surface identical to the GLSL (matches this harness's needs; the
   * in-tree backend may mirror Blender's shaderc performance level). */
  bool optimize = false;
};

/** Compile a create-info-shaped shader. `resources` is the create-info resource
 * list (dense set-0 bindings); it drives both the sampler_mappings handed to
 * Tint and the returned BGL. */
CompileResult compile_shader(const ShaderStageSources &sources,
                             const std::vector<ResourceDesc> &resources,
                             const CompileOptions &options = {});

/* ---- Lower-level building blocks (exposed for the sampler-array probe) ----- */

/** GLSL -> SPIR-V 1.3 (vulkan_1_1) via shaderc. `stage` is a shaderc kind cast;
 * returns empty on failure with `error` set. */
std::vector<uint32_t> compile_glsl_to_spirv(const std::string &glsl,
                                             int shaderc_kind,
                                             const std::string &name,
                                             bool optimize,
                                             std::string &error);

/** SPIR-V -> WGSL via Tint, applying `sampler_mappings` ({0,N}->{0,BASE+N}). */
bool translate_spirv_to_wgsl(const std::vector<uint32_t> &spirv,
                             const std::vector<SamplerRemap> &sampler_mappings,
                             std::string &out_wgsl,
                             std::string &error);

}  // namespace blender::gpu::webgpu
