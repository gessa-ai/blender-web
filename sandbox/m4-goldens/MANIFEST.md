<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# M4 golden candidates — native reference captures (MANIFEST)

Native reference images the M4 "first pixels in a tab" gate will be diffed against.
GOAL M4 gate: *splash + default cube (cube/camera/light, correct theme) matches the
native golden within idiff threshold on the pinned CI adapter.* These are **candidate**
goldens staged in `sandbox/`; the orchestrator installs the chosen set into
`tests/golden/` at the boundary (that path is lock-protected — nothing here writes it).

## Source binary (the pin-verified official build)

| fact | value |
|---|---|
| path | `oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender` |
| version | Blender **5.2.0 LTS** |
| build hash | **fbe6228777e7** (== `oracle/PIN`, == upstream HEAD) |
| build branch | `blender-v5.2-release` · build date 2026-07-14 · type Release · platform Darwin |
| binary sha256 | `60ba7a9b6743f7acf101274361fa76409e382ae07cd2007ce07dea30f6b129f2` |
| binary size | 183237520 bytes |

Official Blender Foundation macOS build (Info.plist: "5.2.0 2026-07-14, Blender
Foundation"); already present in `oracle/` — no download performed. This is the
**GUI-capable** build (Python + UI), unlike `build-native-gpu` (PYTHON=OFF, headless).
Run read-only; all outputs written under `sandbox/m4-goldens/` (oracle/ not modified).

## Capture host / display / scale facts (retina matters)

| fact | value |
|---|---|
| display | Built-in Liquid Retina XDR, 3024 x 1964, Retina |
| `preferences.system.pixel_size` | **2.0** (== backing scale / devicePixelRatio) |
| `preferences.system.ui_scale` | 2.0 |
| `preferences.system.dpi` | 144 |
| GPU backend (native oracle) | **Metal** (Apple). NOTE: the M4 gate adapter is the *pinned CI adapter*; these are captured on Metal — treat as content/layout reference, re-shoot on the CI adapter at install if bit-tolerance demands. |
| window geometry requested | `--window-geometry 0 0 1280 720` (points) |
| screenshot output | **2560 x 1440** px = 1280x720 × pixel_size 2.0 (retina-scaled window pixels) |
| render.opengl / render.render output | **1280 x 720** px (scene render resolution — screen/retina-INDEPENDENT) |

## The captures

Render resolution for B/C set to **1280x720 @100%** by the capture script.
(NB: `facts.*.json` records `render_res` = 1920x1080 because it samples the scene
*before* the script overrides it — the authoritative output dims are the file dims below.)

| file (canonical = run1) | what | how | engine | dims | sha256 (run1) |
|---|---|---|---|---|---|
| `out/D_fullwindow_splash.run1.png` | **the M4 gate frame**: full window, Layout WS, Blender-Dark theme, default cube/camera/light + **splash on top** | `screen.screenshot`, factory-startup | Solid/workbench viewport | 2560x1440 | `3d69aaa9…83322b` |
| `out/A_fullwindow_nosplash.run1.png` | full window, splash suppressed (post-splash steady state; M5 seed) | `screen.screenshot`, opening `default_cube.blend` | Solid/workbench viewport | 2560x1440 | `2efeb74e…33ff6da` |
| `out/B_viewport_workbench.run1.png` | default-view **workbench viewport** of the cube (retina-independent viewport golden) | `render.opengl(view_context=True)` | Workbench (Solid) | 1280x720 | `a37e66f6…41c14e` |
| `out/C_eevee_cube.run1.png` | **EEVEE** camera render of the cube (M6 seed) | `render.render` | `BLENDER_EEVEE` (EEVEE-Next), 16 TAA samples | 1280x720 | `ddcbfdb1…11b39c1` |

`run2` replicas are kept alongside each for independent determinism re-checking.
Input artifacts: `default_cube.blend` (sha256 `234da896…306c4`, factory startup saved
headless — opening it suppresses the splash), `capture.py` (the reproducible driver).

## Exact flags

```
# default-cube scene (splash-suppression input), headless:
Blender --background --factory-startup \
  --python-expr "import bpy; bpy.ops.wm.save_as_mainfile(filepath='.../default_cube.blend')"

# clean captures (A full-window-no-splash, B viewport, C eevee) — splash suppressed by loading a file:
Blender --factory-startup .../default_cube.blend --window-geometry 0 0 1280 720 \
  --python capture.py -- clean <run> .../out

# splash capture (D — the M4 gate frame) — factory-startup shows the first-run splash:
Blender --factory-startup --window-geometry 0 0 1280 720 \
  --python capture.py -- splash <run> .../out
```

## Determinism verdicts (two runs per capture)

Method: `sha256` of the PNG file (byte-compare), `oiiotool --diff` at its strict default
(failthresh 1e-6 → any real ≥1/255 pixel diff fails), and sha256 of the decoded pixels
re-encoded to metadata-free PPM (definitive pixel identity).

| capture | PNG bytes | decoded pixels | verdict |
|---|---|---|---|
| A_fullwindow_nosplash | **identical** (sha256 match) | identical | **fully deterministic** |
| D_fullwindow_splash | **identical** (sha256 match) | identical | **fully deterministic** |
| B_viewport_workbench | differ (6 bytes) | **identical** (PPM sha256 match) | **pixel-deterministic** |
| C_eevee_cube | differ | **identical** (PPM sha256 match) | **pixel-deterministic** |

B/C's file-byte difference is isolated to a PNG `tEXt` ancillary chunk (Blender
render-stamp / save metadata); the `IDAT` pixel stream is byte-identical. EEVEE-Next on
Metal with fixed 16 TAA samples reproduced pixel-exact run-to-run.

## idiff sanity (Blender's own thresholds)

- **Self-diff sanity:** `idiff A.run1 A.run1` → **PASS** (0 divergence) — confirms the
  comparison baseline.
- **Cross-run** `idiff -fail 0.016 -failpercent 1 run1 run2` → **PASS** for all four
  (matches the GOAL tier-(c) thresholds `fail_threshold 0.016`, `fail_percent 1`).

Tools: Homebrew OpenImageIO **3.1.16.0** (`oiiotool` + `idiff` at `/opt/homebrew/bin`).
The project-pinned `lib/macos_arm64/openimageio/bin/oiiotool` has an `@rpath/libOpenEXR`
load error in isolation — use the harness's OIIO env, or the homebrew tool (idiff/oiiotool
diff math is version-independent for these thresholds).

## Caveats for the M4 lane / boundary install

- **Retina:** the full-window screenshots (A/D) are 2× the logical window (2560x1440 for a
  1280x720 window). The browser canvas golden must match at the SAME devicePixelRatio, or
  re-shoot at the target DPR. The `render.opengl`/`render.render` goldens (B/C) are
  DPR-independent (scene-resolution) and are the safer diff targets for viewport pixels.
- **Adapter:** captured on Apple **Metal**. Bit-exact across GPUs is explicitly *not* the
  GOAL bar; the pinned-CI-adapter install may re-capture for the final tolerance baseline.
- **Splash content:** D shows the 5.2 **first-run setup splash** (no prior 5.2 config under
  factory-startup: "Import Blender 4.5 Preferences" / theme=Blender Dark / keymap=Blender).
  Deterministic here; if the gate wants the *regular* splash (recent files/templates), that
  needs an existing userpref and is not factory-deterministic — flag for the gate author.
