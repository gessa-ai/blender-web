<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M4 round 25 (driver) — boot regression KILLED by the urllib3 shim; gate 100%→33.4%; viewport interior isolated to the engine-draw→composite chain

Pin: Blender 5.2 `fbe6228777e7`; build `build-wasm-windowed` (r24 state: patches through
0109 + GHOST present delegation — `ninja blender_browser` reported no work, binary current)
+ the urllib3/pyodide import-shims cherry-picked from `claude/friendly-elgamal-3189df`
`7c1cda2` → `06feea1` on `agent/m2.5-python-boot` (only conflict: append-only
`ledger/progress.txt`, both sides kept). Shim payload verified INSIDE
`blender_browser.data` (manifest lists + content grep hits `site-packages/js.py`,
`pyodide/__init__.py`, `pyodide/ffi.py`). Rig = r23/r24 recipe: headed node-Playwright,
bundled `chromium-1228`, fresh profile per launch (empty OPFS), `:8123/windowed.html`,
CDP `page.screenshot` clipped to the `#canvas` bbox at `deviceScaleFactor:1` = exact
1280x720. Env receipts every boot: `visibilityState "visible"`, `crossOriginIsolated
true`, adapter OK, rAF 115-120/s.

## 1. The r24 boot regression is DEAD (shim confirmed as the fix)

Clean boot (`?pyexpr=` show_splash=False only): **no `ModuleNotFoundError: No module
named 'js'`** anywhere in the console (r24's signature), WM_main at 3.2-3.8 s,
`presentBackbuffer frame 0/1` fires, **zero Dawn validation errors** all boot, full UI
(topbar, tool shelf, properties, outliner, status bar) composites upright and stable
through 90 s. Comparator on the r25 gate capture:

```
bash sandbox/m4-golden-prep/compare_m4.sh <r25-t90s> workspace 1280x720
FAIL workspace_1280x720  Max error = 0.906 over: 308063 pixels (33.4%) over 0.016  (exit 1)
```

r24 was 100% (canvas = CSS background); r23 was 35.5%. The 33.4% IS the blank viewport
interior; UI chrome matches the golden. Boot-payload class CLOSED; the M4 gate turns on
the 3D viewport interior only. Evidence:
`platform_web/shell/evidence/m4-r25-workspace-ui-restored-33p4-1280x720.png`.

## 2. NEW measured gap: GPU readback returns ZEROS in the windowed profile

In-session probe (bpy.app.timer at t=20 s): `bpy.ops.render.opengl(write_still=True,
view_context=True)` **succeeds** (`Saved: '/tmp/vp0.png'`, 1920x1080 in ~5 s — the
workbench engine mechanically renders offscreen) and `bpy.ops.screen.screenshot` writes
`/tmp/win.png`; both pulled via `window.__bwModule.FS.readFile`. **Both are constant
0 in EVERY channel including alpha** (`oiiotool --stats`: Constant: Yes, 0/255) — while
the window content provably composites on-canvas at the same moment (CDP capture shows
the full UI). So `GPU_texture_read`-class sync readback yields zeros under the windowed
profile — the measured consequence of the F9-D/ADR-007 kick-then-consume disposition
(the read returns before the copy resolves). This RETROACTIVELY completes r23's "in-app
readback BLANK" diagnosis: not only the transient surface — even the 0109 persistent
CopySrc backbuffer reads back zeros. Tier-(c)/M5-M6 capture paths MUST pump ticks until
the map resolves (ADR-007 consequence, now with a concrete repro).

## 3. NEW crash: wasm `table index is out of bounds` right after the snapshot ops

Immediately after the two ops above: `Uncaught RuntimeError: table index is out of
bounds` (`blender_browser.js:23578`) from the WM worker; the loop HALTS (captures
byte-identical before/after an orbit drag). Repro = the pyexpr timer running
render.opengl + screen.screenshot back-to-back. Indirect call through a bad
function-table slot on the readback/callback path is the prime suspect family. Not
gate-blocking (the gate capture is CDP-side) but blocks any in-app capture route and
is an M5 hazard. Characterized, unfixed.

## 4. Engine shaders compile CLEAN — the full set, on demand

`?args=` dev hook added to the shell (boot-windowed.js, mirrors the 1850313 pyexpr
hook; `%20`-separated raw argv, rig-only). Debug boots (`--debug-gpu --log gpu.shader
--log-level 2`):

- Boot compiles 14 UI builtins (00:00.3-00:02.7) — why the UI works.
- WM goes IDLE (CLOG silent 00:05-00:36), a Python timer fires ~00:37 (context queries
  with `region=None/area=None`), and at 00:40 the first ENGINE draw runs: a context-
  query burst then the engine caches compile **on demand, serially, on the WM thread**
  (~130 ms each — `use_main_context_workaround=true` on wasm ⇒ ShaderCompiler has NO
  worker ⇒ `async_compilation()` compiles inline; gpu_shader.cc:1064-1072).
- **104 shaders compile with ZERO failures and ZERO Dawn validation errors** across
  overlay_*, workbench prepass set, `draw_command_generate`, `OCIO_Display`, gpencil
  (second wave 03:20). No blacklist candidates surfaced.

CAVEAT recorded: clean boots log nothing (CLOG off), so "when does the engine draw run
without --debug-gpu" is UNKNOWN, not "never" — do not over-conclude from silent boots.

## 5. The isolated residual: engine output never reaches the canvas

After the full compile storm (debug boot, captures at +150 s/+210 s — the +210 s frame
even includes live interactive UI: context menu open, outliner selections, keymap hints
updating, NO crash) the viewport interior STILL shows only the flat region background.
No grid, no cube, no errors. Combined with §2 (the engine renders offscreen
mechanically) and §4 (shaders fine), the M4 blocker is now exactly:
**DRW engine output → GPUViewport textures → `GPU_viewport_draw_to_screen` region
composite produces nothing visible, silently.**

r26 (next round, needs a rebuild): instrument that chain — (a) count
`DrawEngine::draw()` submissions + per-pass drawcall counts (stderr, console-visible);
(b) force-clear the GPUViewport color texture to magenta pre-engine-draw: magenta in
the window ⇒ composite works, render empty; no magenta ⇒ composite/wrap broken;
(c) verify the region-composite shader binds the viewport texture (not a fresh/empty
one) — texture-name/ID log at composite time.

## Build-tree wrinkle (latent, non-gate)

`ninja -C build-wasm-windowed` full-graph fails at the `makesdna` TESTS generation rule:
`cmake -E env <makesdna.js> …` lacks the CROSSCOMPILING_EMULATOR node prefix and
`makesdna.js` has no shebang/+x → `permission denied`. Gtest targets only; the
`blender_browser` target is unaffected. Fix when the wasm gtest lane next runs.

## Receipts

- Cherry-pick `06feea1` (verified fail-on-use design; deferred.json 24 entries,
  `emscripten-network-transport`); wheels.sh idempotent-skip confirmed the shims were
  already harvested into `lib/wasm` site-packages (06:24, pre-dating the current
  binary's 07:35-07:37 link, which therefore already packaged them).
- No gpu/webgpu source touched this round; native census untouched (m3 5/5 GREEN,
  harness/status.sh, 2026-08-07T11:39Z run).
- Comparator selftest re-run PASS (identity + cross-state teeth) before the gate run.
- Rig scripts (session scratchpad, one-shot): rig_r25{,b,c,d,e}.js — recipe fully
  documented in this note + r23's; the ?args= hook is the only committed shell change.
