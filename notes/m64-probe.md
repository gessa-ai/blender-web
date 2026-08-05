<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Memory64 probe — ADR-004 Decision 3 evidence (wasm64 vs pointer-interner)

Date: 2026-08-04. Owner: ABI specialist. Toolchain: emsdk emcc 6.0.5.
Sandbox: `sandbox/memory64-probe/`. TL;DR: **wasm64 is favorable — it builds our dep
shapes, Chrome (the target) instantiates and RUNS it with NO perf tax (actually faster
on memory-bound work), and it links cleanly with our entire flag set incl. JSPI and
emdawnwebgpu. The one real friction: the pinned node (V8 12.4) cannot run `-sMEMORY64`
output (rejects 64-bit *table* limits), so node-based test/CI harnesses need a newer
node (or in-browser running).**

## (a) Toolchain — builds under `-sMEMORY64=1`
| target | wasm32 | wasm64 | note |
|---|---|---|---|
| hello.c | BUILT+RAN(node) | BUILT | ptrbytes 4 vs 8 |
| zlib (emscripten `--use-port=zlib`, compress/uncompress) | BUILT | **BUILT** | real C lib |
| fmt 12.1.0 (`src/format.cc` + fmt::format, C++ templates) | BUILT+RAN | **BUILT** | mid-size C++ dep |
| bench.cpp (STL: unordered_map, chrono) | BUILT | BUILT | C++ STL |
All clean. emcc warns `-sMEMORY64 is deprecated (prefer --target=wasm64)` — same effect.

## (b) Runtime instantiation
- **node 22.15 / 22.16(emsdk) / 22.23 — ALL FAIL**: `CompileError:
  WebAssembly.instantiate(): invalid table elements limits flags`. V8 12.4 supports
  memory64 but NOT the 64-bit **table** limits emscripten emits; `--experimental-wasm-
  memory64` / `--wasm-memory64-trap-handling` do not help (it is the table, not memory).
  => the pinned emsdk node cannot run wasm64.
- **Chrome (Browser pane) — WORKS**: bench64 instantiated and ran to correct results
  (identical `acc`/`f` to wasm32). Memory64 shipped Chrome 133 (inside our Chrome-137
  JSPI floor), so the actual delivery target is fine.

## (c) Perf tax — Chrome, BLI-flavored workload
Workload (chosen as a Blender proxy): (1) `std::unordered_map<u64,u64>` churn, 20M
insert/lookup/erase over a 1M-key space — pointer/hash/alloc-heavy, memory-bound, the
kind of thing `blender::Map`/idmap/oldnewmap does; (2) 60M-iter float loop, compute-bound.
Single fresh instantiation per measurement (multi-run-per-page inflates via accumulated
instances — discarded).

| metric | wasm32 | wasm64 | wasm64 vs wasm32 |
|---|---|---|---|
| map churn ms | 4843.8, 4903.5 (~4874) | 4165.1, 4176.6 (~4171) | **~14% FASTER** |
| float loop ms | ~350 (JIT-warmup noisy: 143–350) | 340.2, 345.8 (~343) | **~equal** |

**No wasm64 perf tax** on this workload — wasm64 matches or beats wasm32. Modern V8
memory64 uses trap/guard-page bounds checks; wasm32 pays explicit i32 bounds-check +
4 GB-mask overhead, so the memory-bound map churn is actually faster at 64-bit. The
historical wasm64 tax is not observed in the target engine.

## (d) Flag compatibility — `-sMEMORY64` link-attempts vs our real flag set
| combination | result |
|---|---|
| WASM_BIGINT + ALLOW_MEMORY_GROWTH (core) | LINK OK |
| + `-pthread -sPROXY_TO_PTHREAD` | LINK OK |
| + `-sMALLOC=dlmalloc -sNODERAWFS -sEXIT_RUNTIME=1` (full blender node profile) | LINK OK |
| + `-sJSPI` | LINK OK |
| + `-sJSPI -pthread -sPROXY_TO_PTHREAD` | LINK OK |
| + `--use-port=emdawnwebgpu` (WebGPU) | LINK OK |
No link-level incompatibilities — memory64 coexists with pthreads/PROXY_TO_PTHREAD,
dlmalloc, JSPI, and the emdawnwebgpu port.

## Verdict for ADR-004 Decision 3
Evidence favors **wasm64** as the structural fix for the 64-bit-.blend truncation class
(and it retires the whole ILP32 bug class — patches 0002/0014 models become native-like,
0018's detector becomes inert):
- Builds, runs in Chrome, no perf tax, links with everything we need.
Costs / open risks (unchanged from ADR-004 + one NEW, concrete):
- **NEW: node (V8 12.4) can't run `-sMEMORY64` (table64).** Our tier-a gtests and m2b
  suites run under emsdk node — they would need a newer node (V8 with table64; already in
  Chrome 133 / newer node lines) or an in-browser runner. This is the main practical
  migration cost, and it is a version bump, not a fundamental blocker.
- Full-stack rebuild for wasm64: every dep + libpython + Blender recompiled `--target=wasm64`.
- Browser floor Chrome 133 (already inside the Chrome-137 JSPI floor).
vs the pointer-interner (ADR-004 option 1): invasive DNA↔readfile coupling / thread-local
nested-read state, silent-corruption risk if wrong, and does NOT retire the ILP32 class.

Recommendation: schedule wasm64 as the structural fix (likely post-M4, pre-launch per
LAUNCH.md drag-drop bar), first resolving the node/CI runner (upgrade node to a table64
build or move readfile suites in-browser). Patch 0018 holds the line meanwhile.

## Receipts
- `sandbox/memory64-probe/`: hello{32,64}, ztest64 (zlib), fmttest{32,64} (fmt 12.1.0),
  bench.cpp + bench{32,64}.mjs/.wasm, bench.html, probe_*.log (link matrix).
- node failures: `invalid table elements limits flags` (22.15/22.16/22.23).
- Chrome: bench32 map ~4874ms; bench64 map ~4171ms (correct, identical acc/f).
