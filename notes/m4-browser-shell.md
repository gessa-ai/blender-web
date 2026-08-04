<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M4.pre — the browser boot shell (ghost-web)

Status (2026-08-04): **GREEN — full headless boot in the tab.** After the DNA
reconstruct fix landed, `blender_browser` was relinked (picks up the DNA-fixed `bf_*`
archives + trampoline-fixed libpython) and now boots Blender all the way through
`import bpy` in a real Chrome tab:
```
crossOriginIsolated=true
Blender 5.2.0 LTS
BPY_OK 5.2.0 LTS 3        (3 objects: cube, camera, light)
Blender quit
process exited, code 0    (state: exited(0), wall ~1.64 s)
```
The earlier milestone (parity to the known pre-Python abort) is superseded by this.

### The scripts-path fix (BLENDER_SYSTEM_RESOURCES) — no rebuild

Post-DNA-fix, the first relink stopped at `bpy: couldn't find 'scripts/modules'` →
`ModuleNotFoundError: No module named '_bpy_types'` in BOTH node and Chrome — so NOT
the node-only fstat issue. Root cause (instrumented, not the node fstat shim): the
`BLENDER_SYSTEM_SCRIPTS` folder-id does **not** read a scripts-specific env var; it
resolves via the umbrella base `BLENDER_SYSTEM_RESOURCES` and looks for
`<base>/scripts/modules` (appdir.cc:712 `case BLENDER_SYSTEM_SCRIPTS` →
`get_path_system_ex` appdir.cc:568 tests `BLENDER_SYSTEM_RESOURCES`). The
m2-python-boot.md recipe's `BLENDER_SYSTEM_SCRIPTS=upstream/scripts` was never
Python-verified (that boot aborted pre-Python). A standalone WASMFS probe confirmed
ENV-injection + preloaded-dir `stat`/`opendir` work fine on the PROXY_TO_PTHREAD
worker — the FS/threading were never the problem. Fix = a **runtime env change only**
(no rebuild): set `BLENDER_SYSTEM_RESOURCES=/bw` in boot.js `ENV_VARS`. Since the
preload mounts scripts/datafiles/python under `/bw`, `/bw` is the base; all three
resolve. Verified `BPY_OK 5.2.0 LTS 3` + exit 0 under both node and real Chrome.

Benign non-fatal noise (does not stop boot): OIIO `physical_memory` wasm stub; Python
`Traceback`s for disabled optional C-extensions (`_multiprocessing`, `sha3`/`shake`)
that make the `bl_pkg` add-on's `register()` fail — Blender catches it and continues.

## What shipped

| artifact | what |
|---|---|
| `patches/platform_wasm.cmake` (browser section) | `blender_web_browser_binary()` + `WITH_BLENDER_WEB_BROWSER` option; clones the `blender` target into a browser-linked `blender_browser`. |
| `platform_web/shell/index.html` + `boot.js` | zero-framework, CSP-clean page: instantiates the module, forwards stdout/stderr to the page `<pre>` + devtools console, surfaces exit code + wall time. |
| `platform_web/shell/README.md` | exact human local-link instructions + expected console tail. |
| `scripts/serve-web.sh` | tiny COOP/COEP static server (python3 http.server subclass). |

No upstream source was touched: `source/creator/CMakeLists.txt` is harness-protected,
so instead of a numbered creator patch the second executable is registered with
`cmake_language(DEFER)` from platform_wasm.cmake (see "Second executable" below).

## Link-profile decision (browser vs node)

`blender_browser` is the SAME compiled Blender as the node `blender` target — same
~200 object archives — relinked for a tab. Deltas vs `blender_web_node_binary()`:

| axis | node `blender` | browser `blender_browser` | why |
|---|---|---|---|
| filesystem | `-sNODERAWFS` | `-sWASMFS -sFORCE_FILESYSTEM=1` | browsers have no host FS. WasmFS keeps the FS in **shared linear memory**, so the preloaded payload is visible on the `-sPROXY_TO_PTHREAD` worker that runs `main()`. Classic MEMFS keeps its dir tree as **per-thread JS objects** the proxied main thread never sees → preloaded files would be invisible. Also GOAL.md's standing FS decision (WasmFS + OPFS). |
| payload | host abs paths via `BLENDER_SYSTEM_*` | `--preload-file` packages @ `/bw/...`, `ENV.BLENDER_SYSTEM_*` set by boot.js | see manifest below. |
| entry | runs immediately | `-sMODULARIZE=1 -sEXPORT_NAME=createBlenderModule` | boot.js owns the `Module` config (arguments / ENV / print / printErr / onExit / onAbort). Also lets the node verifier drive the *identical* artifact. |
| env access | process env | `-sEXPORTED_RUNTIME_METHODS=ENV,FS,callMain` | boot.js seeds `ENV` in `preRun` (the browser equivalent of the node env triad). |
| worker pool | (default) | `-sPTHREAD_POOL_SIZE=8` | pre-spawn workers so TBB + proxied-main don't stall on on-demand creation (task-sized: 8). |
| link guard | `-sERROR_ON_WASM_CHANGES_AFTER_LINK` (non-Release) | **omitted** | dev incremental-cache guard; irrelevant for a one-off artifact and a false trip would waste an iteration. |

Unchanged from the node profile (identical behaviour): `-sMALLOC=dlmalloc` (CPython
vendors its own mimalloc → clash), `-sPROXY_TO_PTHREAD`, `-sINITIAL_MEMORY=512MiB`
+ `-sALLOW_MEMORY_GROWTH`, `-sSTACK_SIZE=8MiB`, `-sWASM_BIGINT`, `-fexceptions`
(JS-EH), `-sEXIT_RUNTIME=1`, `--profiling-funcs`.

## Second executable without patching upstream

`blender_web_browser_binary(blender)` is deferred with `cmake_language(DEFER CALL ...)`
from platform_wasm.cmake (which runs in the **top-level** scope during "Main Platform
Checks"). The deferred call fires at the END of the top-level CMakeLists, after
`add_subdirectory(source/creator)` has fully defined `blender`. It then:

1. clones `blender`'s SOURCES (made absolute), LINK_LIBRARIES, COMPILE_FEATURES;
2. merges `blender`'s **target-level** *and* the creator **directory-level**
   COMPILE_DEFINITIONS / INCLUDE_DIRECTORIES / COMPILE_OPTIONS — the one wrinkle of
   cloning outside creator's own scope is that directory-level `add_definitions()`
   (e.g. `-DWITH_PYTHON`) don't auto-apply, so they're harvested explicitly. The
   global `-pthread/-fexceptions/-funsigned-char` live in `CMAKE_CXX_FLAGS` and apply
   in every scope, so they need no harvesting;
3. sets the browser LINK_FLAGS + `--preload-file` packages.

Gated behind `WITH_BLENDER_WEB_BROWSER` (default **OFF**) **and** `EXCLUDE_FROM_ALL`
so the shared build tree is untouched for other workers: the target only exists after
`-DWITH_BLENDER_WEB_BROWSER=ON`, and even then bare `ninja` skips it — it builds only
on explicit `ninja blender_browser`.

Build:
```
cmake build-wasm -DWITH_BLENDER_WEB_BROWSER=ON
scripts/ninja-locked.sh -C build-wasm blender_browser
```

## Payload manifest (WasmFS preload, virtual root `/bw`)

Mirrors the node boot recipe's `BLENDER_SYSTEM_*` triad. Wholesale directories — the
SIMPLEST profile that boots (task option A over lazy-fetch).

| host source | WasmFS mount | ENV var | size |
|---|---|---|---|
| `lib/wasm/lib/python3.13` | `/bw/python/lib/python3.13` | `BLENDER_SYSTEM_PYTHON=/bw/python` | 51 MB |
| `upstream/scripts` | `/bw/scripts` | `BLENDER_SYSTEM_SCRIPTS=/bw/scripts` | 12 MB |
| `upstream/release/datafiles` | `/bw/datafiles` | `BLENDER_SYSTEM_DATAFILES=/bw/datafiles` | 40 MB |

Built artifact sizes (`build-wasm/bin/`):
- `blender_browser.js`   0.6 MB (MODULARIZE factory + file-packager loader)
- `blender_browser.wasm` 112 MB (**with** `--profiling-funcs` names; ~82 MB stripped)
- `blender_browser.data` 93 MB (the three preload dirs, deduped/packed by file_packager)

### Tradeoff for the M7 staged-loading redesign

This is a **dev-grade eager-preload**: one ~93 MB `.data` fetch + a 112 MB wasm
compile before `main()`. Acceptable for the local link, not for launch. M7 should:
1. **Lazy/staged fetch** (LAUNCH.md budgets): split the payload into a boot-critical
   core (datafiles/colormanagement is read during `WM_init` *before* the scene load;
   python stdlib + scripts are only needed once `BPY_python_start` runs) and
   background-streamed remainder; service-worker cache the packages.
2. **Tree-shake the stdlib** (51 MB → a small fraction): the frozen `import bpy`
   working set is a fraction of the full CPython 3.13 stdlib (`test/`, `idlelib`,
   `tkinter`, `ensurepip`, `lib2to3`, `__pycache__` are dead weight here).
3. **Strip names** for the shipping wasm (drop `--profiling-funcs`).
4. Move the FS backend from the in-memory WasmFS backend to the **OPFS** backend for
   the project store (GOAL.md standing decision) — the preload data mounts stay
   in-memory; user files land in OPFS.

## Verification evidence (headless, self-driven)

All three rungs GREEN on 2026-08-04. The build hits the OLD abort — the DNA fix is
landing in a parallel lane and is not in this `blender_browser` build; that is the
documented parity target, not a regression.

**1. Server headers (`curl -I`, scripts/serve-web.sh on :8123).** Every response —
shell, `/bin/*.js`, `.wasm`, `.data` — carries `Cross-Origin-Opener-Policy:
same-origin` + `Cross-Origin-Embedder-Policy: require-corp` (+ CORP same-origin).
MIME correct: `application/wasm`, `application/octet-stream`, `text/javascript`.

**2. Non-NODERAWFS profile under node** (emsdk node 22.16.0, MODULARIZE factory driven
with the browser ENV + argv; scratchpad `run_browser_node.js`). Output:
```
Blender 5.2.0 LTS
BLI_assert failed: source/blender/blenkernel/intern/layer_utils.cc:205,
  BKE_view_layer_object_bases_get(), at '(view_layer->flag & VIEW_LAYER_OUT_OF_SYNC) == 0'
```
Stack identical to the node NODERAWFS build (m2-python-boot.md):
`main → wm_homefile_read_ex → BKE_blendfile_read_setup_readfile → BKE_scene_set_background
→ BKE_view_layer_object_bases_get → BLI_assert_abort`. Reaching the `.blend` read
means `WM_init` (which reads `/bw/datafiles` colormanagement) succeeded → **the
preloaded WasmFS payload is visible on the proxied `main()` worker** (the load-bearing
risk of this whole design).

**3. Real headless Chrome** (Playwright chromium 1228, scratchpad `chrome_boot.js`):
- `self.crossOriginIsolated === true` (COOP/COEP → SharedArrayBuffer enabled);
- the `-sPTHREAD_POOL_SIZE=8` worker pool spawns in the tab;
- boot.js injects `ENV.BLENDER_SYSTEM_*`, the payload loads, banner prints, then the
  **identical `layer_utils.cc:205` abort** appears in the page `<pre>` + console;
- boot.js `onAbort` fires → page state pill = `aborted`, wall time surfaced.

### Benign diagnostics observed (not browser-layer issues, identical on node)
- `OpenImageIO .../sysutil.cpp:214: physical_memory: Assertion ...` prints at startup:
  an OIIO cross-build stub for `Sysutil::physical_memory` on wasm. Non-fatal (boot
  continues past it); same on any FS profile since it's the same OIIO archive. Revisit
  when OIIO is exercised for real.
- One `net::ERR_ABORTED` on `blender_browser.data` in Chrome: a superseded/duplicate
  fetch (the payload still fully loads — boot proceeds past colormanagement). Benign.

## Reproduce
```
cmake build-wasm -DWITH_BLENDER_WEB_BROWSER=ON && scripts/ninja-locked.sh -C build-wasm blender_browser
scripts/serve-web.sh 8123          # then open http://localhost:8123/ and click "Boot Blender"
```
Node parity check (no browser): drive `build-wasm/bin/blender_browser.js` MODULARIZE
factory with `arguments`/`ENV` as in platform_web/shell/boot.js (see scratchpad
`run_browser_node.js`).
