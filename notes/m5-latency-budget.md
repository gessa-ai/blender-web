<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# M5 input-to-visible-frame LATENCY budget

The last open M5 gate item ("input latency budget met"). GOAL.md left the number
to the eval; this note DEFINES the measurement, PROPOSES the M5 budget with
rationale, and records the PASS/FAIL verdict against it. Rig + code:
`sandbox/m5-latency/**`.

## Binary under test

`build-wasm-windowed/bin/blender_browser.wasm` 926,750,606 B @ 2026-08-07T23:41:40
(the stable -O0 dev build; the same binary the M5 event-simulate replay used, see
`notes/m5-windowed-replay.md`). The -O2 `build-wasm-windowed-opt` binary was
relinking continuously during this run (04:02:49, still shrinking); the HAZARD
rule ("reboot if another lane relinks mid-run") bars measuring on a mid-relink
binary, so the stable dev build is canonical here. The -O0 build is the
WORST-CASE for CPU cost, so a PASS on it is a conservative PASS. Steady-state
interaction latency is dominated by frame cadence + present + compositor (build
-independent), not operator CPU, so these numbers are also a fair read of the
opt build's interaction feel; boot/first-paint is where -O0 hurts (below).

## Method - one wall clock, no monotonic bridging

Blender's own `--enable-event-simulate` drives the input; the visible half is CDP
screencast. All three instants live on ONE wall clock (gettimeofday epoch
seconds), so no clock bridging is needed:

- **keypress dispatch** `t_disp` = Python `time.time()` emitted (raw fd 2,
  `os.write`) IMMEDIATELY before the `window.event_simulate()` call - the honest
  "input arrival" instant. (`M5LAT_DISPATCH i <label> <t>`.)
- **operator start** `t_op` = the `--log operator` CLOG "Started bpy.ops.<op>"
  line. CLOG stamps `gettimeofday`-ms since a `tick_start` set at init
  (`upstream/intern/clog/clog.cc` `write_timestamp`, format `MM:SS.mmm`).
  `tick_start` is calibrated to sub-ms by bracketing several DIRECT
  `bpy.ops.ed.undo_push()` calls with `time.time()` (`M5LAT_CAL k t0 t1`) and
  pairing each with its own CLOG line: `tick_start = mid(t0,t1) - clog_rel`.
  Measured spread across 5 pairs: 0.0-0.5 ms.
- **visible present** `t_vis` = the first CDP `Page.screencastFrame` after
  `t_disp` whose canvas pixels change vs the pre-dispatch baseline frame.
  `metadata.timestamp` is `Network.TimeSinceEpoch` (epoch seconds - same clock).
  Change = greyscale 160x90 thumbnail mean-abs-diff over a static-noise-floor
  threshold (floor p25 ~0.5; the edit-mode/outline toggle signal is ~23, a ~45x
  margin).

Console-line ARRIVAL jitter (worker->main postMessage) is immaterial: every value
is read from the EMBEDDED timestamp inside the line, never from arrival time.

The input is provably pixel-changing: `object.editmode_toggle` (Tab) raises the
edit-mesh overlay; `object.select_all` (A/Alt+A) flips the selection outline.
Both render on this build (dMax ~23 vs ~0.5 static). `G`-move of the cube was NOT
used: the workbench opaque cube does not draw on this build (r28 Bug B), so a
grab would not "provably change pixels".

### Method floors / ceilings (honest bracket)
- **Ceiling (over-estimate):** the screencast frame timestamp is when Chrome
  captured the COMPOSITED frame, i.e. at/after present. `operator->present` (and
  thus end-to-end) therefore includes up to ~1 frame of screencast-capture
  scheduling on top of the true app+present time. Screencast cadence during
  activity: median ~7-8 ms (~130 fps), so this quantization is small.
- **Floor (omission):** compositor -> physical-display scanout (vsync, ~1 display
  refresh, ~8-16 ms) is BELOW the screencast capture point and is NOT measured.
  True user-perceived latency is roughly these numbers + ~1 refresh.
- **rAF cadence** (event waits for the next WM_main iteration to be handled) IS
  captured in `keypress->operator` - it is real input latency, not removed.
- The rig has TEETH: the N-panel toggle (`wm.context_toggle`) fired 20/20 with a
  9 ms keypress->operator, but produced ZERO pixel change (dMax 1.7 < 5) because
  the N-panel region does not paint on this build - the method reported
  `with_visible=0` rather than fabricating a present. (A real finding: N-panel
  region draw is absent on the windowed build.)

## Results (stable dev build, steady state after shader compile)

| metric | probe | n | median | p95 | min | max |
|---|---|---|---|---|---|---|
| keypress -> operator-start | Tab editmode_toggle | 40 | **9.5** | 10.5 | 7.5 | 11.5 |
| operator-start -> present | Tab editmode_toggle | 40 | **30.4** | 36.8 | 20.1 | 454* |
| end-to-end (keypress->visible) | Tab editmode_toggle | 40 | **39.7** | 44.9 | 29.6 | 464* |
| keypress -> operator-start | select_all (cross-check) | 20 | 10.0 | 12.0 | 8.0 | 12.0 |
| operator-start -> present | select_all (cross-check) | 20 | 27.6 | 31.8 | 19.4 | 33.0 |
| end-to-end | select_all (cross-check) | 20 | 37.9 | 41.3 | 30.4 | 43.1 |

All ms. `*` one Tab sample took 454 ms present (a single dropped-frame/GC hitch);
median and p95 are robust to it (it is beyond p95). The two INDEPENDENT probes
(different operator, different visible change) agree to ~2 ms on end-to-end and
~1 ms on keypress->operator, confirming the number is a property of the
input->present pipeline, not the operator.

## Boot-to-interactive (3 cold runs, dev build)

Server sends `Cache-Control: no-store`, so every load re-fetches the 926 MB wasm
+ 85 MB data - genuinely cold.

| run | load -> WM_main | load -> first painted frame |
|---|---|---|
| 1 | 1551 ms | 20036 ms |
| 2 | 1803 ms | 20601 ms |
| 3 | 1777 ms | 19604 ms |
| **median** | **1777 ms** | **20036 ms** |

The main loop pumps in ~1.8 s, but the first PIXELS wait ~20 s for synchronous
workbench WGSL shader compilation on the first draw (the per-shader source dumps
on the console). This is a one-time cost of the -O0 build with no active shader
cache; the designed OPFS shader cache (GOAL "Mirror the Vulkan backend's shader
disk cache onto OPFS") and the opt build are the fix. This is a BOOT-quality
matter (M4/M8), NOT input latency, and is OUT of the M5 latency-budget verdict -
recorded here as a finding.

## Proposed M5 latency budget (record)

- **End-to-end keypress -> visible frame: median <= 100 ms, p95 <= 150 ms.**
  Rationale: 100 ms is the classic HCI "instantaneous / direct-manipulation"
  threshold (below it the system feels like it reacts at once); p95 <= 150 ms
  guards tail hitches while staying inside the "still responsive" band. The bar
  is set on the measured e2e, which slightly OVER-estimates (screencast capture)
  and omits sub-screencast scanout (~1 refresh), so the 100/150 ms bar carries
  that bracket as headroom.
- **Sub-budget - keypress -> operator-start: median <= 33 ms** (<= 2 frames @
  60 Hz): the input-handling half must not itself eat more than a couple frames.

## VERDICT: PASS

| bar | budget | measured (Tab, n=40) | verdict |
|---|---|---|---|
| end-to-end median | <= 100 ms | 39.7 ms | PASS (~2.5x margin) |
| end-to-end p95 | <= 150 ms | 44.9 ms | PASS (~3.3x margin) |
| keypress->operator median | <= 33 ms | 9.5 ms | PASS |

Corroborated by the select_all cross-check (37.9 / 41.3 ms). The M5 gate item
"input latency budget met" is **MET** on the stable windowed build.

## Reproduce
```
BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed/bin \
BLENDER_WEB_SHELL=/Users/paws/blender-web/sandbox/m5-latency/web \
  /opt/homebrew/bin/bash scripts/serve-web.sh 8125            # terminal 1
/opt/homebrew/bin/bash sandbox/m5-latency/web/stage-py.sh     # refresh gen/
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/m5-latency/drive-latency.mjs --port 8125 \
       --session m5_latency.tab --n 40 --spacing 0.6 --label tab-dev
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/m5-latency/drive-latency.mjs --port 8125 \
       --session boot --boots 3 --label dev
```
Results land in `sandbox/m5-latency/out/` (git-ignored): `lat-*.json` (per-sample
+ summary), `boot-*.json`, `*.console.txt`.
