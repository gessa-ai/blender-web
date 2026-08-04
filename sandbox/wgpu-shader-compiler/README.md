<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->
# M3.T7.pre — WebGPU shader-compiler module (standalone-proven)

The two HARD components of M3.T7, developed OUTSIDE the Blender tree against the
`sandbox/dawn-probe` baseline so T7 becomes an integration task. Filenames mirror
`source/blender/gpu/webgpu/` so they drop in later.

```
GLSL (per stage)
  -> shaderc CompileGlslToSpv, env vulkan_1_1  => SPIR-V 1.3   [HARD constraint, T1 §4a]
  -> tint::spirv::reader::ReadIR (sampler_mappings from the interface map)
  -> tint::wgsl::writer::ProgramFromIR -> Generate            => WGSL
  + one group-0 wgpu::BindGroupLayout that binds identically   (normative spec §4-§5)
```

## Files

- `wgpu_shader_interface_map.{hh,cc}` — PURE mapping: create-info resource list →
  `sampler_mappings` ({0,N}→{0,256+N}) + BGL entries + Sampler/Texture binding-type
  inference (`notes/gpu-binding-map-spec.md`, open-question-3). No device needed.
- `wgpu_shader_compiler.{hh,cc}` — the chain above, in one `compile_shader()` call.
- `tests/wgpu_shader_compiler_test.cc` + `tests/test_shaders.hh` — end-to-end harness:
  compile realistic shaders, build BGLs, create LIVE Dawn pipelines.
- `CMakeLists.txt` / `build.sh` — extend the dawn-probe build (same pinned Dawn
  checkout + link recipe) and link Blender's own `lib/<platform>/shaderc`.

## Build & run

```sh
# Reuses the dawn-probe checkout (build-dawn/dawn) and Blender's libs (lib/macos_arm64/shaderc).
harness/buildwrap.sh bash sandbox/wgpu-shader-compiler/build.sh
```

Exit 0 iff all 4 gated cases (bindmap · types · compute_ssbo_atomic · negative-control)
meet expectation on a live Dawn/Metal device. The sampler-array case is a
characterization probe (see `notes/gpu-t7pre-findings.md` §5). Build tree is under
`build-dawn/t7pre-build` (gitignored).

## Result

4/4 gated PASS on "Apple M4 Pro". Findings + the qualifier→BindingType table + the
sampler-array verdict: `notes/gpu-t7pre-findings.md`.
