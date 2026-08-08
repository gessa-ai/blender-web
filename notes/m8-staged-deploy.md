<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 staged-deploy - staged loading made REAL in the deploy bundle

**Date:** 2026-08-08 · **Repo HEAD at assembly:** `156350d` · **Lane:** m8-staged-deploy ·
**Ports:** 8130 (deploy verify), 8127 (scratch). Builds on the deploy-prep lane
(`sandbox/m8-deploy/`, prepare-only monolith bundle, commit `5b46e50`) and the
staged-loading DESIGN (`notes/m8-staged-loading.md`).

## Outcome (headline)

The shipped deploy bundle now **boots on the stage-0 critical payload and streams the
rest after first pixels**, instead of blocking on the full `.data` preload - done
entirely in the DEPLOY BUNDLE ASSEMBLY, with **no relink** and **no edit to any shared
build tree** (the windowed-opt binary is read-only input; only a COPY of the glue is
rewritten in the bundle). Boot integrity is preserved: the staged bundle reaches
WM_main, presents pixels, renders the full Blender UI, runs a `?pyexpr`, and a
deferred-stage asset is proven to load byte-exactly and become functional after the
stream.

- **Critical data on the wire (brotli-q11): 35.28 MB (monolith) -> 15.31 MB (stage-0) = -56%.**
- **Wire-to-interactive (wasm+glue+critical-data, brotli): 57.5 MB -> 37.5 MB = -35%**
  (stage-1 = 18.28 MB brotli, streamed off the critical path).
- On localhost, boot time is unchanged (download is not the bottleneck there); the win
  is download-bound and shows under a constrained link (throttle table below).

## Mechanism (how, and why THIS way)

The emscripten `--preload-file` payload is a bare byte-concatenation; the glue carries
the manifest inline as `loadPackage({files:[{filename,start,end}...],remote_package_size:N})`
and one blocking fetch of `blender_browser.data` gates `run()`/`main()`. To make boot
block on stage-0 only, without relinking:

1. **`stage_pack.py`** re-slices the monolith `blender_browser.data` into
   `stage0.data` (KEEP files, re-offset) and `stage1.data` (DEFER files), drops DROP
   files, and **rewrites the baked manifest in a COPY of the glue**: KEEP entries get
   new offsets into `stage0.data`; every DEFER entry becomes a **zero-length placeholder**
   `{...,start:0,end:0}`; `remote_package_size` becomes `len(stage0.data)`. The bundle's
   `blender_browser.data` is now stage-0 only, so the baked preload downloads/instantiates
   only stage-0.
2. **Why zero-length placeholders and not just fewer files:** the preload root `/bw` is
   mounted **mode 0555** and **directory creation fails post-boot from BOTH threads**
   (recon: `FS.mkdir`, `FS.mkdirTree`, the exported `FS_createPath`/`FS_createDataFile`,
   and Python `os.makedirs` all fail with `FS error` / `EACCES`). But **writing a new or
   existing file into a directory that already exists WORKS** (`FS.writeFile`, and
   overwriting a preloaded file, both verified). So stage-0 must pre-create the *entire
   directory tree* stage-1 needs; the placeholders do exactly that at preload time.
3. **`stage1-loader.js`** (injected after `boot-windowed.js`, bundle-only) waits for
   `__bwModule` + first pixels, fetches `stage1.data` + `stage1-manifest.json`, and
   `FS.writeFile`s each deferred file into its now-existing directory (chunked, yields
   between batches so the WM loop keeps breathing). `?stage1=manual` /
   `window.__BW_STAGE1_MANUAL` disables the auto-schedule for controlled tests.

Directory creation is impossible post-boot, but file writes into existing dirs are not -
so the placeholder set + `FS.writeFile` stream is the whole trick. No relink needed
because the manifest lives in the glue text, and the bundle owns its glue copy.

## The stage split (oracle-validated, from notes/m8-staged-loading.md sec 2-3)

`stage_pack.py classify()`:
- **DROP** (neither stage): `__pycache__`/`.pyc` (already pruned upstream), pip `.whl`.
- **DEFER** (-> stage-1): dead stdlib not imported at `--factory-startup` (asyncio,
  tkinter, idlelib, unittest, sqlite3, pydoc_data, ...); addons whose `register()` does
  NOT run at boot (rigify, node_wrangler, ...); CJK/intl fonts (keep Inter +
  DejaVuSansMono); colormanagement display LUTs except the default AgX-sRGB path
  (`config.ocio` + `AgX_Base_sRGB.cube` + the two default `.spi1d`). `[--defer-datafiles]`
- **KEEP** (-> stage-0): everything else - all enabled addons, imported stdlib, bfont,
  Latin UI fonts, the default AgX display path.

Measured split (current `build-wasm-windowed-opt/bin`, 3304 manifest entries, 85.20 MB data):

| bucket | files | raw | note |
|---|---:|---:|---|
| KEEP (stage-0) | 2814 | 44.21 MB | boot-critical |
| DEFER (stage-1) | 489 | 39.07 MB | fonts (CJK 11.4 MB), LUTs (~19 MB), rigify, dead stdlib |
| DROP | 1 | 1.79 MB | pip wheel |

**Datafiles-defer risk cleared:** the biggest DEFER wins (CJK font, non-default LUTs)
were the correctness risk (OCIO eager-validating a deferred LUT at `config.ocio` parse,
or the English UI demanding a deferred glyph). The staged bundle **boots clean and
renders the full UI** with them deferred (screenshot below), so the aggressive defer is
safe for the English `--factory-startup` path. A `--no-defer-datafiles` variant (stage-0
= 72.7 MB, stage-1 = 6.7 MB) exists as the conservative fallback; it was not needed.

## Wire sizes (brotli-q11; wasm brotli-q10)

| file | raw | brotli | stage |
|---|---:|---:|---|
| `blender_browser.wasm` | 100.13 MB | 22.15 MB (q10; RANKING q11 = 20.13) | critical (unchanged) |
| `blender_browser.js` (glue) | 0.59 MB | 0.075 MB | critical |
| `blender_browser.data` = **stage-0** | 44.21 MB | **15.31 MB** | critical |
| `stage1.data` | 39.07 MB | **18.28 MB** | deferred |
| monolith `.data` (baseline) | 85.20 MB | 35.28 MB | (was all-critical) |

- **Wire-to-interactive:** monolith 57.5 MB brotli -> staged **37.5 MB brotli (-35%)**.
- Still far above LAUNCH.md's <=15 MB bar because the **22 MB-brotli wasm dominates and
  is unchanged** by data staging - exactly the note's standing verdict. Data staging is
  necessary and now real, but wasm shrink / JSPI split (out of this lane) is the gate.

## Measurements (headed node-Playwright, BUNDLED Chromium)

`NODE_PATH=/Users/paws/plushly/game-platform/node_modules`; bundled Chromium
(`ms-playwright/chromium-1228`), never an in-app pane. Metrics from navigation start:
**time-to-WM_main** (the `#state` "main loop (WM_main)" marker == emscripten runtime
initialized, gated on the wasm+data preload) and **time-to-first-pixels** (GHOST's
`presentBackbuffer frame 0`). 3 runs each; median reported. Cold = fresh browser context
(empty HTTP+wasm cache + empty OPFS). Warm = same context, one warm-up load then measured
reloads (production cache policy: `bin/*` `max-age=3600`). Both bundles built from ONE
frozen binary snapshot (`sandbox/m8-staged-deploy/snapshot-bin/`, glue md5 94f2720...)
so the comparison is apples-to-apples and immune to the concurrent gpu-lane relinks.

### Un-throttled (localhost) - download is NOT the bottleneck here

| scenario | bundle | time-to-WM_main (median) | time-to-first-pixels (median) | WM runs |
|---|---|---:|---:|---|
| cold | monolith | 460 ms | 2720 ms | 337,460,612 |
| cold | staged   | 562 ms | 2860 ms | 298,601,562 |
| warm | monolith | 277 ms | 2169 ms | 271,282,277 |
| warm | staged   | 220 ms | 2129 ms | 253,220,220 |

Honest reading: on localhost the two are **within run-to-run noise** - as expected, since
localhost download is ~instant and boot is dominated by wasm compile + BPY init, not by
the 85->42 MB data reduction. Staging does not (and cannot) speed up a boot that is not
download-bound. Its win is the wire, which localhost hides.

### Throttled cold (CDP 1.5 MB/s "4G", served BROTLI as Cloudflare would) - the real win

CDP `Network.emulateNetworkConditions` at 1.5 MB/s down / 0.75 up / 40 ms; server sends
the `.br` files with `Content-Encoding: br` so the throttle measures the REAL compressed
wire (as Cloudflare Pages serves it). Very low variance (download-bound).

| scenario | bundle | time-to-WM_main (median) | time-to-first-pixels (median) | WM runs |
|---|---|---:|---:|---|
| cold, 1.5 MB/s, brotli | monolith | **39,005 ms** | **41,263 ms** | 39005,38970,39100 |
| cold, 1.5 MB/s, brotli | staged   | **25,468 ms** | **27,771 ms** | 25470,25465,25468 |
| **staged win** | | **-13,537 ms (-35%)** | **-13,492 ms (-33%)** | |

This is the payoff: at 4G, staging cuts time-to-interactive by **~13.5 s (a third)**,
exactly tracking the 20 MB brotli wire delta (20 MB / 1.5 MB/s = 13.3 s). Both remain far
above LAUNCH.md's 5-8 s bar because the 22 MB-brotli wasm alone is ~15 s at this link -
the wasm-shrink gate again, unaffected by data staging. Warm boots are unaffected by the
link (cache hit), so warm has no throttled row.

## Functional integrity of the staged bundle (verify_staged.mjs, PASS)

Boot on stage-0 ALONE, gate 1280x720, `?stage1=manual`:
- `crossOriginIsolated=true`, `SharedArrayBuffer=true`; **WM_main in ~167-210 ms**;
  `presentBackbuffer` fired; `window.__bwModule` exposed; gate backing exactly 1280x720.
- **`?pyexpr` runs inside WM_main:** marker `PYEXPR_OK bpy=5.2.0 LTS` (a timer the boot
  argv `--python-expr` registered wrote it).
- **Full UI renders** on stage-0 with fonts/LUTs deferred: menu bar + workspace tabs,
  toolbar, 3D viewport (grid, axes, camera+light gizmos, nav gizmo), outliner,
  properties with live Transform fields, timeline, and the exact `5.2.0 LTS` splash art
  with crisp Latin fonts - no missing-glyph boxes, no broken color path. Screenshot:
  `sandbox/m8-staged-deploy/artifacts/staged_boot_1280x720.png` (+ `.license`, CC0-1.0).
- **Deferred-stage asset loads (the concrete probe):**
  `/bw/python/lib/python3.13/asyncio/tasks.py` - `FS.stat().size == 0` after stage-0 boot
  (placeholder), then after the stage-1 stream `== 39757` bytes and **byte-identical** to
  its slice in `stage1.data`.
- **...and is functional:** deferred `pydoc_data.topics` (a pure-data module, no `print`,
  no `inspect`->`dis` dependency) is unusable before the stream and imports with
  `len(topics)==80` after it (`import` re-run after `del sys.modules[...]`).

Stage-1 stream itself: 489 files / 39.07 MB fetched in ~59 ms + unpacked (FS.writeFile)
in ~85 ms on localhost; on the 1.5 MB/s link the 18.28 MB brotli stage-1 is ~12 s of
background transfer, entirely after first pixels.

### Benign boot debts (identical in monolith and staged - NOT staging regressions)

The staged boot carries the same debts the monolith already has (A/B-confirmed by
booting both): `inspect.py`'s `import dis` fails because **`dis.py` is absent from the
CPython trim in the build payload** (present in NEITHER `.data`), so a few boot-time addon
registrations (`pose_library`, `bl_pkg` via `dataclasses`->`inspect`) log a caught
traceback; plus the known OIIO `physical_memory` assertion and the multiprocessing "no
Python binary" line. All are caught; boot proceeds to WM_main + present in both bundles.
Staging changes payload timing only, not boot behavior. (Flagged for the build/python
lane, not fixed here - out of this lane's scope.)

## Deploy-flow wiring (deliverable 1) - the exact commands

The blender-web "deploy flow" is: assemble a static bundle -> Cloudflare Pages (Pages
brotli-compresses at the edge; you upload raw). `make_staged_bundle.sh` is the staged
evolution of the deploy-prep `make_bundle.sh` (which the deploy-prep README already
anticipated as additive).

```
# 1. Assemble the uploadable STAGED bundle (real file copies; reads the build tree
#    read-only; rewrites only the bundle's glue copy). Defer datafiles by default.
sandbox/m8-staged-deploy/make_staged_bundle.sh --copy
#    conservative variant (keep fonts/LUTs in stage-0):
sandbox/m8-staged-deploy/make_staged_bundle.sh --copy --no-defer-datafiles
#    override the source build dir with --bin DIR or $BLENDER_WEB_BIN.

# 2. Serve COOP/COEP-isolated for local verify (port 8130).
python3 sandbox/m8-deploy/serve_bundle.py 8130 sandbox/m8-staged-deploy/bundle-staged

# 3. Boot + integrity verify (headed bundled Chromium).
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/m8-staged-deploy/verify_staged.mjs 8130

# 4. (measurement) production cache policy + brotli transfer; then measure.
python3 sandbox/m8-staged-deploy/serve_measure.py 8130 sandbox/m8-staged-deploy/bundle-staged
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/m8-staged-deploy/measure_boot.mjs 8130 staged 3
```

On Cloudflare Pages: upload the `bundle-staged/` dir; Pages serves `bin/*` brotli at the
edge (do NOT upload the `.br` files - those are only for local throttle measurement).
`bundle-staged/_headers` carries COOP/COEP/CORP + the `.json` rule for
`stage1-manifest.json`. The stage-1 fetch is same-origin, so CORP `same-origin` still
holds.

## Files (this lane; all SPDX-tagged; `sandbox/m8-staged-deploy/`)

| file | role |
|---|---|
| `stage_pack.py` | re-slice monolith -> stage0.data + stage1.data + rewritten glue manifest |
| `make_staged_bundle.sh` | assemble the staged bundle (calls stage_pack.py; injects loader) |
| `stage1-loader.js` | deferred STAGE-1 streamer (FS.writeFile into pre-created dirs) |
| `verify_staged.mjs` | boot + pyexpr + deferred-asset (byte-exact + functional) + capture |
| `measure_boot.mjs` | cold/warm + throttled boot timing (WM_main + first-pixels) |
| `serve_measure.py` | COOP/COEP server w/ prod cache policy + brotli Content-Encoding |
| `recon_fs.mjs`, `recon_fs2.mjs`, `diag_*.mjs` | recon that settled the FS mechanism / channel |

## Residuals / honest caveats

1. **Wasm is the gate, not data.** Wire-to-interactive is 37.5 MB brotli; the 22 MB
   wasm dominates and staging cannot touch it. <=15 MB needs wasm shrink / JSPI split
   (out of this lane; see `sandbox/m8-dce-ranking/RANKING.md`).
2. **Coarse stage-0/stage-1 split**, streamed in bulk after first pixels (the LAUNCH.md
   "stream the rest into cache" pattern), not per-asset on-touch. Fine-grained on-touch
   (a font when a CJK glyph appears, a LUT when that view transform is picked) is the
   WasmFS-fetch-backend follow-up the design note already scoped.
3. **Placeholder window:** deferred Python packages exist as zero-length placeholders
   between stage-0 boot and stage-1 completion (~a few seconds). Nothing imports them at
   boot (oracle-validated), and the stream fills them before any user action would; but a
   module imported inside that window would cache empty. Acceptable for the bulk-stream
   model; the on-touch backend removes it.
4. **No service-worker precache yet** (LAUNCH.md wants it for near-instant reload). The
   `_headers` `max-age` gives warm-cache reuse today; a `/sw.js` precache of stage-0 +
   stage-1 is the additive next step.
5. **`dis.py` absent from the CPython trim** (benign today, caught) - a build/python-lane
   item, not staging.
6. Progress UI: the shell loader honestly reports stage-0 byte progress during the
   blocking preload (emscripten `setStatus` -> `bin/blender_browser.data` = stage-0 only,
   so it is truthful, not a fake 100%); stage-1 streams after the loader is dismissed,
   with honest `window.__bwStage1` state + `[stage1]` console counters. A visible
   post-first-pixels "streaming assets" phase-label is a small polish follow-up.

## Reproduce

```
# freeze a consistent binary snapshot (js+wasm+data from one link), then build both:
SNAP=sandbox/m8-staged-deploy/snapshot-bin
sandbox/m8-deploy/make_bundle.sh --copy --bin "$SNAP" --out sandbox/m8-staged-deploy/bundle-mono
cp platform_web/shell/file-bridge.js sandbox/m8-staged-deploy/bundle-mono/
sandbox/m8-staged-deploy/make_staged_bundle.sh --copy --bin "$SNAP" --out sandbox/m8-staged-deploy/bundle-staged
# verify + measure per the deploy-flow commands above.
```
