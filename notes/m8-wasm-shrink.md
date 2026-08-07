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

_(rows for --closure 1 / -flto appended as measured)_
