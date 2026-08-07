<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 size-probe — first RELEASE-PROFILE windowed link (-O2 -g0)

**Date:** 2026-08-06 · **Tree:** `build-wasm-windowed-opt/` (mine) · **Binary:**
`build-wasm-windowed-opt/bin/blender_browser.{wasm,js,data}` · not landed in upstream.

## Outcome (headline)

The windowed browser binary previously existed only as a ~921 MB debug-info link. The
first **release-profile** link (`CMAKE_BUILD_TYPE=Release`, link `-O2 -g0`, closure OFF,
LTO OFF) is **120.1 MB raw wasm — a 7.7× reduction — and 20.1 MB over the wire (brotli).**
The whole app is **47.5 MB brotli** (wasm+data+js). It **boots clean in real Chrome**
through GHOST-web → WebGPU device (22 features) → GPU_init → Python/BPY → a stable
`WM_main` loop, with **zero `-O2`-induced failures** (no shader-compile errors, no
unaligned-atomic trap, no aborts; flat JS heap).

**The whole size win is pure debug-info stripping at ZERO codegen change.** This project's
`RelWithDebInfo` and `Release` are both `-O2 -DNDEBUG`; they differ *only* by `-g`. So the
release link is literally "the dev link minus DWARF" — DWARF is ~87% of the debug wasm.
Correctness risk from the delta is therefore nil (stripping `-g` cannot change generated
code); the interesting UB/-O2 questions only begin at `-O3`/LTO (next probes).

## Size table (bytes; MiB in parens)

| profile | artifact | raw | gzip -9 | brotli -q11 |
|---|---|---|---|---|
| **opt** (Release `-O2 -g0`) | wasm | 120,114,157 (114.5) | 29,191,721 (27.8) | **20,127,950 (19.2)** |
| | data | 106,203,547 (101.3) | 41,248,276 (39.3) | **29,602,051 (28.2)** |
| | js   | 763,473 (0.73) | 111,948 | **85,611** |
| | **total** | **227,081,177 (216.6)** | **70,551,945 (67.3)** | **49,815,612 (47.5)** |
| **dev** (RelWithDebInfo `-O2 -g`) | wasm | 926,818,197 (884.0) | 294,114,926 (280.5) | n/a¹ |
| | data | 132,121,409 (126.0) | 54,418,840 (51.9) | n/a¹ |
| | js   | 1,240,344 (1.18) | 161,162 | n/a¹ |
| | **total** | **1,060,179,950 (1011)** | **348,694,928 (332.5)** | — |

¹ brotli skipped on the dev artifacts (922 MB DWARF blob, never shippable; gzip suffices).

- **wasm raw: 926.8 → 120.1 MB = 7.72×.** `.data` and `.js` also shrank, but note the dev
  binary is a **later source revision** (r18-era, patches 0098+) than the opt binary
  (aec2568-era) — so a small part of the `.data`/`.js`/`.wasm` raw delta is source drift.
  The dominant wasm factor is DWARF: `-g0` removes ~800 MB of debug sections; the residual
  120 MB is the actual code+data at `-O2`.
- **Compression ratios (opt wasm):** brotli-q11 = 16.8% of raw (5.97×); gzip-9 = 24.3%
  (4.11×). brotli beats gzip by 31% on the wasm — worth the CDN config.

## Link / build time

| | opt (`-O2 -g0`) | dev (`-O2 -g`) |
|---|---|---|
| link edge wall (`.ninja_log`) | **38.2 s** | 103.8 s |
| full cold `ninja blender_browser` (compile+link) | 657 s (~11 min) | — |

The release link is **2.7× faster** (less to serialize, `wasm-opt` over a far smaller
module, no DWARF to emit). Cold full build was ~11 min on this many-core host at `-O2`
without `-g`/PCH bloat (ccache OFF, matching the dev tree).

## Boot timings & correctness (opt, real Chrome, localhost:8124)

Served `BLENDER_WEB_BIN=build-wasm-windowed-opt/bin scripts/serve-web.sh 8124`,
`windowed.html`, `--factory-startup`, `crossOriginIsolated: true`. Markers are wall-clock
from the Boot-button click (evidence: `sandbox/size-probe/boot-transcript-opt-O2.txt`).

| marker | opt (`-O2 -g0`) | dev baseline (r16 evidence²) |
|---|---|---|
| first Blender stdout (main/WM_init) | 2.46 s | — |
| WebGPU device pre-acquired (22 feat.) | 2.63 s | (present) |
| GHOST surface configured 1800×1169 | 5.75 s | (present) |
| Python/BPY startup | 8.64 s | ~15.5 s (T11 CLOG) |
| splash-image read (Blender clock) | 9.95 s (00:07.173) | (present) |
| first UI composite | **N/A³** | ~visible (Quick Setup splash + Layout) |
| JS heap (steady) | **109.4 MB** (flat 26→174 s) | ~121 MB |
| loop state | stable `WM_main`, exit —, 174 s+ | stable `WM_main` |

² Dev boot baseline is qualitative from the r16 first-pixels evidence
(`platform_web/shell/evidence/m4-first-ui-pixels-*`) — a **later** binary on :8123, not a
same-source A/B. A same-source dev A/B is unnecessary: see the codegen-identity argument.
³ **No UI pixels this run** — the boot log says *"UI pending backend sync_backbuffer"*.
This binary's source (aec2568-era) predates the full UI-composite backend path; the black
canvas is a **source-revision artifact, not an `-O2` regression** (coordinator-confirmed).

### Correctness verdict: PASS for everything `-O2 -g0` can affect

- **GPU_init completes at `-O2`:** device (22 features) + surface (1800×1169 BGRA8)
  configured; surface-proof clear composited (GPU path proven end-to-end on the WM worker).
- **No shader-compile regression.** No shaderc/Tint/WGSL errors through GPU/surface
  bring-up. The full runtime BSL→shaderc→Tint→WGSL chain was *not re-exercised* only
  because this revision doesn't draw UI (no lazy shader compile triggered) — but see the
  0054 note: it cannot regress from this delta.
- **Patch 0054's non-foldable `nan_flt_webgpu` helper — SURVIVES `-O2`.** The helper's
  concern is a constant-folded NaN reaching Tint (which rejects `OpIsNan`/const-NaN). The
  dev link already compiles at `-O2` and renders real UI shaders (r16). The release link
  uses **byte-identical codegen** — `-g`→`-g0` only strips debug sections, it does not
  change the emitted wasm — so the helper (and every shader) behaves exactly as in the dev
  link. No fold is possible that wasn't already possible at dev's `-O2`.
- **No new UB / traps:** no "operation does not support unaligned accesses", no
  `BLI_assert`/`draw_indirect` abort, no Dawn "Render pass has no attachments". Stable loop,
  flat heap (109.3→109.4 MB over ~150 s = no leak signature).
- **Pre-existing debts (non-`-O2`, unchanged):** OIIO `physical_memory` stub; splash imbuf
  unknown-format; Python `cattrs` ModuleNotFoundError (bl_pkg register fails, caught by
  `addon_utils.enable`) — a python-wasm payload gap in this revision, not codegen.

## Recommended next probes (priority order)

1. **`.data` tree-shake / staged loading — highest leverage now that DWARF is gone.** The
   monolithic payload is **47.5 MB brotli** (wasm 19.2 + data 28.2). LAUNCH.md wants
   ≤15 MB-to-interactive with the rest streamed. `.data` is the eagerly-preloaded whole
   `python3.13` stdlib + `scripts/` + `datafiles/` (M4.pre eager-preload debt): trim `bl_ui`
   to a minimal set, drop unused stdlib, and lazy-fetch datafiles. Biggest single win after
   this probe; no rebuild of Blender required, only the preload manifest.
2. **`-Oz`/`-Os` (MinSizeRel = `-Os -DNDEBUG`) for the wasm — the right *size* lever.**
   `-O3` optimizes for *speed* and typically **grows** the wasm (more inlining); it is not
   a size probe. `-Os`/`-Oz` should shave the 120 MB further. This *is* a codegen change, so
   re-run the boot/shader correctness check (the first place `-O2`-vs-lower UB could differ).
3. **`--closure 1` on the JS glue.** Would shrink `blender_browser.js` (86 KB brotli today)
   by maybe half — trivial absolute win (<0.2% of payload) but cheap; verify the shell's
   `--post-js` (wgpu-preinit-worker) survives closure name-mangling before adopting.
4. **LTO — a dedicated *launch-build* probe, never on iteration (GOAL.md).** `-flto` /
   `WITH_COMPILER_LTO` can cross-module DCE/inline for perhaps 10–20% more wasm reduction,
   but link time and memory balloon (dev link is already 104 s; expect many minutes) — do it
   once for the launch artifact, measure size vs link-cost, and re-run full correctness.

## Reproduce

```
BLENDER_WEB_WINDOWED=1 cmake -S upstream -B build-wasm-windowed-opt -G Ninja \
  -C patches/blender_web.cmake \
  -DCMAKE_TOOLCHAIN_FILE=tools/emsdk/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake \
  -DCMAKE_BUILD_TYPE=Release -DWITH_BLENDER_WEB_BROWSER=ON -DCMAKE_EXE_LINKER_FLAGS=-g0
harness/buildwrap.sh ninja -C build-wasm-windowed-opt blender_browser
```

**Exact flag deltas vs `build-wasm-windowed` (dev):** `CMAKE_BUILD_TYPE` RelWithDebInfo→Release
(compile/link `-O2 -g -DNDEBUG` → `-O2 -DNDEBUG`, i.e. drop `-g`); `CMAKE_EXE_LINKER_FLAGS`
`` → `-g0` (explicit DWARF strip). Everything else identical — same `-O2`, same closure OFF,
same LTO OFF, same `--profiling-funcs` (kept for named boot stack traces), same emdawnwebgpu /
OFFSCREENCANVAS / 32 MB-stack / preload flags. Verified in the generated link line:
`-O2 -g0 --profiling-funcs`, no `-g`, no `--closure`, no `-flto`.

**Caveats:** binary built from the aec2568-era tree (predates patches 0098+), so UI-composite
behavior differs from the current dev binary by *source revision*, not by `-O2`. `nice -19`
was requested but is unavailable to non-root on macOS (`setpriority: Permission denied`); the
build ran at default priority (scheduling only — no effect on output).
