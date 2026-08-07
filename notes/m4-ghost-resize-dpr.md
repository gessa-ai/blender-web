<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 GHOST-side live resize + devicePixelRatio (ghost-web lane)

Fixes the two user-reported windowed-boot defects that the shell-native lane
characterised but could not fix from the shell alone (its "Residual gaps" 1 and 2):

1. **Live window resize -> black bars / blurry downscale.** Post-boot the `#canvas`
   is a worker-owned OffscreenCanvas; the main thread cannot grow its backing store,
   so the shell could only CSS-stretch (blur) or letterbox. FIXED GHOST-side.
2. **UI tiny at DPR >= 2.** `ghost_web_device_pixel_ratio()` returned 1.0 on the WM
   worker (no `window` there), so `U.pixelsize` stayed 1 while the backing store was
   2x. FIXED by forwarding the real DPR and reporting it through GHOST the macOS way.

Binary these fixes were verified on: `build-wasm-windowed/bin/blender_browser.wasm`
**wasm@2026-08-07T18:25:44-0400** (926372377 bytes), built from the shared working
tree (my WIP + the r28a gpu lane's in-flight edits). Export `_bw_shell_set_display`
confirmed present in the glue.

## Architecture wired

The load-bearing constraint: under `-sPROXY_TO_PTHREAD` + `OFFSCREENCANVASES_TO_PTHREAD`
main() and all GPU/GHOST work run on the WM worker, which owns the OffscreenCanvas but
has no `window`/`document`; the browser main thread has `window.devicePixelRatio` and the
resize events but cannot touch the transferred canvas. So both facts are handed across a
**shared-memory handshake** (`platform_web/ghost/GHOST_WebDisplayState.hh`):

- **Shell -> worker (main thread):** `boot-windowed.js` calls the EMSCRIPTEN_KEEPALIVE
  export `bw_shell_set_display(backingW, backingH, dpr)` (defined in `GHOST_SystemWeb.cc`).
  KEEPALIVE puts it in the module exports without editing the link flags (the build only
  exports `ENV,FS,callMain`, so `ccall`/`_emscripten_set_canvas_element_size` are NOT
  reachable - the shell-native lane's blocker). It performs only relaxed/release atomic
  stores into shared wasm memory, so calling it from the main thread and consuming on the
  worker is race-free and realm-independent. Posted at three points: `preRun` (before the
  proxied main() -> before the first `getDPIHint`/window size, so the UI boots at the right
  scale), once more after the module resolves (self-heals a preRun race), and on every
  `resize` / `ResizeObserver` / `(resolution)` media-query change.
- **Worker consumers:** `ghost_web::device_pixel_ratio()` (a plain shared atomic load) feeds
  the three GHOST DPI/scale answers; `ghost_web::poll_pending_backing()` is drained once per
  WM tick in `GHOST_SystemWeb::processEvents` - on a change it resizes the OffscreenCanvas
  backing store (`emscripten_set_canvas_element_size`, legal on the owning worker),
  `reconfigureSurface()` (which reconfigures the WebGPU surface + persistent back-buffer to
  the new extent - `configureSurface`/`ensureBackbuffer` already recreate on resize), and
  posts `GHOST_kEventWindowSize`. That size event makes the WM relayout AND recompute the UI
  scale (`wm_window.cc` GHOST_kEventWindowSize -> `WM_window_dpi_set_userdef`, unconditional).

### DPR model - mirrors macOS Cocoa exactly

`WM_window_dpi_set_userdef` does `auto_dpi = getDPIHint(); auto_dpi *= getNativePixelSize();`
On macOS `getDPIHint()` is the base constant **96** and `getNativePixelSize()` is the backing
scale (`drawableSize/clientBounds` == DPR). So GHOST_WindowWeb now:

- `getNativePixelSize()` -> **DPR** (was: base default 1.0 - never overridden).
- `getDPIHint()` -> **96** constant (was: `96*dpr`, which now would double-count against
  `getNativePixelSize()==DPR` and blow the UI up ~DPR x too large).
- `getClientBounds()` -> **logical** (backing / DPR), like Cocoa returning NSView points.
  Blender lays UI out in logical units and multiplies by `getNativePixelSize()` to reach the
  physical framebuffer (`wm_subwindow.cc wmWindowViewport_ex` uses
  `WM_window_native_pixel_size = sizex * nativePixelSize`). The WebGPU surface/back-buffer are
  sized directly from `emscripten_get_canvas_element_size` (backing), so `viewport =
  round(backing/DPR) * DPR = backing` stays consistent end to end (surface == back-buffer ==
  back_left == GPU viewport, all physical).

This also corrects a latent input bug: Emscripten `mouseEvent.targetX/Y` are CSS pixels
(`clientX - rect.left`), so with the old physical `getClientBounds` + `nativePixelSize==1` the
cursor was confined to the top-left quadrant at DPR>1. Now `cursor = targetX(CSS) *
nativePixelSize(DPR) = physical`, correct.

At **DPR 1 the whole change set is the mathematical identity** (getClientBounds divides by 1,
nativePixelSize=1, getDPIHint 96*1==96), so the golden/gate path and standard-DPI displays are
byte-identical to before.

## Files

- `platform_web/ghost/GHOST_WebDisplayState.hh` (new) - handshake accessor declarations.
- `platform_web/ghost/GHOST_SystemWeb.cc` - atomics + `bw_shell_set_display` KEEPALIVE export +
  `ghost_web::` accessors + the resize poll in `processEvents` (bounded diagnostic printf).
- `platform_web/ghost/GHOST_WindowWeb.{cc,hh}` - getNativePixelSize/getDPIHint/getClientBounds
  + setClient* logical<->backing scaling; removed the worker-blind `ghost_web_device_pixel_ratio`
  EM_JS.
- `platform_web/shell/boot-windowed.js` - `pushDisplayToWorker` via the export; preRun DPR seed;
  post-resolve re-push; resize/ResizeObserver/media-query wiring. No change to windowed.html or
  wgpu-preinit-worker.js; all dev hooks (?pyexpr/?args/?gate/window.__bwModule/#state) preserved.

## Verification verdicts (headed Playwright, bundled Chromium, port 8128, wasm@18:25:44)

`platform_web/shell/evidence/verify-resize-dpr.mjs` -> **10/10 checks passed**. Blender-internal
state read via a `?pyexpr` snapshot written to WasmFS and read back through `Module.FS`
(`win.width/height` == `win->sizex/sizey`; `preferences.system.pixel_size` == `U.pixelsize`).

- **Bug #2 - DPR-2 UI scale: FIXED.** DPR2 1440x900 -> `win=1440x900` (logical, not 2880x1800),
  `pixel_size=2.000`, dpi=144, ui_scale=2.000. Native 2x UI.
- **DPR-1 no regression:** DPR1 1280x720 -> `win=1280x720`, `pixel_size=1.000`. Unchanged.
- **Bug #1 - live resize: FIXED.** Resize 1440x900 -> 1000x700 @ DPR2 logged
  `WGPUWeb-resize: backing -> 2000x1400 (canvas readback 2000x1400, dpr 2.000)` - the
  OffscreenCanvas backing grew to exactly `cssPx * DPR` (=1000x700 * 2), surface reconfigured,
  WindowSize delivered. Canvas CSS box fills the window (fixed `inset:0`, `100vw/100vh`), so no
  letterbox + backing==cssPx*DPR => no blur. Reproduced 3x independently (2200x1560, 2000x1400 x2).
  NB: the WM rAF loop throttles when fully idle, so the poll drains on the next browser event
  (the resize itself, or any input) - exactly the real resize scenario; only a headless test with
  a fully idle loop needs an input nudge to observe it deterministically.
- **?gate=WxH regression: PASS.** `?gate=1280x720` under deviceScaleFactor 2 -> canvas backing
  EXACTLY 1280x720, bw-gate layout, loader gone, and Blender sees `win=1280x720 pixel_size=1.000`
  (DPR forced 1, DPR-independent). Gate contract intact.

Evidence PNGs: `m4-ghost-resize-01-dpr2-1440x900.png`, `-02-dpr2-resized-1000x700.png`,
`-03-dpr1-1280x720.png`, `-04-gate-1280x720.png` (the 01/03/04 page.screenshots read blank -
the known M4 OffscreenCanvas readback blocker for programmatic capture; the substantive proof is
the bpy-state numbers above), plus `-05-composite-1600x900.png` (a real rendered full-window
capture via the parity-lane pyexpr-kick method).

## Y-inversion (driver alert): NOT this lane, NOT fixed

`m4-ghost-resize-05-composite-1600x900.png` (wasm@18:25:44, gate 1600x900) still composites the
whole UI **vertically inverted**: File/Edit topbar + workspace tabs at the window BOTTOM, viewport
header + "Pan View / Context Menu" status text at the TOP, Outliner below Properties on the right
rail. Text is upright (not a per-pixel flip) - a region-layout Y-origin inversion in the composite.

**Not caused by this lane.** The parity harness measures in `?gate` (DPR 1), where this entire
change set is the identity (see above) and the resize poll never fires (the shell posts nothing in
gate mode). This lane never touches the composite/present path (`configureSurface`/`ensureBackbuffer`/
`presentBackbuffer`/the present shader) or the gpu backend. The inversion reproduces with the r28a
gpu lane's `[bw-r28]` diagnostics live in the same binary; per the driver it is new in the r28 WIP
(r27 committed evidence was upright) and is the r28a lane's to resolve. My orthogonal fixes do not
make it better or worse.

## Residuals / follow-ups

1. **Y-inversion** (above) - r28a gpu-backend lane; my landing does not depend on or affect it.
2. **`WM_window_dpi_get_scale`** (wm_window.cc:782) is `OS_MAC`-gated, so on the wasm build it
   returns `getDPIHint()/96 == 1` regardless of DPR. It only scales the SOFTWARE cursor
   (`wm_cursors.cc`, `wm_draw.cc`) - rarely hit on the web (the hardware CSS cursor is used), so
   the software cursor is not upscaled at DPR>=1. Cosmetic; the primary UI scale (U.pixelsize/
   scale_factor/widget_unit) is correct via `WM_window_dpi_set_userdef`. Fixing needs an upstream
   patch (can't touch upstream from this lane).
3. **Idle-loop resize latency:** the resize applies on the next browser event, not on a fully idle
   frame (the emscripten rAF main loop throttles when idle). Real resizes carry their own events so
   this is invisible in practice; a future invalidate-driven present would remove even the
   theoretical latency.
4. **Programmatic capture of the WebGPU OffscreenCanvas** stays blank via `page.screenshot`/
   `toDataURL` for plain boots (r24/r25 readback-zero blocker); the parity-lane pyexpr-kick method
   yields a real frame. Orientation/state verification here is bpy-state based, so it is unaffected.
