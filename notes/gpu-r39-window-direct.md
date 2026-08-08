<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# r39 window-direct / viewport-edge - ONE root cause, four defects, one patch (0121)

Pin: Blender 5.2 `fbe6228777e7`. Build: `build-wasm-windowed-opt` (relinked fix-only
2026-08-08 ~16:48) + `build-native-gpu` (rebuilt). Rig: headed node-Playwright, bundled
Chromium, `NODE_PATH=/Users/paws/plushly/game-platform/node_modules`, port **8123**,
`?gate=1600x900` (DPR 1), `?pyexpr=` + BW_DIAG (patch 0117 readback). Drivers:
`sandbox/gpu-r39/disc_dtxl.mjs`.

## HEADLINE

The r36/r37 "window-direct / viewport-edge" family was **one** backend defect: the WebGPU
single-pass and immediate DRAW paths never applied SetViewport/SetScissorRect. The Vulkan
backend this was ported from DOES (`vk_framebuffer.cc` `vk_viewports_append` /
`render_area_update`); the port dropped it. For region content that is normally rendered
into a **region-sized offscreen** (viewport == whole target) this is harmless, so it went
unnoticed. But `wm_draw_window_onscreen` draws region overlays
(`wm_region_draw_overlay` -> `ED_*_draw_overlay`) and paint cursors **STRAIGHT to the
window backbuffer** with a region sub-rect set by `wmViewport(region->winrct)` /
`GPU_scissor`. With no viewport applied, that region-local geometry was transformed against
the FULL window and landed off-target / unconfined.

**Patch 0121** (`wgpu_framebuffer.cc` `begin_load_pass`) applies the frontend
viewport/scissor for the **window backbuffer only**, converting the stored GL bottom-origin
Y to the WebGPU top-origin backbuffer with the same flip as the 0115 blit
(`y' = H - (y + h)`). Offscreen targets and the native/headless gpu gate (no window
backbuffer, `is_window_backbuffer` false) keep the whole-target default untouched -> the
fix is **inert on native**, so the census cannot regress from it.

Whole-window parity **11.0% -> 2.19%** (31,468 px over 0.016; mean 0.00874->0.00428). ONE
fix attempt of five spent.

## Per-defect discriminator outcome + status

### DEFECT A - viewport bottom band (+7.8/255 plateau, ~90k px). FIXED. r36 root cause FALSIFIED.
r36 hypothesised the band was `color_render_tx` (`dtxl_color`, the RGBA16F viewport render
target) carrying **stale/negative alpha (~-0.13)** in its bottom ~59-85 px, surfaced by the
overlay Background alpha-under blend (`frag_color = bg_col * (1 - alpha)`).

**Discriminator (BW_DIAG dtxl_color readback, `disc_dtxl.mjs` -> `r39-dtxl.result.json`):**
dumped the ALPHA channel of `dtxl_color` (1311x787, RGBA16Float) directly at the workbench
render. Result: **every bottom row reads alpha = 0.0** (negRows-below-(-0.02) = 0,
minAlpha = 0.0 at row 0; bottom 20 rows all 0.0; only the cube band mid-texture is
non-zero). The texture does NOT carry negative alpha. r36's hypothesis is **falsified**.

The band was the SAME window-direct defect: an unconfined window-direct overlay draw
(timeline region draw_overlay area, transformed against the full window instead of its
`winrct`) painted the low-value plateau over the viewport bottom. Since patch 0121 touches
only window-direct draws and never `dtxl_color`, and the band is gone, it cannot have been a
`dtxl_color` alpha problem. Post-fix the y740-810 strip is **0.129%** over 0.016 (was a
uniform plateau); mean 0.00087. Do NOT clamp alpha in `overlay_background_frag.glsl` (r36's
own "do not band-aid" note stands, for the right reason now).

### DEFECT B - timeline current-frame indicator missing. FIXED (acceptance test).
`ED_time_scrub_draw_current_frame` draws window-direct via `wmViewport(region->winrct)`.
Post-0121 the blue playhead box + "1" render at frame 1, matching native
(`sandbox/gpu-r39/tlfull_stack.png`: gold top, web bottom, box present at left of ruler).

### DEFECT C - blue spike (x~95, lower-left, since r27). FIXED.
r37 predicted "same window-direct origin family; expect fixing B to move or kill it."
Confirmed killed: the spike region (x60-170, y150-380) is **0 px (0%)** over 0.016 post-fix
(was a bright fusiform y~180-360). No separate chase needed.

### DEFECT D - toolbar-left region-overlap. NOT in this family; left (opportunistic).
Toolbar region 4.01%; the seam column and tool-icon strip diff (max error 0.83 at an icon
pixel, `sandbox/gpu-r39/seam_stack.png`) is icon/SDF + AA, not a mis-viewported
window-direct draw (the toolbar is an offscreen region + overlap blend, unaffected by 0121).
Handoff: it is a region-overlap-blend / icon-render seam, a DIFFERENT root than 0121.

## Final region numbers (VERBATIM 0.016 / failpercent 1, oiiotool unchanged)
| region | over 0.016 | note |
|---|---|---|
| topbar    1600x52   | 1.64% | AA glyph floor (tab/menu text) |
| toolbar   60x763    | 4.01% | Defect D residual (icon/SDF + seam), not in family |
| viewport  1262x763  | 2.10% | dominated by cube AgX/OCIO darkening (r38 lane, NOT gpu backend) |
| sidebar   278x763   | 0.00% | PASS |
| statusbar 1600x85   | 5.93% | AA glyph floor (timeline frame numbers + status text); playhead present |
| WHOLE 1600x900      | **2.19%** | 31,468 px; mean 0.00428 (was 11.0% / mean 0.00874) |

Remaining whole-window mass is now (a) the cube AgX/OCIO darkening (r38's colour-management
lane - display-space overlays match native) and (b) the cross-renderer AA glyph floor
(D-9's ~3.5% instrument floor), plus the Defect D toolbar seam. None are the window-direct
family.

## Census (unchanged by 0121; inert on native)
build-native-gpu blender_test: **149 PASS / 7 FAIL / 2 CRASH**, static_shaders **956/973**.
Only RED = the known human-flagged I10 un-defer candidate
(`vertex_buffer_fetch_mode__GPU_COMP_I10__GPU_FETCH_INT_TO_FLOAT_UNIT`, run.sh EXPECT map,
harness out of fence). No other regression.

## DO-NOT-RE-RUN (r39; earlier lists still stand)
1. The window-direct family (bottom band A / timeline indicator B / blue spike C) is ONE
   defect: viewport/scissor never applied for window-backbuffer draws. FIXED (0121). Do NOT
   re-investigate the overlay Background shader, `dtxl_color` clear/load-store (0110), or a
   DRW render viewport-Y for the band - the texture alpha was proven CLEAN (bottom rows
   0.0); the band was window-direct.
2. `color_render_tx` / `dtxl_color` does NOT carry negative alpha. r36's alpha-under
   inference is retired. Do not clamp alpha in `overlay_background_frag.glsl`.
3. Do NOT apply viewport/scissor to offscreen targets - region offscreens are region-sized
   (viewport == whole target); applying it there is a no-op at best and risks regressing the
   gpu gate. 0121 gates on `is_window_backbuffer` for exactly this reason.
4. The window-direct flip is `y' = H - (y + h)` (GL bottom-origin -> WebGPU top-origin),
   the SAME as the 0115 blit flip, because the backbuffer is presented 1:1 upright
   (`GHOST_ContextWGPUWeb::presentBackbuffer`, `flip_y = false` for the backbuffer). Do not
   add a second flip.
5. Defect D (toolbar overlap seam) is NOT in this family; it is a region-overlap-blend /
   icon-render seam. Do not fold it into a window-direct viewport fix.

## Evidence (sandbox/gpu-r39/, + .license CC0-1.0)
`disc_dtxl.mjs`; `r39-dtxl.result.json` (dtxl_color alpha rows = 0.0); `r39-dtxl.all.log`;
`composite_bfix.png` (native|web|diffx3); `tlfull_stack.png` (timeline box present);
`heat_bottom.png` (bottom-strip residual = AA glyphs only); `seam_stack.png` (Defect D);
`web_1600x900_r39_fix.png` (final capture). Patch:
`patches/0121-gpu-webgpu-window-direct-viewport-scissor.patch`.
