<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# blender-web — 75-second demo script (M5 interactive)

A tight, honest walkthrough of the windowed build doing real modeling in a
browser tab. Every step carries a **verdict** grounded in the M5 tier-(c)
event-simulate replay (`notes/m5-windowed-replay.md`,
`sandbox/m5-prep/wasm-out/`): **PROVEN** = a replay session reproduced it with
byte-exact state + operator-trace parity vs the native oracle; **OBSERVED** =
seen live/interactively but not in the automated state/trace battery;
**BLOCKED** = does not work on the current windowed build, with the named
blocker. Binary: `build-wasm-windowed/bin` @ 2026-08-07T23:41 relink.

Setup for a live run: serve the windowed build and open the tab (auto-boots):
```
BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed/bin \
  bash scripts/serve-web.sh 8125
# open http://localhost:8125/windowed.html
```

| t (s) | step | on screen | verdict | evidence |
|---|---|---|---|---|
| 0-8 | **Load** — open the tab | loader, then splash-suppressed default workspace boots | **PROVEN** | all 8 sessions boot to `WM_main` ~1.4 s warm; upright chrome (patch 0115) |
| 8-15 | **Default scene** | Cube (selected) + Camera + Light, grid, red/green axes, nav gizmo | **PROVEN** | every session's post-load `bpy.data` state dump is byte-identical to the native factory-startup oracle (`compare_dumps.py --tolerance 0`) |
| 15-25 | **Select** — press `A` (select all), `Alt+A` (deselect) | cube outline toggles on/off | **PROVEN** | `object_select_all`: state PASS + trace PASS (byte-exact) |
| 25-40 | **G / R / S** — `G X 2 ⏎`, `R Z 45 ⏎`, `S 2 ⏎` | cube translates on X, rotates 45° on Z, scales 2x | **PROVEN** | `object_transform_grxsz`: state PASS + trace PASS; numeric-entry modal transforms with axis constraints match native exactly |
| 40-48 | **Orbit / zoom** — MMB-drag orbit, wheel zoom | viewport camera orbits + dollies smoothly | **OBSERVED** | viewport navigation mutates no `bpy.data`, so it is out of scope for the state/trace battery; orbit/zoom seen live (human drove orbit mid-capture, ledger) and the WM loop pumps input every session |
| 48-60 | **Tab -> edit mode + Extrude** — `Tab`, `3` (face), `A`, `E Z 1 ⏎` | enter edit mode, select all faces, extrude +1 on Z | **PROVEN** | `edit_mode_toggle` (trace PASS), `edit_mode_select_modes` (PASS), `mesh_extrude_region` (state PASS + trace PASS*); undo/redo depth also PROVEN (`undo_depth`) |
| 60-68 | **Add Torus via menu** — Add ▸ Mesh ▸ Torus | a torus primitive appears at the cursor | **OBSERVED** | not in the automated battery; menu hit-testing and operator execution are each exercised by the passing sessions (tool_set + modal ops), but this specific add-primitive-via-menu path is not tier-c-verified here |
| 68-73 | **Offline proof** — open DevTools ▸ Network | zero external requests; everything served from localhost | **PROVEN** | `offline-proof.mjs`: 42 requests, all `localhost:8125`, 0 external hosts (`wasm-out/offline-proof.json`) |
| 73-75 | **End** | a modeled scene, built and running entirely in the browser, offline | — | — |

\* trace PASS after normalizing a spurious trailing NUL byte the NATIVE oracle
emits on the `extrude_region_move` macro log line; the operator + full property
dict and the resulting mesh are byte-identical (see `notes/m5-windowed-replay.md`).

## Presenter notes (honesty first)
- **Use `A` (select-all) for the "select" beat, not click-select.** Mouse
  click-select (`view3d.select`) does GPU-buffer object picking, which stalls the
  WM worker on this windowed build (registered `gpu-sync-readback-windowed`
  deferral): the `object_click_select` session reproduces the first three ops
  byte-for-byte then hangs on the ~10 s pick readback. Demo select-all / box; keep
  click-select out until that GPU-readback deferral lands.
- **Solid shading** of the cube lands via a separate GPU lane; this M5 demo is
  about interaction (select / transform / edit / extrude), which is correct
  regardless of the solid-pass state. If the solid cube is not yet composited,
  the outline + gizmos + grid still read clearly and every interaction above is
  faithful.
- Everything above is driven by real Blender operators (the trace lines are the
  same `bpy.ops....` the native app logs), not a scripted mock.
