<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# cycle-6 step 2 — browser GPU render harness (the pixels-in-the-link vehicle)

A dedicated small wasm binary that LINKS the REAL Blender WebGPU backend
(`build-wasm-gpu/lib/libbf_gpu.a`) + its minimal dep closure + the emdawnwebgpu web
context, and drives the gpu-module API to render a triangle offscreen in a browser
tab. Location: `sandbox/gpu-render-harness/` (page + boot in `web/`).

Model: `source/blender/gpu/tests/gpu_testing.cc` (bootstrap, minus gtest) +
`platform_web/ghost/harness-wgpu/` (async boot + readback→PNG page).

## RESULT — GPU_init COMPLETES and a REAL shader COMPILES in a WebGPU tab (2026-08-05, M3.F5)

Verified in a real WebGPU browser (Claude Browser pane: `navigator.gpu`=true,
`crossOriginIsolated`=true, COOP/COEP server, Chrome 148). The 22 MB `gpu_harness.wasm`
now reports, in order (evidence: `evidence/intab_gpu_init_shader_finalize.txt`):

```
backend = WEBGPU; creating GHOST_ContextWGPUWeb on '#gpucanvas'
CONTEXT OK: emdawnwebgpu device acquired
GPU_context_create OK (WGPUContext borrowed the device)   <- seam (patch 0037) works
GPG.init + main-context-workaround set                    <- harness workarounds (A,B below)
GPU_init OK                                               <- GPU_init COMPLETES in-tab
GPU_texture_create_2d OK
framebuffer bound + cleared to (0.10, 0.45, 0.85, 1.0)
FIRST PIXELS (clear readback) center RGBA=(99,52,32,98)   <- readback pipeline runs (garbage; blocker D)
binding GPU_SHADER_3D_UNIFORM_COLOR (-> shader finalize)
SHADER FINALIZE OK — builtin program bound               <- REAL shader compiled in-tab:
       GLSL create-info -> SPIR-V (shaderc) -> WGSL (Tint) -> wgpuDeviceCreateShaderModule
```

So the real WebGPU backend runs `GPU_init` to COMPLETION and compiles a real Blender
builtin shader — **in a browser tab**. The readback pipeline executes and produces a
256×256 PNG, but its content is uninitialised (blocker D). Correct pixels remain gated
on blockers C (immediate mode) and D (async readback), both routed to lane A.

- **Node** (no `navigator.gpu`): links + boots + selects WEBGPU + kicks the async
  device request, then `CONTEXT FAIL` (no device) — validates the whole 21 MB link.

## The link closure (determined empirically)

Naive link → 651 undefined; **640 were `datatoc_*` shader-source blobs** resolved by
the shader archives. The real code closure is tiny — after adding the shader archives
+ tbb + fmt, only **5 residual externals** remained, all trivial for an offscreen
triangle and provided by `harness_stubs.cc` (harness-only; the full binary links the
real ones):

| external | home | harness stub |
|---|---|---|
| `blender::G`, `blender::U` | blenkernel globals | real DNA types, zero-init (correct layout for `G.debug` reads) |
| `EIG_invert_m4_m4` | intern/eigen | returns false → blenlib uses its analytic fallback |
| `blender::draw::DebugDraw::{clear_gpu_data,reset}` | draw | empty (get/acquire/release are header-inline, already resolved) |

Minimal archive set (from `build-wasm-gpu`): `libbf_gpu` + `libbf_{gpu,draw,compositor,
imbuf_opencolorio}_shaders` + `libbf_blenlib` + `libbf_dna{,_blenlib}` +
`libbf_intern_{clog,guardedalloc}` + `lib/wasm/lib/{libtbb,libtbbmalloc,libfmt}` + the
shader chain (`lib/wasm/{shaderc,tint}`, single-SPIRV-Tools group). Link flags:
`--use-port=emdawnwebgpu`, `-pthread -fexceptions` (JS-EH), `-sSTACK_SIZE=32MB` (the
shader-path stack finding), `EXIT_RUNTIME=0`, `MODULARIZE`.

## The seam (patch 0035 — proven in-tab)

`wgpu_context.cc` borrowed the device via `static_cast<GHOST_ContextWGPU *>` (the
NATIVE class) + `getAdapterName()`. In the browser the GHOST context is the SIBLING
`GHOST_ContextWGPUWeb` (no `getAdapterName()`). `patches/0037-gpu-webgpu-context-web.patch`
guards this under `__EMSCRIPTEN__` (bind the concrete type via a `WGPUGhostContext`
alias; `adapter_name_ = "emdawnwebgpu"`). Forward-applies cleanly to the tree. The
harness proved it works: `GPU_context_create OK` in a real tab. The webgpu backend
TU needs `-I platform_web/ghost` under emscripten (the harness passes it; the in-tree
arm should add it to the WITH_WEBGPU_BACKEND INC when 0035 lands). The clean long-term
fix is a `GHOST_IContext` virtual (mirroring `getVulkanHandles`) — flagged for lane routing.

## Root cause of the old "abort" — a wasm32 int-width bug, NOT comment stripping (FIXED)

The historical "shader-source comments not stripped" blocker was a **misdiagnosis**.
The wasm build already strips comments build-side: ADR-002 runs the NATIVE host
`shader_tool` (`BLENDER_WEB_HOST_TOOLS_DIR`) via `glsl_to_c`, and all 904 `*.tmp` are
comment-free (verified by decoding every datatoc'd `.c`). The real blocker was a
**wasm32 integer-width bug** in the gpu shader system:

- `StringRefBase::find()` returns `int64_t` with `not_found = -1`, but the "no comments"
  assert compared it against `std::string::npos` (a `size_t`; on wasm32 that is 32-bit
  `0xFFFFFFFF`, which promotes to `int64_t 4294967295 != -1`). On Blender's 64-bit
  native targets `npos` and `-1` coincide bit-for-bit, so it passes there. On wasm32 the
  assert fired on the **first** source regardless of content — hence the non-deterministic
  "culprit" and the `len=0`/garbage-`find` red herrings.
- The printf-format loop had the sibling bug: `int64_t end = format.find_first_of('%',…)`
  then `!= -1`; the 32-bit `npos` never equals `-1`, so it overran → "Printing format
  unsupported".

Fixed at ROOT CAUSE, `__EMSCRIPTEN__`-guarded (native lane byte-untouched; both
reverse-apply clean):
- `patches/0060-gpu-shader-dependency-wasm32-npos.patch` — the GPUSource "no comments"
  assert + the printf-format loop, in `gpu_shader_dependency.cc`.
- `patches/0061-gpu-shader-preprocessor-wasm32-npos.patch` — the identical assert in
  `Shader::run_preprocessor` (`gpu_shader_preprocessor.cc:1654`), hit during the runtime
  GLSL compile.

With both, `gpu_shader_dependency_init()` completes and the builtin shader compiles
in-tab (verified in Node against the real archives, then in a WebGPU tab).

(The old pthread-pool note is moot: `build.sh` already links `-sPTHREAD_POOL_SIZE=32`.)

## Remaining blockers to CORRECT pixels (routed to lane A; harness-worked-around where possible)

- **A. WGPUBackend never calls `platform_init()`** → `GPU_type_matches_ex()` asserts
  `GPG.initialized` (`gpu_platform.cc:179`) during shader compile. The webgpu backend has
  no `platform_init`/`GPG.init` at all (Vulkan does, `vk_backend.cc:461`). Harness
  workaround: `gpu_render_harness.cc` calls `blender::gpu::GPG.init(…WEBGPU…)` before
  `GPU_init()`. Real fix: add it to `WGPUBackend::init_resources`/context init (webgpu/).

- **B. Cross-thread WebGPU device.** emdawnwebgpu keeps WebGPU objects (Device/Queue) in
  the MAIN thread's per-thread JS object table; a `ShaderCompiler` worker cannot see the
  device, so `wgpuDeviceCreateShaderModule()` aborts in `getJsObject()` on the worker.
  Harness workaround: set `GCaps.use_main_context_workaround = true` before `GPU_init()`
  so `ShaderCompiler` creates no worker and compiles on the main thread (device valid
  there). Real fix: a cross-thread device strategy (proxy device calls to main, or a
  per-worker device) — ghost-web / main-loop lane.

- **C. WGPUImmediate not usable.** `immBegin()` asserts `imm->prim_type == GPU_PRIM_NONE`
  (`gpu_immediate.cc:204`) on the first immediate-mode primitive → the triangle draw is
  blocked. → webgpu/`wgpu_immediate.cc` (patch 0035 territory), lane A.

- **D. Synchronous readback returns garbage (the current pixels blocker).**
  `WGPUTexture::read()` (`webgpu/wgpu_texture.cc:1192`) blocks on
  `ctx->instance_get().WaitAny(future, UINT64_MAX)` to await the staging-buffer
  `MapAsync`. emdawnwebgpu does NOT support synchronous `WaitAny` on the browser main
  thread (same delta as async device acquisition, gpu-wasm-compile.md #2), so the map
  never completes and the read copies uninitialised memory — the clear-readback PNG is
  256×256 of random per-pixel garbage (`evidence/intab_clear_readback_garbage.png`), not
  the cleared blue. `WGPUContext::finish()` is also a no-op (`wgpu_context.cc:181`).
  Needs an async-readback strategy: `-sJSPI` so `WaitAny` can suspend/resume on the main
  thread, or run the readback on a worker where `Atomics.wait` can block. → ghost-web /
  main-loop lane (ADR-003).

## Reproduce

```
bash sandbox/gpu-render-harness/build.sh                    # -> build-deps/gpu-harness/gpu_harness.{js,wasm}
cp build-deps/gpu-harness/gpu_harness.{js,wasm} sandbox/gpu-render-harness/web/
python3 sandbox/gpu-render-harness/web/server.py 8130       # COOP/COEP
# open http://127.0.0.1:8130/ in a WebGPU browser
```
Evidence: `sandbox/gpu-render-harness/evidence/browser-run.txt`.
