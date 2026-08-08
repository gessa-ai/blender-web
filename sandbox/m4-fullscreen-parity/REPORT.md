<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# M4-fullscreen-parity - full-window native-vs-web comparison (r34, 2026-08-08)

Honest 1:1 comparison of the ENTIRE Blender window (topbar, toolbar, 3D viewport,
sidebar, status bar) between the WEB build and the NATIVE 5.2.0 oracle at an
identical 1600x900, with Blender's own tier-c thresholds (oiiotool `--fail 0.016
--failpercent 1 --diff`, NEVER weakened).

## Verdict: FAIL - 11.4% of pixels over 0.016 (max 0.996, mean 0.0087)

```
bash sandbox/m4-fullscreen-parity/compare_fullscreen.sh \
  sandbox/m4-fullscreen-parity/artifacts/web_1600x900.png workspace 1600x900
FAIL workspace_1600x900  Max error = 0.9960784912109375  Mean error = 0.00873744 | 163469 pixels (11.4%) over 0.016   (exit 1)
```

Trend (whole-window % over 0.016): **84.6 -> 74.5 -> 60.2 -> 11.4 (r33 solid-cube
fix) -> 11.4 (r34, reproduced on HEAD; no regression, no new fix landed) -> 11.4
(r36, opt build BYTE-IDENTICAL to r34's debug capture, md5
`700245836bdc95d71a6ccbd05b4aece9`; two residuals RE-ROOT-CAUSED, no fix landed -
both are GPU-backend seams outside the r36 non-GPU fence, handed to r35/r37)**. r34
reproduced r33 byte-for-byte on the current HEAD tree (`upstream/` clean, windowed
wasm relinked 2026-08-08 10:06) then ENUMERATED + ROOT-CAUSED the residuals per
cluster (below). SELFTEST_PASS every run (identity PASS + perturbed(+0.1) FAIL).

**r36 CORRECTION (2026-08-08, evidence-first, `os.write(2,…)` bpy probes):** cluster 1's
"asset shelf visible" attribution is **FALSIFIED**, and cluster 5's timeline indicator is
**localized to a GPU seam**. See the two amended clusters below and
`notes/gpu-r36-chrome-defects.md`. Neither is a region-visibility / startup.blend /
wm_draw C++ fix; both roots live in `source/blender/gpu/webgpu/**` (r35/r37). No fix
landed on this lane (0/5 attempts; the honest outcome is the falsification + two seams).

Side-by-side (native | web | inferno diff-heatmap):
`sandbox/m4-fullscreen-parity/artifacts/sidebyside_workspace_1600x900.png`.
Per-cluster crops: `artifacts/residual_r34_{bottom_band_assetshelf,left_edge_spike,cube_shading}.png`.

## Gate reachability (honest): NOT reachable at 0.016/failpercent1 via web-side fixes

The gate needs <1% of pixels over 0.016. The failing mass decomposes as:

| cluster                                   | failing px | share |
|-------------------------------------------|-----------:|------:|
| viewport bottom band (asset-shelf region) |     92,960 | 56.9% |
| chrome text/icons AA (all 4 bars)         |    ~43,884 | 26.8% |
| cube workbench shading (too dark)         |     15,866 |  9.7% |
| left-edge toolbar shadow + "blue spike"   |     ~3,000 |  1.8% |
| nav-gizmo ball (AA/pos)                    |      2,019 |  1.2% |
| misc (origin dot, gizmo/grid AA)          |     ~5,700 |  3.5% |
| **WHOLE**                                 |**163,469** |**100%**|

Even if every GEOMETRIC/region cluster were fixed (~113k px), the residual floor is
**~50k px = ~3.5%**, dominated by cross-renderer antialiased TEXT/ICONS (native
Metal + system FreeType vs web WebGPU/Dawn + wasm FreeType rasterize glyph edges
with sub-pixel/blend differences exceeding 0.016 on edge pixels). Chrome text-AA
alone is ~3.0% and cannot be driven under 1% by any theme/backend fix. **The
full-window M4 gate at the verbatim 0.016/1 thresholds is therefore not
achievable**; the driver should scope the M4 gate to the 3D-viewport-interior
region (where the r33 cube fix already collapsed the dominant delta) or accept a
documented per-glyph-AA deferral. Thresholds UNCHANGED, golden UNTOUCHED (it is not
flawed - native correctly hides the asset shelf; see cluster 1).

## Golden provenance + determinism check

- Native oracle: `oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender`
  (Blender 5.2.0 LTS, Cocoa+Metal, pin `fbe6228777e7`), via the m4-golden-prep
  windowed screenshot method (`bpy.ops.screen.screenshot`, `show_splash=False`).
- Golden: `goldens/workspace_1600x900.png`, sha256
  `ab62e3f0c406acb503bb9d21ab8fcbb454b1d16e9baa85118a225336e166e697`, byte-identical
  across 4+ warm windowed processes. Only golden staged (no splash golden).
  (Comparator: oiiotool 3.1.16.0.)
- NOT flawed: the golden contains no transient (no hover tooltip, no stray cursor);
  its bottom viewport shows the default Layout with the asset shelf HIDDEN, the
  correct native default. The r33-era "hover tooltip" residual is GONE - it belonged
  to the old mirrored-chrome capture, not this one. No golden repair was needed.

## Web build measured

- Binary: `build-wasm-windowed/bin/blender_browser.{js,wasm,data}`, relinked
  2026-08-08 10:06, repo HEAD `d04b17e` (r33 verified; patch 0118 applied),
  `upstream/` clean at HEAD.
- Capture: headed bundled Chromium (Playwright), `?gate=1600x900` (DPR forced 1),
  `?pyexpr=` = `show_splash=False` + a 1 s VIEW_3D `region.tag_redraw()` kick timer,
  60 s settle, CDP screenshot clipped to `#canvas` = exactly 1600x900. Cursor rests
  off-canvas at viewport (0,0) (neutral; the canvas is centre-placed with a 50 px
  margin, so no hover state composites in).
- A diagnostic re-capture toggling the asset shelf via bpy `show_region_asset_shelf
  = False` was BYTE-IDENTICAL (bpy `print()` does not reach the browser console, and
  the toggle did not re-lay-out before capture), so the bottom band was root-caused
  from pixels + source (cluster 1) rather than from a bpy state dump.

## Per-region characterization

```
bash sandbox/m4-fullscreen-parity/compare_fullscreen.sh --regions \
  sandbox/m4-fullscreen-parity/artifacts/web_1600x900.png workspace 1600x900
```

| region     | rect (WxH+X+Y)     | verdict | % over 0.016 | mean err  |
|------------|--------------------|---------|--------------|-----------|
| topbar     | `1600x52+0+0`      | FAIL    | 1.64%        | 0.00466   |
| toolbar    | `60x763+0+52`      | FAIL    | 19.7%        | 0.0284    |
| viewport   | `1262x763+60+52`   | FAIL    | 12.4%        | 0.00781   |
| sidebar    | `278x763+1322+52`  | FAIL    | 8.93%        | 0.00782   |
| statusbar  | `1600x85+0+815`    | FAIL    | 10.7%        | 0.0126    |
| WHOLE      | `1600x900+0+0`     | FAIL    | 11.4%        | 0.00874   |

The viewport carries 119,585 of the 163,469 failing pixels (73%). Its empty
background and gradient MATCH native to within threshold (65.3 vs 65.4; a
cube-free/grid-only quadrant fails only 0.013%), so the viewport residual is
entirely discrete elements, enumerated below.

### Residual clusters (dominant to minor) - root-caused

1. **Viewport bottom band. 92,960 px, 56.9% of ALL failures - the #1 defect.**
   A full-width, uniform **+7.8/255** plateau over the viewport bottom (absolute y
   745-800, ramp y 715-745); grid lines show THROUGH it; rows 0-660 match native
   perfectly.
   **~~r34: the ASSET SHELF region rendered in web while native hides it.~~ FALSIFIED
   by r36 (direct `os.write(2,…)` bpy probe).** The active workspace is Layout, and
   its `RGN_TYPE_ASSET_SHELF` region is HIDDEN in web exactly as in native:
   `show_region_asset_shelf=False`, `winx/winy=1`, `RGN_FLAG_POLL_FAILED` set (poll
   fails in Object Mode → the RNA is even read-only). `region_evaluate_visibility`
   sets `runtime->visible=false`, so every blit/blend loop skips it - it CANNOT draw.
   (r34 inferred the shelf from source+pixels, unable to dump bpy state; its "toggle"
   test silently threw `AttributeError`.)
   **Actual root:** the viewport OFFSCREEN render target `color_render_tx` carries
   stale/negative alpha (≈ -0.13) in its bottom ~59-85 px, surfaced by the overlay
   Background alpha-under blend (`frag_color = bg_col*(1-alpha)`,
   `overlay_background_frag.glsl`). GPU-backend render-target CLEAR / load-store
   (patch 0110 domain) or DRW render viewport-Y. Evidence:
   `artifacts/residual_r36_bottom_band_not_shelf.png` (web|gold|diff x8).
   **Fix owner: r35/r37 (`source/blender/gpu/webgpu/**`)** - NOT editors/screen /
   region-ensure / startup.blend. See `notes/gpu-r36-chrome-defects.md`.

2. **Cube workbench solid-shading is too dark. ~15,866 px (viewport-interior
   headline).** Every cube face is 25-45% darker than native (native top/left/front
   ~109/136/126; web ~83/76/84) and the brightest face flips (native: left; web:
   front/top) - a studio-LIGHT direction/intensity delta, not a uniform gamma. The
   OVERLAY-drawn elements (background, grid, world axes, camera + light gizmos) all
   MATCH native, so this is isolated to the WORKBENCH solid-shading output, NOT
   color management/view-transform and NOT theme. The r33 stencil fix made the cube
   SOLID; its LIGHTING is the remaining delta. Evidence:
   `artifacts/residual_r34_cube_shading.png`. Fix owner: gpu/webgpu workbench
   studio-light UBO / matcap sampling (patches flow).

3. **Left viewport edge: toolbar region-overlap shadow + the pre-existing "blue
   spike". ~3,000 px.** The toolbar (left overlapping region) casts a dark edge fade
   into the viewport that native lacks (x 62-72 drops to ~28-37 vs native ~65; faint
   blue tint at the x=60 seam) - same overlapping-region class as cluster 1. Riding
   on it is a bright (~93/255) thin vertical gizmo-like bar with a central bulge at
   x~95, y~150-360 (the "blue spike"); its exact draw call still needs BW_DIAG on the
   overlay/gizmo pass. Evidence: `artifacts/residual_r34_left_edge_spike.png`.
   Sidebar-right and topbar-bottom edges are CLEAN (+1/255), so the overlap artifact
   is specific to the two visible overlapping regions of the 3D viewport
   (toolbar-left, asset-shelf-bottom).

4. **Navigation gizmo ball. 2,019 px.** Now RENDERS (colored X/Y/Z + hollow
   -X/-Y/-Z balls, correct layout); residual is sub-pixel AA/position/colour only.
   (The stale report's "gizmo ball absent" item is FIXED - dropped.)

5. **Chrome text + icons (topbar/toolbar/sidebar/statusbar). ~43,884 px, 26.8%.**
   Region FILLS are near-perfect (+1/255, within threshold: sidebar/topbar/statusbar
   backgrounds all exactly +1); the failures are cross-renderer antialiased TEXT and
   ICON edges - irreducible at 0.016 (see gate note). One real widget defect rides
   here: the timeline current-frame indicator (the blue frame box + number + stalk +
   tip) is MISSING in web.
   **r36 root-cause:** it is drawn WINDOW-DIRECT via the region `draw_overlay` callback
   (`action_main_region_draw_overlay` → `ED_time_scrub_draw_current_frame` →
   `draw_playhead_box/stalk/tip`), executed by `wm_region_draw_overlay` as geometry
   straight to the WINDOW BACKBUFFER (`wmViewport(region->winrct)`), after the region
   blits. The box uses `GPU_SHADER_2D_WIDGET_BASE` - the SAME shader as the "Playback"
   dropdown that renders fine when drawn to an OFFSCREEN region buffer - so the shader
   is fine; window-direct geometry against the window backbuffer is dropped. Same domain
   as patch 0115 (window-backbuffer blit origin flip): blits/blends to the backbuffer
   were origin-flipped, but the window-direct overlay draw viewport was not made
   consistent (probe: blue absent everywhere, not flipped-elsewhere; unclipped at
   frame 30 still absent). Evidence:
   `artifacts/residual_r36_timeline_curframe_missing.png` (web|gold).
   **Fix owner: r35/r37 (`source/blender/gpu/webgpu/**` + possibly `platform_web/ghost`
   presentBackbuffer)** - NOT a wm_draw / time_scrub_ui C++ fix. See
   `notes/gpu-r36-chrome-defects.md`.
   (The stale "chrome vertical mirror" and "menu-background inversion / solid-cube
   absent" items are FIXED - chrome is upright, fills match, the cube is solid;
   dropped.)

## Re-run (any lane, one command each)

```
# 1) web capture (serve on this lane's port 8129 first):
BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed/bin bash scripts/serve-web.sh 8129 &
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/m4-fullscreen-parity/capture_web.mjs 1600x900 8129 60000
# 2) verdict + side-by-side + per-region + teeth:
bash sandbox/m4-fullscreen-parity/compare_fullscreen.sh sandbox/m4-fullscreen-parity/artifacts/web_1600x900.png workspace 1600x900
bash sandbox/m4-fullscreen-parity/compare_fullscreen.sh --composite sandbox/m4-fullscreen-parity/artifacts/web_1600x900.png workspace 1600x900
bash sandbox/m4-fullscreen-parity/compare_fullscreen.sh --regions   sandbox/m4-fullscreen-parity/artifacts/web_1600x900.png workspace 1600x900
bash sandbox/m4-fullscreen-parity/compare_fullscreen.sh --selftest
# regenerate the native golden (opens a real window twice for the determinism check):
bash sandbox/m4-fullscreen-parity/capture_fullscreen_golden.sh
```

The M4 gate turns GREEN when this passes at 0.016/1 with the chrome upright, the
solid cube shaded, and the gizmo ball present - the last two are DONE. Today: FAIL
11.4%, dominated by the web-only asset-shelf bottom band (56.9%) and an irreducible
cross-renderer text-AA floor (~3%). See the gate-reachability note above.
