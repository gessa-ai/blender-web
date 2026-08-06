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

## M4.T10 — the "unaligned atomic" crash was NOT an emdawnwebgpu port bug (2026-08-05)

The T9 blocker #3 was dispatched as "emdawnwebgpu RefCounted wasm32 atomic alignment —
fix the port." That diagnosis was WRONG. The crash
(`wgpuInstanceAddRef → RefCounted::AddRef → std::atomic<uint64_t>::fetch_add → operation
does not support unaligned accesses`) is real, but its cause is a **garbage/misaligned
instance pointer**, not a misaligned atomic member. Empirically established (real Chrome,
in-tab boot; trace `getInstance() instance_=0x11 (%8=1)`), not theory. The emdawnwebgpu
port is used AS-IS (`--use-port=emdawnwebgpu`, Dawn v20260423.175430) — nothing vendored,
`ledger/deps.json` unchanged; a standalone repro proved `wgpuCreateInstance`'s
`WGPUInstanceImpl` is always 8-byte aligned under dlmalloc across every profile
(main-thread / PROXY_TO_PTHREAD / asyncify / TimedWaitAny).

**Why the in-tab render harness never hit it (the puzzle):** the harness links its OWN
`sandbox/gpu-render-harness/wgpu_context_web.cc`, whose `#ifdef __EMSCRIPTEN__` seam casts
the GHOST context to `GHOST_ContextWGPUWeb*` (the correct type) and drives device
acquisition through `initAsync` (`CreateInstance(nullptr)`, no TimedWaitAny). Nothing to do
with allocator or thread — it is the corrected cast + the no-TimedWaitAny path.

**Two real bugs fixed (both prerequisites, neither sufficient alone):**

1. **Wrong GHOST-context cast — `patches/0066-gpu-webgpu-windowed-ghost-context-cast.patch`
   (upstream `source/blender/gpu/webgpu/wgpu_context.cc`).** The `WGPUContext` ctor cast
   `ghost_context` to the NATIVE `GHOST_ContextWGPU*` and called `getInstance()`. In the
   browser the object is `GHOST_ContextWGPUWeb`, whose layout differs (it stores
   `std::string canvas_selector_` + `width_`/`height_` BEFORE the handles), so `getInstance()`
   read the std::string's SSO bytes as the instance pointer → misaligned garbage. Fix = the
   same `#ifdef` seam the harness already had, gated `#if defined(__EMSCRIPTEN__) &&
   !defined(WITH_HEADLESS)`. NB: the guard is `!WITH_HEADLESS`, NOT `WITH_GHOST_WEB` —
   `add_definitions(-DWITH_GHOST_WEB)` is scoped to `intern/ghost/` only and never reaches
   `bf_gpu`'s compile (a first attempt with that guard silently compiled the native branch).
   `WITH_HEADLESS` is ON for `build-wasm-gpu` (M3, native branch, byte-identical) and OFF for
   `build-wasm-windowed` (web branch; `platform_web/ghost` is already on bf_gpu's include
   path there) — so the change is provably a no-op for the gpu-lane build.

2. **Window never initialized its drawing context — `platform_web/ghost/GHOST_WindowWeb.cc`.**
   The `GHOST_WindowWeb` ctor DROPPED its `GHOST_TDrawingContextType type` param
   (`/*type*/`) and never called `setDrawingContextType(type)`; `GHOST_SystemWeb::createWindow`
   didn't either. So the base `GHOST_Window` kept its default `GHOST_ContextNone` (base ctor
   `context_ = new GHOST_ContextNone`), and `GPU_context_create(win, nullptr) →
   WGPUBackend::context_alloc → getDrawingContext()` handed the `WGPUContext` ctor that
   `GHOST_ContextNone` — even the corrected cast then reads garbage from it (`instance_=0x11`).
   Fix = call `setDrawingContextType(type)` in the web window ctor, mirroring
   `GHOST_WindowSDL/Win32/X11/Wayland`. Confirmed live: `initializeDrawingContext()` now RUNS.

**The remaining blocker — the DEVICE AWAIT (now made concrete, file:line):**
With both fixes, boot advances INTO `GHOST_ContextWGPUWeb::initializeDrawingContext()`
(trace `initializeDrawingContext ENTER`), which requests `wgpu::InstanceFeatureName::
TimedWaitAny` (needed for its blocking `instance.WaitAny(…, UINT64_MAX)` device await,
`platform_web/ghost/GHOST_ContextWGPUWeb.cc:45-49`). Under the ADR-006 profile (NO `-sJSPI`,
NO `-sASYNCIFY`) `emscripten_has_asyncify()==0`, so emdawnwebgpu's `WGPUInstanceImpl::Create`
rejects TimedWaitAny and returns null (port `webgpu/src/webgpu.cpp:1643-1649`). Trace:
`CreateInstance(&idesc TimedWaitAny) -> 0` → `WGPUWeb: CreateInstance failed` →
`newDrawingContext` returns null → `setDrawingContextType` falls back to
`GHOST_ContextNone` → the same downstream `AddRef` trap. The port additionally can't do a
non-blocking `WaitAny(…, 0)` either (`abort("TODO: Implement asyncify-free WaitAny for
timeout=0")`), and on the WM worker the async callback path can't complete because
`initializeDrawingContext` runs straight-line during `WM_init`, before `WM_main`'s
`emscripten_set_main_loop` pump exists — so NO emdawnwebgpu wait works synchronously on the
worker without asyncify. This is an ARCHITECTURE decision (interacts with ADR-006), not a
worker quick-fix. Option space for the driver: (a) main-thread device acquisition in the
shell + `emscripten_webgpu_import_device` into the wasm (event loop pumps naturally on the
browser main thread); (b) restructure the windowed boot so window/GPU-context creation is
deferred until an async device-ready callback fires (event-loop-driven boot); (c) a new ADR
re-introducing a scoped async mechanism with a ctor-suspend-free proof (reverses ADR-006).
`GHOST_ContextWGPUWeb::initAsync` (the harness's AllowSpontaneous path) already exists as the
building block for (a)/(b).

## M4.T11 — emdawnwebgpu port probe (feeds ADR-007) — 2026-08-06

Probed the PINNED port's actual mechanics (sources:
`tools/emsdk/upstream/emscripten/cache/ports/emdawnwebgpu/emdawnwebgpu_pkg/webgpu/src/`
`webgpu.cpp` + `library_webgpu.js`; Emscripten runtime in the built `blender_browser.js`)
plus two EMPIRICAL browser tests in a real Chrome tab (crossOriginIsolated, WebGPU floor
met). Findings are load-bearing; the driver turns them into ADR-007.

### (i) Cross-thread device import — NO (device is bound to its acquiring thread)

- emdawnwebgpu keeps ALL WebGPU JS objects in a **per-thread, module-level table**
  `WebGPU.Internals.jsObjects = []` (`library_webgpu.js:119`). Under `-pthread` every
  pthread is a separate Web Worker with its own JS realm and its own copy of this table.
  A WGPU handle (`WGPUDevice` etc.) is just a pointer key INTO the owning thread's table;
  the same pointer is meaningless on another thread. There is **no proxying** of WebGPU
  calls to a single owner thread (grep: zero `proxy`/`MAIN_THREAD` in the port JS) — each
  thread talks to its own `navigator.gpu`.
- The port DOES expose import entry points: `emscripten_webgpu_import_device`,
  `…_import_adapter`, … (`webgpu.h:2345` decl `emscripten_webgpu_get_device(void)`;
  JS `importJsDevice` at `library_webgpu.js:180`, `emscripten_webgpu_get_device` reads
  `Module['preinitializedWebGPUDevice']` at `:657`). BUT import takes a **JS GPUDevice
  object that must already live in the CURRENT thread's realm** and inserts it into THAT
  thread's table. It does not move an object across realms.
- **EMPIRICAL (Chrome, this env):** a `GPUDevice` acquired on the browser main thread
  **cannot be `postMessage`'d to a Worker** — `DataCloneError: GPUDevice object could not
  be cloned` (structured clone) and `…does not have a transferable type` (transfer list).
  So the classic "acquire on the main thread, `Module.preinitializedWebGPUDevice`, import
  on the worker" pattern is **impossible for this port under PROXY_TO_PTHREAD** — the
  device must be acquired ON the thread that will use it.

### (ii) Where callbacks fire — the OWNING thread's event loop only

- `RequestAdapter`/`RequestDevice`/`MapAsync` return JS promises created against the
  calling thread's `navigator.gpu`. Their C-side completion runs when the JS promise
  resolves on **that same thread's event loop**, via `emwgpuOnRequestDeviceCompleted` →
  `EventManager::SetFutureReady` (`webgpu.cpp:675`). With `WGPUCallbackMode_AllowSpontaneous`
  the C++ `Complete()` fires IMMEDIATELY inside `SetFutureReady` (`:693-701`) — no
  ProcessEvents needed; with `AllowProcessEvents` it fires on the next
  `instance.ProcessEvents()` call on the owning thread (`:510-547`); with `WaitAnyOnly`
  only via `WaitAny`.
- The `futures` table and the async `emwgpuWaitAny` JS impl are **`#if ASYNCIFY`-only**
  (`library_webgpu.js:137-141, 690-719`). Under ADR-006 (no `-sJSPI`, no `-sASYNCIFY`)
  `emscripten_has_asyncify()==0`, so: (a) a `TimedWaitAny`-featured `CreateInstance` is
  REJECTED and returns null (`webgpu.cpp:1643-1649`) — this is exactly what
  `initializeDrawingContext` hit; (b) `WaitAny(timeout>0)` asserts asyncify (`:562`); the
  JS fallback `emwgpuWaitAny` is `abort('TODO: asyncify-free WaitAny for timeout=0')`
  (`:716-718`); (c) `WaitAny(timeout=0)` merely POLLS `mIsReady` (`:612-645`) — which
  never becomes true because the promise cannot resolve while the thread is not turning
  its event loop.
- **Consequence (the deadlock, now proven from the port):** a same-thread blocking wait
  on a WebGPU future is structurally impossible without asyncify. `Atomics.wait` halts the
  worker's microtask/event loop, so the worker cannot resolve its OWN promise. The device
  future can only complete when the acquiring worker's event loop turns with no C++ frame
  on the stack — i.e. **pre-main, or after `main()` yields to `emscripten_set_main_loop`.**

### (iii) WebGPU inside the WM (proxied-main) worker — YES (this is the opening)

- **EMPIRICAL (Chrome, this env):** a plain dedicated `Worker` (which is exactly what an
  Emscripten pthread is) has `navigator.gpu`, and `requestAdapter()` → `requestDevice()`
  succeed inside it; `navigator.gpu.getPreferredCanvasFormat()` = `bgra8unorm`. Page is
  `crossOriginIsolated:true`. So the WM worker CAN own a device.
- Therefore the viable path is **option-(a)/(iii): acquire the device ON the WM worker
  itself, asynchronously, in the one window where that worker's event loop is free — BEFORE
  `main()` runs straight-line.** Under `-sPROXY_TO_PTHREAD` the proxied main pthread runs
  `_main_thread` (`crt1_proxy_main.c:27,52`, `arg==NULL`) via the worker's cmd==2 handler →
  `invokeEntryPoint` (`blender_browser.js:22515`). Gating that cmd==2 on a completed
  `await navigator.gpu.request{Adapter,Device}()` and stashing the result in the worker's
  `Module['preinitializedWebGPUDevice']` makes the device already-present when
  `initializeDrawingContext` calls `emscripten_webgpu_get_device()` SYNCHRONOUSLY. No
  spin/race is possible because the await COMPLETES before `invokeEntryPoint` — a C++ spin
  could never help (it can't turn the worker's JS event loop).

### Surface / canvas — a SEPARATE downstream blocker (the WM worker has no DOM)

- The device is enough for `GPU_context_create`/`GPU_init`: `WGPUContext`'s ctor uses only
  instance/device/queue + `device_.GetLimits` (`wgpu_context.cc:43-79,107-170`); it never
  reads the surface. The surface is used only by the swap path (main loop).
- But `wgpuInstanceCreateSurface` resolves the canvas via `findCanvasEventTarget(selector)`
  → `findEventTarget` = `specialHTMLTargets[t] || document?.querySelector(t)`
  (`blender_browser.js:24351`). On a worker `document` is undefined and the current browser
  link has **no `-sOFFSCREENCANVAS_SUPPORT`**, so `#canvas` cannot be resolved from the WM
  worker → CreateSurface would fail there. Fix (later step): `-sOFFSCREENCANVAS_SUPPORT` +
  `-sOFFSCREENCANVASES_TO_PTHREAD="#canvas"` — Emscripten's proxied-main already requests
  the transfer (`crt1_proxy_main.c:48 settransferredcanvases(-1)`), which registers the
  OffscreenCanvas in `specialHTMLTargets` on the WM worker so the selector resolves. This
  round keeps surface creation NON-FATAL so the boot advances past context creation and the
  surface path can be characterized independently.

### (4) Render-loop-time blocking (readback MapAsync, shader-compile waits) — the port's answer

- Same knot, same resolution: those are futures on the WM worker. Because the WM worker
  runs `main()`/`WM_main` via `emscripten_set_main_loop` (patch 0026), the worker's event
  loop DOES turn between ticks. So the port's mechanism is **`AllowProcessEvents` +
  `instance.ProcessEvents()` pumped from the main loop, or `AllowSpontaneous` +
  yield-to-loop**: kick the async op, RETURN to the loop, and consume the result on a later
  tick when the callback has fired (`SetFutureReady`→`Complete`). A synchronous
  `WaitAny`-blocks-the-worker readback is NOT available without asyncify (proven above:
  `emwgpuWaitAny` aborts). Main-thread proxying is NOT offered by this port. So any Blender
  code that expects a synchronous GPU readback (`GPU_texture_read` immediate return) must be
  adapted on wasm to a poll-across-ticks (or deferred-result) shape — an F9-D / render-loop
  concern, characterized here for the driver, not implemented this round.

## M4.T11 RESULT — windowed boot advances to the WM_main loop + BPY startup (2026-08-06)

Implemented the option-(a)/(iii) path and the windowed boot now advances FAR past the
prior gate (device await), through GPU_init, into Python/BPY startup and the WM_main loop.
Verified in a real Chrome tab (`:8123/windowed.html`, `--factory-startup`, no
`--background`).

**Implemented (all owned files; upstream/gpu/webgpu UNTOUCHED):**
1. `platform_web/shell/wgpu-preinit-worker.js` (NEW, linked via `--post-js` in the browser
   arm of `patches/platform_wasm.cmake`). Runs in every pthread worker; for the proxied
   application-main thread (cmd:2 with `arg==0`) it OWNS `self.onmessage` via an accessor
   takeover (the handler is an own property on `self`, not the prototype — the `[Global]`
   special case; and Emscripten's cmd:1 `startWorker` re-assigns `self.onmessage`, so a
   plain wrapper is clobbered and an `addEventListener` fires too late). It `await`s
   `navigator.gpu.request{Adapter,Device}()` on the WM worker, stashes the device in that
   worker's `Module.preinitializedWebGPUDevice`, and only then dispatches the entry so
   `main()` runs with the device already present. No race/spin — the await completes before
   `invokeEntryPoint`.
2. `platform_web/ghost/GHOST_ContextWGPUWeb.cc::initializeDrawingContext()` — replaced the
   TimedWaitAny+WaitAny acquisition (returns null under ADR-006) with: check
   `Module.preinitializedWebGPUDevice`, `CreateInstance(nullptr)` (featureless = valid
   without asyncify), `emscripten_webgpu_get_device()` → `wgpu::Device::Acquire`, `GetQueue`.
   Surface creation is made NON-FATAL and guarded by `ghost_web_canvas_resolvable()` (the WM
   worker has no DOM canvas yet, and emdawnwebgpu's `CreateSurface` would ABORT on an
   unresolvable selector) — device stays live, `ready_=true`, boot continues.
3. `platform_web/ghost/GHOST_WindowWeb.cc` — guarded the `ghost_web_device_pixel_ratio`
   (`window.devicePixelRatio`) and `ghost_web_set_document_title` (`document.title`) EM_JS
   for the worker (no `window`/`document` there → bare refs throw ReferenceError). DPR
   defaults to 1.0; title update no-ops on the worker.

**How far it gets (empirical, in-tab):**
- `[bw] WM-worker WebGPU device pre-acquired (ADR-007)` → `initializeDrawingContext` imports
  it → **`GPU_context_create` returns a live context with a real device** (the round's
  gate). Real WebGPU work executes: render passes are encoded and `Queue.Submit`ted on the
  device timeline (backend genuinely live).
- **GPU_init completes windowed** (boot proceeds past it).
- **Python/BPY startup runs**: `addon_utils`/`bl_pkg` addon registration + `bl_ui` scripts
  execute (CLOG time reached ~15.5 s).
- **GHOST window management is live**: the window sized/resized the `#canvas` to 1800×1169
  via the (worker→main-thread proxied) `emscripten_set_canvas_element_size`.
- **WM_main loop stage reached**: WM_init completed and `main()` does not exit (stable, no
  abort, exit `—`, for 20 s+). Initial window draws are attempted each tick.

**Remaining blockers (precise, characterized — none fatal to the boot this round):**
1. **Surface / first pixels — the real next gate (OWNED, next round).** The WM worker has no
   DOM canvas, so `wgpuInstanceCreateSurface`→`findCanvasEventTarget('#canvas')` can't
   resolve (`document` undefined; no OffscreenCanvas), surface deferred. Every window draw
   therefore hits Dawn `Render pass has no attachments` (the window framebuffer has no color
   attachment) → `[Invalid CommandBuffer]` on `Queue.Submit`; the canvas stays blank. FIX:
   add `-sOFFSCREENCANVAS_SUPPORT` + `-sOFFSCREENCANVASES_TO_PTHREAD="#canvas"` to the
   browser arm (`patches/platform_wasm.cmake`) — Emscripten's proxied-main already requests
   the transfer (`crt1_proxy_main.c:48 settransferredcanvases(-1)`), which registers the
   OffscreenCanvas in `specialHTMLTargets` on the WM worker so the selector resolves — then
   re-enable `finishSetup()` in `GHOST_ContextWGPUWeb::initializeDrawingContext`
   (`ghost_web_canvas_resolvable()` will return true). Files: `patches/platform_wasm.cmake`,
   `platform_web/ghost/GHOST_ContextWGPUWeb.cc`.
2. **Python C-extensions missing (python-wasm lane, NON-fatal — caught):**
   - `_multiprocessing` → `ModuleNotFoundError` at `multiprocessing/synchronize.py:17`
     (reached from `bl_pkg/__init__.py:580 _remote_asset_library_restore_backups` →
     `_bpy_internal/http/downloader.py:49`). `addon_utils.enable` catches it; `bl_pkg`
     addon fails to register but boot continues.
   - `_sha3` → hashlib `unsupported hash type sha3_512/shake_128/shake_256` at
     `hashlib.py:123` (logged, non-fatal).
3. **Splash image (imbuf lane, NON-fatal):** `IMB_load_image_from_memory: unknown
   file-format (<splash screen>)` — the splash image decodes to nothing; splash won't
   render, boot continues.
4. **Liveness nuance (honest):** whether WM_main continuously ticks at idle vs. parks after
   the initial draws is not distinguishable from the (Dawn-throttled) validation-warning
   channel this round; no fatal error occurs and BPY-level startup completed, which meets
   the ceiling. If a render-loop-time blocking readback (F9-D) is ever on the first-draw
   path it would park the worker — resolve per the "(4)" render-loop answer above
   (ProcessEvents-pump / poll-across-ticks), not a synchronous WaitAny.
