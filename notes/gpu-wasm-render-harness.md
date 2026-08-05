<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# cycle-6 step 2 — browser GPU render harness (the pixels-in-the-link vehicle)

A dedicated small wasm binary that LINKS the REAL Blender WebGPU backend
(`build-wasm-gpu/lib/libbf_gpu.a`) + its minimal dep closure + the emdawnwebgpu web
context, and drives the gpu-module API to render a triangle offscreen in a browser
tab. Location: `sandbox/gpu-render-harness/` (page + boot in `web/`).

Model: `source/blender/gpu/tests/gpu_testing.cc` (bootstrap, minus gtest) +
`platform_web/ghost/harness-wgpu/` (async boot + readback→PNG page).

## RESULT — links + runs the real backend in a real WebGPU tab

Verified in a real WebGPU browser (Claude Browser pane: `navigator.gpu`=true,
`crossOriginIsolated`=true, COOP/COEP server). The 22 MB `gpu_harness.wasm` boots and
reports, in order:

```
[gpu-harness] backend = WEBGPU; creating GHOST_ContextWGPUWeb on '#gpucanvas'
CONTEXT OK: emdawnwebgpu device acquired
GPU_context_create OK (WGPUContext borrowed the device)   <- the seam (patch 0035) works
```

then enters `GPU_init` and drives **deep into the gpu-module shader-dependency
system**, aborting at a specific, characterized assert (below). So: the real WebGPU
backend selects, acquires the browser device through OUR `GHOST_ContextWGPUWeb`,
borrows it into `WGPUContext`, and runs `GPU_init` — **in a browser tab**. Browser
parity of the backend link + context + init path is proven; the two remaining
blockers to pixels are specific and routed.

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
`GHOST_ContextWGPUWeb` (no `getAdapterName()`). `patches/0035-gpu-webgpu-context-web.patch`
guards this under `__EMSCRIPTEN__` (bind the concrete type via a `WGPUGhostContext`
alias; `adapter_name_ = "emdawnwebgpu"`). Forward-applies cleanly to the tree. The
harness proved it works: `GPU_context_create OK` in a real tab. The webgpu backend
TU needs `-I platform_web/ghost` under emscripten (the harness passes it; the in-tree
arm should add it to the WITH_WEBGPU_BACKEND INC when 0035 lands). The clean long-term
fix is a `GHOST_IContext` virtual (mirroring `getVulkanHandles`) — flagged for lane routing.

## Two blockers to pixels (both routed, neither architectural)

1. **Shader-source comments not stripped (the abort).**
   `GPUSource()` (`gpu_shader_dependency.cc:196`) asserts the datatoc'd shader source
   is already comment-free ("Input source should have no comments."). The
   `build-wasm-gpu` shader datatoc does NOT pre-strip comments, so `GPU_init`'s shader
   graph construction aborts. Native passes because its shader-source build strips
   comments. → gpu/build lane: the wasm shader-source codegen must strip comments
   (or the assert path must call `.remove_comments()` — one exists at :536).

2. **pthread pool exhausted during GPU_init threading.**
   TBB / `GPU_init` spawn threads; the harness linked without a pool
   (non-`PROXY_TO_PTHREAD`, so main can't block-spawn). Warnings, not the abort cause.
   → the real binary already uses `-sPROXY_TO_PTHREAD` + a pool (platform_wasm profile);
   a browser harness that keeps DOM reporting needs main-thread EM_JS proxying, so the
   harness reports via the main thread and leaves proxy off — good enough to reach the
   shader path. Add `-sPTHREAD_POOL_SIZE` for a cleaner run.

## Reproduce

```
bash sandbox/gpu-render-harness/build.sh                    # -> build-deps/gpu-harness/gpu_harness.{js,wasm}
cp build-deps/gpu-harness/gpu_harness.{js,wasm} sandbox/gpu-render-harness/web/
python3 sandbox/gpu-render-harness/web/server.py 8130       # COOP/COEP
# open http://127.0.0.1:8130/ in a WebGPU browser
```
Evidence: `sandbox/gpu-render-harness/evidence/browser-run.txt`.
