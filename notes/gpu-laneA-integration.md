<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M3 integration lane A — context/buffers/shader-chain (progress + T7 recipe)

Pin: Blender 5.2 `fbe6228777e7`; Dawn `chromium/7989`. Lane A owns
context/device/buffers/shaders. Round-3 delta = **patch 0019** (T5 context caps,
T6 storage/vertex/index buffers, T7 shader-chain modules ported in-tree).

## Landed + VERIFIED (patch 0019, bf_gpu green, WITH_WEBGPU_BACKEND=ON)

- **T5** — `wgpu_context.{hh,cc}`: real `activate`/`deactivate` (is_active_ guard)
  + device-probed `capabilities_init()` (`device_.GetLimits()` → `GCaps`,
  modelled on vk_backend.cc:905). instance/adapter getters added (readback WaitAny).
- **T6** — functional `wgpu_storage_buffer.{hh,cc}` (update/clear/copy_sub/read),
  `wgpu_vertex_buffer.{hh,cc}`, `wgpu_index_buffer.{hh,cc}`; backend
  vertbuf/indexbuf/storagebuf allocators upgraded assert→functional. All wrap the
  standalone-proven `webgpu::Buffer` (sandbox/wgpu-buffers 5/5 live). `read()`→const.
- **T7 (foundation)** — the two standalone-proven modules ported in-tree and
  **COMPILING in bf_gpu** at C++20 against the real Tint + shaderc headers:
  `wgpu_shader_interface_map.{hh,cc}` (create-info resource list → sampler_mappings
  + group-0 BGL) and `wgpu_shader_compiler.{hh,cc}` (shaderc GLSL→SPIR-V 1.3 →
  Tint ReadIR/ProgramFromIR/Generate → WGSL). Include dirs wired via additive
  cache vars `TINT_INCLUDE_DIRS` (=build-dawn/dawn) + `SHADERC_INCLUDE_DIR`
  (=lib/macos_arm64/shaderc/include). The compiler .o carries **undefined** Tint
  symbols (`U tint::wgsl::writer::ProgramFromIR` …) — resolved only at
  executable-link time; nothing in-tree calls the modules yet, so no executable
  pulls them and the shared bf_gpu-consuming links (Blender.app, gpu tests) are
  UNAFFECTED (verified: no in-tree caller of compile_shader/build_interface_map).

## T7 remaining (characterized) — the next iteration

1. **`wgpu_shader.{hh,cc}`** — the real `Shader` + `ShaderCompiler` subclass:
   walk `ShaderCreateInfo` resources → `ResourceDesc[]` (dense set-0 N; the adapter
   is a short loop, the struct mirrors create-info 1:1 — notes/gpu-t7pre-findings §6.1);
   GLSL per stage from the create-info codegen via `run_preprocessor()` (reuse the
   Vulkan interface builders, arch §3a); call `compile_shader()`; build
   `WGPUShaderModule`s from the returned WGSL. `WGPUBackend::init_resources()`
   constructs the compiler; `shader_alloc` returns `WGPUShader`. Sampler arrays →
   unroll to scalar samplers at GLSL codegen (Tint parser.cc:200 rejects handle
   arrays — findings §5).
2. **`wgpu_bind_group.{hh,cc}` + pipeline wiring** — cache the returned BGL; compose
   the pipeline layout (lane B's `wgpu_pipeline`).
3. **EXECUTABLE Tint link** — add the Tint archive set to the LIB list of the
   bf_gpu-linked executables (or the gpu module LIB, once a caller exists). The
   EXACT ordered set (extracted from the proven sandbox link, all present under
   `build-dawn/probe-build/dawn/src/tint/` — the same Dawn build that produced the
   linked `libwebgpu_dawn.a`, so no Dawn rebuild):
   `libtint_api`, `libtint_lang_spirv_reader{,_lower,_parser,_common}`,
   `libtint_lang_spirv{,_ir,_intrinsic,_type,_validate}`,
   `libSPIRV-Tools-opt`, `libSPIRV-Tools`,
   `libtint_lang_wgsl_writer{,_ast_printer,_ir_to_program,_raise,_common}`,
   `libtint_lang_wgsl{,_ast,_ir,_intrinsic,_program,_reader*,_resolver,_sem,_inspector}`,
   `libtint_lang_core{,_ir*,_intrinsic,_constant,_type}`,
   `libtint_lang_msl*`, `libtint_lang_null_writer*`, `libtint_api_common`,
   `libtint_utils*`, `libdawn_shared_utils`, `libabsl_*`,
   + **`libshaderc_shared.dylib`** (Blender's own; its bundled SPIRV-Tools stays
   PRIVATE so it can't clash with Tint's SPIRV-Tools on one link line — the T7
   coexistence hazard, findings §2). shaderc **env = vulkan_1_1** (SPIR-V 1.3),
   NOT Blender's 1.2 — Tint's reader hardcodes SPV_ENV_VULKAN_1_1.

## GATE status (honest)

The gpu-suite buffer/shader tests bootstrap through `GPUTest::SetUpTestSuite` →
`GPU_init`, which eagerly warms builtin shaders (`shader_alloc` = T7 remaining) and
`gpu_batch_presets` (`batch_alloc` = **lane B**), both still assert. So GPU_init
cannot complete and NO gpu-suite test runs yet — buffer/shader tests are
**BLOCKED-ON**: T7 `wgpu_shader`/`shader_alloc` (lane A, next) + lane-B
`batch_alloc`. Every landed class builds green and wraps standalone-proven code;
no runtime gpu-suite PASS claimable yet — reported as such.
