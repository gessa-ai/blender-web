<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# oneTBB under Emscripten (M1.7) — load-bearing flag knowledge

**Status: WORKING.** oneTBB `v2022.3.0` (Blender's pin) builds static under emcc 6.0.5
and `tbb::parallel_for` runs correctly under wasm threads in Node — 14 threads,
~500+ parallel chunks, exact sum, no deadlock.

## Version / source
- oneTBB `v2022.3.0` (matches `upstream/build_files/build_environment/cmake/versions.cmake`).
- MD5 `2b242c465b194ac8e1451ea1354873ae` (matches Blender's `TBB_HASH`).
- License Apache-2.0 (GPL-compatible).

## Build config (emcmake)
oneTBB ships official wasm support (`WASM_Support.md`). Static build, pthreads on:

    emcmake cmake .. \
      -DCMAKE_C_COMPILER=emcc -DCMAKE_CXX_COMPILER=em++ \
      -DTBB_STRICT=OFF \
      -DCMAKE_C_FLAGS="-pthread -Wno-unused-command-line-argument" \
      -DCMAKE_CXX_FLAGS="-pthread -Wno-unused-command-line-argument" \
      -DTBB_DISABLE_HWLOC_AUTOMATIC_SEARCH=ON \
      -DBUILD_SHARED_LIBS=OFF \
      -DTBBMALLOC_BUILD=ON -DTBBMALLOC_PROXY_BUILD=OFF \
      -DTBB_TEST=OFF -DTBB_EXAMPLES=OFF \
      -DCMAKE_BUILD_TYPE=Release

- We build **static** (`BUILD_SHARED_LIBS=OFF`) — Blender builds shared natively, but
  the wasm port is mono-wasm (no dynamic linking; see GOAL Emscripten posture).
- `TBBMALLOC_PROXY_BUILD=OFF` on purpose: the malloc-proxy overrides `malloc`, which
  would collide with GOAL's `-sMALLOC=mimalloc`. We ship `libtbb.a` + `libtbbmalloc.a`
  (proxy omitted). Blender links `TBB::tbb`; it does not require the proxy.
- Installs to `lib/wasm`: `lib/{libtbb.a,libtbbmalloc.a}`, `include/{tbb,oneapi}/…`,
  `lib/cmake/TBB/TBBConfig.cmake` (usable via `find_package(TBB)`).

## THE LOAD-BEARING PART — flags to *consume* TBB under wasm threads
Any later milestone linking TBB into a wasm module must compile/link its objects with:

| flag | why |
|---|---|
| `-pthread` | TBB is a threading lib; SharedArrayBuffer + Atomics. Required at compile AND link. |
| `-fexceptions` | TBB uses C++ exceptions internally. Without it, emscripten disables exception catching and a throw traps/aborts. Use `-fexceptions` (or `-fwasm-exceptions` once the whole build commits to wasm-EH — must be uniform across all objects + TBB). |
| `-sPROXY_TO_PTHREAD` | **Browser-critical.** Splits init into a browser thread + a proxied main worker so the browser thread stays in the event loop and can service nested Web-Worker (`pthread_create`) scheduling. Per oneTBB `WASM_Support.md` this is the recommended fix for the "runs serially / deadlocks" nested-worker limitation. |
| `-sPTHREAD_POOL_SIZE=N` | Pre-spawn N workers so TBB's arena has threads ready (avoids sync `pthread_create` from a worker). Size to expected concurrency. |
| `-sWASM_BIGINT` | GOAL posture; i64 across JS boundary. |

### PROXY_TO_PTHREAD nuance (verified 2026-08-03)
- **Under Node**: TBB runs correctly **with OR without** `-sPROXY_TO_PTHREAD` — Node's
  `worker_threads` permit a worker to spawn nested workers, so no deadlock either way.
- **Under a browser**: `-sPROXY_TO_PTHREAD` is **required** (a Web Worker cannot spawn a
  nested Worker without a browser thread present). Omitting it makes TBB run serially or
  deadlock. So: always ship `-sPROXY_TO_PTHREAD` for browser targets; Node CI passes
  regardless but keep it for parity.
- Node needs **no** COOP/COEP headers; the browser host does (SharedArrayBuffer) — served
  by the Cloudflare `_headers` per GOAL hosting.

### Output-format gotcha (cost one debug cycle)
`-o foo.mjs` triggers `MODULARIZE`/`EXPORT_ES6` — the module exports a **factory** and does
NOT auto-run `main`. `node foo.mjs` then exits 0 having done nothing (silent no-op).
For a self-running smoke test use `-o foo.js` (auto-runs). For real embedding, call the
exported factory yourself.

## Proof
`sandbox/tbb_smoke.cpp` — `parallel_for` over [0,1e6), atomic sum, counts chunks.
Compile+run recipe (working):

    em++ -std=c++17 -pthread -fexceptions -I lib/wasm/include \
      sandbox/tbb_smoke.cpp lib/wasm/lib/libtbb.a \
      -sPROXY_TO_PTHREAD -sPTHREAD_POOL_SIZE=8 -sEXIT_RUNTIME=1 \
      -sINITIAL_MEMORY=134217728 -sWASM_BIGINT -o tbb_smoke.js
    "$EMSDK_NODE" tbb_smoke.js
    # -> max_concurrency=14 / sum=499999500000 expected=499999500000 / TBB_WASM_OK

Reproduce via `scripts/deps/tbb.sh` (idempotent; `--test` reruns the smoke test).
The recipe invokes emsdk's pinned Node directly and rejects a serial result, a
non-shared Wasm memory, or generated glue that does not proxy `main()` to a worker.
