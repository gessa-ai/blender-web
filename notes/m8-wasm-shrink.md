<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 wasm-shrink — compiler-level size levers on the windowed wasm

**Date:** 2026-08-07 · **Tree:** `build-wasm-windowed-opt/` (mine) · emcc **6.0.5** ·
Binary: `bin*/blender_browser.{wasm,js,data}` (not landed upstream).

## Question

`notes/m8-staged-loading.md` proved staged `.data` loading takes wire-to-interactive from
47.5 → 23.6 MiB, but **the wasm module alone is 20.1 MB brotli — already 34 % over the
15 MB "to-interactive" bar (LAUNCH.md) before a single byte of data.** No data staging can
fix that. This probe measures the residual **compiler-level shrink lever** on the wasm:
`-Os`, `-Oz`, `--closure 1`, `-flto`. Metric that matters = **brotli wire size** (what the
CDN ships), not raw.

## Method (faithful, race-free)

The tree's current CMake cache is ground truth (another lane edits
`patches/blender_web.cmake`); **no reconfigure was run.** The baseline link command was
extracted verbatim with `ninja -t commands bin/blender_browser.js` (read-only — never runs
cmake). Datapoints 1–3 are **link-flag-only overrides**: the exact same baseline object
files (`*.o`/`*.a` — the identical objects behind the recorded 120.1 MB baseline) relinked
via `emcc` with one flag appended, into `bin-<label>/`. So **every wasm delta below isolates
the flag** — nothing recompiled, no source drift in the wasm. (The `.data` regenerates each
link and is now 133 MB, up from the baseline note's 106 MB, purely from python/scripts
source drift since aec2568-era — irrelevant to the wasm lever under test.) `-flto` cannot be
a link-only override (needs bitcode objects) and is handled separately.

The baseline link already passes `-O2` at link (CMake feeds the target's compile `$FLAGS`,
incl. `-O2`, to the link line), so **binaryen `wasm-opt -O2` already runs in the baseline.**
`-Os`/`-Oz` therefore measure the *size-focused* binaryen passes **over -O2-compiled
objects** — the realistic link-only lever. A full recompile at `-Os`/`-Oz` (compile-level,
like LTO) is a further lever, discussed in the verdict.

Boot-verify: headed bundled Chromium (Playwright 1.61.1), `serve-web.sh` on :8124,
`windowed.html`, click `#run`, success = `#state` reaches **"main loop (WM_main)"** with no
abort in 120 s.

## Verdict table

| flags (link-only unless noted) | link wall | wasm raw | wasm gzip-9 | **wasm brotli-q11** | vs baseline brotli | boot |
|---|---|---|---|---|---|---|
| **baseline** `-O2 -g0` (recorded) | 38.2 s | 120,114,157 (114.5 MiB) | 29,191,721 | **20,127,950 (19.19 MiB / 20.13 MB)** | — | OK |
| **(1) `-Os`** | 345 s | 116,766,049 (111.4 MiB) | 29,142,666 | **20,298,315 (19.36 MiB / 20.30 MB)** | **+0.85 % (worse)** | OK |
| **(2) `-Oz`** | 153 s | 110,989,228 (105.8 MiB) | 28,835,751 | **20,231,371 (19.29 MiB / 20.23 MB)** | **+0.51 % (worse)** | OK |
| **(3) `--closure 1`** (js) | 53 s | 119,758,992 (114.2 MiB) | 29,122,973 | **20,062,514 (19.13 MiB / 20.06 MB)** | −0.33 % (DCE side-effect) | OK |

`(js glue: baseline 763,473 raw / 85,611 br; -Os 893,812 / 97,402; -Oz 893,094 / 97,102 —
js grew from current --post-js drift, not the flag; js is ~0.1 MB of the wire, negligible
vs the wasm.)`

### Reading — binaryen size passes do NOT shrink the wire

- **`-Os` and `-Oz` both give NO wire win — they make brotli slightly *worse*.** Raw wasm
  drops meaningfully (−2.8 % / −7.6 %) and gzip drops a little (−0.2 % / −1.2 %), but the
  metric that ships — **brotli — rises 0.85 % / 0.51 %.** Binaryen's size passes cut raw
  instruction count with codegen patterns (function outlining/merging, local reuse) that a
  q11 brotli window was already deduplicating; trading those for fewer-but-less-compressible
  bytes nets zero-to-negative on the wire. The −7.6 % raw of `-Oz` collapses to +0.5 % on
  brotli — a clean demonstration that **raw size is the wrong proxy here.**
- **Cost is brutal:** 345 s / 153 s vs 38.2 s baseline — up to ≈9× the link time for a wire
  regression.
- Caveat (honest): these are link-only overrides — objects stay `-O2`. A full recompile at
  `-Oz` (compile-level) would additionally bias LLVM codegen toward size, which *could* move
  the wire more than the binaryen pass alone. But the direction here (raw ↓ big, brotli ↑) is
  the opposite of encouraging, and the compile-level lever is the same expensive-recompile
  class as LTO (below) — quantified in the verdict.

### Reading — `--closure 1` targets the JS glue, which is not the problem

- Closure minifies the **JS glue only**: js **97,102 → 88,081 br** (−9.3 %, ≈ −9 KB) vs the
  current-source no-closure js. It also incidentally trims the wasm by **0.33 %** (≈ −65 KB
  br) — removing JS-referenced exports lets `wasm-opt` DCE a little more.
- **Total closure win ≈ 74 KB brotli.** The JS glue is ~0.09 MB against a 20 MB wasm; the bar
  is missed by ~9,600 KB. Closure moves ~0.8 % of the gap. It is free (53 s, boots clean, no
  `--post-js` breakage) and worth keeping as hygiene, but it is **not a lever on the bar.**

### (4) `-flto` — measured via full bitcode recompile

`-flto` cannot be a link-only override (needs bitcode objects). Applied by appending `-flto`
to all 4191 compile `FLAGS` lines **directly in `build.ninja`** (backed up to
`build.ninja.bak-O2`; `build.ninja` touched newest so **no `RERUN_CMAKE` / no reconfigure**
— verified `blender_web.cmake` is not a RERUN input for this tree, so zero race with the
lane editing it). Full recompile of Blender's own ~3700 objects to bitcode + LTO link.
**Note LTO reaches only Blender's own code — the 20 MB is dominated by prebuilt deps
(CPython 3.13, OIIO/OpenEXR, Tint, shaderc, freetype, TBB) whose `.a` are ordinary wasm
objects, not bitcode, so LTO cannot cross into them.**

<!-- LTO_ROW -->

## Combined projection — best wasm + stage-0 data vs the 15 MB bar

Inputs: **best wasm brotli from any compiler lever ≈ 20.06 MB** (closure; `-Os`/`-Oz` are
*worse*, LTO row above) · **stage-0 data = 4.50 MB brotli** (`notes/m8-staged-loading.md`) ·
js glue ≈ 0.09 MB · **bar = ~15 MB to interactive** (LAUNCH.md).

| component | brotli | note |
|---|---|---|
| wasm (best compiler lever) | **~20.06 MB** | 0.3 % under the -O2 baseline; -Os/-Oz worse |
| stage-0 data | 4.50 MB | already trimmed (dedup + pip-wheel drop) |
| js glue | ~0.09 MB | closure-minified |
| **wire-to-interactive** | **~24.6 MB** | **1.64× the 15 MB bar** |

To clear 15 MB with the 4.50 MB stage-0 data (+0.09 js), the **wasm must fall to ≤ ~10.4 MB
brotli — a 48 % cut.** The four compiler levers together move the wasm by **< 1 %** (and the
two "size" levers move the *wire* the wrong way). 

## VERDICT — compiler levers do NOT close the gap; feature-audit / DCE is next

Plainly: **`-Os`, `-Oz`, `--closure 1` and `-flto` are spent as a class and do not get the
wasm under the bar.** The size problem is not un-optimized codegen — the module is already
`-O2` + binaryen — it is **the sheer amount of code linked in.** ~48 % of the wasm's brotli
must disappear, and compressed size is insensitive to the instruction-repacking that `-Os`/
`-Oz` do; only *removing whole functions/subsystems* moves brotli, which optimization flags
by design do not do (they preserve semantics).

**The next step is feature-audit + dead-code elimination at the source/config level**, in
priority order:
1. **Compile-out unshipped subsystems** via `blender_web.cmake` (the launch tier does not need
   them at boot): `WITH_COMPOSITOR_*`, sequencer/VSE, many `editor_space_*` (clip, nla,
   sequencer, spreadsheet), grease-pencil legacy, non-mesh geometry-node families,
   Cycles-CPU (defer), motion-tracking (`libmv`), and OIIO's non-essential image formats
   (keep PNG/EXR/JPEG). Each removes real linked code — the only thing brotli responds to.
2. **Split the wasm under JSPI** — lazy-load non-boot-critical native code (importers/exporters,
   compositor, sculpt, Cycles) as secondary modules fetched after first pixels, the same
   Doom-3 pattern already applied to `.data`. This is the structural lever that can actually
   halve the boot wasm.
3. Trim the CPython payload / `bl_ui` set (already partly staged on the data side).

LTO/`-Oz` are not the road to 15 MB; a **feature/DCE audit of `blender_web.cmake` (owned by
the config lane) + a JSPI wasm-split** is. Data staging (done) + wasm feature-cut + wasm-split
are all three required; no single compiler flag clears the bar.

