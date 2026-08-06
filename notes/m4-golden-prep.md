<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->
# M4-golden-prep — native first-pixels goldens + comparator (OUTCOME)

Outcome-first index for the M4 gate prep. GOAL.md M4 (tier-c pixels): "splash +
default cube (cube/camera/light, correct theme) matches the native golden within
idiff threshold on the pinned CI adapter." This stages the NATIVE goldens and a
size-parameterized comparator now, oracle-side (the m5/m6-prep pattern), so the
moment the wasm cube renders the comparison is one command, not a project.

## Verdict: 4 goldens staged, byte-identical across two runs; comparator has teeth

| state | requested | staged size | determinism | sha256 (first 16) |
|---|---|---|---|---|
| `splash` | 1280x720 | **1280x720** | byte-identical ×2 | `b258e12ddb168648` |
| `workspace` | 1280x720 | **1280x720** | byte-identical ×2 | `4e791b135e763501` |
| `splash` | 1800x1169 | **1800x1001** (clamped) | byte-identical ×2 | `0f62d114a4a7fafc` |
| `workspace` | 1800x1169 | **1800x1001** (clamped) | byte-identical ×2 | `515dda0d5b1f5681` |

All four are **byte-identical PNGs across two independent windowed processes**, and
reproduce byte-identically across sessions (the staged 1280x720 shas equal a
separately-run determinism sweep). Determinism is stronger than the tier-c bar
(no threshold slack needed). Comparator self-test: **identity PASS, cross-state
FAIL** (splash vs workspace differ 24.2% / 12.6% of pixels over 0.016 — far above
the 1% bar). Full 64-hex shas in `manifest.tsv`.

- **splash** = the startup Quick Setup splash overlaid on the default cube.
- **workspace** = the post-splash default Layout: cube (selected) + camera + light,
  Blender Dark theme, outliner + properties. See `goldens/`.

## Exact invocations

Native pin: `oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender` (Blender
5.2.0 LTS, Cocoa+Metal — same oracle the corpus/m5/m6 goldens use). Comparator:
`oiiotool` 3.1.16.0 (`/opt/homebrew/bin/oiiotool`).

Capture (per state, run twice, staged only if byte- or threshold-identical):

```
BLENDER_USER_CONFIG=<empty-tmp-dir> \
oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender \
  -p 0 0 W H --factory-startup --no-native-pixels --no-window-frame \
  --python sandbox/m4-golden-prep/m4_capture.py -- \
  --out <png> --mode <splash|workspace> --delay 1.0
```

Run the whole staging: `bash sandbox/m4-golden-prep/capture_m4_golden.sh all`.
Compare a wasm candidate:
`bash sandbox/m4-golden-prep/compare_m4.sh <candidate.png> <state> <WxH>`.
Self-test: `bash sandbox/m4-golden-prep/compare_m4.sh --selftest`.

### How each state is produced (mechanics, verified against the pin)

- A real window opens briefly per run (macOS has no headless GUI backend — same as
  m5-prep). `--no-native-pixels` forces `pixel_size 1` so the window content is
  1:1 with the requested size (no HiDPI doubling) and the UI is at scale 1×.
- Capture is Blender's **own** `bpy.ops.screen.screenshot(filepath=…)`, which reads
  the window client-area framebuffer (`WM_window_pixels_read`,
  `screendump.cc:70`) — exactly what `canvas.toDataURL()` reads on the wasm side.
  It forces a full `WM_redraw_windows` before reading (`screendump.cc:69`), so the
  `--delay` only has to cover startup, not draw-settle.
- **splash**: the startup splash auto-shows (`WM_init_splash_on_startup`,
  `creator.cc:661`); we just screenshot it. `WM_redraw_windows` does NOT strip it
  (that comment refers to transient menus) — verified: the splash composites into
  the capture. The **fresh** variant ("Quick Setup" + **Continue**, no import
  button) is forced by `BLENDER_USER_CONFIG=<empty dir>`: that makes
  `PREFERENCES_OT_copy_prev.poll()` return False (env-override branch,
  `userpref.py:154-159`) ⇒ `can_import=False` (`wm.py:3360`), the same layout a
  fresh-OPFS wasm boot draws. (`--factory-startup` alone is NOT enough on a host
  that has a prior-version Blender config — it would show "Import Blender 4.5
  Preferences".)
- **workspace**: the driver sets `preferences.view.show_splash = False` at module
  scope. `--python` (ARG_PASS_FINAL) runs BEFORE `WM_init_splash_on_startup`, so
  `USER_SPLASH_DISABLE` is set in time and the splash never appears — a clean
  default Layout with **no popup to dismiss and no event injection**. (ESC / click
  via `event_simulate` did NOT dismiss the already-open splash — it is
  `BLOCK_KEEP_OPEN`, `wm_splash_screen.cc:299`; `read_homefile` clears
  `bpy.app.timers` and hangs the capture. Suppress-before-show is the robust path.)

## Determinism receipts

Two independent processes per (state,size); PNGs compared by sha256 then, on a
mismatch, by `oiiotool … --fail 0.016 --failpercent 1 --diff`. **All four are
byte-identical** (see table). Non-determinism sources considered and cleared:
no cursor in the capture (front-buffer read excludes the OS HW cursor and no mouse
is moved into the window), no clock/animated element in either state, static
splash artwork, deterministic FreeType text. GPU (Metal) viewport shading was
byte-stable here; the 0.016/1 threshold is the fallback if a future host shows LSB
jitter.

## What the wasm side must produce (the M4 gate command)

For each state the wasm build must emit a **PNG** captured from the canvas
(`canvas.toDataURL('image/png')` or an OffscreenCanvas read — the WebGPU
front/backbuffer, matching `screen.screenshot`), then:

`compare_m4.sh <candidate.png> <state> <WxH>` → exit 0 = within tolerance.

Hard requirements:
1. **Exact size.** The canvas must be **exactly** the golden's `WxH`
   (1280×720 available now). A 1px difference makes `oiiotool` a size mismatch ⇒
   FAIL — the canvas is being made size-deterministic this round; that is why.
   Use `1280x720` as the arg (see the 1800 caveat below).
2. **Two states.** `splash` (startup Quick Setup over the cube) and `workspace`
   (default Layout, splash suppressed/dismissed). Fresh OPFS (no prior-version
   config) so the splash is the "Quick Setup / Continue" variant — matches the
   golden. If OPFS ever carries a prior config, the splash gains an import button
   and mismatches; keep the first-pixels capture on a fresh profile.
3. **Channels.** RGB or RGBA both work — `compare_m4.sh` reduces both sides to
   `R,G,B` (`--ch R,G,B`) before the diff, because the native golden is 3-channel
   RGB (`screendump.cc:120`) and `toDataURL` is 4-channel RGBA; without this the
   golden's absent alpha diffs as 0 and 100% of pixels spuriously fail.

## Native-vs-web deltas to watch

- **Splash variant** (above): env-controlled on native, environment-controlled on
  wasm (fresh OPFS). Both must land on "Quick Setup / Continue".
- **Rosetta warning**: native has an Apple-only splash warning
  (`wm_splash_screen.cc:368-403`) that shows only under Rosetta. Our native pin is
  arm64 ⇒ absent; wasm never compiles the `__APPLE__` path ⇒ absent. No delta, but
  if goldens are ever re-cut on an x86-emulated host the warning would pollute.
- **GPU adapter**: native Metal vs wasm WebGPU is **not** bit-exact — tier-c is not
  a bit-exact bar. The 0.016/1 idiff threshold is the cross-adapter absorber; the
  M4 gate is stated "on the pinned CI adapter". Expect the real wasm-vs-native diff
  to be non-zero (viewport gradient, cube workbench shading, text AA) but under
  threshold; if it exceeds 1% of pixels, that is a real backend bug, not golden
  drift.
- **wasm boot chrome**: any wasm-only overlay at boot — an OPFS/file-access
  permission dialog, a "loading assets" splash, an asset-browser prompt — would
  composite into `toDataURL` and pollute the capture. It must be gone before the
  M4 capture. Flagged because it has no native analogue.
- **Version string**: splash top-right "5.2.0 LTS" and status-bar "5.2.0" must
  match (both sides pin 5.2 @ `fbe6228777e7`).

## The 1800×1169 constraint (host display clamp)

`1800×1169` was requested but the capture host (3024×1964 Retina, main display)
clamps window **content height to ~1001px** — even a 1100 request returns
1800×1001, deterministically. So the "large" goldens are staged at their **true**
1800×1001 (named by actual size; the capture script WARNs and never mislabels).
A genuine 1800×1169 native golden needs a capture host / CI runner with ≥1169px
usable display height; then it is one command:
`bash sandbox/m4-golden-prep/capture_m4_golden.sh splash 1800 1169` (and
`workspace`). The comparator is size-parameterized, so adding sizes is free.
**Use 1280×720 as the primary M4 gate size** — it is within bounds, exact, and
byte-identical.

## Files

- `sandbox/m4-golden-prep/m4_capture.py` — in-Blender `--python` driver.
- `sandbox/m4-golden-prep/capture_m4_golden.sh` — windowed capture + determinism +
  staging (names goldens by actual dims).
- `sandbox/m4-golden-prep/compare_m4.sh` — the gate comparator (oiiotool
  0.016/1 verbatim + `R,G,B` normalization; exit-code-primary; `--selftest`).
- `sandbox/m4-golden-prep/goldens/{splash,workspace}_{1280x720,1800x1001}.png`.
- `sandbox/m4-golden-prep/manifest.tsv` — state → size → golden → thresholds → sha.

**Boundary note:** staged goldens stay under `sandbox/m4-golden-prep/`. Installing
them into `tests/golden/` is a driver-at-boundary action — NOT done here.
