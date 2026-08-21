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
- `tests/wgpu_shader_compiler_test.cc` + `tests/test_shaders.hh` — device-free
  compiler/interface contract plus end-to-end harness: compile realistic shaders,
  build BGLs, and, on an accepted adapter, create live Dawn pipelines.
- `CMakeLists.txt` / `build.sh` — extend the dawn-probe build (same pinned Dawn
  checkout + link recipe) and build/link exact shaderc v2025.4 from its
  checksum-bound source archive.

## Build & run

```sh
# Accepted hardware adapter: compile-only contract, then live pipelines.
harness/buildwrap.sh bash sandbox/wgpu-shader-compiler/build.sh

# Known software-only host: compile-only contract, then require exact rc=5 and
# PROBE_BLOCKED before device creation. This is evidence, never a live receipt.
BW_T7_EXPECT_ADAPTER=blocked \
  harness/buildwrap.sh bash sandbox/wgpu-shader-compiler/build.sh
```

The driver first runs six deterministic device-free contracts: mapped bindmap,
qualifier types, compute/SSBO atomic lowering, default-Tint negative semantics,
the exact sampler-array rejection, and interface bounds/type inference. Live mode
then requires all four pipeline cases (bindmap · types · compute_ssbo_atomic ·
negative-control) on a hardware Metal or Vulkan adapter. `blocked` mode succeeds
only when the live executable returns exactly 5 with one non-hardware rejection
and no live PASS. Direct `--compile-only` execution is available for diagnostics,
but the build driver always enforces either the accepted-hardware or
expected-blocked live boundary. The build tree is under
`build-dawn/t7pre-build`; device-free output is under `build-deps/t7pre/evidence`
(both gitignored).

## Result

Historical live result: 4/4 gated PASS on "Apple M4 Pro". Fresh Linux result:
6/6 device-free contracts PASS through exact shaderc v2025.4 and Dawn/Tint
`36cf1fae`, while llvmpipe is rejected before device creation and binds no
receipt. Findings + the qualifier→BindingType table + the sampler-array verdict:
`notes/gpu-t7pre-findings.md`; Linux reconciliation:
`notes/m3-t7pre-linux-reconcile-20260821.md`.
