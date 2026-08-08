<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# M5 tier-(c) — event-simulate replay on the WINDOWED wasm build

The oracle half (native goldens + traces, twice-deterministic) is
`sandbox/m5-prep/` (see `notes/m5-ui-simulate-prep.md`). This note is the **wasm
half**: the 8 M5 sessions replayed IN A BROWSER TAB against the windowed
`blender_browser` build, driven by Blender's own `--enable-event-simulate` +
the `ui_simulate` easy_keys DSL (events injected inside Blender via Python — no
browser input at all), with operator-trace + state-dump parity vs the native
goldens.

## What runs where

- **Server:** `scripts/serve-web.sh` with `BLENDER_WEB_SHELL=sandbox/m5-prep/web`
  and `BLENDER_WEB_BIN=build-wasm-windowed/bin`, port 8125.
  `BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed/bin BLENDER_WEB_SHELL=/Users/paws/blender-web/sandbox/m5-prep/web /opt/homebrew/bin/bash scripts/serve-web.sh 8125`
- **Page:** `sandbox/m5-prep/web/index.html` + `m5-boot.js` — a purpose-built boot
  shell (boot-windowed.js cannot express a custom argv + in-Python staging). One
  page load == one session (`?session=<mod.func>`), for crash isolation.
- **Driver:** `sandbox/m5-prep/web/drive-sessions.mjs` — headed bundled-Chromium
  Playwright (`NODE_PATH=/Users/paws/plushly/game-platform/node_modules`). One
  fresh context per session; boots, waits for the "main loop (WM_main)" marker,
  waits for the run to finish, pulls the artifacts, saves to `wasm-out/`.
- **Staged Python (WasmFS `/m5`):** `m5_wasm_runner.py` (mine) + the ui_simulate
  `modules` package (`easy_keys`, `ui_test_utils`), the session module
  `m5_core.py`, and `state_dump.py`. `stage-py.sh` refreshes `web/py/gen/` from
  the committed sources so nothing drifts; `web/py/gen/` is git-ignored.
- **Compare:** `sandbox/m5-prep/web/compare-all.sh` runs
  `sandbox/corpus-prep/compare_dumps.py --tolerance 0` (EXACT) on the state dumps
  and `diff` on the sanitized operator traces.

## The hard part — how the tab talks to Blender on the WM worker

The windowed build is `-sPROXY_TO_PTHREAD`: `main()` (and thus WasmFS and all of
Blender) live on the WM **worker**; the page is the **browser thread**. Getting
the session in and the results out needed a channel audit (probes in
`sandbox/m5-prep/web/probe-pyexpr.mjs`). Findings on this binary
(`blender_browser.wasm` @ 2026-08-07T23:41 relink):

| channel | works? | note |
|---|---|---|
| `FS.writeFile` from the browser thread (preRun) | **NO** — `Aborted()` | WasmFS is worker-owned; preRun runs on the browser thread before it exists. |
| `--python-expr` executes | **YES** | creator.cc:622 `ARG_PASS_FINAL` runs it straight-line BEFORE `WM_main` (:663); in wasm `WM_main` is an `emscripten_set_main_loop` that returns without the process exiting. |
| Python `print()` / `sys.stderr.write()+flush()` -> console | **NO** | wasm stdout is block-buffered and never flushes (no process exit); Blender's `sys.stderr` does not reach fd 2 either. |
| **`os.write(2, ...)` (raw fd 2) -> console** | **YES** | reaches `Module.printErr` per newline. The only reliable Python->browser channel. |
| **CLOG `--log operator` -> console** | **YES** | lands on fd 2 in the native `HH:MM.mmm  operator | Started bpy.ops....` form — the operator trace, straight off the console. |
| Python file I/O to WasmFS on the worker | **YES** | `open('/m5/out.json','w')` works. |
| **`FS.readFile` from the browser thread POST-boot** | **YES** | `readdir('/')` shows `/m5`; reads back the file. (The earlier abort was a preRun-timing artifact, not a thread rule.) |

### Consequences (the design)

1. **Stage IN** via a `--python-expr` *stager* built by `m5-boot.js`: it embeds
   the 5 Python files as base64 in the argv string, decodes+writes them to `/m5`
   from inside Python on the worker, sets `sys.path`/`sys.argv`, and `exec`s the
   runner as `__main__`.
2. **Signal + dump OUT** via `os.write(2)`: the runner emits `M5_*` status lines
   and the post-session dump as base64 chunks (`M5_OUT i n <chunk>`) that the
   page reassembles (race-free). `/m5/out.json` is also written and cross-checked
   via `FS.readFile` when the module is still alive.
3. **Operator trace** = the console `--log operator` lines, sanitized to the
   oracle's canonical `bpy.ops....` form (strip up to `| Started `), identical
   sanitizer to `run_oracle_sessions.sh`.
4. The runner quits (`wm.quit_blender()`) LAST so the closing op lands in the
   trace exactly like the native golden; the dump is already emitted, so the GPU
   teardown (fragile on the windowed build) is harmless after.

### HAZARD respected
No session and neither the runner nor `state_dump` calls any bpy
screenshot/render/GPU-readback op — those crash the WM worker (deferral
`gpu-sync-readback-windowed`). The dump is pure `bpy.data` mirroring, the same
method as the native oracle.

## Determinism / parity contract
- **State dump:** `compare_dumps.py --tolerance 0` — EXACT (no floats in the
  JSON; every value is a micro-int or a sha256, the corpus contract proven
  bit-exact 64-bit->wasm32). Full dump compared, run-scoped tags included
  (`_m5_session`/`_m5_result` match; `source_name` identical).
- **Operator trace:** plain `diff` of the sanitized `bpy.ops....` lines,
  including the trailing `wm.quit_blender()`.

## Results

Binary under test: `build-wasm-windowed/bin/blender_browser.wasm` 926,750,606 B
@ 2026-08-07T23:41 (a fresh relink by another lane landed mid-session; the run
above used it after it held stable ~3 min). `.js` @ 23:41, `.data` 85,203,093 B
@ 23:23. Boot to `WM_main` ~1.4 s (warm), sessions ~16-17 s each.

Run: `drive-sessions.mjs` (headed Chromium, one fresh boot per session) then
`compare-all.sh` (`compare_dumps.py --tolerance 0` EXACT on state; `diff` on the
sanitized trace, native macro-repr NUL normalized out of both sides).

| # | session (GOAL M5 target) | state dump | operator trace | ops | note |
|---|---|---|---|---|---|
| 1 | `object_select_all` (select-all A/Alt+A) | **PASS** | **PASS** | 4 | byte-exact |
| 2 | `object_click_select` (click-select) | NO-DUMP | FAIL | 3/4 | **GPU-pick stall** (see below) |
| 3 | `object_transform_grxsz` (G X 2 / R Z 45 / S 2) | **PASS** | **PASS** | 6 | byte-exact |
| 4 | `edit_mode_toggle` (Tab in/out) | **PASS** | **PASS** | 8 | byte-exact |
| 5 | `edit_mode_select_modes` (1/2/3) | **PASS** | **PASS** | 13 | byte-exact |
| 6 | `mesh_extrude_region` (E Z 1) | **PASS** | **PASS*** | 12 | *native macro NUL normalized |
| 7 | `mesh_bevel` (Ctrl+B 0.2) | **PASS** | **PASS** | 10 | byte-exact |
| 8 | `undo_depth` (2x extrude, undo x2, redo) | **PASS** | **PASS*** | 16 | *native macro NUL normalized |

**7/8 full state + operator-trace parity.** Every produced state dump is
byte-identical to the native golden under `compare_dumps.py --tolerance 0` (the
same EXACT bar as the corpus). Traces are byte-identical to the native golden
including the trailing `wm.quit_blender()`.

### Divergence 1 — `object_click_select` (BLOCKED by a known deferral)
The harness worked: `M5_BEGIN`/`M5_ARMED` emitted, the deselect + click were
injected, and the first three ops (`tool_set_by_id`, `object.select_all(DESELECT)`,
`view3d.select(deselect_all=True)`) are **byte-identical to the native golden**.
But `view3d.select` is the ONLY session op that does GPU-buffer object picking
(the console shows the `overlay_*_selectable` GPU pick pipelines building); it ran
for ~10 s (blocking readback), reported `Finished ...view3d.select(...,
location=(525,310))`, and left the WM worker stalled (`present` frozen at 2, the
`bpy.app` timer stopped), so the session never reached its post-click assert or
the dump. This is the registered **`gpu-sync-readback-windowed`** deferral
(screenshot/render/select-buffer readbacks stall the windowed WM worker), NOT an
event-simulate or state-dump defect. Re-test click-select once that GPU-readback
deferral is resolved. The other 7 sessions do no GPU picking and pass.

### Divergence 2 — native macro-repr trailing NUL (cosmetic, normalized)
For the two sessions whose trace contains the `mesh.extrude_region_move` MACRO op
(`mesh_extrude_region` x1, `undo_depth` x2), the NATIVE oracle log line ends with
a spurious NUL byte (`\0`) before the newline; the wasm build emits the identical
repr without it (native NUL count 1/2, wasm 0). This is a native
CLOG/`WM_operator_as_string` artifact on macro operators, not a wasm behavior
difference — the operator idname + full property dict match byte-for-byte and the
resulting mesh state dump is byte-identical, proving the extrude / undo / redo
behave identically. `compare-all.sh` normalizes NUL out of both sides (recorded in
`*.trace.nul.txt`); the raw bytes remain in `wasm-out/*.trace.txt` for audit.

### Offline proof
`offline-proof.mjs` records every network request the tab makes during a session:
all requests target `localhost:8125` only (the `/bin` wasm/js/data + `/py` bundle);
zero external hosts. `wasm-out/offline-proof.json`.

### Reproduce
```
BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed/bin \
BLENDER_WEB_SHELL=/Users/paws/blender-web/sandbox/m5-prep/web \
  /opt/homebrew/bin/bash scripts/serve-web.sh 8125            # terminal 1
/opt/homebrew/bin/bash sandbox/m5-prep/web/stage-py.sh        # refresh gen/
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/m5-prep/web/drive-sessions.mjs 8125            # all 8 sessions
/opt/homebrew/bin/bash sandbox/m5-prep/web/compare-all.sh     # verdicts
```

