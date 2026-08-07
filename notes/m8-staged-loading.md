<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 staged-loading probe — decompose the .data, split stage-0, prove lazy fetch

**Date:** 2026-08-07 · **Tree:** `build-wasm-windowed-opt/` (opt binary, aec2568-era,
`-O2 -g0`) · **Sandbox:** `sandbox/staged-probe/` · **Port:** 8125 · not landed upstream.
Sizes pinned to the **measured** `blender_browser.data` manifest (immune to the concurrent
python-shim churn in `lib/wasm`). MiB = 2^20; MB = 10^6; brotli = brotli-q11.

## Outcome (headline + verdict)

The monolithic `.data` (106.2 MB raw / **28.2 MiB brotli**) decomposes into **62 MiB of
Python code that is shipped THREE-to-FOUR times over** (`.py` source **plus** `.pyc` in all
three optimization levels), ~19 MiB of colormanagement display LUTs, and ~15 MiB of fonts
(11 MiB of which is one CJK file). A boot-critical **STAGE-0** partition — validated against
the native oracle for which stdlib and addons actually load at `--factory-startup` — is
**21.62 MiB raw / 4.29 MiB brotli (4.50 MB).**

| | brotli | vs 15 MB bar |
|---|---|---|
| wasm (opt `-O2 -g0`) | **19.19 MiB / 20.13 MB** | **already OVER by itself** |
| js glue | 0.08 MiB / 0.09 MB | |
| STAGE-0 data | 4.29 MiB / 4.50 MB | |
| **STAGE-0 wire-to-interactive** | **23.57 MiB / 24.71 MB** | **1.6× over** |
| monolith wire (today) | 47.51 MiB / 49.82 MB | 3.2× over |
| STAGE-1 (lazy, deferred) | 23.5 MiB / ~24.6 MB | off critical path |

**VERDICT — achievable on data, but NEEDS WASM SPLIT/SHRINK TOO.** Staged `.data` loading
is necessary and high-value: it takes wire-to-interactive from **47.5 → 23.6 MiB (−50%)** and
pushes 79 MB / ~24.6 MiB-brotli of payload off the critical path, with a working lazy-fetch
mechanism (proven below). But it is **not sufficient** to reach LAUNCH.md's ≤15 MB bar: **the
wasm module alone is 20.1 MB brotli — 34% over the bar before a single byte of data.** No
`.data` staging can fix that. Reaching ≤15 MB requires *also* shrinking the wasm — the `-Oz`/
`-Os` probe (size-probe next-probe #2), LTO (#4), and/or wasm code-splitting under JSPI. Data
staging + wasm-shrink are both required; neither alone clears the bar.

## 1. Decomposition (ranked; from the 4795-entry file_packager manifest)

Top-level: **python 45.48 MiB** (2564 files) · **datafiles 36.56 MiB** (1078) ·
**scripts 18.64 MiB** (1153). Total 100.7 MiB across 4795 files (`.data` file 101.3 MiB;
the small delta is 8 alignment gaps). By bucket, top 10:

| # | bucket | raw MiB | stage | note |
|---|---|---:|---|---|
| 1 | python `__pycache__` (.pyc, ×3 opt levels) | 40.84 | **drop** | opt-0 19.29 / opt-1 11.58 / opt-2 9.97 — redundant: `.py` already shipped |
| 2 | python `.py` sources | 21.14 | 0 | authoritative; keep these (see §2) |
| 3 | datafiles colormanagement `.cube`/`.spi1d` LUTs | 19.21 | mostly **1** | OCIO display transforms; lazy-loaded per-transform |
| 4 | datafiles fonts `.woff2` | 14.67 | mostly **1** | `Noto Sans CJK Regular` 11.16 alone; Latin (Inter+mono) 0.48 |
| 5 | scripts `startup/bl_ui` | 4.61 | 0 | UI panels — registered at boot |
| 6 | scripts `addons_core/rigify` | 3.72 | **1** | NOT enabled at `--factory-startup` (oracle) |
| 7 | ensurepip `pip-*.whl` | 1.70 | **drop** | never needed at runtime |
| 8 | scripts `addons_core/io_scene_gltf2` | 1.49 | 0 | enabled at boot (oracle) |
| 9 | scripts `startup/bl_operators` | 1.46 | 0 | operators — registered at boot |
| 10 | scripts `addons_core/bl_pkg` | 1.28 | 0 | enabled at boot (registers, cattrs-fails, caught) |

## 2. The dominant finding: Python code is shipped 3–4× redundant

- Both `.py` source (21.14 MiB) **and** compiled `.pyc` (40.84 MiB) are packaged. CPython
  needs only one. And the `.pyc` is present in **all three optimization levels**
  (plain/opt-1/opt-2) — 3× the bytecode. So each stdlib module ships up to **4 copies**.
- Wire cost, measured (whole python subtree, brotli-q11): **`.py` sources = 1.83 MiB** vs
  **`.pyc` opt-0 only = 3.04 MiB.** Source both compresses *better* and imports directly.
- **Decision: keep `.py`, drop ALL `__pycache__`.** −40.84 MiB raw at zero import-correctness
  risk (source is authoritative; CPython recompiles to memory). Cost: first-import compile
  CPU at boot — the production-optimal is a single sourceless `.pyc` set (or a `python313.zip`
  zipimport), but that needs a `__pycache__`→flat relayout; `.py`-only is the simpler, smaller
  prototype and is what STAGE-0 below uses.

## 3. The stage split (oracle-validated)

Native oracle (`oracle/bpy.sh --factory-startup`) settled the risky calls:
- **stdlib actually imported at boot:** of a 30-module "obviously-dead" candidate list, only
  **`multiprocessing`** is imported at boot → kept in stage-0. idlelib, tkinter, turtledemo,
  ensurepip, pydoc_data, lib2to3, venv, asyncio, xmlrpc, wsgiref, unittest, sqlite3, curses,
  zoneinfo, distutils, … are **not** imported → stage-1.
- **addons enabled at `--factory-startup`** (their `register()` runs at boot → MUST be
  stage-0): `bl_pkg, io_scene_fbx, io_scene_gltf2, io_anim_bvh, pose_library, io_curve_svg,
  io_mesh_uv_layout` (`cycles` is `WITH_CYCLES=OFF` → not in payload). Deferrable to stage-1:
  **rigify (3.72 MiB — the big one)**, node_wrangler, viewport_vr_preview, ui_translate,
  hydra_storm.

**STAGE-0** = drop `__pycache__` + drop pip wheel; defer dead stdlib, non-enabled addons,
intl/CJK fonts (keep Inter + DejaVuSansMono), and colormanagement LUTs except the default
AgX-sRGB display path (`config.ocio`, `AgX_Base_sRGB.cube`, `AgX_False_Color.spi1d`,
`Guard_Rail_Shaper_EOTF.spi1d`). **STAGE-1** = everything deferred, fetched in the background
after first interactive (or on-demand: a font when a non-Latin glyph appears, a LUT when the
user picks that view transform, an addon when enabled).

### Measured cumulative reduction (data only, brotli-q11 on the endpoints)

| step | files | raw MiB | brotli |
|---|---:|---:|---:|
| S1 drop `__pycache__` (keep `.py`) | 2583 | 59.84 | 23.22 MiB |
| S2 + defer dead stdlib | 2328 | 54.14 | |
| S3 + defer non-enabled addons | ~2200 | ~50 | |
| S4 + defer intl/CJK fonts | | 35.68 | |
| S5 + defer CM display LUTs | | 19.29 | |
| **STAGE-0** (S5 + drop pip wheel, enabled-addon-corrected) | 2174 | **21.62** | **4.29 MiB / 4.50 MB** |
| STAGE-1 remainder | 2621 | 79.07 | ~24.6 MiB |

Note S1 (safe dedup-only) is still 23.22 MiB brotli — barely better than the 28.2 MiB
monolith — because it keeps every font and LUT. **The leverage is in the datafiles defers
(fonts −14.7, LUTs −16) and rigify, not in the pyc dedup's brotli footprint** (source
compresses so well that the 40 MiB of pyc was only ~5 MiB of the brotli). Dedup's win is
mostly *raw* (decode/instantiate memory + first-boot IO), which still matters.

## 4. Mechanism (emcc 6.0.5)

Two options; **file_packager multi-package** is the mature, well-supported one and is what the
build already uses for the single preload:
- **file_packager multi-package** — run `tools/file_packager.py` once per stage to emit
  `stageN.data` + a `stageN.js` loader (the `loadPackage`/`FS_createPreloadedFile` pattern).
  The main module preloads stage-0; stage-1 loaders are `<script>`-injected / fetched after
  first interactive and mount into the same FS. **Validated here:** file_packager (emcc 6.0.5)
  produced a loadable `stage1_probe.{data,js}` (`sandbox/staged-probe/web/stage1_probe.js`).
  Production needs the main link to export the loader helpers
  (`-sEXPORTED_RUNTIME_METHODS+=FS_createPreloadedFile,addRunDependency,removeRunDependency`).
- **WasmFS fetch backend** (`wasmfs_create_fetch_backend`) — true per-file on-demand lazy
  fetch, no pre-partition. More elegant for "fetch a LUT/font/addon exactly when touched", but
  less battle-tested than file_packager and needs a WasmFS backend mount per lazy subtree.
  Recommend file_packager for the coarse stage-0/stage-1 split now; revisit the fetch backend
  for fine-grained on-touch assets (fonts/LUTs) post-launch.

## 5. Lazy-load PROOF (headed bundled-Chromium, :8125, opt binary)

Rig `sandbox/staged-probe/rig_staged.js` (per notes/gpu-r23 recipe). Receipts in
`sandbox/staged-probe/evidence/lazy-load-proof.txt`:

- **Boot:** `coi:true, gpu:true, vis:visible, canvas 1280x720`; reaches `WM_main` (WebGPU
  device 23 features, surface configured). Clean boot (same benign cattrs/imbuf/OIIO debts).
- **Lazy fetch → import:** a **synthetic module absent from `blender_browser.data`**
  (`bw_stage1_probe.py`, unique marker `STAGE1_LAZY_OK_44424edfbc32`) is fetched over the wire
  *after* boot, written into the live WASMFS via the exported `FS` API (main-thread write
  propagates to the `PROXY_TO_PTHREAD` WM worker's shared WASMFS), and **imported by the
  running interpreter** via a `bpy.app.timer` inside `WM_main`:
  `LAZY_LOAD_RESULT OK STAGE1_LAZY_OK_44424edfbc32 file=/bw/python/lib/python3.13/bw_stage1_probe.py`
  This is exactly the stage-1 mechanism — a module not in the boot payload, fetched on demand,
  importable — proven without breaking Python (boot continued to stable `WM_main`).
- Gotcha recorded: `FS.mkdir` under the preload root `/bw` fails ("FS error") from the main
  thread; writing into a pre-existing on-`sys.path` dir works. Timer uses
  `importlib.invalidate_caches()` before import.

## 6. Throttle (CDP, validated)

CDP `Network.emulateNetworkConditions`. Directly measured: the real 4.5 MB `stage0.data.br`
downloads in **3.07 s at 1.46 MB/s** under a 1.5 MB/s (4G) cap — throttle applied correctly.
Time-to-**download**-interactive (add ~5–9 s wasm-compile+BPY boot from the size-probe):

| link | STAGE-0 (24.7 MB) | monolith (49.8 MB) |
|---|---:|---:|
| Fast-3G (0.2 MB/s) | 124 s | 249 s |
| 4G (1.5 MB/s, measured) | 16.5 s | 33.2 s |
| broadband (25 MB/s) | 1.0 s | 2.0 s |

Staging roughly halves download time everywhere, but on mobile links even STAGE-0 is far above
the ≤5–8 s bar because the 20 MB wasm dominates. On broadband the bottleneck flips to the
wasm-compile/boot compute (~2.5 s to first stdout, ~8.6 s to BPY per the size-probe).

## 7. What productionizing needs

1. **Wasm shrink is the gating item** (not this probe's scope): `-Oz`/`-Os` + LTO, and/or
   JSPI-compatible wasm code-splitting, to get the 20.1 MB brotli wasm toward the bar.
2. **Relink stage-0-only preload** + export the file_packager loader helpers; ship `stage1.js`
   loaders fetched after first interactive with a real progress UI (MB counters, phase labels).
3. **Confirm the aggressive datafiles defers before shipping them:** trace that OCIO does not
   eager-validate the deferred `.cube`/`.spi1d` at `config.ocio` parse (else missing files =
   boot break), and that the default English UI never demands a deferred font glyph before the
   first composite. Both are the last correctness risks in STAGE-0.
4. **Service-worker precache** stage-1 packages (Photoshop's ~75% reload-init cut).
5. Consider the WasmFS fetch backend for on-touch fonts/LUTs (finer than the coarse split).
6. Production Python payload: single sourceless `.pyc` set or `python313.zip` zipimport for the
   best size/boot-speed balance (vs the `.py`-only prototype here).

## Reproduce

```
# decompose (manifest already extracted to sandbox/staged-probe/manifest_raw.txt):
python3 sandbox/staged-probe/decompose.py sandbox/staged-probe/manifest_raw.txt
python3 sandbox/staged-probe/measure_stages.py s1 s6 stage1 pyonly pyc0   # brotli the endpoints
python3 sandbox/staged-probe/extract_artifacts.py                          # writes web/stage0.data, stage1.data
brotli -q 11 -f -o sandbox/staged-probe/web/stage0.data.br sandbox/staged-probe/web/stage0.data
# serve + prove:
BLENDER_WEB_SHELL=$PWD/sandbox/staged-probe/web BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin \
  scripts/serve-web.sh 8125
PW=<path>/node_modules/playwright node sandbox/staged-probe/rig_staged.js
```

**Caveats:** opt binary is aec2568-era and draws no UI pixels ("UI pending backend
sync_backbuffer") — a source-revision artifact, not this probe's variable; STAGE-0 here is the
*payload to reach the point at which a UI-working build composites the splash*, measured by
wire bytes, not by a captured splash pixel (the current dev build's composite is blocked in the
GPU lane, r24). Sizes pinned to the measured `.data`; a python-shim landing in `lib/wasm`
mid-probe does not move these numbers.
