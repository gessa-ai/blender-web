# M3 — WebGPU backend architecture & implementation plan

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

Author: gpu-backend architect. Pin: Blender 5.2 LTS `fbe6228777e7`. READ-ONLY recon; every
claim is cited `path:line` against `upstream/`. **VERIFIED** = read at the pin. **INFER** =
reasoned from verified facts + WebGPU/Dawn semantics (not in-tree). A precise uncertainty is
flagged, not smoothed over. Companion: `notes/gpu-shader-chain.md` (deep shader hazards + the
M4 in-browser Tint decision).

Design target: a new `source/blender/gpu/webgpu/` backend implementing the `GPUBackend`
surface against **native Dawn** (`webgpu.h` / `webgpu_cpp.h`), gated by Blender's own `gpu`
module gtests on this Mac (M3), before any Emscripten/browser work (M4).

---

## 0. Headline numbers (derived, not guessed)

- Vulkan backend production code (excl. tests): **28,062 LOC** (VERIFIED, `wc -l` all
  `.cc/.hh` under `upstream/source/blender/gpu/vulkan/` minus `tests/` + `render_graph/tests/`).
- Single biggest deletion: **`render_graph/` = 6,658 LOC** of production code that WebGPU's
  implicit driver model makes **entirely unnecessary** (automatic hazard tracking, barrier
  insertion, command scheduling — all done by the WebGPU implementation).
- **Evidence-based webgpu/ estimate: ~13,000–17,000 LOC (central ~15k)**, replacing the
  12–22k guess in GOAL.md/D-2 with a tighter, lower band. Derivation in §2.
- Backend surface: **19 pure-virtuals** on `GPUBackend` (14 allocators incl. `context_alloc`,
  2 compute-dispatch, 3 render-frame, `init/delete_resources`, `shader_cache_dir_clear_old`).
  `StateManager` and `Immediate` are **not** backend factories — they are created by the
  `Context` subclass. `DrawList` is gone (confirmed absent from the surface).

---

## 1. The exact `GPUBackend` surface at this pin

Source of truth: `upstream/source/blender/gpu/intern/gpu_backend.hh:39-82` (VERIFIED, full read).

### 1a. Pure-virtual methods (all `= 0`)

| # | Method (gpu_backend.hh) | Returns | Vulkan override | WebGPU mapping |
|---|---|---|---|---|
| 1 | `init_resources()` :47 | void | vk_backend.cc | Create the `ShaderCompiler` (`compiler_`), warm caches. Dawn device already up via context. |
| 2 | `delete_resources()` :48 | void | vk_backend.cc | Destroy compiler + global caches. |
| 3 | `compute_dispatch(x,y,z)` :58 | void | vk_backend.cc | `wgpuComputePassEncoderDispatchWorkgroups`. |
| 4 | `compute_dispatch_indirect(StorageBuf*)` :59 | void | vk_backend.cc | `...DispatchWorkgroupsIndirect(buf,off)`. |
| 5 | `context_alloc(GHOST_IWindow*, GHOST_IContext*)` :61 | `Context*` | `VKContext` (vk_context, 846) | `WGPUContext`. |
| 6 | `batch_alloc()` :63 | `Batch*` | `VKBatch` (vk_batch, 178) | `WGPUBatch`. |
| 7 | `fence_alloc()` :64 | `Fence*` | `VKFence` (vk_fence, 61) | `WGPUFence` (queue `onSubmittedWorkDone`). |
| 8 | `framebuffer_alloc(name)` :65 | `FrameBuffer*` | `VKFrameBuffer` (vk_framebuffer, 946) | `WGPUFrameBuffer` → `GPURenderPassDescriptor`. |
| 9 | `indexbuf_alloc()` :66 | `IndexBuf*` | `VKIndexBuffer` (vk_index_buffer, 195) | `WGPUIndexBuffer`. |
| 10 | `pixelbuf_alloc(size)` :67 | `PixelBuffer*` | `VKPixelBuffer` (vk_pixel_buffer, 164) | `WGPUPixelBuffer` (mappable `GPUBuffer`). |
| 11 | `querypool_alloc()` :68 | `QueryPool*` | `VKQueryPool` (vk_query, 159) | `WGPUQueryPool` (`GPUQuerySet`). |
| 12 | `shader_alloc(name)` :69 | `Shader*` | `VKShader` (vk_shader, 1634) | `WGPUShader`. |
| 13 | `texture_alloc(name)` :70 | `Texture*` | `VKTexture` (vk_texture, 1089) | `WGPUTexture`. |
| 14 | `texturepool_alloc()` :71 | `TexturePool*` | `VKTexturePool` (vk_texture_pool, 768) | `WGPUTexturePool`. |
| 15 | `uniformbuf_alloc(size,name)` :72 | `UniformBuf*` | `VKUniformBuffer` (vk_uniform_buffer, 188) | `WGPUUniformBuffer`. |
| 16 | `storagebuf_alloc(size,usage,name)` :73 | `StorageBuf*` | `VKStorageBuffer` (vk_storage_buffer, 234) | `WGPUStorageBuffer`. |
| 17 | `vertbuf_alloc()` :74 | `VertBuf*` | `VKVertexBuffer` (vk_vertex_buffer, 303) | `WGPUVertexBuffer`. |
| 18 | `shader_cache_dir_clear_old()` :75 | void | `VKShaderCompiler::cache_dir_clear_old()` | prune WGSL/SPIR-V OPFS cache. |
| 19 | `render_begin/end/step(bool)` :79-81 | void | vk_backend.cc | per-frame resource release / submit boundaries. |

Non-virtual: `get_compiler()` :53 returns `compiler_` (a `ShaderCompiler*` the backend
constructs in `init_resources`). `ShaderCompiler` is therefore **created by the backend but
not through a virtual factory** — the WebGPU backend allocates its `WGPUShaderCompiler` in
`init_resources()`, exactly as `VKBackend` does (vk_backend.hh:88 wires
`VKShaderCompiler::cache_dir_clear_old`).

### 1b. Classes created by the `Context` (not the backend)

`StateManager` and `Immediate` are per-context. `VKContext` constructs `VKStateManager`
(vk_state_manager, 411) and `VKImmediate` (vk_immediate, 205). The WebGPU `Context` does the
same → `WGPUStateManager`, `WGPUImmediate`. The frontend base classes these all derive from
live in `gpu/intern/` and are **reused untouched** (`Context` in gpu_context.hh, `Shader`/
`ShaderCompiler` in gpu_shader_private.hh, `StateManager` in gpu_state_private.hh, `Immediate`
in gpu_immediate_private.hh, etc.). This confirms D-2: the 71-file frontend is backend-agnostic.

### 1c. Backend registration (integration edits, additive, land in `patches/`)

- Enum: `GPU_BACKEND_WEBGPU = 1 << 2` — the **unused bit** (VERIFIED
  `GPU_platform_backend_enum.h:14-20`: OPENGL 1<<0, METAL 1<<1, VULKAN 1<<3; **1<<2 is free**).
  Must be mirrored in DNA `eUserPref_GPUBackendType` (`DNA_userdef_types.h:207-209`,
  `USER_GPU_BACKEND_* `, same bit pattern — comment at enum head demands they stay in sync).
- Switch arms to extend (all in `intern/gpu_context.cc`, VERIFIED): `gpu_backend_type_name`
  :450, `GPU_backend_type_selection_detect` :475, `gpu_backend_supported` :511,
  `gpu_backend_create` :548 (`new WGPUBackend`), `GPU_backend_get_type` :597 (dynamic_cast),
  `ghost_context_type` :639 (→ `GHOST_kDrawingContextTypeWebGPU`). Each is an **additive
  `#ifdef WITH_WEBGPU_BACKEND` case** — no upstream logic rewritten, satisfying the ground rule.
- CMake option `WITH_WEBGPU_BACKEND` mirroring `WITH_VULKAN_BACKEND` (top `CMakeLists.txt`) and
  the `gpu/CMakeLists.txt:462-474` block (`list(APPEND SRC ${WEBGPU_SRC})`, link Dawn + reuse
  `bf::dependencies::optional::shaderc`, `add_definitions(-DWITH_WEBGPU_BACKEND)`).

---

## 2. Where Vulkan's ~28k LOC goes, and the webgpu/ estimate

Measured groups (VERIFIED, non-overlapping partition of the 21,378 top-level LOC + the 6,658
`render_graph/` production LOC; script partition sums exactly):

| Group | Vulkan LOC | Fate under WebGPU's implicit model | webgpu/ est. |
|---|---:|---|---:|
| `render_graph/` (command graph, scheduler, barriers, 25 node types) | 6,658 | **ELIMINATED.** WebGPU driver auto-tracks hazards, inserts barriers, orders work. Keep only a thin command-encoder wrapper. | 0–300 |
| Descriptor (pools/sets/layouts/push_constants) | 1,734 | **Shrinks hard.** No pool alloc/recycle. Bind-group + layout objects remain, but WebGPU builds them from reflection. Push-constants → UBO (see §3). | 600–900 |
| Memory/staging (buffer, VMA pool, staging, streaming, resource_pool, data_conversion) | 3,267 | **Shrinks hard.** No explicit allocation (no VMA), no manual staging/streaming — `queue.writeBuffer` + `mapAsync`. `vk_data_conversion` (1,456) mostly **stays** (pixel-format conversion still needed; WebGPU has fewer formats). | 1,400–1,900 |
| Pipeline (pipeline_pool 1,243, graphics_pipeline 766) | 2,009 | **Shrinks.** No `VkPipelineLayout`/`VkRenderPass` objects. Still need a `GPURender/ComputePipeline` descriptor builder + cache. | 1,200–1,700 |
| Shader (shader, compiler, interface, module, log) | 2,805 | **Similar / grows.** Reuse GLSL codegen + shaderc→SPIR-V; **add** Tint SPIR-V→WGSL driver (~300). Interface/reflection stays. | 2,800–3,400 |
| Device/ctx/backend (device, submission, common, debug, to_string, ghost_api, backend, context) | 5,840 | **Shrinks moderately.** No instance/physical-device/queue-family/extension enumeration (`vk_device` 1,116 + `vk_device_submission` 325 collapse to a ~200-line adapter/device request). `vk_common` enum maps stay (~900). `vk_to_string` 1,017 is debug-only → mostly drop. | 2,600–3,500 |
| API objects (texture, framebuffer, vert/index/uniform/storage buf, sampler, state, immediate, batch, pixel, query, fence, VAO) | 5,723 | **Similar.** Thin wrappers over `GPUBuffer`/`GPUTexture`. `framebuffer` (946) simplifies (transient render pass, no `VkFramebuffer`); rest ~constant. | 4,000–4,800 |
| **Totals** | **28,036** (+26 blit-shader `.hh`) | | **≈ 13k–17k** |

**Estimate: ~13,000–17,000 LOC of hand-written webgpu/ (central ~15,000)**, plus vendored Tint
(not counted — it is a dependency, not our code). The dominant saving is render_graph (a clean
6.7k deletion): WebGPU *is* the render graph. Second saving is the memory/device plumbing that
WebGPU's implicit allocation absorbs. The estimate lands **below** the middle of the 12–22k
guess because render_graph and the VMA/staging layer are larger and more cleanly eliminable
than the guess assumed, while shader/data-conversion/API-object code is essentially conserved.

Uncertainty band drivers (why not a point estimate): (i) bind-group churn — WebGPU bind groups
are immutable, so per-draw rebind bookkeeping may exceed Vulkan's descriptor-set tracker;
(ii) how much `vk_common`/`vk_data_conversion` format logic transfers vs. needs a WebGPU-specific
rewrite; (iii) whether the WGSL shader-interface reflection needs materially more code than
Vulkan's SPIR-V reflection.

---

## 3. Shader chain, concretely

Full mechanics + the extended per-shader hazard catalog: `notes/gpu-shader-chain.md`.
Summary of the M3 chain:

### 3a. How the Vulkan path drives shaderc at runtime (VERIFIED)

- Entry point: `VKShaderCompiler::compile_module(VKShader&, shaderc_shader_kind, VKShaderModule&)`
  (`vk_shader_compiler.cc:259`) → `compile_ex` → `compiler.CompileGlslToSpv(sources, stage,
  name, options)` :249 using Google **shaderc** (`shaderc::Compiler` :263).
- **Input is GLSL text**, not SPIR-V. It is `VKShaderModule::combined_sources`, assembled by
  `VKShader::build_shader_module` → `combine_sources()` (`vk_shader.cc:564`) from the
  **create-info codegen** (`fragment_interface_declare`, `resources_declare`, geometry/vertex
  interface builders in vk_shader.cc) run through `Shader::run_preprocessor()` (the backend-
  agnostic BSL/`shader_tool` preprocessor, invoked at `vk_shader_compiler.cc:195`).
- Dialect/target: `SetTargetEnvironment(shaderc_target_env_vulkan, shaderc_env_version_vulkan_1_2)`
  :211, `SetOptimizationLevel(performance)` :219, `SetMaxIdBound(0xffffff)` :238. So the
  produced SPIR-V is **Vulkan 1.2 flavour** — separate descriptor sets/bindings, Vulkan
  builtins, 0..1 depth convention.
- Disk cache: `.spv` + `.sidecar.bin` keyed on `sources_hash` (:53-121). **This is the cache
  D-2 says to mirror onto OPFS** — but for WGSL we cache the *WGSL* (or the Tint output),
  since the browser device consumes WGSL, not SPIR-V.
- shaderc dependency: `bf::dependencies::optional::shaderc` (`gpu/CMakeLists.txt:470`), built by
  the superbuild (google/shaderc, `build_files/build_environment/cmake/versions.cmake`).

### 3b. Where Tint slots in

New step after shaderc, in a new `wgpu_shader_compiler.cc`:
`shaderc → SPIR-V (uint32 words) → tint::spirv::reader::Read(words, opts) → tint::Program →
tint::wgsl::writer::Generate(program, opts) → WGSL string → wgpuDeviceCreateShaderModule(WGSL)`.
This mirrors Autodesk HgiWebGPU (D-2). C++ surface needed: Tint's SPIR-V **reader** (requires
the SPV-reader build flag) and WGSL **writer**. Tint lives **inside Dawn's tree**
(`third_party/dawn/src/tint`) — it is **not vendored in this repo** (VERIFIED: nothing under
`extern/` matches dawn/tint/shaderc; the only shaderc reference is the Vulkan superbuild
recipe). So Dawn/Tint must be **added as a dependency**:
- **M3 (native, this Mac):** add a Dawn native build to the superbuild (or `find_package(Dawn)`)
  with the SPIR-V reader enabled; link `webgpu_dawn` (+ Tint). In-process Tint call.
- **M4 (browser):** `--use-port=emdawnwebgpu` provides Dawn **WGSL-only** — the browser Dawn
  has **no SPIR-V reader**. So SPIR-V→WGSL must run either (a) at runtime via **tint-compiled-
  to-wasm** (the `twgsl`/`tint-wasm` precedent in D-2), or (b) **offline** for the static shader
  corpus with runtime translation only for dynamic permutations. Decision deferred to
  `gpu-shader-chain.md` §4 with an ADR after M3 conformance data (matches GOAL.md).

### 3c. The nastiest translation hazards (checked against the pin's actual shaders)

Shader-tree scan (VERIFIED, `rg` over `source/blender`): 613 `.glsl` tree-wide; **220 in
`gpu/shaders/`** (the M3 gpu-module corpus). Counts below are `gpu/shaders/` unless noted.

1. **Push constants → no WGSL equivalent. LOW risk (machinery exists).** WGSL/WebGPU has no
   push constants. Vulkan **already** falls back to a UBO: `VKPushConstants::StorageType::BUFFER`
   (`vk_push_constants.cc:53-64` `determine_storage_type` returns FALLBACK when size >
   `maxPushConstantsSize`; the codegen emits `layout(binding=N) uniform` for that path,
   `vk_shader.cc:845`). WebGPU: set device `maxPushConstantsSize = 0` → **always BUFFER**. Reuse
   the existing emulation wholesale.
2. **Combined image samplers → separated in WGSL. MEDIUM-HIGH risk (the nastiest).** GLSL
   `sampler2D` → SPIR-V `OpTypeSampledImage`; WGSL/WebGPU **requires** split `texture_2d<f32>` +
   `sampler` at distinct `@group @binding`. Tint's SPIR-V reader can split these, but the
   binding-number remapping it invents must match the bind-group layout Blender's
   `shader_interface` builds. This is the single most likely source of silent mis-binding.
3. **Geometry-shader workaround injection → no WGSL geometry stage. HIGH risk for M6, LOW for
   M3.** No create-info declares `geometry_source` at the pin (VERIFIED: 0 hits tree-wide; the
   two `*geom*.glsl` files are *math* libs, not geometry stages). BUT
   `VKShader::do_geometry_shader_injection` (`vk_shader.cc:1262`) **synthesises** a geometry
   stage when `BuiltinBits::LAYER`, `VIEWPORT_INDEX`, or `BARYCENTRIC_COORD` is requested and
   the extension is missing. WebGPU has **no geometry stage at all**, so this emulation is
   unavailable — impacts layered rendering (cubemap/shadow arrays, EEVEE), viewport arrays, and
   barycentrics. The M3 gpu-module tests do not exercise it; flag for M6.
4. **Storage images / `imageLoad`/`imageStore`. MEDIUM (heavy for M6).** Only **1** file in
   `gpu/shaders/` uses it (122 tree-wide). WGSL storage textures are restricted: write-only by
   default (read-write needs a feature), a limited format list, no auto format conversion.
5. **SSBO std430 + atomics. MEDIUM.** **2** atomic files in `gpu/shaders/` (8 tree-wide). WGSL
   only supports `atomic<u32>`/`atomic<i32>`; std430 struct layout differs (vec3 aligns to 16,
   array stride rules). Tint handles layout, but Blender's GLSL std430 assumptions must survive
   the round-trip.
6. **`gl_PointSize` → WebGPU points are always 1px. MEDIUM.** **7** files in `gpu/shaders/` (25
   tree-wide). Blender already faces this on Metal; point-sprite expansion paths exist but must
   be exercised. Also **`gl_ClipDistance`** (3 files) → WGSL `clip_distances` is an optional
   feature — affects `gpu_clip_planes`.

---

## 4. Dawn-native test harness plan (this Mac)

### 4a. What tests exist and how they bootstrap (VERIFIED)

`gpu/tests/` = **17 files, ~7,822 LOC**. The M3 gate is these (minus `shader_preprocess_test.cc`,
3,368 LOC, which is backend-agnostic). Bootstrap: `GPUTest::SetUpTestSuite` (`gpu_testing.cc:31`):
`bke::gtest_setup()` → `GPU_backend_type_selection_set(backend)` → `GHOST_ISystem::
createSystemBackground()` → `getSystem()` → `createOffscreenContext(gpu_settings{context_type})`
→ `activateDrawingContext()` → `GPU_context_create(nullptr, ghost_context)` → `GPU_init()`. Then
`GPU_TEST(name)` (`gpu_testing.hh:163`) expands to per-backend `TEST_F` variants (OpenGL, Metal,
Vulkan). **Everything is headless/offscreen — no window, no surface.**

### 4b. Minimal changes to run against native Dawn

1. GHOST enum: add `GHOST_kDrawingContextTypeWebGPU` to `GHOST_Types.hh:274` (VERIFIED enum:
   None/OpenGL/D3D/Metal/Vulkan).
2. New `intern/ghost/intern/GHOST_ContextWGPU.{hh,cc}` (native Dawn): create
   `WGPUInstance`→`RequestAdapter`→`RequestDevice`, **no surface** (offscreen). ~250 LOC.
3. Add a `case GHOST_kDrawingContextTypeWebGPU` under `#ifdef WITH_WEBGPU_BACKEND` to
   `GHOST_SystemHeadless::createOffscreenContext` (`GHOST_SystemHeadless.hh:116`, VERIFIED it
   already switches on `context_type` and returns `GHOST_ContextVK` for Vulkan).
4. Add `GPUWebGPUTest` class + `GPU_WEBGPU_TEST(name)` macro to `gpu_testing.hh` mirroring
   `GPUVulkanTest`/`GPU_VULKAN_TEST` (:121, :150), and add it to the composite `GPU_TEST` (:163).
5. Build option `WITH_WEBGPU_BACKEND` + the enum/switch integration from §1c.

### 4c. Smallest path + Metal coexistence (VERIFIED + INFER)

`createSystemBackground()` → `createSystem(background=true)` picks the platform system, but under
**`WITH_HEADLESS`** it uses `GHOST_SystemHeadless` (`GHOST_ISystem.cc:29,58`; on macOS it would
otherwise be `GHOST_SystemCocoa`). **Smallest path: build the M3 gpu-test binary with
`WITH_HEADLESS=ON`** so only the headless offscreen case (step 3) is needed — no Cocoa/window
integration.

Metal-vs-Dawn coexistence is a **non-issue at runtime** (INFER, high confidence): native Dawn on
macOS uses Metal *internally* and creates its **own** `MTLDevice`, entirely separate from
Blender's `MTLBackend`. macOS permits many concurrent `MTLDevice`s. The only interaction is at
the symbol/enum level, and the gpu tests select the backend **explicitly**
(`GPU_backend_type_selection_set(GPU_BACKEND_WEBGPU)`), so there is no auto-selection collision.
Build the M3 test binary with `WITH_WEBGPU_BACKEND=ON` and `WITH_METAL_BACKEND=OFF` to keep the
link surface clean; both-on also compiles (each backend is `#ifdef`-guarded in the switch).

---

## 5. File-by-file skeleton — `source/blender/gpu/webgpu/`

Naming mirrors `vulkan/` with a `wgpu_` prefix. `render_graph/` and the descriptor-pool / VMA /
staging / streaming files have **no counterpart** (folded away). LOC = estimate. This table is
the worker task breakdown.

| File pair | Responsibility | LOC |
|---|---|---:|
| `wgpu_backend.{hh,cc}` | `GPUBackend` impl: 19 factories, `is_supported`, adapter/device request, compute_dispatch, render_begin/end/step | 700 |
| `wgpu_context.{hh,cc}` | `Context`: queue, command-encoder lifecycle, per-frame submit, creates StateManager+Immediate | 700 |
| `wgpu_device.{hh,cc}` | `WGPUAdapter/Device/Queue` wrapper, limits/features, `capabilities_init` (replaces vk_device 1116) | 450 |
| `wgpu_common.{hh,cc}` | GPU↔WGPU enum/format conversion tables (mirror vk_common) | 900 |
| `wgpu_debug.{hh,cc}` | error scopes, debug groups/labels | 200 |
| `wgpu_shader.{hh,cc}` | `Shader`: create-info→GLSL codegen (reuse VK builders), drives compiler, module/pipeline wiring | 1400 |
| `wgpu_shader_compiler.{hh,cc}` | shaderc GLSL→SPIR-V (reuse) + **Tint SPIR-V→WGSL** + WGSL cache (OPFS at M4) | 500 |
| `wgpu_shader_interface.{hh,cc}` | binding reflection → bind-group-layout mapping (combined-sampler split lives here) | 600 |
| `wgpu_shader_module.{hh,cc}` | per-stage WGSL + `WGPUShaderModule` | 150 |
| `wgpu_pipeline.{hh,cc}` | render/compute pipeline descriptor build + cache (replaces pipeline_pool+graphics_pipeline) | 1300 |
| `wgpu_bind_group.{hh,cc}` | bind group + layout build/cache (replaces descriptor_set/pools/layouts) | 700 |
| `wgpu_push_constants.{hh,cc}` | push-constant UBO emulation, BUFFER path only | 350 |
| `wgpu_buffer.{hh,cc}` | `GPUBuffer` wrapper + `writeBuffer`/`mapAsync` (replaces buffer/pool/staging/streaming/memory) | 500 |
| `wgpu_vertex_buffer.{hh,cc}` | `VertBuf` | 250 |
| `wgpu_index_buffer.{hh,cc}` | `IndexBuf` | 150 |
| `wgpu_uniform_buffer.{hh,cc}` | `UniformBuf` | 120 |
| `wgpu_storage_buffer.{hh,cc}` | `StorageBuf` | 180 |
| `wgpu_texture.{hh,cc}` | `Texture` + views | 900 |
| `wgpu_texture_pool.{hh,cc}` | `TexturePool` | 250 |
| `wgpu_pixel_buffer.{hh,cc}` | `PixelBuffer` (mappable buffer) | 120 |
| `wgpu_framebuffer.{hh,cc}` | `FrameBuffer` → `GPURenderPassDescriptor` build | 600 |
| `wgpu_sampler.{hh,cc}` / `wgpu_samplers.{hh,cc}` | sampler cache | 180 |
| `wgpu_state_manager.{hh,cc}` | `StateManager` → pipeline-state assembly | 350 |
| `wgpu_immediate.{hh,cc}` | `Immediate` | 250 |
| `wgpu_batch.{hh,cc}` | `Batch` → draw encoding | 250 |
| `wgpu_vertex_input.{hh,cc}` | vertex-buffer layout for the pipeline (replaces VAO/vertex_input) | 200 |
| `wgpu_fence.{hh,cc}` | `Fence` → `onSubmittedWorkDone` | 80 |
| `wgpu_query.{hh,cc}` | `QueryPool` → `GPUQuerySet` (timestamp/occlusion) | 150 |
| `wgpu_data_conversion.{hh,cc}` | pixel-format conversion (port vk_data_conversion) | 1200 |
| `wgpu_ghost_api.hh` | GHOST↔WGPU glue | 60 |
| **Total** | | **~14,300** |

(Plus `CMakeLists.txt` `WEBGPU_SRC` block + the `patches/` integration edits from §1c.)

---

## 6. Risk register (ranked) + earliest cheap probe

| # | Risk | Sev | Earliest cheap probe |
|---|---|---|---|
| R1 | **Combined image sampler split**: Tint's SPIR-V→WGSL binding remap doesn't match Blender's bind-group layout → silent wrong-texture. | HIGH | Feed one `sampler2D` create-info's SPIR-V (from shaderc) through native Tint, dump the WGSL `@group/@binding`, diff against `wgpu_shader_interface` expectations. One `.cc` harness, no backend needed. |
| R2 | **Dawn/Tint native build + SPV reader** not trivially available in the superbuild; `webgpu_cpp.h` API churn (GOAL flags it unstable). | HIGH | Build Dawn native on this Mac at a pinned commit with `TINT_BUILD_SPV_READER=ON`; compile a 20-line SPIR-V→WGSL round-trip. Blocks everything else. |
| R3 | **Layered rendering / geometry-injection gap** (LAYER/VIEWPORT_INDEX/barycentric) — no WGSL geometry stage; needed by EEVEE (M6). | HIGH (M6) | Grep create-infos for `BuiltinBits::LAYER/VIEWPORT_INDEX` users; prototype a multi-pass or `@builtin` alternative on one shadow-cube shader. Defer to M6, but scope now. |
| R4 | **Bind-group immutability churn**: WebGPU bind groups can't be patched → per-draw re-creation may blow the LOC/perf budget vs Vulkan's descriptor tracker. | MED | Micro-bench: N draws rebinding one UBO offset via fresh bind groups vs a cached-by-key scheme, native Dawn. Informs `wgpu_bind_group` design. |
| R5 | **Storage-texture format/access limits** (write-only default, narrow format list). | MED (M6) | Enumerate storage-image formats used across `draw/`+`eevee/` shaders; cross-check against WebGPU's guaranteed storage formats. Pure `rg`, no code. |
| R6 | **std430/atomic round-trip** through Tint changes layout/semantics. | MED | Round-trip the `gpu_compute_ssbo_test` + `gpu_texture_atomic_test` create-infos; run the existing `storage_buffer_test`/`shader_texture_atomic` against native Dawn. |
| R7 | **`gl_PointSize` / `gl_ClipDistance`** unsupported → UI/overlay + clip-plane breakage. | MED | Run `immediate_test` (points) + a clip-plane shader against Dawn; check point-sprite fallback path. |
| R8 | **WGSL shader cache** semantics on OPFS (sync-access-handle worker-only) diverge from the disk cache. | LOW (M4) | Deferred to M4; the M3 cache is native filesystem (reuse the Vulkan cache shape). |

---

## 7. First 10 implementation tasks (dependency order) — paste into fix_plan.md M3

Each is independently verifiable. T1–T3 de-risk the two HIGH risks before any backend LOC.

1. **T1 — Dawn+Tint native toolchain probe (R2).** Build Dawn native on this Mac at a pinned
   commit with SPV reader on; a standalone `.cc` does shaderc(GLSL)→SPIR-V→Tint→WGSL→
   `wgpuDeviceCreateShaderModule` on one trivial shader. *Verify:* WGSL prints, module validates,
   process exits 0. **Blocks all.**
2. **T2 — Combined-sampler binding audit (R1).** Extend T1's harness to a `sampler2D` +
   push-constant + UBO create-info; dump Tint's `@group/@binding` for texture vs sampler vs UBO.
   *Verify:* documented, deterministic binding map → feeds `wgpu_shader_interface` spec.
3. **T3 — GHOST WebGPU offscreen context.** `GHOST_kDrawingContextTypeWebGPU` +
   `GHOST_ContextWGPU` (native Dawn, no surface) + `GHOST_SystemHeadless` case + `WITH_WEBGPU_
   BACKEND` option. *Verify:* a headless bin calls `createOffscreenContext` and gets a live
   `WGPUDevice`.
4. **T4 — Backend + enum registration skeleton.** `GPU_BACKEND_WEBGPU=1<<2` + DNA sync + all
   `gpu_context.cc` switch arms + `WGPUBackend` stub whose 19 factories return
   `BLI_assert_unreachable` placeholders. *Verify:* `GPU_backend_type_selection_set(WEBGPU)` +
   `GPU_backend_supported()` returns true; links.
5. **T5 — Context + device + capabilities.** `WGPUContext`, `WGPUDevice` (adapter/device/queue,
   limits→`GPU_capabilities`), `wgpu_common` format tables. *Verify:* `GPU_context_create` +
   `GPU_init()` succeed under the gpu-test bootstrap (SetUpTestSuite runs green with no draws).
6. **T6 — Buffers (vert/index/uniform/storage) + `wgpu_buffer`.** `writeBuffer`/`mapAsync`.
   *Verify:* `vertex_buffer_test`, `index_buffer_test`, `storage_buffer_test` pass on Dawn.
7. **T7 — Shader compile pipeline end-to-end.** `WGPUShader` + `wgpu_shader_compiler` (reuse VK
   codegen + shaderc, add Tint) + `wgpu_shader_interface` (T2's map) + `wgpu_bind_group` +
   push-constant UBO. *Verify:* `shader_create_info_test` + the `shader_test` compute-create
   cases compile.
8. **T8 — Compute dispatch + SSBO/atomics (R6).** `compute_dispatch(_indirect)`, compute
   pipeline. *Verify:* `compute_test`, `shader_ssbo_binding`, `shader_texture_atomic` pass.
9. **T9 — Textures + samplers + pixel buffer + data conversion (R5).** `WGPUTexture`, views,
   `wgpu_data_conversion`. *Verify:* `texture_test`, `texture_view_test`, `buffer_texture_test`.
10. **T10 — Framebuffer + render pipeline + state + immediate + batch.** Render pass build,
    `WGPURenderPipeline`, `WGPUStateManager`, `WGPUImmediate`, `WGPUBatch`. *Verify:*
    `framebuffer_test`, `state_blend_test`, `immediate_test`, `push_constants_test`,
    `specialization_constants_test` → **M3 gate: full `gpu` suite green on native Dawn.**
