<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# M4-fullscreen-parity - full-window native-vs-web comparison (2026-08-07)

Honest 1:1 comparison of the ENTIRE Blender window (topbar, toolbar, 3D viewport,
sidebar, status bar) between the WEB build and the NATIVE 5.2.0 oracle at an
identical 1600x900, with Blender's own tier-c thresholds (oiiotool `--fail 0.016
--failpercent 1 --diff`, NEVER weakened).

## Verdict: FAIL - 84.6% of pixels over 0.016 (max 0.906, mean 0.050)

```
bash sandbox/m4-fullscreen-parity/compare_fullscreen.sh \
  sandbox/m4-fullscreen-parity/artifacts/web_1600x900.png workspace 1600x900
FAIL workspace_1600x900  Max error = 0.9058824  Mean error = 0.0497898 | 1218855 pixels (84.6%) over 0.016   (exit 1)
```

This FAIL is expected and correct: the web build is mid-flight (other lanes are
fixing the solid cube, gizmo ball, and menu backgrounds). This harness MEASURES
that work; it does not massage it. The comparator's teeth are proven every run:
`--selftest` = identity PASS + a deterministically perturbed copy (+0.1/channel)
FAIL, giving SELFTEST_PASS.

Side-by-side (native | web | inferno diff-heatmap):
`sandbox/m4-fullscreen-parity/artifacts/sidebyside_workspace_1600x900.png`.

## Golden provenance + determinism check

- Native oracle: `oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender`
  (Blender 5.2.0 LTS, Cocoa+Metal, pin `fbe6228777e7`) - the SAME binary the
  m4/m5/m6 goldens came from, via the m4-golden-prep windowed screenshot method
  (`bpy.ops.screen.screenshot`, splash suppressed with `show_splash=False`).
- Golden: `goldens/workspace_1600x900.png`, captured at the EXACT requested
  1600x900 (the 3024x1964 Retina host clamps content height ~1001px; 900 is within
  bounds - no clamp, unlike the m4-golden-prep 1800x1169 -> 1800x1001 case).
- Determinism: byte-identical PNG across independent windowed processes,
  sha256 `ab62e3f0c406acb503bb9d21ab8fcbb454b1d16e9baa85118a225336e166e697`,
  reproduced 4+ times. Delta source documented: the very FIRST cold-start capture
  in a fresh session differed (sha `78767eb2...`) but was threshold-identical
  (within 0.016/1) - a GPU/font/shader cold-cache warmup frame. Every WARM capture
  is byte-identical; the golden is the stable warm frame, not the cold outlier.
  (Comparator: oiiotool 3.1.16.0.)

## Web build measured

- Binary: `build-wasm-windowed/bin/blender_browser.{js,wasm,data}`, wasm built
  2026-08-07 17:25:32, repo HEAD `8f446a6` (r28 five-lane dispatch).
- Capture: headed bundled Chromium (Playwright), `?gate=1600x900` (DPR forced 1),
  `?pyexpr=` = `show_splash=False` + a 1 s VIEW_3D `region.tag_redraw()` kick timer,
  60 s settle, CDP screenshot clipped to the `#canvas` bbox = exactly 1600x900
  (`toDataURL` IHDR independently confirmed 1600x900). WM_main in 1.46 s;
  `presentBackbuffer` fired x2; no GPU validation errors during boot+settle
  (the 4 console lines were a favicon 404, a non-fatal OIIO `physical_memory`
  sysutil stub assertion, an informational WM-worker device-acquire line, and a
  `multiprocessing` warning - none touch the render).
- CROSS-CHECK (size-independence, independent golden): a clean same-rig 1280x720
  capture (`artifacts/web_1280x720.png`, against a later rebuild wasm@17:59) diffs
  82.1% over the PRE-EXISTING `m4-golden-prep` workspace_1280x720 golden
  (`bash sandbox/m4-golden-prep/compare_m4.sh artifacts/web_1280x720.png workspace
  1280x720` -> FAIL, max 0.906). Same chrome inversion + outline-only cube at a
  different size and against a golden a different lane cut: the deltas are
  size-independent and the harness reproduces. The binary is rebuilt every ~30 min
  by other lanes (it relinked again 21 s after this capture), so the 1600x900
  numbers above are pinned to wasm@17:25 / HEAD 8f446a6; re-run the one-liner below
  to measure whatever build is current.

## Per-region characterization

```
bash sandbox/m4-fullscreen-parity/compare_fullscreen.sh --regions \
  sandbox/m4-fullscreen-parity/artifacts/web_1600x900.png workspace 1600x900
```

| region     | rect (WxH+X+Y)     | verdict | % over 0.016 | mean err |
|------------|--------------------|---------|--------------|----------|
| topbar     | `1600x52+0+0`      | FAIL    | 35.6%        | 0.0535   |
| toolbar    | `60x763+0+52`      | FAIL    | 91.2%        | 0.0600   |
| viewport   | `1262x763+60+52`   | FAIL    | 93.5%        | 0.0371   |
| sidebar    | `278x763+1322+52`  | FAIL    | 81.5%        | 0.0841   |
| statusbar  | `1600x85+0+815`    | FAIL    | 54.7%        | 0.0808   |
| WHOLE      | `1600x900+0+0`     | FAIL    | 84.6%        | 0.0498   |

Rects are in native-layout coordinates; the diff at each rect measures whether the
web content at that position matches native there.

### What the deltas are (dominant to minor)

1. Full-window UI-chrome vertical mirror (dominant). In the web capture the
   topbar/menus (File/Edit + workspace tabs) composite at the BOTTOM and the
   status bar (Select / Pan View / Context Menu) at the TOP; on the right rail the
   properties editor sits ABOVE the outliner (native: outliner above properties).
   Because every chrome region lands at the mirror of its native position, the
   same-rect diff compares cross-content and every chrome region fails hard
   (toolbar 91.2%, sidebar 81.5%, statusbar 54.7%, topbar 35.6%). The last
   COMMITTED upright web evidence is r27 (`platform_web/shell/evidence/
   m4-r27-grid-axes-zero-errors-1280x720.png`, topbar at top); this mirror is new
   in the current r28-WIP binary. Root-causing the flip is another lane's work -
   this harness records it with numbers.
2. Missing solid cube shading (viewport headline gap). The web viewport draws
   only the crumpled orange SELECTION OUTLINE of the cube; native shows a solid
   shaded gray workbench cube. This is the largest viewport-interior contributor
   (viewport 93.5%). Grid, red/green world axes, the camera wireframe, and the
   light gizmo ARE present and correctly oriented - the viewport 3D CONTENT is
   upright (only the chrome is mirrored), and the cube geometry exists (outline).
3. Navigation gizmo ball absent. Native's colored XYZ orientation ball
   (top-right of the viewport) is missing on the web side - only faint Z/Y/X axis
   labels render.
4. Blue vertical spike artifact (lower-left of the viewport). A stray
   overlay/gizmo sliver; PRE-EXISTING - it is visible in the committed r27 evidence
   too, so it is not new to this capture.
5. Menu/panel backgrounds + a stray hover tooltip. Panel/header fills differ
   from native, and a properties-panel hover tooltip ("Disable in Renders / ...")
   composited into this capture (a transient hover state, not a persistent bug).

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

The M4 gate turns GREEN when this comparison passes at 0.016/1 with the chrome
upright, the solid cube shaded, and the gizmo ball present. Today: FAIL, 84.6%.
