<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Checkpoint 02 — M1 tier-(a): Blender's own gtests on WebAssembly

Date: 2026-08-03. Author: tier-(a) gate worker (Opus driver).
Scope: the M1 tier-(a) correctness gate — run Blender's real `blenlib` and
`bmesh_core` gtest suites compiled to wasm32, under Node.

## OUTCOME (first)

**Partial — blenlib: YES; bmesh_core: BLOCKED.**

- **blenlib gtests PASS on WebAssembly: 1655 / 1665 (99 suites, 0 skipped),**
  node v22.23.1, ~0.84 s. Re-verified this session from the already-built
  `BLI_test_rawfs.js` (the prior crashed run's numbers were *not* trusted — and
  indeed differed: it recorded 10 non-passes; the honest count is 10 *with*
  `--test-assets-dir` and 12 without it).
  - **All 10 non-passes are non-faithfulness failures. ZERO are wasm CPU-logic
    or wasm32-ABI miscomputations:**
    - **9× `expr_pylike.Error_*`** — WebAssembly has no floating-point exception
      status register, so `fetestexcept()` is a no-op and div-by-zero / domain
      errors are not *flagged* (the arithmetic result itself is correct). These
      pass natively. Logged as a hardware deferral: `ledger/deferred.json`
      → `wasm-fp-exception-status`.
    - **1× `ChangeWorkingDirectoryTest`** — macOS host artifact: under NODERAWFS,
      `/tmp` resolves to `/private/tmp`, and the test's `__APPLE__`
      canonicalization is compiled out under emscripten. Expected green on the
      Linux oracle host (not independently re-run on Linux this session — caveat).
  - Bonus: the suite caught a **real latent ILP32 bug in Blender's own
    `path_utils.cc`** (`BLI_path_extension_ensure`: `size_t` underflow when
    `path_len==0`, harmless on LP64, out-of-bounds on wasm32). Fixed in
    patch 0006; native behavior byte-identical. This is the cross-build oracle
    doing exactly what GOAL.md promises it would.

- **bmesh_core gtests: CANNOT LINK OR RUN (structural blocker, not a defect).**
  Blender emits **no standalone per-suite test binary** — `bmesh_core` /
  `bmesh_core_test` are CTest *names* against one combined runner
  `bin/tests/blender_test.js` that links ~200 archives (essentially all of
  Blender). `bf_bmesh` PRIVATE-depends on `bf::blenkernel` + `bf::depsgraph` +
  `bf::blentranslation` (+`animrig` transitively); **none of those, nor
  `bf_bmesh` itself, are built for wasm.** M1.9 delivered only `bf_blenlib` +
  `bf_dna`. So bmesh_core tier-(a) is gated behind porting blenkernel + depsgraph
  (+ RNA `makesrna` generation and the `datatoc` host-tool wiring) — the rest of
  M1 headless-core, bleeding into M2. **No pass was fabricated.**

## What blenlib passing PROVES

- Blender's real C++ (139 blenlib TUs, ~1650 assertions across containers, math,
  hashing, strings, paths, geometry primitives, virtual arrays, index masks,
  memory pools, task/threading) **computes bit-for-bit like native when compiled
  to wasm32** — the deepest free correctness oracle in the plan is green.
- The **wasm32 ABI work is sound end-to-end**: the makesdna alignment fix
  (patch 0002) and the DNA/blenlib TUs produce a layout the compiler agrees with,
  and 1655 tests exercising that layout pass. Alignment, endianness, integer
  widths, float determinism (`-ffp-contract=off`) all hold.
- **wasm threads run Blender code correctly under Node** (TBB-backed task graph;
  no deadlock — the `-sPROXY_TO_PTHREAD` interaction from `notes/deps-tbb.md`
  is not triggered under Node's nested `worker_threads`).
- UTF-8 filesystem paths work: a Cyrillic-named file opens via `std::fstream`
  under NODERAWFS.

## What it does NOT prove

- **Nothing above blenlib is exercised.** blenkernel, depsgraph, bmesh, RNA,
  the operator/bpy layer, GPU, and UI are untested on wasm — bmesh_core, the
  second half of this very gate, is blocked precisely because that core isn't
  ported yet.
- The 9 `expr_pylike` divergences are a **real wasm-vs-native behavioral gap**
  (error *detection*, not computation). Parity there needs a source-level
  explicit divide/NaN check; deferred, tracked, not silently passed.
- The macOS `ChangeWorkingDirectory` result is **assumed** green on Linux, not
  measured there this session.
- Node ≠ browser: this is Node `worker_threads`, not a COOP/COEP browser tab.

## What's next (ranked)

1. **Port `bf_blenkernel` + `bf_depsgraph` to wasm32** (the true unblock for
   bmesh_core and for M1's "headless core boots"). Expect the same fix classes
   already catalogued: Class-1 `sizeof==<LP64>` asserts, Class-2 libc gaps,
   plus RNA `makesrna` host-tool generation (wired, unverified) and `datatoc`
   host-tool wiring (`blender_web_host_tool()` pattern, proven for makesdna).
2. **Wire a runnable bmesh test binary.** Either a targeted hand-link of
   `libbmesh_tests.a` + `bf_bmesh` + the minimal core deps (mirroring how
   `BLI_test` was hand-linked standalone), or build the combined `blender_test`
   once the core libs exist. Re-run and record bmesh_core numbers.
3. **Capture the blenlib standalone-link recipe as a script/patch.** `BLI_test`
   was hand-linked ad hoc; the artifact runs but the exact command isn't in a
   patch or `scripts/` — a reproducibility gap to close.
4. Consider the source-level `expr_pylike` divide/NaN check to close the 9-test
   deferral when a driver-network suite (tier-b/c) starts exercising it.

## Honest caveats

- **The prior crashed run under-reported.** It logged "10 non-pass" but ran the
  binary *with* `--test-assets-dir`; a bare run yields 12 (2 extra `fileops`
  tests need external assets). Both extra failures are environmental and pass
  once the asset dir is supplied. Trusting the prior number blindly would have
  been wrong — this is the "verify, don't trust" rule earning its keep.
- blenlib is marked pass in `ledger/results/m1.json`, but **overall `m1.pass`
  is `false`**: bmesh_core is the other half of the gate and is blocked, and the
  9 `expr_pylike` divergences are deferrals, not clean greens. M1_CORE_BOOTS is
  **not** promisable.
- `upstream/` left **pristine** (`git -C upstream status --porcelain` empty);
  the full patch series 0001–0006 applies clean and produces exactly 10 modified
  files. Disk 15 GiB free (above the 8 GiB abort floor).
