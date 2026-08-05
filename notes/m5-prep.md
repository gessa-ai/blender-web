<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->
# M5-prep — tier-(c) event-simulate sessions (OUTCOME)

Outcome-first index for the M5 interactive-parity prep. GOAL.md M5 (tier-c):
event-simulate sessions (`--enable-event-simulate` + `Window.event_simulate`,
reusing the upstream `tests/python/ui_simulate/` easy_keys DSL) covering the core
loop — select, G/R/S with axis constraints, Tab edit-mode, extrude/bevel, undo
depth — with **operator-trace + state parity**. Full DSL/windowing recon lives in
`notes/m5-ui-simulate-prep.md`; this note is the verdict, receipts, invocation,
and the validation-binary situation.

## Verdict: 8/8 sessions validated, twice-deterministic (oracle-side, ready now)

All sessions in `sandbox/m5-prep/sessions/m5_core.py` produce a **byte-identical
operator trace AND post-session state dump across two independent windowed native
runs**, and every inline `t.assert*` gate passes. The freshly-regenerated
artifacts are also byte-identical to the committed goldens/traces (cross-session
reproduction, not just within one script run).

| session | GOAL M5 category | state sha256 | trace sha256 | ops |
|---|---|---|---|---|
| `object_select_all` | (a) select — Alt+A / A toggle | `d9d3687c…` | `89a9527b…` | 4 |
| `object_click_select` | (a) select — click the Cube | `2443da63…` | `ab8df70a…` | 4 |
| `object_transform_grxsz` | (b) G/R/S+axis+numeric — `G X 2`, `R Z 45`, `S 2` | `2bfa5570…` | `efe19731…` | 6 |
| `edit_mode_toggle` | (c) Tab — EDIT ↔ OBJECT | `1b075bb1…` | `2e5f8080…` | 8 |
| `edit_mode_select_modes` | (c) vertex/edge/face select modes — keys 1/2/3 | `fac97b75…` | `15cabdb3…` | 13 |
| `mesh_extrude_region` | (d) extrude — Tab, face-select, A, `E Z 1` | `410160f7…` | `0d45cd41…` | 12 |
| `mesh_bevel` | (d) bevel — Tab, A, `Ctrl+B` numeric 0.2 | `4ab4cfa3…` | `ca324258…` | 10 |
| `undo_depth` | (e) undo/redo depth — 2 extrudes, `Ctrl+Z ×2`, `Ctrl+Shift+Z ×1` | `ce5f04cf…` | `58e82b46…` | 16 |

Full 64-hex hashes are printed by `run_oracle_sessions.sh`; the abbreviations
here match the committed goldens. Coverage maps to all five task categories:
(a) two select variants, (b) transform with axis+numeric input, (c) Tab **and**
vertex/edge/face select-mode switching, (d) extrude + bevel, (e) undo/redo depth.

## Validation binary — NATIVE oracle used; pin-built native is MISSING

- **`build-native-gpu/bin/Blender.app` is an empty bundle** —
  `Contents/MacOS/` contains no `Blender` executable (only the GPU lane's host
  tools `makesdna/makesrna/shader_tool/datatoc` exist under `build-native-gpu/bin/`,
  not a full app). Per the "no builds — if missing/stale, report" rule, it was
  **not** built here.
- **Validated against `oracle/blender-5.2.0/Blender.app`** — a full native
  **Blender 5.2.0 LTS** (Cocoa + Metal, build date 2026-07-14), the same native
  oracle the corpus goldens use. This is the correct available native reference for
  tier-(c) state/trace parity (tier-c is not bit-exact-across-GPU; the trace is
  operator idnames+props, the state is quantized ints — neither depends on the GPU
  adapter).
- **When the pin-built native (`build-native-gpu`) lands:** re-point `BIN` in
  `run_oracle_sessions.sh` and re-baseline. If any golden shifts, that is a
  pin-vs-5.2.0-release delta to characterize, not a session bug — the sessions and
  determinism method are binary-agnostic.

## Exact invocation (per session, run twice)

`run_oracle_sessions.sh` launches, for each session, in two separate processes:

```
oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender \
  -p 0 0 800 600 --factory-startup --no-window-frame --no-native-pixels \
  --enable-event-simulate --log "operator" --log-level "debug" \
  --python sandbox/m5-prep/m5_run_session.py -- \
  --session <mod.func> --state-out <out.json>
```

- A real 800×600 window opens on screen briefly per run (macOS has no headless GUI
  backend — see recon note §2). `--no-native-pixels` forces pixel_size 1 so
  `event_simulate` window coords need no HiDPI scaling.
- **Trace** = stdout `… operator | Started bpy.ops.…` lines, timestamp stripped
  (the only non-deterministic field) → `traces/<session>.trace.txt`.
- **State** = `sandbox/corpus-prep/state_dump.py` `build_dump()` (all floats
  quantized to micro-unit ints, `QUANT = 1_000_000`; no floats reach JSON) →
  `goldens/<session>.json`.
- Determinism gate: both artifacts must be byte-identical across the two runs
  before a golden is staged.

Run the whole gate: `bash sandbox/m5-prep/run_oracle_sessions.sh` → `ALL_PASS`.

## DSL gotchas (condensed; full detail in m5-ui-simulate-prep.md §1)

- **A session is a generator that `yield`s** the `EventGenerate`; `easy_keys.run`
  drives it via a persistent `bpy.app.timers` callback every `TICKS=4` ticks ⇒
  **requires the WM event loop running** (a real window, never `--background`).
- Chaining builds one modal action per yield: `e.g().x().text("2").ret()` =
  grab→constrain X→type 2→Enter; `e.ctrl.z(2)` = undo ×2.
- **Coord gotcha:** `bpy_extras.view3d_utils.location_3d_to_region_2d` is
  region-relative but `event_simulate` x/y are window-relative → add
  `region.x, region.y` (done in `_screen_loc`). Upstream sessions dodge this only
  by full-screening VIEW_3D first.
- **Tab logs two ops** (`object.editmode_toggle` + inner `object.mode_set`) — both
  captured, deterministically. Select-mode keys log `mesh.select_mode(type=…)`.
- Each session ends in OBJECT mode so the edit-mesh flushes to the mesh datablock
  before the state dump.

## What the wasm side needs to replay these (blocks on M4)

The oracle half is ready. The wasm half needs, from M4/M5:
1. **A GHOST-web window + WM main loop** (`emscripten_set_main_loop` on the WM
   worker) — `event_simulate` injects into the WM queue and `bpy.app.timers` fires
   only while that loop runs. No window today ⇒ wasm run blocks on M4.
2. **`--enable-event-simulate` wired through the wasm creator args** (the RNA
   method is core WM, already compiled; only the flag + a window are missing).
3. Then the wasm runner = `run_oracle_sessions.sh` adapted to
   `node build-wasm/bin/blender.js` against the GHOST-web canvas. `--log operator`
   → stdout and `build_dump` already work on the node build, so no artifact-tooling
   changes. Compare with `sandbox/corpus-prep/compare_dumps.py` (`--tolerance 0`)
   for state and plain `diff` for the sanitized trace.

The GPU backend need not be pixel-correct for tier-(c) state/trace parity — a
booted WebGPU context sufficient for `gpu.platform.*` and the operators' RNA side
effects is enough; render goldens are the separate M6 tier.

**Boundary note:** staged goldens stay under `sandbox/m5-prep/`. Installing them
into `tests/golden/` is a driver-at-boundary action — NOT done here.
