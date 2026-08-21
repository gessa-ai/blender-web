<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# M4-fullscreen-parity - full-window native-vs-web 1:1 comparison harness

A repo-committable, full-window, honest 1:1 comparison between the **web** build
and the **installed native Blender 5.2.0** oracle: the ENTIRE Blender window
(topbar with File/Edit, left toolbar, 3D viewport with the shaded cube + grid +
gizmos, right sidebar with outliner + properties, status bar + timeline) captured
from BOTH sides at an IDENTICAL 1600x900 and diffed with the house comparator
(oiiotool `--fail 0.016 --failpercent 1 --diff` - Blender's own tier-c thresholds,
NEVER weakened).

This EXTENDS `sandbox/m4-golden-prep/` (the 1280x720 / 1800x1001 canvas method) to
a full-window WORKSPACE golden at 1600x900. The workspace state (splash suppressed)
is the whole window; the splash-only state and its config-class Language-row caveat
are avoided entirely here.

## Files

- `fullscreen_capture.py` - in-Blender `--python` driver (copied/extended from
  `m4-golden-prep/m4_capture.py`); captures via Blender's own
  `bpy.ops.screen.screenshot` (window framebuffer read, screendump.cc:70).
- `capture_fullscreen_golden.sh` - NATIVE side: windowed capture at 1600x900,
  captured TWICE in independent processes with a determinism receipt, staged into
  `goldens/` named by ACTUAL captured dims, with a CC0 `.license` sidecar and a
  `manifest.tsv` row.
- `capture_web.mjs` - WEB side: headed bundled-Chromium Playwright rig; boots the
  windowed wasm build in `?gate=1600x900` mode, drives the workspace render
  (`?pyexpr=` show_splash=False + a 1 s VIEW_3D `tag_redraw` kick timer), settles
  60 s, and CDP-captures the canvas at EXACTLY 1600x900. It derives the checkout
  from `import.meta.url`, accepts only Node 22.16.0 + Playwright 1.61.1, and has a
  browser-free `--selfcheck` mode.
- `compare_fullscreen.sh` - the comparator. Mirrors `m4-golden-prep/compare_m4.sh`
  verbatim on threshold discipline (exit-code primary, `--ch R,G,B` normalize,
  size mismatch = FAIL). Subcommands: default verdict, `--selftest` (identity PASS
  + perturbed FAIL), `--regions` (per-region % over threshold), `--composite`
  (native | web | inferno-heatmap side-by-side PNG).
- `goldens/workspace_1600x900.png` (+ `.license`) - the staged native golden.
- `artifacts/web_1600x900.png` (+ `.license`) - the web capture (today's build).
- `artifacts/sidebyside_workspace_1600x900.png` (+ `.license`) - the human-facing
  native | web | diff-heatmap composite.
- `manifest.tsv` - state -> size -> golden -> thresholds -> determinism -> sha256.
- `REPORT.md` - today's honest numbers, per-region characterization, re-run command.

## Provenance

- Native oracle: `oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender`
  (Blender 5.2.0 LTS, Cocoa+Metal, pin `fbe6228777e7`) - the SAME binary the
  m4/m5/m6 goldens came from, invoked via the documented capture path.
- Comparator: `oiiotool` 3.1.16.0 (`/opt/homebrew/bin/oiiotool`).
- Capture host: 3024x1964 Retina; content-height clamps ~1001px, so 1600x900 is
  within bounds and captures at the EXACT requested size.

## Regenerate

```
# NATIVE golden (opens a real Blender window twice for the determinism check):
bash sandbox/m4-fullscreen-parity/capture_fullscreen_golden.sh          # workspace 1600x900

# WEB capture (serve first on this lane's port 8129):
BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin \
  bash scripts/serve-web.sh 8129 &
BW_NODE_MODULES=$PWD/.m4-node/node_modules \
  tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m4-fullscreen-parity/capture_web.mjs 1600x900 8129 60000

# Browser-free root/module/platform check (safe under the s7 software-adapter stop):
BW_NODE_MODULES=$PWD/.m4-node/node_modules \
  tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m4-fullscreen-parity/capture_web.mjs --selfcheck

# COMPARE + side-by-side + per-region + teeth:
bash sandbox/m4-fullscreen-parity/compare_fullscreen.sh \
  sandbox/m4-fullscreen-parity/artifacts/web_1600x900.png workspace 1600x900
bash sandbox/m4-fullscreen-parity/compare_fullscreen.sh --composite \
  sandbox/m4-fullscreen-parity/artifacts/web_1600x900.png workspace 1600x900
bash sandbox/m4-fullscreen-parity/compare_fullscreen.sh --regions \
  sandbox/m4-fullscreen-parity/artifacts/web_1600x900.png workspace 1600x900
bash sandbox/m4-fullscreen-parity/compare_fullscreen.sh --selftest
```

Exit 0 = within Blender's tier-c tolerance; 1 = FAIL; 2 = usage/missing input.
This harness MEASURES the other lanes' in-progress work (solid cube, gizmo ball,
menu backgrounds, and - as of this build - a full-window chrome flip); it never
massages the numbers to pass. Live capture still requires the accepted hardware
WebGPU adapter from migration runbook s7; `--selfcheck` launches no browser and
creates no artifact or receipt.
