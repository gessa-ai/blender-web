<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 GHOST-side live resize + devicePixelRatio (ghost-web lane) — LANDED + VERIFIED

Fixes the two windowed-boot defects the shell-native lane characterised but could
only fix GHOST-side, PLUS the definitive root-cause of the full-window chrome
Y-inversion (which is NOT this lane's — see the last section).

1. **Live window resize -> black bars / blurry downscale.** Post-boot the `#canvas`
   is a worker-owned OffscreenCanvas; the main thread cannot grow its backing store,
   so the shell could only CSS-stretch (blur) or letterbox. FIXED GHOST-side.
2. **UI tiny at DPR >= 2.** `ghost_web_device_pixel_ratio()` returned 1.0 on the WM
   worker (no `window` there), so `U.pixelsize` stayed 1 while the backing store was
   2x. FIXED by forwarding the real DPR and reporting it through GHOST the macOS way.

## Verification binary (fresh, from committed HEAD)

`build-wasm-windowed/bin/blender_browser.wasm` **wasm@2026-08-07T19:21:43-0400**
(926288376 bytes), rebuilt clean from committed HEAD `8dedfe6` (which includes this
lane's `79941b4`). NB: to build in a bare shell set `EMSDK_PYTHON` to the emsdk's
bundled interpreter — `tools/emsdk/python/3.13.3_64bit/bin/python3` — otherwise `em++`
falls back to `/usr/bin/python3` (Xcode 3.9.6) and aborts with "emscripten requires
python 3.10 or above". This is a per-shell env fact, not a harness or code defect.
Export `_bw_shell_set_display` confirmed present + reachable.

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
  the new extent), and posts `GHOST_kEventWindowSize`. That size event makes the WM relayout
  AND recompute the UI scale (`wm_window.cc` GHOST_kEventWindowSize -> `WM_window_dpi_set_userdef`).

### DPR model - mirrors macOS Cocoa exactly

`WM_window_dpi_set_userdef` does `auto_dpi = getDPIHint(); auto_dpi *= getNativePixelSize();`
On macOS `getDPIHint()` is the base constant **96** and `getNativePixelSize()` is the backing
scale (== DPR). So GHOST_WindowWeb: `getNativePixelSize()` -> DPR, `getDPIHint()` -> 96,
`getClientBounds()` -> logical (backing / DPR).

**Composite unit-safety at DPR>1 (verified by code trace, closes the shell-native worry).**
Blender lays out the screen/regions from `WM_window_rect_calc` ->
`WM_window_native_pixel_size(win)` = `getClientBounds_logical * getNativePixelSize()` =
`sizex_logical * DPR` = the PHYSICAL backing extent (upstream/source/blender/windowmanager/
intern/wm_window.cc:3121-3126, screen_geometry.cc:255). So every `ARegion.winrct` is in
PHYSICAL device pixels — the SAME units as the window back-buffer texture (my `backbuffer_`,
sized to the canvas backing = physical). Splitting getClientBounds into logical + DPR-as-
nativePixelSize therefore reconstructs the exact physical layout the renderer needs; the
logical getClientBounds change is composite-safe at any DPR. At **DPR 1 the whole change set
is the mathematical identity**, so the golden/gate path is byte-identical.

## Files

- `platform_web/ghost/GHOST_WebDisplayState.hh` (new) - handshake accessor declarations.
- `platform_web/ghost/GHOST_SystemWeb.cc` - atomics + `bw_shell_set_display` KEEPALIVE export +
  `ghost_web::` accessors + the resize poll in `processEvents` (bounded diagnostic printf).
- `platform_web/ghost/GHOST_WindowWeb.{cc,hh}` - getNativePixelSize/getDPIHint/getClientBounds
  + setClient* logical<->backing scaling.
- `platform_web/shell/boot-windowed.js` - `pushDisplayToWorker` via the export; preRun DPR seed;
  post-resolve re-push; resize/ResizeObserver/media-query wiring.

## Verification verdicts (headed Playwright, bundled Chromium, port 8128, wasm@19:21:43)

`platform_web/shell/evidence/verify-resize-dpr.mjs` -> **10/10 checks passed** on the fresh
binary. Blender-internal state read via a `?pyexpr` snapshot written to WasmFS and read back
through `Module.FS`.

- **Bug #2 - DPR-2 UI scale: FIXED.** DPR2 1440x900 -> `win=1440x900` (logical), `pixel_size=2.000`,
  `dpi=144`, `ui_scale=2.000`. Native 2x UI.
- **DPR-1 no regression:** DPR1 1280x720 -> `win=1280x720`, `pixel_size=1.000`. Unchanged.
- **Bug #1 - live resize: FIXED.** Resize 1440x900 -> 1000x700 @ DPR2 logged
  `WGPUWeb-resize: backing -> 2000x1400 (canvas readback 2000x1400, dpr 2.000)` - the
  OffscreenCanvas backing grew to exactly `cssPx * DPR`, surface reconfigured, WindowSize
  delivered. Canvas CSS box == window (`{w:1000,h:700,iw:1000,ih:700}`) -> no letterbox +
  backing==cssPx*DPR -> no blur.
- **?gate=WxH regression: PASS.** `?gate=1280x720` under deviceScaleFactor 2 -> canvas backing
  EXACTLY 1280x720, `bw-gate` layout, loader gone, Blender sees `win=1280x720 pixel_size=1.000`
  (DPR forced 1). Gate contract intact.

Evidence PNGs (regenerated on wasm@19:21:43): `m4-ghost-resize-01-dpr2-1440x900.png`,
`-02-dpr2-resized-1000x700.png`, `-03-dpr1-1280x720.png`, `-04-gate-1280x720.png`
(01/02/03/04 page.screenshots read blank - the known M4 OffscreenCanvas readback blocker for
programmatic capture; the substantive proof is the bpy-state numbers above).

## Full-window CHROME Y-INVERSION — root-caused. NOT this lane. r28b's patch 0098.

`platform_web/shell/evidence/m4-ghost-inversion-1600x900-wasm19-21.png` (a REAL rendered frame
via the parity-lane pyexpr-kick, gate 1600x900, wasm@19:21:43) reproduces the inversion:
the GLOBAL top-bar (File/Edit/Render/Window/Help + workspace tabs + Scene/ViewLayer) composites
at the window BOTTOM; the 3D viewport header at the top; on the right rail Properties sits ABOVE
the Outliner. Every strip's TEXT is upright/readable and the 3D viewport (grid, world axes, cube
outline, camera, nav-gizmo ball) is upright and correctly placed. Signature: **chrome region
PLACEMENT vertically mirrored, all content upright, 3D viewport correct.**

### Root cause (definitive, code + pixels)

The WM composites each non-viewport region's offscreen onto the window back-buffer via
`GPU_offscreen_draw_to_screen(ofs, region->winrct.xmin, region->winrct.ymin)`
(wm_draw.cc:841) -> `FrameBuffer::blit_to(..., dst_offset_x=winrct.xmin, dst_offset_y=winrct.ymin)`
(gpu_framebuffer.cc:840). `winrct` is GL **bottom-origin**. Because the region offscreen is
RGBA8 and the window back-buffer is BGRA8, `WGPUFrameBuffer::blit_to` takes the cross-format
fallback `WGPUContext::blit_color_render(..., dst_x, dst_y)`, which does:

    pass.SetViewport(float(dst_x), float(dst_y), float(w), float(h), 0, 1);   // wgpu_context.cc:420
    pass.SetScissorRect(dst_x, dst_y, w, h);                                  // wgpu_context.cc:421

using the bottom-origin `dst_y` (= `winrct.ymin`) DIRECTLY as a WebGPU **top-origin** viewport/
scissor origin. The `dst_y' = dst_fb_height - dst_y - h` conversion is MISSING, so every chrome
region lands at the exact vertical mirror of its true position (topbar@bottom, statusbar@top,
properties<->outliner). This is a pure mirror (`raw = H - correct - h`), hence DPR- AND
size-independent — it reproduces in `?gate` at DPR 1 (where this ghost lane is the identity) and
at both 1600x900 and 1280x720.

The 3D VIEWPORT is correct because it takes a DIFFERENT path: `GPU_viewport_draw_to_screen` ->
`gpu_viewport_draw_colormanaged` (a shader-quad DRAW through the normal batch/immediate path,
`flip_y=!is_window_backbuffer` = false = upright), not `blit_to`. Only the `blit_color_render`
composite of the chrome regions is mirrored.

### Ownership + fix (for r28b — do NOT edit from this lane)

Lives entirely in **patch `0098-gpu-webgpu-cross-format-region-blit.patch`** (committed 6605e98,
"M4 gpu round 18 / M4.T15"), files `upstream/source/blender/gpu/webgpu/wgpu_framebuffer.cc`
(`blit_to`) + `wgpu_context.cc` (`blit_color_render`) — r28b's owned surface right now. NOT this
lane's files. NOT introduced by 79941b4 (ghost resize/DPR, identity at DPR 1) nor 2294a89 (shell
full-window sizing, a pure mirror is size-independent). It became VISIBLE in r28 only because the
r27->r28 IBO/bind fixes (patches 0112/0113/0114) made the chrome region offscreens render
non-empty content, which then began compositing through the pre-existing (round-18) buggy blit.

Suggested fix (r28b), no magic constants — the destination framebuffer height is already in hand
as `ds[1]` in `blit_to`; convert the offset to top-origin before the cross-format call, gated on
`is_window_backbuffer(dst)` so offscreen-to-offscreen blits keep their convention:

    if (sfmt != dfmt) {
      int dy = int(dst_offset_y);
      if (ctx->is_window_backbuffer(dst_fb)) {          // top-origin upright target (M4.T14a)
        dy = int(ds[1]) - int(dst_offset_y) - int(h);   // GL bottom-origin -> WebGPU top-origin
      }
      ctx->blit_color_render(stex, dtex, w, h, uint32_t(dst_offset_x), uint32_t(std::max(dy, 0)));
      return;
    }

Content orientation (the `uv.y = y` tuning already in `blit_color_render`) is UNAFFECTED — the
fix only repositions the viewport rect; the region content stays upright. Both `SetViewport` and
`SetScissorRect` consume the same converted `dst_y`, so no second edit is needed.

## Parity number on the fresh binary (inversion still present)

`sandbox/m4-fullscreen-parity` re-run (wasm@19:21:43, gate 1600x900):
**FAIL 74.5% over 0.016** (max 0.906, mean 0.0464), SELFTEST_PASS. Per-region: topbar 21.6%,
toolbar 60.8%, viewport 83.7%, sidebar 61.7%, statusbar 66.2%. Improved from the REPORT's 84.6%
baseline purely from the committed r28a IBO/bind fixes in the fresh binary (cube outline etc.),
NOT from the inversion — the chrome regions still fail hard (60-66%), consistent with the mirror
still present. The number will drop materially further once r28b lands the `dst_y` flip above.

## Residuals / follow-ups

1. **Chrome Y-inversion** (above) — r28b patch 0098; ready-to-apply fix supplied. This lane's
   landing does not depend on or affect it.
2. **`WM_window_dpi_get_scale`** (wm_window.cc) is `OS_MAC`-gated -> returns 1 on wasm regardless
   of DPR; only scales the SOFTWARE cursor (rarely hit — hardware CSS cursor is used). Cosmetic;
   fixing needs an upstream patch (can't touch upstream from this lane).
3. **Programmatic capture of the WebGPU OffscreenCanvas** stays blank via `page.screenshot`/
   `toDataURL` for plain boots; the parity-lane pyexpr-kick method yields a real frame (used for
   the inversion evidence). Resize/DPR verification here is bpy-state based, so it is unaffected.
