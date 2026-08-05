<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M4 integration — tasks 1–5 (windowed boot seams)

Wires the proven GHOST-web event layer + in-tab WebGPU context into the real build so
the windowed path (`else` branch of `creator.cc:643`, `WM_init_splash_on_startup` +
`WM_main`) can run. Map: `notes/m4-windowed-boot-recon.md`. Backend-independent seams;
the full windowed **link** is gated on the M3 WebGPU backend (see "Gate" below).

## Status (2026-08-04)

All five seams applied to the shared tree and **compile-verified in the current
(headless, dormant) config** — each is a no-op until the windowed profile turns it on,
so the proven `--background` BPY_OK boot is untouched.

| # | task | change | patch / file | compile-checked |
|---|---|---|---|---|
| 1 | build-config flip + compile `platform_web/ghost` into GHOST lib | windowed profile in blender_web.cmake (opt-in) + ghost `CMakeLists.txt` `WITH_GHOST_WEB` block; icons_init un-gate | `blender_web.cmake` (owned), `patches/0027-ghost-cmake-web.patch`, `patches/0024-icons-init-web.patch` | ✅ `bf_intern_ghost`, `bf_editor_interface` |
| 2 | GHOST factory `WITH_GHOST_WEB` branch → `GHOST_SystemWeb` | `GHOST_ISystem::createSystem()` | `patches/0025-ghost-factory-web.patch` | ✅ `bf_intern_ghost` |
| 3 | wm drawing-context map: `GPU_BACKEND_WEBGPU → GHOST_kDrawingContextTypeWebGPU` | `wm_ghost_drawing_context_type` | `patches/0023-wm-webgpu-drawing-context.patch` | ✅ `bf_windowmanager` |
| 4 | context reconciliation: `GHOST_ContextWGPUWeb : GHOST_Context` + `__EMSCRIPTEN__` selection seam | `GHOST_ContextWGPUWeb.{hh,cc}`, `GHOST_WindowWeb.cc`, `GHOST_SystemWeb.cc` (owned) | — (owned files) | ✅ builds + **renders** (harness-wgpu, real Chrome, READBACK PASS) |
| 5 | main-loop hook: `WM_main` `while(true)` → `emscripten_set_main_loop` | `WM_main` web arm (`__EMSCRIPTEN__`) | `patches/0026-wm-main-loop-web.patch` | ✅ `bf_windowmanager` |

## Design decisions

**T2 factory (0025).** `createSystem()` gains `#elif defined(WITH_GHOST_WEB)` →
`system_ = new GHOST_SystemWeb();`, placed after the `WITH_HEADLESS` pass-arm so it wins
when HEADLESS is OFF (windowed). The `#include "GHOST_SystemWeb.hh"` is `#ifdef
WITH_GHOST_WEB`-guarded (platform_web/ghost is on the GHOST include path only in the
windowed config). `createSystemBackground()` unchanged — its existing fallback handles
background.

**T4 context reconciliation (§4 of the recon).** Two Dawn variants stay two classes
behind one `#ifdef __EMSCRIPTEN__` seam (native `GHOST_ContextWGPU` for M3 offscreen
conformance; browser `GHOST_ContextWGPUWeb` for the tab) — folding them into one TU
would entangle native `webgpu_cpp.h` with emdawnwebgpu's (different surface struct +
wait model). `GHOST_ContextWGPUWeb` now derives `GHOST_Context` and implements its six
pure virtuals (`initializeDrawingContext`, `releaseNativeHandles`, `swapBufferAcquire`,
`swapBufferRelease`, `activateDrawingContext`, `releaseDrawingContext`).
`GHOST_WindowWeb::newDrawingContext` / `GHOST_SystemWeb::createOffscreenContext` return
it under `__EMSCRIPTEN__`, the native class otherwise.

*Async→sync bridge (the load-bearing bit).* `newDrawingContext` must return a ready
context synchronously, but browser device acquisition is async (`AllowSpontaneous`,
never a blocking `WaitAny` — that deadlocks the browser main thread). Resolution: the
GHOST-web **system** runs `initAsync()` ONCE at startup and gates the WM main-loop start
on the ready-callback (a single top-level await — ADR-003-legal). By the time
`createWindow → newDrawingContext → initializeDrawingContext()` runs, the device is
acquired, so the sync `initializeDrawingContext()` just returns `ready_`.
**Remaining wiring for the windowed run:** the system-level startup await (acquire the
device before `WM_init`'s window creation). Currently `initializeDrawingContext()`
returns failure until a device is acquired — the harness proves the render path; the
startup-await hook is the one runtime piece left for the windowed integration (task 6).

**T5 main-loop (0026).** A blocking `while(true)` is fatal in the browser (starves the
event loop delivering proxied HTML5 input; blocks every JSPI yield). The `__EMSCRIPTEN__`
arm drives ONE `WM_main` body per `emscripten_set_main_loop(tick, 0, /*infinite*/1)`
tick on the WM worker — the single top-level pump/suspend point (ADR-003). Capless
lambda + a function-static `bContext*`. `WM_main` isn't called in `--background`, so this
is compile-active but runtime-dormant for the headless boot.

**T1 config.** `WITH_BLENDER_WEB_WINDOWED` (default OFF) flips `WITH_HEADLESS` OFF +
`WITH_WEBGPU_BACKEND` ON + `WITH_GHOST_WEB` ON. The ghost `CMakeLists.txt` `WITH_GHOST_WEB`
block adds the five `platform_web/ghost` sources + include + `-DWITH_GHOST_WEB`. icons_init
un-gated to `#if !defined(WITH_HEADLESS) || defined(WITH_GHOST_WEB)`.

## Gate — the full windowed compile-LINK (honest status)

The five seams compile; the **windowed link is not yet reachable in this session** and
is gated on the M3 WebGPU backend, which the recon itself names ("Dispatch gate: M3's
WebGPU gpu suite green"):

- `WITH_BLENDER_WEB_WINDOWED=ON` sets `WITH_WEBGPU_BACKEND=ON`, which compiles
  `source/blender/gpu/webgpu/` (M3, 22 files, under construction) + needs
  `--use-port=emdawnwebgpu` on the windowed target's compile/link flags (not yet wired
  into platform_wasm.cmake's browser target — recon task 7).
- `WITH_HEADLESS=OFF` requires a GPU backend; the only wasm one is WebGPU, so the link
  cannot be produced without the M3 backend compiling for wasm.

So the "reaches the GPU-init abort" gate needs a dedicated windowed build
(`-C patches/blender_web.cmake -DWITH_BLENDER_WEB_WINDOWED=ON` in a SEPARATE build dir,
so the shared headless `build-wasm` is untouched) once the M3 backend compiles under
emscripten. Recommended sequencing: land M3 wasm-compile → wire `--use-port=emdawnwebgpu`
into the browser target (task 7) → configure the windowed build dir → link → expect the
first-draw abort (backend incomplete) = this lane's gate.

## Remaining (tasks 6–9, recon §5)

6. system-level startup device-await + canvas/swapchain sizing (devicePixelRatio).
7. boot args (drop `--background`, add windowed args + canvas selector) + wire
   `--use-port=emdawnwebgpu` into the browser link target.
8. first-draw bring-up (startup.blend → Layout + cube/camera/light; icons upload; theme;
   splash).
9. M4 gate: idiff first frame vs native golden; register deferrals.
