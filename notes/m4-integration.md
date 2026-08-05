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

## Tasks 6–9 (windowed link) — status (2026-08-05)

Unblocked once the M3 WebGPU backend compiled for wasm (`build-wasm-gpu`,
`notes/gpu-wasm-compile.md`) and the shader chain landed (`lib/wasm/{tint,shaderc}`,
`notes/deps-shader-chain.md`).

**T6 — startup device-await (DONE, compiles active).** `GHOST_ContextWGPUWeb::
initializeDrawingContext()` now acquires the device SYNCHRONOUSLY via `instance.WaitAny(
RequestAdapter/RequestDevice, UINT64_MAX)` — under `-sJSPI` (windowed link) `WaitAny`
SUSPENDS to the event loop instead of blocking, the one-time top-level startup await
ADR-003 permits (mirrors native `GHOST_ContextWGPU`). Canvas size read from the DOM. The
async callback path (`initAsync`) is kept for the standalone harness. Payload: **no gap**
— recon §2's inventory is already covered by the `/bw/datafiles` (fonts/colormgmt) +
`/bw/scripts` mounts; icons are datatoc'd into the wasm (the only "missing" piece was
`icons_init` being compiled out — fixed by T1/0024).

**T7 — windowed link flags (DONE).** The gpu-lane WebGPU arm already adds
`--use-port=emdawnwebgpu` + `TINT_INCLUDE_DIRS`/`SHADERC_INCLUDE_DIR`/`WGPU_TINT_LIBS`
when `WITH_WEBGPU_BACKEND=ON`. My browser target OVERWRITES `LINK_FLAGS`, so
`blender_web_browser_binary()` now re-adds, under `WITH_WEBGPU_BACKEND`:
`--use-port=emdawnwebgpu -sJSPI -sSTACK_SIZE=33554432 -sDEFAULT_PTHREAD_STACK_SIZE=33554432`
(32 MB stack = deps-shader-chain.md finding 3; JSPI = the T6 await). `WGPU_TINT_LIBS`
(shaderc+Tint) link via `bf_gpu`'s cloned `LINK_LIBRARIES`.

The exact block (live on disk in `platform_wasm.cmake`'s `blender_web_browser_binary()`,
just before `set_target_properties(... LINK_FLAGS ...)`) — NOT in the M4 commit to avoid
conflating with the gpu-lane's WebGPU arm; the driver applies it onto that arm:
```cmake
  if(WITH_WEBGPU_BACKEND)
    string(APPEND _bw_browser_flags
      " --use-port=emdawnwebgpu -sJSPI"
      " -sSTACK_SIZE=33554432 -sDEFAULT_PTHREAD_STACK_SIZE=33554432")
  endif()
```

**T8 — windowed configure (GREEN).** Separate tree, shared `build-wasm` untouched:
```
BLENDER_WEB_WINDOWED=1 cmake -S upstream -B build-wasm-windowed -G Ninja \
  -C patches/blender_web.cmake -DCMAKE_TOOLCHAIN_FILE=<emscripten> \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo -DWITH_BLENDER_WEB_BROWSER=ON
```
NOTE: `-C` initial-cache runs BEFORE `-D`, so the windowed switch is the ENV knob
`BLENDER_WEB_WINDOWED=1` (not `-DWITH_BLENDER_WEB_WINDOWED`). Cache verified:
`WITH_HEADLESS=OFF`, `WITH_WEBGPU_BACKEND=ON`, `WITH_GHOST_WEB=ON`. **The full GHOST
windowed integration compiles active** in this config: `lib/libbf_intern_ghost.a` builds
with all four `platform_web/ghost/*.o` (SystemWeb/WindowWeb/EventBridgeWeb/ContextWGPUWeb)
— i.e. the T2 factory branch, the T4 `__EMSCRIPTEN__` selection seam → `GHOST_ContextWGPUWeb`,
and the T6 `WaitAny` await all compile with `WITH_GHOST_WEB`+`WITH_WEBGPU_BACKEND` live
(needed the ghost `CMakeLists.txt` `INC` fix: add `intern` so the out-of-tree sources see
the GHOST base headers — patch 0027).

**T9 — full windowed LINK + boot characterization (DONE 2026-08-05).** The cold windowed
`blender_browser` linked clean (`bin/blender_browser.{wasm 921 MB,js,data 117 MB}`) — NO
symbol gaps; the browser link profile (`blender_web_browser_binary()`) already carried the
whole editors/interface/draw + webgpu backend + Tint/shaderc closure. Booted in a real
Chrome tab via the M4 windowed shell (`platform_web/shell/windowed.html` + `boot-windowed.js`,
served by `BLENDER_WEB_BIN=build-wasm-windowed/bin scripts/serve-web.sh 8123`; argv
`--factory-startup`, NO `--background`, canvas `#canvas`). Three blockers surfaced in
dependency order; the first two were windowed-integration bugs I fixed, the third is a
gpu-backend/emdawnwebgpu bug (characterized, handed to lane A):

1. **`-sJSPI` ctor-suspend crash (FIXED — link flag).** Boot aborted during `initRuntime`
   BEFORE `main()`: `SuspendError: trying to suspend without WebAssembly.promising`, stack
   `__wasm_call_ctors → _GLOBAL__I → std::ios_base::Init::Init()`. Emscripten wraps only
   `main`/`__main_argc_argv` (and the proxied pthread entry `invokeEntryPoint`) with
   `WebAssembly.promising`; `initRuntime()` calls `__wasm_call_ctors()` RAW on the MAIN
   thread, so any `-sJSPI` suspend reached from a C++ static ctor has no Suspender → abort.
   Fix: DROP `-sJSPI` from the browser arm — main()/the WaitAny device await run on the
   PROXY_TO_PTHREAD WM worker, which BLOCKS via `Atomics.wait` (JSPI unneeded and harmful).
   `patches/platform_wasm.cmake` browser arm; `notes/porting-patterns.md` Class 4.

2. **Missing `-DWITH_WEBGPU_BACKEND` in windowmanager (FIXED — patch 0065).** Next abort:
   `BLI_assert_unreachable()` at `wm_window.cc:2399`, INSIDE `case GPU_BACKEND_WEBGPU:`
   after the `#endif` — i.e. backend selection correctly returned `GPU_BACKEND_WEBGPU` but
   the `#ifdef WITH_WEBGPU_BACKEND` guard (patch 0023) was compiled OUT. Blender adds the
   backend define PER consuming module (`add_definitions` in gpu/, intern/ghost/, +
   VULKAN's in creator/draw/windowmanager/…); patch 0023 added the wm_window.cc case but
   not the matching define in `windowmanager/CMakeLists.txt`. `patches/0065-wm-webgpu-
   backend-define.patch` mirrors the OPENGL/VULKAN blocks (gated `if(WITH_WEBGPU_BACKEND)`).

3. **emdawnwebgpu RefCounted unaligned 64-bit atomic (LANE A / gpu-backend — characterized,
   NOT mine).** With (1)+(2) fixed the boot reaches `GPU_context_create` (wm_window.cc:1045,
   real window creation) → `WGPUBackend::context_alloc` → `WGPUContext::WGPUContext` ctor →
   `wgpuInstanceAddRef` → `(anonymous namespace)::RefCounted::AddRef()` →
   `std::atomic<uint64_t>::fetch_add` → `RuntimeError: operation does not support unaligned
   accesses`. wasm32 i64 atomic RMW needs 8-byte alignment; the Dawn/emdawnwebgpu RefCounted
   refcount lands misaligned. This is BEFORE the device await, so every windowed-integration
   seam (GHOST factory, drawing-context map, context selection, GPU_context_create call) is
   validated. Fix belongs to the WebGPU backend/emdawnwebgpu port (gpu/webgpu, lane A):
   ensure `RefCounted`'s `std::atomic<uint64_t>` is 8-byte-aligned on wasm32 — likely an
   allocation/struct-packing alignment fix in the emdawnwebgpu port or a wasm32 build flag.
   (Note: patch 0075's per-thread/main-context workaround was already in this binary — it
   does not address this alignment trap.) Also benign: `unsupported syscall
   __syscall_prlimit64` (Emscripten libc gap, non-fatal), and the OIIO `physical_memory`
   stub (same as headless). Diagnostic capture used a throwaway `-sASSERTIONS=2` relink,
   reverted; the committed browser arm is the clean profile.

**Next windowed task:** first-window pixels, gated on lane A fixing blocker #3 (the
emdawnwebgpu RefCounted wasm32 atomic alignment). Once `WGPUContext` constructs, the path
continues into `initializeDrawingContext()`'s worker-blocking `WaitAny` device await —
whose empirical validation (coordinator's "does Atomics.wait block work on the WM worker")
is the FOLLOWING unknown, not yet reached.
