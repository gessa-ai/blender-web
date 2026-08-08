<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 name-section strip + 30-minute soak

**Date:** 2026-08-08 · **Author:** M8 stability worker · emcc **6.0.5** ·
Gate tree: `build-wasm-windowed-opt` (`CMAKE_BUILD_TYPE=Release`, `-O2 -DNDEBUG`) ·
Port **8127**.

Two deliverables: (1) wire the wasm `name`-section strip into the shipped browser
binary and measure the wire win; (2) a 30-minute automated soak of the relinked
gate binary against a stated no-leak budget.

---

## 1. Name-section strip (the ~1 MB brotli zero-risk win)

### What the flag is (RANKING.md item 1, made precise)

`sandbox/m8-dce-ranking/RANKING.md` names the lever "`-sno-name-section`". There is
**no literal `-s NO_NAME_SECTION`** in emcc 6.0.5. The wasm `name` section is
governed by the internal setting `EMIT_NAME_SECTION`
(`tools/emsdk/upstream/emscripten/src/settings_internal.js:119`, default `false`),
which is turned **on** by:

- `--profiling-funcs` -> `EMIT_NAME_SECTION = 1` (`tools/cmdline.py:417-418`)
- `-g` / `-g2`+       -> `EMIT_NAME_SECTION = 1` (`tools/cmdline.py:367-368`)

and forced **off** by:

- `-g0` -> `EMIT_NAME_SECTION = 0` (explicit, order-independent; `tools/cmdline.py:362-366`)

The shipped browser binary carried a name section **only** because
`_bw_browser_flags` in `patches/platform_wasm.cmake` passed `--profiling-funcs`
unconditionally. The fix is to gate it on the build type.

### The change (patches/platform_wasm.cmake, BEGIN/END BLENDER-WEB NAME-SECTION STRIP)

`--profiling-funcs` removed from the base `_bw_browser_flags` string; then:

```cmake
if(CMAKE_BUILD_TYPE STREQUAL "Release")
  string(APPEND _bw_browser_flags " -g0")          # SHIPPED -> drop name section
else()
  string(APPEND _bw_browser_flags " --profiling-funcs")   # dev/debug -> keep it
endif()
```

Reverse-appliable, clearly-marked block (mirrors the sibling M8 PYCACHE PRUNE
block); the pycache-prune block is left intact. This is the exact existing idiom in
this file (`if(NOT CMAKE_BUILD_TYPE STREQUAL "Release")` already gates
`-sERROR_ON_WASM_CHANGES_AFTER_LINK` in two places).

Gate proven with a standalone cmake test (`sandbox/m8-soak/cmake-logic-test/`):

| CMAKE_BUILD_TYPE | resulting tail flag |
|---|---|
| Release          | `-g0` (name section stripped) |
| RelWithDebInfo   | `--profiling-funcs` (kept) |
| Debug            | `--profiling-funcs` (kept) |
| (empty)          | `--profiling-funcs` (kept) |

So the shipped tree `build-wasm-windowed-opt` (Release) strips; the debug twin
`build-wasm-windowed` (RelWithDebInfo) keeps it.

### The census / debug-workflow decision (documented)

The name section serves ONLY debugging: browser-console stack-trace symbolication
and the DCE census (`llvm-nm --print-size --demangle` per-subsystem byte
attribution that RANKING.md itself depends on). Dropping it from the shipped
(Release) binary is safe because:

- **Dev/debug builds keep it.** `RelWithDebInfo` / `Debug` still emit
  `--profiling-funcs`, so named stack traces survive off the critical path.
- **The census loses nothing.** It must move from the Release tree to the
  RelWithDebInfo twin `build-wasm-windowed`, which is the **same `-O2` objects**
  as the Release tree (both `-O2`; RelWithDebInfo just adds `-g` DWARF in separate
  sections). Per-function CODE sizes are therefore identical to the shipped module,
  so the attribution numbers are unchanged. Verified below: the CODE and DATA
  sections are byte-identical between the name-stripped and name-bearing links of
  the same objects.

### Measurement method (race-safe, link-only)

The r29 lane was actively relinking the shared gate binary
(`build-wasm-windowed-opt/bin/`) during this work, and its in-flight instrumented
source (draw_command.cc, wgpu backend, the workbench shaders) is uncommitted in
`upstream/`. A `ninja` relink of the shared tree would have (a) contended on the
ninja lock and (b) baked r29 WIP into the measured binary. So — exactly as
`notes/m8-wasm-shrink.md` did — the measurement is a **link-only relink of the
already-compiled objects**, differing by the flag only, into sibling dirs that
r29 never writes:

- `bin-proffuncs/` = baseline verbatim (keeps `--profiling-funcs`) = the BEFORE.
- `bin-namestrip/` = `--profiling-funcs` removed, `-g0` appended = the AFTER
  (== what the cmake edit produces on a Release relink).

Both from identical objects -> the delta isolates the flag. (Independently
confirmed: the r29 lane's own `ninja` relink of the shared tree, picking up this
cmake edit, produced a binary byte-consistent in size with `bin-namestrip`
-- end-to-end proof the cmake path yields the stripped binary.) Scripts:
`sandbox/m8-soak/relink-{namestrip,proffuncs}.sh`.

### Measured before/after (blender_browser.wasm)

| | raw wasm | brotli-q11 wasm | name section |
|---|---:|---:|---|
| **BEFORE** (`--profiling-funcs`) | 123,273,267 | **22,553,609** | present (23,145,958 B raw) |
| **AFTER** (`-g0`, stripped)      | 100,127,299 | **21,269,072** | absent |
| **delta**                        | **-23,145,968 (-18.78 %)** | **-1,284,537 (-5.70 %)** | removed |

- **Wire win = ~1.28 MB brotli** (1,284,537 B), ~1.22 MiB. Slightly better than
  RANKING.md's ~1.04 MB estimate (their name section was 20.4 MB raw; this tree's
  is 23.1 MB after source drift).
- Cross-check: the name section compressed **alone** is 1,265,177 B brotli-q11,
  matching the whole-file delta (1,284,537) to within 1.5 % -> the delta is exactly
  the name section, nothing else moved.
- CODE section (78,112,485 B) and DATA section (21,528,654 B) are **byte-identical**
  before vs after; `blender_browser.js` (600,303 B) and `.data` (85,203,093 B) are
  identical. **The strip touches only the `.wasm` name section -- zero runtime
  bytes change**, which is why it is zero feature risk and why the soak result
  transfers 1:1 to the unstripped binary.

BEFORE (123,273,267 B) reproduces the original shipped binary (123,273,566 B at
session start) to within 299 B -> faithful.

### Boot-verify (headed Playwright, port 8127)

`sandbox/m8-soak/boot-verify.mjs` against `bin-namestrip`:

- WM_main reached in **~525 ms** (warm), state marker `main loop (WM_main)`.
- First-pixels `presentBackbuffer` marker seen; loader dismissed.
- **0 GPU errors**, no abort, `window.__bwModule` present.
- Visual capture `evidence/boot-verify-namestrip.png` -- default workspace renders
  (topbar, viewport, cube), unregressed vs the name-bearing binary (same CODE).

Verdict: **name-strip boot PASS** -- the stripped shipped binary boots and
composites identically.

---

## 2. Soak test (30 minutes)

### Harness reality (channel audit for this windowed build)

Establishing what can actually be driven/measured under Playwright against this
build cost most of the setup; recorded here so the next lane does not re-derive it:

- **Straight-line pyexpr (before WM_main) runs; `os.write(2)` reaches the console**
  (via `boot-windowed.js` `Module.printErr -> console.error`). This is the M5 path.
- **`bpy.app.timers` callbacks DO NOT fire** under the automated harness (tested:
  a repeating 0.5 s timer, even with `page.bringToFront()`, never fired). M5 also
  ran everything straight-line, never via timers.
- **`SpaceView3D` draw handlers DO NOT fire** (0 POST_PIXEL callbacks across boot +
  input) -- the web draw path does not invoke Python draw handlers.
- **`resource` module is ABSENT** (`ModuleNotFoundError`) -> no `ru_maxrss`.
  `sys.getallocatedblocks()` returns 0 (CPython's vendored mimalloc). `gc.get_objects()`
  works (73,469 objects at boot).
- **wasm linear memory is NOT readable from JS.** `__bwModule` (main thread) exposes
  30 keys but **no** `HEAP*`/`wasmMemory`/`_sbrk`/`_emscripten_get_heap_size` (only
  `_main`, `FS`, `callMain`, `ENV`, `pause/resumeMainLoop`). `MODULARIZE` hides
  `wasmMemory` in the factory closure; pool-worker `evaluate` either times out
  (busy WM worker) or the emscripten runtime lives in a closure the worker global
  cannot see. `performance.measureUserAgentSpecificMemory()` returns ~4.2 GB
  (the reserved growable-SharedArrayBuffer max for pthreads) -- constant, so not a
  sensitive leak signal.
- **Present liveness signal chosen: the main-thread rAF counter.** WM_main is
  `emscripten_set_main_loop` driven by the main thread's rAF (proxied to the WM
  worker), so an injected `requestAnimationFrame` counter advances in lockstep with
  WM iterations; if Blender's per-frame draw/present blocks, the main thread blocks
  and the counter freezes. Measured ~120 fps sustained. (The C-side
  `presentBackbuffer` printf is capped at 2 frames -- `GHOST_ContextWGPUWeb.cc:442`
  -- so it cannot serve as an ongoing frame counter.)

### What the soak measures (and its honest scope)

Because the name-strip changes **zero runtime bytes**, the soak's job is to confirm
the stripped shipped binary boots and runs **stably** over sustained operation and
to give a leak/stability datapoint for the gate tree. Activity: periodic input
bursts (every 15 s) of the M5-proven set driven to the canvas -- mouse pick/orbit +
keys A (select-all), G-move (grab/translate/confirm), Tab in/out (edit-mode
enter/exit = the bmesh alloc/free leak surface), Ctrl+Z x2 (undo-stack churn) --
between which the WM loop keeps pumping at ~120 fps. `sandbox/m8-soak/soak.mjs`.

Sampled every 30 s: `usedJSHeapSize` + `totalJSHeapSize` (JS glue heap), rAF frame
count (liveness), console-line / GPU-error / fatal counts. A 2 s watchdog flags any
present stall > 5 s. Time series -> `soak-timeseries.csv`; live status ->
`soak-live.json`; final -> `soak-result.json`.

**Scope caveat (stated plainly):** the soak directly measures loop/present liveness,
JS-glue-heap trend, GPU-error rate, and crash/abort. It does **not** directly
measure wasm linear-memory growth (unreadable in this build, per the audit above).
For a future wasm-memory soak, the clean fix is a tiny debug-only exported accessor
(e.g. `EXPORTED_FUNCTIONS+=_emscripten_get_heap_size` behind a non-Release guard)
so the sampler can read committed heap on the main thread.

**Binary caveat:** the gate-tree objects (hence `bin-namestrip`) currently carry
the r29 lane's in-flight `[bw-r29-*]` diagnostic instrumentation (uncommitted WIP
for their open opaque-group bug). Steady idle console ~7 lines/s; input bursts spike
to ~450 lines/s (r29 per-draw diags). This does not affect the name-strip delta
(CODE identical before/after) and will retire when r29 lands; the soak is therefore
of "the gate tree as it stands mid-r29-investigation".

### PASS bar (concrete)

- **Heap:** `usedJSHeapSize` back-half mean growth **< 10 %** vs front-half.
- **Liveness:** rAF advances in every 30 s window (`rafDelta > 0`) and **no present
  stall > 5 s** (watchdog `stalls == 0`).
- **GPU errors:** **zero** `GPU-ERROR` / `ValidationError` / Dawn errors during the
  run (r29 `[bw-r29-*]` diag lines are not GPU errors and are not counted).
- **No crash / abort / pageerror** over the full run.

### Result

<!-- SOAK_RESULT (filled from soak-result.json) -->
_2-min smoke test (pre-flight):_ boot 525 ms, 4 samples, heap flat ~93.5 MB,
rafDelta ~3600/30 s, 0 GPU errors, 0 stalls, 0 fatals -> harness validated.

_30-min run:_ see the "SOAK VERDICT" line below (appended on completion) and
`soak-result.json` + `soak-timeseries.csv` for the full time series.

---

## Reproduce

```
# serve the stripped gate binary
BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin-namestrip \
BLENDER_WEB_SHELL=$PWD/platform_web/shell PORT=8127 \
  /opt/homebrew/bin/bash scripts/serve-web.sh 8127
# name-strip relink (link-only, from the shipped objects)
EMSDK_PYTHON=$PWD/tools/emsdk/python/3.13.3_64bit/bin/python3 \
  bash sandbox/m8-soak/relink-namestrip.sh
# boot-verify + 30-min soak
NODE_PATH=/Users/paws/plushly/game-platform/node_modules node sandbox/m8-soak/boot-verify.mjs 8127
NODE_PATH=/Users/paws/plushly/game-platform/node_modules node sandbox/m8-soak/soak.mjs 8127 30
```

**SOAK VERDICT (30-min run, driver-salvaged from soak-result.json after the lane
process died pre-commit): PASS on all four bars.** 1,783 s, 60 samples, 111 input
bursts. Heap: front-half mean 93.48 MB vs back-half 93.43 MB = **-0.05 % growth**
(bar < +10 %); first 93.75 -> last 93.49 MB, dead flat. Liveness: min rafDelta
3,606 per 30 s window (~120 fps sustained), **0 present stalls** (bar: none > 5 s).
**0 GPU errors. 0 fatals/aborts/pageerrors.** Boot 523 ms. Full series:
`sandbox/m8-soak/soak-timeseries.csv`; verdict JSON: `sandbox/m8-soak/soak-result.json`.
