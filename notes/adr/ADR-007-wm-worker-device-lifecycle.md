<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# ADR-007 — WebGPU device lifecycle lives on the WM worker; futures resolve across main-loop ticks

**Status:** ACCEPTED 2026-08-06 (driver), authored from the M4.T11 empirical probe
(commit d4708b9; findings recorded in notes/m4-integration.md before implementation).
Companion to ADR-006 (no JSPI/asyncify — stands unchanged).

## Context (measured, not assumed)

Probing the pinned emdawnwebgpu port in real Chrome established three facts:

1. **No cross-thread WebGPU objects.** The port's JS-object table is per-thread
   (library_webgpu.js:119). A `GPUDevice` is neither structured-cloneable nor
   transferable (empirical `DataCloneError` both directions). Main-thread acquisition
   + hand-off to the WM worker is impossible for this port.
2. **Callbacks resolve only on the acquiring thread's event loop**, and the port's
   blocking waits (`futures`/`emwgpuWaitAny`) are `#if ASYNCIFY`-only. A thread blocked
   in `Atomics.wait` halts its own event loop, so same-thread synchronous waits on
   WebGPU promises are structurally impossible under ADR-006.
3. **Dedicated Workers have `navigator.gpu`** (Chrome). An Emscripten pthread — in
   particular the PROXY_TO_PTHREAD "proxied main" WM worker — can acquire the adapter
   and device itself.

## Decision

- The WebGPU instance/adapter/device are acquired **on the WM worker, pre-main**:
  a `--post-js` shim (platform_web/shell/wgpu-preinit-worker.js) intercepts the
  worker's startup message, awaits `requestAdapter/requestDevice` while the worker's
  event loop is still free, stashes `Module.preinitializedWebGPUDevice`, then releases
  `main()`. `GHOST_ContextWGPUWeb::initializeDrawingContext` imports it via
  `emscripten_webgpu_get_device()` + `CreateInstance(nullptr)` — no TimedWaitAny
  feature, no blocking acquisition.
- **All GPU futures resolve on the WM worker's event loop between
  `emscripten_set_main_loop` ticks.** Blocking-style GPU APIs (texture-readback
  MapAsync, shader-compile waits) become kick-then-consume: submit, return to the
  loop, consume on a later tick (`AllowProcessEvents` + `instance.ProcessEvents()`
  pumping, or `AllowSpontaneous`). Any Blender path expecting synchronous
  `GPU_texture_read` semantics is deferred/poll on wasm — this is the F9-D
  disposition.

## Consequences

- No cross-thread GPU object sharing anywhere in the port: async shader-compile
  worker threads cannot touch the device — the main-context workaround (patch 0075)
  is the standing posture, meaning compiles execute on the WM thread.
- The offscreen render harness's browser-main-thread profile remains a separate,
  workaround-carrying profile (documented in notes/gpu-wasm-render-harness.md);
  the windowed WM-worker profile is the shipping architecture.
- Tier-(c) tests that read pixels back must pump ticks; the harness/runner design for
  M5/M6 inherits this.
- DOM access from the WM worker is mediated (canvas via OffscreenCanvas transfer —
  M4.T12; `window`/`document` EM_JS guarded).

## Rejected

- Main-thread acquisition + import into the worker: no port mechanism, empirically
  DataCloneError (finding 1).
- JSPI/asyncify blocking waits: ADR-006, ctor-suspend abort + size tax.
- Vendoring the port to add cross-thread proxying: large maintenance surface against
  an actively-pinned upstream port; unnecessary given finding 3.
