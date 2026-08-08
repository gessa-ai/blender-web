<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 wasm module-split feasibility - the one deep size item

**Date:** 2026-08-08 · **Author:** M8 wasm-split research lane · emcc **6.0.5** ·
binaryen `wasm-split` (bundled) · prototype tree `sandbox/m8-wasm-split/` (own build
dir; never the shared trees) · browser proof on **:8127** (headed bundled Chromium,
Playwright 1.61.1, `NODE_PATH=/Users/paws/plushly/game-platform/node_modules`).

## Charter (what this lane had to answer)

Shipped windowed wasm = **21.27 MB brotli** (after the name-strip) vs the **15 MB**
LAUNCH.md to-interactive bar. Compiler levers (`-Os`/`-Oz`/`--closure`/`-flto`) and the
name-strip are spent (`notes/m8-wasm-shrink.md`, `sandbox/m8-dce-ranking/RANKING.md`,
`notes/m8-soak-and-namestrip.md`). The one remaining structural lever on record is
**module splitting**: ship a primary wasm with the boot+UI critical path and demand-load
the rest. This is RESEARCH + a sandbox prototype + an honest go/no-go, NOT a production
change. Three questions:

1. Does emscripten 6.0.5's `SPLIT_MODULE`/`wasm-split` flow work under this build's
   constraint set (`-pthread`, `-sPROXY_TO_PTHREAD`, mono-wasm, WasmFS, emdawnwebgpu,
   MODULARIZE, **no JSPI per ADR-006**)? Specifically: does the placeholder mechanism
   need Asyncify/JSPI at the split boundary (which would violate ADR-006)? WHERE does the
   async boundary land and on WHICH thread?
2. If the stock flow is incompatible, what are the honest alternatives?
3. For the most promising route, prove the mechanism with measured primary/secondary
   sizes and a working browser demand-load.

---

## 1. Constraint analysis - the split boundary is JSPI-FREE on this thread topology

### The stock SPLIT_MODULE runtime, read from source (emcc 6.0.5)

`tools/emsdk/upstream/emscripten/src/preamble.js` `splitModuleProxyHandler` +
`loadSplitModule` (lines ~507-545):

```js
{{{ makeModuleReceiveWithVar('loadSplitModule', undefined,
      JSPI ? '(secondaryFile, imports) => instantiateAsync(...)' : 'instantiateSync') }}}
...
let ret = {{{ asyncIf(ASYNCIFY == 2) }}} (...args) => {
  var imports = {'primary': wasmRawExports};
  {{{ awaitIf(ASYNCIFY == 2) }}}loadSplitModule(secondaryFile, imports, base);
  return wasmTable.get(base)(...args);   // call the now-loaded real function
};
{{{ JSPI ? 'return new WebAssembly.Suspending(ret);' : 'return ret;' }}}
```

The JSPI/Asyncify wrapping is **conditional**. With **no JSPI and no Asyncify** (our
profile, ADR-006), `loadSplitModule === instantiateSync`, the placeholder is a **plain
synchronous function** (no `WebAssembly.Suspending`, no `await`), and the load chain is:

- `instantiateSync(file)` -> `getBinarySync(file)` -> `readBinary(url)` =
  **synchronous `XMLHttpRequest` (`xhr.open('GET', url, false)`)**
  (`src/web_or_worker_shell_read.js`, worker branch), then
- `new WebAssembly.Module(binary)` (**synchronous compile**) +
  `new WebAssembly.Instance(module, {'primary': wasmRawExports})`.

**Where the boundary lands / on which thread.** The demand-load is a blocking
sync-XHR + sync-compile + sync-instantiate executed **on the thread that first calls a
secondary (placeholder) function**. This is legal **only off the browser main thread**:
synchronous XHR and synchronous compilation of a module > 4 KB are forbidden on the
browser main thread but **allowed on Web Workers**. Under **`-sPROXY_TO_PTHREAD`,
`main()` and all of Blender's logic run on the WM worker**, never the browser main
thread - so the blocking load is legal by construction. It is the **exact same
worker-blocking posture ADR-006 already sanctions** for the WebGPU device `WaitAny` and
texture readbacks. **No JSPI, no Asyncify, no ADR-006 violation.** The ADR-006 suspend
invariant stays vacuous: there are still zero suspends.

Corollary invariant (new, enforceable at review): **a cold/secondary subsystem must
never be first-triggered from the browser main thread** - only from the WM worker or
other pthreads - else the sync compile of a large secondary throws. Under
PROXY_TO_PTHREAD this holds automatically for all Blender code.

### The secondary module's shape (measured on the real split)

`wasm-split` makes the secondary **import the primary's shared memory and the primary's
`__indirect_function_table`**, and install its functions into that table via an active
elem segment; callers in the primary reach split functions through placeholder imports
(namespace `placeholder.deferred` -> runtime fetches `<base>.deferred.wasm`). Because the
memory is the shared pthread SAB, any secondary code that touches WasmFS/WebGPU/Blender
state works unchanged. mono-wasm/DCE is a **non-issue and in fact the key advantage over
dynamic linking**: `wasm-split` runs **after** link + `-O2` + binaryen DCE on the already
optimized module, so nothing is de-DCE'd (unlike `MAIN_MODULE`/`SIDE_MODULE`, which GOAL
notes kills DCE under pthreads).

### The pthreads gap - real, but a one-line glue fix (found + fixed + proven)

Stock `SPLIT_MODULE` **does not boot under `-pthread`/`-sPROXY_TO_PTHREAD` as shipped.**
Root cause (pinpointed in `harness.js`): pthread workers instantiate the
placeholder-importing primary via `new WebAssembly.Instance(wasmModule, getWasmImports())`
(the `ENVIRONMENT_IS_PTHREAD` branch of `createWasm`) but **never run the main thread's
`wasmBinaryFile ??= findWasmBinary()`**. The `splitModuleProxyHandler` then dereferences
an **undefined `wasmBinaryFile`** at instantiation time (`.slice` on undefined) and
**every pooled worker crashes at boot** (`PTHREAD_POOL_SIZE` pre-spawns them), aborting
the whole app before `main()`.

Fix = a **one-line guard** in the split proxy handler (upstream-shaped):
`if (typeof wasmBinaryFile == 'undefined' || !wasmBinaryFile) wasmBinaryFile = findWasmBinary();`
`findWasmBinary()` (=`locateFile("harness.wasm")`) resolves on workers from
`self.location.href`, so it is correct on every thread. Applied post-link in the
prototype (`sandbox/m8-wasm-split/build.sh`); a production landing would carry it as a
`--pre-js`/glue patch or upstream PR. With the guard, all pthread instantiation and
demand-load works (proof below).

### Per-thread secondary load (measured cost caveat)

The `__indirect_function_table` is **per-thread** in this emscripten pthread model (each
worker re-instantiates; tables are not shared). Proven by the network log: the secondary
`harness.deferred.wasm` is **fetched once per thread that first calls a split function**
(the driver saw it fetched twice - once on the proxied-main worker, once on a fresh
pthread). Consequences:

- **Correctness:** fine - each thread independently sync-loads the secondary on first
  cold use. No coordination needed, no JSPI.
- **Cost:** the secondary is **compiled once per pthread that touches it** (network is
  HTTP-cache-cheap after the first; compile is not). For a large secondary invoked from
  many TBB workers this is real CPU/RAM. **Mitigation = pick split boundaries at
  subsystems invoked from a single thread** (the WM worker) - shader compile,
  importers/exporters, compositor, sculpt are WM-worker-driven; a TBB-parallel cold leaf
  is the bad case. This shapes WHICH subsystems are good split candidates.

---

## 2. Cold/hot table - byte-accurate subsystem attribution (the core research artifact)

**Method (named, with confidence).** Byte-accurate **name-section attribution of the
shipped `-O2` module**, the same census as `RANKING.md` (llvm-nm `--print-size` over the
demangled name section; ordered-regex subsystem classifier
`sandbox/m8-dce-ranking/classify.py`). Run here on the **RelWithDebInfo twin**
`build-wasm-windowed` because the shipped Release binary is now name-stripped (`-g0`); the
twin keeps the name section by design (`notes/m8-soak-and-namestrip.md`). **Confidence:
HIGH for per-function byte cost** (each symbol's size is its real code cost after DCE),
**MEDIUM for the boot cold/hot split** - this is *subsystem* granularity by architecture,
not a runtime *function-level* profile (see §4). **Honest twin caveat:** RelWithDebInfo is
`-O2 -g` (asserts present, no `-DNDEBUG`); its CODE is **86.98 MB vs the Release wire's
78.11 MB (~+11%)**, so absolute bytes here slightly overstate the wire; proportions and
the cold/hot verdict transfer.

| subsystem | funcs | raw MiB | boot? | notes |
|---|---:|---:|:--:|---|
| blender::blenlib | 52,362 | 21.95 | **HOT** | core containers/math/alloc; floored (over-attributed catch-all) |
| unclassified (libc/c++/glue) | 20,100 | 8.30 | **HOT** | libc++/runtime |
| geonodes (all families) | 8,397 | 6.17 | mixed | launch tier needs MESH geonodes at first-interaction, none in default cube at boot; NOT cleanly separable (one lib, shared field/socket infra) |
| CPython | 16,295 | 6.03 | **HOT** | UI is Python; `import bpy` + `bl_ui` at boot |
| blender::bke | 10,281 | 5.57 | **HOT** | blenkernel; mostly boot-reachable |
| blender::ed (other) | 7,507 | 4.69 | **HOT** | editors incl. view3d/space core |
| **shaderc/glslang/SPIRV** | 9,510 | 3.91 | **COLD** | shader compiler; not needed at boot IF shaders precompiled to WGSL + OPFS-cached (M3 plan) |
| OpenColorIO | 8,821 | 3.69 | **HOT** | AgX view transform is on the boot display path |
| blender::nodes (other) | 5,343 | 3.02 | **HOT** | shader/function node decl infra |
| blender::gpu | 3,285 | 2.84 | **HOT** | GPU backend |
| **tint** | 5,996 | 2.44 | **COLD** | WGSL translator; pairs with shaderc (same defer) |
| OpenImageIO | 4,379 | 2.22 | mostly HOT | image IO; some format leaf cold |
| **grease_pencil** | 3,701 | 1.94 | **COLD** | not launch-tier; cut-whole risk (DNA/back-compat) |
| **compositor** | 2,797 | 1.79 | **COLD** | workbench+EEVEE viewport does not need it |
| blender::rna | 5,040 | 1.43 | **HOT** | RNA registration at boot |
| blender::draw | 2,212 | 1.41 | **HOT** | draw manager |
| **numpy** | 1,369 | 1.31 | **COLD** | pulled by addons (glTF), not boot |
| tbb | 3,286 | 1.09 | **HOT** | threading |
| **seq/VSE** | 1,230 | 0.57 | **COLD** | leaf editor space |
| blender::bmesh | 551 | 0.50 | **HOT** | edit-mode core |
| freetype | 1,030 | 0.49 | **HOT** | UI text |
| zlib/zstd | 316 | 0.46 | **HOT** | .blend + data decompress |
| png/jpeg/tiff | 787 | 0.42 | mostly HOT | icons/thumbnails |
| openexr/imath | 1,262 | 0.27 | HOT | color/image |
| **ed:spreadsheet** | 572 | 0.21 | **COLD** | leaf editor space |
| **ed:nla** | 436 | 0.15 | **COLD** | leaf editor UI |
| **ed:clip/tracking** | 323 | 0.09 | **COLD** | residual (WITH_LIBMV OFF) |

**Cleanly-separable COLD-at-boot set** (shaderc/glslang + tint + grease_pencil +
compositor + numpy + seq/VSE + spreadsheet + nla + clip) = **25,934 funcs, 13.02 MiB raw
= 14.96% of code.** (sculpt/paint, RANKING item C ~0.67 MB brotli, has no distinct
namespace in the classifier - folded into ed/bke - so it is NOT in this measured cut; it
is a real additional candidate via a new WITH_ guard.)

---

## 3. Prototype - proven mechanism + measured real-module split

### 3a. Reduced harness - the mechanism (decisive on Q1)

`sandbox/m8-wasm-split/{harness.c,build.sh,shell.html,drive.mjs}`. A C program built with
the **load-bearing shipped constraints** (`-pthread -sPROXY_TO_PTHREAD -sMODULARIZE
-sEXPORT_NAME -fexceptions/JS-EH -sWASM_BIGINT -sALLOW_MEMORY_GROWTH -sMALLOC=dlmalloc`,
**no JSPI**, `-sSPLIT_MODULE=1`), then `wasm-split --split --split-funcs cold_subsystem`.
Deliberately omits WasmFS/emdawnwebgpu (orthogonal linked code that shares memory; not
part of the split mechanism). `cold_subsystem` is split to the secondary; it is called on
demand from (1) the proxied-main worker and (2) a freshly spawned pthread. Driven headed
on :8127.

**Result (`sandbox/m8-wasm-split/evidence/drive-result.json`): PASS on all three.**

- **T1 boot:** `boot-done`, `coldRuns=0`, `harness.deferred.wasm` **NOT fetched** - the
  primary boots standalone; the secondary is truly deferred.
- **T2 demand (proxied-main worker):** placeholder fires -> **secondary fetched now**
  (demand, not at boot) -> `cold_subsystem` executes, correct result, **0 fatal, no
  SuspendError, no abort** - synchronous demand-load with **no JSPI**.
- **T3 demand (fresh pthread):** cold executes on a newly spawned pthread, correct
  result, **0 fatal** - pthread path works (with the §1 glue fix). Network shows the
  secondary fetched a **2nd time** = per-thread table load, as analysed.

Harness sizes (mechanism, not representative of the win): primary 31,707 B raw / 12,935 B
brotli; secondary (`harness.deferred.wasm`) 413 B raw / 241 B brotli.

### 3b. Real Blender module split - the size measurement (Q3)

`sandbox/m8-wasm-split/{split_real.sh,wasm_section_filter.py,cold_set.py}`. **Tool-only,
NO relink** (disk guard: 36 GB free < 40 GB, so no new full-tree build dir; this operates
on the existing twin binary). Pipeline: strip DWARF from the twin (keep names) -> nm ->
classify the §2 COLD set to mangled names -> `wasm-split --split --split-funcs @coldfuncs`
-> strip name sections -> brotli-q11 the `-g0` wire modules.

**Raw split:** whole 109.08 MB -> **primary 96.39 MB + secondary 13.29 MB** (cold set
removed 12.69 MB raw from the boot wasm).

**Wire (brotli-q11), twin/RelWithDebInfo:**

| module | raw | brotli-q11 |
|---|---:|---:|
| whole (twin, -g0 wire) | 109,079,480 | **21,438,062 (21.44 MB)** |
| **primary (boot wasm)** | 96,385,552 | **19,360,385 (19.36 MB)** |
| **secondary (deferred)** | 13,286,808 | **2,264,956 (2.26 MB)** |

**The twin is a faithful wire proxy - the +11% raw-code inflation compresses away.**
The twin whole (**21.44 MB brotli**) matches the shipped Release wire (**21.27 MB**) to
**+0.8%**: the extra `-g` assert code is repetitive and brotli eats it. So the twin
primary/secondary transfer to the wire essentially 1:1 (a Release relink would land within
~1%). Scaled by the whole ratio, **Release primary ≈ 21.27 × (19.36/21.44) = 19.21 MB
brotli.**

- **Marginal cut** = whole − primary = **2.08 MB brotli** removed from the boot wasm by
  deferring the 13.0 MiB cold set (the secondary compresses to 2.26 MB standalone;
  primary+secondary = 21.62 MB vs whole 21.44 MB, so the split adds only **~0.18 MB** of
  boundary/dup overhead - cheap).
- Independent cross-check: RANKING's per-subsystem brotli attribution of the *actual* opt
  module predicted ~2.3-3.3 MB removable; the measured marginal 2.08 MB sits just under it
  (standalone-subsystem brotli overcounts vs the true marginal), consistent.

---

## 4. VERDICT

**GO on the mechanism; the 15 MB bar is NOT reached by this cut and needs the deeper
profile-driven split (which the mechanism now unblocks).** Precisely:

### GO (proven, ADR-compliant)
Emscripten 6.0.5 `wasm-split` demand-loading **works under our full constraint set with
NO JSPI and NO ADR-006 violation.** The split boundary is a worker-blocking sync
load - the sanctioned ADR-006 posture - not a suspend. mono-wasm/DCE is preserved (split
is post-link). The one real gap (pthread `wasmBinaryFile`) is a **one-line glue fix**,
proven end-to-end in the browser (T1-T3 PASS on :8127).

### But the WIN is short of 15 MB with subsystem-granularity cuts
The **measured** split of the cleanly-separable cold set (shader compiler + compositor +
grease pencil + VSE/spreadsheet/nla/clip + numpy = 13.0 MiB raw / 14.96% of code) takes
the primary from 21.27 to **19.36 MB brotli measured (Release ≈ 19.21 MB)** - a real
**~2.1 MB win**, but **still ~4.2 MB over the 15 MB bar.** The reason is structural: the
HOT core (blenlib 22 MB + libc/c++ 8 MB + CPython 6 MB + bke 5.6 MB + ed 4.7 MB + OCIO
3.7 MB + gpu/draw/rna/tbb ...) dominates, and whole *subsystems* cannot be cut from it.
Even adding sculpt (RANKING ~0.67 MB) and, aggressively, deferring geonodes + OIIO leaf
formats would only reach ~17.5-18 MB - subsystem cuts alone do not clear the bar.

### The only route to 15 MB, and its honest confidence
**Function-level, profile-driven splitting** (the emcc `SPLIT_MODULE` instrument flow:
`wasm-split --instrument` -> boot -> `__write_profile` -> split keep=hot). Typical wasm
apps have a large fraction of functions cold at startup, and the giant HOT *subsystems*
(52k blenlib funcs, 16k CPython funcs) certainly contain many boot-unreachable functions
that subsystem attribution counts as HOT. If the true boot hot-set is <~14 MB brotli, a
profile-driven primary clears the bar. **This is UNMEASURED here** (a faithful profile
needs an instrumented boot of the full windowed build; not run in this lane to avoid a
fragile 100 MB-module instrument-boot and to respect the disk/lane discipline - the shared
`-opt` tree is under active r30-r32 GPU work). **Confidence that profile-driven splitting
reaches 15 MB: MEDIUM** - plausible and the recommended path, but must be proven with a
real profile before it is promised.

### Recommended landing plan (staged, evidence-ordered)
1. **Land the shader-compiler split first** (shaderc+glslang+SPIRV-Tools+tint, ~6.35 MiB
   raw): the single biggest, safest, WM-worker-only deferral; it needs the M3 "precompile
   shader library to WGSL + OPFS cache" so the compiler is not on the boot path. Primary
   21.27 -> ~20 MB (about half the measured 2.1 MB cut is the shader compiler). Mechanism
   proven; carry the §1 glue patch.
2. **Add the leaf compile-outs** (compositor, grease pencil, VSE/spreadsheet/nla) either
   as splits or as `blender_web.cmake` WITH_ guards (RANKING's config-lane cuts) - the
   remainder of the measured cut. Primary -> **~19.2 MB (measured)**.
3. **Run the instrument profile** to measure the true boot hot-set and, if <~14 MB, do a
   profile-driven primary/secondary split to clear 15 MB. This is the make-or-break step
   for the bar; do it before promising the bar.
4. **If the profile shows the hot-set cannot fit** (blenlib/CPython/bke boot closure too
   large): accept the bar miss, ship at ~19 MB primary + staged `.data`, and record the
   deferral (below) with staged loading as the mitigation.

### Two caveats to carry
- **Glue patch required** (`wasmBinaryFile` guard for pthread workers) - small, but must
  land with any split or boot aborts.
- **Per-thread secondary compile** - pick split boundaries at single-(WM-)thread
  subsystems; do not split TBB-parallel leaves.

---

## Reproduce

```
# mechanism harness (browser demand-load proof, :8127)
bash sandbox/m8-wasm-split/build.sh
BLENDER_WEB_BIN=$PWD/sandbox/m8-wasm-split/build \
BLENDER_WEB_SHELL=$PWD/sandbox/m8-wasm-split/build PORT=8127 bash scripts/serve-web.sh 8127 &
NODE_PATH=/Users/paws/plushly/game-platform/node_modules node sandbox/m8-wasm-split/drive.mjs 8127

# real-module cold-set split measurement (tool-only, no relink)
bash sandbox/m8-wasm-split/split_real.sh
```

Artifacts: `sandbox/m8-wasm-split/evidence/{drive-result.json,drive-console.log,harness-final.png}`;
`sandbox/m8-wasm-split/real-split/{coldfuncs.txt,*_g0.wasm,brotli_results.txt}`.
