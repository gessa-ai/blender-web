<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M3.T4 — GPU_BACKEND_WEBGPU registration + WGPUBackend/WGPUContext skeleton

Uncommitted worker notes for orchestrator review. Pin: Blender 5.2 `fbe6228777e7`;
Dawn `chromium/7989 @ 36cf1fae`. Builds on T3 (patch 0011).

## Per-stage status

| stage | result | evidence |
|---|---|---|
| enum + DNA | **DONE** | `GPU_BACKEND_WEBGPU = 1 << 2` (GPU_platform_backend_enum.h) + `USER_GPU_BACKEND_WEBGPU = 1 << 2` (DNA_userdef_types.h). Additive enum value on a `: short` enum — no layout change, no ABI stop-condition. |
| gpu_context.cc arms | **DONE (compile-proven)** | all 7 arms (include / name / detect / supported / create / get_type / ghost_context_type) added; `bf_gpu` compiles with them. |
| skeleton | **DONE (compile-proven)** | `WGPUBackend` (21 pure-virtuals) + `WGPUContext` (14 Context pure-virtuals) under `source/blender/gpu/webgpu/`; both TUs compile in `bf_gpu`. |
| gpu/CMakeLists WITH_WEBGPU block | **DONE** | SRC + `webgpu` + `intern/ghost/intern` INC + `DAWN_INCLUDE_DIRS`/`DAWN_LIBRARIES` + `-DWITH_WEBGPU_BACKEND`. |
| **bf_gpu build (WITH_WEBGPU_BACKEND=ON)** | **PASS** | `libbf_gpu.a` links; `wgpu_backend.cc.o` + `wgpu_context.cc.o` + `wgpu_storage_buffer.hh` built. |
| **registered-backend runtime verify** | **PASS (exit 0)** | `wgpu_register_verify`: `GPU_backend_type_selection_set(WEBGPU)` → `GPU_context_create` → `WGPUBackend::context_alloc` → **`WGPUContext`, backend name "WebGPU", adapter "Apple M4 Pro", device LIVE**. §4. |

## 1. Patches

- `0011-ghost-webgpu-context.patch` — **regenerated** this task (see §5: the
  original had a mangled top-comment in GHOST_ContextWGPU.hh). Applies clean.
- `0012-gpu-webgpu-backend.patch` — enum + DNA + 7 gpu_context.cc arms + the
  4 `webgpu/` skeleton files + gpu/CMakeLists block. Applies clean on 0011.

## 2. The 21 GPUBackend virtuals — no-op vs assert (deliberate)

`context_alloc` is real; the frame/resource *lifecycle* hooks the bootstrap runs
are safe no-ops; the *resource allocators* assert (filled in T6-T10).

| GPUBackend method | disposition | why |
|---|---|---|
| `context_alloc` | **REAL** | returns `new WGPUContext(...)` wrapping GHOST_ContextWGPU's live device/queue |
| `init_resources` | no-op | `GPU_init` calls it; skeleton warms no caches (no ShaderCompiler yet) |
| `delete_resources` | no-op | `GPU_exit` teardown |
| `render_begin` / `render_end` | no-op | `GPU_render_begin/end` bracket the bootstrap |
| `render_step` | no-op | per-frame coordination; empty is safe |
| `shader_cache_dir_clear_old` | no-op | may run at init/exit; nothing to prune |
| `texturepool_alloc` | **FUNCTIONAL** (`new TexturePoolImpl()`) | **not optional** — `Context::Context()` calls it for EVERY context (gpu_context.cc). Uses the backend-agnostic frontend pool (VKBackend's `texture_pool_workaround` fallback); it only calls `texture_alloc` lazily on acquire, which the bootstrap never reaches. |
| `storagebuf_alloc` | **FUNCTIONAL** (no-op `WGPUStorageBuffer`) | **not optional** — the bootstrap's `DebugDraw::acquire()`→`reset()` allocates + `push_update()`s one storage buffer. A no-op StorageBuf (never read/bound in bring-up) survives; real GPUBuffer impl = T6. |
| `compute_dispatch`, `compute_dispatch_indirect` | **assert** | not reached pre-draw |
| `batch_alloc`, `fence_alloc`, `framebuffer_alloc`, `indexbuf_alloc`, `pixelbuf_alloc`, `querypool_alloc`, `shader_alloc`, `texture_alloc`, `texturepool` (draw-time), `uniformbuf_alloc`, `vertbuf_alloc` | **assert** (`BLI_assert_unreachable` + `nullptr`) | resource creation is T6-T10; `GPU_init`'s batch-presets / shader warm-up would hit these — hence the gate stops before `GPU_init` |

**Discovery (important, corrects §4's earlier guess):** the two allocators above
are *bootstrap-mandatory*, not deferrable — `Context::Context()` needs a texture
pool and `GPU_context_create`'s `DebugDraw` needs a storage buffer. They were
upgraded from assert to minimal-functional so the registered-backend context can
be created. Everything else still asserts.

## 3. The 14 Context virtuals — all safe no-ops

`activate`/`deactivate`/`begin_frame`/`end_frame`/`flush`/`finish` = empty;
`memory_statistics_get` writes 0/0; `debug_capture_begin` returns **false** (not
capturing); `debug_capture_scope_create` returns nullptr; `debug_capture_scope_
begin` returns false; the rest empty. The bootstrap calls `activate` (via
`GPU_context_active_set`), `begin_frame`, `debug_capture_begin` — all covered.

## 4. Where the skeleton stops — and the runtime-verify link wall

Tracing `GPUTest::SetUpTestSuite` (gpu_testing.cc:38-59) against the skeleton:

- `GPU_backend_type_selection_set(WEBGPU)` → OK (arm).
- `GPU_backend_supported()` → `WGPUBackend::is_supported()` → true.
- `createOffscreenContext(WebGPU)` → **GHOST_ContextWGPU, live Dawn device** (T3).
- `GPU_context_create` → `gpu_backend_create` (`new WGPUBackend`) →
  `WGPUBackend::context_alloc` → **`WGPUContext` holding the device**. ← T4 gate.
- `GPU_init()` → `gpu_batch_init`→`gpu_batch_presets_init` and the builtin-shader
  warm-up **allocate** (`vertbuf_alloc`/`batch_alloc`/`shader_alloc`) → the
  skeleton asserts. **So the gate is the pre-`GPU_init` subset**, exactly as the
  brief anticipated. Full `SetUpTestSuite` needs the resource work of T6-T10.

**Runtime-verify link reality (resolved):** `gpu_context.cc` bundles
`GPU_backend_*`, the `Context` base ctor, AND `GPU_context_create` (which calls
`draw::DebugDraw::get().acquire()`) in ONE translation unit, so any executable
that creates a context pulls `draw::DebugDraw` → the entire `draw`+engines+
blenkernel+windowmanager closure (~2986 ninja edges) — the same link as Blender's
combined test binary. Getting the standalone verify to link required disabling
the `WITH_PYTHON=OFF`-incompatible / build-metadata inputs (config, not code):
`-DWITH_FREESTYLE=OFF` (PCH needs Python.h), `-DWITH_AUDASPACE=OFF` (missing
`audaspace-py`), `-DWITH_BUILDINFO=OFF` (`_build_hash`/`_build_commit_timestamp`).
After that the full closure links and the verify runs.

**Runtime result (`wgpu_register_verify`, exit 0):**
```
registered backend name : WebGPU
WGPUContext adapter     : Apple M4 Pro
WGPUContext device      : LIVE
T4 VERIFY PASS: live context created through the REGISTERED WebGPU backend
(GPU_backend_type_selection_set -> GPU_context_create -> WGPUBackend::context_alloc
 -> WGPUContext; pre-GPU_init subset).
```
Runtime bring-up needed `CLG_init()` (the GHOST/GPU path logs through CLOG; the
full `bke::gtest_setup()` pulls gtest infra headers, so just CLG is used).

## 5. patches/0011 was modified this task — explanation

The T3 patch generator's `clean_new_file()` (which stripped a sandbox-only NOTE
paragraph from GHOST_ContextWGPU.hh) removed the `*/` that closed the file's top
comment, so the patched upstream header had an unterminated comment that swallowed
its `#include`s. The T3 *sandbox* verify passed because it compiled the clean
sandbox copy, not the patched file — the defect only surfaced when `bf_gpu`
compiled the patched `wgpu_context.cc` (`unknown type name 'GHOST_ContextParams'`).
Fix: regenerate 0011 from the sandbox files **verbatim** (no NOTE-stripping). The
change is comment-only in one new file; enum/CMake/SystemHeadless hunks are
byte-identical. 0011 now applies clean and `bf_gpu` compiles.

## 6. Temp verify harness (patches/9999) — disposition

`9999-t4-verify-harness.patch` (a throwaway `wgpu_register_verify` executable +
the CMake target that links `bf_gpu`) was **deleted** and reverse-applied from
upstream — the port series is exactly 0011+0012, with no heavy throwaway target
in the normal build. The verify main lives at
`sandbox/dawn-probe/webgpu-skeleton/wgpu_register_verify.cc`. To reproduce the
gate, append this inside the `if(WITH_WEBGPU_BACKEND)` block of
`source/blender/gpu/CMakeLists.txt` and build the target:

```cmake
if(WITH_GTESTS)
  add_executable(wgpu_register_verify webgpu/wgpu_register_verify.cc)
  target_include_directories(wgpu_register_verify PRIVATE
    $<TARGET_PROPERTY:bf_gpu,INCLUDE_DIRECTORIES> ${DAWN_INCLUDE_DIRS})
  target_link_libraries(wgpu_register_verify PRIVATE bf_gpu)
endif()
```
Configure `build-native-gpu` with `-DWITH_WEBGPU_BACKEND=ON` + the DAWN vars +
`-DWITH_FREESTYLE=OFF -DWITH_AUDASPACE=OFF -DWITH_BUILDINFO=OFF`, then
`ninja -C build-native-gpu wgpu_register_verify && build-native-gpu/bin/wgpu_register_verify`.

## 7. Deliverables

- Patches `0011` (regenerated) + `0012`; skeleton sources committed via 0012.
- `sandbox/dawn-probe/webgpu-skeleton/` (the source form + the verify main).
- upstream HEAD untouched (`fbe6228`); `build-native-gpu/` + `lib/macos_arm64/`
  gitignored.
