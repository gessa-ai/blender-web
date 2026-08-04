<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->
# M5.pre — tier-(c) event-simulate recon (ORACLE-SIDE)

GOAL.md M5 (tier-c): scripted sessions via `--enable-event-simulate` +
`Window.event_simulate`, reusing the `tests/python/ui_simulate/` easy_keys DSL,
checked by **operator-trace + state parity** for the core loop (select, G/R/S with
axis constraints, Tab edit-mode, extrude, bevel, undo depth). This note is the
oracle-side half: it needs no pixels from us. Deliverables under
`sandbox/m5-prep/` (sessions, in-Blender runner, oracle driver, goldens, traces).
Oracle: Blender **5.2.0 LTS** build **fbe6228777e7** (matches `upstream/PIN`).

## 1. The DSL — how sessions are authored, invoked, asserted, windowed

### 1a. `modules/easy_keys.py` — the event-authoring API (cited)
- `EventGenerate(window)` (`ui_test_utils.test_window()` returns
  `(e, t, window)`, `t = unittest.TestCase()`). Attribute access maps a key name
  to an `_EventBuilder`; chaining builds modifier combos.
  - `e.g()` taps G (PRESS+RELEASE via `window.event_simulate(type='G', value=…)`);
    `e.ctrl.z()` = Ctrl+Z; `e.g().x().text("2").ret()` = grab → constrain X → type
    "2" → Enter, i.e. **a whole modal transform is one chained yield**
    (easy_keys.py:119 `_key_press_release`, :162 the `event_simulate` call).
  - `e(count)` repeats a tap: `e.ctrl.z(4)` = undo ×4 (`__call__`, easy_keys.py:113).
  - `e.text("…")` types phrases; `e.leftmouse.tap()` / `e.ctrl.leftmouse.tap()`
    click / extend-select; `e.cursor_position_set(x, y, move=True)` moves the mouse
    (window-relative pixels).
- **A session is a generator that `yield`s** the `EventGenerate` between event
  batches. `easy_keys.run(gen, on_error, on_exit)` registers a **persistent
  `bpy.app.timers` callback** that advances the generator every `TICKS=4` timer
  ticks, injecting the batch, until `StopIteration` → `on_exit` (easy_keys.py:287,
  :382). **⇒ requires the WM event loop to be running** (a real window, not
  `--background`).
- `easy_keys.setup_default_preferences()` disables splash / smooth_view /
  save-prompt → the viewport is stable and numeric-entry transforms are
  deterministic (easy_keys.py:385).

### 1b. `modules/ui_test_utils.py` helpers (cited)
`test_window(i=0)` → `bpy.data.window_managers[0].windows[i]`;
`get_window_area_by_type(window,'VIEW_3D')`, `get_area_center(area)`;
`call_menu/call_operator(e, "Add -> Mesh -> Cube")` (F3 search); `idle_until` for
job-backed ops. **Coord gotcha (fixed in our sessions):**
`bpy_extras.view3d_utils.location_3d_to_region_2d` is **region-relative**, but
`event_simulate` x/y are **window-relative** → add `region.x, region.y`
(upstream `_view3d_object_select_by_name` gets away without it only because its
sessions first make VIEW_3D full-screen).

### 1c. Invocation & CMake registration (cited)
- Outer driver `ui_simulate/run.py` spawns, per test:
  `blender --enable-event-simulate --factory-startup --python run_blender_setup.py
  -- --tests <mod.func>` (run.py:126). `run_blender_setup.py` imports the test
  module, gets the function, and calls `easy_keys.run(test_fn(), …)`;
  `on_exit → bpy.ops.wm.quit_blender()` (run_blender_setup.py:132).
- CMake (`tests/python/CMakeLists.txt:1684` `if(WITH_UI_TESTS)`), section titled
  **"Headless GUI Tests"**, registers each test through
  `add_blender_test_ui → add_blender_test_ui_backend` (CMakeLists.txt:112), which:
  - **removes `--background`** (a real window is required, :115),
  - launches via `tests/utils/blender_headless.py` (:120),
  - passes `--factory-startup --no-native-pixels --no-window-frame -p 0 0 800 600
    --gpu-backend {opengl|metal|vulkan}` (:124-130),
  - and **`--log "operator" --log-level "debug"`** — this is the **operator trace**
    source (:132).

### 1d. What the tests assert
Two things, both reused here: (a) inline `t.assertEqual(...)` state checks inside
the generator (immediate gate); (b) the **operator log** (`--log operator`)
records every op for buildbot debugging. There is no recorder — sequences are
hand-authored (matches GOAL.md).

## 2. Windowing / GHOST backend — EXACT feasibility

`tests/utils/blender_headless.py` (the "headless GUI" wrapper) dispatches by
platform (`main()`, :375):
- **Linux (default):** `backend_wayland` launches a **headless Weston compositor**
  (`weston --backend=headless --width=800 --height=600`), sets `WAYLAND_DISPLAY`,
  runs Blender against it via **GHOST_WAYLAND**. **Not Xvfb** — the mechanism is
  weston headless. Needs `WITH_GHOST_WAYLAND` + a `weston` binary (CMakeLists.txt
  :81 gates `WITH_UI_TESTS_HEADLESS` on `WITH_GHOST_WAYLAND`).
- **macOS / Windows:** `backend = backend_base`, whose `run()` prints
  *"No headless back-ends for 'darwin'"* and returns 1 (:100, :381). **There is no
  headless path on macOS** — GUI tests need a real Cocoa window server session
  (or `USE_WINDOW`/`PASS_THROUGH` to run on the developer's live display).

**The oracle here** is `oracle/blender-5.2.0/Blender.app` — a macOS **Cocoa +
Metal** GUI build (`oracle/bpy.sh` normally forces `-b`). Probed directly
(windowed, self-quitting): **it creates a real 800×600 window in this
environment** — `gpu.platform.backend_type_get()=='METAL'`, device `APPLE`,
`len(windows)==1`, areas `[PROPERTIES, OUTLINER, DOPESHEET_EDITOR, VIEW_3D]`,
`bpy.app.use_event_simulate==True`, `window.event_simulate` callable, exit 0, no
GHOST/Cocoa errors. **`event_simulate` RNA is only present with
`--enable-event-simulate`** (absent otherwise — confirmed).

### Feasibility verdict: GO on this host.
Full ui_simulate sessions run on the oracle **windowed** here (macOS host has a
live window server). A Linux/Docker oracle would instead need
`WITH_GHOST_WAYLAND` + `weston` (headless). Either way `--background` is
impossible for tier-c — a window is mandatory. This is not an obstacle for the
oracle half: the goldens below are produced and are twice-verified deterministic.

## 3. Sessions authored (`sandbox/m5-prep/sessions/m5_core.py`)
Seven sessions covering the full GOAL.md M5 core loop, in the upstream DSL,
operating on the factory-startup default scene (Cube/Camera/Light):

| session | interaction (GOAL M5 target) |
|---|---|
| `object_select_all` | **select-all** — Alt+A deselect / A select-all toggle |
| `object_click_select` | **click-select** — deselect, then click the Cube (view3d.select) |
| `object_transform_grxsz` | **G/R/S + axis** — `G X 2`, `R Z 45`, `S 2` |
| `edit_mode_toggle` | **Tab** — into EDIT, back to OBJECT |
| `mesh_extrude_region` | **extrude** — Tab, face-select, A, `E Z 1` |
| `mesh_bevel` | **bevel** — Tab, A, `Ctrl+B` numeric offset 0.2 |
| `undo_depth` | **undo depth** — 2 extrudes, `Ctrl+Z ×2`, `Ctrl+Shift+Z ×1`, asserting each rung |

Each ends in OBJECT mode so the edit-mesh is flushed to the mesh datablock for the
state dump. Mesh sessions assert vertex-count deltas; transform asserts loc/rot/
scale; each keeps the inline `t.assert*` gate.

## 4. Parity design (two artifacts, both diffed exactly)
Per file, `sandbox/m5-prep/m5_run_session.py` (in-Blender, modeled on
`run_blender_setup.py`) drives one session and on `on_exit` captures **(b)**:

- **(a) Operator trace** — from `--log operator --log-level debug` on **stdout**
  (CLOG category `"operator"`, declared `wm_init_exit.cc:122`
  `WM_LOG_OPERATORS`). Lines look like
  `HH:MM.mmm  operator | Started bpy.ops.<idname>(<props>)`. Sanitizer keeps only
  `Started bpy.ops.…` lines and **strips the leading timestamp** (the sole
  non-deterministic field) → `traces/<session>.trace.txt`. The op idnames **and
  their full property dicts are deterministic** (e.g. the extrude trace carries
  the entire `TRANSFORM_OT_translate={…}` snapshot verbatim). This is the
  behavioral trace — the primary artifact for pure-selection sessions whose saved
  state barely changes.
- **(b) Post-session state dump** — reuses `sandbox/corpus-prep/state_dump.py`
  `build_dump()` (the same schema proven bit-exact 64-bit→wasm32 in
  m1-corpus-prep §7/§8; **no floats reach the JSON**, all quantized ints) over the
  resulting `bpy.data` → `goldens/<session>.json`, with `_m5_session` /
  `_m5_result` tags. This is the result artifact for transform/extrude/bevel/undo.

The wasm side will reuse `compare_dumps.py` (EXACT, `--tolerance 0`) for the state
dump and a plain `diff` for the sanitized trace. Determinism gate: each session is
run **twice in separate oracle processes** and BOTH artifacts must be
byte-identical before a golden is staged (same discipline as the corpus).

## 5. Results — `run_oracle_sessions.sh` (7/7 PASS, twice-deterministic)

| session | state sha256 | trace sha256 | ops |
|---|---|---|---|
| object_select_all | `d9d3687c…` | `89a9527b…` | 4 |
| object_click_select | `2443da63…` | `ab8df70a…` | 4 |
| object_transform_grxsz | `2bfa5570…` | `efe19731…` | 6 |
| edit_mode_toggle | `1b075bb1…` | `2e5f8080…` | 8 |
| mesh_extrude_region | `410160f7…` | `0d45cd41…` | 12 |
| mesh_bevel | `4ab4cfa3…` | `ca324258…` | 10 |
| undo_depth | `ce5f04cf…` | `58e82b46…` | 16 |

All 7 sessions produced **byte-identical state dump AND operator trace across two
independent windowed oracle runs**, and every inline `t.assert*` passed. Example
traces: transform = `select_all(SELECT) → transform.translate → transform.rotate →
transform.resize`; undo = `mode_set(EDIT) → editmode_toggle → mesh.select_all →
edit_mesh_extrude_move_normal → extrude_region_move{…} → (×2) → ed.undo → ed.undo →
ed.redo → mode_set`. (Note Tab fires both `editmode_toggle` and its inner
`mode_set` — both logged, deterministically.)

## 6. Wasm-side sequencing (what this unblocks / blocks on)
This oracle half is **ready now**. The wasm half needs, from M4/M5:
1. **A GHOST-web window + WM main loop.** `event_simulate` injects into the WM
   event queue and `bpy.app.timers` fires only while the WM loop runs; on wasm that
   is `emscripten_set_main_loop` on the WM worker (the staged M4 task 5,
   ledger 2026-08-04 M4 plan). No window today ⇒ the wasm run blocks on M4, exactly
   as m1-corpus-prep §6 flagged the M2 sequencing for the load gate.
2. **`--enable-event-simulate` wired through the wasm creator args** (the RNA
   method is core WM, already compiled in; only the flag + a window are missing).
3. Then the wasm runner is `run_oracle_sessions.sh` adapted to
   `node build-wasm/bin/blender.js` against the GHOST-web canvas; trace capture
   (`--log operator` → stdout, already captured on the node build) and
   `build_dump` (already proven on wasm) need no changes.
The GPU backend need not be pixel-correct for tier-c state/trace parity — a booted
WebGPU context sufficient for `gpu.platform.*` and the operators' RNA side effects
is enough; render goldens are the separate M6 tier.

## 7. Open items
- **Bevel/extrude exact geometry** is captured by hash; if a wasm divergence ever
  appears it is a real modeling-op finding (edit-mesh/bmesh), first paths cited by
  `compare_dumps.py` — same method as the corpus.
- **macOS pixel_size**: sessions run with `--no-native-pixels` (pixel_size 1) so
  `event_simulate` window coords need no HiDPI scaling; a Retina run without that
  flag would (see `ui_test_utils.get_window_size_in_pixels`). The wasm/browser
  canvas is 1:1 by our control, so this is macOS-oracle-only.
- Multi-window undo (`view3d_multi_mode_multi_window`) and job-backed ops
  (`idle_until`) are deferred from this core set — layer in after the wasm window
  lands.
