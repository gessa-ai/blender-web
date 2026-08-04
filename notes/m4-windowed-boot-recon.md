<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M4 — windowed-boot recon (the "looks like Blender" gap list)

Read-only recon at the pin (`fbe6228777e7`). Current state: headless `--background`
boots to `BPY_OK` in a Chrome tab (`notes/m4-browser-shell.md`); GHOST-web event layer
proven standalone (`notes/ghost-web-{recon,design}.md`); browser WebGPU context proven
in-tab (`GHOST_ContextWGPUWeb`, `notes/ghost-web-wgpu-context.md`); native-Dawn
`GHOST_ContextWGPU` + `webgpu/` backend under construction (M3, 22 files).

**Headline:** the 93 MB payload is already sufficient — no new UI assets are needed.
The M4 gap is entirely **build-config + integration seams**: flip `WITH_HEADLESS` OFF
/ `WITH_WEBGPU_BACKEND` ON, add the GHOST factory branch, map the WebGPU drawing-context
type, reconcile the two WGPU context classes, and hook `WM_main`'s blocking loop onto
`emscripten_set_main_loop`. Everything above GHOST/GPU is Blender's own code and is
already exercised by the headless boot.

---

## 1. The windowed init path — what `--background` skips

Top-level split (`creator.cc:643-664`): `G.background` → `WM_exit`; **else →
`WM_init_splash_on_startup(C)` + `WM_main(C)`** (creator.cc:661,663). Our current build
takes the background branch; M4 is the `else`.

`WM_init` (`wm_init_exit.cc:201`) has three `!G.background` blocks the background path skips:

| step | call site | what it needs |
|---|---|---|
| GHOST system create | `wm_ghost_init(C)` `wm_init_exit.cc:205` → `wm_window.cc:2269` | `GHOST_ISystem::createSystem()` (2283) — **the factory, which `WITH_HEADLESS` no-ops**; `GPU_backend_ghost_system_set` (2285); `addEventConsumer` (2306); `useNativePixel`/`useWindowFocus`. (Background uses `wm_ghost_init_background` `:2328` → `createSystemBackground()` → `GHOST_SystemHeadless`.) |
| cursor data | `wm_init_cursor_data()` `:206` | loads standard cursor bitmaps (cheap). |
| GPU + interface | block `:295-324` | `wm_window_ghostwindows_remove_invalid`; `GPU_render_begin`; **`WM_init_gpu()` `:314`** (→ `DRW_gpu_context_create` + `GPU_init`, `wm_init_exit.cc:148`); `WM_platform_support_perform_checks`; **`ui::init()` `:321`** (→ `resources_init` `resources.cc:55` → `icons_init()` `:57`) inside `GPU_context_begin_frame/end_frame` — **needs a live GPU context**. |

`BPY_python_start` (`:331`) runs in **both** modes (not gated) — so the Python
registration chain is already proven headless (§3).

**Window creation** happens *after* file-read, via `wm_window_ghostwindows_ensure`
(`wm_window.cc:1196`, asserts `G.background==false`; called from `wm.cc` on file-load) →
`wm_window_ghostwindow_ensure` (`:1100`) → `wm_window_ghostwindow_add` (`:960`). The
load-bearing body (`:1001-1092`):

```
gpu_settings.context_type = wm_ghost_drawing_context_type(GPU_backend_type_selection_get())  //:1011
ghost_window = g_system->createWindow(title,x,y,w,h,state,gpu_settings,...)                    //:1032
win->runtime->gpuctx = GPU_context_create(ghost_window, nullptr)                               //:1045
GPU_render_begin(); GPU_init();                                                                //:1046,1049
wm_window_set_drawable(...); ui::theme::theme_set(SPACE_TOPBAR,...);                            //:1053,1076
wm_window_swap_buffer_acquire(win); GPU_clear_color(bg...); WM_window_dpi_set_userdef(win);     //:1080-1084
wm_window_swap_buffer_release(win); GPU_clear_color(...); GPU_render_end();                     //:1086-1091
```

`wm_ghost_drawing_context_type` (`wm_window.cc:2369-2399`) has cases for
None/OpenGL/Vulkan/Metal but **no WebGPU case** — a `GPU_BACKEND_WEBGPU` here hits
`BLI_assert_unreachable()`. **Gap: patch needed** (`GPU_BACKEND_WEBGPU →
GHOST_kDrawingContextTypeWebGPU`; enum already exists `GHOST_Types.hh:289`).

**Main loop.** `WM_main` (`wm.cc:598`) is a blocking `while(true) {
wm_window_events_process; wm_event_do_handlers; wm_event_do_notifiers; wm_draw_update }`.
`wm_window_events_process` (`wm_window.cc:2198`) asserts `BLI_thread_is_main()` (= the
proxied-main WM worker), then `g_system->processEvents(false)` → `dispatchEvents()`, and
**`BLI_time_sleep_precise_us(5000)` when idle** (`:2226`).

*Emscripten hook (integration decision, per `ghost-web-design.md` §main-loop + ADR-003):*
the blocking `while(true)` must become an `emscripten_set_main_loop(tick, 0,
/*simulate_infinite_loop=*/1)` on the WM worker, where `tick` = **one iteration** of the
`WM_main` body — the single top-level suspend/pump point. `processEvents` already returns
without blocking (`GHOST_SystemWeb::processEvents` ignores `waitForEvent`); the idle
`BLI_time_sleep_precise_us` must become a yield, not a busy-block. Callbacks must be
registered on the WM pthread (`_callback_on_thread(..., wm_pthread)`) so proxied HTML5
events drain at the tick — the one piece the standalone harness did not exercise.

Splash: `WM_init_splash_on_startup` (`wm_init_exit.cc:397`) → shows unless
`USER_SPLASH_DISABLE` / a file is loaded → `WM_OT_splash` operator (`:416`, Python UI op).
Non-blocking modal popup; not on the critical path to first pixels.

---

## 2. UI payload inventory — already covered by the 93 MB preload

Two delivery mechanisms: **datatoc** (`data_to_c_simple` → C array compiled into the wasm,
already in the 112 MB `.wasm`) vs **runtime file** (read from `BLENDER_DATAFILES`/`SCRIPTS`,
which we mount wholesale at `/bw`).

| asset | source path | size | mechanism | in current payload? |
|---|---|---|---|---|
| UI icons (mono+color) | `release/datafiles/icons_svg/*.svg` | 3.1 MB src | **datatoc** (`editors/datafiles/CMakeLists.txt:1023`); rasterized at runtime by `icons_init()` (`interface_icons.cc:937`, types `ICON_TYPE_SVG_MONO/COLOR`) | **in wasm** — but `icons_init()` is `#ifndef WITH_HEADLESS` (`:1124-1130`) → skipped today |
| fallback vector font | `release/datafiles/bfont.pfb` | 28 KB | **datatoc** (`editors/datafiles/CMakeLists.txt:178`) | in wasm |
| splash image | `release/datafiles/splash.png` | (datatoc) | **datatoc** (`:1076`) | in wasm |
| UI fonts (Inter, mono, CJK, …) | `release/datafiles/fonts/*.woff2` | 15 MB | **runtime** — `BLF_load_default` reads `BLENDER_DATAFILES/fonts/Inter.woff2` etc. (`blf_font_default.cc:26-49`; names = `BLF_DEFAULT_*` `BLF_api.hh`) | **yes** (datafiles mount) |
| studiolights + matcaps | `release/datafiles/studiolights/{world,studio,matcap}` | 168 KB | **runtime** — `BKE_studiolight_init` (`wm_init_exit.cc:251`) scans dir | **yes** (datafiles mount) |
| colormanagement (OCIO) | `release/datafiles/colormanagement` | 19 MB | **runtime** (read in `WM_init` before scene) | **yes** (datafiles mount) |
| cursors | `release/datafiles/cursors` | 304 KB | runtime | yes (datafiles mount) |
| startup.blend / userdef / preview.blend | `release/datafiles/{startup.blend,userdef,preview.blend}` | ~150 KB | runtime (home-file read) | yes (datafiles mount) |
| `bl_ui` (79) / `bl_operators` (36) | `scripts/startup/bl_{ui,operators}` | (in 12 MB scripts) | runtime import | **yes** (scripts mount) |
| keymaps / themes / presets | `scripts/presets/keyconfig`, `scripts/presets/interface_theme`, … | (in 12 MB scripts) | runtime | **yes** (scripts mount) |

**Conclusion:** the existing wholesale `datafiles` + `scripts` mounts (`m4-browser-shell.md`
manifest) already carry every windowed-UI asset. The only "missing" piece is that
`icons_init()` is compiled out by `WITH_HEADLESS` — a build-config fix, not a payload fix.
(M7 size work will tree-shake fonts/CJK and stdlib; out of M4 scope.)

---

## 3. The registration chain — already proven headless

`BPY_python_start` (`wm_init_exit.cc:331`) is **not** gated by `G.background`, so
`bpy.utils.load_scripts()` registers `bl_ui`/`bl_operators` in our current headless boot.
Evidence: the boot reaches `BPY_OK 5.2.0 LTS 3` (`m4-browser-shell.md`) — i.e. panel/menu
`register_class` runs to completion (RNA-type registration needs **no** window or GPU).
`WM_keyconfig_init` (`:363`) and `load_scripts_extensions` (`wm_init_scripts_extensions_once`
`:367,425`) also run in both modes.

**Headless-vs-windowed difference is GPU-side, not Python-side:** the windowed-only work is
`ui::init()`/`icons_init()` (texture upload) — panels themselves register identically.

Known web-hostile registration cases (already triaged, all *caught & non-fatal* —
`m4-browser-shell.md`): the `bl_pkg` extensions add-on `register()` fails because
`_multiprocessing` and `sha3`/`shake` C-extensions are disabled in the wasm CPython;
Blender catches it and continues. No *new* web-hostile dependency is introduced by
`bl_ui.register` itself. M4 adds no new registration risk beyond these.

---

## 4. GHOST integration seams — wm's call surface vs our classes

Blender 5.2 wm uses the **C++ GHOST interface directly** (`GHOST_ISystem*`/`GHOST_IWindow*`,
`wm_window.cc:30-35`), not the C-API — which matches our `GHOST_System`/`GHOST_Window`
subclasses. Load-bearing calls (`rg '->method('` in `wm_window.cc` + `wm_init_exit.cc`),
mapped onto `platform_web/ghost/`:

| GHOST call (wm) | status in our classes | note |
|---|---|---|
| `GHOST_ISystem::createSystem()` (factory) | **MISS — critical** | `wm_ghost_init:2283`. Factory is `#if WITH_HEADLESS /* Pass */` (`GHOST_ISystem.cc`). Needs a `WITH_GHOST_WEB` branch constructing `GHOST_SystemWeb`. |
| `createWindow` | **covered** | `GHOST_SystemWeb::createWindow` (SystemWeb.cc:233) → `new GHOST_WindowWeb`. |
| `createOffscreenContext` / `newDrawingContext` | **stub — wrong class** | both return the **native** `GHOST_ContextWGPU` (SystemWeb.cc:215, WindowWeb.cc:161) whose `initializeDrawingContext()` does sync `instance_.WaitAny(...)` (`GHOST_ContextWGPU.cc:39,65`) → **deadlocks the browser** (wgpu-context note delta #2). Must use the async `GHOST_ContextWGPUWeb`. See reconciliation below. |
| `processEvents`/`dispatchEvents` | **covered** | `processEvents` non-blocking (SystemWeb); `dispatchEvents` + `addEventConsumer` via `GHOST_System` base (`ghost_event_proc`/`GHOST_CallbackEventConsumer` `wm_window.cc:2278`). |
| `getModifierKeys`/`getButtons`/`getCapabilities`/`getCursorPosition`/`getMainDisplayDimensions`/`getAllDisplayDimensions`/`getMilliSeconds`/`getWindowUnderCursor` | **covered** | implemented in `GHOST_SystemWeb`. |
| `getClipboard`/`putClipboard` | **stub (deferred)** | null/no-op — async browser clipboard; capability off. |
| `hasClipboardImage`/`getClipboardImage`/`putClipboardImage` | base default (no-op) | deferred; not on boot path. |
| `initDebug`/`useNativePixel`/`useWindowFocus`/`setTabletAPI`/`setMultitouchGestures`/`getTime` | base default (`GHOST_System`) | fine. |
| `setConsoleWindowState` | **covered** (returns false) | `wm_init_exit.cc:340`. |
| `setIconGenerator`/`setWindowCSD*` | N/A | `WITH_GHOST_WAYLAND`/`WITH_GHOST_CSD` only (both OFF). |
| `showMessageBox` | base default | GPU-fallback/platform-support path; harmless. |
| **Window:** `getState`/`setState`/`setTitle`/`getTitle`/`getClientBounds`/`screenToClient`/`clientToScreen`/`setClientSize`/`invalidate`/`getDPIHint` | **covered** | `GHOST_WindowWeb`. |
| `getNativePixelSize` (11× in wm) | base default → `1.0f` | acceptable for M4 (HiDPI via `getDPIHint`); revisit for retina swapchain. |
| `swapBufferAcquire`/`swapBufferRelease`/`activateDrawingContext` | **covered / no-op** | web auto-presents on yield (wgpu-context note delta #3); `swapBufferRelease`→no-op. |
| `setPath`/`setOrder`/`setProgressBar`/`endProgressBar`/`setModifiedState`/`beginIME`/`endIME`/`set*DecorationStyle*` | base default / stub | non-boot-critical; IME + decoration deferred. |
| `setWindowCursorShape`/`Visibility`/`Grab` (protected) | **stub (no-op)** | M4 uses the browser/CSS cursor; map to `canvas.style.cursor` later. |

### WGPU context duality — recommendation

Two classes exist for the same job:
- **`GHOST_ContextWGPU`** (`upstream/intern/ghost/intern/GHOST_ContextWGPU.{cc,hh}`, patch
  0011) — a real `GHOST_Context` subclass, **native Dawn**, **synchronous** `WaitAny`
  device acquisition. Purpose: M3 native-Dawn offscreen conformance (`GHOST_SystemHeadless`
  offscreen case). **Deadlocks in-browser.**
- **`GHOST_ContextWGPUWeb`** (`platform_web/ghost/GHOST_ContextWGPUWeb.{hh,cc}`) —
  **emdawnwebgpu**, **async** (`CallbackMode::AllowSpontaneous`), proven in a real Chrome
  tab. But it is **not** a `GHOST_Context` subclass (hh:40), so it cannot be returned from
  `newDrawingContext()` (which must return `GHOST_Context*`).

**Recommendation: two classes + one `#ifdef __EMSCRIPTEN__` selection seam — NOT one class
with arms.** Native Dawn and emdawnwebgpu are genuinely different *link targets* (different
`webgpu.h`, different surface structs, different wait model per the 3 documented deltas);
folding them into one TU with `#ifdef` arms would entangle two Dawn variants in a single
compile. Instead:
1. Promote `GHOST_ContextWGPUWeb` to derive `GHOST_Context` (its accessors already mirror
   `GHOST_ContextWGPU` by design — wgpu-context note "GHOST integration").
2. In `GHOST_WindowWeb::newDrawingContext` / `GHOST_SystemWeb::createOffscreenContext`,
   `#ifdef __EMSCRIPTEN__` return `GHOST_ContextWGPUWeb`, else the native `GHOST_ContextWGPU`
   (keeps the M3 native offscreen-conformance harness intact).
3. Bridge async→sync at **one** top-level boundary: acquire the device via a one-time JSPI
   await (or gate the WM-loop start on the ready-callback) at startup, so
   `createWindow`→`GPU_context_create`→`GPU_init` (`wm_window.cc:1045-1049`) see a ready
   device. ADR-003-legal (suspend at the init boundary, never inside a render `try`).
   `swapBufferRelease`/`activateDrawingContext` → no-ops (implicit-present device model).

The WebGPU GPU backend (`gpu/webgpu/wgpu_context.cc`) then pulls `getDevice/getQueue/
getSurface/getSurfaceFormat` off whichever context the seam returned — one
`GHOST_kDrawingContextTypeWebGPU` code path in wm/gpu regardless.

---

## 5. The minimal honest M4 cut + task list (dependency order)

**Target:** one canvas window, default startup workspace (Layout), default scene
(cube/camera/light), correct theme, splash on top, first frame matching the native golden
within idiff. **Explicitly deferred:** multi-window, drag-n-drop, IME/dead-keys, clipboard,
cursor-warp / Pointer-Lock, tablet/NDOF, software cursor (use CSS cursor), retina swapchain
tuning, staged/lazy payload (M7).

**Dispatch gate:** M3's WebGPU `gpu` suite green (native Dawn) — this list wires the
already-proven GHOST-web + in-tab WebGPU context to the real build.

| # | task | files / seam | depends |
|---|---|---|---|
| 1 | **Build-config flip** `WITH_HEADLESS` OFF + `WITH_WEBGPU_BACKEND` ON; add `WITH_GHOST_WEB` and compile `platform_web/ghost/*` into the GHOST lib | `patches/blender_web.cmake:44`, `patches/platform_wasm.cmake`, ghost `CMakeLists.txt` | — (unblocks icons_init, DRW, interface) |
| 2 | **GHOST factory seam:** construct `GHOST_SystemWeb` from `createSystem()`/`createSystemBackground()` under `WITH_GHOST_WEB` | patch `intern/ghost/intern/GHOST_ISystem.cc` | 1 |
| 3 | **wm drawing-context map:** add `case GPU_BACKEND_WEBGPU → GHOST_kDrawingContextTypeWebGPU` | patch `windowmanager/intern/wm_window.cc:2369` (`wm_ghost_drawing_context_type`) | 1 |
| 4 | **Context reconciliation** (§4): `GHOST_ContextWGPUWeb : GHOST_Context`; `#ifdef __EMSCRIPTEN__` return it from `newDrawingContext`/`createOffscreenContext`; one-time startup device await | `platform_web/ghost/GHOST_ContextWGPUWeb.{hh,cc}`, `GHOST_WindowWeb.cc:157`, `GHOST_SystemWeb.cc:210` | 2,3 |
| 5 | **Main-loop hook:** `WM_main` blocking `while(true)` → `emscripten_set_main_loop(tick,0,1)` on WM worker (tick = one loop body); idle `BLI_time_sleep_precise_us` → yield; register HTML5 callbacks on the WM pthread | `wm.cc:598` (patch or a web `WM_main_web` entry), `GHOST_SystemWeb::registerCanvasCallbacks` | 4 |
| 6 | **Canvas/swapchain sizing:** reconcile `getClientBounds`/`getMainDisplayDimensions` with canvas drawing-buffer + `devicePixelRatio`; confirm `swapBufferRelease` no-op auto-present | `GHOST_WindowWeb.cc`, `GHOST_ContextWGPUWeb` configure | 4 |
| 7 | **Boot args:** drop `--background`, add windowed args + canvas selector in `boot.js`; verify `blender_web_browser_binary` links the interface/DRW archives now that `WITH_HEADLESS` is OFF | `platform_web/shell/boot.js`, `patches/platform_wasm.cmake` browser target | 1 |
| 8 | **First-draw bring-up:** default `startup.blend` → Layout workspace + cube/camera/light; `ui::init`/`icons_init` upload; `theme_set`; splash (`WM_OT_splash`) renders | (integration; no new files) | 5,6,7 |
| 9 | **M4 gate:** idiff first frame vs native golden on the pinned adapter; register deferrals in `ledger/deferred.json` | harness | 8 |

Cross-refs: `notes/ghost-web-design.md` (main-loop/ADR-003), `notes/ghost-web-recon.md`
(surface tables), `notes/ghost-web-wgpu-context.md` (async device deltas),
`notes/m4-browser-shell.md` (payload manifest + headless boot evidence).
