<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M4.pre2 — GHOST-web design (event layer + main loop)

The backend-independent half of M4: a custom GHOST platform back-end over Emscripten
HTML5 input, built + verified standalone (like the GPU sandbox modules). The GPU/canvas
context is the separate `GHOST_ContextWGPU` lane (patch 0011). Recon + tables:
`notes/ghost-web-recon.md`.

## Module layout (`platform_web/ghost/`)

| file | role |
|---|---|
| `GHOST_SystemWeb.{hh,cc}` | platform half: registers HTML5 callbacks, owns the canvas window + tracked input state (modifiers/buttons/cursor), drives the GHOST queue. Subclass of the real `GHOST_System`. |
| `GHOST_WindowWeb.{hh,cc}` | `<canvas>`-backed `GHOST_Window`: size/DPI/fullscreen, WGPU context (gated). |
| `GHOST_EventBridgeWeb.{hh,cc}` | **pure translation**: `EmscriptenMouseEvent/WheelEvent/KeyboardEvent/UiEvent` → `GHOST_Event*` + `pushEvent()`. No registration/lifetime logic. |
| `GHOST_KeyMapWeb.hh` | `code`→`GHOST_TKey` table + utf8-from-`key`. |
| `harness/` | standalone wasm test page (see Verification). |

Separation rationale: the **bridge** is stateless, unit-reasonable translation; the
**system** owns platform registration + the state the bridge writes and GHOST reads.
Static C callback thunks (in `GHOST_SystemWeb.cc`) recover the `GHOST_SystemWeb*` from
the HTML5 `userData` pointer and call the bridge — no globals/singleton.

## Main-loop design under our threading model (ADR-003)

This is the load-bearing integration decision for the real Blender build (the harness
is deliberately single-threaded — see Verification).

**Topology.** Under GOAL's posture (`-pthread` + `-sPROXY_TO_PTHREAD`), Blender's
`main()` / `WM_main` loop runs on a **worker** (the "main" pthread); the browser main
thread only services the event loop. Emscripten HTML5 input fires on the **browser
main thread**; `emscripten_set_*_callback[_on_thread]` **proxies** each event to the
thread that registered it (default = calling thread). So the callbacks, registered from
the WM worker, are delivered on that worker — but only when the worker **pumps the proxy
queue**, which happens at its main-loop yields.

**Shape (required):**
1. Run the WM loop under `emscripten_set_main_loop(tick, 0, /*simulate_infinite_loop=*/1)`
   on the WM worker (rAF-paced; `fps=0` = `requestAnimationFrame`). NOT a blocking
   `while(1)` — a blocking loop starves the proxy queue and never sees input, and cannot
   yield to JSPI.
2. Each `tick` is the ONE place events are pumped and the ONE permitted suspend point:
   `GHOST_ProcessEvents` (drains proxied callbacks → `pushEvent`) → `GHOST_DispatchEvents`
   (WM handlers) → redraw. This is exactly **ADR-003's suspend-topology invariant**:
   *"JSPI suspend points may exist ONLY at top-level async boundaries — main-loop tick,
   event-handler entry, and the OPFS/async shims — and NEVER while a C++ `try` is active
   or the imbuf/jpeg setjmp scope is live."* The event pump sits at the top-level tick,
   above any `try`/`setjmp` scope, so a GPU `wait` or OPFS read reached from a tick can
   suspend cleanly.
3. `processEvents(waitForEvent)` must **not block** on the web: there is no
   `SDL_WaitEvent` equivalent that is safe on a worker servicing a proxy queue. Ours
   returns immediately, reporting whether the queue is non-empty (callbacks already
   enqueued). `waitForEvent` is ignored (documented in `GHOST_SystemWeb::processEvents`).

`requestAnimationFrame` vs `emscripten_set_main_loop`: use the latter — it *is* rAF
under the hood but also integrates emscripten's proxy-queue draining and runtime
lifetime. A hand-rolled rAF from JS would bypass the proxy pump.

**Callback thread targeting (M4 integration TODO):** register with
`emscripten_set_*_callback_on_thread(..., wm_pthread)` so events land on the WM worker
directly (or use `EM_CALLBACK_THREAD_CONTEXT_MAIN_BROWSER_THREAD` + explicit proxying).
The harness (main-thread) uses the plain `_callback` convenience form. This is the one
piece the standalone harness does not exercise; it is covered by the ADR-003 M4 gate
(Chrome ≥137 topology smoke).

## State tracking

- **Modifiers**: updated from every DOM event's `ctrlKey/shiftKey/altKey/metaKey`.
  `getModifierKeys()` reports **left variants** (DOM flags don't distinguish sides);
  key *events* carry the exact left/right `GHOST_TKey` via `code`. SDL-grade limitation,
  documented.
- **Buttons**: `GHOST_Buttons` updated on down/up; returned by `getButtons()`. Browser focus loss
  snapshots the held set, clears all seven tracked buttons and every modifier, and emits a
  `ButtonUp` for each held button before `WindowDeactivate`. This retires physical state even
  when a tab switch or browser blur supplies no matching DOM release event.
- **Cursor**: last canvas-relative `targetX/targetY` while unlocked. During a wrap/hide grab,
  Pointer Lock `movementX/Y` advances the virtual cursor with signed-int saturation;
  `getCursorPosition()` returns that virtual position.

## Capabilities & browser constraints

`getCapabilities()` = `GHOST_CAPABILITY_FLAG_ALL` minus a sandboxed-canvas mask:
`WindowPosition` (no OS window), `CursorWarp` (absolute positioning is unavailable),
`Clipboard{Primary,Image}`, `DesktopSample`, `WindowDecorationStyles`,
`KeyboardHyperKey`, `Cursor{RGBA,Generator}`, `MultiMonitorPlacement`, `WindowPath`.

Constraints and deferrals (with a named blocker wherever work remains):
- **IME / dead-keys** — implemented. A hidden browser textarea follows Blender's requested caret
  rectangle and turns `compositionstart/update/end` into owned UTF-8 start/update/commit/end
  messages. A bounded SPSC queue crosses from the browser main thread to the WM worker, where
  `processEvents()` creates the stock `GHOST_kEventImeComposition*` events. Disabled input and
  saturation reject without overwriting earlier transitions; the capability is advertised.
- **Text clipboard** — implemented through a browser-main cache. Trusted `paste` events publish
  external text before the queued worker key event; `putClipboard` synchronously owns Blender's
  borrowed UTF-8 before starting `navigator.clipboard.writeText`, and `getClipboard` allocates an
  owned UTF-8 result on the main runtime thread. Already-granted read permission also refreshes
  before menu interaction. Primary selection and image clipboard remain capability-masked.
- **Cursor grab / absolute warp** — wrap and hide grabs use Pointer Lock and consume relative
  movement; wrap retains Blender's software cursor while hide does not. Disable exits Pointer
  Lock, and normal preserves visible-pointer semantics. Absolute `setCursorPosition` remains
  unavailable and returns failure, so `CursorWarp` stays honestly off.
- **Fullscreen state transitions** — implemented with the HTML5 Fullscreen API. Entry
  accepts Emscripten's deferred user-activation result; normal/maximized exit fullscreen,
  and browser-impossible minimization fails honestly. The shell display bridge owns the
  transferred canvas's backing-size update after the DOM changes its CSS extent.
- **Tablet / NDOF / trackpad gestures** — `GHOST_TABLET_DATA_NONE`; PointerEvent
  pressure + gesture events are a later pass.

## Verification (headless, self-driven — 2026-08-04)

Standalone harness `platform_web/ghost/harness/` builds the web classes + the REAL
upstream GHOST bases (recon §4) with the product's WasmFS + PROXY_TO_PTHREAD topology.
A logging `GHOST_IEventConsumer` registered on the real `GHOST_EventManager` prints each
decoded event; window-state requests cross shared atomics and execute only on the WM worker.

- **Server headers**: served via `scripts/serve-web.sh` (`BLENDER_WEB_SHELL=.../harness`);
  correct MIME (`application/wasm`, `text/javascript`).
- **Real headless Chrome** (Playwright chromium; scratchpad `chrome_ghost.js`): synthetic
  input over the canvas → **11/11** GHOST-event assertions PASS, dispatched through the
  genuine `GHOST_EventManager`:
  - `CursorMove x,y` (canvas-relative `targetX/Y`);
  - `ButtonDown/Up button=0` (left), `button=2` (right);
  - `Wheel axis=0 value=-1` (down) / `value=1` (up);
  - `KeyDown key=0x041 utf8='a'`, `KeyDown key=0x042 utf8='B'` (Shift+B), `Shift`
    modifier `key=0x100`, `ArrowLeft key=0x10F`, `Escape key=0x01B`, matching `KeyUp`s.

Manual: `scripts/serve-web.sh` with the harness docroot, open the URL, move/click/
scroll/type over the dashed canvas; events appear in the log box.

## Open questions for M4 integration

1. **Callback thread targeting** — register HTML5 callbacks on the WM pthread vs proxy
   from the browser main thread. Decide with the real proxied loop; validated by the
   ADR-003 M4 smoke. (The only untested-by-harness piece.)
2. **Canvas sizing / HiDPI** — reconcile CSS size vs drawing-buffer size vs
   `devicePixelRatio` with the WGPU swapchain (`GHOST_ContextWGPU`). `getDPIHint` returns
   `96*dpr`; the buffer-size policy is a context-integration call.
3. **`processEvents` cadence** — confirm the WM's expectation that `processEvents` never
   blocks holds across modal operators (they run their own inner `GHOST` pumps).
4. **Focus model** — single-canvas blur state retirement is resolved: tracked modifiers/buttons
   clear before deactivation and held buttons receive releases. When there are multiple GHOST
   windows (later), route keyboard input by focused canvas.
5. **Coordinate origin** — GHOST expects top-left client origin; `targetX/Y` match. The
   Pointer Lock wrap path now preserves a virtual GHOST position through relative deltas; the
   real product middle-drag path is covered by the 2026-08-25 diagnostic.
