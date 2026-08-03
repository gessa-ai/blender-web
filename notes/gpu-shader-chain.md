# M3 — Shader chain deep dive (GLSL/BSL → SPIR-V → WGSL)

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

Companion to `notes/gpu-webgpu-architecture.md` §3. Pin `fbe6228777e7`. **VERIFIED** = read at
the pin; **INFER** = reasoned from WebGPU/Tint semantics.

## 1. The chain, step by step

```
create-info (C++ macros, *_info.hh)                 [reused untouched]
  -> GLSL source assembly (VKShader codegen)        [reuse VK builders, WGSL tweaks]
  -> Shader::run_preprocessor()  (BSL / shader_tool) [backend-agnostic, reused]
  -> shaderc: CompileGlslToSpv(vulkan1.2)            [reuse; produces SPIR-V uint32[]]
  -> tint::spirv::reader::Read -> tint::Program      [NEW: wgpu_shader_compiler.cc]
  -> tint::wgsl::writer::Generate -> WGSL string     [NEW]
  -> wgpuDeviceCreateShaderModule(WGSL)              [NEW; browser accepts WGSL only]
```

Verified anchors (`upstream/source/blender/gpu/`):
- `run_preprocessor` invoked at `vulkan/vk_shader_compiler.cc:195`; the same call exists for all
  backends (it is `Shader::run_preprocessor`, defined in the frontend `intern/`).
- shaderc call `vulkan/vk_shader_compiler.cc:249`; target env vulkan-1.2 `:211`;
  optimization performance `:219`; `SetMaxIdBound(0xffffff)` `:238`.
- SPIR-V disk cache (`.spv` + `.sidecar.bin`, key = `sources_hash`) `:53-121`. The WebGPU
  backend caches WGSL/Tint output instead (browser device consumes WGSL).
- Source assembly: `VKShader::build_shader_module` → `combine_sources` `vulkan/vk_shader.cc:564`;
  create-info codegen (`resources_declare`, `fragment_interface_declare`, push-const emission
  `:845`) is the material a WGSL path reuses.
- shaderc dependency wiring: `gpu/CMakeLists.txt:470` (`bf::dependencies::optional::shaderc`).
  Tint/Dawn: **NOT vendored** here — must be added (see §4).

## 2. What the M3 gpu-module shader corpus actually needs

The gpu-module gtests (`gpu/tests/shader_test.cc`, VERIFIED) create these named create-infos:
`gpu_compute_2d_test`, `gpu_compute_1d_test`, `gpu_compute_vbo_test`, `gpu_compute_ibo_test`,
`gpu_compute_ssbo_test`, `gpu_compute_ssbo_binding_test`, `gpu_sampler_arg_buf_test`,
`gpu_texture_atomic_test`, plus python-defined compute/graphic shaders and a `math_lib` sweep.
So the M3 shader gate exercises: **compute dispatch, SSBO read/write + bindings, sampler
argument buffers, texture atomics, and the math library** — a focused, mostly-compute corpus.
The heavy raster/geometry hazards (below) are largely M4/M6 surface, not M3.

## 3. Per-hazard catalog (scoped to gpu/shaders unless noted; counts VERIFIED via rg)

| Hazard | gpu/shaders | tree-wide | WGSL/WebGPU reality | Disposition |
|---|---:|---:|---|---|
| Push constants | — | — | no push constants | **Solved**: force `StorageType::BUFFER` (UBO), reuse `vk_push_constants.cc:53-64` + codegen `:845`. Set device `maxPushConstantsSize=0`. |
| Combined image sampler | present | — | split `texture` + `sampler` @ distinct `@group/@binding` | **R1/HIGH**: rely on Tint reader split; pin the binding map (probe T2). |
| Geometry-stage injection | — | 0 create-infos | no geometry stage | Only the `do_geometry_shader_injection` workaround path (`vk_shader.cc:1262`) matters; needed for LAYER/VIEWPORT_INDEX/BARYCENTRIC. **M6**, not M3. |
| `imageLoad/Store` | 1 | 122 | storage textures: write-only default, narrow formats | **M6-heavy**; enumerate formats (probe R5). |
| Atomics | 2 | 8 | only `atomic<u32>/<i32>` | Round-trip probe R6 (M3 has `texture_atomic`+`ssbo`). |
| `shared`/`barrier` (workgroup) | 3 | 12 | `var<workgroup>` + `workgroupBarrier()` | Maps cleanly (INFER); verify in compute tests. |
| `gl_PointSize` | 7 | 25 | points always 1px | **M4/M5** UI/overlay; point-sprite expansion. |
| `gl_ClipDistance` | 3 | 3 | `clip_distances` optional feature | `gpu_clip_planes`; enable feature or emulate. |
| Depth convention | — | — | WGSL clip depth is 0..1 (like Vulkan) | **Free**: reuse Vulkan's `retarget_depth` logic (`vk_shader.cc:901-903`) — same convention, no GL -1..1 fixups. |

## 4. WHERE SPIR-V→WGSL runs — M3 vs M4 (the load-bearing decision)

- **M3 (native, this Mac):** link Tint **in-process** (it lives in Dawn's tree,
  `third_party/dawn/src/tint`; build with the SPV reader enabled). Simplest, mirrors HgiWebGPU.
- **M4 (browser):** `--use-port=emdawnwebgpu` ships Dawn **WGSL-only** — the browser build has
  **no SPIR-V reader** (browsers reject SPIR-V modules). Two viable placements, decide by ADR
  after M3 conformance data (GOAL.md defers this):
  - **(A) Runtime tint-wasm.** Compile Tint (SPV reader + WGSL writer) to wasm — the
    `twgsl`/`tint-wasm` precedent — and run the *same* runtime chain as native: shaderc(wasm)
    → SPIR-V → tint(wasm) → WGSL → device. Pro: identical code path M3↔M4, handles arbitrary
    runtime permutations (specialization constants, create-info variants). Con: shaderc(glslang)
    **and** Tint both in the wasm payload = size + first-compile latency; mitigate with the OPFS
    WGSL cache (mirror `vk_shader_compiler.cc:53-121`, but sync-access-handle worker-only per the
    Emscripten posture in GOAL.md).
  - **(B) Offline static corpus + runtime remainder.** Translate the static shader library to
    WGSL at build time (host Tint), ship WGSL; run tint-wasm only for dynamic permutations.
    Pro: smallest runtime, fastest first paint. Con: cannot cover all runtime-generated
    permutations, so still needs (A) as a fallback → more machinery.
  - **Recommendation (INFER):** ship (A) first (correctness + single code path), add (B)'s
    offline pre-bake for the hot static set as an M7 size/latency optimization. A native
    `shader_tool` WGSL target (D-2's "cleaner alternative") is a post-M3 ADR, not an M3 blocker.

## 5. Open questions to resolve during T1/T2 (cheap, before backend LOC)

1. Does Tint's SPIR-V reader, on Blender's shaderc output (optimized, maxIdBound 0xffffff),
   preserve `DescriptorSet=0` + `Binding=n` decorations as WGSL `@group(0) @binding(n)`, and
   how does it number the split sampler vs texture? (Probe T2 — the R1 blocker.)
2. Do specialization constants survive as WGSL `override` → pipeline `constants`? (Blender sets
   them via `GPU_shader_create_from_info` specialization; `specialization_constants_test` is the
   M3 check.)
3. Which Tint/Dawn commit pins cleanly against emcc 6.0.5 / emdawnwebgpu ≥4.0.10 for M4, so the
   native M3 Tint and the browser M4 Tint agree on WGSL output? (Version-pin discipline.)
