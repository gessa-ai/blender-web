<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 shell - native-app windowed boot (shell-native lane)

Makes `platform_web/shell/windowed.html` + `boot-windowed.js` feel like a native
desktop app instead of an HTML mockup: instant black boot, a sharp full-window
canvas at the display's real pixel density, and input that reaches Blender rather
than the browser. Scope is the SHELL only - no GHOST / GPU / build changes. The
verification/gate contract the M4 rig depends on is preserved verbatim.

## What shipped

1. **No context menu; right-clicks reach Blender.** `contextmenu` is
   `preventDefault()`-ed at the window. This suppresses only the browser's HTML
   menu - the `mousedown`/`mouseup` (button 2) still fire and reach GHOST's
   Emscripten mouse callbacks, so Blender opens its OWN viewport menu.
2. **Instant boot, no mockup chrome.** The Boot button, status pills and log
   panel are gone from the view. The page auto-boots on load; it is all-black
   (`html,body,#canvas` background `#000`) with a centred pulse + progress bar.
   `boot()` is idempotent, so a rig that still clicks the (hidden) `#run` element
   is a harmless no-op.
3. **Full-window, DPR-correct canvas.** Before the module boots (before the
   canvas is transferred to the WM worker as an OffscreenCanvas), the shell sets
   `canvas.width/height = innerW/innerH * devicePixelRatio` and CSS to
   `100vw/100vh`. GHOST adopts that backing extent as the window client size
   (`GHOST_WindowWeb` ctor "ADOPT the canvas's existing extent") and configures
   the WebGPU surface to match. Verified: 1440×900 @ DPR 2 → 2880×1800 backing,
   canvas fills the window.
4. **Loading indicator that vanishes on first pixels.** Progress is driven by
   Emscripten's `setStatus` `(cur/total)` byte counts (reuses the existing
   `dlEl` wiring); it dismisses on the `presentBackbuffer` stdout signal, with a
   WM_main + 2.5 s settle fallback (both sanctioned by the task). In this build
   `presentBackbuffer` did not surface to the main-thread console, so the settle
   fallback is what fired - the loader reliably disappears either way.
5. **Native input hardening** (see sources below).

## Input-hardening measures + sources

| Measure | How | Source |
| --- | --- | --- |
| No page scroll / rubber-band | `overflow:hidden` + `overscroll-behavior:none` on `html,body` | MDN `overscroll-behavior` <https://developer.mozilla.org/en-US/docs/Web/CSS/overscroll-behavior> |
| App owns all touch gestures | `touch-action:none` on `html,body,#canvas` | MDN `touch-action` <https://developer.mozilla.org/en-US/docs/Web/CSS/touch-action> |
| No text selection | `user-select:none` (+ `-webkit-`/`-moz-`) | MDN `user-select` <https://developer.mozilla.org/en-US/docs/Web/CSS/user-select> |
| No iOS long-press callout / tap flash | `-webkit-touch-callout:none`, `-webkit-tap-highlight-color:transparent` | Kiosk guide <https://digitalrecordboard.com/blog/disable-pinch-zoom-css-html-js-kiosk/> |
| No pinch / double-tap zoom | `meta viewport user-scalable=no,maximum-scale=1` + `touch-action:none` + `preventDefault` on `wheel` w/ `ctrlKey` (trackpad pinch) + Safari `gesture*` events + double-`touchend`<300ms guard | Kiosk guide (above); MDN `touch-action` |
| DPR-correct sharp canvas | `canvas.width = cssW * devicePixelRatio` (backing store ≠ CSS size) | "Drawing Pixels is Hard" <https://phoboslab.org/log/2012/09/drawing-pixels-is-hard>; "High DPI rendering on HTML5 canvas" <https://cmdcolin.github.io/posts/2014-05-22/>; MDN `devicePixelRatio` <https://developer.mozilla.org/en-US/docs/Web/API/Window/devicePixelRatio> |
| Keyboard reaches Blender, not the browser | `keydown` capture-phase `preventDefault` for Tab / Space / arrows / PageUp-Down / Home / End / Backspace / F1–F11 / Ctrl+Cmd+S / quick-find `'` `/` - **only when the canvas owns focus**, and never `stopPropagation` (Emscripten's own listener still gets the key) | MDN `KeyboardEvent.preventDefault`; general canvas-game practice |
| Drags that leave the window keep working | `setPointerCapture(e.pointerId)` on `pointerdown` | MDN `Element.setPointerCapture` <https://developer.mozilla.org/en-US/docs/Web/API/Element/setPointerCapture> |
| Keyboard focus from frame 0 | `canvas` `tabindex=0` + `autofocus` + explicit `focus({preventScroll})` | canvas-game practice |

### Dev-safety carve-outs (important)
Aggressive key capture is **gated behind canvas focus** and explicitly does NOT
intercept: **F12**, **Cmd/Ctrl+R** (reload), **Cmd+Alt+I/J** and
**Cmd/Ctrl+Shift+I/J/C** (devtools). This keeps normal dev inspection/reload
working while the app is focused. `touch-action:none` is the intended trade-off
for a native app that owns raw pointer input; the kiosk guide notes it disables
browser scroll optimisations and pinch-to-zoom accessibility - acceptable here
because Blender is the input consumer.

## Verification/gate contract - PRESERVED

- `?pyexpr=` / `window.__BW_PYEXPR` and `?args=` / `window.__BW_ARGS` behave
  exactly as before (appended to boot argv, pyexpr last).
- `window.__bwModule` is set after `createBlenderModule` resolves.
- `?gate=WxH` (e.g. `?gate=1280x720`): canvas at EXACTLY that CSS+backing size,
  DPR forced to 1 (deviceScaleFactor-independent), centred on black, no loading
  UI once booted. Verified under deviceScaleFactor 2: `canvas.width/height` and
  `toDataURL` bitmap are exactly 1280×720.
- The DOM-visible **"main loop (WM_main)"** state marker is still emitted (the
  hidden `#state` element), so existing `waitForFunction` rigs still match.

## Verified (headed Playwright, bundled chromium-1228, port 8126)
`platform_web/shell/evidence/verify-native.mjs` run → **16/16 checks passed**:
instant black page, `overflow:hidden`, loader shown then dismissed, no visible
Boot button, WM_main marker, `window.__bwModule` present, 2880×1800 DPR backing +
full-window CSS, no page scroll on Space/arrows/Tab, `contextmenu` defaultPrevented,
gate 1280×720 exact (backing + CSS + `toDataURL`), gate centred, gate loader gone.
Evidence PNGs: `m4-shell-native-01-loading-black.png` (black + pulse + "6%" bar),
`-02-fullwindow-dpr2.png`, `-03-gate-1280x720.png`, `-04-rightclick-blender-menu.png`.

## Residual gaps / follow-ups (NOT hacked around - for later owners)

1. **UI is tiny at DPR ≥ 2 (GHOST DPI hook).** The backing store is now
   `css × DPR`, but `GHOST_WindowWeb.cc:34` `ghost_web_device_pixel_ratio()`
   returns **1.0 on the WM worker** (the worker has no `window`), so Blender's
   `U.pixelsize`/UI scale stays 1 while the surface is 2× - the UI renders at
   half physical size on a Retina display. FIX (GHOST, read-only for this lane):
   forward the real `devicePixelRatio` from the main thread to the worker and
   feed it to `getNativePixelSize`/DPI so `pixelsize` tracks DPR. Until then, the
   canvas is SHARP (primary deliverable) but the chrome is small at high DPR.
2. **Live window-resize does not grow the backing store.** After boot the canvas
   is an OffscreenCanvas owned by the WM worker; resizing it must be initiated
   from that worker. This build's `blender_browser.js` exposes **neither `ccall`
   nor `_emscripten_set_canvas_element_size` on the Module object** (confirmed by
   grep), so the shell cannot proxy a resize from the main thread. `boot-windowed.js`
   attempts it best-effort and, finding no export, logs once and degrades to CSS
   stretch (the canvas still fills the window, but at the boot-time backing
   resolution until reload). FIX (GHOST worker-side): have `on_resize` call
   `emscripten_set_canvas_element_size(selector, innerW*dpr, innerH*dpr)` before
   `reconfigureSurface()`, OR export `emscripten_set_canvas_element_size` +
   `ccall` from the build. Initial full-window DPR sizing is unaffected (works).
3. **`presentBackbuffer` first-pixels signal not observed on the main thread** in
   this build; the loader uses the WM_main+settle fallback. If a worker→main
   stdout route lands later, the `presentBackbuffer` scan will take over with no
   shell change.
4. **Canvas content is the M4 GPU state**, not the shell's: programmatic capture
   (`toDataURL` / Playwright screenshot) of the WebGPU OffscreenCanvas returns the
   known blank/uniform-clear (r24/r25 readback-zero + viewport-interior blocker).
   Right-click definitively kills the browser menu and reaches GHOST; visual
   confirmation of Blender's own menu is blocked by that separate M4 issue.
