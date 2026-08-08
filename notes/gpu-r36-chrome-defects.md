<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# r36 chrome-defects - two r34-mapped residuals RE-ROOT-CAUSED with live evidence

Pin: Blender 5.2 `fbe6228777e7`. Builds probed: `build-wasm-windowed-opt` (relinked
2026-08-08 11:04) and `build-wasm-windowed` (r34's, 2026-08-08 10:06). Rig: headed
node-Playwright + bundled Chromium, `?gate=1600x900` (DPR 1), `?pyexpr=` probes with
`os.write(2, …)` reaching the console (python `print()` does NOT). Port 8129.

**Headline: BOTH r34-mapped "chrome" defects on this lane's surface are GPU-backend
seams (`source/blender/gpu/webgpu/**`), which are FENCED for this lane (r35/r37 own
them). Zero fix attempts spent (0/5). No upstream/asset edits landed - the honest
outcome is the falsification + two precise seams below.**

The r36 opt-build capture is BYTE-IDENTICAL to r34's debug capture
(md5 `700245836bdc95d71a6ccbd05b4aece9`, 163469 px / 11.4% over 0.016, mean 0.00873744,
max 0.996). The output is build-independent (opt == debug, byte for byte).

---

## DEFECT 1 - r34's "asset shelf visible (56.9%)" is FALSIFIED. The band is a
## VIEWPORT-RENDER bottom-strip alpha artifact, not a region-visibility bug.

r34 INFERRED the asset shelf from source + pixels and explicitly noted it could not dump
bpy state ("print does not reach the browser console"). A direct `os.write(2,…)` probe
overturns that inference:

- Active window: **workspace = Layout, screen = Layout** (the captured state).
- `SpaceView3D.show_region_asset_shelf = **False**`; the `RGN_TYPE_ASSET_SHELF` region is
  **winx/winy = 1** (collapsed / hidden) - byte-identical to the native oracle
  (`--factory-startup` dump: `ASSET_SHELF w=1 h=1`).
- `show_region_asset_shelf` is **read-only** in this context, because the region carries
  `RGN_FLAG_POLL_FAILED` (no asset-shelf type is active in Object Mode / Layout;
  `asset::shelf::regions_poll` → `asset_shelf_space_poll` fails). So r34's own "toggle
  `show_region_asset_shelf = False`" test actually threw `AttributeError` (their print
  never surfaced it) - "byte-identical" only meant "the failed set did nothing."
- Source proof it CANNOT draw: `region_evaluate_visibility` (area.cc:2034) sets
  `runtime->visible = false` for `RGN_FLAG_HIDDEN | RGN_FLAG_POLL_FAILED`, and every
  blit/blend loop in `wm_draw_window_onscreen` (wm_draw.cc:1138/1179) skips
  `!runtime->visible`. Only Sculpting / Texture-Paint workspaces expand the shelf
  (`h=59`, correct native behavior - brush shelf).

**What the band actually is** (evidence: `artifacts/residual_r36_bottom_band_not_shelf.png`):
a full-width, uniform **+7.8/255** plateau over the viewport bottom, top-origin
y≈745-800 with a soft ramp y≈715-745 (bottom-origin y≈100-155). Top 660 rows match
native to <0.3/255. The grid draws OVER it, so it lives at the background layer.
Column profile (x150-350), WEB vs GOLD: y660 63.7/63.7 → y745 71.4/63.6 → y775 71.3/63.4.

Mechanism: `overlay_background_frag.glsl` composites the viewport background as
"alpha-under": `frag_color = float4(bg_col,1) * (1 - alpha)`, where
`alpha = texture(color_buffer, screen_uv).a` and `color_buffer = res.color_render_tx`
(the workbench/DRW render). 71 = 63·(1-alpha) ⇒ **alpha ≈ -0.13** in the bottom strip -
i.e. `color_render_tx.a` is stale/negative in the bottom ~59-85 px instead of 0. The
strip height ≈ the asset-shelf prefsize (`region_prefsizey ≈ 59 px`), which is a red
herring: it is the DRW offscreen render target's bottom rows carrying wrong alpha, not a
reserved region. Same shader compiled for native (correct) and web (wrong) ⇒ the
divergence is the WebGPU backend's render-target CLEAR / load-store (patch 0110 domain)
or a DRW-render viewport-Y in the offscreen viewport pass.

**SEAM (for r35/r37):** `color_render_tx` (viewport offscreen color target) has non-zero
(negative) alpha in its bottom ~59-85 px after the workbench/overlay render. Read it back
with the 0117 diag path at the overlay-Background submit to confirm which rows are
unwritten, then fix the clear/load-store of that target (or the render viewport rect) in
`source/blender/gpu/webgpu/` (candidates: wgpu_framebuffer.cc load-store 0110,
wgpu_context viewport). NOT a region/asset-shelf fix - the golden is correct, the shelf
is correctly hidden.

## DEFECT 2 - timeline current-frame indicator MISSING = window-direct overlay geometry
## dropped against the window backbuffer (GPU present/origin-flip seam).

Evidence: `artifacts/residual_r36_timeline_curframe_missing.png` (web | gold). The blue
playhead box + frame number + stalk line + tip are absent in web; the frame ruler
(12/24/36…) and the "Playback" dropdown render fine. Moving the current frame to 30
(mid-timeline, unclipped) still shows NO blue anywhere - a full-column scan finds only
grayscale (R=G=B); the indicator is not flipped-elsewhere, it is simply not in the output.
(Gold blue box: R49 G65 B90.)

Draw path: `action_main_region_draw_overlay` → `ED_time_scrub_draw_current_frame` →
`draw_playhead_box/stalk/tip` (time_scrub_ui.cc). This runs in the region `draw_overlay`
callback, executed by `wm_region_draw_overlay` (wm_draw.cc:~1150) as **window-direct**
geometry: `wmViewport(&region->winrct)` then draws straight to the WINDOW BACKBUFFER
(the persistent offscreen backbuffer adopted by patch 0109), AFTER the region blits.

The box uses `GPU_SHADER_2D_WIDGET_BASE` - the SAME shader as the "Playback" dropdown,
which renders when drawn to an OFFSCREEN region buffer. So the shader/data/coords are
fine; the failure is specific to window-direct geometry against the window backbuffer.
This is the exact domain of patch **0115** (`wgpu_framebuffer.cc`, window-backbuffer blit
origin flip): region BLITS were flipped to composite upright, but the window-direct
overlay draw viewport (`wmViewport(region->winrct)` into the same backbuffer) was not made
consistent, so overlay geometry lands off-target / clipped and produces nothing.

**SEAM (for r35/r37):** window-direct geometry draws (region `draw_overlay` /
`wm_paintcursor_draw`) against the window backbuffer are dropped/mis-viewported while
textured-quad blits (0098) and overlap blends (0115) to the same backbuffer work. Make the
overlay-draw viewport/scissor origin consistent with the 0115 blit flip in
`source/blender/gpu/webgpu/` (+ possibly `platform_web/ghost` presentBackbuffer). Verify
with the timeline current-frame box and any paint cursor.

---

## DO-NOT-RE-RUN (settled; don't re-litigate without NEW evidence)

1. **Asset shelf is NOT visible in web.** Layout shelf is `POLL_FAILED` + `winx/winy=1`,
   `show_region_asset_shelf=False` (read-only), identical to native. Do not "hide the
   shelf" - it is already hidden; a region-visibility / startup.blend / versioning fix is
   the WRONG tree. r34's 56.9% attribution is retired.
2. `show_region_asset_shelf` is READ-ONLY in Object Mode/Layout (poll fails). Setting it
   via bpy throws `AttributeError` - do not use it as a toggle probe here.
3. opt vs debug build produce a BYTE-IDENTICAL 1600x900 parity image
   (md5 700245836bdc95d71a6ccbd05b4aece9). Re-capturing on the other build is pointless.
4. Both defects are GPU-backend (`gpu/webgpu`), NOT editors/screen or wm_draw C++ (that
   path is identical native/web). Do not patch wm_draw / area.cc / space_action for these.
5. The `overlay_background_frag.glsl` shader is correct (native renders it correctly);
   do NOT clamp alpha there as a band-aid - fix the render-target content in the backend.

## Re-run (probe, this lane's port 8129)

```
BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed-opt/bin bash scripts/serve-web.sh 8129 &
# region-flag probe (os.write reaches console; print does not):
#   pyexpr walks bpy.data.screens VIEW_3D areas, dumps show_region_asset_shelf + region winx/winy.
# capture + compare (VERBATIM thresholds, unchanged):
NODE_PATH=/Users/paws/plushly/game-platform/node_modules node sandbox/m4-fullscreen-parity/capture_web.mjs 1600x900 8129 60000
bash sandbox/m4-fullscreen-parity/compare_fullscreen.sh sandbox/m4-fullscreen-parity/artifacts/web_1600x900.png workspace 1600x900
```
