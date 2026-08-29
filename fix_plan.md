<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# fix_plan.md — active milestones: M3 WEBGPU BACKEND (manifest frozen; device-free audits active; fresh Linux receipt blocked by s7) + M4 FIRST PIXELS (UI renders in-tab, polish rounds)

Driver-owned. Workers claim a task via `claimed_by:` on its line (atomic write) and
report results; they never rewrite this file. Task grammar: one line, independently
verifiable, `[area]` path-owner, explicit `blocked-by`. Areas: build-deps | python-wasm |
gpu-backend | ghost-web | harness | compliance | driver.

Recon round 1 (4 workers) verdict: **the CMake spine already configures end-to-end for
wasm with faked deps (Configuring+Generating done, 60.6s). Blender's own build logic is
NOT the wall.** The wall is (1) cross-compiling the mandatory dep set to `lib/wasm`, and
(2) a real `platform_web.cmake`. Two findings reorder everything: **OpenImageIO is on the
tier-(a) gtest critical path** (blenlib PUBLIC-links `OpenImageIO::OpenImageIO`), so the
Imath→OpenEXR→OIIO stack must exist in `lib/wasm` before a single gtest links — it is NOT
deferrable to M2. And **the whole M1 dep build is gated on disk** (see M0.8-CRIT).

---

## M0 residual (must clear before / alongside M1)

- [x] **M0.8-CRIT [driver → HUMAN]** Disk blocker — paged twice (both 2026-08-03: first at
  4.9 GiB pre-deps; recurred same day at 4.9→3.8 GiB, consumer was other projects' /private/tmp
  build dirs, see reports/disk-block-20260803.md). Human cleared to **18 GiB free** — M1 wave
  unblocked. **Residual: GOAL requires ≥40 GB before M2 (CPython superbuild) — re-page at M2 entry
  if below.** Disk monitor pattern: background `until df -g ...` watch.
- [x] **M0-hygiene [harness] (5cee2c4):** the pinned checkout now runs the exact scoped
  `git -C upstream lfs pull --include "release/datafiles/*"` hydration step. The cold-state
  discriminator proves `startup.blend` is a 131-byte stored pointer versus a 121,384-byte
  hydrated worktree file; the real bootstrap, shell syntax, and REUSE checks pass. Required
  `m0` and regression gates remain honestly red only on their separately named oracle and
  strict-receipt boundaries.
- [x] **M0-LINUX-ORACLE [driver] (10804af):** enrolled the ornith-lab user in the existing
  Docker group, built and verified the digest-pinned Blender 5.2.0/OIIO 2.4.17.0 image, and
  added a self-cleaning `with-env` mode that routes the protected M0 Blender and `oiiotool`
  checks through that network-disabled image without editing `oracle/` or `harness/`. Fresh
  immutable container proof `m0-oracle-ornith-20260820-r1` passes; `m0` is 6/6 GREEN and
  `--regress` retains the separately named M1-M6 receipt/artifact/hardware failures. This is
  runtime oracle evidence, not a fresh strict M0-M3 candidate or milestone promise.
- [x] **M0.9 [harness] RECONCILED:** the owner-provided public source destination now exists,
  and the canonical tree's CI skeleton is executable rather than documentary. The workflow pins
  all three third-party actions and the emsdk repository/release, restores separate `EM_CACHE`
  and `CCACHE_DIR` trees, runs REUSE before dependency checkout, compiles/runs a Wasm program,
  proves a compiler-cache hit, compiles through the emdawnwebgpu port, and shallow-fetches the
  exact Blender pin. The structural self-check and exact workflow payload pass on ornith-lab.
  This closes only source readiness: no hosted Actions run or milestone receipt is claimed because
  the unauthenticated workflow endpoint was not visible from this host. See
  `notes/m0-public-ci-skeleton-reconciliation-20260827.md`.
- Harness registry H-1 (result schema), H-2 (`--regress` missing, highest), H-3 (live emcc probe)
  stay open in `notes/harness-issues.md`; driver reconciles at the M1 boundary (lift lock, fix,
  re-run 6/6, add an `m1` regress scope, re-lock). H-2 blocks honest regression from M1.10 on.

---

## M1 — headless wasm core → tier-(a) gtests under node (ORDERED)

Honest sequencing: tasks M1.1–M1.3 are parallel CMake work; **M1.8 (real configure) cannot
complete, and M1.9–M1.12 cannot start, until the OIIO stack (M1.4→M1.6) is harvested to
`lib/wasm`** — which is itself blocked by the disk fix. There is no way to link blenlib/bmesh
gtests without OIIO+fmt+zlib+zstd+TBB present. Do not pretend the dep waves are optional.

### Platform CMake layer (parallel, no dep build needed)

- [x] **M1.1 [build-deps] RECONCILED by `ee412de` + `87ada67`:**
  `patches/0001-platform-wasm.patch` inserts the Emscripten branch before
  `UNIX AND NOT APPLE`, adds the port directory to `CMAKE_MODULE_PATH`, and includes the
  canonical `patches/platform_wasm.cmake`; the temporary
  `patches/cmake_wasm/platform_unix.cmake` shadow was deleted. The current integration source
  retains that exact branch and the canonical clean-pin replayer reproduces it from
  `fbe6228777e7`. This closes stale bring-up accounting only; it does not promote a strict
  receipt, result flag, or milestone promise.
- [x] **M1.2 [build-deps] RECONCILED by `87ada67`:** the canonical platform layer forces
  `WITH_OPENGL_BACKEND=OFF` and `WITH_VULKAN_BACKEND=OFF`, leaves the Epoxy include/library
  variables empty, and applies `-fexceptions` uniformly to C, C++, and platform compile flags.
  The historical pre-library configure reached `Configuring done` + `Generating done` without
  Epoxy/Vulkan discovery; the current product cache and emitted Ninja flags retain that contract.
  ShaderC's later M3 WebGPU role does not re-enable Blender's Vulkan backend. This closes stale
  M1 headless accounting only; it does not promote a strict receipt, result flag, or promise.
- [x] **M1.3 [build-deps] RECONCILED by `87ada67`, `02de79e`, and `96e3a0f`:** the
  historical M1 initial cache forced both `WITH_CYCLES` and `WITH_PYTHON` OFF, and its
  dependency-placeholder configure reached `Configuring done` + `Generating done` without
  entering either discovery path. M2.3 deliberately restored Python after the wasm CPython
  harvest; the M6 compile probe later closed the Cycles revisit by building the scalar CPU
  closure with Embree, OSL, path guiding, and GPU devices disabled. The current launch profile
  therefore correctly keeps Python and Cycles-CPU ON. This closes stale milestone-scoped
  accounting only; it does not change a build profile, product, receipt, result flag, or promise.

### Dep superbuild (historical sequence; M0.8-CRIT disk blocker resolved)

- [x] **M1.4 [build-deps] RECONCILED by `79eca04`, `4d55843`, `7c87f6e`, `53ed467`,
  and `5e379cd`:** zlib, zstd, fmt, Imath, libjpeg-turbo (`WITH_SIMD=OFF`), libpng,
  and oneTBB are harvested as real static Wasm archives with headers and consumer configs;
  Eigen and robin-map are correctly header-only. The TBB `parallel_for` smoke runs on Wasm
  threads. Pugixml is deliberately bundled by OIIO (`USE_EXTERNAL_PUGIXML=OFF`) rather than
  emitted as a standalone archive, with its installed detail headers and MIT license accounted
  under the OIIO dependency row. The former disk blocker is resolved. This closes stale Wave-0
  accounting only; it does not promote a strict receipt, result flag, or milestone promise.
- [x] **M1.5 [build-deps] RECONCILED by `7f5ca60`:** OpenEXR 3.4.10 and libtiff 4.7.1
  are harvested as static pthread Wasm archives with headers and CMake consumer packages.
  OpenEXR's pinned closure uses external Imath, libdeflate 1.18, and generic OpenJPH 0.25.2;
  TIFF binds the prefix's zlib and libjpeg while optional codecs, tools, tests, and docs stay
  disabled. The exported targets preserve those transitive links, and a fresh downstream Wasm
  smoke writes and reads a ZIP-compressed EXR plus a DEFLATE TIFF under Node. All four runtime
  dependencies remain licensed and GPL-compatible in `ledger/deps.json`. This closes stale
  Wave-1 accounting only; it does not promote a strict receipt, result flag, or milestone promise.
- [x] **M1.6 [build-deps] RECONCILED by `5e379cd`, `f7ec391`, `f41a474`, and
  `f0f93c7`:** OpenImageIO 3.1.13.1 is harvested as static pthread Wasm archives with
  embedded EXR/TIFF/PNG/JPEG readers, bundled pugixml, and the mandatory OpenColorIO subtree;
  tools, Python, TBB, SIMD, and unneeded codecs stay disabled inside OIIO. A fresh downstream
  Wasm consumer writes and reads all four enabled formats under Node. The pinned native Linux
  dependency package supplies `oiiotool` 3.1.13.1, which generates and inspects an image under
  the canonical `PLATFORM_ENV_BUILD` library environment. At the source pin it is host-side test
  plumbing, not a product data-generation edge. All seven Wave-2 ledger rows remain licensed and
  GPL-compatible. This closes stale Wave-2 accounting only; it does not promote a strict receipt,
  result flag, or milestone promise.
- [x] **M1.7 [build-deps] RECONCILED by `53ed467` and `3482fa0`:** Blender-pinned
  oneTBB 2022.3.0 is harvested as real static Wasm archives, and a fresh
  `parallel_for` run under exact emsdk Node 22.16.0 produces the exact arithmetic
  result across multiple chunks. The smoke now invokes `EMSDK_NODE` instead of the
  ambient host Node and rejects serial execution, non-shared Wasm memory, or generated
  glue that does not proxy `main()` to a worker. This closes stale dependency-risk
  accounting only; it does not promote a strict receipt, result flag, or milestone promise.

### Real configure → compile → link → run

- [x] **M1.8 [build-deps] RECONCILED by `25ad33a`:** `platform_wasm.cmake` resolves the
  populated `lib/wasm` prefix through real package targets and archives, including the mandatory
  OIIO/OCIO/OpenEXR/Imath/fmt/TBB/Eigen/JPEG/PNG/TIFF/zlib/zstd/Freetype/Brotli closure. A fresh
  Linux headless configure under emcc 6.0.5 and host CPython 3.13.13 reaches `Configuring done` +
  `Generating done`; its cache keeps `WITH_LIBS_PRECOMPILED=ON`, its generated graph binds 30
  nonempty Wasm archives with zero fallback-placeholder paths, and a locked `bf_blenlib` dry-run
  succeeds. This closes stale real-configure accounting only; it does not promote a strict
  receipt, result flag, or milestone promise.
- [x] **M1.9 [build-deps] RECONCILED by `b0be2bf`, `01ddce3`, `aaa54c9`,
  `338387a`, `a3f73b5`, `48f04de`, `3466022`, and `db88bd3`:** the accepted
  headless Wasm path compiles DNA/RNA, blenlib/bmesh, intern/extern, blenkernel, depsgraph,
  and the complete standalone tier-(a) link closure. Its root-cause fixes remain in the
  canonical frozen source and the recurring wasm32/libc/host-codegen patterns are recorded in
  `notes/porting-patterns.md`. A fresh Linux locked rebuild of `BLI_test`, `bmesh_core_test`,
  and `blender` completes the full graph and reproduces the documented artifact hashes; the
  Release parity cache keeps `WITH_HEADLESS=ON` and WebGPU/OpenGL/Vulkan backends OFF. This
  closes stale core-compilation accounting only; it does not promote a strict receipt, result
  flag, or milestone promise.
- [x] **M1.10 [harness]** blenlib gtests GREEN on wasm/node: **1655/1665**, 10 non-passes all
  characterized non-faithfulness (9 fenv deferral + 1 macOS-host chdir). `ledger/results/m1.json`.
  Harness `m1` scope registration deferred to the M1-boundary reconcile (H-4).
- [x] **M1-FENV-DEFERRAL-CLOSURE [driver, blocked-by: none] COMPLETE:** the current canonical
  evaluator uses a software exception accumulator instead of relying on wasm's absent fenv status
  register. Fresh Linux native/wasm focused runs pass the same 144 `expr_pylike` cases, and sealed
  receipt `m1-fenv-closure-ornith-linux-20260824-r3` passes BLI 1,667/1,667, bmesh-core 1/1,
  corpus 9/9, and versioning 12/12 against the current 20,258-entry freeze. The historical
  patch-0004 compile-only result above remains accurate history; the corresponding ledger row is
  now resolved. Aggregate M1 remains RED only because the unchanged strict adapter requires the
  s7-blocked complete M0-M3 candidate. See `notes/m1-fenv-deferral-closure-20260824.md`.
- [x] **M1.11 [harness]** **TIER-(a) GATE 2/2 GREEN** (2026-08-04, driver): bmesh_core_test.js
  linked (62.1MB, ~200 archives, SINGLE_BINARY=OFF standalone route) + runs under node: **1/1
  PASSED, exit 0, 116ms** — verified = the FULL upstream suite (bmesh_core_test.cc has exactly
  one TEST_F, BMVertCreate). One link fix: patch 0009 (unguarded WITH_PYTHON=OFF BPY_ call
  sites in interface_handlers.cc — latent upstream bug). m1.json 5/5, gate green. Warts
  recorded: OIIO physical_memory assert-print, OCIO fallback (both environmental, non-fatal).
- [x] **M1.12 [harness] RECONCILED by `0121ea3`, `ba34e75`, `00bc5f5`, and
  `b63ae5f`:** the deterministic nine-file corpus runs the same float-free bpy state dumper on
  the pinned native oracle and wasm32 product, covering startup plus authored mesh, modifier,
  animation, node, curve/text, armature, collection/instancing, and mixed-stress files. The
  accepted Wasm run and historical M1 harness were 9/9 byte-identical at exact tolerance zero;
  immutable Linux receipt `m1-ornith-linux-20260820-r5` later rebound all nine native/Wasm
  dumps to the canonical product and source freeze. A fresh Linux replay again produces 9/9
  exact equality. This closes stale corpus accounting only; it does not reissue the historical
  M1 promise or promote the currently RED strict receipt, result flag, or milestone gate.

### M1 remainder — port the core libs bmesh needs (dispatched 2026-08-03, post-disk-clear)

- [x] **M1.13 + M1.13a + M1.14 [build-deps]** ALL GREEN (01ddce3, driver-verified): blenkernel
  34.4MB/288 obj + depsgraph + blentranslation + animrig on wasm32. ADR-002 executed: native
  shader_tool+datatoc (scripts/build-hosttools.sh, FATAL_ERROR guard in platform_wasm.cmake);
  **byte-identity audit PASS** — 752+25 datatoc + 66+466 shader_tool identical, all 44 stale
  diffs = wasm-tool bugs (20 crash, 24 SILENT-CORRUPT → native tools necessary, not just
  convenient), 0 target-dependence. Fixes: 1 LP64 shift (image.cc 1<<32, patch 0008) + host
  PYTHON_EXECUTABLE for discover_nodes.py (Class-3b, porting-patterns.md). Series 0001-0008.
  makesrna first-execution confirmed. **→ CODEGEN-GREEN: wave-2 fan-out FIRED.**
- [x] **M1.15 [build-deps] RECONCILED by `2ebb9ff` and `01ddce3`:** the ABI-producing
  `makesrna` remains a Wasm host tool executed under Node, while target-independent `datatoc`
  and `shader_tool` use native host binaries per ADR-002. The current M1 graph contains one
  Node `makesrna` command, 909/907 native `datatoc`/`shader_tool` commands, and zero Wasm
  text-tool commands. Fresh graph-selected and pinned-emsdk Node executions regenerate all 79
  RNA outputs byte-for-byte, and a fresh native shader-tool-to-datatoc chain matches four built
  outputs exactly. This closes stale host-tool accounting only; it does not change product
  source, a receipt, result flag, or milestone promise.
- [x] **M1.15b [build-deps] RECONCILED by `45ed7ab`, `aaa54c9`, `338387a`,
  `3466022`, `48f04de`, `a3f73b5`, and `db88bd3`:** the five disjoint lanes compiled all
  90 planned production archives / 2,147 TU after CODEGEN-GREEN. P1, P3, P4, and P5 needed no
  source fixes; P2 needed only the accepted Python-off `asset_system` guard in patch 0120. The
  serialized tail linked the standalone `bmesh_core_test` after the accepted patch-0009
  Python-off fix and passed its complete one-test upstream suite. A fresh Linux audit finds the
  same 90 targets as nonempty Wasm archives in the current launch-enabled graph, the complete
  locked target set is no-work, and the canonical Node runtime again passes 1/1. This closes
  stale wide-grind accounting only; it does not change product source, a receipt, result flag,
  or milestone promise.
- [x] **M1.16 [driver] RECONCILED by `b8828a9`, `488679e`, `00bc5f5`,
  `2bd738f`, and `ea7133e`:** the historical boundary fixed H-1/H-2/H-3, registered the
  JSON-counted BLI and complete bmesh-core checks after M1.11, added corpus parity, restored the
  lock, and ran M0 plus full regression green. The current harness preserves `m1` and
  `--regress` but upgrades the mutable direct scope to the fail-closed strict-final adapter.
  Fresh Linux component evidence bound to a new clean-pin freeze passes BLI 1,667/1,667,
  bmesh-core 1/1, main corpus 9/9, and versioning 12/12 under the authoritative verifier.
  Aggregate `m1` remains honestly RED because its current adapter requires the unavailable
  complete M0-M3 manifest; s7's software-only Vulkan adapter still blocks that manifest. This
  closes stale boundary accounting only; it does not change harness source, a result flag,
  deferral, or milestone promise.

---

## M2 — DEPS + PYTHON BOOTS

- [x] **M2.0 [driver GATE]** DECIDED 2026-08-03 → **notes/adr/ADR-001**: stay on emcc 6.0.5;
  build vanilla CPython 3.13.13 + minimal patch subset ({LONG_BIT, trampoline back-ported from
  Pyodide MAIN}, added only as the build demands). 4.0.9 downgrade REJECTED (LLVM ABI break =
  rebuild 29 deps; loses emdawnwebgpu ≥4.0.10 = the M3/M4 path). Evidence: 3-agent research wave.
- [x] **M2.0b [python-wasm EXPERIMENT]** DONE 2026-08-03 (notes/python-emcc605-probe.md):
  vanilla 3.13.13 builds+runs on 6.0.5 in BOTH EH configs, ZERO patches — LONG_BIT/trampoline
  back-port unnecessary (in-tree trampoline works). **EH RESOLVED: JS-EH** (ADR-001 appendix) —
  joins the 29 JS-EH deps with zero rebuild; Wasm-EH proven viable as later fallback. Open:
  JSPI×setjmp at full link (M2.7); `_ctypes/_ssl/_hashlib/_lzma/_uuid` need libffi/openssl/xz
  if bpy startup requires (check at M2.5).
- [x] **M2.1 [python-wasm]** DONE (21b5fe3): deps.json `wasm_built.python` (PSF-2.0,
  GPL-compat, MD5 vs versions.cmake:385).
- [x] **M2.2 [python-wasm]** DONE (21b5fe3): `scripts/deps/python.sh` idempotent (2nd run 0s),
  clean-state verified via buildwrap. Harvest: `lib/wasm/lib/libpython3.13.a` (42.2MB, 2850 T
  = probe parity), `include/python3.13/`, `lib/python3.13/` stdlib (51MB/632 py, sysconfigdata
  present, tests excluded). Zero patches, JS-EH.
- [x] **M2.3 [python-wasm]** DONE 2026-08-04: WITH_PYTHON ON; PYTHON_* cache vars direct to
  lib/wasm (no find_package re-rooting); bf_python(+bmesh/ext/gpu/mathutils) builds 0 fixes;
  **`bin/blender.js` LINKS (82MB wasm) and BOOTS under node** to scene-load. Seams: mimalloc
  dup-syms → blender uses dlmalloc via blender_web_node_binary() AFTER setup_platform_linker_flags
  (patch 0010, last--sMALLOC-wins); libpython rebuilt -matomics -mbulk-memory self-contained
  (optional C-exts needing sqlite/bz2/mpdec/Hacl disabled — revisit if bpy needs); INITIAL_MEMORY
  512M/STACK 8M; PROXY_TO_PTHREAD stays ON (proven gtest profile, TBB). notes/m2-python-boot.md.
- [x] **M2.5a [DIAGNOSED]** (eb15a17, notes/m2-dna-reconstruct-diagnosis.md): NOT makesdna —
  patch 0002 proven correct (9357/9357 offsets, 992 structs, 0 mismatch). Root cause =
  **runtime `create_reconstruct_steps_for_struct` (dna_genfile.cc:1497-1508) accumulates target
  offsets UNPADDED** — an independent copy of the i386 model 0002 fixed in the generator;
  invisible on LP64 (hand-padding == unpadded), drifts on wasm32 from customdata_mask (5012 vs
  5016) through master_collection (5404 vs 5408 → NULL read). Blast radius MEASURED: exactly 1
  divergent struct in the whole SDNA (Scene, 17/51 members) — but reconstructed on every .blend
  open. ListBaseT hypothesis disproven. dna_verify gap explained: it certifies write-side tables,
  never the runtime accumulation — remains trustworthy for what it certifies.
- [x] **M2.5b [driver] RECONCILED by `a37bcab`:** patch 0014 keeps the target-side
  reconstruction on makesdna's emitted wasm32-padded member offsets instead of duplicating the
  layout model in `dna_genfile.cc`; every production change remains `__EMSCRIPTEN__`-guarded and
  the Scene special-case remains absent. A fresh generated-table audit matches all 9,831 runtime
  offsets to all 9,831 compiled `offsetof` assertions across 993 SDNA structs, including
  `Scene.customdata_mask=5016` and `Scene.master_collection=5408`. Pinned native and Wasm startup
  probes both expose Blender 5.2.0 LTS, three default objects, and the valid `Scene Collection`;
  the locked `bf_dna`/`blender` closure is exact no-work. This closes stale DNA-reconstruction
  accounting only; it does not change product or upstream source, a receipt, result flag,
  deferral, or milestone promise.
- [x] **M2.4 [build-deps]** Already done during M1: OCIO subtree forced by OIIO 3.x hard-dep
  (M1.6, commit 5e379cd), freetype+brotli forced by no-off-switch (M1.8, 25ad33a). Verified
  present in lib/wasm/lib (driver, 2026-08-03): libOpenColorIO/libfreetype/libbrotli*/
  libyaml-cpp/libexpat/libpystring/libminizip.
- [x] **M2.5 [python-wasm] RECONCILED by `02de79e`, `a37bcab`, and `d0c0a8f`:** the
  current Release headless product retains `WITH_PYTHON=ON`, the direct `lib/wasm` CPython
  binding, CPython's enabled Emscripten call trampoline, and the Node-only guarded `fstat`
  pre-js seam. A fresh pinned native-oracle probe and the exact Node 22.16.0 Wasm worker each
  assert Blender 5.2.0 LTS, the factory Camera/Cube/Light set, and a successful
  `primitive_cube_add` result with four objects; the locked `blender` target is exact no-work.
  This closes stale tier-(b) entry accounting only; it does not change product or upstream
  source, a strict receipt, result flag, deferral, or milestone promise.
- [x] **M2.6 [harness]** **TIER-(b) GATE GREEN — M2 COMPLETE** (2026-08-05): scope_m2b installed
  (harness v1.4) → 4/4 GREEN: 75 CORE rows, **64/64 must-pass exit-0** (ESSENTIALS_LANDED=1,
  NUMPY_HARVESTED=1), deferral_consistency enforced (10 raw-fails ALL registry-mapped: 3 ULP,
  1 ADR-004, 6 feature-off). Full regress m0 6/6 + m1 5/5 + m2b 4/4; lock restored. numpy in
  the binary (0033, gate 2.3.4/15); corpus 9/9 re-verified on the relinked binary.
  **PREP DONE (98d3c37, notes/m2-tierb-prep.md):** 43/43 oracle-green (38-CORE ≈595 cases,
  ~2m17s; 4 AMBER wasm-conditional; 1 excluded as parity-theater). m2b scope DRAFTED:
  exit-code-primary (sidesteps wasm stdout drops), binary-agnostic manifest (same args, swap
  oracle for node). TRAP documented: TEST_SRC_DIR_EXISTS lies (stub dirs exist, inputs are
  130-B LFS pointers). **DRIVER DECIDED: cheap LFS pull APPROVED (38.4 MB/89 files →
  ~doubles suites to ~75; dispatched). Full 0.76 GB pull deferred; render/GPU 447 MB never
  needed for tier-b.**
- [x] **M2.6-RECONCILE [driver] CLOSED by fresh Linux r8:** a new pinned upstream freeze
  (sha256:c0b961e0498a) and the exact container-oracle/Node 22.16.0 matrix completed all 75 rows
  without exposing another stream layout. Receipt sha256:7b78f3f26cf9 records 65 exact parity
  passes, 3 existing pass-with-deferral rows, and 7 existing registry-mapped deferred failures.
  The independent verifier replayed every raw native/Wasm log and all staged runtime assets;
  runner, aggregate, composer, and strict-adapter adversarial checks remain green. This closes the
  stale tier-(b) replay accounting only. Aggregate `m2b` remains honestly RED until the complete
  M0-M3 strict candidate exists; no product, upstream, harness, result flag, deferral, or milestone
  promise changed.
- [x] **M2-PASS-DELTA-REFRESH [driver, blocked-by: none] COMPLETE:** the exact current
  container-oracle/Node 22.16.0 matrix again passes all 75 tier-(b) rows: 65 `PASS`, seven named
  `DEFERRED`, and three exact-schema `PASS_WITH_DEFERRAL`. Independent raw-log replay and both
  mutation suites are green against the 20,258-entry freeze. The post-patch-0248 runtime does not
  retire the animation ObjectData or library-override ID-name deltas, so both named ledger rows
  remain honestly deferred. Aggregate `m2b` remains red only at the separate s7-blocked complete
  M0-M3 manifest boundary. See `notes/m2-pass-delta-refresh-20260824.md`.
- [x] **M2.7 [python-wasm] RECONCILED against `7c1722f`/`26025bd` and ADR-006:** the
  sandbox reproducer now derives its checkout from its own path, runs from root or descendant,
  requires a genuinely JSPI-capable runtime, rejects bundled Node 22.16.0 before compilation,
  and uses the harvested CPython/expat/stdlib closure when the historical probe tree is absent.
  Fresh emcc 6.0.5 + Node 25.1.0 runs reproduce A/C/D PASS, exact JS-EH B rejection, and all
  Wasm-EH/Asyncify controls from both working directories (20260821T180252-413106,
  20260821T180311-415168; negative 20260821T180311-415170). ADR-006 separately supersedes the
  old M4 topology residual: the shipping windowed profile has no JSPI and this experiment does
  not reintroduce it.
- [x] **M2.7c [python-wasm PROBE] RECONCILED alongside M2.7 against `cb4258c`:** the
  fail-closed replay preserves F1/F3 `SuspendError`, F2 PASS, every Wasm-EH PASS, exact JS-EH
  `invoke_*` 7/7/8 versus Wasm-EH 0/0/0, and zero SjLj refs in harvested libpython, libjpeg,
  and the linked Python image. ADR-003 remains the historical JSPI/exception result; ADR-006's
  no-JSPI product decision remains current. No product, upstream, gate, result flag, dependency
  record, deferral, or milestone promise changed.
- [~] **M2.8 [compliance] TECHNICAL INVENTORY RECONCILED; EXTERNAL POLICY BLOCKED:** fresh
  strict Linux evidence `m2-8-reconcile-20260821-r1` binds the current 37-row
  `wasm_built` ledger and canonical inventory to source freeze
  `c0b961e0498a`, enumerates 111 unique artifacts with zero missing/unlisted,
  passes exact REUSE 6.2.0, and reports 35 runtime-linked dependencies. Its
  external-policy verdict is honestly false for exactly one row: OpenSubdiv
  3.7.0 is recorded as `LicenseRef-OpenSubdiv-TOST-1.0` with compatibility and
  sufficiency unresolved. GOAL's runtime-deps-compatible contract therefore
  remains unsatisfied until the named GPL-literate lawyer review in
  `notes/m8-technical-closeout.md` records a disposition; never restore the old
  Apache-2.0 label or mark this item complete from machine inference. The old
  M1.6/M2.3 technical blockers are resolved. Evidence and rationale:
  `notes/m2-dependency-compliance-reconcile-20260821.md`.

---

## M4.pre — browser boot shell: **DONE** (babd6ba, notes/m4-browser-shell.md)

`blender_browser` target (WITH_BLENDER_WEB_BROWSER, EXCLUDE_FROM_ALL; creator target CLONED
via cmake_language(DEFER) — zero upstream patch) — WASMFS shared-memory FS (payload visible
to the proxied main worker — the load-bearing choice), 93MB preload (.data) + 112MB wasm.
Shell page + COOP/COEP server. **VERIFIED 3/3 incl. REAL HEADLESS CHROME: crossOriginIsolated,
pthread pool in-tab, payload loads, runs to the EXACT known DNA abort in the tab = browser
layer proven end-to-end.** Flips to BPY_OK on the 0014 rebuild, zero shell changes. Local
link: `scripts/serve-web.sh 8123` → http://localhost:8123/. M7 debt logged (eager preload →
staged/lazy + stdlib tree-shake + OPFS).

## M3 — WEBGPU BACKEND (native Dawn) — architecture DONE (notes/gpu-webgpu-architecture.md
## + notes/gpu-shader-chain.md, 2026-08-03); T-tasks runnable in parallel with M1/M2 tails

Measured basis: Vulkan backend = 28,062 LOC; webgpu/ estimate **13–17k** (render_graph 6,658
LOC eliminated by WebGPU's implicit model; skeleton = 30 wgpu_ file-pairs ≈ 14.3k). Backend
surface = **21 pure-virtuals** (T3 recon correction, cited gpu_backend.hh:47-81 — the
architect's 19 missed compute_dispatch×2 + render_begin/end/step); StateManager/Immediate
come from Context, not backend factories. GHOST swap API at this pin = swapBufferAcquire/
swapBufferRelease (not swapBuffers); GPU_BACKEND_WEBGPU takes the unused 1<<2 bit + needs
the matching eUserPref_GPUBackendType DNA value; gpu gtest bootstrap needs NO Python.
Top risks: R1 combined-sampler binding remap (T2 probes), R2 Dawn+Tint native build (T1
probes), R3 geometry-stage gap (ZERO geometry create-infos at pin → M6 concern, not M3).

- [x] **M3.T1 [gpu-backend]** **PASS** (77dd1ea, notes/gpu-dawn-probe.md): full chain GLSL→
  SPIR-V→Tint→WGSL→CreateShaderModule validates clean on headless Dawn/Metal (M4 Pro). Dawn
  pinned chromium/7989 @ 36cf1fae0cd8. **Three load-bearing T7 spec deltas vs the architecture
  doc:** (1) Tint is IR-based: ReadIR→ProgramFromIR→Generate (old Read→Program API gone);
  (2) Tint's SPV reader hardcodes SPV_ENV_VULKAN_1_1 → **shader compiler must emit SPIR-V 1.3
  (shaderc vulkan_1_1), NOT vulkan_1_2**; (3) link the monolithic dawn::webgpu_dawn, C++20
  required, Dawn codegen needs a working host python (Homebrew 3.14 pyexpat ABI-broken —
  build.sh pins 3.13). **R1 characterized AND controllable**: sampler split invents a sampler
  binding that bumps subsequent UBO bindings (deterministic); spirv::reader::Options::
  sampler_mappings controls it → T2 = mapping exercise, not open risk.
  **Linux device-free chain RECONCILED:** the checkout-relative locked-Ninja smoke now builds
  exact native shaderc v2025.4 plus the harvested Wasm closure against the same Dawn/Tint pin;
  Node 22.16.0 produces 498 byte-identical WGSL bytes (`sha256:2516371cb532`). The retained
  Linux precompiled shaderc identifies as v2023.8 and is intentionally not an oracle (it changed
  the homogeneous position constant). Wrong Dawn pins fail before output allocation. Live Dawn
  validation still rejects llvmpipe with `PROBE_BLOCKED`, so this reconciliation creates no M3
  receipt and leaves **M3-LINUX-REPLAY** blocked by s7. Evidence:
  `notes/m3-t1-shader-chain-linux-reconcile-20260821.md`.
- [x] **M3.T2 [gpu-backend]** **PASS** (4671835, notes/gpu-binding-map-spec.md = NORMATIVE for
  T7): Blender's scheme = single set-0, dense sequential bindings (vk_shader_interface.cc:205).
  Default Tint per-stage renumbering BREAKS cross-stage layouts (negative control: Dawn REJECTS
  pipeline — R1 confirmed real). Fix: sampler_mappings keyed by original {0,N} → {0,256+N};
  pipeline creation PASSES with explicit BGL. **T7 HARD RULE: non-empty map disables the
  conflict pass — EVERY combined sampler must be mapped.** Open for T7: sampler arrays
  (probe first), SAMPLER_BASE policy, sampler/texture type inference for BGL.
  **Linux device-free mapping RECONCILED:** identical native and Wasm shaderc v2025.4 +
  Dawn/Tint `36cf1fae` executions now assert the complete two-stage resource census for both
  default Tint and `{0,1}->{0,257}, {0,2}->{0,258}`. Their complete 6,911-byte evidence is
  byte-identical (`sha256:26e1351ee716`). The build is checkout-relative, exact-pin and
  locked-Ninja only; wrong Dawn rejects before allocation. The historical C1 rejection/C2
  pipeline acceptance still requires an accepted hardware adapter for a fresh Linux replay;
  current llvmpipe stops at `PROBE_BLOCKED` and creates no receipt. Evidence:
  `notes/m3-t2-bindmap-linux-reconcile-20260821.md`.
- [x] **M3.T3 [gpu-backend]** **DEVICE-LIVE PROVEN** (66500f0 patch 0011 + 8607fac sandbox
  proof): GHOST_ContextWGPU (130 LOC — half the estimate, WebGPU implicit model) brings up a
  live WGPUDevice+queue on Dawn/Metal via the same createOffscreenContext path; patch 0011 =
  context class + enum + SystemHeadless case + ghost CMake + WITH_WEBGPU_BACKEND option
  (default OFF). Native harness VIABLE: lib/macos_arm64 at pin SHA 5a140a8 out-of-tree (2.4GB,
  upstream untouched), native headless configure 11s. Dawn link = monolithic libwebgpu_dawn.a
  + 7 frameworks; **Tint NOT needed until T7**; C++20 native (no shim). The Linux preflight
  found that the frozen native context still selected Metal unconditionally. Patch 0149 is the
  verified correction (Metal/macOS, Vulkan/Linux, D3D12/Windows, no native browser selection)
  and is now composed into the SHA-256-bound canonical source snapshot. The checkout-relative
  driver requires that integrated postimage, stages it outside read-only `upstream/`, compiles it
  through pinned Dawn's locked CMake graph, and rejects the current llvmpipe adapter before the
  context path or receipt allocation. Root/descendant controls and final no-work are green; the
  source-integration prerequisite is closed while the hardware replay remains blocked by s7.
  Remaining implementation half folded into T4. See `notes/gpu-t3-harness.md` and
  `notes/m3-t3-context-linux-preflight-20260821.md`.
- [x] **M3.T4 [gpu-backend]** CLOSED (`212e1a4`, patch 0012; driver acceptance
  `ef4ff73`): `GPU_BACKEND_WEBGPU` and its DNA mirror are registered, all seven
  `gpu_context.cc` dispatch points select WebGPU, the CMake source block builds
  `WGPUBackend`/`WGPUContext`, and the native Dawn/Metal full-closure verifier reached a live
  context through `GPU_backend_type_selection_set(WEBGPU)` and `GPU_context_create`. Later
  GPU-suite rounds replace every skeleton allocator. This is active-plan reconciliation;
  the fresh Linux M3 receipt remains blocked by the named s7 hardware-adapter condition.
- [x] **M3.T7.pre [gpu-backend]** COMPLETE (4f36210, notes/gpu-t7pre-findings.md): shader-
  compiler module standalone-proven 4/4 on live Dawn (bindmap re-validated; type-inference
  table COMPLETE + live-validated for Float/Shadow/Uint arms; compute+SSBO+atomic pipeline
  created → **T8's R6 pre-cleared**; negative control holds). Sampler arrays: **broken in
  Tint's reader itself** ("arrays of handle types are not supported", parser.cc:200, pre-
  split) → **T7 must unroll sampler arrays at GLSL codegen**; map is per-element-ready.
  **Integration hazard caught: shaderc's bundled SPIRV-Tools vs Tint's static one must not
  meet in a link — use Blender's shaderc shared library.** T7 = wiring, not development.
  **Linux device-free contract RECONCILED:** the checkout-relative driver now checksum-binds
  exact shaderc v2025.4 and Dawn/Tint `36cf1fae`, selects Vulkan on Linux, uses only locked
  Ninja builds, and proves six compiler/interface contracts before any live-device request.
  Root and descendant runs emit identical 249-byte evidence
  (`sha256:db4b0c2fe03e`); wrong pins and invalid modes reject before output allocation. The
  live path independently identifies llvmpipe and exits 5 with one `PROBE_BLOCKED` before
  device creation, so no pipeline or M3 receipt is claimed. Historical Metal 4/4 remains the
  live proof; **M3-LINUX-REPLAY** still requires accepted hardware. Evidence:
  `notes/m3-t7pre-linux-reconcile-20260821.md`.
- [x] **M3.T7.integrated [gpu-backend]** RECONCILED on Linux: the canonical in-tree compiler
  postimage (interface map, shaderc/Tint compiler, cache, and six exact source/header inputs) now
  builds through the existing locked native and Wasm graphs and runs five device-free contracts
  for cold/warm cache identity, entry-point reflection, compute atomics, storage visibility, and
  17-sampler compaction. Native and Node 22.16.0 emit identical 469-byte evidence and four
  byte-identical cache entries against shaderc v2025.4 plus Dawn/Tint `36cf1fae`; source is bound
  to the canonical clean-pin replay before evidence allocation, and wrong Dawn rejects with zero
  allocations. This is CPU translation/layout proof only: no adapter/device or receipt is created,
  and **M3-LINUX-REPLAY** remains blocked by s7. Evidence:
  `notes/m3-t7-integrated-linux-reconcile-20260821.md`.
- [x] **M3.T7.frontend.integrated [gpu-backend]** RECONCILED on Linux: the canonical in-tree
  shader frontend now has a checkout-relative, device-free native/Wasm contract covering all 39
  distinct image types, all 63 texture formats, all eight qualifier patterns, and 30 std140
  layouts. Its unchanged pre-fix oracle caught `AtomicInt2DArray` losing the `Array` suffix;
  patch 0150 restores `isampler2DArray`/`iimage2DArray`, and the source freezer composes that
  postimage into the exact 257-path canonical snapshot. Root and descendant runs emit identical
  313-byte evidence against pinned Dawn, emcc, Node, and byte-identical fmt inputs; wrong identities
  reject before evidence. It creates no instance, adapter, device, shader module, pipeline, or
  receipt; live shader validation remains owned by **M3-LINUX-REPLAY** and blocked by s7. Evidence:
  `notes/m3-t7-frontend-integrated-linux-reconcile-20260821.md`.
- [x] **M3.T7.rewrite.integrated [gpu-backend]** RECONCILED on Linux: the canonical in-tree
  post-preprocessor shader transforms now run in the existing checkout-relative, device-free
  native/wasm32 frontend contract. Four added families cover nested texel-buffer helper inlining,
  seven integer-sampler calls plus controls, all physical 1D-array sampled/storage operations,
  and finite-builtin lowering. The unchanged oracle caught longer `myisnan(`/`myisinf(`
  identifiers injecting unused helpers; patch 0151 now requires a builtin identifier boundary.
  Root and descendant runs emit identical 581-byte evidence against exact source/tool identities. No
  adapter, device, shader module, pipeline, or receipt is created; live validation remains owned
  by **M3-LINUX-REPLAY** and blocked by s7. Evidence:
  `notes/m3-t7-rewrite-integrated-linux-reconcile-20260821.md`.
- [x] **M3.T7.push-array.integrated [gpu-backend]** RECONCILED on Linux: the canonical
  `WGPUShader::push_constant_set` body is extracted byte-for-byte with unique fail-closed
  boundaries and compiled into the existing device-free native/Wasm frontend contract. Five
  scalar/vector arrays cover 19 elements, all 148 payload bytes, and all 156 std140 padding bytes;
  native and Node 22.16.0 output is byte-identical at 669 bytes. A malformed-method control allocates
  no generated output, canonical replay is bound before extraction, and both targets end at
  locked-Ninja no-work. It creates no adapter/device/buffer or receipt and does not claim the
  separately found mat3 gap. Evidence:
  `notes/m3-t7-push-array-integrated-linux-reconcile-20260821.md`.
- [x] **M3.T7.mat3-packing [gpu-backend]** COMPLETE (patch 0152): the canonical writer now packs
  each float3x3 as three 12-byte columns at a 16-byte std140 stride, matching Vulkan. The extracted
  native/Wasm contract binds all four pinned matrix declarations and every payload/padding byte;
  malformed array/matrix methods fail before evidence allocation. The 257-path canonical freeze,
  windowed rebuild/no-work, and exact receipts are recorded in
  `notes/m3-t7-mat3-packing-integrated-linux-20260821.md`. Fresh M3 receipt ownership remains with
  M3-LINUX-REPLAY under the live s7 hardware blocker.
- [x] **M3.T6.integrated [gpu-backend]** RECONCILED on Linux: a checkout-relative,
  device-free native/Wasm contract now compiles the canonical in-tree common-buffer and
  readback-registry postimages directly. Five contracts cover the exact 32-case usage matrix,
  alignment/index helpers, invalid-buffer behavior, move lifetime, and real invalid-readback
  ticket lifecycle. Native and Node 22.16.0 emit identical 348-byte evidence against clean Dawn
  `36cf1fae` and emcc 6.0.5; the driver binds canonical clean-pin replay before evidence,
  rejects a wrong Dawn with zero allocations, and ends both targets at locked-Ninja no-work.
  It creates no adapter/device or receipt; the historical live 5/5 buffer replay remains owned
  by **M3-LINUX-REPLAY** and blocked by s7. Evidence:
  `notes/m3-t6-integrated-linux-reconcile-20260821.md`.
- [x] **M3.T6.pixel.integrated [gpu-backend]** RECONCILED on Linux: the existing
  device-free buffer contract now also compiles the canonical CPU-backed pixel-upload buffer and
  its real guardedalloc closure in both native and Wasm graphs. A sixth contract covers seven
  allocation sizes, exact size/native-handle semantics, duplicate-map and mapped/oversized-upload
  rejection, 4,869 preserved bytes, and stable remapping. Native and Node 22.16.0 emit identical
  441-byte evidence against clean Dawn `36cf1fae`, emcc 6.0.5, byte-identical fmt headers, and 15
  exact source inputs; canonical replay is bound before evidence, wrong Dawn/Node identities
  allocate nothing, and both targets end at locked-Ninja no-work. It creates no instance, adapter,
  device, GPU buffer, texture, upload, or receipt; live pixel upload remains owned by
  **M3-LINUX-REPLAY** and blocked by s7. Evidence:
  `notes/m3-t6-pixel-integrated-linux-reconcile-20260821.md`.
- [x] **M3.T6.readback-capacity.integrated [gpu-backend]** RECONCILED on Linux: the real
  readback registry's exact terminal-record limit now runs in the existing device-free
  native/Wasm buffer contract. The seventh contract fills all 256 slots, proves overflow is
  fail-closed, retires and replaces exactly 128 records, restores the cap, and proves complete
  reuse with zero pending GPU work. Root and descendant runs emit identical 529-byte evidence;
  canonical replay, locked windowed no-work, and REUSE 2,004/2,004 are green. It creates no
  instance, adapter, device, GPU buffer, callback, or receipt; live completion/ordering remains
  owned by **M3-LINUX-REPLAY** and blocked by s7. Evidence:
  `notes/m3-t6-readback-capacity-integrated-linux-reconcile-20260821.md`.
- [x] **M3.T6.vertex.integrated [gpu-backend]** RECONCILED on Linux: a checkout-relative,
  device-free native/Wasm contract includes the canonical in-tree vertex-buffer translation unit
  directly and exercises its private CPU helpers without copying them. Six contracts exhaust all
  1,024 signed 10-bit component encodings, every attribute detection slot, 1,024 interleaved and
  17 deinterleaved vertices, bounded truncation, and all eight base/flag usage combinations. Native
  and Node 22.16.0 emit identical 422-byte evidence against clean Dawn `36cf1fae` and emcc 6.0.5;
  canonical replay is bound before evidence, wrong Dawn/Node identities allocate nothing, and both
  targets end at locked-Ninja no-work. It creates no instance, adapter, device, GPU buffer, upload,
  or receipt; live vertex allocation/draw proof remains owned by **M3-LINUX-REPLAY** and blocked by
  s7. Evidence: `notes/m3-t6-vertex-integrated-linux-reconcile-20260821.md`.
- [x] **M3.T6.point-restart.integrated [gpu-backend] COMPLETE (patch 0154):** WebGPU point-list
  restart markers are now compacted stably before `IndexBuf::init()` squeezes the data, closing the
  silent out-of-range fetch path while preserving surviving point order. The exact extracted method
  runs through Blender's real base initializer in native/wasm32 for mixed, all-restart, wide-u32,
  and rebased-u16 inputs plus subrange/device metadata; both legs emit identical 692-byte evidence.
  No instance, adapter, device, GPU buffer, or receipt is created; live proof remains owned by
  **M3-LINUX-REPLAY** under s7. Evidence:
  `notes/m3-t6-point-restart-integrated-linux-20260821.md`.
- [x] **M3.T9.integrated [gpu-backend]** RECONCILED on Linux: a checkout-relative,
  device-free native/Wasm contract now compiles the canonical in-tree texture-format and
  RGB-to-RGBA conversion postimages against Blender's real `TextureFormat` enum. Five contracts
  cover all 63 format rows, capability classification, five bidirectional linear/sRGB view
  pairs, every byte of all 13 promotion paths, and invalid/boundary behavior. Native and Node
  22.16.0 emit identical 426-byte evidence against Dawn `36cf1fae` and emcc 6.0.5; canonical
  replay is bound before evidence, wrong Dawn/Node identities allocate nothing, and both targets
  end at locked-Ninja no-work. It creates no instance, adapter, device, texture, or receipt; the
  historical live T9 creation/upload/readback proof remains owned by **M3-LINUX-REPLAY** and
  blocked by s7. Evidence: `notes/m3-t9-integrated-linux-reconcile-20260821.md`.
- [x] **M3.T9.rgb9e5 [gpu-backend] COMPLETE (patch 0153):** the canonical texture path now
  classifies `UFLOAT_9_9_9_EXP_5` as native RGB9E5 and uses exact shared-exponent packing for
  upload/clear plus unpacking for readback. Three pinned Dawn decode vectors and seven
  canonical/edge encodes run byte-identically in native/wasm32, with exact shipping-call-site
  and eight-source binding. Live texture proof and the strict receipt remain owned by
  **M3-LINUX-REPLAY** under s7. Evidence:
  `notes/m3-t9-rgb9e5-integrated-linux-20260821.md`.
- [x] **M3.T9.rg11b10 [gpu-backend] COMPLETE (patch 0156):** the canonical RG11B10 upload,
  readback, and clear paths now share the pinned Vulkan backend's exact F32↔F11/F10 conversion
  policy instead of an ad-hoc encoder that mishandled infinities, NaNs, and exponent boundaries.
  Sixteen encode and nine decode vectors run byte-identically in native/wasm32 and bind all three
  shipping call sites plus the exact Vulkan oracle sources. No instance, adapter, device, texture,
  or receipt is created; live proof remains owned by **M3-LINUX-REPLAY** under s7. Evidence:
  `notes/m3-t9-rg11b10-vulkan-parity-20260821.md`.
- [x] **M3.F7.index-subrange [gpu-backend] COMPLETE (patch 0157):** multi-viewport indexed
  draws now retain both the parent-buffer byte window and the squeezed-u16 base vertex through a
  shared binding plan, matching the existing single-pass semantics. Native/wasm32 metadata cases
  cover u16 and u32 subranges byte-identically; exact source checks bind ordinary/multi-viewport
  draw arms and separately census EEVEE-shadow multi-viewport and mesh-subrange producers. The
  real windowed Wasm product compiles and links the changed batch path. No instance, adapter,
  device, draw, browser, or receipt is created; live pixel proof remains owned by
  **M3-LINUX-REPLAY** under s7. Evidence:
  `notes/m3-f7-index-subrange-binding-20260821.md`.
- [x] **M3.F7.indirect-subrange [gpu-backend] COMPLETE (patch 0158):** indirect indexed draws
  now bind the complete parent allocation because Blender's generated `DrawCommandIndexed`
  already carries the absolute first index and squeezed-u16 base vertex; the former WebGPU path
  applied the subrange start twice. The canonical native/wasm32 metadata contract covers direct
  and indirect u16/u32 plans and exact-source binds both shipping encoders plus the pinned command
  producer. The real windowed Wasm product compiles and links the changed batch path. No instance,
  adapter, device, draw, browser, or receipt is created; live pixel proof remains owned by
  **M3-LINUX-REPLAY** under s7. Evidence:
  `notes/m3-f7-indirect-index-subrange-20260821.md`.
- [x] **M3.T10.state.integrated [gpu-backend]** RECONCILED on Linux: a checkout-relative,
  device-free native/Wasm contract now compiles the canonical in-tree fixed-function state table
  directly against Blender's real GPU enums. Four exhaustive contracts cover all 16 blend rows,
  seven depth modes, 16 stencil test/operation pairs, three cull modes, front-face and provoking-
  vertex behavior, and all 64 write masks. Native and Node 22.16.0 emit identical 372-byte
  evidence against clean Dawn `36cf1fae` and emcc 6.0.5; canonical replay is bound before
  evidence, wrong Dawn/Node identities allocate nothing, and both targets end at locked-Ninja
  no-work. It creates no instance, adapter, device, pipeline, or receipt; historical live T10
  pipeline/pixel proof remains owned by **M3-LINUX-REPLAY** and blocked by s7. Evidence:
  `notes/m3-t10-state-integrated-linux-reconcile-20260821.md`.
- [x] **M3.T10.pipeline.integrated [gpu-backend]** RECONCILED on Linux: a checkout-relative,
  device-free native/Wasm contract now compiles the canonical in-tree render-pipeline postimage
  directly. Four contracts cover all 11 primitive rows and all 96 component/length/fetch
  combinations, including normalized signed-I10 to `Snorm8x4` and the fail-visible triangle-fan
  fallback. Native and Node 22.16.0 emit byte-identical 232-byte stdout plus byte-identical exact
  diagnostics against clean Dawn `36cf1fae` and emcc 6.0.5; canonical replay is bound before
  evidence, wrong Dawn/Node identities allocate nothing, and both targets end at locked-Ninja
  no-work. It creates no instance, adapter, device, render pipeline, or receipt; historical live
  T10 proof remains owned by **M3-LINUX-REPLAY** and blocked by s7. Evidence:
  `notes/m3-t10-pipeline-integrated-linux-reconcile-20260821.md`.
- [x] **M3.T10.dummy-zero-stride [gpu-backend] COMPLETE (patch 0159):** missing vertex
  attributes now use Dawn-valid zero-stride, vertex-stepped bindings over one 16-byte zero buffer,
  removing the former 4,096-instance ceiling for `Float32x4` inputs. The canonical native/wasm32
  contract covers all 32 shader input types and source-binds Dawn's stride-zero pipeline and
  draw-range validators. No instance, adapter, device, pipeline, draw, or receipt is created;
  live proof remains owned by **M3-LINUX-REPLAY** under s7. Evidence:
  `notes/m3-t10-dummy-zero-stride-20260821.md`.
- [x] **M3.T10.render-pipeline-identity [gpu-backend] COMPLETE (patch 0160):** the process-wide
  batch/immediate pipeline pools now key a shader by both address and a monotonic per-instance
  identity, so guardedalloc address reuse cannot return a prior shader's retained pipeline. The
  canonical native/wasm32 contract simulates 4,096 lifetimes at one address with 4,096 distinct
  keys and source-binds all three shipping constructors. The real windowed product compiles and
  links the changed shader/pipeline/batch/immediate paths. No instance, adapter, device, pipeline,
  draw, or receipt is created; live proof remains owned by **M3-LINUX-REPLAY** under s7. Evidence:
  `notes/m3-t10-render-pipeline-identity-20260821.md`.
- [x] **M3.T10.pipeline-alias-key [gpu-backend] COMPLETE (patch 0161):** the render-pipeline
  key now length-frames every vertex-attribute alias, separating valid alias sequences whose
  undelimited bytes concatenate identically but whose shader-location matches can differ. Two
  real `GPUVertFormat` collision inputs run byte-identically in native/wasm32, and the real
  windowed product compiles and links the corrected cache path. No instance, adapter, device,
  pipeline, draw, or receipt is created; live proof remains owned by **M3-LINUX-REPLAY** under
  s7. Evidence: `notes/m3-t10-pipeline-alias-key-20260821.md`.
- [x] **M3.T7.cache-envelope [gpu-backend] COMPLETE (patch 0162):** the WGSL disk-cache reader
  now requires EOF immediately after the bounded checksummed payload, so appended or torn bytes
  force translation instead of accepting a valid prefix. The exact shipping reader's native/
  wasm32 contract proves a clean hit, appended-byte miss, unchanged output sentinels, and cleanup;
  the real windowed product compiles and links the corrected cache path. No instance, adapter,
  device, shader module, pipeline, browser receipt, or result promotion is created. Evidence:
  `notes/m3-t7-cache-envelope-20260821.md`.
- [x] **M3.T7.cache-key-binding [gpu-backend] COMPLETE (patch 0163):** each v3 WGSL cache
  envelope now stores and verifies the requested 128-bit content key before reading stage lengths
  or allocating outputs, so a valid entry copied under another key fails closed. The exact
  shipping reader's native/wasm32 contract proves substitution rejection with unchanged caller
  sentinels, and the real windowed product compiles and links the corrected cache path. No
  instance, adapter, device, shader module, pipeline, browser receipt, or result promotion is
  created. Evidence: `notes/m3-t7-cache-key-binding-20260821.md`.
- [x] **M3.T10.indexed-strip-format [gpu-backend] COMPLETE (patch 0155):** direct and indirect
  indexed line-strip, line-loop, and triangle-strip draws now carry their bound Uint16/Uint32
  format into the render-pipeline descriptor and cache key. Pinned Dawn rejects the former
  Undefined format at DrawIndexed validation. The device-free native/wasm32 contract exhausts all
  33 primitive/index-format combinations and source-binds both shipping batch call sites. No
  adapter, device, pipeline, draw, or receipt is created; live proof remains owned by
  **M3-LINUX-REPLAY** under s7. Evidence:
  `notes/m3-t10-indexed-strip-format-integrated-linux-20260821.md`.
- [x] **M3.T10.query.integrated [gpu-backend]** RECONCILED on Linux: a checkout-relative,
  device-free native/Wasm contract now compiles the canonical in-tree conservative occlusion-query
  implementation directly and verifies initial state, five valid begin/end transitions, guarded
  duplicate transitions, and seven exact zero-hit results. Root and descendant runs emit identical
  252-byte evidence against clean Dawn `36cf1fae`, emcc 6.0.5, and Node 22.16.0; wrong Dawn/Node
  identities allocate no evidence and both targets end at locked-Ninja no-work. The audit also
  registers `webgpu-sync-occlusion-query`: the existing conservative-fallback GPU test is an honest
  implementation test, not browser gizmo-selection parity. It creates no instance, adapter, device,
  query set, or receipt; a real async result path remains an M5 caller redesign and live proof stays
  owned by **M3-LINUX-REPLAY**, blocked by s7. Evidence:
  `notes/m3-t10-query-integrated-linux-reconcile-20260821.md`.
- [x] **M3.T10.bindspace.integrated [gpu-backend]** RECONCILED on Linux: a
  checkout-relative, device-free native/Wasm contract now compiles the canonical in-tree
  state manager plus Blender's real base `StateManager` constructor. Four contracts cover
  default immutable/mutable state, last-bind-wins texture/image maps, namespace isolation,
  resource-wide and all-bind cleanup, implicit state/barrier preservation, and the reusable
  signal/wait fence lifecycle. Root and Node 22.16.0 output is byte-identical at 300 bytes
  (`sha256:2112ce5e5dcc`); wrong Dawn/Node/fmt identities allocate no evidence, canonical
  replay is bound before allocation, and both targets end locked-Ninja no-work. It creates no
  instance, adapter, device, bind group, command, or receipt; live assembly/ordering remains
  owned by **M3-LINUX-REPLAY** and blocked by s7. Evidence:
  `notes/m3-t10-bindspace-integrated-linux-reconcile-20260821.md`.
- [x] **M3.T10.sampler-anisotropy [gpu-backend] COMPLETE (patch 0164):** the shipping
  sampler descriptor now preserves Blender's mip-gated 2x/4x/8x/16x anisotropy request and
  forces Dawn's required linear min/mag/mip filters. The exact extracted native/wasm32 contract
  covers every level, the no-mipmap gate, custom samplers, and all address modes byte-identically;
  the real windowed product compiles and links the corrected context path. No adapter, device,
  sampler, browser receipt, or result promotion is created. Evidence:
  `notes/m3-t10-sampler-anisotropy-20260822.md`.
- [x] **M3.T9.feature-render-attachments [gpu-backend] COMPLETE (patch 0165):** texture
  allocation now derives render-attachment eligibility from the exact enabled optional-format
  features, restoring the production Grease Pencil `UNORM_16` render mask while preserving the
  independent RG11B10 and D32/S8 feature gates. A 16-case native/wasm32 contract binds core,
  Unorm16, Tier1, RG11B10, and D32/S8 positive and negative decisions byte-identically; the real
  windowed product compiles and links the corrected texture path. No adapter, device, framebuffer,
  browser receipt, or result promotion is created. Evidence:
  `notes/m3-t9-feature-render-attachments-20260822.md`.
- [x] **M3.T10.dummy-attribute-default [gpu-backend] COMPLETE (patch 0166):** the shared
  zero-stride dummy vertex buffer now contains Blender's Vulkan/default-attribute
  `(0,0,0,1)` value instead of WebGPU's all-zero initialization, restoring the fourth
  component used by missing orcos. The exact shipping method runs in a device-free
  native/wasm32 create/write contract with byte-identical evidence and one queue-ordered
  16-byte write; the real windowed product compiles and links the corrected context path.
  No adapter, device, buffer, draw, browser receipt, or result promotion is created.
  Evidence: `notes/m3-t10-dummy-attribute-default-20260822.md`.
- [x] **M3.T3.native-float32-filterable-patch [gpu-backend] VERIFIED (patch 0167):**
  native GHOST now has an adapter-guarded request for `Float32Filterable`, matching the
  backend's gated R/RG/RGBA32-float filtering policy and the browser's request of every
  exposed adapter feature. The T3 driver applies 0167 only to an isolated source stage,
  compiles the real GHOST context against pinned Dawn, and exhausts all 256 combinations of
  its eight optional features; extractor mutation controls reject missing, mismatched,
  duplicated, side-effecting, and ambiguous selectors. The live Vulkan control still rejects
  llvmpipe and emits no receipt. Evidence:
  `notes/m3-t3-native-float32-filterable-20260822.md`.
- [x] **M3.T3.native-float32-filterable-integration [gpu-backend] COMPLETE:** patch 0167's
  verified postimage is composed into the canonical 257-path / 20,258-entry source snapshot;
  the T3 verifier reverse-checks it, canonical replay is exact, and the real windowed product
  compiles, links, and ends locked-Ninja no-work. The live control still rejects llvmpipe and
  creates no hardware receipt. Evidence:
  `notes/m3-t3-native-float32-filterable-20260822.md`.
- [x] **M3.T9.packed-upload-row-stride [gpu-backend] COMPLETE (patch 0168):** strided
  texture uploads now size each source row with Blender's whole-texel helper, so compact
  RGB10A2 and R11G11B10 host rows remain four bytes per texel instead of being multiplied by
  their logical component count. The exact call site and six helper cases pass byte-identically
  in native/wasm32, canonical replay is exact, and the real windowed product rebuilds and ends
  locked-Ninja no-work. No adapter, device, texture, browser receipt, or result promotion is
  created. Evidence: `notes/m3-t9-packed-upload-row-stride-20260822.md`.
- [x] **M3.T6.i10-subrange-update [gpu-backend] COMPLETE (patch 0169):** vertex-buffer
  subrange updates now transcode complete signed packed-normal fields to the `Snorm8x4`
  storage representation used by full uploads, while partial packed fields reject atomically.
  The native/wasm32 contract covers interleaved and deinterleaved ranges, full-upload identity,
  four rejection controls, and constant work at a `UINT32_MAX` vertex census; canonical replay
  is exact and the real windowed product rebuilds and ends locked-Ninja no-work. No adapter,
  device, buffer, draw, browser receipt, or result promotion is created. Evidence:
  `notes/m3-t6-i10-subrange-update-20260822.md`.
- [x] **M3.T6.buffer-range-overflow [gpu-backend] COMPLETE (patch 0174):** the shared
  WebGPU buffer wrapper now rejects unrepresentable 4-byte alignment and overflowed
  update/read ranges before any Dawn call. Seven checked-alignment and four range-boundary
  cases through `SIZE_MAX` pass byte-identically in native/wasm32; canonical replay is exact,
  and the real windowed product rebuilds and ends locked-Ninja no-work. No adapter, device,
  buffer operation, browser receipt, or result promotion is created. Evidence:
  `notes/m3-t6-buffer-range-overflow-20260822.md`.
- [x] **M3.T6.storage-copy-ranges [gpu-backend] COMPLETE (patch 0175):** the
  vertex-to-storage copy path now rejects zero-size, misaligned, and out-of-allocation source or
  destination spans before creating a Dawn command encoder. Nine boundary cases through
  `SIZE_MAX` pass byte-identically in native/wasm32; canonical replay is exact, and the real
  windowed product rebuilds and ends locked-Ninja no-work. No adapter, device, buffer command,
  browser receipt, or result promotion is created. Evidence:
  `notes/m3-t6-storage-copy-ranges-20260822.md`.
- [x] **M3.T6.buffer-allocation-limit [gpu-backend] COMPLETE (patch 0176):** the shared
  WebGPU buffer wrapper now checks the live device's `maxBufferSize` after checked alignment and
  before mutating wrapper state or calling Dawn, so an over-limit descriptor cannot be accepted
  as a non-null error buffer. Ten zero, exact-limit, over-limit, and `SIZE_MAX` cases pass
  byte-identically in native/wasm32; canonical replay is exact, and the real windowed product
  rebuilds and ends locked-Ninja no-work. No adapter, device, buffer allocation, browser receipt,
  or result promotion is created. Evidence:
  `notes/m3-t6-buffer-allocation-limit-20260822.md`.
- [x] **M3.T9.texture-allocation-limits [gpu-backend] COMPLETE (patch 0177):** texture
  creation now rejects physical 1D/2D/array/3D extents and mip counts outside the live device
  limits before Dawn can return a non-null error texture. Twenty-six zero, exact-limit,
  over-limit, and NPOT mip cases pass byte-identically in native/wasm32; canonical replay is
  exact, and the real windowed product rebuilds and ends locked-Ninja no-work. No adapter,
  device, texture, browser receipt, or result promotion is created. Evidence:
  `notes/m3-t9-texture-allocation-limits-20260822.md`.
- [x] **M3.T9.texture-upload-layout [gpu-backend] COMPLETE (patch 0178):** uncompressed
  texture updates now validate their physical copy box and every source/device byte product
  before allocating conversion storage or reading caller memory. Fourteen tight, strided, and
  overflow layout cases plus 13 exact region boundaries pass byte-identically in native/wasm32;
  canonical replay is exact and the real windowed product rebuilds then ends locked-Ninja
  no-work. No adapter, device, texture, upload, browser receipt, or result promotion is created.
  Evidence: `notes/m3-t9-texture-upload-layout-20260822.md`.
- [x] **M3.T9.texture-readback-layout [gpu-backend] COMPLETE (patch 0179):** synchronous and
  asynchronous texture readbacks now preflight tight and 256-byte-padded rows, every native/
  wasm32 host product, and the live device `maxBufferSize` before allocating a host or WebGPU
  buffer. Five exact-limit layouts and ten zero/overflow/over-limit cases pass byte-identically;
  canonical replay is exact and the real windowed product rebuilds then ends locked-Ninja
  no-work. No adapter, device, texture, readback, browser receipt, or result promotion is created.
  Evidence: `notes/m3-t9-texture-readback-layout-20260822.md`.
- [x] **M3.T9.bc-upload [gpu-backend] COMPLETE (patch 0170):** Blender's existing BC1/2/3
  DDS mip blocks now reach `Queue::WriteTexture` with Dawn's physical 4x4 extent, exact block-row
  stride, edge, layer, and overflow validation. Unsupported texture types or devices without
  `TextureCompressionBC` fail allocation so the pinned image caller takes its faithful
  uncompressed fallback. Seven layouts and all nine texture-type enumerators pass byte-identically
  in native/wasm32; canonical replay is exact and the real windowed product rebuilds and ends
  locked-Ninja no-work. No live device, texture, sample, browser receipt, or result promotion is
  claimed. Evidence: `notes/m3-t9-bc-upload-20260822.md`.
- [x] **M3.T9.component-swizzle [gpu-backend] COMPLETE (patch 0171):** sampled texture views
  now apply Blender's documented `rgba` / `xyzw` / `01` channel masks through Dawn's stable
  `TextureComponentSwizzle` feature. Native device creation requests the feature only when the
  adapter exposes it; invalid masks and unavailable non-identity swizzles fail closed instead of
  silently sampling identity channels. Ten symbols pass byte-identically in native/wasm32, the
  native GHOST contract exhausts all 512 combinations of its nine optional features, canonical
  replay is exact, and the real windowed product rebuilds and ends locked-Ninja no-work. No live
  adapter, sampled texture, pixel, browser receipt, or result promotion is claimed. Evidence:
  `notes/m3-t9-texture-component-swizzle-20260822.md`.
- [x] **M3.T4–T10 [gpu-backend]** CLOSED by the accepted successor rounds: the registered
  backend now has real context/capabilities, buffer factories, shaderc→Tint→WGSL compilation,
  direct/indirect compute, textures/data conversion, framebuffer/pipeline/state, immediate, and
  batch paths. The final frozen macOS Dawn/Metal source passed the exact 197/197 GPU manifest,
  DrawWebGPU 2/2, and exact 1,003/1,003 shader manifest recorded in
  `notes/gpu-r26-migration-savepoint.md`; current canonical replay reproduces that source and both
  checked-in identity hashes. This closes the stale implementation-sweep item only. A fresh Linux
  strict receipt remains separately blocked by the named s7 hardware-adapter condition and must
  not be inferred from the historical proof.

### M3 frames-gate rounds 8-9 (2026-08-05, post-handoff resume — driver)

**FIRST RENDERED FRAMES PROVEN** (B1, temp-wire): blend family 12/12 byte-match, evidence
`sandbox/gpu-render-harness/evidence/first_frames_blend.png`. Landed: 0043 CopyDst (dd5a6fc),
0050 host-shared deferral — static_shaders 289→481/973 (2d54f06). Real-path green routed:

- [x] **M3.F1 [gpu-backend laneA]** DONE r9 (6823756, patch 0051): populate_builtins +
  builtin_blocks loops after sort_inputs(), per vk_shader_interface.cc:190-203.
- [x] **M3.F2 [gpu-backend laneA+laneB]** DONE both halves (ADR-005): 0052 clip-Y flip (laneA,
  6823756) + 0044 front-face swap + 0045 readback row-flip (laneB). **REAL-PATH BLEND 12/12 —
  DRIVER-VERIFIED by independent gtest run 2026-08-05.** texture gate held 64/64.
- [x] **M3.F3 [gpu-backend laneA]** DONE r9 (bf67491): 0053 GPU_WEBGPU standard_defines arm +
  0054 NAN_FLT non-foldable guard. static_shaders **481→513/973**, nan bucket 32→0, no new
  buckets. Driver spot-checked artifacts + reverse-applies.
- [x] **M3.F4 [gpu-backend laneB]** CLOSED by successor rounds r8-r13 (patches 0046, 0055,
  0056, 0083; driver-verified): the attachment view is one layer, immediate mode is wired
  into the context lifecycle, compute dispatch executes the push-constant path, and faithful
  multi-pass viewport/layer emulation is implemented. `framebuffer_multi_viewport` passes,
  `immediate_*` is 2/2, and `push_constants*` is 10/10. This is active-plan reconciliation;
  the fresh Linux M3 receipt remains blocked by the named s7 hardware-adapter condition.
- [x] **M3.F5 [driver → worker]** RESULT (863e9b9+c588af3): **GPU_init COMPLETES + a real
  Blender shader COMPILES (full shaderc→Tint chain) in a real WebGPU tab.** Correct pixels
  gated on readback (F9-D). KEY FINDING: handoff's "comments not stripped" was a MISDIAGNOSIS —
  real cause = wasm32 int-width npos bug (StringRefBase::find int64_t -1 vs 32-bit size_t npos
  promotes ≠), patches 0060+0061 __EMSCRIPTEN__-guarded. **This also explains the dormant
  "data-race hunt" signature** (comment-assert with run-to-run-varying file set = thread
  arrival order picking which source hit the always-firing assert first) — data-race item
  CLOSED unless it reproduces post-0060. Evidence: sandbox/gpu-render-harness/evidence/
  intab_gpu_init_shader_finalize.txt.
- [x] **M3.F9 [gpu-backend]** RECONCILED by the accepted successor rounds: patch 0075
  publishes and clears `GPG`, and selects the Emscripten main-context workaround; patch 0055
  constructs and activates `WGPUImmediate` (`immediate_*` 2/2); patch 0076 completed the
  14-site `gpu/intern` wasm32 `npos` sweep. The F9-D prediction that the WM worker could block
  was falsified at r49: a same-worker wait starves the callback that must settle it. Patches
  0133/0138 instead provide the heap-owned tick-pumped backend primitive and exact tickets,
  while public L-B and caller L-C remain honestly registered under the partial M5 deferral
  `gpu-sync-readback-windowed` with its named structural blocker. This closes the stale F9
  umbrella accounting only; it makes no synchronous-caller, M5, or fresh Linux runtime claim.
- [x] **M3-hygiene [driver, boundary]** CLOSED (`5423913` + `904a5a8`, Linux replay
  `20260821T011519-2745630`): `patches/series` records the numbered development-history order,
  including the 0016b/0016c deviation. Because later shared-lane preimages are mutually
  dependent, `patches/canonical` now names the SHA-256-bound squashed clean-pin authority;
  the default replayer reproduces all 257 concrete upstream paths byte-for-byte.

### M4 T9 RESULT (2026-08-05, e48906b) + the new windowed gate

**Windowed `blender_browser` LINKED (zero symbol gaps, 921MB dev) + BOOTED in real Chrome,
deep into GPU init — every windowed seam validated** (GHOST factory, drawing-context map,
backend selection, GPU_context_create). Two blockers fixed in-lane: **-sJSPI dropped**
(ctor-suspend abort; ratified as **ADR-006** — worker-blocking waits under PROXY_TO_PTHREAD
replace suspension) and patch 0065 (missing per-module WITH_WEBGPU_BACKEND define in
windowmanager — latent gap in 0023). Shell: platform_web/shell/windowed.html, server :8123.

- [x] **M4.T10 RESULT (a1011f0, driver-verified 0066 clean):** dispatch premise WRONG — not a
  port alignment bug. Real causes: (1) wgpu_context.cc cast ghost context to NATIVE
  GHOST_ContextWGPU → read std::string SSO bytes as instance ptr (patch 0066,
  `__EMSCRIPTEN__ && !WITH_HEADLESS` seam — NOT WITH_GHOST_WEB, that define never reaches
  bf_gpu); (2) GHOST_WindowWeb ctor never called setDrawingContextType. Port AS-IS, nothing
  vendored. Boot now RUNS initializeDrawingContext → next gate below.
- [x] **M4.T11 RESULT (d4708b9, driver-verified): WINDOWED BOOT REACHES WM_main + BPY STARTUP
  IN A TAB** — device pre-acquired on the WM worker (probe: no cross-thread objects, workers
  HAVE navigator.gpu → **ADR-007** written from findings), GPU_context_create live,
  GPU_init completes windowed, real render passes submitted, bl_ui registers, stable main
  loop 20s+. Remaining: T12 surface/pixels (below); python-wasm: _multiprocessing + _sha3
  missing (non-fatal, caught — M2.3 "optional C-exts" debt now has real consumers, queue
  python-wasm task); imbuf: splash "unknown file-format" (non-fatal — check which reader
  is off in blender_web config).
- [x] **M4.T12 RESULT (d135063, driver-verified): FIRST WINDOW PIXELS — the GHOST WebGPU
  surface PAINTS THE TAB** (teal proof frame composited end-to-end: OffscreenCanvas transfer
  → worker surface → Configure 1800×1169 BGRA8 → GetCurrentTexture → submit → visible).
  Four root causes fixed in owned files (canvas-table check, cursor-EM_ASM guard, all-features
  device request, link flags). GHOST side COMPLETE for the pixels gate (getSurface() exposed).
  Teal clear = removable scaffolding once Blender's frame composites. Evidence:
  platform_web/shell/evidence/boot-transcript-0{1,2}-*.txt. Boot aborts at Blender's first
  UI draw on the backend triplet below (~4-5s boot-to-abort; loop health unmeasurable until
  then).
- [x] **M4.T13 r16 RESULT (536a8e6, 0092-0095, driver-verified incl. the PNG itself):
  BLENDER'S UI RENDERS IN A REAL CHROME TAB** — Quick Setup splash text + Layout workspace
  + header menus + toolbar icons + widgets, interactive (mouse/click/Esc), stable WM_main,
  ZERO Dawn validation errors, JS heap ~121MB. Root causes: draw_indirect implemented (0093);
  bind-group assembly completed incl. the load-bearing per-type→dense binding remap (0092);
  sync_backbuffer wraps surface GetCurrentTexture as back_left (0094); web-only NaN
  depthClearValue trap (0095 — native Dawn ignores it, emdawnwebgpu rejects). Census held
  148/158 byte-identical across 5 re-runs. Evidence:
  platform_web/shell/evidence/m4-first-ui-pixels-quicksetup-splash.png + transcript.
- [x] **M4.T14 r17 RESULT (f2291fc/8a67d9e/aa4653c, 0096+0097 clean, driver-verified incl.
  the upright capture): WINDOW RENDERS UPRIGHT** (elegant fix: clip-Y sign as pipeline
  override constant, flip_y=false only for the surface backbuffer — offscreen byte-identical,
  hit-testing aligned). **static_shaders 956/973 — ALL remaining 17 = registered deferral
  classes; the M3 gate has NO un-dispositioned item left.** Splash root-cause = LFS stubs
  (156/157 binary datafiles are pointers — M0-hygiene debt; pull authorized → r18). Mirror
  0-drift. Census held 148/158. New porting fact: shader_tool needs brace-balanced ifdef arms.
- [x] ~~M4.T14-old~~ (a) Y-FLIP of the surface present (dominant imperfection —
  whole window mirrored; ADR-005 fixed offscreen, the present composite path needs its half;
  likely a flip in the backbuffer blit/present or viewport transform when rendering to the
  surface-adopted back_left); (b) uniformity-5 (M3.F13 decision 1 — still owed, static
  951→~956; the LAST M3-gate code item); (c) stretch: imbuf splash root-cause (which reader
  is off in blender_web config — "IMB_load_image_from_memory: unknown file-format"); (d)
  lane-a-staging mirror sync (r16 flagged, driver-sanctioned as part of this round).
  DISPATCHED (patches 0096-0099).
- [x] **M4.python-debt RESULT (c1f6477, driver-verified):** _sha3+md5+sha1+blake2 ENABLED
  (M2.3 rationale was factually backwards — only _sha2 needs the prebuilt Hacl .a; digests
  byte-identical to native 3.13.13). _multiprocessing GENUINELY unbuildable (named
  semaphores absent in non-pthread emscripten libc; configure receipts) → documented
  thread-backed SemLock shim (scripts/deps/python-shims/, Pyodide-precedented);
  multiprocessing.synchronize imports → no asset dialog. libpython +1.04MB, atomic-swap
  harvest. NOTE for r17/windowed verify: the shim lives in the preloaded stdlib — the
  windowed .data must regenerate on relink for the dialog to disappear. (1) `WGPUBatch::draw_indirect` stub (wgpu_batch.cc:249) → BLI_assert abort at
  Blender's first UI batch — implement (WebGPU has native indirect draw; buffer already
  bindable per 0085 family). (2) UI bind-group assembly incomplete: Dawn "entries (1) !=
  expected (4)" for widget layout {texture@0, storage@1, uniform@2, sampler@256} + compute
  "binding index 2/11 not present" — complete draw-time bind-group assembly for
  texture+sampler+storage entries (0059/0085 machinery extends). (3) `sync_backbuffer`
  missing: mirror vk_context.cc:67 — set back_left colour attachment from
  GHOST_ContextWGPUWeb::getSurface() each activate() (~40-60 LOC wgpu_context.{cc,hh} +
  store ghost_context_). Then re-run windowed boot → BLENDER UI PIXELS → screenshot vs M4
  golden (idiff, pinned adapter).
- [x] **M4.T11 device-await plan RECONCILED by `d4708b9` and ADR-007:** the pinned-port
  probes falsified main-thread device handoff and same-thread blocking waits: WebGPU objects
  are realm-local, while a blocked WM worker cannot resolve its own promise. The accepted
  path acquires the adapter/device asynchronously on that WM worker before `main()` through
  the `wgpu-preinit-worker.js` post-js shim, then GHOST imports the stored device with
  `emscripten_webgpu_get_device()` and a featureless `CreateInstance(nullptr)`. Historical
  live proof reaches GPU initialization, Python/BPY startup, and the `WM_main` loop without
  JSPI/Asyncify; later async readback work retains ADR-007's kick-then-consume contract.
  This closes only the superseded device-await plan. **M4-LINUX-REPLAY** still owns the fresh
  Linux binding/receipt and remains blocked by s7's llvmpipe-only adapter.
- [x] **M3.F6 [gpu-backend laneA r10]** DONE (0055-0058, b0c94ce/fd007d8/cc3f34c/7b9ea5a, all
  reverse-apply clean): imm wiring → immediate 2/2; compute_dispatch real (pipeline cached ON
  WGPUShader — pointer-keyed pool rejected as stale-address bug) → push_constants **10/10**;
  gpu_ViewportIndex/gpu_Layer codegen → multi_viewport CRASH→honest FAIL; stretch: gl_PointSize
  redirect → static_shaders **519/973** (point_size bucket 54→0). Blend held 12/12.
  **DRIVER-VERIFIED independent run: immediate 2/2 + push_constants 10/10.**
- [x] **M3.F8 [gpu-backend]** RECONCILED by the accepted successor rounds. Patch 0059 records
  storage-image binds and the current shared resource assembler consumes them for compute and
  draw; patches 0077-0079 close the shader-environment and compute-specialization paths, with
  runtime pipeline variants keyed by exact override values. Patch 0080 changed subpass-input
  crashes into measurable behavior; `framebuffer_subpass_input_clearops` now passes, while the
  true input-attachment gap remains honestly registered as `subpass-input-attachment`. Patches
  0082/0086/0097 and the later gate rounds dispositioned the shader-front-end, integer-sampler,
  and uniformity tails. The frozen release contract binds exact 197-test and 1,003-shader
  identity manifests. This closes stale round-11 accounting only; it creates no fresh Linux
  runtime receipt and does not relax the named WebGPU deferrals or the s7 hardware boundary.
- [x] **M3.F7 [driver DECISION → r13]** DECIDED 2026-08-05: multi-pass emulation — one render
  pass per viewport rect (single-layer views exist, 0046), vertex's gpu_ViewportIndex carried
  to fragment as flat varying, per-pass discard of non-matching primitives; GL-identical
  readback. REJECTED: geometry duplication/instance+clip (restructures shaders); leaving it
  deferred (it's in the gate suite). Revisit only if a hot runtime path (not tests) uses
  viewport arrays. IMPLEMENTATION → r13.
- [x] **M3.F8 r12 RESULT (0077-0080, driver-verified spot-runs):** static_shaders **698/973**
  (+179: env/feature buckets 0077 +122, spec-constant codegen 0078 +56); specialization_
  constants_compute PASS (0079 runtime re-specialization); subpass_input CRASH→honest FAIL
  (0080). Nothing regressed (per-family sweep). Residual buckets characterized: SampledBuffer
  93 (needs design), gl_PointCoord 50, shared-vars 61, textureSample 37, textureDimensions 13,
  imageAtomic 6, vertex-rw-SSBO 2 (WebGPU-forbidden → deferral registry).
- [x] **M3.F10 r13 RESULT (0081-0083, driver-verified):** **multi_viewport PASSES faithfully**
  (F7 emulation implemented; driver re-ran it PASS 483ms). static_shaders **786/973** (+87:
  gl_PointCoord 50→0, shared-vars ~59 cleared). VERIFICATION NOTE: 0081-0083 stack on shared
  hunks — reverse-apply verified IN ORDER 0083→0082→0081, tree byte-identical on re-apply
  (individual-reverse of 0081 alone fails, benign; RECORD IN series MANIFEST: 0081<0082<0083).
  Characterized: textureSample-nomatch 37 = integer-sampler filtered `texture()` (workbench
  composite — LAUNCH tier, needs texture→textureLoad transform); textureDimensions 13 =
  map_image dim-inference bug; imageAtomic 6 = WGSL has NO storage-texture atomics → DEFERRAL;
  vbo/ibo bind_as_ssbo = empty stub (wgpu_vertex_buffer.cc:152), same buffer-binding family
  as SampledBuffer.
- [x] **M3.F11-DECISION [driver]** SampledBuffer (93 shaders, curves 44/pointcloud 41/gpencil
  7 — NONE on mesh first-pixels path): **ACCEPT option (a)** storage-buffer-backed fetch
  (samplerBuffer→readonly std430 + texelFetch→index; VertBufs already Vertex|Storage;
  Tint-supported; zero format conversion at launch formats), STAGED — SMALL core (~85) first,
  MEDIUM customdata tail after. REJECTED: 2D-texture repack (8192 limit + per-frame cost).
  Design: notes/gpu-sampledbuffer-design.md.
- [x] **M3.F11 r14 RESULT (0084-0088, driver-verified spot-runs incl. compute vbo/ibo PASS):**
  static_shaders **909/973** (+125): SampledBuffer 93→0, int-sampler 37→0, textureDimensions
  25→0 (1D-array→2D UDIM emulation), IsNan/IsInf 9→0; compute family **15/15**. Zero
  regressions. STACK ORDER for manifest: 0084<0086<0087<0088 (wgpu_shader.cc). Remaining 64:
  26 MEDIUM-tail (samplerBuffer as fn param — curves/pointcloud customdata), 16
  switch-fallthrough (Tint reader rejects; fix = GLSL restructure, off-limits → escalated),
  8 imageAtomic (DEFERRAL), 5 uniform-CF (eevee DoF/shadow), 4 subdiv dialect, 4 vertex-RW
  (DEFERRAL), 1 Metal-census artifact (fullscreen_blit).
- [x] **M3.F12-DECISIONS [driver]:** (1) switch-fallthrough: APPROVED narrow GPU_WEBGPU-guarded
  GLSL restructure of the two families (2D_update_mipmaps 14 + eevee_light_culling 2) — same
  exception class as 0054; shader_tool edits remain forbidden. (2) R32F buffer-texture:
  APPROVED format-generic access via override constants (component count specialized at
  pipeline time — the 0079 mechanism) IF in-bound; else land characterized-error guard and
  list gpu_buffer_texture_test as an M3-gate blacklist candidate with justification.
- [x] **M3.F12 r15 RESULT (2a3f697, 0089-0091, driver-verified): THE GATE MEASUREMENT —
  full GPUWebGPUTest suite 158 tests: 148 PASS / 8 FAIL / 2 CRASH, every non-pass
  characterized, zero undiagnosed defects.** static_shaders **951/973** (customdata 26→0
  via helper inlining 0090; fallthrough 16→0 via approved GLSL variant 0089; bind_as_texture
  wired 0091). Census + registries: notes/gpu-gate-census.md. Mirror drift reconciled to 0.
  Stack orders recorded (0084<0086<0087<0088<0090; 0085<0091).
- [x] **M3.F13-DECISIONS [driver, 2026-08-06]:** (1) uniformity-5 (barrier under
  invocation-id-dependent CF; Tint conservative analysis, no disable lever): APPROVED
  GPU_WEBGPU-guarded GLSL restructure (hoist barrier / workgroupUniformLoad), same exception
  class as 0089 — eevee shadow/DoF are M6 launch tier, deferral would bite later.
  (2) subpass_input×2: DEFER at M3 gate (named blocker: WebGPU has no subpass inputs;
  2-pass emulation designed notes/gpu-laneB) — REVISIT flagged at M6 entry on EEVEE render
  evidence. (3) fullscreen_blit + shader_sampler_argument_buffer_binding: census artifacts
  (Metal-only, CMakeLists.txt:457 WITH_METAL_BACKEND) — excluded from the WebGPU gate with
  cmake evidence, NO code change (gpu/metal off-limits). (4) buffer_texture R32F + subdiv×4:
  BLACKLIST with justifications (R32F = post-launch format-generic work; subdiv = runtime
  OSD injection missing for all backends at this harness profile).
### M4 viewport recon (dfbac20, driver-verified): THE M4-GATE BLOCKER MAP

UI chrome + splash render; **3D viewport interior = BLACK** (no cube/grid/gizmos). Five Dawn
classes drop viewport command buffers at Submit: (1) DOMINANT surface-blit format mismatch —
region RGBA8Unorm vs surface BGRA8Unorm, CopyTextureToTexture needs identical formats;
(2) UBO bound where SSBO expected (missing Storage usage); (3) dense-remap binding COLLISION;
(4) dense-remap GAP (binding 3 absent); (5) vertex UBO 352B vs minBindingSize 16384.
CRASH SIGNATURE: Tab → createBindGroup 'buffer' undefined (js:19731) → render loop halts
silently (no abort propagation). Also: first-composite-needs-an-input-event (ghost-web);
spurious "using OpenGL instead" dialog despite live device; cattrs missing (python);
splash decoder (imbuf). Evidence: platform_web/shell/evidence/viewport-recon-*.

- [x] **M4.T15 viewport-draw umbrella RECONCILED by the accepted successor rounds:** patches
  0098-0100 retain the cross-format region blit, null-resource bind guard, and 16 KiB UBO
  allocation that made the full UI composite upright without the Tab crash. The r18 cube/grid
  darkness was subsequently closed by the kind/depth/layout/dedup, mapped-first load-store,
  index-range, window-origin, and dynamic-stencil fixes in patches 0101-0103, 0106,
  0110/0112/0113, 0115, and 0118. The rejected emitter-only remap skip remains absent. The r27
  evidence is validation-clean with grid/axes, r33 renders the solid cube, and historical D-9
  passes splash/workspace at 0.204%/0.505% over 0.016. This closes stale r18 accounting only;
  **M4-LINUX-REPLAY** still owns the fresh Linux receipt and remains blocked by s7's
  llvmpipe-only adapter.
  - [x] **M4.T16 viewport blockers RECONCILED by the accepted successor rounds:** patches
    0101/0106 enforce buffer-kind correctness and full-range bind deduplication; 0102/0103
    isolate depth sampling and omit Tint-pruned bindings; 0112 gives mapped resources precedence
    over stale identity fallbacks; and 0115 converts the window-backbuffer destination Y origin.
    The r27 proof renders grid/axes with zero validation errors, 0118 restores the solid shaded
    cube, and the later historical D-9 gate passes splash/workspace at 0.204%/0.505% over 0.016.
    This closes only the stale r19 blocker list. **M4-LINUX-REPLAY** remains the sole owner of a
    fresh Linux binding/receipt and is still blocked by s7's llvmpipe-only adapter.
  - [x] **M4.T22 r25 [driver, 2026-08-07]: urllib3-shim merge + gate re-measure — boot-payload
    regression CLOSED, gate 100%→33.4%.** 7c1cda2 cherry-picked (06feea1), shim verified in the
    .data payload, clean boots: NO ModuleNotFoundError, zero Dawn errors, full UI stable; comparator
    FAIL 33.4% = the viewport interior only. NEW measured: sync GPU readback = all-zero in the
    windowed profile (F9-D consequence, r23 "blank" fully explained); wasm table-OOB crash after
    in-app snapshot ops (loop halts — M5 hazard, unfixed); full engine shader set (104) compiles
    CLEAN inline-on-demand (workerless ShaderCompiler under use_main_context_workaround). Shell
    gained a rig-only `?args=` argv hook. notes/gpu-r25-shim-boot-restored-viewport-isolated.md.
  - [x] **M4.T23 r26/r27 RESOLVED (2e74628): bind-collision root cause** — two-pass mapped-first
    bind assembly + loadstore honor + sampler/BGL-visibility strips + index start/base; grid,
    axes, camera, light, selection outline render; first zero-validation-error boot. Patches
    0110/0112/0113; census held twice. notes/gpu-r26-bind-collision-root-cause.md.
  - [x] **M4.T24 r28 RESOLVED except (a)** — (b) interaction regressions fixed: IBO upload
    before draw (0114) + deferred-bind claim-on-emit (0116) restored menus/toolbar/topbar/
    outline/nav-gizmo; (c) resize letterbox/blur + DPR>=2 UI scale fixed (79941b4, 10/10
    verify); (d) full-window parity harness landed (sandbox/m4-fullscreen-parity, baseline
    trend 84.6%→74.5%→60.2% failing); (e) audit passed post-correction. Only (a)'s solid
    pass remains, promoted to T25.
  - [x] **M4.T25 solid-cube hunt RESOLVED r33 (68e2bce, patch 0118)** — root cause: the
    backend never emitted SetStencilReference, so every stencil-tested draw compared against
    reference 0; the workbench prepass (NEQUAL @ 0xFF) rejected every fragment as a VALID
    stencil op — zero errors by design, which is why r29-r32's eliminations (args, pipeline,
    buffers, binds all correct) kept coming back clean. Fix mirrors vk_context dynamic state:
    apply_stencil_reference after SetPipeline in all 4 draw paths. Receipts: gbuffer
    writtenFrac 0.0157 x3, census green unchanged, SOLID SHADED CUBE on screen
    (m4-r33-solid-cube-shot.png). Hunt tooling kept: patch 0117 diag readback.
  - [x] **M4.T26 parity gate CLOSED [D-9, ac03fa6]:** exact 1280x720 DPR1 splash and
    workspace captures pass the unchanged 0.016 / 1% comparator at 0.204% and 0.505%.
    r58 (ce728d7) closes the old toolbar sub-item: 0134's triangle-fan emulation reduced
    the toolbar from 1,022 failing pixels to 2, with one icon-strip pixel and zero seam
    pixels. The remaining bottom-region mass is a mismatched capture state (Timeline active
    outline plus web-only Pan/Options hints), not a rendering patch target; future cleanup
    must align native and web pointer/event state before comparison.
  - [x] **M4.T23 r26 diagnostic queue RECONCILED by the accepted r26/r27 results:** the planned
    draw, texture-identity, compute, and magenta probes all ran and proved that draws submitted and
    the viewport transport reached the canvas. They isolated stale context-wide resources colliding
    with legitimate dense bindings; patches 0110/0112/0113 retain the load-store, mapped-first bind
    assembly, and indexed-subrange repairs after all temporary instrumentation was removed. The r26
    capture shows first viewport geometry, r27 is validation-clean with grid/axes, and the later D-9
    gate passes. The historical makesdna TESTS side-note is separately superseded by the strict M1
    native/Wasm gtest receipt. This closes stale diagnosis text only; **M4-LINUX-REPLAY** still owns
    the fresh Linux receipt and remains blocked by s7's llvmpipe-only adapter.
  - [x] **M4.T27 i18n restoration [r45 Phase 1 + r47 Phase 2, D-10]: LANDED** (c5e465b +
    422b488, driver-verified). Language row restored; splash 17.8% -> 4.54%; workspace
    2.05% -> 1.11%; real Noto CJK ja_JP switch proven (Add menu renders translated) with
    en_US round-trip; stage-0 +2,248 B exactly (languages index), 49 .mo (76.72 MiB raw)
    ride stage-1; patch 0127 applied + series entry. Residual coverage note: registration-
    cached bl_labels need the full-register path (faithful native behavior).
  - [x] **M4.T28 splash-image wedge [gpu, r52/0134]: FIXED** (fd624eb, driver-verified).
    The splash quad reached WebGPU as GPU_PRIM_TRI_FAN, whose unsupported fallback was
    TriangleStrip and omitted the fan's second triangle. Native-faithful indexed fan
    emulation removes the wedge; the final D-9 splash passes at 0.204% over 0.016.
  - [~] **M6.EEVEE-A [gpu-backend, L1]: Phase A C1-C4 LANDED; pixels still blocked.**
    Patch 0136 (159e4a0, driver-verified) strips writable storage-image Vertex visibility,
    opts into adapter-supported TextureFormatsTier1/Tier2, and requests the measured 8/10
    storage limits. The clean Phase A rescore (99a83d2) removes the old C1-C4 flood but
    captures zero EEVEE device-byte results: 20 rows return OK with zero GPU errors but
    do not reach the backend read seam, seven stop on RG11B10Ufloat ReadWrite,
    transmission returns OK and then reports a post-render Image Editor mip-7 alias, and
    two never emit the START marker within 200 seconds. The controlled 2442b90 A/B and
    timestamp receipt proves the transmission alias is display work, not a render blocker
    or the cause of the missing Film hook. Next: Phase A' RG11 substitution, a true
    one-output final-mip variant, and view-aware L-B/L-C readback. Patch 0138 (f075180,
    driver-verified) now supplies exact immutable backend tickets and proves a source-free
    nonzero-layer texture view in bundled Chromium, but the F12 control exits before
    Film::read_pass because the tag-update and default shadow material shaders fail.
    Patch 0143 (e9808d9, driver-verified) now lands the full framebuffer/root subresource
    dependency: flattened source-free mip/layer/aspect ownership, exact attachment/clear/copy
    and typed-blit routing, 3D slices, physical 1D arrays with matching shader lowering, and
    guarded RG11/D32S8 capabilities. All 15 added WebGPU tests pass, actual Dawn optional-RG11
    and depth-route controls pass, and Workbench pixel controls remain native-faithful with zero
    GPU errors. Patch 0211 (`2aab304`) closes a Phase A-prime storage-interface seam: write-only
    RG16Float DoF images retain their native format, while physically promoted read-write
    RG16Float resources now carry RGBA16Float consistently through GLSL, shader-interface, and
    bind-group metadata. The exhaustive native/Wasm contract, canonical replay, full product
    rebuild/no-work, and REUSE are GREEN; this is device-free proof and claims no pixel result.
    Next is the frozen 0144 Phase A-prime rebase and its EEVEE acceptance matrix,
    followed by the public async API and caller continuation. No EEVEE pixel-pass claim until a
    non-black result reaches the pinned comparator.
  - [~] **M6.EEVEE-B [gpu-backend, L2, own lane]:** the virtual-shadow-map SSBO-atomic
    implementation is present but remains pixel-partial. Patch 0210 (`3d093db`) closes a
    device-free READY handoff defect: if the atlas receipt settled after `Instance::init()` had
    synced unbound passes, the image-render state machine now rebuilds them exactly once before
    entering sample rendering. The fail-first/final source contract, shipping Wasm rebuild/no-work,
    canonical clean-pin replay, and REUSE are GREEN. The four shadow-scene goldens still require
    the deferred conformant hardware receipt; no pixel or M6 pass is claimed.
  - [x] **M6.EEVEE-HARDWARE-RECEIPT-GUARD [driver, device-free]:** the physical-F12
    EEVEE producer no longer permits a software/fallback browser to mint an acceptance row.
    Manifest v5 records the shared `hardware-webgpu-adapter-v1` receipt, reading the current
    `GPUAdapterInfo.isFallbackAdapter` location before its legacy fallback and rejecting absent,
    masked, fallback, CPU, SwiftShader, llvmpipe, lavapipe, softpipe, WARP, and other named
    software identities. Matrix result/provenance v2 requires the same accepted identity across
    every row; the final M6 verifier independently recomputes and checks that binding. The
    canonical current/legacy adapter-shape fixtures, 30 generated-driver self-checks, verifier
    mutation fixtures, and Python/JavaScript syntax checks are GREEN. This is receipt-integrity
    work only: no hardware run or EEVEE pixel pass is claimed, and the old v4/v1 matrix cannot
    satisfy current M6.
  - [x] **GPU-fallback dialog re-triage [driver, diagnosis-only]:** the inherited non-Apple
    `UserDef.gpu_backend` default is OpenGL, and `wm_gpu_backend_override_from_userdef()` inserts
    it before the compiled-in WebGPU backend. Detection rejects that compiled-out override, sets
    `G_FLAG_GPU_BACKEND_FALLBACK`, then accepts WebGPU. This is not a pre-device capability race;
    current `WGPUBackend::is_supported()` is unconditional. Patch 0107 only hides the stale bit.
    The faithful selection/default/CLI/RNA repair is browser-rebuild work blocked by
    M4-LINUX-REPLAY. Evidence: `notes/gpu-fallback-retriage-20260820.md` and
    `sandbox/gpu-fallback-retriage/probe_default.cc`.
  - [x] P2 ghost-web blocker #6 "first composite needs an input event": **FALSIFIED by r50**
    (f108934, diagnosis-only, 0/5 attempts used). The initial expose/size/activate events
    have existed since r19/r22 (GHOST_SystemWeb.cc:595 posts kEventWindowSize at
    createWindow); 8 zero-input boots composite the FULL UI unprompted at ~+17s, identical
    to with-input boots. The dead-tab window is the INLINE SHADER COMPILE blocking the WM
    worker (+1.0s to +17.4s, load-sensitive; frame 1 presents the instant it finishes).
    Capture rigs no longer need the mouse-nudge for correctness (keep it for older builds).
  - [~] **M4.T29/M8 boot-latency: shader-compile block [gpu]: persistent + first-boot paths fixed.**
    The OPFS WGSL translation cache cuts retained clean zero-input first-UI timing from
    ~16.3s cold to ~3.0s warm, with exact shaderc v2025.4 plus Tint/Dawn 36cf1fae
    invalidation pins. Patch 0285 adds a deterministic read-only 100-entry first-boot seed,
    guarded by the same key/salt/length/checksum envelope and a bounded fail-closed pack
    parser. On the exact rebuilt CAPTURE product's software-adapter diagnostic, seed-disabled
    first presentation is 22,472 ms versus 5,207 ms bundled (101 hits, zero misses, zero page
    errors), a 17,265 ms reduction. This is not a hardware performance receipt. The 87,696 B
    Brotli seed initially moved the conservative complete-wire projection to ~15,056,447 B.
    The subsequent layout-preserving Stage-0 UI-font bootstrap recovers 314,343 net critical
    bytes after its stronger publisher/control contracts, bringing the projection to ~14,742,104 B.
    The current APPLY product must still be built and measured exactly. Evidence:
    `notes/m8-first-boot-shader-cache-seed-20260826.md` and
    `notes/m8-stage0-ui-font-bootstrap-20260826.md`.
  - P3 python (cattrs) follows separately.

### Migration save point — 2026-08-18 (ornith-lab, WSL2 Linux)

- [x] **M4 durable evidence:** retain the immutable 2026-08-09 D-9 PASS as historical evidence:
  splash 0.204% and workspace 0.505% over 0.016, both below the unchanged 1% threshold. The
  newer `ledger/results/m4.json` RED is also correct: later windowed artifacts no longer match
  that binding. Never overwrite or relabel either result.
- [x] **M4 rig path portability:** `sandbox/m4-d9-gate/capture_m4.mjs` now derives the repository
  root and resolves Playwright from `BW_NODE_MODULES`, `NODE_PATH`, or local `node_modules`.
  The macOS paths `/Users/paws/plushly/game-platform/node_modules` and
  `~/Library/Caches/ms-playwright` are no longer source assumptions.
- [x] **Source preservation:** the ignored `upstream/` integration diff is frozen in the single
  squashed patch named by `patches/canonical` (SHA-256 recorded beside it); `lib/` and every build
  tree are explicitly rebuild-only. See `notes/gpu-r26-migration-savepoint.md` and
  `notes/migration-to-ornith-lab.md`.
- [x] **SOURCE-SERIES-REPLAY [driver]:** exact migration reconstruction is independently GREEN
  on Linux. The final-source freezer regenerated a canonical patch and complete 20,258-entry
  live/replay manifests; the patch is byte-identical to the accepted hash-pinned preview and its
  clean-pin postimage matches all 257 concrete modified/untracked paths. `patches/canonical` now
  makes that squashed authority explicit and the verifier's default path is green. The 125-entry
  numbered list remains non-replayable development history after the mandated retry ceiling
  (`0016`/`0019`, `0016b`/`0022`, then `0027`); exact reconstruction no longer depends on repairing
  those stale historical preimages. See `notes/patch-series-replay-20260820.md`.
- [x] **M4-LINUX-SPLIT-CONTRACT [driver] (a3f4c4b):** the cold rebuild's missing deferred shard
  is root-caused to `BLENDER_WEB_WASM_SPLIT_MODE=OFF`, not an unexplained link failure. A locked
  Emscripten repro proves OFF/CAPTURE output shapes; the new preflight validates OFF, CAPTURE, and
  exact profile-bound APPLY inventories and rejects stale/symlinked/receipt-drifted shards. The
  runbook now reconstructs CAPTURE -> two strict accepted-hardware profiles -> union -> APPLY.
  Focused tests + all split Python self-checks + REUSE are green. Current APPLY preflight exits 5
  because software llvmpipe binds no profile; no shard or receipt was fabricated.
- [x] **M4-CAPTURE-PROFILE-LINUX-PORTABILITY [driver, producer-only] (afbd834):** the strict success/
  terminal-error profile producer derives its checkout, module, binary, and confined immutable
  output roots; requires Node 22.16.0, Playwright 1.61.1, PNGJS 7.0.0, and bundled Chromium
  149.0.7827.55; and selects Linux WebGPU arguments. Before evidence allocation it records and
  requires a non-fallback hardware adapter with unmasked identity. Producer fixtures plus both
  profile-union and APPLY consumers reject llvmpipe/SwiftShader/CPU/software and 28 receipt
  mutations. No profile or receipt was produced: s7 remains blocked. See
  `notes/m4-capture-profile-linux-portability-20260820.md`.
- [x] **M4-FULLSCREEN-LINUX-PORTABILITY [driver, browser-free] (a29dd65):** the active full-window
  parity tripwire now derives its checkout, exact artifact directory, and deduplicated module roots;
  requires Node 22.16.0 plus Playwright 1.61.1; and selects Linux WebGPU arguments without Metal
  ANGLE. Base and live root/descendant self-checks pass with zero browser launches, while Node 25
  and the retired absolute module root fail closed. No capture or receipt was produced: the live
  tripwire remains blocked by s7 and the APPLY product, and its native golden, comparator, threshold,
  and historical artifact are unchanged.
- [x] **M8-SPLIT-RUNTIME-LINUX-PORTABILITY [driver, browser-free] (9c2410f):** the strict APPLY
  runtime proof now derives exact Node 22.16.0/Playwright 1.61.1/PNGJS 7.0.0 roots, pins Chromium
  149.0.7827.55, selects Linux WebGPU arguments, and binds the shared accepted-hardware adapter
  before immutable evidence allocation. Root/descendant fixtures prove 9 positive/15 adversarial
  cases with zero launches; software reaches zero allocations, accepted hardware exactly one, and
  missing APPLY allocates nothing. No browser or receipt was produced; s7 remains live. See
  `notes/m8-split-runtime-linux-portability-20260821.md`.
- [x] **M8-MONOLITHIC-DEPLOY-LINUX-PORTABILITY [driver, browser-free] (75b4902):** the retained
  OFF-mode deployment diagnostic now derives its checkout and exact Playwright root, copies the
  current shell set, emits portable metadata, and confines replacement to `bundle`/`bundle-*`.
  External fake-checkout fixtures pass five root/descendant, copy/symlink, confinement, and
  no-allocation cases; the real OFF product assembles without launching a browser. This is not
  the shipping APPLY/staged path and creates no adapter, profile, product, or M8 receipt. See
  `notes/m8-monolithic-deploy-linux-portability-20260821.md`.
- [x] **STUCK-20260820-S7 [driver, diagnosis-only]:** seven consecutive post-compliance
  iterations changed no harness suite result because the same llvmpipe-only s7 condition blocks
  the complete M0-M3 manifest and every APPLY/browser receipt. Fresh `vulkaninfo` still reports
  exactly one CPU llvmpipe device; current strict producers and consumers already reject it
  before evidence allocation. The resume path is split into external ICD/session recovery,
  accepted-adapter proof, M4 CAPTURE/APPLY/rebind, exact M3 replay, then aggregate/live gates.
  No receipt, profile, result, deferral, or promise changed. See `notes/stuck-2026-08-20.md`.
- [x] **M0-ORACLE-GROUP-RECOVERY [driver, environment-only]:** the account's existing Docker
  enrollment was absent only from the inherited process group list. A preauthorized group-scoped
  subprocess verified the digest-pinned, network-disabled oracle and routed the unchanged harness
  through its committed container shims, restoring M0 to 6/6 GREEN. Full regression retains the
  existing M1-M8 strict-manifest/APPLY/browser/run-label/hardware failures. No source, harness,
  oracle, receipt, result expectation, deferral, or promise changed. See
  `notes/m0-oracle-group-recovery-20260821.md`.
- [ ] **M4-LINUX-REPLAY [driver, first ornith-lab browser task]:** blocked-by the named WSL
  hardware-Vulkan/Chromium adapter condition. Once cleared, install the pinned Playwright 1.61.1
  browser, execute the strict CAPTURE -> APPLY sequence, serve with COOP/COEP under WSLg, capture
  fresh immutable splash/workspace labels at 1280x720 DPR1, bind, run the unchanged comparator,
  then run `harness/run.sh --scope m4`. Do not adapt the old macOS receipt or profile to the new
  binary.
- [~] **M3-LINUX-REPLAY [gpu-backend, before any translation feature work]:** Linux probe
  portability is complete in `68296ec`: Dawn selects Vulkan instead of Metal, both probe
  targets build through `scripts/ninja-locked.sh`, and CPU/unknown adapters fail closed with
  `PROBE_BLOCKED`. Runtime replay remains blocked because ornith-lab exposes only llvmpipe;
  that software result binds no receipt. Once a hardware Vulkan adapter is available, rebuild
  the canonical test target against Dawn `36cf1fae` and require the
  checked-in exact 197/1,003 manifests, 197/197, DrawWebGPU 2/2, cold 1,003 MISS/files, warm
  1,003 HIT, zero uncaptured errors, OpenSubdiv proof, and final Ninja no-work. Any platform
  delta is a new named round, not an automatic rebaseline.
- [x] **M2-FINAL-SELFCHECK [driver]:** the unfinished `484219d` six-ID library-override
  bijection verifier now passes the complete hermetic positive/adversarial suite on Linux:
  runner, compose, aggregate verifier, and strict-final-adapter self-checks. This closes the
  verifier-validation gap only; it does not turn the historical M2 candidate into a fresh
  Linux receipt or change the strict `m2b` RED state.
- [x] **M1-LINUX-PARITY-PREFLIGHT [driver]:** dedicated Release native/Wasm parity trees build
  clean through `scripts/ninja-locked.sh`; exact manifests match and fresh execution is BLI
  1,667/1,667 plus bmesh-core 1/1 on both platforms. Cold-host fixes: hydrate the pinned
  `lib/linux_x64` LFS payload and install/document `libegl-dev`. This is direct tier-(a)
  evidence only, not a strict receipt; see `notes/m1-linux-parity-20260820.md`.
- [x] **M0-M3-NINJA-LOCK [driver] (6719ab3):** every producer, verifier, and hermetic
  self-check Ninja execution in `sandbox/final-m0-m3/` now goes through the canonical
  `scripts/ninja-locked.sh` path. M0 hash-binds the executable wrapper; raw-Ninja receipt
  substitutions fail closed; exact no-work, wrong-root, wrong-target, stale-output, and
  nonzero contracts remain covered. All four documented self-checks and real M1 native/Wasm
  locked dry-runs pass. The absent canonical `build-native-gpu` tree leaves the separate
  M3-LINUX-REPLAY item unchanged.
- [x] **M1-LINUX-STRICT-RECEIPT [driver] (ea7133e):** immutable
  `m1-ornith-linux-20260820-r5` binds the final source freeze and passes BLI 1,667/1,667,
  bmesh-core 1/1, the 9/9 main corpus, and all 12 versioning comparisons (10 passes plus two
  oracle-matching refusals). The independent component verifier rechecks live source,
  artifacts, raw receipts, corpus/versioning evidence, and exact locked-Ninja no-work
  (`20260820T064610`); receipt SHA-256 is
  `b92077470080382c1aaa29c9b8f5c39bfe1b8a791fe59cd5e53ade7bbebaf694`. The aggregate
  `m1` and regression gates remain honestly RED because the strict adapter requires one
  complete fresh M0-M3 candidate manifest, which cannot exist until the named llvmpipe-only
  M3 hardware-Vulkan blocker is cleared; no pass flag, deferral, or promise was promoted.
- [x] **M2-LINUX-STRICT-RECEIPT [driver] (e56ab57):** immutable
  `m2-ornith-linux-20260820-r35` runs all 75 tier-(b) suites against the pinned Linux oracle
  and canonical Wasm runtime: 65 PASS, 7 named DEFERRED, and 3 exact-schema
  PASS_WITH_DEFERRAL. The first independent replay rejected r34 because embedded Wasm Python
  had grown 190 unreceipted `.pyc` files; the producer now removes only generated bytecode and
  requires both composed trees to equal their receipt inventories before sealing. Independent
  replay passes (`20260820T100236`); receipt SHA-256 is
  `1661f59f16dc4f8a331e987b874671404b42031b1da2827cf1c5b34979e9bc7f`. Producer
  (`20260820T095432`), all four final-evidence self-checks
  (`20260820T100542/100545/100256/100309`), M0 self-check (`20260820T100310`), and REUSE
  1,892/1,892 (`20260820T100356`) are green. Required `m2b` and regression runs remain
  honestly RED (`20260820T100436/100444`) because the strict adapter requires one complete
  fresh M0-M3 manifest, still impossible under the named llvmpipe-only M3 hardware-Vulkan
  blocker; no pass flag, deferral, or promise was promoted.
- [x] **M6-CYCLES-LINUX-REPLAY [driver, CPU-only]:** immutable
  `m6-cycles-ornith-linux-20260820-r3` renders all 27 rows and independently live-verifies
  25 PASS / 2 measured SKIP / 0 FAIL / 0 stale / 0 blocked against pinned oiiotool 2.4.17.0.
  The Release product is exact locked no-work; JS/Wasm SHA-256 begin `f1028f32d168` /
  `de05586d625b`. Fresh native-BVH2 controls pass both excluded goldens and exact 0/0
  one-vs-two-thread Wasm comparisons pass, narrowing the blocker to a wasm32/native edge
  divergence rather than Embree, OpenSubdiv, or thread determinism. The runner now creates
  its ignored parent on a clean checkout and the independent verifier has an explicit CPU-only
  mode; its default aggregate gate is unchanged. This does not promote M6 while Workbench/EEVEE,
  APPLY, and the strict M0-M3 manifest remain blocked by s7. See
  `notes/m6-cycles-linux-replay-20260820.md`.
- [x] **M6-CYCLES-ARITHMETIC-ATTRIBUTION [driver, CPU-only]:** full-product SIMD128/SSE4.2
  and strict-scalar-FP A/Bs falsify both suspected causes without moving either comparator:
  default stays max 0.1098 / 20.8% over and emission-alpha stays max 0.6863 / 11.4% over.
  SIMD changes only 1/13 pixels versus scalar; strict reciprocal/signed-zero/contraction-off
  renders are pixel-exact to scalar. Both preview patches were rejected, upstream restored to
  exact hashes, and the receipt-bound JS/Wasm pair restored byte-for-byte with locked no-work.
  No blacklist, threshold, golden, result, or deferral changed. See
  `notes/m6-cycles-arithmetic-attribution-20260820.md`.
- [x] **M6-CYCLES-EDGE-ATTRIBUTION [driver, CPU-only]:** the 30-pair native/Wasm float-pass
  and one-variable reduction matrix overturns the arithmetic attribution. The suite loads the
  old `.blend` before registering its staged Cycles add-on, so the persistent file-version
  handler never runs: Wasm uses Automatic/blue-noise + adaptive/light-tree current defaults
  while native preserves Tabulated Sobol and legacy settings. One-sample Object Index is exact
  and Position stays below 1.6e-5 while Diffuse Direct already differs on 48.6%/80.4% of pixels.
  Calling the exact handler makes both native/Wasm and unchanged pinned-golden comparisons pass
  at 0%/0.0061% over 0.016. Sealed verifier and 30-pair matrix are GREEN
  (`20260820T174027-2271099` / `20260820T173718-2262051`); no product source, blacklist,
  threshold, golden, result, or deferral changed. See
  `notes/m6-cycles-edge-attribution-20260820.md`.
- [x] **M6-CYCLES-LOAD-ORDER-REPAIR [driver, CPU-only]:** the staged Cycles add-on and exact
  version handler now register before each `.blend` open. Receipt schema v3 binds every render,
  comparator, node log, pre-load handler event, file version, and legacy sampling assertion.
  The full pre-removal control is exactly 25 PASS / 2 STALE; after retiring only those two
  Cycles rows, immutable `m6-cycles-ornith-linux-20260820-r5` is 27 PASS / 0 SKIP with stable
  artifacts and an independently replayed live comparator. Nine old inputs prove Tabulated
  Sobol migration; eighteen newer inputs prove the handler event without a false legacy
  expectation. Required M6/regression remain RED on the existing Workbench/current-artifact,
  strict-manifest, split-product, and s7 hardware gates; no aggregate result was promoted. See
  `notes/m6-cycles-load-order-repair-20260820.md`.
- [x] **M6-WORKBENCH-LINUX-PORTABILITY [driver, producer-only]:** the Workbench driver and
  scorer now derive the checkout root, resolve Playwright through the documented local module
  roots, confine output to one safe immutable-run child, and attest the current six-file shell
  set including `diagnostics-bootstrap.js`. Driver, scorer, and aggregate-verifier self-checks
  pass from Linux and from a descendant cwd. No matrix or receipt was produced: the 20-row replay
  remains blocked by s7's hardware-adapter requirement and the resulting APPLY split product.
  See `notes/m6-workbench-linux-portability-20260820.md`.
- [x] **M6-EEVEE-LINUX-PORTABILITY [driver, producer-only]:** the current 30-row browser-matrix
  producer derives its checkout and safe run root from `import.meta.url`, replaces the retained
  one-row driver's macOS root/Playwright/Metal/OIIO/shell seams with exact-count guards, and binds
  the selected module root, Linux browser arguments, and six served shell files into each row.
  Root and descendant-cwd self-checks each pass 30 generated syntax + 30 generated-driver checks
  with zero browser launches. No matrix or receipt was produced: s7 hardware plus APPLY remain the
  gate, and the optional native-prebake route is separate. See
  `notes/m6-eevee-linux-portability-20260820.md`.
- [x] **M5-CLICK-PICK-LINUX-PORTABILITY [driver, producer-only]:** the first strict M5 browser
  producer now derives its checkout and evidence root from its own source, resolves Playwright
  through explicit and repo-local module roots, rejects output outside one repository-local
  immutable child, and has a browser/product-free self-check. Root and descendant-cwd checks pass;
  the live loader resolves Linux Playwright 1.61.1 with zero browser launches. No M5 receipt was
  produced because s7 hardware plus the APPLY split product remain mandatory. See
  `notes/m5-click-pick-linux-portability-20260820.md`.
- [x] **M5-CANVAS-LINUX-PORTABILITY [driver, producer-only]:** the trusted-keyboard canvas-smoke
  producer now derives its checkout and output root, resolves exact Playwright 1.61.1 through
  explicit/platform-delimited/repository-local module roots, rejects evidence path escapes, and
  has 17/17 base plus 18/18 live-loader browser-free self-checks from root and descendant cwd.
  No browser or receipt was produced; s7 hardware plus APPLY remain mandatory. See
  `notes/m5-canvas-linux-portability-20260820.md`.
- [x] **M5-LATENCY-LINUX-PORTABILITY [driver, producer-only] (8bc251b):** the current
  ROI-latency producer now derives checkout/module/evidence paths, requires Node 22.16.0 plus
  Playwright 1.61.1/Sharp 0.35.3/libvips 8.18.3, confines output to one repository-local immutable
  child, and has 15/15 base plus 17/17 live browser-free self-checks from root and descendant CWD.
  Sharp and its host-only Linux closure are recorded in `ledger/deps.json`; the established
  greyscale/resize/MAD detector and budgets are unchanged. No browser or receipt was produced;
  s7 hardware plus APPLY remain mandatory. See `notes/m5-latency-linux-portability-20260820.md`.
- [x] **M7-USD-LINUX-PORTABILITY [driver, producer-only]:** the strict USD browser producer now
  derives its checkout/product/evidence paths, requires Node 22.16.0 plus Playwright 1.61.1,
  accepts an explicit canonical source freeze, and confines immutable output to one repository
  child. Root/descendant self-checks pass 13/13 without dependencies and 14/14 with the live
  loader, all with zero browser launches. The gate entrypoint and bundle/source checker now
  reach the honest missing-current-staged/files/APPLY boundary. No receipt was produced; s7
  hardware remains mandatory. See `notes/m7-usd-linux-portability-20260820.md`.
- [x] **M7-NATIVE-USD-LINUX-PORTABILITY [driver, producer-only]:** the native USD capability
  producer now derives its checkout/build/output paths, requires an explicit source freeze,
  confines immutable output to the repository, and validates all product inputs before evidence
  allocation. Root and descendant self-checks each pass 5 positive / 7 negative cases; missing
  freeze and absent `build-native-gpu` controls allocate nothing. No native USD receipt was
  produced, and M7 remains blocked by the existing staged/files/APPLY and s7 browser boundaries.
  See `notes/m7-native-usd-linux-portability-20260820.md`.
- [x] **M7-FALLBACK-CONTRACT-LINUX-PORTABILITY [driver, selfcheck-only]:** the branded
  Firefox/Safari producer and aggregate contract self-checks now run from the Linux checkout root
  or a descendant CWD without installed browsers, WebDrivers, or `codesign`. Exact Apple
  identifier/team parsing has positive and adversarial fixtures, a missing identity command fails
  closed, and a real Linux production invocation is rejected before evidence allocation. The
  strict two-browser capture remains deliberately macOS-only because only that host can run real
  Safari; no browser or M7 receipt was produced and no signing/schema requirement changed. See
  `notes/m7-fallback-contract-linux-portability-20260820.md`.
- [x] **M7-FILES-LINUX-PORTABILITY [driver, producer-only] (cfc1f5b):** the current trusted-drop/FSA/
  fallback/OPFS browser producer now derives its checkout, bundle, binary, fixture, output, and
  module roots; requires Node 22.16.0 plus Playwright 1.61.1; validates a loopback origin and the
  exact M8-derived bundle identity before launch; and has browser/product-free root and
  descendant-CWD self-checks. No files receipt was produced: s7 hardware plus the APPLY bundle
  remain mandatory. See `notes/m7-files-linux-portability-20260820.md`.
- [x] **M8-BROWSER-IDENTITY-LINUX-PORTABILITY [driver, producer-only]:** the branded Chrome/Edge
  matrix and independent aggregate verifier now bind Linux rows to canonical amd64 PIE ELFs,
  exact package ownership/version/integrity, the vendor APT candidate and archive SHA-256, and
  dedicated source/keyring bytes plus accepted primary fingerprints. Darwin retains its strict
  Apple signature/notarization path. Producer, shared-contract, and independent-verifier
  adversarial self-checks pass without browsers; no matrix receipt was produced because the
  s7-cleared hardware adapter and APPLY split product remain mandatory. See
  `notes/m8-browser-identity-linux-portability-20260820.md`.
- [x] **M8-PRODUCT-BAR-LINUX-PORTABILITY [driver, producer-only]:** the strict 30-second
  skeptic/own-file/share-route producer now derives its checkout and exact Playwright/PNGJS
  roots, requires pinned Node 22.16.0 plus an explicit canonical branded Chrome executable,
  and uses the shared Linux ELF/dpkg/APT/keyring identity without weakening Darwin signing.
  The two exact host-only dependency decisions are recorded in `ledger/deps.json`.
  Root/descendant and live-loader self-checks run with zero browser launches; the shared
  runtime-evidence adversarial check independently rejects the retired macOS roots and identity
  bypass. No product receipt was produced because s7 hardware plus APPLY remain mandatory. See
  `notes/m8-product-bar-linux-portability-20260820.md`.
- [x] **M8-PERFORMANCE-LINUX-PORTABILITY [driver, producer-only]:** the pinned 1.5 MB/s +
  40 ms cold-performance producer now derives its checkout/module/output roots, requires exact
  Node 22.16.0 plus Playwright 1.61.1/PNGJS 7.0.0 and an explicit canonical Chrome executable,
  and selects the shared Darwin/Linux browser identity plus matching stable-release feed. Base
  and live-loader self-checks pass from root and descendant CWD with zero browser launches; the
  shared producer/consumer contract remains green. No performance receipt was produced: a real
  Linux-shaped invocation rejects the absent canonical Chrome package before evidence allocation,
  while s7 still blocks the APPLY product. See
  `notes/m8-performance-linux-portability-20260820.md`. Its soak successor is closed below;
  staged capture follows separately.
- [x] **M8-SOAK-LINUX-PORTABILITY [driver, producer-only]:** the strict current-bundle
  30-minute soak now derives checkout/module/evidence/profile paths, requires Node 22.16.0 plus
  exact Playwright 1.61.1/PNGJS 7.0.0 and an explicit canonical Chrome executable, and selects
  the shared Darwin/Linux identity and stable-release feed without changing any duration,
  cadence, RSS/heap, liveness, pixel, or error bar. Base 14/14 and live root+descendant 15/14
  self-checks pass with zero launches; shared producer/consumer checks are GREEN. The real
  package-absent Linux path rejects before profile/receipt allocation. No soak receipt was
  produced because s7 plus APPLY remain mandatory. See
  `notes/m8-soak-linux-portability-20260820.md`.
- [x] **M8-STAGED-CAPTURE-LINUX-PORTABILITY [driver, producer-only]:** the strict three-process
  staged runtime producer now derives its checkout/module/evidence paths, requires Node 22.16.0
  plus exact Playwright 1.61.1/PNGJS 7.0.0 and an explicit canonical Chrome executable, and
  selects the shared Darwin/Linux browser identity without changing its cold/warm/offline,
  service-worker, PARK..RESUMED, trusted-input, pixel, or receipt contract. Base 10/10 and live
  root+descendant 11/10 self-checks pass with zero launches; shared identity and independent M8
  consumer checks are GREEN. A Linux package-absent invocation rejects before product/evidence
  access. No staged/browser receipt was produced because s7 plus APPLY remain mandatory. See
  `notes/m8-staged-capture-linux-portability-20260820.md`.
- [x] **M8-STAGED-SUPPORT-LINUX-PORTABILITY [driver, browser-free] (6832429):** staged assembly,
  exact-tree server, and two-version update-transition checks derive their checkout from their
  own shell/Python/JavaScript files. Root and descendant-CWD checks pass without an APPLY manifest;
  absent-product and escaped-output controls prove zero reads/writes and confinement. The existing
  transport/update contracts and independent M8 consumer/receipt self-checks remain green. No
  bundle, APPLY artifact, browser/GPU receipt, result promotion, or promise was created. See
  `notes/m8-staged-support-linux-portability-20260820.md`.
- [x] **M8-COMPLIANCE-LINUX-PORTABILITY [compliance, browser-free] (43934f9):** the technical-package producer resolves only exact REUSE 6.2.0 from an explicit, repository-local, or `PATH` executable; binds its path/size/SHA-256; and rejects seven missing/indirect/drifted cases before receipt allocation. All nine technical facts and REUSE 1,931/1,931 are green; M8 drops 43 to 22 failures while four external-policy facts and the existing s7/APPLY boundary remain honest. See `notes/m8-compliance-linux-portability-20260820.md`.
- [x] **AUDIT-20260820 [driver]:** adversarial last-25 review (`334e734..0ea2cd0`) recorded in
  `reports/audit-20260820.md`: 0 critical / 3 major / 1 minor. Strict M1/M2 receipts and all
  four hermetic verifier suites recheck clean. Fixed the cold-runbook host-tool/compiler/native-
  library omission and verified all three native tools plus 49 locale catalogs. No hardware
  receipt, result flag, deferral, or promise changed.
- [x] **M4-LINUX-HOSTTOOL-ORDER [driver]:** the audit's native `shader_tool` rebuild happened
  after its recorded windowed no-work check and invalidated 3,587 generated-code edges. A locked
  rebuild restored `blender_browser` (`20260820T150017`, 76 s), the locked dry-run is exact
  no-work (`20260820T150138`), and OFF-mode product preflight passes. The cold runbook already
  orders host tools before the product; the recurring ordering invariant is now recorded in
  `notes/porting-patterns.md`. This restores a coherent development artifact only and binds no
  M3/M4 hardware profile, receipt, result, or promise.
- [x] **AUDIT-20260820-HARNESS [driver/harness] (2bd738f):** the sanctioned lock-lift is
  complete and the lock is restored. `harness/buildwrap.sh` atomically reserves
  timestamp/PID/suffix log names; a frozen-clock fixture proves 4 sequential, 32 concurrent,
  and 16 forced-same-basename invocations preserve 52/52 unique logs. `GATE_RED` scope joining
  no longer emits trailing whitespace. M0 remains 6/6 GREEN and regression remains honestly
  RED only on the existing M1-M6 receipt/artifact/hardware/run-label gates. The separate final
  human harness-digest ratification item in `notes/harness-issues.md` remains open.
- [x] **AUDIT-20260820-R2 [driver] (deac4ec):** adversarial review of `8bc251b..67c5dc4`
  found 0 critical / 3 major / 0 minor. CAPTURE now requires an explicitly reported
  non-fallback adapter in its producer plus both consumers, and M8 now independently consumes
  the recorded REUSE executable identity. All focused self-checks are green; no receipt or pass
  was promoted. See `reports/audit-20260820-r2.md`.
- [x] **AUDIT-20260820-R2-RUNTIME-ADAPTER [driver/harness] (a41a35a):** all seven audited
  Linux M5-M8 browser producers now require one exact shared hardware-WebGPU adapter record before
  allocating receipt output; the soak also rebinds its persistent context to its pre-allocation
  probe. Independent M7/M8 consumers reject absent, fallback, masked, software, forged, or
  cross-lane-drifted adapters. Contract, mutation, producer, consumer, and live software-rejection
  checks are green; no receipt was created and live acceptance remains **blocked-by s7 hardware
  Vulkan/WebGPU**. See `notes/runtime-adapter-linux-contract-20260820.md`.
- [x] **AUDIT-20260821-R3 [driver]:** adversarial latest-25 review
  (`3d6b7de..01eee70`) found 0 critical / 1 major / 0 minor. The T3 hardware verifier had
  classified a separate preflight adapter and accepted status zero without requiring its exact
  success transcript. It now reclassifies the adapter retained by the real GHOST context and
  requires one adapter line, one backend-specific PASS line, no blocked marker, and exit zero;
  six parser cases, the real postimage build, and llvmpipe rejection are green. All audited
  device-free contracts replay, canonical source remains exact, and REUSE is 1,983/1,983. No
  hardware receipt or result was promoted. See `reports/audit-20260821.md`.
- [x] **AUDIT-20260822-R4 [driver] (a1355a3):** adversarial exact latest-25 review
  (`908449b..fc63056`) found 0 critical / 2 major / 2 minor. Native device creation now requests
  adapter-supported BC compression, feature-gated Unorm16 and D32/S8 creation fails before Dawn
  can return an error texture, and the broken pipeline marker plus stale selector census are
  repaired. The ten-feature/1,024-mask GHOST contract, 448-case native/wasm32 format contract,
  affected integrated contracts, canonical replay, windowed product rebuild/no-work, and REUSE
  are green. M0 remains 6/6; s7 still blocks a fresh hardware receipt. No result, deferral,
  tolerance, golden, blacklist, or promise changed. See `reports/audit-20260822.md`.
- [x] **M3.T9-TEXTURE-CLEAR-LAYOUT [gpu-backend]:** patch 0180 routes the non-renderable
  clear fallback through checked row/sample/data geometry before host allocation or
  `Queue::WriteTexture`. The root/descendant native/wasm32 contract covers six clear layouts
  byte-identically; canonical replay, the windowed rebuild/no-work check, OFF preflight, and REUSE
  are green. Required M3 remains red for the absent strict candidate and s7 still blocks live
  clear proof. See `notes/m3-t9-texture-clear-layout-20260822.md`.
- [x] **M3.T10-FRAMEBUFFER-SUBRESOURCE-READ [gpu-backend]:** patch 0181 makes framebuffer
  readback resolve the attached mip/layer, separates source and requested channel geometry, and
  validates the crop before allocation or caller writes. The pinned native oracle proves two
  array layers, all four requested channel counts, and R/RG default-channel extension; the
  device-free native/wasm32 contract covers crop, Y-flip, truncation, extension, and atomic
  rejection byte-identically. Canonical replay and the real windowed rebuild/no-work check are
  green. Required M3 remains red for the absent strict candidate and s7 still blocks live WebGPU
  readback proof. See `notes/m3-t10-framebuffer-subresource-read-20260822.md`.
- [x] **M3.T10-FRAMEBUFFER-LAYERED-CLEAR [gpu-backend]:** patch 0182 classifies each color
  and depth attachment independently on every one-layer WebGPU clear pass. Exhausting a shorter
  all-layer attachment now omits only that attachment instead of aborting the remaining layers;
  invalid selections still fail closed. The pinned native oracle clears both layers of a
  two-layer attachment beside a one-layer sibling, and the 11-case device-free native/wasm32
  contract is byte-identical. Canonical replay and the real windowed rebuild/no-work check are
  green. Required M3 remains red for the absent strict candidate and s7 still blocks live WebGPU
  clear proof. See `notes/m3-t10-framebuffer-layered-clear-20260822.md`.
- [x] **M3.T10-FRAMEBUFFER-LAYERED-DRAW [gpu-backend]:** patch 0183 derives the emulated
  draw-pass count only from all-layer attachments, requires those counts to agree before any
  encoding, and preserves fixed frontend layer selections across every pass. The 16-case
  device-free native/wasm32 contract covers fixed/all-layer composition and atomic invalid-count
  rejection. Canonical replay and the real windowed rebuild/no-work check are green. Required M3
  remains red for the absent strict candidate and s7 still blocks live layered-draw proof. See
  `notes/m3-t10-framebuffer-layered-draw-20260822.md`.
- [x] **M3.T10-FRAMEBUFFER-LAYERED-LOAD-CLEAR [gpu-backend]:** patch 0184 classifies pending
  explicit clears before draw-pass assembly and materializes only multi-layer all-layer selections
  through the complete layered-clear path. Fixed and single-layer actions retain their one-pass
  behavior. The pinned native oracle covers all-layer scope, and the ten-case device-free
  native/wasm32 contract covers exact classification and invalid boundaries. Canonical replay and
  the real windowed rebuild/no-work check are green. Required M3 remains red for the absent strict
  candidate and s7 still blocks live WebGPU load-clear proof. See
  `notes/m3-t10-framebuffer-layered-load-clear-20260822.md`.
- [x] **M3.T6-STORAGE-UPDATE-PADDING [gpu-backend]:** patch 0185 preserves caller ownership
  when a logical storage-buffer update is not four-byte aligned: aligned transfers keep the
  original pointer, while unaligned transfers copy only logical bytes and zero-fill the padding.
  The ASan repro detects the former over-read; ten native/wasm32 cases cover exact bytes,
  alignment overflow, allocation bounds, and atomic rejection. Canonical replay, the real
  windowed rebuild/no-work check, OFF preflight, and REUSE are green. Required M3 remains red for
  the absent strict candidate and s7 still blocks live WebGPU update proof. See
  `notes/m3-t6-storage-update-padding-20260822.md`.
- [x] **M3.T9-TEXTURE-1D-SRGB-CLEAR [gpu-backend]:** patch 0186 applies the sRGB
  output transfer function to RGB before the raw `Queue::WriteTexture` fallback clears a
  non-renderable 1D sRGB texture; alpha remains linear. The pinned native 1D sampling oracle and
  12-case native/wasm32 byte contract bind the expected semantics and encoded bytes. Canonical
  replay, the real windowed rebuild/no-work check, OFF preflight, and REUSE are green. Required M3
  remains red for the absent strict candidate and s7 still blocks live WebGPU clear proof. See
  `notes/m3-t9-texture-1d-srgb-clear-20260822.md`.
- [x] **M3.T10-INDIRECT-DRAW-RANGES [gpu-backend]:** patch 0187 resolves one atomic byte span
  before pipeline or render-pass work: signed inputs, tightly-packed zero stride, four-byte
  alignment, 16/20-byte command shapes, multiplication overflow, and the indirect allocation are
  all fail-closed. Nineteen native/wasm32 cases are byte-identical, including seven accepted and
  twelve rejected ranges with unchanged rejection output. Canonical replay, the real windowed
  rebuild/no-work check, OFF preflight, and REUSE are green. Required M3 remains red for the absent
  strict candidate and s7 still blocks live WebGPU draw proof. See
  `notes/m3-t10-indirect-draw-ranges-20260822.md`.
- [x] **M3.T8-COMPUTE-DISPATCH-RANGES [gpu-backend]:** patch 0188 validates signed direct
  workgroup counts against the three published backend limits before converting them to WebGPU,
  and proves the complete aligned 12-byte indirect command before pipeline/pass work. Fifteen
  direct and thirteen indirect cases are byte-identical on native and wasm32, including negative,
  zero, exact-limit, over-limit, alignment, exact-fit, undersized, and arithmetic-boundary inputs.
  Canonical replay, the real windowed rebuild/no-work check, OFF preflight, and REUSE are green.
  Required M3 remains red for the absent strict candidate and s7 still blocks live WebGPU compute
  proof. See `notes/m3-t8-compute-dispatch-ranges-20260822.md`.
- [x] **M3.T10-DIRECT-DRAW-RANGES [gpu-backend]:** patch 0189 converts the four signed
  backend draw parameters exactly once before context, geometry, pipeline, or pass work. Negative
  first values and non-positive normalized counts fail atomically; the full positive `int` domain
  reaches fan, indexed, non-indexed, single-pass, and layered draws through one unsigned plan. The
  16-case native/wasm32 contract is byte-identical, canonical replay and reverse application are
  green, and the real windowed product rebuilds then ends locked-Ninja no-work. Required M3 remains
  red for the absent strict candidate and s7 still blocks live WebGPU draw proof. See
  `notes/m3-t10-direct-draw-ranges-20260822.md`.
- [x] **M3.T10-MULTIVIEWPORT-SCISSOR [gpu-backend]:** patch 0190 preserves Blender's signed
  viewport transform while intersecting a separate unsigned scissor with the framebuffer before
  direct or indirect multi-viewport pass work. The 28-case native/wasm32 contract covers negative,
  partial, outside, exact-limit, device-limit, and integer-boundary rectangles atomically.
  Canonical replay and the real windowed rebuild/no-work check are green. Required M3 remains red
  for the absent strict candidate and s7 still blocks live WebGPU draw proof. See
  `notes/m3-t10-multiviewport-scissor-20260822.md`.
- [x] **M3.T9-MIPMAP-ODD-KERNEL [gpu-backend]:** patch 0191 replaces the normalized/float
  render fallback's clamped 2x2 reduction with Blender's pinned separable 1/2/3-tap kernel, so an
  odd source axis retains its final texel. Eleven native/wasm32 axis plans prove exact weights and
  the 5-to-2 ramp; pinned Tint parses the exact WGSL consumed by `WGPUTexture`. Canonical replay,
  the real windowed rebuild/no-work check, OFF preflight, and REUSE are green. Required M3 remains
  red for the absent strict candidate and s7 still blocks live WebGPU sampling proof. See
  `notes/m3-t9-mipmap-odd-kernel-20260822.md`.
- [x] **M3.T10-WINDOW-VIEWPORT-SCISSOR [gpu-backend]:** patch 0192 preserves the signed
  window-backbuffer viewport while converting its bottom-origin Y in widened arithmetic and
  clips an enabled frontend scissor independently. Both rectangles now validate before layered
  clears or render-pass allocation. The 32-case native/wasm32 contract covers partial, outside,
  device-limit, disabled-scissor, oversized-scissor, null, and integer-boundary inputs atomically.
  Canonical replay, the real windowed rebuild/no-work check, OFF preflight, and REUSE are green.
  Required M3 remains red for the absent strict candidate and s7 still blocks live window proof.
  See `notes/m3-t10-window-viewport-scissor-20260822.md`.
- [x] **M3.T10-OFFSCREEN-VIEWPORT-SCISSOR [gpu-backend]:** patch 0193 applies Blender's
  stored viewport and optional independent scissor to ordinary offscreen render passes in the
  lower-left coordinates fixed by a pinned native pixel oracle. Audit patch 0201 composes that
  oracle with WebGPU's top-origin placement/readback contract and corrects both rectangles with
  `H-y-height`; the revised 21-case native/wasm32
  contract covers oracle, partial, outside, disabled-scissor, device-limit, null, and integer-edge
  state atomically. Canonical replay, patch reversal/forward application, the real windowed
  rebuild/no-work check, and OFF preflight are green. Required M3 remains red for the absent
  strict candidate and s7 still blocks live WebGPU draw proof. This task does not claim clear
  semantics. See `notes/m3-t10-offscreen-viewport-scissor-20260822.md`.
- [x] **M3.T10-FRAMEBUFFER-SCISSORED-CLEAR [gpu-backend]:** patch 0194 preserves the native
  lower-left scissor footprint with typed color/depth/stencil fullscreen draws over
  `loadOp=Load`, while disabled and exact-full scissors retain whole-attachment
  `loadOp=Clear`. Empty intersections are no-ops, window Y conversion is widened, all-layer
  selections reuse the guarded pass selector, and explicit load-action materialization stays
  unconditionally full attachment. The native oracle, fail-first 18-case native/wasm32 policy
  contract, exact four-shader Tint parse, canonical replay, product rebuild/no-work check, and
  OFF preflight are green. Required M3 remains red for the absent strict candidate; s7 still
  blocks live WebGPU pixel proof. Audit patches 0201/0202 correct offscreen Y and make pipeline
  cache publication retry-safe. See `notes/m3-t10-framebuffer-scissored-clear-20260822.md`.
- [x] **M3.T6-BUFFER-READ-OFFSET-ALIGNMENT [gpu-backend] (d186fef):** patch 0195 routes
  `Buffer::read()` through the existing checked `CopyBufferToBuffer` span validator after size
  alignment, rejecting a contained but misaligned source offset before native encoding or browser
  ticket work. The fail-first source guard, nine-case copy-range matrix inside 13 byte-identical
  native/wasm32 contracts, canonical replay/reverse check, real windowed rebuild/no-work check,
  OFF preflight, and REUSE are green. Required M3 remains red for the absent strict candidate and
  s7 still blocks live hardware readback proof. See
  `notes/m3-t6-buffer-read-offset-alignment-20260822.md`.
- [x] **M3.T6-VERTEX-UPLOAD-PADDING [gpu-backend] (526305a):** patch 0196 routes initial VBO
  uploads through the owned aligned-payload helper and checks the transfer before deleting static
  host data or clearing dirty state. The fail-first guard plus nine-case native/wasm32 matrix cover
  logical sizes one through eight, all preserved bytes, all zero-filled transfer tails, aligned
  pointer retention, and atomic rejection. Canonical replay/reverse check, the real windowed
  rebuild/no-work check, OFF preflight, and REUSE are green. Required M3 remains red for the absent
  strict candidate and s7 still blocks live hardware upload proof. See
  `notes/m3-t6-vertex-upload-padding-20260822.md`.
- [x] **M3.T6-INDEX-UPLOAD-COMMIT [gpu-backend] (7b3a59b):** patch 0197 publishes a common
  WebGPU buffer handle only after mapped initialization succeeds and transfers initial index-data
  ownership only after that transaction commits. The fail-first extracted shipping-method
  contract plus six-case native/wasm32 matrix prove failed creation retains an invalid destination,
  host bytes, and uncommitted state before a successful retry. Canonical replay/reverse check, the
  real windowed rebuild/no-work check, OFF preflight, and REUSE are green. Required M3 remains red
  for the absent strict candidate and s7 still blocks live hardware upload proof. See
  `notes/m3-t6-index-upload-commit-20260822.md`.
- [x] **M3.T6-BUFFER-STAGING-MAP [gpu-backend] (c63ec78):** patch 0198 checks the
  mapped-at-creation staging range before a large buffer update copies, unmaps, encodes, or
  submits. The fail-first source guard plus nine-case exact extracted state machine cover invalid
  inputs, direct-write threshold, allocation failure, map failure with zero later work, and
  successful exact-byte staging on native/wasm32. Canonical replay/reverse check, the real
  windowed rebuild/no-work check, OFF preflight, and REUSE are green. Required M3 remains red for
  the absent strict candidate and s7 still blocks live hardware upload proof. See
  `notes/m3-t6-buffer-staging-map-20260822.md`.
- [x] **M3.T9-DEPTH-UPLOAD-MAPPED-RANGES [gpu-backend] (af2caa0):** patch 0199 routes both
  mapped-at-creation values/parameter writes in the depth-texture render upload through one
  fail-closed helper. The fail-first source guard plus four-case native/wasm32 contract prove null
  and empty inputs, missing mapped range with zero copy/unmap work, and exact successful bytes.
  Canonical replay/reverse check, real windowed rebuild/no-work check, OFF preflight, and REUSE are
  green. Required M3 remains red for the absent strict candidate and s7 still blocks live hardware
  upload/pixel proof. See `notes/m3-t9-depth-upload-mapped-ranges-20260822.md`.
- [x] **M3.T10-MULTIVIEWPORT-UNIFORM-ALLOCATION [gpu-backend] (f699b30):** patch 0200 makes
  the shared 16-byte `{layer, viewport}` buffer creation atomic and guards both direct and indirect
  multi-viewport paths before state flush, queue, pass, or draw work. The fail-first source guard
  plus two-case native/wasm32 transaction contract prove exact descriptor fields, unchanged output
  on allocation failure, and successful publication byte-identically. Canonical replay, patch
  reversal, the real windowed rebuild/no-work check, OFF preflight, and REUSE are green. Required
  M3 remains red for the absent strict candidate and s7 still blocks live hardware draw proof. See
  `notes/m3-t10-multiview-uniform-allocation-20260822.md`.
- [x] **AUDIT-20260822-R5 [driver] (cde8ed8):** adversarially reviewed exact range
  `783b42d^..19c62fd` (25 commits): 0 critical, 1 major, 2 minor. Patches 0201/0202 fix the
  offscreen bottom/top-origin composition and retry-poisoned scissored-clear caches; canonical,
  native/wasm32, real product, OFF preflight, REUSE, scoped, and container-backed regression
  evidence is recorded in `reports/audit-20260822-r5.md`. The remaining valid-empty/load-action
  minor is queued immediately below; no hardware receipt or gate promotion occurred.
- [x] **M3.T10-EMPTY-RASTER-LOADOP [gpu-backend] (4dd5f75):** patch 0203 separates
  negative/device-invalid raster state from legal zero or fully clipped viewports/scissors. Empty
  state now preserves a zero viewport or contained `(0,0,0,0)` scissor, allowing ordinary and
  multi-viewport passes to
  consume pending attachment load clears without producing fragments. The fail-first planner,
  28/32/21-case native/wasm32 boundaries, checksum-bound bind-loadstore/draw/framebuffer-read GPU
  regression, targeted wasm32 test-TU compile, canonical replay/reverse, real product rebuild and
  no-work check, OFF preflight, REUSE, scoped M3, and container-backed regression are verified.
  Live GPU-test pixel proof remains s7-blocked. See
  `notes/m3-t10-empty-raster-loadop-20260822.md`.
- [x] **M3.T10-CACHE-PUBLICATION [gpu-backend] (01a4627):** patch 0204 keeps null sampler
  and render-pipeline candidates out of the context-local and process-wide caches, preserving a
  later retry after transient creation failure. The unchanged source fails before evidence;
  native/wasm32 fail-first/retry behavior is byte-identical, and exact source guards bind all
  five live publication sites. Canonical replay/reverse, the real product rebuild/no-work check,
  OFF preflight, REUSE, scoped M3, and container-backed regression are verified. Live retry and
  pixel proof remain s7-blocked. See `notes/m3-t10-cache-publication-20260822.md`.
- [x] **M3.T8-COMPUTE-CACHE-PUBLICATION [gpu-backend] (268b2b5):** patch 0205 keeps a null
  specialization-keyed compute pipeline out of the per-shader variant sequence, preserving a
  later retry after transient creation failure. The unchanged source fails before evidence; the
  native/wasm32 fail-first contract is byte-identical and exact source guards bind the shipping
  miss path. Canonical replay/reverse, the real product rebuild/no-work check, OFF preflight,
  REUSE, scoped M3, and container-backed regression are verified. Live retry/dispatch proof
  remains s7-blocked. See `notes/m3-t8-compute-cache-publication-20260822.md`.
- [x] **M3.T10-COLOR-BLIT-RESOURCE-GUARDS [gpu-backend] (6a27d5d):** patch 0206 rejects failed
  lazy shader-module, 16-byte uniform-buffer, and bind-group creation before the cross-format
  color-blit fallback reaches pipeline, queue, encoder, or pass work. The unchanged source fails
  before evidence; the shared two-case allocation transaction is byte-identical on native/wasm32,
  and exact source-order guards bind all three shipping failure boundaries. Canonical replay,
  patch reversal, the real product rebuild/no-work check, OFF preflight, REUSE, scoped M3, and
  container-backed regression are verified. Live draw/pixel proof remains s7-blocked. See
  `notes/m3-t10-color-blit-resource-guards-20260822.md`.
- [x] **M3.T9-MIPMAP-RESOURCE-TRANSACTION [gpu-backend] (8eb6231):** patch 0207 rejects failed
  shader-module, command-encoder, texture-view, bind-group, render-pass, and finished-command-
  buffer creation before dependent mipmap work or queue submission. The unchanged source fails
  before evidence; the exact shipping method's nine cases stop all eight injected failures before
  submit and pass byte-identically on native/wasm32 within 24 integrated texture contracts.
  Canonical replay/reverse, the real product rebuild/no-work check, OFF preflight, scoped M3, and
  container-backed regression are verified. Live mipmap/pixel proof remains blocked by no
  conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). See
  `notes/m3-t9-mipmap-resource-transaction-20260822.md`.
- [x] **M3.T6/T9-READBACK-COMMAND-TRANSACTION [gpu-backend] (9b7a566):** patch 0208 routes
  both asynchronous readback copies through one checked encoder/finish/submit transaction. Null
  encoder or finished-command-buffer handles now settle the reserved ticket as
  `CommandEncodingFailed`, release all staging/source pins, and stop before mapping or submission.
  The fail-first source guard, three-case native/wasm32 transaction, canonical replay/reverse,
  real product rebuild/no-work check, OFF preflight, REUSE, scoped M3, and container-backed
  regression are verified. Live readback/pixel proof remains blocked by no conformant hardware
  Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). See
  `notes/m3-t6-t9-readback-command-transaction-20260822.md`.
- [x] **M3.T8-COMPUTE-COMMAND-TRANSACTION [gpu-backend] (76227cc):** patch 0209 routes direct
  and indirect compute dispatch through one checked encoder/pass/finish/submit transaction. The
  fail-first source guard and four-case native/wasm32 contract prove every failed handle stops
  before dependent work or submission. Canonical replay/reverse, the real product rebuild/no-work
  check, OFF preflight, REUSE, scoped M3, and container-backed regression are verified. Live
  compute dispatch and pixel proof remain blocked by no conformant hardware Vulkan ICD in WSL2
  (NVIDIA ships none; Mesa dzn rejected by Dawn). See
  `notes/m3-t8-compute-command-transaction-20260822.md`.
- [x] **M3.T10-INDEXED-FAN-RESOURCE-TRANSACTION [gpu-backend] (d2c2c16):** patch 0212 rejects
  a failed shader module before indexed-fan pipeline creation and routes expansion through the
  checked encoder/pass/finish/submit transaction. The fail-first source guard plus existing
  four-case native/wasm32 command contract prove failure stops before dependent work or submission.
  Canonical replay/reverse, real product rebuild/no-work, OFF preflight, and REUSE are green.
  Required M3 remains red for the absent strict candidate, and live fan draw/pixel proof remains
  blocked by no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by
  Dawn). See `notes/m3-t10-indexed-fan-resource-transaction-20260823.md`.
- [x] **M3.T10-IMMEDIATE-COMMAND-GUARDS [gpu-backend] (2f05b4d):** patch 0213 rejects a
  failed immediate-draw command encoder before render-pass creation and a failed finished command
  buffer before queue submission. The unchanged source fails the exact guard-order contract before
  evidence allocation; final root/descendant native+wasm32 contracts remain byte-identical and bind
  the shipping immediate method through the canonical source digest. Canonical replay/reverse, the
  real product rebuild/no-work check, OFF preflight, REUSE, scoped M3, and container-backed
  regression are verified. Live immediate draw/pixel proof remains blocked by no conformant
  hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). See
  `notes/m3-t10-immediate-command-guards-20260823.md`.
- [x] **M3.T10-BATCH-COMMAND-TRANSACTION [gpu-backend] (036e976):** patch 0214 rejects failed
  command encoders before pass creation and failed finished command buffers before submission in
  all four direct/indirect ordinary/multi-viewport batch paths. The unchanged source fails first;
  exact source ordering, native/wasm32 parity, canonical replay/reverse, the real product rebuild
  and no-work check, OFF preflight, REUSE, scoped M3, and container-backed regression are verified.
  Live draw/pixel proof remains blocked by no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships
  none; Mesa dzn rejected by Dawn). See
  `notes/m3-t10-batch-command-transaction-20260823.md`.
- [x] **M3.T6-BUFFER-COMMAND-TRANSACTION [gpu-backend] (0760734):** patch 0215 routes staged
  buffer uploads and native synchronous readback copies through the checked encoder/finish/submit
  helper. The unchanged source fails first; the three-case native/wasm32 contract proves encoder
  and finished-command-buffer failures stop before dependent work or submission. Canonical
  replay/reverse, the real product rebuild/no-work check, OFF preflight, REUSE, scoped M3, and
  container-backed regression are verified. Live buffer/pixel proof remains blocked by no
  conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). See
  `notes/m3-t6-buffer-command-transaction-20260823.md`.
- [x] **M3.T6-STORAGE-COMMAND-TRANSACTION [gpu-backend] (c6dec91):** patch 0216 routes
  vertex-to-storage copies through the checked encoder/finish/submit helper after exact range
  validation. The unchanged source fails first; the shared three-case native/wasm32 contract and
  exact shipping-method guard prove encoder and finished-command-buffer failures stop before copy
  or submission. Canonical replay/reverse, the real product rebuild/no-work check, OFF preflight,
  REUSE, scoped M3, and container-backed regression are verified. Live copy/pixel proof remains
  blocked by no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by
  Dawn). See `notes/m3-t6-storage-command-transaction-20260823.md`.
- [x] **M3.T10-CONTEXT-RENDER-COMMAND-TRANSACTION [gpu-backend] (d8d331c):** patch 0217
  routes color/depth blits and depth uploads through the checked encoder/pass/finish/submit
  transaction and propagates failure to each boolean caller. The unchanged source fails first;
  the four-case native/wasm32 contract plus exact three-method guards prove every failed handle
  stops before dependent work or submission. Canonical replay/reverse, the real product
  rebuild/no-work check, OFF preflight, REUSE, scoped M3, and container-backed regression are
  verified. Live draw/pixel proof remains blocked by no conformant hardware Vulkan ICD in WSL2
  (NVIDIA ships none; Mesa dzn rejected by Dawn). See
  `notes/m3-t10-context-render-command-transaction-20260823.md`.
- [x] **M3.T10-FRAMEBUFFER-SCISSORED-COMMAND-TRANSACTION [gpu-backend] (3a0af60):** patch
  0218 routes both typed scissored framebuffer clear paths through the checked
  encoder/pass/finish/submit transaction and returns its result. The unchanged source fails first;
  the shared four-case native/wasm32 transaction plus exact two-method guards prove every failed
  handle stops before dependent clear work or submission. Canonical replay/reverse, the real
  product rebuild/no-work check, OFF preflight, REUSE, scoped M3, and container-backed regression
  are verified. Live clear/pixel proof remains blocked by no conformant hardware Vulkan ICD in
  WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). See
  `notes/m3-t10-framebuffer-scissored-command-transaction-20260823.md`.
- [x] **M3.T10-FRAMEBUFFER-FULL-CLEAR-COMMAND-TRANSACTION [gpu-backend] (b922d87):** patch
  0219 routes multi-attachment and dedicated single-color full clears through the checked
  encoder/pass/finish/submit transaction. The unchanged source fails first; the shared four-case
  native/wasm32 transaction plus exact two-method guards prove failed handles stop before
  dependent pass work or submission. Canonical replay/reverse, the real product rebuild/no-work
  check, OFF preflight, REUSE, scoped M3, and container-backed regression are verified. Live
  clear/pixel proof remains blocked by no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships
  none; Mesa dzn rejected by Dawn). See
  `notes/m3-t10-framebuffer-full-clear-command-transaction-20260823.md`.
- [x] **M3.T10-FRAMEBUFFER-COPY-COMMAND-TRANSACTION [gpu-backend] (5b98d6c):** patch 0220
  routes the stencil-buffer bridge and raw framebuffer texture copy through the checked encoder/
  finish/submit transaction. The unchanged source fails first; the shared three-case native/
  wasm32 contract plus exact method-body guards prove encoder failure stops before all three copy
  operations and finished-command-buffer failure stops before submission. Canonical replay/
  reverse, the real product rebuild/no-work check, OFF preflight, REUSE, scoped M3, and container-
  backed regression are verified. Live copy/pixel proof remains blocked by no conformant hardware
  Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). See
  `notes/m3-t10-framebuffer-copy-command-transaction-20260823.md`.
- [x] **M3.T9-TEXTURE-RENDER-CLEAR-TRANSACTION [gpu-backend] (e4f860d):** patch 0221
  preserves one-command-buffer layered depth/stencil and renderable-color clears while rejecting
  failed encoder, per-layer view/pass, and finished-command-buffer handles before partial
  submission. The callback-abort transaction is device-free proven on native/wasm32 and both
  shipping branches are source-bound. Canonical replay/reverse, real product rebuild/no-work,
  OFF preflight, REUSE, scoped M3, and container-backed regression are verified. Live pixel proof
  remains blocked by the named s7 hardware-adapter condition. See
  `notes/m3-t9-texture-render-clear-transaction-20260823.md`.
- [x] **M3.T9-TEXTURE-READBACK-COMMAND-TRANSACTION [gpu-backend] (f134090):** patch 0222
  routes native synchronous texture readback through the checked encoder/finish/submit helper and
  returns before staging-map work on command failure. The unchanged source rejects first;
  root/descendant native+wasm32 contracts, wrong-Node control, canonical replay/reverse, real
  product rebuild/no-work, OFF preflight, REUSE, scoped M3, and container-backed regression are
  verified. Live copy/map/pixel proof remains blocked by the named s7 hardware-adapter condition.
  See `notes/m3-t9-texture-readback-command-transaction-20260823.md`.
- [x] **M3.T9-TEXTURE-COPY-COMMAND-TRANSACTION [gpu-backend] (ef53318):** patch 0223 keeps
  the complete per-mip compatibility/skip loop inside one checked encoder/finish/submit transaction.
  The unchanged source fails first; root/descendant native+wasm32 contracts, wrong-Node control,
  canonical replay, numbered apply/reverse, real product rebuild/no-work, OFF preflight, REUSE,
  scoped M3, and container-backed regression are verified. Live copy/pixel proof remains blocked
  by the named s7 hardware-adapter condition. See
  `notes/m3-t9-texture-copy-command-transaction-20260823.md`.
- [x] **M3.T8/T10-BIND-GROUP-RESOURCE-TRANSACTION [gpu-backend] (259a2e5):** patch 0224
  publishes transient bind groups only after non-null creation and rejects failure before compute,
  ordinary/multi-viewport direct/indirect batch, or immediate pass work. Compute retains a distinct
  valid empty-resource state. The fail-first source guard, two-case native/wasm32 transaction, all
  six shipping creation sites and both compute callers, canonical replay, numbered apply/reverse,
  real product rebuild/no-work, OFF preflight, REUSE, scoped M3, and container-backed regression
  are verified. Live dispatch/draw/pixel proof remains blocked by the named s7 hardware-adapter
  condition. See `notes/m3-t8-t10-bind-group-resource-transaction-20260823.md`.
- [x] **M3.T10-FRAMEBUFFER-LOAD-PASS-PUBLICATION [gpu-backend] (121d696):** patch 0225
  publishes `begin_load_pass()` only after `BeginRenderPass()` returns a non-null handle, before
  ordinary viewport or scissor state is applied. The fail-first source contract, root/descendant
  native+wasm32 parity, wrong-Node control, canonical replay, numbered apply/reverse, real product
  rebuild/no-work, OFF preflight, REUSE, scoped M3, and container-backed regression are verified.
  Live pass/draw/pixel proof remains blocked by the named s7 hardware-adapter condition. See
  `notes/m3-t10-framebuffer-load-pass-publication-20260823.md`.
- [x] **M3.T10-VERTEX-BUFFER-RESOURCE-TRANSACTION [gpu-backend] (9d8c391):** patch 0226
  resolves every pipeline-planned real or dummy vertex-buffer handle before direct batch,
  indirect batch, or immediate draw command encoding, rejecting the whole ordered plan on any
  missing resource. The fail-first source guard, three-case native/wasm32 transaction,
  root/descendant parity, wrong-Node control, canonical replay, numbered forward/reverse checks,
  real product rebuild/no-work, OFF preflight, REUSE, scoped M3, and container-backed regression
  are verified. Live draw/pixel proof remains blocked by the named s7 hardware-adapter condition.
  See `notes/m3-t10-vertex-buffer-resource-transaction-20260823.md`.
- [x] **M3.T10-INDEX-BUFFER-RESOURCE-TRANSACTION [gpu-backend] (fb38385):** patch 0227
  resolves the required index-buffer handle before direct batch, indirect batch, or immediate
  pipeline/command work. Failed indexed uploads reject rather than silently changing direct or
  indirect draw semantics, and all triangle-fan paths bind the resolved transient handle. The
  fail-first source guard, three-case native/wasm32 transaction, root/descendant parity,
  wrong-Node control, canonical replay, numbered forward/reverse checks, real product
  rebuild/no-work, OFF preflight, REUSE, scoped M3, and container-backed regression are verified.
  Live draw/pixel proof remains blocked by the named s7 hardware-adapter condition. See
  `notes/m3-t10-index-buffer-resource-transaction-20260823.md`.
- [x] **M3.T7-SHADER-LAYOUT-RESOURCE-TRANSACTION [gpu-backend] (8bb9908):** patch 0228
  separates intentional semantic auto-layout fallback from null bind-group-layout or
  pipeline-layout resource failures, and publishes the two handles only as one valid pair. The
  fail-first source guard, three-case native/wasm32 transaction, root/descendant parity,
  wrong-Node control, self-check, canonical replay, numbered forward/reverse checks, real product
  rebuild/no-work, OFF preflight, scoped M3, and container-backed regression are verified. Live
  layout/pipeline/draw proof remains blocked by the named s7 hardware-adapter condition. See
  `notes/m3-t7-shader-layout-resource-transaction-20260823.md`.
- [x] **M3.T10-FRAMEBUFFER-LAYERED-LOAD-COMMIT [gpu-backend] (1ba3e94):** patch 0229
  propagates full-clear command success and consumes a pending all-layer load clear only after
  every selected layer reaches the queue. Failed view, encoder, pass, or command-buffer creation
  retains the action for retry. The fail-first source guard, two-case native/wasm32 transaction,
  wrong-Node zero-evidence control, canonical replay, numbered reverse/forward cycles, real
  product rebuild/no-work, OFF preflight, scoped M3, and container-backed regression are
  verified. Live clear/draw/pixel proof remains blocked by the named s7 hardware-adapter
  condition. See `notes/m3-t10-framebuffer-layered-load-commit-20260823.md`.
- [x] **S7-WSL2-HARDWARE-DEFERRAL [driver] (b28ddf0):** six exact M3-M8 rows now record
  `no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)` in
  `ledger/deferred.json`. M1/M2 remain receipt-backed, M6 Cycles-CPU remains 27/27 GREEN, and the
  M8 size/latency blocker remains independently active. The fail-first/final contract, unique JSON
  registry, REUSE, M3 scope, and container-backed regression are verified; M0 is 6/6 GREEN while
  M1-M8 remain honestly RED. No software adapter, receipt, result flag, tolerance, golden,
  blacklist, or promise changed. See `notes/s7-wsl2-hardware-blocker-20260822.md`.
- [x] **P0-M4-WM-WORKER-PRESENTATION-PREINIT [ghost-web] (645e2da):** the pre-main
  wrapper now resolves `#canvas` from the intercepted Emscripten `cmd:2` transfer payload before
  the inner handler publishes `GL.offscreenCanvases`, validates the persistent backbuffer before
  configuring the surface, and binds the post-js source into the browser target's incremental
  link dependencies. The real-order pinned test fails on the predecessor and passes all 11 cases;
  a locked relink followed by the headed windowed software diagnostic reaches `WM_main` with one
  device and one presentation pre-acquisition and zero stage-1/import failures. That diagnostic is
  explicitly non-receipt evidence and does not promote M4 pixels or alter the s7 hardware blocker.
  See `notes/m4-wm-worker-presentation-preinit-20260825.md`.
- [x] **P0-M4-WM-WORKER-EARLY-CANVAS-REGISTRATION [ghost-web] (1fc5986):** the provisional
  direct payload lookup now uses Emscripten's own `PThread.receiveOffscreenCanvases(d)` before
  preflight, after which the original `cmd:2` handler repeats registration idempotently. The
  20-case worker model requires registration before surface lookup and rejects its removal; exact
  commit replay, native/wasm32 present transactions, locked product relink/no-work, OFF preflight,
  and sustained headed fallback diagnostics are green with zero stage-1/import/destroyed-texture
  failures. The live run remains diagnostic-nonreceipt and the s7 hardware blocker is unchanged.
  See `notes/m4-wm-worker-early-canvas-registration-20260825.md`.
- [x] **P0-B-S7-GPUADAPTERINFO-FALLBACK [driver] (30fa865):** the CAPTURE producer now
  prefers the current `GPUAdapterInfo.isFallbackAdapter` boolean and retains the retired
  `GPUAdapter.isFallbackAdapter` location only as a compatibility fallback. Its executable
  fixtures cover current, legacy, precedence, true-fallback, absent, masked, and software shapes;
  both immutable receipt consumers and the complete two-phase source contract remain green. No
  adapter or receipt was produced, and the exact s7 blocker is unchanged. See
  `notes/s7-adapter-info-fallback-20260825.md`.
- [x] **P0-B-M8-RUNTIME-GPUADAPTERINFO-FALLBACK [driver] (fe9ef91):** the shared M5–M8
  runtime-evidence probe now prefers the current `GPUAdapterInfo.isFallbackAdapter` boolean while
  retaining the legacy adapter property only as a compatibility fallback. Executable fixtures
  drive current, legacy, conflicting-precedence, true-fallback, and software raw shapes through
  the actual page callback; the normalized receipt and consumers remain strictly fail-closed. No
  adapter or receipt was produced, and the exact s7 blocker is unchanged. See
  `notes/m8-runtime-adapter-info-fallback-20260825.md`.
- [x] **P0-B-M4-PREINIT-ADAPTER-SHAPE-CONTRACT [driver] (b41258d):** the shipping WM-worker
  preinit model now executes current, legacy, both conflicting-precedence, and unknown fallback
  shapes through the real source. Three source mutations reject legacy-only extraction,
  legacy-first precedence, and unknown-as-fallback behavior; the CAPTURE and shared M5–M8 producer
  self-checks keep the other acceptance-critical adapter callbacks covered. No adapter or receipt
  was produced, and the exact s7 blocker is unchanged. See
  `notes/m4-preinit-adapter-info-shapes-20260825.md`.
- [x] **M4.T21-GHOST-PRESENT-RESOURCE-TRANSACTION [ghost-web] (844e683):** the browser
  compositor preserves the last usable resize texture until replacement succeeds, publishes its
  bind-group layout/pipeline only as a complete pair, and rejects failed per-frame views, bind
  group, encoder, pass, or finished command buffer before dependent work or submission. The
  first-pixels marker and keepalive counter now advance only after submit. A 14-case fail-first
  native/wasm32 contract, descendant replay, wrong-Node zero-evidence control, real product
  rebuild/no-work, OFF preflight, REUSE, scoped M4, and container-backed regression are verified.
  Live present/pixel proof remains blocked by the named s7 hardware-adapter condition. See
  `notes/m4-t21-ghost-present-resource-transaction-20260823.md`.
- [x] **M4-GHOST-WINDOW-PUBLICATION [ghost-web] (472d9b1):** web-window validity now follows
  the exact drawing-context initialization result, and only a valid candidate reaches callback
  registration, the active-window slot, manager insertion, or the initial event queue. Invalid
  candidates are destroyed and returned as null. A five-case fail-first native/wasm32 contract,
  descendant replay, wrong-Node zero-evidence control, real product rebuild/no-work, OFF
  preflight, REUSE, scoped M4, and container-backed regression are verified. Live browser proof
  remains blocked by the named s7 hardware-adapter condition. See
  `notes/m4-ghost-window-publication-20260823.md`.
- [x] **AUDIT-20260823-R6 [driver] (c7050ce):** adversarially reviewed exact latest-25 range
  `ba828d6^..e4ad1d4` with an independent subagent and a pinned-Dawn runtime control. The audit
  found five open semantic defects, while canonical replay, integrated native/wasm32 builds,
  provenance, protected-path ownership, and the hardware/non-receipt boundary remain clean. See
  `reports/audit-20260823-r6.md`.
- [x] **AUDIT-R6-GHOST-ERROR-OBJECT-CONTRACT [ghost-web] (ce5eb31):** backbuffer and present-pipeline
  candidates now publish only after validation/OOM/internal scopes complete cleanly; present
  encoding is scope-validated before submission, and a second submit scope precedes first-pixel
  and keepalive commits. The fail-first contract, root/descendant native+wasm32 parity, pinned-Dawn
  non-receipt error-object control, real product rebuild/no-work, OFF preflight, scoped M4, and
  container-backed regression are verified. Live pixels remain blocked by the named s7 hardware
  condition. See `notes/m4-ghost-error-object-contract-20260823.md`.
- [x] **AUDIT-R6-GPU-COMMAND-ERROR-OBJECT-CONTRACT [gpu-backend] (d5029d5):** every short-lived
  backend command submission and direct queue write now runs through completed
  validation/OOM/internal scopes and one ordered frame-epoch scheduler. Encoding/submission error
  objects never reach a later submit or commit and later same-epoch queue work is canceled.
  Caller-owned upload retry state and bounded failure draining were not part of this slice and are
  reopened by R7 below. Native/wasm32 parity, the pinned-Dawn llvmpipe non-receipt control, product
  rebuild/no-work, OFF preflight, canonical replay, and reverse application are verified. This
  closes the command/queue half only; live hardware proof remains blocked by s7. See
  `notes/m3-gpu-command-error-object-contract-20260823.md`.
- [x] **AUDIT-R6-GPU-SAMPLER-ERROR-OBJECT-CONTRACT [gpu-backend] (3d67aa6):** sampler cache misses
  now remain pending until completed validation/OOM/internal scopes accept them. Duplicate pending
  misses are suppressed, non-null error objects remain unpublished, rejected keys retry cleanly,
  and accepted cached handles remain stable. Native/wasm32 parity, the exact pinned-Dawn llvmpipe
  non-receipt control, canonical freeze, product rebuild/no-work, OFF preflight, REUSE, scoped M3,
  and container-backed regression are verified. This closes the sampler slice only; live hardware
  proof remains blocked by s7. See `notes/m3-gpu-sampler-error-object-contract-20260823.md`.
- [x] **AUDIT-R6-GPU-DUMMY-BUFFER-ERROR-OBJECT-CONTRACT [gpu-backend] (d8cd71d):** the shared
  default-attribute buffer is initialized through `mappedAtCreation` inside its creation scope and
  remains pending until validation/OOM/internal scopes accept it. Rejected non-null candidates
  stay out of draw binding and retry cleanly. Native/wasm32 parity, the exact pinned-Dawn llvmpipe
  non-receipt control, canonical freeze, isolated numbered round trip, product rebuild/no-work,
  OFF preflight, REUSE, scoped M3, and container-backed regression are verified. Live hardware
  proof remains blocked by s7. See
  `notes/m3-gpu-dummy-buffer-error-object-contract-20260823.md`.
- [x] **AUDIT-R6-GPU-PERSISTENT-BUFFER-ERROR-OBJECT-CONTRACT [gpu-backend] (b3a0abb):** persistent
  index, vertex, uniform, storage, texel-expansion, and push-constant buffers now publish one
  composite handle/metadata allocation only after validation/OOM/internal scopes accept it.
  Pending calls deduplicate, rejected non-null candidates retry, and initial index bytes remain
  owned until accepted publication. R7 found that SSBO/UBO updates arriving during that pending
  interval are not retained; the narrower handle-publication proof remains valid. Native/wasm32
  parity, the exact pinned-Dawn llvmpipe
  non-receipt control, canonical freeze, isolated numbered application, product rebuild/no-work,
  OFF preflight, REUSE, scoped M3, and container-backed regression are verified. Live hardware
  proof remains blocked by s7. See
  `notes/m3-gpu-persistent-buffer-error-object-contract-20260823.md`.
- [x] **AUDIT-R6-GPU-TRANSIENT-BUFFER-ERROR-OBJECT-CONTRACT [gpu-backend] (d7b7db1):** all five
  short-lived batch/immediate buffer allocations now reserve an ordered frame-epoch gate before
  creation. Literal nulls and completed validation/OOM/internal error objects cancel dependent
  queue work, while a clean next epoch recreates and retries; callback state owns the provisional
  candidate without retaining a stack wrapper. Native/wasm32 parity, both callback orders, the
  pinned-Dawn llvmpipe non-receipt control, canonical freeze, numbered round trip, real product
  rebuild/no-work, OFF preflight, REUSE, scoped M3, and container-backed regression are verified.
  Live hardware proof remains blocked by s7. See
  `notes/m3-gpu-transient-buffer-error-object-contract-20260823.md`.
- [x] **AUDIT-R6-GPU-TEXTURE-VIEW-ERROR-OBJECT-CONTRACT [gpu-backend] (8443017):** root
  textures and standalone views now reserve an ordered validation gate before creation, while
  views created during scoped command encoding stay inside that enclosing scope. Rejected root
  status invalidates every copied subresource range, and the backend-private empty-framebuffer
  texture/view pair publishes atomically without replacing an accepted old pair while pending.
  Native/wasm32 parity, the exact pinned-Dawn llvmpipe non-receipt control, canonical freeze,
  isolated numbered round trip, real product rebuild/no-work, OFF preflight, REUSE, scoped M3,
  and container-backed regression are verified. Live hardware proof remains blocked by s7. See
  `notes/m3-gpu-texture-view-error-object-contract-20260823.md`.
- [x] **AUDIT-R6-GPU-BIND-GROUP-LAYOUT-ERROR-OBJECT-CONTRACT [gpu-backend] (424c9f2):**
  transient bind groups created before command transactions now reserve ordered validation gates,
  while command-local groups remain covered by their enclosing command scopes. A shader's
  explicit bind-group-layout/pipeline-layout pair publishes atomically after completed scopes;
  covered-layout requirement stays distinct from readiness so pending or rejected pairs block
  auto-layout fallback and retry from retained CPU entries. Native/wasm32 parity, pinned-Dawn
  llvmpipe non-receipt controls, canonical freeze, numbered round trip, real product
  rebuild/no-work, OFF preflight, REUSE, scoped M3, and container-backed regression are verified.
  Live hardware proof remains blocked by s7. See
  `notes/m3-gpu-bind-group-layout-error-object-contract-20260823.md`.
- [x] **AUDIT-R6-GPU-RESOURCE-ERROR-OBJECT-CONTRACT [gpu-backend] (46a1eb0):** every remaining
  shader-module and render/compute-pipeline factory now publishes through completed
  validation/OOM/internal scopes. Final WGSL, explicit layouts, and specialization keys remain CPU
  retry state; required shader modules publish atomically, persistent caches deduplicate pending
  keys and preserve accepted entries, and the one-shot mipmap pair reserves the ordered transient
  gate before command work. Native/wasm32 parity, real non-null pinned-Dawn llvmpipe rejection and
  clean retries, canonical freeze/replay, numbered patch round trip, product rebuild/no-work, OFF
  preflight, REUSE, scoped M3, and container-backed regression are verified. This closes the R6
  GPU resource error-object prerequisite only; live hardware proof remains blocked by s7. See
  `notes/m3-gpu-shader-pipeline-error-object-contract-20260823.md`.
- [x] **AUDIT-R6-BIND-GROUP-COMPLETENESS [gpu-backend] (fd04ebb):** shader finalization's exact
  surviving group-0 binding set is now compared with the unique live-resource entry IDs before
  compute, direct/indirect batch, multi-viewport, or immediate command work. Genuinely empty,
  complete, duplicate, required-but-empty, partial, and extra sets pass/fail exactly; injected
  push-constant and multi-viewport uniforms participate in the same census. Native/wasm32 parity,
  source-order binding, isolated patch round trip, clean-pin canonical replay, real product
  build/no-work, CAPTURE preflight, REUSE, M3 scope, and container-backed regression are verified.
  R7 separately reopens compute bind-group error-scope placement. Live hardware proof remains
  blocked by s7. See
  `notes/m3-gpu-bind-group-completeness-20260823.md`.
- [x] **AUDIT-R6-FRAMEBUFFER-LOAD-COMMIT [gpu-backend] (4a1821b):** ordinary color/depth
  `CLEAR` actions are now per-command reservations that commit only after every later attachment,
  bind-group, command-buffer, and submission boundary succeeds. Late-view and late-bind failures
  release the reservation for retry, same-epoch commands observe `LOAD`, and generation matching
  isolates newer frontend binds from stale callbacks. Native/wasm32 parity, exact shipping-source
  order guards, isolated patch round trip, canonical freeze/replay, real product rebuild/no-work,
  OFF preflight, REUSE, M3 scope, and container-backed regression are verified. R7 separately
  reopens the nested all-layer materialization order. Live hardware proof remains blocked by s7. See
  `notes/m3-gpu-framebuffer-load-action-transaction-20260823.md`.
- [x] **AUDIT-R6-GHOST-RESIZE-COHERENCE [ghost-web] (a52f311):** requested canvas extents now
  remain separate from the last complete configured surface/backbuffer state. Only a validated
  current candidate configures and publishes every size-bound field; rejected and superseded
  candidates preserve the old coherent state, exact extent matching gates present, and the next
  frame retries without another browser resize event. Native/wasm32 parity, a real pinned-Dawn
  non-null texture error-object control, product rebuild/no-work, OFF preflight, canonical replay,
  REUSE, scoped M4, and Docker-backed regression are verified. Live pixels remain blocked by s7.
  See `notes/m4-ghost-resize-coherence-20260823.md`.
- [x] **AUDIT-R6-GHOST-SURFACE-PUBLICATION [ghost-web] (0b8c500):** the pre-main WM worker
  validates the transferred canvas, surface configuration, acquired surface texture, and initial
  persistent backbuffer before synchronous GHOST setup. Presentable contexts import only the
  complete bundle; every partial stage fails child initialization and is destroyed before window
  publication, while offscreen contexts select an explicit device-only mode. Native/wasm32 status
  parity, a seven-case pinned-Node worker transaction, canonical replay, real product
  rebuild/no-work, OFF preflight, REUSE, scoped M4, and container-backed regression are verified.
  Live pixels remain blocked by s7. See `notes/m4-ghost-surface-publication-20260823.md`.
- [x] **AUDIT-R6-GHOST-SURFACE-FAILURE-PROPAGATION [ghost-web] (33dfe08):** per-frame
  surface acquisition now requires an optimal/suboptimal status plus a live texture, maps timeout,
  outdated/error, lost, and suboptimal results to exact retry/reconfigure/recreate actions, and
  propagates an unscheduled present as `GHOST_kFailure` while keeping device-only swaps explicit.
  Fail-first source binding, native/wasm32 status parity, wrong-Node control, standalone context,
  canonical replay, real product rebuild/no-work, OFF preflight, REUSE, scoped M4, and
  container-backed regression are verified. Live pixels remain blocked by s7. See
  `notes/m4-ghost-surface-failure-propagation-20260823.md`.
- [x] **AUDIT-R6-GHOST-DEVICE-LOSS-PROPAGATION [ghost-web] (2e2f560):** the pre-main worker
  publishes a generation-bound browser-native loss signal before its imported device, and stale
  promises cannot poison replacement generations. Imported and fallback contexts share a
  monotonic terminal state; the fallback device-lost callback retains no context pointer, while a
  later public-boundary terminal propagation disables outstanding callbacks, clears every GPU
  handle/pending transaction, and blocks subsequent initialization, swap, surface, and present
  work. R7 separately reopens raw adapter/device request callbacks and the pre-propagation in-flight
  window. Native/wasm32 parity, an 11-case pinned-Node promise matrix, real pinned-Dawn
  loss/error-texture software control, canonical replay,
  standalone/product builds, no-work, OFF preflight, REUSE, scoped M4, and container-backed
  regression are verified without treating software Dawn as a receipt. Live pixels remain
  blocked by s7. See `notes/m4-ghost-device-loss-propagation-20260823.md`.
- [x] **AUDIT-20260823-R7 [driver] (618c0ac):** adversarially reviewed exact range
  `f9ae49a^..c5c341c` with an independent subagent. The audit found three critical and four major
  product-correctness/lifetime defects while canonical replay, native/wasm32 controls, the real
  product no-work build, compliance, protected-path ownership, and hardware/non-receipt boundaries
  remain clean. See `reports/audit-20260823-r7.md`.
- [x] **AUDIT-R7-GPU-PENDING-BUFFER-PAYLOAD [gpu-backend, blocked-by: none] COMPLETE (d999280,
  patch 0240):** SSBO/UBO updates, clears, and attached data now transfer into an ordered owned
  queue while persistent allocation validation is pending; rejection retains retry state and an
  accepted publication replays each payload exactly once without a second frontend call. R8
  separately reopens FIFO reservation when two callers enter replay concurrently. Extracted
  frontend native/wasm32 parity, sentinel ordering, non-null pinned-Dawn rejection/retry, canonical
  replay, real product rebuild/no-work, OFF preflight, and compliance are verified. See
  `notes/m3-gpu-pending-buffer-payload-20260823.md`.
- [x] **AUDIT-R7-GPU-LAYERED-CLEAR-ORDER [gpu-backend, blocked-by: none] COMPLETE (b8ce1e7,
  patch 0241):** every materialized all-layer load clear now reserves ahead of its dependent draw,
  and one idempotent completion group commits the shared load-action generation only after all
  clears and the draw validate. Real-FIFO clean/failure/cancellation/generation-isolation traces,
  native/wasm32 parity, exact shipping-source binds, canonical replay, real product rebuild/no-work,
  OFF preflight, and compliance are verified. See
  `notes/m3-gpu-layered-clear-order-20260823.md`.
- [x] **AUDIT-R7-GPU-UPLOAD-COMMIT [gpu-backend, blocked-by: none] COMPLETE (c9cddfa,
  patch 0242):** direct and staged buffer uploads now publish explicit pending/accepted/rejected
  transaction state, while the buffer owns exact retry bytes and VBO/UBO frontends preserve dirty
  or attached data until implementation-scope acceptance. R8 separately reopens newer VBO
  mutations during a pending transaction and the staging buffer's resource-scope placement.
  Native/wasm32 rejection/retry parity, source-bound frontend cleanup order, non-null pinned-Dawn
  rejection, canonical replay, real product rebuild/no-work, OFF preflight, and compliance are
  verified. See
  `notes/m3-gpu-upload-commit-20260823.md`.
- [x] **AUDIT-R7-GPU-COMPUTE-BIND-SCOPE [gpu-backend, blocked-by: none] COMPLETE (88003fd,
  patch 0243):** direct and indirect compute bind groups now reserve one ordered transient resource
  gate and create under completed implementation scopes before their dependent command can submit.
  Native/wasm32 parity covers non-null error-object rejection, zero uncaptured errors,
  same-epoch cancellation, and clean retry; pinned-Dawn software control, canonical replay, real
  product rebuild/no-work, OFF preflight, compliance, scoped M3, and regression are verified. See
  `notes/m3-gpu-compute-bind-scope-20260823.md`.
- [x] **AUDIT-R7-GHOST-ACQUISITION-LIFETIME [ghost-web, blocked-by: none] COMPLETE (8822ef2):**
  spontaneous fallback adapter/device request completions now capture one shared owner-lifetime
  gate instead of the raw GHOST context, and every acquisition delivery enters that gate. R8
  separately reopens admission ordering once destruction has begun. Delayed native-ASan/wasm32
  delivery performs zero owner access, initialization completion, or follow-on request after
  completed invalidation; the unsafe raw-owner control is caught by ASan. Source binding,
  standalone/product builds, OFF preflight, canonical replay, compliance, scoped M4, and
  container-backed regression are verified. See
  `notes/m4-ghost-acquisition-lifetime-20260823.md`.
- [x] **AUDIT-R7-GHOST-LOSS-INFLIGHT-CANCEL [ghost-web, blocked-by: none] COMPLETE (22a5514):**
  pending fallback resize, pipeline, submission, and present completions now consult the shared
  terminal device state before Configure, handle publication, queue Submit, or `note_present()`.
  R8 separately reopens owner cleanup concurrency and failed initialization settlement when a lost
  callback returns before any public boundary. Fail-first source binding, active/lost
  native/wasm32 parity, standalone/product builds, OFF preflight, canonical replay, compliance,
  scoped M4, and container-backed regression are verified. See
  `notes/m4-ghost-loss-inflight-cancel-20260823.md`.
- [x] **AUDIT-R7-GPU-SCHEDULER-FAILURE-DRAIN [gpu-backend, blocked-by: none] COMPLETE (a15900d,
  patch 0244):** synchronous operation completion and same-epoch cancellation now share one
  iterative drain owner, while exact queued-epoch references prune failures once neither current
  nor reachable. Native/wasm32 parity cancels 100,000 followers with bounded stack use, retains at
  most one of 100,000 sequential failed epochs, and accepts a clean retry. Canonical replay, the
  real product rebuild/no-work, OFF preflight, compliance, scoped M3, and container-backed
  regression are verified. The R7 device-free corrective queue is complete. See
  `notes/m3-gpu-scheduler-failure-drain-20260823.md`.
- [x] **AUDIT-R8-GHOST-CALLBACK-LIFECYCLE [ghost-web, blocked-by: none] COMPLETE (938ade4):**
  all seven asynchronous context completions now register with one synchronized owner gate, and
  completed invalidation rejects delayed delivery without deadlocking a self-destroying callback.
  R8 separately reopens the interval after destruction begins but before invalidation closes
  admission. Their shared device state samples the exact imported JavaScript loss generation at
  callback time and makes settled/replaced signals sticky terminal. Fail-first source binding,
  byte-identical native/wasm32 concurrency and loss contracts, unsafe ASan control, canonical
  integrated parity, real product rebuild/no-work, and compliance are verified. See
  `notes/m4-ghost-callback-lifecycle-r8-20260823.md`.
- [x] **AUDIT-R8-GHOST-CALLBACK-SERIALIZATION [ghost-web, blocked-by: none] COMPLETE (5652eff):**
  arbitrary-thread `AllowSpontaneous` completions now hold one reentrant serialized owner slot for
  their complete callback, preventing callback-vs-callback mutation while preserving nested
  delivery, self-destruction, and non-waiting loss cancellation. R8 separately reopens
  callback-vs-public-owner/device-cleanup execution. Fail-first and final native/wasm32 concurrency
  contracts, unsafe ASan control, canonical integrated parity, real product rebuild/no-work, OFF
  preflight, canonical replay, and compliance are verified. See
  `notes/m4-ghost-callback-serialization-r8-20260823.md`.
- [x] **AUDIT-20260823-R8 [driver] (1973e70):** adversarially reviewed exact range
  `4122d60^..9505bfb` with an independent subagent. The audit found two critical, four major, and
  two minor correctness/lifetime/evidence defects while canonical replay, native/wasm32 controls,
  the real product no-work build, compliance, protected-path ownership, and hardware/non-receipt
  boundaries remain clean. See `reports/audit-20260823-r8.md`.
- [x] **AUDIT-R8-GHOST-OWNER-EXECUTION-LIFECYCLE [ghost-web, blocked-by: none] COMPLETE
  (9e91146 + fixup 9a51b86):** all seven spontaneous callbacks, nine out-of-line owner boundaries,
  and eight inline accessors now share one reentrant execution slot. Terminal cleanup enters it;
  destruction closes admission before waiting. Native/wasm32 barriers prove callback-vs-owner serialization,
  cleanup quiescence, blocked late nested/queued delivery, and safe nested/self-destruction behavior
  while retaining the unsafe ASan control. Integrated parity, standalone/product builds, OFF
  preflight, canonical replay, compliance, scoped M4, and container-backed regression are verified.
  See `notes/m4-ghost-owner-execution-lifecycle-r8-20260824.md`.
- [x] **AUDIT-R8-GPU-UPLOAD-GENERATION [gpu-backend, blocked-by: none] COMPLETE (393e33c):**
  ordinary VBO and float buffer-texture uploads now consume the exact dirty snapshot when its
  payload is retained, so acceptance cannot clear/free a newer stock-frontend mutation. Extracted
  A-schedule/B-mutate/A-accept native/wasm32 contracts prove five ordered payloads and final B
  publication. Product, canonical replay, compliance, scoped M3, and regression are verified. See
  `notes/m3-gpu-upload-generation-r8-20260824.md`.
- [x] **AUDIT-R8-GPU-PAYLOAD-REPLAY-FIFO [gpu-backend, blocked-by: none] COMPLETE (703de76,
  patch 0246):** one generation-stamped replay drainer now reserves retained buffer payloads in
  deque order and absorbs a concurrently retained tail. A forced E1/E2/E3 barrier rejects the
  predecessor in native/wasm32, while final byte-identical runs require FIFO scheduler order and E3
  final overlapping bytes. Patch round trip, canonical replay, product rebuild/no-work, OFF
  preflight, compliance, scoped M3, and container-backed regression are verified. See
  `notes/m3-gpu-payload-replay-fifo-r8-20260824.md`.
- [x] **AUDIT-R8-GHOST-LOSS-INIT-SETTLEMENT [ghost-web, blocked-by: none] COMPLETE (8d7565d):**
  fallback device loss now marks callback-owned terminal state before one shared-gate owner
  delivery; serialized cleanup clears every pending flag/handle and settles initialization once
  with failure. Native-ASan/wasm32 backbuffer/configuration, duplicate-loss, and late-completion
  contracts, exact indexed compilation, integrated parity, standalone/product builds, canonical
  replay, OFF preflight, compliance, scoped M4, and container-backed regression are verified. See
  `notes/m4-ghost-loss-init-settlement-r8-20260824.md`.
- [x] **AUDIT-R8-GHOST-READY-CALLBACK-LIFETIME [ghost-web, blocked-by: none] COMPLETE (56f7057):**
  `completeInitialization()` moves and clears `on_ready_` before invoking the detached callable as
  its final owner action. A production-shaped self-destroying callback passes native-ASan/wasm32,
  while the retained in-place member control is ASan-rejected. Focused/integrated parity, the real
  product rebuild/no-work check, OFF preflight, canonical replay, compliance, scoped M4, and
  container-backed regression are verified. See
  `notes/m4-ghost-ready-callback-lifetime-r8-20260824.md`.
- [x] **AUDIT-R8-GPU-STAGING-RESOURCE-SCOPE [gpu-backend, blocked-by: none] COMPLETE (412e10b,
  patch 0247):** large-upload staging creation now reserves a validation/OOM/internal resource gate
  before its dependent command ticket. Extracted native/wasm32 contracts reject a non-null error
  object with zero uncaptured errors, cancel same-epoch submission, retain exact bytes, and accept a
  clean-epoch retry. Pinned Dawn remains explicit llvmpipe software non-receipt evidence. Product,
  canonical replay, OFF preflight, scoped M3, and container-backed regression are verified. See
  `notes/m3-gpu-staging-resource-scope-r8-20260824.md`.
- [x] **AUDIT-R8-GHOST-CALLBACK-SOURCE-GATE [ghost-web, blocked-by: none] COMPLETE (c36e225):**
  an explicit lexer/balanced-structure manifest now binds all eight shipping asynchronous callback
  roles by method, callee, argument, capture, owner gate, and callback-time device state. Three
  in-memory mutations reject the retired gate's dead-text/alias false positive, implicit capture,
  and an added callback. A production-shaped eight-role matrix covers live delivery, fallback loss,
  and post-loss/destruction rejection with byte-identical native/wasm32 behavior while retaining
  both unsafe ASan controls. See `notes/m4-ghost-callback-source-gate-r8-20260824.md`.
- [x] **AUDIT-R8-GHOST-INHERITANCE-DOC [ghost-web, blocked-by: none] COMPLETE (0ca3bc3):** the
  public header now documents its actual `GHOST_Context` inheritance, synchronous pre-main import,
  standalone callback path, and shared owner-lifecycle gate. The R8 source-compliance check binds
  those claims to the subclass declaration and rejects both retired lifecycle descriptions.
  Focused/integrated native/wasm32 parity, real product rebuild/no-work, OFF preflight, canonical
  replay, compliance, scoped M4, and container-backed regression are verified. See
  `notes/m4-ghost-inheritance-documentation-r8-20260824.md`.
- [x] **M8-SCULPT-PAINT-REGISTRATION-CUT [driver, blocked-by: none] COMPLETE (26e8166,
  patch 0248):** the windowed profile omits only non-launch sculpt/paint operator, macro, and
  keymap roots while native/headless registration and shared data/RNA/helpers remain intact. The
  real locked product drops 2,825,954 raw and 489,232 pinned Brotli-q11 bytes; focused mutation
  controls, native/headless preservation builds, canonical replay, REUSE, scoped M8, and
  container-backed regression are verified. M8 remains RED: the 24,236,667-byte Wasm alone still
  exceeds the complete 15 MB interactive budget before stage-0 data, and hardware/APPLY receipts
  remain s7-blocked. See `notes/m8-sculpt-paint-registration-cut-20260824.md`.
- [x] **M8-GREASE-PENCIL-REGISTRATION-CUT [driver, blocked-by: none] COMPLETE (patch 0249):**
  the windowed profile omits only five non-launch legacy-annotation/Grease-Pencil editing
  registration roots while native/headless registration and data/RNA/file/drawing paths remain.
  The real locked product drops 1,965,548 raw and 336,480 pinned Brotli-q11 bytes; focused
  fail-first/mutation/round-trip controls, native/headless preservation builds, canonical replay,
  REUSE, scoped M8, and container-backed regression are verified. M8 remains RED: the
  23,900,187-byte Wasm alone still exceeds the complete 15 MB interactive budget before stage-0
  data, and hardware/APPLY receipts remain s7-blocked. See
  `notes/m8-grease-pencil-registration-cut-20260824.md`.
- [x] **M8-COMPOSITOR-REGISTRATION-CUT [driver, blocked-by: none] COMPLETE (patch 0250):** the
  windowed profile omits only the generated concrete compositor-node registration root while its
  tree type, DNA/RNA, generic `.blend` loading, and native/headless registration remain. The real
  locked product drops 1,544,869 raw and 236,893 pinned Brotli-q11 bytes; focused fail-first and
  mutation/round-trip controls, native/headless preservation builds, canonical replay, REUSE,
  scoped M8, and container-backed regression are verified. M8 remains RED: the 23,663,294-byte
  Wasm alone is 8,663,294 bytes over the complete 15 MB budget before stage-0 data, and
  hardware/APPLY receipts remain s7-blocked. See
  `notes/m8-compositor-registration-cut-20260824.md`.
- [x] **M8-VSE-REGISTRATION-CUT [driver, blocked-by: none] COMPLETE (patch 0251):** the windowed
  profile omits only the VSE space-type and macro registration roots while strip DNA/RNA, core
  sequencer data, generic `.blend` loading, and native/headless registration remain. The real
  locked product drops 330,595 raw and 74,433 pinned Brotli-q11 bytes; focused fail-first and
  mutation/round-trip controls, native/headless preservation builds, canonical replay, REUSE,
  scoped M8, and container-backed regression are verified. M8 remains RED: the 23,588,861-byte
  Wasm alone is 8,588,861 bytes over the complete 15 MB budget before stage-0 data, and
  hardware/APPLY receipts remain s7-blocked. See
  `notes/m8-vse-registration-cut-20260824.md`.
- [x] **M8-SPREADSHEET-REGISTRATION-CUT [driver, blocked-by: none] COMPLETE (patch 0252):** the
  windowed profile omits only the Spreadsheet space registration root while preserving its
  DNA/RNA, generic `.blend` loading, geometry-node data paths, and native/headless registration.
  The real locked product drops 279,672 raw and 39,919 pinned Brotli-q11 bytes; focused
  fail-first/mutation/round-trip controls, native/headless preservation builds, canonical replay,
  REUSE, scoped M8, and container-backed regression are verified. M8 remains RED: the
  23,548,942-byte Wasm alone is 8,548,942 bytes over the complete 15 MB budget before stage-0
  data, and hardware/APPLY receipts remain s7-blocked. See
  `notes/m8-spreadsheet-registration-cut-20260824.md`.
- [x] **M8-CLIP-REGISTRATION-CUT [driver, blocked-by: none] COMPLETE (patch 0253):** the windowed
  profile omits only the non-launch Clip/Motion Tracking space-type and macro registration roots
  while MovieClip DNA/RNA, generic `.blend` loading, shared image/movie paths, and native/headless
  registration remain. The real locked product drops 128,010 raw and 33,048 pinned Brotli-q11
  bytes; focused fail-first/mutation/round-trip controls, preservation builds, canonical replay,
  REUSE, scoped M8, and container-backed regression are verified. M8 remains RED: the
  23,515,894-byte Wasm alone is 8,515,894 bytes over the complete 15 MB budget before stage-0
  data, and hardware/APPLY receipts remain s7-blocked. See
  `notes/m8-clip-registration-cut-20260824.md`.
- [x] **M8-NLA-REGISTRATION-CUT [driver, blocked-by: none] COMPLETE (patch 0254):** the windowed
  profile omits only the non-launch NLA space-type and macro registration roots while NLA
  DNA/RNA, generic `.blend` loading, core animation, and native/headless registration remain. The
  real locked product drops 60,283 raw and 31,745 pinned Brotli-q11 bytes; focused
  fail-first/mutation/round-trip controls, preservation builds, canonical replay, REUSE, scoped
  M8, and container-backed regression are verified. M8 remains RED: the 23,484,149-byte Wasm
  alone is 8,484,149 bytes over the complete 15 MB budget before stage-0 data, and
  hardware/APPLY receipts remain s7-blocked. See `notes/m8-nla-registration-cut-20260824.md`.
- [x] **M8-SCRIPT-REGISTRATION-CUT [driver, blocked-by: none] REJECTED:** the exact
  deprecated-`SPACE_SCRIPT` candidate preserved the Text Editor, Python Console/runtime, blend
  compatibility, and native/headless behavior, and removed 1,691 raw Wasm bytes, but increased
  the pinned Brotli-q11 release payload by 19,232 bytes. The candidate was fully removed and the
  patch-0254 product restored byte-for-byte; no option, patch, feature cut, or deferral ships.
  See `notes/m8-script-registration-cut-rejected-20260824.md`.
- [x] **M8-PHYSICS-REGISTRATION-CUT [driver, blocked-by: none] COMPLETE (patch 0255):** the
  windowed profile omits only the non-launch physics operator and Particle Edit keymap
  registration roots while physics DNA/RNA, generic `.blend` loading, modifiers, simulation
  data, and native/headless registration remain. The real locked product drops 117,398 raw and
  13,116 pinned Brotli-q11 bytes; focused fail-first/mutation/round-trip controls, preservation
  builds, canonical replay, REUSE, scoped M8, and container-backed regression are verified. M8
  remains RED: the 23,471,033-byte Wasm alone is 8,471,033 bytes over the complete 15 MB budget
  before stage-0 data, and hardware/APPLY receipts remain s7-blocked. See
  `notes/m8-physics-registration-cut-20260824.md`.
- [x] **M8-MASK-REGISTRATION-CUT [driver, blocked-by: none] REJECTED:** an exact
  windowed-only guard around the Mask operator, macro, and keymap roots preserved Mask data and
  stock native/headless behavior but removed only 1,452 pinned Brotli-q11 bytes while hiding 40
  visible operators. The candidate patch, option, verifier, and postimage were removed; no feature
  cut or deferral ships. See `notes/m8-mask-registration-cut-rejected-20260824.md`.
- [x] **AUDIT-20260824-R9 [driver] (`3920f42`):** adversarially reviewed exact range
  `c36e225^..44186b4` and found three critical, two major, and two minor fidelity, file-preservation,
  source-gate, evidence, documentation, and process defects. Canonical replay, the real product
  no-work build, compliance, protected-path ownership, authorship, and hardware/non-receipt
  boundaries remain clean. See `reports/audit-20260824-r9.md` and
  `notes/stuck-2026-08-24.md`.
- [x] **AUDIT-R9-M8-FIDELITY-RESTORE [driver, blocked-by: none] COMPLETE (`a86ce79`):** all
  21 registration calls are unconditional again; patches 0248-0255, their feature switches,
  size-only deferrals, and non-composable verifiers are retired while eight notes preserve the
  rejected measurements. The aggregate gate rejects eight mutations, the 257-path canonical
  postimage replays exactly, native/headless preservation builds are green, and the real locked
  product is byte-identical to the pre-cut baseline. M8 remains honestly red at its independent
  25 technical boundaries. See `notes/m8-registration-fidelity-restore-20260824.md`.
- [x] **AUDIT-R9-M7-OMITTED-TYPE-ROUNDTRIP [driver, blocked-by:
  AUDIT-R9-M8-FIDELITY-RESTORE] COMPLETE (`6168983`):** a pinned native-authored fixture now
  proves exact native/Wasm load-save-reload state parity for linked storage-bearing compositor
  nodes and active/inactive VSE, Spreadsheet, Clip, and NLA spaces. Seven state comparisons and
  eight semantic mutations reject undefined nodes, `SPACE_EMPTY`, missing spaces/regions, and
  type-specific state loss. The freshly linked headless Wasm graph ends no-work. The focused
  component receipt does not promote M7 or claim stock-native readability of Wasm32 output. See
  `notes/m7-omitted-type-roundtrip-20260824.md`.
- [x] **M7-WASM32-WRITE-CROSS-ABI [driver, blocked-by: none] COMPLETE (patch 0248):** regular
  Wasm32 saves now reconstruct compiled structs into Blender's canonical historical 32-bit layout
  before pointer remapping, while live memory and undo retain the real wasm32 layout. Unmodified
  pinned native Blender and Wasm preserve seven exact semantic states across both directions; the
  pinned historical BHead4 corpus round-trips with 1,718 independently checked structured blocks,
  upstream global undo preserves runtime-layout memfiles, and fourteen mutations reject schema,
  header, length, truncation, and semantic corruption. Native makesdna output remains
  byte-identical. See
  `notes/m7-wasm32-write-cross-abi-20260824.md`.
- [x] **AUDIT-R9-GHOST-CALLBACK-CENSUS [ghost-web, blocked-by: none] COMPLETE
  (`2181d34`):** all six `CallbackMode::AllowSpontaneous` registrations are structurally bound by
  method, exact callee, argument positions, callback form, and owner role. The prior eight-role
  alias escape now rejects, while native/wasm32 lifecycle parity and both unsafe-ASan controls
  remain green. See `notes/m4-ghost-callback-registration-census-r9-20260824.md`.
- [x] **AUDIT-R9-GHOST-INHERITANCE-DOC [ghost-web, blocked-by: none] COMPLETE (`fe1ebb4`):** the
  class-adjacent Doxygen contract now separates the shipping pre-main bundle import from standalone
  `initAsync()` acquisition and binds both to the shared owner-lifecycle gate. A structural checker
  rejects six inheritance, path, gate, prefix-only, and stale-duplicate mutations while the full
  native-ASan/wasm32 lifecycle matrix remains green. See
  `notes/m4-ghost-inheritance-documentation-r9-20260824.md`.
- [x] **M8-COMPLIANCE-CURRENT-RECEIPT [compliance, blocked-by: none] COMPLETE:** the exact
  repository-local REUSE 6.2.0 producer now binds the current tracked-input and reachable-history
  digests with all nine technical facts and 2,283/2,283 files green. Independent resolver,
  consumer, and receipt-mutation contracts pass; the real M8 scope drops exactly the two stale
  compliance failures (25 to 23) while all four external-policy facts remain honestly false. The
  ignored receipt is regenerated after the record commit so that commit is included in both
  digests. See `notes/m8-compliance-current-receipt-20260824.md`.
- [x] **M8-PUBLIC-DISCLAIMER [compliance, blocked-by: none] COMPLETE (`35736d9`):** the root
  README and visible browser footer now carry the complete standing affiliation, endorsement,
  sponsorship, and trademark statement, and the staged runtime verifier requires the same text.
  A browser-free source gate passes one live case and rejects eight wording, visibility/link,
  script-order, and verifier mutations. The current compliance receipt flips exactly
  `public_disclaimer_complete` to true; technical compliance remains green, three external-policy
  facts remain false, and M8 retains its 23 independent APPLY/browser/aggregate boundaries. See
  `notes/m8-public-disclaimer-20260824.md`.
- [x] **M3-BINDSPACE-SCOPED-RESOURCE-VERIFIER [gpu-backend, blocked-by: none] COMPLETE
  (`72616c2`):** the device-free bind-space driver now extracts the sampler descriptor through the
  current scoped-cache boundary and the dummy-vertex mapped-at-creation helper plus its scoped
  context call. Root/descendant runs pass seven fail-closed mutations and six byte-identical
  native/Wasm contracts; canonical replay, the real product no-work check, OFF preflight, REUSE,
  scoped M3, and container-backed regression are verified without promoting the s7-blocked live
  receipt. See `notes/m3-bindspace-scoped-resource-verifier-20260824.md`.
- [x] **M6-CYCLES-PASS-DELTA-REFRESH [driver, blocked-by: none] COMPLETE:** the current
  dedicated Release Cycles-CPU Wasm product rebuilds and ends locked no-work. Immutable Linux
  receipt `m6-cycles-ornith-linux-20260824-r6` passes all 27 scenes with zero exclusions, and an
  independent pinned-OIIO replay is green; every verdict and stored pixel metric is unchanged
  from r5. Aggregate M6 remains red only at its separate s7-blocked Workbench/EEVEE, browser,
  and complete-product boundaries. See `notes/m6-cycles-pass-delta-refresh-20260824.md`.
- [x] **M5-ASYNC-READBACK-CONTRACT-RECONCILE [driver, complete]:** COMPLETE (`d58164f`;
  Linux receipts `20260824T132924-89982`/`20260824T132351-86123`): the actual readback and
  selection sources pass byte-identical native/wasm32 owned-result, exact-replay, and failure
  contracts; the source receipt binds L-B and C1 across 20 files and fails closed under six
  mutations. Seven synchronous caller families remain registered under
  `gpu-sync-readback-windowed`, and live M5 acceptance retains its separate named hardware
  blocker. See `notes/m5-async-readback-contract-reconcile-20260824.md`.
- [x] **M5-VIEWPORT-COLOR-READBACK [driver, complete]:** COMPLETE (`c9ac6eb`, patch 0249;
  Linux receipts `20260824T140833-124956`/`20260824T140638-122768`): the retained View3D
  eyedropper copy now owns and exactly consumes an async texture-read ticket, confirmation waits
  through a bounded modal continuation, and failure/timeout cancels before texture release.
  Native/wasm32 contracts are byte-identical; the partial deferral now names six synchronous
  families. See `notes/m5-viewport-color-readback-20260824.md`.
- [x] **M5-SCREENSHOT-ASYNC-READBACK [driver, complete]:** COMPLETE (`55afed3`, patch 0250;
  Linux receipts `20260824T143611-146139`/`20260824T143622-146564`): the stock screenshot operator
  now retains one exact WM offscreen capture across its file selector and resumes direct or
  early-confirmed execution through a bounded modal timer. Native/wasm32 contracts are
  byte-identical; the partial deferral now names five synchronous families. See
  `notes/m5-screenshot-async-readback-20260824.md`.
- [x] **M5-FRAMEBUFFER-ASYNC-READBACK-PRIMITIVE [driver, complete]:** COMPLETE (`19accd5`, patch 0251;
  Linux receipts `20260824T151831-184570`/`20260824T151932-186003`/
  `20260824T151956-186925`): public color/depth framebuffer regions now return owned results;
  native backends complete immediately while WebGPU retains an exact subresource ticket and
  applies the existing crop, row-order, channel-extension, and format transform once after
  settlement. Native/wasm32 owned-result, texture, and pipeline contracts are byte-identical.
  This is an enabler only: all five synchronous caller families remain explicitly deferred.
- [x] **M5-WINDOW-COLOR-ASYNC-READBACK [driver, complete]:** COMPLETE (`c9b0118`, patch 0252;
  Linux receipts `20260824T155547-216321`/`20260824T155805-219151`): one owned full-window
  snapshot now serves the main colour eyedropper, colour-band gradient/point sampling, and
  grease-pencil material sampling. Their exact event/action state resumes through bounded modal
  timers, with cancellation before pixel release. Native/wasm32 contracts are byte-identical;
  the partial deferral now names four synchronous families. See
  `notes/m5-window-color-readback-20260824.md`.
- [x] **M5-LEGACY-SELECTION-READBACK-PRIMITIVE [driver, complete]:** COMPLETE (patch 0253;
  Linux receipt `20260824T163743-254924`): the draw-selection layer now owns an exact
  viewport-clamped framebuffer request and realigns only settled bytes into the synchronous
  layout. Five native/wasm32 contracts are byte-identical and 14 source mutations fail closed.
  This is an enabler only: all four synchronous caller families remain explicitly deferred. See
  `notes/m5-legacy-selection-readback-primitive-20260824.md`.
- [x] **M5-LEGACY-SELECTION-CLICK-CONTINUATION [driver, complete]:** COMPLETE (patch 0254;
  Linux receipt `20260824T171112-282764`): edit-mesh face/edge/vertex click selection now owns
  sample/nearest queries across the existing bounded View3D timer, replays exact IDs and Manhattan
  distance, and restores each result's producing element-range context before mapping it. Six
  native/wasm32 contracts are byte-identical and 21 source mutations fail closed. The legacy
  selection family remains partial only for box/lasso/circle gesture callers. See
  `notes/m5-legacy-selection-click-continuation-20260824.md`.
- [x] **M5-LEGACY-SELECTION-GESTURE-CONTINUATION [driver, complete]:** COMPLETE (91cc626,
  patch 0255;
  Linux receipt `20260824T175224-312862`): edit-mesh box/lasso/circle bitmap reads now own their
  raw requests and exact producing context across bounded operator continuations. Rectangle,
  polygon-mask, strict circle-radius, bitmap-index, pre-deselect, exact circle-input replay, and
  queued-event semantics pass byte-identical native/wasm32 contracts. Three synchronous families
  remain. See `notes/m5-legacy-selection-gesture-continuation-20260824.md`.
- [x] **M5-CURSOR-DEPTH-PICK-CONTINUATION [driver, complete]:** COMPLETE (24b455e, patch 0256;
  Linux receipts `20260824T185550-361269`/`20260824T185406-360275`/
  `20260824T185413-360351`): cursor placement now owns one exact progressive 0/2/4-pixel depth
  request across a bounded View3D modal continuation. Native immediate and browser pending paths
  preserve the producing event/orientation; supersession, failure, timeout, view drift, and later
  cursor mutation cancel without a stale write. Six native/wasm32 contracts are byte-identical
  and 13 source mutations fail closed. The depth-pick family remains partial for navigation,
  center-pick, eyedropper, painting, zoom-border, and NDOF consumers; the overall census therefore
  remains three families. See `notes/m5-cursor-depth-pick-continuation-20260824.md`.
- [x] **M5-VIEW-CENTER-PICK-CONTINUATION [driver, complete]:** COMPLETE (97729d0, patch 0257;
  Linux receipt `20260824T191910-380328`): Center View to Mouse now retains its exact event,
  smooth-view duration, and producing viewport across the shared progressive depth request.
  Native-ready and browser-pending paths apply the stock hit/simple-pan result exactly once;
  supersession, Escape, failure, timeout, cancellation, and view drift retire without starting a
  stale smooth-view transition. Six native/wasm32 contracts and 13 cases are byte-identical; five
  depth-pick consumer groups remain and the overall census remains three synchronous families.
- [x] **M5-DEPTH-EYEDROPPER-CONTINUATION [driver, complete]:** COMPLETE (88ac170, patch 0258;
  Linux receipt `20260824T195226-407678`): the depth eyedropper now retains its exact producing
  viewport, view origin, event, accumulation action, and pending confirmation across the shared
  progressive depth request. Native-ready and browser-pending paths preserve aligned distance,
  accumulation/reset, latest-drag supersession, and the pinned direct-confirm behavior; context
  drift, failure, timeout, and cancellation retire without a stale property write. Six
  native/wasm32 contracts and 13 cases are byte-identical; navigation, painting, zoom-border, and
  NDOF remain, so the overall census remains three synchronous families.
- [x] **M5-NAVIGATION-DEPTH-CONTINUATION [driver, complete]:** COMPLETE (7f71566, patch 0259;
  Linux receipt `20260824T203717-442946`): ordinary rotate/move/pan/zoom operators now retain the
  stock initialization prelude, exact invoke event, and latest queued event across the shared
  progressive depth request. Native-ready requests remain immediate; browser-pending requests
  resume the stock pivot and navigation initializer exactly once. Context drift, Escape, external
  cancel, readback failure, and timeout restore the backed-up view. The embedded navigation
  utility, direct dolly, and NDOF custom-data paths remain pinned instead of starting an unowned
  continuation. Six native/wasm32 contracts and nine cases are byte-identical; direct dolly,
  painting, zoom-border, and NDOF remain, so the overall census remains three synchronous families.
- [x] **M5-DOLLY-DEPTH-CONTINUATION [driver, complete]:** COMPLETE (`1f06cdb`, patch 0260;
  Linux receipt `20260824T211104-470894`): direct dolly now enters the owned generic
  navigation-depth continuation and resumes its exact delta, vertical/horizontal trackpad,
  perspective, modal-switch, cancellation, autokey, and undo tails only after settlement. Eight
  native/wasm32 contracts and 16 cases are byte-identical; painting, zoom-border, and NDOF remain,
  so the overall census stays at three synchronous families. See
  `notes/m5-dolly-depth-continuation-20260824.md`.
- [x] **M5-PAINTING-DEPTH-CONTINUATION [driver, complete]:** COMPLETE (`91f2974`, patch 0261;
  Linux receipts `20260824T220055-509353`/`20260824T220116-509701`): texture paint's
  inverted-clone cursor now owns its exact progressive-depth request across browser ticks and
  defers the exact custom-data-free terminal event until settlement. Native-immediate and no-hit
  paths remain stock; latest-motion supersession, producing-context/cursor drift, failure,
  timeout, unsafe event payload, and cancellation cannot publish a stale cursor or outlive the
  paint handle. Eight native/wasm32 contracts and 13 cases are byte-identical; zoom-border and
  NDOF remain, so the overall census stays at three synchronous families. See
  `notes/m5-painting-depth-continuation-20260824.md`.
- [x] **M5-ZOOM-BORDER-DEPTH-CONTINUATION [driver, complete]:** COMPLETE (`85b24e7`, patch
  0262; Linux receipts `20260824T223725-538489`/`20260824T223702-537136`): Zoom to Border
  now owns its exact post-clamp rectangle-depth request, transfers a pending request out of the
  generic box gesture into a bounded modal continuation, and replays the producing view, zoom
  direction, smooth duration, nearest-depth reduction, perspective cancellation, and orthographic
  fallback exactly once. Eight native/wasm32 contracts and 20 cases are byte-identical; 15 source
  mutations fail closed. Only NDOF remains in the depth-pick family, so the overall census stays at
  three synchronous families. See `notes/m5-zoom-border-depth-continuation-20260824.md`.
- [x] **M5-NDOF-DEPTH-CONTINUATION [driver, complete]:** COMPLETE (`5605c85`, patch 0263;
  Linux receipts `20260824T231821-569100`/`20260824T231848-569669`): NDOF keeps the stock
  bounds-first orbit-center choice, owns only the fallback rectangle-depth request, and retains the
  exact starting plus queued 3D-mouse payloads in FIFO order across bounded browser settlement.
  Native-ready behavior remains immediate; producing-view drift, invalid payloads, queue overflow,
  timeout, backend failure, Escape, and external cancellation converge on owned cleanup. Eight
  native/wasm32 contracts and 20 cases are byte-identical; eight source mutations fail closed. This
  closes the depth-pick family at the source/device-free boundary, leaving exactly depth cache and
  WM window capture synchronous. See `notes/m5-ndof-depth-continuation-20260824.md`.
- [x] **M5-DEPTH-CACHE-READBACK-PRIMITIVE [driver, complete]:** COMPLETE (`f81d38e`, patch 0264;
  Linux receipts `20260825T000145-605723`/`20260824T235745-601686`): one owned full-viewport
  request now retains the exact texture dimensions, producing region and view matrices, validates
  byte/allocation/index geometry, and transfers one `ViewDepths` only after settlement. Six
  native/wasm32 contracts and 14 cases are byte-identical; nine source mutations fail closed and
  both product-graph translation-unit compiles pass. This is an enabler only: depth-cache caller
  continuations and WM window capture remain open, while live M5 acceptance retains its named
  hardware blocker. See `notes/m5-depth-cache-readback-primitive-20260825.md`.
- [x] **M5-CURVE-DRAW-DEPTH-CACHE-CONTINUATION [driver, complete]:** COMPLETE (`2d6dd6a`,
  patch 0265; Linux receipts `20260825T004848-645324`/`20260825T004914-645849`): both
  `CURVE_OT_draw` and `CURVES_OT_draw` now force the stock depth pass without a synchronous cache
  read, retain their producing context and a bounded custom-data-free event FIFO while the owned
  cache settles, and replay through the original modal dispatcher. Native-immediate, pending
  wait/non-wait, fallback, drift, failure, timeout, queue, Escape, and external-cancel behavior
  passes eight byte-identical native/wasm32 contracts and 16 cases; 19 source mutations fail closed
  and all three product-graph translation units compile. Legacy annotation, Grease Pencil surface
  placement, object axis-target placement, and particle edit keep the depth-cache family partial;
  WM window capture remains the other synchronous family, and live M5 acceptance retains its named
  hardware blocker. See `notes/m5-curve-depth-cache-continuation-20260825.md`.
- [x] **M5-ANNOTATION-DEPTH-CACHE-CONTINUATION [driver, complete]:** COMPLETE (`940fccd`, patch
  0266; Linux receipts `20260825T014913-693360`/`20260825T013752-683591`): interactive
  `GPENCIL_OT_annotate` draw, polyline-update, and depth-aware eraser events now retain the exact
  initiating disposition plus a bounded custom-data-free FIFO behind one producing-view-guarded
  depth-cache request. Native-immediate, pending initial apply, eraser FIFO, chained polyline
  refresh, failure, drift, timeout, bounds, and external cancellation pass eight byte-identical
  native/wasm32 contracts and 18 cases; 12 focused and 39 aggregate mutations fail closed. The
  recorded-stroke `exec` callback remains an explicit synchronous residual alongside Grease Pencil
  placement, object axis-target placement, particle edit, and WM window capture; live M5 acceptance
  retains its named hardware blocker. See
  `notes/m5-annotation-depth-cache-continuation-20260825.md`.
- [x] **M5-ANNOTATION-RECORDED-DEPTH-CACHE-CONTINUATION [driver, complete]:** COMPLETE
  (`a9074d2`, patch 0267; Linux receipts `20260825T022323-723190`/
  `20260825T022342-723491`): recorded `GPENCIL_OT_annotate.exec` snapshots exactly the four RNA
  fields consumed by stock replay and retains its point cursor across owned cache settlement. It
  preserves multi-stroke end/start ordering, native-ready execution on the original stack, and
  depth-aware eraser reuse; pending generations resume through the bounded annotation timer while
  unrelated events are swallowed and Escape cancels. Thirteen native/wasm32 contracts and 31
  cases are byte-identical; 17 focused and 40 aggregate mutations fail closed, all annotation
  synchronous depth overrides are gone, and the production translation unit plus windowed product
  compile. Grease Pencil placement, object axis-target placement, particle edit, and WM window
  capture remain explicit residuals; live M5 acceptance retains its named hardware blocker. See
  `notes/m5-annotation-recorded-depth-cache-continuation-20260825.md`.
- [x] **M5-GREASE-PENCIL-PAINT-DEPTH-CACHE-CONTINUATION [driver, complete]:** COMPLETE
  (`148d1bc`, patch 0268; Linux receipts `20260825T030716-764796`/
  `20260825T030658-764357`): freehand `GREASE_PENCIL_OT_brush_stroke` surface/stroke placement now
  owns one full-viewport depth-cache request and retains its exact first plus generated input
  samples behind one bounded, producing-view-guarded modal timer. Settlement replays the sample
  FIFO and a sanitized terminal event through the stock paint dispatcher, preserving release-time
  line/anchored-brush finalization; native-ready and non-depth paths remain immediate. Eight
  byte-identical native/wasm32 contracts and 18 cases pass, 12 source mutations fail closed, and
  exact native/wasm product-graph compiles plus the real windowed product are green. Grease Pencil
  primitive/fill/pen-helper placement, object axis-target placement, particle edit, and WM window
  capture remain explicit residuals; live M5 acceptance retains its named hardware blocker. See
  `notes/m5-grease-pencil-depth-cache-continuation-20260825.md`.
- [x] **M5-GREASE-PENCIL-PRIMITIVE-DEPTH-CACHE-CONTINUATION [driver, complete]:** COMPLETE
  (`72e1939`, patch 0269; Linux receipts `20260825T034959-802925`/
  `20260825T034535-798854`): the shared invoke for all six `GREASE_PENCIL_OT_primitive_*`
  operators now owns one bounded full-viewport cache request before its first projected point.
  Invoke-time coordinates/type/subdivision plus up to 256 safe modal events remain behind one
  producing-context-guarded 240-tick timer; settlement creates navigation, geometry, preview, and
  modal state exactly once before FIFO replay. Native-ready, non-depth, and stock initial-failure
  fallback paths remain immediate. Eight byte-identical native/wasm32 contracts and 28 cases pass,
  16 mutations fail closed, and exact native/wasm product-graph compiles plus the real windowed
  product are green. Fill/pen-helper placement, object axis-target placement, particle edit, and WM
  window capture remain explicit residuals; live M5 acceptance retains its named hardware blocker.
  See `notes/m5-grease-pencil-primitive-depth-cache-continuation-20260825.md`.
- [x] **M5-GREASE-PENCIL-FILL-DEPTH-CACHE-CONTINUATION [driver, complete]:** COMPLETE
  (`340a412`, patch 0270; Linux receipts `20260825T042956-838065`/
  `20260825T042859-837447`): the fill operator now owns one exact click and full-viewport
  placement request before editable drawings, pixel images, or Delaunay results exist. Both solvers
  consume the same ready placement through explicit helper parameters; non-depth, native-ready,
  and initial-failure fallback remain immediate. Eight native/wasm32 contracts and 28 cases are
  byte-identical, 12 source mutations fail closed, and exact native/wasm product translation units
  plus the real windowed product are green. Pen-helper placement, object axis-target placement,
  particle edit, and WM window capture remain explicit residuals; live M5 acceptance retains its
  named hardware blocker. See
  `notes/m5-grease-pencil-fill-depth-cache-continuation-20260825.md`.
- [x] **M5-GREASE-PENCIL-PEN-DEPTH-CACHE-CONTINUATION [driver, complete]:** COMPLETE
  (`71f82ec`, patch 0271; Linux receipts `20260825T050322-863354`/
  `20260825T050406-864531`): `GREASE_PENCIL_OT_pen` now owns one surface/stroke placement request
  before keyframe duplication or editable-drawing/transform capture, retains the exact initiating
  event plus up to 256 safe modal events behind a producing-context-guarded 240-tick timer, and
  resumes through the shared stock first-event seam before FIFO modal replay. Non-depth,
  native-ready, and initial-failure fallback remain immediate. Nine native/wasm32 contracts and 33
  cases are byte-identical, 14 mutations fail closed, and exact native/wasm product translation
  units plus the real windowed product are green. Object axis-target placement, particle edit, and
  WM window capture remain explicit residuals; live M5 acceptance retains its named hardware
  blocker. See `notes/m5-grease-pencil-pen-depth-cache-continuation-20260825.md`.
- [x] **M5-OBJECT-AXIS-TARGET-DEPTH-CACHE-CONTINUATION [driver, complete]:** COMPLETE
  (`d2a2456`, patch 0272; Linux receipts `20260825T054216-898447`/
  `20260825T054234-898674`): `OBJECT_OT_transform_axis_target` now restores its temporary render
  override before starting one owned full-viewport cache request, retains the exact initiating
  event plus up to 256 safe modal events behind a producing-context-guarded 240-tick timer, and
  captures selected objects/transform backups only after exact cache transfer. Immediate-ready,
  incompatible-target, stock no-depth cancellation, translation, confirm/release, and cancellation
  semantics remain intact. Eight native/wasm32 contracts and 36 cases are byte-identical, 17
  mutations fail closed, and exact native/wasm product-graph compiles plus the real windowed
  product are green. Particle edit is the sole depth-cache residual; WM window capture remains the
  other synchronous family, and live M5 acceptance retains its named hardware blocker. See
  `notes/m5-object-axis-target-depth-cache-continuation-20260825.md`.
- [x] **M5-PARTICLE-EDIT-DEPTH-CACHE-CONTINUATION [driver, complete]:** COMPLETE
  (`32c338a`, patch 0273; Linux receipts `20260825T064636-947776`/
  `20260825T064916-950503`): click, linked-pick, box, lasso, circle, and brush-start now own an
  exact full-viewport prepare/consume session before any `PEData` traversal or selection mutation.
  XRAY and native-ready paths remain immediate; pending paths retain exact inputs behind identified
  240-tick polls and bounded 512/256-event FIFOs, with producing-context validation and complete
  cleanup. Eight native/wasm32 contracts and 44 cases are byte-identical, 20 focused and 44
  aggregate mutations fail closed, and exact native/wasm product-graph compiles plus the real
  windowed product are green. This closes the depth-cache caller family; WM window capture is the
  sole synchronous residual, and live M5 acceptance retains its named hardware blocker. See
  `notes/m5-particle-edit-depth-cache-continuation-20260825.md`.
- [x] **M5-ASSET-PREVIEW-WINDOW-CAPTURE-CONTINUATION [driver, complete]:** COMPLETE
  (`564cd59`, patch 0274; Linux receipts `20260825T081222-1026760`/
  `20260825T081000-1024727`): `ASSET_OT_screenshot_preview` now owns its general-window snapshot,
  exact crop, producing window context, asset type, and weak reference behind an identified
  240-tick timer before preview or asset mutation. Native-ready and 3D-viewport offscreen paths
  remain immediate; direct execution gains a modal owner, and every drift/failure/timeout/cancel
  path retires the timer and request. Eight native/wasm32 contracts and 28 cases are byte-identical,
  18 focused and 46 aggregate mutations fail closed, and exact product-graph compiles plus the real
  windowed product are green. Only synchronous Python `Window.screenshot()` remains in the WM
  capture family; it requires a separate API/design decision, while live M5 acceptance retains its
  named hardware blocker. See
  `notes/m5-asset-preview-window-capture-continuation-20260825.md`.
- [x] **M5-PYTHON-WINDOW-SCREENSHOT-BROWSER-DEFERRAL [driver, blocked-by: none]:** COMPLETE
  (`ea8dc3c`, patch 0275): the stock `Window.screenshot()` method, keyword parsing, background
  error, crop/alpha handling, and immediate owned-memoryview return remain exact on native, while
  Emscripten raises an actionable `RuntimeError` before any synchronous pixel read and directs file
  capture to the already-owned screenshot-operator continuation. Focused post-commit source,
  numbered-round-trip, exact native/wasm product-object, and 12-mutation checks are green; symbol
  inspection proves only the native object references `WM_window_pixels_read`. The aggregate
  50-source/48-mutation contract reports zero remaining browser-sync families and one explicit API
  deferral. The real product rebuild/no-work, OFF preflight, canonical replay, REUSE, M5 scope, and
  container-backed regression retain their strict boundaries. See
  `notes/m5-python-window-screenshot-browser-deferral-20260825.md`.
- [x] **AUDIT-20260825-R10 [driver] (`b190bbe`):** adversarially reviewed exact range
  `2d6dd6a519db13d1f8e4b479f35a59372073eb18..88572261b39a85dea9a1b8e44e9aee4f64ae4bec`
  and found zero critical, four major, and three minor presentation-validation, liveness,
  stale-producer, evidence-freshness, and process defects. Both reported P0 root fixes are
  structurally correct; focused contracts, current canonical replay, the product no-work build,
  compliance, protected-path ownership, authorship, and hardware/non-receipt boundaries remain
  clean. Four asset-preview fixture EOF defects are fixed here. See
  `reports/audit-20260825-r10.md`.
- [x] **AUDIT-R10-M4-SURFACE-PREFLIGHT-VALIDATION [ghost-web] (`7bc9916`):** replaced the
  worker's optional one-turn `uncapturederror` observation with a scoped first surface submission
  and queue-work completion before non-fallback publication. Exact browser-reported fallback is a
  labeled diagnostic-only compatibility path that binds no receipt; false or missing status fails
  closed through strict validation. Fourteen production-shaped cases decouple synchronous,
  delayed, and omitted telemetry from deterministic scope results. See
  `notes/m4-surface-preflight-validation-20260825.md`.
- [x] **AUDIT-R10-M4-SUSTAINED-WM-LIVENESS [ghost-web] (`17f1265`):** the fallback-only headed
  diagnostic now uses Chromium's software GPU-test posture, waits boundedly for a second real WM
  tick, proves continued progress across two further samples, and requires trusted canvas input to
  produce both another tick and presentation with zero device loss. A device-free classifier
  rejects 23 frozen/missing/late/hardware/error mutations. The live result remains explicitly
  `diagnostic-nonreceipt`; it binds no adapter, pixel, profile, or hardware receipt. See
  `notes/m4-sustained-wm-liveness-20260825.md`.
- [x] **AUDIT-R10-M5-AXIS-TARGET-PRODUCER-STATE [driver] (`7271d4e`, patch 0276):** pending
  Look at Surface depth now retains the producer frame plus exact compatible-target pointer/session,
  parent/data, local-channel, inverse, and evaluated-matrix state before suspension, and rejects any
  same-pointer drift before cache transfer or modal-backup creation. The predecessor fails before
  evidence; final focused native/wasm32 verification passes 9 contracts/39 cases and 23 mutations,
  while the 51-source aggregate passes 52 mutations with zero synchronous browser families. Exact
  patch round-trip, native/windowed product-TU compiles, canonical replay, real product relink/no-work,
  OFF preflight, REUSE, M5 scope, and container-backed regression retain their strict boundaries. See
  `notes/m5-axis-target-producer-state-20260825.md`.
- [x] **AUDIT-R10-M5-PARTICLE-PRODUCER-STATE [driver] (`9e9fc95`, patch 0277):** pending
  particle depth now retains the producer frame, object identity/matrices, and a 128-bit token over
  particle-system, topology, coordinate, time, and flag state before preparation. The token is
  recomputed only at readiness immediately before depth transfer; drift fails while click, gesture,
  and brush callers remain uninitialized. Final focused native/wasm32 verification passes 9
  contracts/53 cases and 26 mutations, while the 51-source aggregate passes 56 mutations with zero
  synchronous browser families. Exact patch round-trip, product-TU compiles, canonical replay,
  real product relink/no-work, OFF preflight, REUSE, M5 scope, and container-backed regression
  retain their strict boundaries. See `notes/m5-particle-producer-state-20260825.md`.
- [x] **AUDIT-R10-CANONICAL-RECEIPT-FRESHNESS [driver] (`421e610`):** the fixed-path upstream
  freeze receipt is now an accepted input to canonical replay: stale patch bytes/hash, pin,
  schema/check set, manifest identity, or malformed provenance rejects before PASS. A genuine
  full-freezer refresh binds the current 303-path snapshot, and 18 hermetic mutations fail closed;
  absolute evidence-origin paths do not prevent byte-identical clones from verifying the proof.
  See `notes/audit-r10-canonical-receipt-freshness-20260825.md`.
- [x] **P0-M4-SURFACE-SAME-TURN-SUBMISSION [ghost-web] (`69307e4`):** complete surface command
  buffers now submit synchronously in their acquisition turn instead of waiting for asynchronous
  encoding scopes to yield and destroy Chromium's transient texture. Encoding and submission
  results join before present publication, while null handles still submit nothing. Native/wasm32,
  callback-lifecycle/ASan, locked product/no-work/OFF-preflight, and the headed zero-rejection
  fallback diagnostic are green. The live result remains diagnostic-nonreceipt and the hardware
  blocker is unchanged. See `notes/m4-present-same-turn-submission-20260825.md`.
- [x] **M4-LOCAL-PRODUCT-ENTRY [driver] (`3aef6f1`):** the canonical COOP/COEP development
  server now exposes the intended windowed native-app shell and windowed-opt binary at `/` by
  default. Explicit `BLENDER_WEB_ENTRY=index.html` preserves the legacy headless root, index-only
  harnesses retain their old behavior, and canonicalized entry paths cannot escape the shell root.
  Four hermetic HTTP cases, exact real-product root identity, locked product no-work, and the
  headed sustained-WM/input/presentation diagnostic at `/` are green. The live run is explicitly
  fallback-software diagnostic evidence and binds no adapter, pixel, profile, or milestone receipt.
  See `notes/m4-local-product-entry-20260825.md`.
- [x] **M3.T10-CONTEXT-OWNED-PIPELINE-CACHES [gpu-backend] (c5f5565):** patch 0278 moves the
  batch, immediate, and indexed-triangle-fan pipeline caches onto `WGPUContext`, preserving cache
  separation while preventing a replacement device/context from receiving retained handles. The
  fail-first eight-case native/wasm32 ownership contract, five-file isolated patch replay,
  canonical replay, real product rebuild/no-work, OFF preflight, same-artifact headed fallback
  diagnostic, REUSE, scoped M3, and full regression are verified. Strict live proof retains the
  named s7 hardware blocker. See `notes/m3-t10-context-owned-pipeline-caches-20260825.md`.
- [x] **M3.T5-CONTEXT-BACKEND-HANDLE-REGISTRY [gpu-backend] (4b28c64):** patch 0279 replaces
  independently mutable process-static instance/device/queue fields with one locked
  latest-live-owner tuple. Async shader compilation takes one coherent snapshot; older teardown
  preserves a newer context and newest teardown restores the previous live owner. Fail-first
  native/wasm32 lifetime coverage, four-file patch replay, canonical replay, locked product
  rebuild/no-work, same-artifact headed fallback diagnostics, REUSE, scoped M3, and full regression
  are verified. Strict live proof retains the named s7 hardware blocker. See
  `notes/m3-context-backend-handle-registry-20260825.md`.
- [x] **M4-GHOST-WINDOW-ACTIVATION [ghost-web] (8942b4e):** the browser window now delegates
  activation through stock `GHOST_Window`, returning the imported WebGPU context's real device
  status instead of the original unconditional failure stub. The fail-first/final source contract,
  three mutations, integrated native/wasm32 matrix, locked product relink/no-work, OFF preflight,
  sustained headed fallback diagnostic, REUSE, scoped M4, and container-backed regression are
  verified. Live proof remains diagnostic-nonreceipt and the s7 blocker is unchanged. See
  `notes/m4-ghost-window-activation-20260825.md`.
- [x] **M4-WEB-CURSOR-MAIN-THREAD-BRIDGE [ghost-web] (0aa45be):** standard shape and
  visibility requests now publish atomic shared-Wasm state from the WM worker and the first shell
  script applies all 46 supported GHOST shapes to the DOM canvas. Arbitrary custom cursors fail
  honestly instead of reporting a no-op success. Five source mutations, complete mapping and
  recovery behavior, integrated native/wasm32 parity, locked product relink/no-work, OFF preflight,
  a real headed fallback cursor snapshot, REUSE, scoped M4, and container-backed regression are
  verified. The live run remains diagnostic-nonreceipt and the s7 blocker is unchanged. See
  `notes/m4-web-cursor-main-thread-bridge-20260825.md`.
- [x] **M4-WEB-WINDOW-TITLE-MAIN-THREAD [ghost-web] (`93df837`):** window-title changes now
  synchronously proxy their owned UTF-8 input from the WM worker to the browser main thread instead
  of silently executing a worker-local DOM no-op. A pinned `PROXY_TO_PTHREAD` repro covers Unicode
  and empty titles, five source mutations fail closed, native/wasm32 integration stays
  byte-identical, and the relinked product publishes `(Unsaved) - Blender 5.2.0 LTS` while retaining
  sustained fallback input/presentation progress and zero presentation rejections. The live run is
  diagnostic-nonreceipt and the s7 blocker is unchanged. See
  `notes/m4-web-window-title-main-thread-20260825.md`.
- [x] **M4-WEB-FULLSCREEN-STATE [ghost-web] (`6d71197`):** `GHOST_WindowWeb::setState()` now
  drives HTML5 fullscreen entry/exit, accepts Emscripten's deferred user-activation result, maps
  normal/maximized to the page-filling state, and rejects browser-impossible minimization. The
  real GHOST harness runs the shipping WasmFS/worker topology and proves all four states; focused
  mutations, native/wasm32 parity, exact-commit replay, locked product relink/no-work, OFF
  preflight, sustained fallback diagnostics, canonical replay, REUSE, M4 scope, and regression are
  verified. Live GPU proof remains diagnostic-nonreceipt and the s7 blocker is unchanged. See
  `notes/m4-web-fullscreen-state-20260825.md`.
- [x] **M4-WEB-POINTER-LOCK [ghost-web] (`b09aa76`):** wrap/hide cursor grabs now use Pointer
  Lock, relative DOM movement advances Blender's saturated virtual cursor, and wrap mode retains
  its software cursor. The fail-first false-success repro, 13 fail-closed mutations, real
  worker-topology browser runs, fullscreen regression, native/wasm32 parity, locked product
  relink/no-work, OFF preflight, and real-product middle-drag diagnostic are verified. The live
  run is fallback-software diagnostic evidence only; M4 and the s7 blocker are unchanged. R11
  leaves browser loss/error/deferred-outcome reconciliation open below. See
  `notes/m4-web-pointer-lock-20260825.md` and `reports/audit-20260825-r11.md`.
- [x] **M4-WEB-TEXT-CLIPBOARD [ghost-web] (`5d21f1c`):** trusted paste events now publish
  external text before Emscripten's queued worker key callback, while GHOST's synchronous getter
  returns an owned UTF-8 allocation and Blender copy owns its borrowed input before the browser
  write promise. Primary/image clipboards remain honestly unsupported. The predecessor stub,
  17 mutations, real worker harness, native/wasm32 integration, baked optimized runtime, locked
  relink/no-work, and product Python-Console paste/copy round-trip are verified. The live product
  run uses fallback software and binds no receipt; M4 and the s7 blocker are unchanged. See
  `notes/m4-web-text-clipboard-20260825.md`.
- [x] **M4-WEB-IME-COMPOSITION [ghost-web] (`9608169`):** DOM composition now crosses from
  the browser main thread to the owning WM worker through a bounded SPSC queue of owned UTF-8
  messages, where start/update/commit/end become Blender's stock GHOST IME events. The hidden
  textarea tracks Blender's requested caret rectangle, focus returns to the canvas on end, and
  the windowed product now advertises its implemented IME capability. Twenty-one fail-closed
  mutations, the real worker harness, canonical replay, optimized product relink/no-work, baked
  runtime binding, and a synthetic real-product Unicode object-name commit are verified. This
  closes the bridge/ownership path only: R11 leaves terminal recovery and trusted physical
  IME/dead-key evidence open below. The live product run uses fallback software and binds no
  receipt; M4 and the s7 blocker are unchanged. See
  `notes/m4-web-ime-composition-20260825.md` and `reports/audit-20260825-r11.md`.
- [x] **M4-WEB-FOCUS-STATE-RESET [ghost-web] (`453d587`):** canvas/tab blur now snapshots and
  retires all seven tracked mouse buttons plus every modifier before `WindowDeactivate`,
  publishing held button releases so missing DOM release events cannot leave Blender navigation
  or shortcuts stuck. Fail-first/final real worker harness, 10 mutations, 5,139-byte native/wasm
  parity, canonical replay, optimized product relink/no-work, zero-rejection fallback diagnostic,
  M4 scope, and container regression are verified; the live proof remains nonreceipt and s7 is
  unchanged. See `notes/m4-web-focus-state-reset-20260825.md`.
- [x] **M4-WEB-WINDOW-DISPOSAL-LIFECYCLE [ghost-web] (`64a2578`):** active-window disposal now
  atomically retires the callback owner, removes all ten HTML5 listeners, drains IME, clears input,
  and detaches every system lookup before the base class deletes the window; replacement windows
  rebind callbacks and reset first-pixel settling. The predecessor retained the deleted pointer,
  while the final real worker harness, 17 mutations, native/wasm parity, locked product, sustained
  fallback diagnostic, canonical replay, M4 scope, and regression preserve their strict existing
  boundaries. R11 leaves the cross-registration queued-callback epoch open below. See
  `notes/m4-web-window-disposal-lifecycle-20260825.md` and `reports/audit-20260825-r11.md`.
- [x] **M4-WEB-CUSTOM-CURSOR-BRIDGE [ghost-web] (`1e24fc3`):** Blender's borrowed RGBA and
  legacy XBM custom-cursor spans are now copied synchronously on the browser main thread,
  rasterized to a bounded CSS image cursor with the exact hotspot, and published through the
  existing release generation. RGBA is advertised while the unimplemented generator remains
  masked; invalid geometry/spans preserve the last valid cursor. Fail-first, 12 mutations,
  native/wasm32 parity, real worker/browser pixels, locked product/no-work/OFF-preflight,
  sustained fallback diagnostics, REUSE, M4 scope, and regression preserve their strict existing
  boundaries. See `notes/m4-web-custom-cursor-bridge-20260825.md`.
- [x] **M4-WEB-FRONTBUFFER-CAPABILITY [ghost-web] (`c9502ee`):** GHOST-web now masks the
  synchronous front-buffer capability that its one-turn browser readback cannot satisfy, so stock
  window sampling no longer promotes an interim buffer to success and browser callers reach their
  owned pending/settled continuations. A three-source routing contract rejects six mutations; the
  integrated native/wasm32 matrix, locked product relink/no-work, OFF preflight, sustained fallback
  diagnostic, REUSE, M4 scope, and container regression preserve their strict existing boundaries.
  See `notes/m4-web-frontbuffer-capability-20260825.md`.
- [x] **M4-WEB-CAPABILITY-CLOSURE [ghost-web] (`315a6d6`):** the canvas backend now masks raw
  physical trackpad direction and server-side window decorations: DOM wheel deltas arrive after
  system preference handling, and the browser canvas has no server-owned frame. The exact-commit
  three-source contract rejects six mutations while retaining implemented IME and RGBA cursors;
  integrated native/wasm32 parity, locked product relink/no-work, OFF preflight, sustained fallback
  diagnostics, REUSE, M4 scope, and container regression preserve their strict existing boundaries.
  See `notes/m4-web-capability-closure-20260825.md`.
- [x] **M4-WEB-WINDOW-HIT-TEST [ghost-web] (`e113f1a`):** the single-canvas system now returns
  its active window only when the supplied screen/client point lies inside the live client bounds,
  and returns null after disposal or beyond every edge as required by the pinned GHOST interface.
  The predecessor real worker harness returned only the four interior bits; final exact-commit and
  10-mutation contracts, seven-point browser behavior, integrated native/wasm32 parity, locked
  integration-product relink/no-work, OFF preflight, fallback diagnostic, REUSE, M4 scope, and
  container-backed regression preserve their strict existing boundaries. See
  `notes/m4-web-window-hit-test-20260825.md`.
- [x] **AUDIT-20260825-R11 [driver] (`d7498de`):** adversarially reviewed exact range
  `8942b4ed335bc730912c1e6d7a1d21d2cf311a00..9b51af8eada1b0668e1b4de3af376ad0d30199d7`
  and found zero critical, four major, and three minor input/lifecycle, evidence, compliance, and
  process defects. The three supplied P0 root fixes remain structurally correct and their focused
  Linux checks are fresh. The overclaimed IME/dead-key row is partial again and stale M4 notes are
  corrected; no receipt/result/gate/promise was promoted. See `reports/audit-20260825-r11.md`.
- [x] **AUDIT-R11-M4-POINTER-LOCK-OUTCOME-LIFECYCLE [ghost-web] (`32640eb`):** deferred
  requests now remain Pending until the owned canvas reports an active lock; document change/error
  callbacks reconcile GHOST and active-only relative motion on success, rejection, Escape/loss,
  blur, explicit release, and disposal. The 21-mutation source contract, real worker lifecycle,
  existing focus/disposal regressions, native/wasm32 matrix, locked product relink/no-work, OFF
  preflight, and baked-product external-loss/reacquire diagnostic are green without changing the
  nonreceipt boundary. See `notes/m4-pointer-lock-outcome-lifecycle-20260825.md`.
- [x] **AUDIT-R11-M4-IME-TERMINAL-RECOVERY [ghost-web] (`5daef5f`):** the browser-main/WM-worker
  SPSC queue now reserves its final two slots for Commit and End, stores messages in fixed slots,
  and publishes End/cancel without allocation. Saturation or text-allocation failure explicitly
  cancels composition and suppresses later disposable updates; completed begin and explicit end
  share the same recovery. Native/wasm32 allocation and saturation contracts, the real worker
  saturation/cancel harness, integrated matrix, baked product, and fallback diagnostic are green
  without changing the nonreceipt boundary. See `notes/m4-ime-terminal-recovery-20260825.md`.
- [x] **AUDIT-R11-M4-CALLBACK-REGISTRATION-EPOCH [ghost-web] (`5ac001e`):** each HTML5 listener
  set now owns durable unique userdata and an atomically retired epoch, so callbacks queued under
  either of two prior registrations cannot target a replacement window. Exact-commit mutation,
  real-worker repeated-replacement, native/wasm32, product relink/no-work/OFF-preflight, headed
  fallback diagnostic, canonical, REUSE, M4, and regression checks preserve their strict existing
  boundaries. See `notes/m4-callback-registration-epoch-20260825.md`.
- [x] **AUDIT-R11-M4-CALLBACK-REGISTRATION-TRANSACTION [ghost-web] (`ef25bfa`):** all twelve
  HTML5 listener results now form one ordered transaction; failure removes the exact successful
  prefix and leaves owner/epoch/registered state unpublished, while failed initial or replacement
  windows are destroyed before publication. Native/wasm32 cover every failure position plus
  replacement rollback/retry, and the real worker/product regressions preserve the strict
  nonreceipt boundary. See `notes/m4-callback-registration-transaction-20260825.md`.
- [x] **AUDIT-R11-M4-INPUT-RECORD-RECONCILIATION [driver] (`9d5f485`):** current design and
  deferral records now reflect the implemented fixed-slot IME terminal recovery and complete
  Pointer Lock outcome lifecycle. The `ime-dead-keys` row remains partial solely for trusted
  physical browser/OS evidence; 29 IME and 21 Pointer Lock mutations, REUSE, scoped M4, and
  container-backed regression preserve the existing receipt boundaries.
- [x] **M4-WEB-FIRST-PIXEL-SETTLE-EPOCH [ghost-web] (`f08f451`):** first-pixel settling now uses
  bounded ordinary WindowUpdate events relative to each published window's present baseline;
  replacements no longer inherit a process-global completed count or require synthetic focus/mouse
  events. Eleven mutations, 14 native/wasm cases, the real worker replacement harness, optimized
  product relink/no-work, OFF preflight, and sustained fallback diagnostic are green without
  changing the hardware receipt boundary. See `notes/m4-first-pixel-settle-epoch-20260825.md`.
- [x] **P0-M4-BOOT-PRESENT-ADAPTER-POST-HEAD-REVALIDATION [driver]:** after the first-pixel
  lifecycle change, the committed early canvas registration, same-turn surface submission, and
  current/legacy adapter-shape fixes remain green in the integrated native/wasm matrix and all
  strict producer/consumer self-checks. The exact no-work OFF artifact reaches running WM at the
  canonical windowed `/` entry, advances idle and trusted-input ticks, presents after input, and
  reports zero stage-1/import/submission/transaction/device-loss failures. A stale pre-existing
  port-8123 process was isolated as the retired headless root and binds no evidence; the current
  server on an unused port supplied the passing diagnostic. No hardware receipt or gate changed.
- [x] **M4-WEB-KEYBOARD-FOCUS-OWNERSHIP [ghost-web] (`55db332`):** raw key-down/up listeners
  now register and unregister on the focusable canvas rather than `window`, so ordinary DOM
  controls and Blender's hidden IME textarea cannot also feed their keys into GHOST. The fail-first
  worker run delivered both events while `#clear` owned focus; final focused/blurred browser,
  registration-epoch replacement, IME, focus-state, eight-mutation source, native/wasm32,
  optimized-product, OFF-preflight, fallback-diagnostic, canonical, compliance, M4, and regression
  checks preserve their strict existing boundaries. See `notes/m4-keyboard-focus-20260825.md`.
- [x] **M4-WEB-MOUSE-RELEASE-OWNERSHIP [ghost-web] (`d964a5f`):** a canvas-owned press now
  receives its terminal mouse-up from window capture after the pointer leaves the canvas, while a
  matching tracked-button gate rejects unrelated page releases and preserves their browser default.
  Viewport release coordinates are normalized back to canvas space and listener removal follows the
  exact registration target. The real worker outcome, 12 focused and 32 lifecycle mutations,
  native/wasm32 matrix, locked product relink/no-work, OFF preflight, fallback diagnostic, canonical
  replay, REUSE, M4 scope, and container regression preserve their strict existing boundaries. See
  `notes/m4-mouse-release-ownership-20260825.md`.
- [x] **M4-WEB-MOUSE-DRAG-MOTION-OWNERSHIP [ghost-web] (`303847a`):** window-captured
  mouse-move now continues a canvas-owned drag beyond the element while rejecting unrelated page
  motion unless GHOST owns a tracked button or active Pointer Lock. One coherent DOM canvas
  rectangle is cached at registration/resize, so viewport coordinates translate locally on the WM
  worker without a per-motion main-thread proxy. The fail-first/final real-worker outcome, 22
  focused and 32 lifecycle mutations, native/wasm32 parity, locked product relink/no-work, OFF
  preflight, sustained fallback diagnostic, canonical replay, M4 scope, and container regression
  preserve their strict existing boundaries. See
  `notes/m4-mouse-drag-motion-ownership-20260825.md`.
- [x] **M4-WEB-ACTIVE-WINDOW-MANAGER-LIFECYCLE [ghost-web] (`d343e9e`):** every valid
  canvas publication and DOM focus transition now reconciles `GHOST_WindowManager` before the
  matching GHOST event, while the separate live-canvas target preserves hover and owned-drag
  delivery. The fail-first real worker, 46 focus/lifecycle mutations, native/wasm32 matrix,
  optimized product, OFF preflight, fallback diagnostic, canonical replay, REUSE, M4 scope, and
  container regression preserve their strict existing boundaries. See
  `notes/m4-active-window-lifecycle-20260825.md`.
- [x] **M4-WEB-IME-FOCUS-OWNERSHIP [ghost-web] (`27b75ca`):** the canvas and Blender's enabled
  hidden IME textarea now form one logical GHOST focus domain, so begin/end composition handoffs
  cannot publish false activation transitions or clear the active window. Ordinary page-control
  focus and browser-window loss still deactivate exactly once. The fail-first/final real-worker
  outcome, 17 focused and 33 lifecycle mutations, 14-listener native/wasm transaction matrix,
  locked product relink/no-work, OFF preflight, sustained fallback diagnostic, canonical replay,
  REUSE, M4 scope, and container regression preserve their strict existing boundaries. See
  `notes/m4-ime-focus-ownership-20260825.md`.
- [x] **M4-WEB-MODIFIER-SIDE-STATE [ghost-web] (`f41ebe0`):** DOM keyboard `code` now owns
  exact left/right Shift, Control, Alt, and OS state, including simultaneous sides; aggregate
  mouse/wheel flags preserve known sides and fall back left only without key history. Trusted CDP
  input, focus loss, 19 mutations, integrated parity, the relinked product, and neighboring input
  contracts are green without changing the hardware receipt boundary. See
  `notes/m4-modifier-side-state-20260825.md`.
- [x] **M4-WEB-FOCUS-TRANSITION-ORDER [ghost-web] (`aae9c9a`):** a capturing DOM blur now
  publishes a monotonic loss boundary before Emscripten's proxied callback can observe a later
  refocus and suppress it. The WM worker retires held input before reconciling current focus,
  ordinary blurs acknowledge their publication to prevent duplicate transitions, and explicit
  IME handoffs remain domain-internal. Seventeen mutations, repeated real-worker rapid/ordinary
  cases, all adjacent focus/input contracts, integrated native/wasm32 parity, locked product
  relink/no-work, OFF preflight, sustained fallback diagnostic, M4 scope, and container regression
  preserve their strict existing boundaries. See `notes/m4-focus-transition-order-20260825.md`.
- [x] **P0-M4-BOOT-PRESENT-ADAPTER-CURRENT-HEAD-REVALIDATION [driver, current-head
  `b8f1850`]:** the committed early cmd:2 canvas registration, same-turn surface submission, and
  current/legacy adapter-shape fixes remain green together in the native/wasm matrix and strict
  producer/consumer self-checks. Locked Ninja is exact no-work, the built JavaScript contains the
  early registration exactly once, and the canonical `/` windowed product advances 78 idle ticks
  plus nine trusted-input ticks/two presents with zero stage-1/import/submission/transaction/loss
  failures. The live run is fallback-software diagnostic evidence only; no receipt or s7 boundary
  changed. See `notes/p0-boot-present-adapter-current-head-revalidation-20260825.md`.
- [x] **P0-D-M4-VIEWPORT-BIND-GROUP-READINESS [gpu-backend, patches 0281+0283]:** diagnostic-first
  live sets prove the completeness failures are missing bindings, never extras: the low IDs are
  validation-pending backend push-constant UBOs and `256+` are validation-pending Tint sampler
  halves. Patch 0281 starts push allocation before module/layout readiness and queue-gates every
  provisional shared-sampler observer while preserving exact completeness. Driver hardware then
  proved those same shaders draw correctly after external invalidation, falsifying the old
  two-present settle stop. Patch 0283 now publishes accepted module/layout/render/compute readiness
  into bounded ordinary window updates; incomplete draws retry only inside the active episode and
  cannot rearm its 180-tick ceiling. Fifteen native/wasm behavior cases, 29 source mutations,
  native/wasm32 parity, canonical replay, the CAPTURE relink, and the fallback warning diagnostic
  are green. **Hardware closed 2026-08-26:** the driver-operated Apple M4 Pro paints the complete
  UI plus grid/axes/camera/shaded Cube/gizmo at 23–24 seconds with zero input, stays painted at
  idle, and produces the expected semantic pixel delta across MMB orbit with zero encode/present
  rejection. See `notes/p0-bind-group-readiness-20260826.md` and
  `notes/p0-redraw-recovery-20260826.md`.
- [x] **P0-H-M4-ORDERED-PRESENT-BOOT-CRASH [ghost-web, patch 0289] (`2971ea0`):**
  the driver isolated a 10/10 Apple M4 Pro boot abort in `BLI_strdupn()` to the
  `e3d284c7da0e` generation; `94cccc1` boots cleanly on the same rig, and `2c887da`/patch 0288 is
  the only runtime commit in that range. Patch 0288 moved the actual surface acquire/blit/submit
  out of GHOST's synchronous `swapBufferRelease()` boundary into a later backend queue callback.
  Patch 0289 preserves the rejected experiment in history but reverses its backend registration;
  the dead GHOST callback interface is removed and a fail-closed contract forbids all five seam
  markers. The final four-source 12-check/11-mutation contract, patch round-trip, canonical freeze,
  native/Wasm 42-contract GPU suite, split/capture producer self-checks, and locked relink/no-work
  are green. **RELINKED windowed-opt:** all five artifact identities are byte-identical to the
  driver-proven clean-boot `94cccc1` generation, including `.wasm.orig` 119,148,240 bytes at
  SHA-256 `aed9ba633f08b02d5fecaa461713cfbc2fabe880c0aad09ab3b88d037e47863a`.
  A fresh fallback windowed boot reaches first presentation in 5.578 seconds with zero page errors
  or Blender assertions; that run binds no hardware pixel/performance receipt. This closes the
  crash by exact rollback, not by weakening `BLI_strdupn()` or masking the assertion. P0-E remains
  open at its pre-0288 grey-resize baseline. See
  `notes/p0-boot-crash-ordered-present-rollback-20260827.md`.
- [x] **P0-E-M4-RESIZE-AREA-SURFACE-COHERENCE [gpu-backend, patches 0282/0290–0293, hardware-verified 2026-08-27]:** live tracing disproved
  a missing GHOST/WM resize: the event is processed and Blender relayouts every area. The persistent
  `WGPUTexture` wrapper adopts the new handle/extent in place, but pointer-identical
  `FrameBuffer::attachment_set()` leaves the default framebuffers' cached width/height stale.
  `sync_backbuffer()` now publishes the live extent to both caches on every activation. The exact
  shipping product shrinks 1280x720 -> 1100x640 and restores with WM/presentation progress and zero
  scissor, encode, submit, transaction, or device-loss errors on the local fallback adapter.
  **Hardware refinement 2026-08-26:** Apple confirms zero scissor/encode errors and a healthy
  renderer after shrink/restore, but the resized canvas remains blank at idle until the next input
  invalidates it. The applied-resize path now re-arms P0-D's ordinary bounded WindowUpdate episode
  after surface reconfiguration and the WM size event (`8744f4f`). The predecessor rejects at the
  missing publication; final native/Wasm behavior, 30 mutations, locked CAPTURE relink/no-work,
  inventory/self-check, and an exact-product fallback shrink/restore with 15/19 bounded redraw
  presentations and zero rejection/loss are green. **Not resolved:** the Apple rig must show idle
  semantic pixels after shrink and restore with no intervening input.
  **Hardware refinement 2026-08-27:** the predecessor passed only 5/8 identical clean shrinks; an
  applied resize could consume the tail of an older bounded episode while the replacement
  surface/backbuffer was still validating, and the later coherent commit published no redraw.
  `8f604ab` gives committed drawables a distinct monotonic generation that starts one fresh bounded
  episode without weakening ordinary shader/drop ceilings. Native/Wasm 19-case behavior,
  seven-source/39-mutation binding, exact CAPTURE preflight, and a live fallback shrink/restore are
  green with commit generations `0/1/2`, redraw presentations `18/18`, and zero rejection/loss.
  **RELINKED windowed-opt @ `8f604ab`:** `.wasm.orig` is 119,144,886 bytes at SHA-256
  `390062afea7c7117c40640b3259ae7328507c840ada80b62551f33ad992507f2`.
  Ten fresh local fallback-browser shrink/restore cycles are green against that exact generation:
  every run publishes commit episodes `0/1/2`, produces 18–19 redraw presentations per resized
  extent, and reports zero rejection/loss (`20260827T044246-1631630`). This is diagnostic only.
  **Hardware rejection 2026-08-27:** both `8f604ab` and its follow-up `d137387` score 0/10 on the
  Apple shrink bar with the same stable grey-overdraw signature. Direct counters prove each resize
  episode produces about 19 real presents, so missing presentation is falsified. Patch 0286 and
  `140f50b` now correlate every successful episode present with cumulative all/window draw counts
  plus exact target/viewport/scissor records for `overlay_background` and `OCIO_Display`, capped at
  24 lines per episode and 64 per process. The exact fallback product parses 37 coherent trace rows
  across shrink/restore (`20260827T062044-1706137`). **RELINKED windowed-opt @ `140f50b`:**
  `.wasm.orig` is 119,148,234 bytes at SHA-256
  `6730a8ad7b2050ca8873f6a73187556a74f4034e33e75e797248fe1d5ddb2f09`.
  **Backbuffer-lifecycle candidate 2026-08-27:** source tracing found that the persistent replacement
  backbuffer is adopted only from `WGPUContext::activate()`, while the single-window WM keeps the
  same drawable active and can skip activation across every bounded resize redraw. Patch 0287 and
  `94cccc1` extend Blender's existing Metal per-frame drawable reset to Emscripten WebGPU, forcing
  adoption before region draws without changing native WebGPU. Focused fail-first/final contracts,
  canonical replay, locked compile/relink/no-work, CAPTURE preflight, and exact-product fallback
  shrink/restore are green. **RELINKED windowed-opt @ `94cccc1`:** `.wasm.orig` is 119,148,240 bytes
  at SHA-256 `aed9ba633f08b02d5fecaa461713cfbc2fabe880c0aad09ab3b88d037e47863a`.
  **Trace-consumer hardening 2026-08-27:** `9f5037e` makes the exact-product repro parse all three
  emitted draw plans instead of accepting only the log prefix. Each resize episode now requires
  monotonic all/window draw counts, advancing `overlay_background` and `OCIO_Display` sequences,
  current direct-window target extents, and contained scissors. The exact relinked fallback product
  passes with 19/18 resize presentations and 37 fully checked trace rows; this strengthens the
  diagnostic only and binds no hardware pixels.
  **Ordered-present candidate 2026-08-27 (patch 0288):** direct Blender layout introspection
  falsifies the driver's proposed full-window substitution: `overlay_background=900x547` is the
  exact live `VIEW_3D` region after shrink, and correctly returns to 1048x621 after restore.
  The actual ordering gap is between encoding and submission. Browser error scopes leave the
  frame's draw/write submissions pending in `OrderedQueueScheduler`, while GHOST previously
  submitted the backbuffer-to-surface blit immediately outside that FIFO. The browser GPU context
  now registers the swap blit as an ordered operation after all prior frame work; surface acquire,
  encode, and submit remain synchronous within the eventual callback turn, and the standalone
  GHOST harness retains its immediate path. Fail-first/final source binding, native/Wasm queue
  ordering/cancel/retry, canonical replay, locked CAPTURE relink/no-work, exact inventory, producer
  self-check, and fallback shrink/restore are green. **RELINKED windowed-opt candidate:**
  `.wasm.orig` is 119,155,301 bytes at SHA-256
  `e3d284c7da0e11f09beada6c9a4b788044b0c8f9715dcee42bc80839d70c8238`.
  **Hardware acceptance producer 2026-08-27 (`4b6710a`):** the driver's calibrated ten-attempt
  semantic shrink check is now repository-owned and portable. It requires the current-spec
  hardware-adapter contract, exact pinned browser stack, the expected local and served CAPTURE
  generation, ten fresh 1280x720 -> 1100x640 contexts with zero post-resize input, 24-second
  bounded non-flat VIEW_3D pixels, zero page/WebGPU errors, and immutable receipt plus PNGs.
  Browser-free self-check is 26 positive/17 negative; a live Linux adapter-absent probe and a stale
  generation both reject before evidence allocation. This adds no pixel evidence and does not
  change the relinked candidate. See `notes/p0-window-resize-hardware-acceptance-20260827.md`.
  **Acceptance stability hardening 2026-08-27 (`4abbbb8`):** the live producer no longer accepts
  the first isolated non-flat shrink sample. It now requires three consecutive painted samples
  inside the unchanged 24-second bound, resets the streak on any stale frame, records the required
  streak in the receipt contract, and bases the final attempt verdict on the completed streak.
  The fail-first seam and final 31-positive/17-negative self-check reject both a one-frame recovery
  followed by stale pixels and an incomplete two-frame streak. REUSE and the pinned-container
  regression are green at their existing boundaries. The exact relinked candidate is unchanged.
  **Local ordering audit 2026-08-27:** the complete backend queue-mutation census still permits no
  direct `Submit`, `WriteBuffer`, or `WriteTexture` outside the ordered helpers; every async encode
  reserves its ticket before scope settlement, and the GHOST surface blit remains the sole separate
  submit behind that FIFO. The focused 14-mutation source contract and 43-contract native/Wasm
  ordering smoke are green at `20260827T083704-1814063` and `20260827T083708-1814093`.
  The relinked candidate is unchanged.
  **Trace/layout binding 2026-08-27:** the exact-product repro now parses Blender's live
  `VIEW_3D`/`WINDOW` region after each WM relayout and requires every `overlay_background` target
  and viewport to match it while remaining offscreen; `OCIO_Display` must remain a direct
  full-window draw. The relinked fallback product passes shrink/restore with eleven advancing,
  current, contained, VIEW_3D-bound traces and zero rejection/loss
  (`20260827T091755-1848021`). This executable boundary rejects the proposed full-window
  substitution for the correct 900x547 region and changes no runtime byte or pending candidate.
  **Candidate-preservation audit 2026-08-27:** the source/trace/hardware-producer self-checks and
  43-case native/Wasm ordered-queue suite remain green
  (`20260827T093320-1859811`/`1859812`/`1859815`, `20260827T093324-1859898`). A mandatory locked
  `blender_browser` invocation is a true no-op (`20260827T093347-1861874`), and all five CAPTURE
  identities still exactly match the documented `e3d284c7da0e` generation. No full-window extent
  substitution or relink was made while that exact candidate awaits Apple acceptance.
  **Fresh handoff reconciliation 2026-08-27:** direct review of the round-4 trace and failed Apple
  pixels shows correctly resized grid/gizmo content around the stale grey layer, reinforcing an
  ordering/stale-composite failure rather than an invalid 900x547 region target. The portable
  hardware-acceptance self-check remains green (`20260827T100818-1894660`), and pinned-container
  regression restores M0 6/6 while retaining the named later-tier boundaries
  (`20260827T101510-1899114`). The exact relinked candidate remains unchanged and hardware-pending.
  **P0-H supersession 2026-08-27 (patch 0289):** Apple hardware could not evaluate resize on the
  `e3d284c7da0e` ordered-present generation because it hard-aborted during boot on 10/10 attempts.
  That cross-frame callback seam is retired. The current CAPTURE generation is byte-identical to
  the hardware-known-clean-boot `94cccc1` artifacts (`.wasm.orig` `aed9ba633f08...`), which are a
  safe diagnostic baseline but already known not to clear P0-E's grey-overdraw pixel bar. The next
  P0-E candidate must start from this safe baseline and preserve synchronous GHOST presentation.
  **Completed-frame barrier candidate 2026-08-27 (`86d2ef6`, patch 0290):** the browser backend now
  appends a resize-only tail barrier to its existing ordered queue and GHOST withholds interim
  surface copies until all earlier frame submissions have settled. One synthetic WindowUpdate then
  performs the actual acquire/encode/submit synchronously inside `swapBufferRelease()` before the
  barrier releases later work, preserving P0-H's safe boundary. The 44-case native/Wasm model,
  44-mutation recovery contract, 31-mutation trace contract, canonical replay, producer
  self-checks, and REUSE are green. The exact fallback product completes shrink/restore with
  episodes `0/1/2`, presents `16/17/18`, exactly one ordered present per resize, two complete draw
  plans, and zero rejection/loss (`20260827T112204-1953387`). **RELINKED windowed-opt @ `86d2ef6`:**
  `.wasm.orig` is 119,152,777 bytes at SHA-256
  `2f45a8ed62ebeee3a9a80587ceca7e6918cb5c79c59f5a8fcd8219bb4934ffc6`.
  Ten further fresh-browser/fresh-X-server fallback shrink/restore cycles pass against those exact
  bytes with episodes `0/1/2`, one barrier present per resized extent, complete/current/contained/
  VIEW_3D-bound plans, and zero rejection/loss (`20260827T113859-1968370`). This is diagnostic
  lifecycle stress only and does not bind the hardware pixel gate.
  **Post-handoff safe-boundary audit 2026-08-27:** the focused source/trace contracts, 44-case
  native/Wasm queue suite, and 31-positive/17-negative hardware-producer self-check remain green;
  CAPTURE preflight and locked no-work retain exact `.wasm.orig` SHA-256 `2f45a8ed62eb...` while
  forbidding patch 0288's deferred GHOST present seam. This changes no artifact and supplies no
  Apple pixel evidence.
  **Window frame-tail call-graph audit 2026-08-27:** the resize source contract now distinguishes
  per-window `GPU_context_end_frame()` from backend-wide `GPU_render_end()` and binds the exact
  encode -> context-tail -> synchronous-GHOST-swap order. The fail-first contract exposed all
  three missing/misordered-tail mutations; the final 35-check/20-mutation verifier rejects them.
  This preserves the exact pending CAPTURE generation and adds no device-free pixel claim.
  **Exact-candidate handoff audit 2026-08-27:** the P0-H-forbidden deferred-present seam remains
  absent, the focused resize source contract and pinned 31-positive/17-negative Apple-producer
  self-check remain green, and all five CAPTURE hashes still match the `86d2ef6` generation,
  including `.wasm.orig` `2f45a8ed62eb...`. Authoritative container regression restores M0 6/6;
  no newer Apple evidence is present, so this audit changes no runtime byte or pixel verdict.
  **Integrated queue/barrier contract 2026-08-27 (`4be0219`):** the native/Wasm GPU parity suite
  now exercises `OrderedQueueScheduler` and `RedrawPresentBarrier` together, proving that prior
  frame work drains before barrier arrival, later-frame work stays held through the synchronous
  GHOST present, and queue release occurs only afterward. The exact CAPTURE candidate remains
  byte-identical; this closes a device-free contract gap and supplies no hardware pixel verdict.
  **Rejection-recovery integration 2026-08-27 (`0161808`):** the same shipping-type native/Wasm
  contract now covers a failed submission ahead of the barrier and a failed synchronous GHOST
  present. Both paths drain later-epoch work, clear present suppression, and leave the current
  resize episode retryable instead of bricking the renderer. The exact CAPTURE candidate remains
  byte-identical and still requires Apple 10/10 pixels.
  **Hardware receipt ingestion 2026-08-27 (`3168ee0`):** the acceptance producer now binds every
  canonical CAPTURE file and all 30 retained boot/baseline/shrink PNGs by byte count and SHA-256.
  A separate post-capture consumer re-hashes those bytes, decodes every PNG, replays the unchanged
  VIEW_3D semantic threshold, and requires the exact 10-attempt/three-stable-sample/zero-input/
  zero-error hardware contract with no missing or extra evidence. Producer self-check is 32/17;
  consumer self-check is 2/13 and rejects stale product/source/image identities, mutated or flat
  frames, and inventory drift. This changes no runtime byte and supplies no Apple pixels; the exact
  candidate remains `.wasm.orig` `2f45a8ed62eb...`.
  **Resize-drag supersession integration 2026-08-27 (`fcbf8d9`):** the shipping native/Wasm
  scheduler/barrier contract now covers a replacement extent arriving both before the old barrier
  reaches the queue head and after it is ready but before GHOST presents it. The obsolete
  completion fails exactly once, the replacement epoch drains, and a stale GHOST completion cannot
  retire the replacement barrier. A callback-transfer mutant fails at the new ready-supersession
  boundary; final 28-case output is byte-identical across runtimes. Runtime artifacts remain exact,
  so this strengthens the pending candidate without starting another Apple generation.
  **Hardware rejection 2026-08-27, round 6:** the driver-deposited ten-attempt result reports
  `passed=0`; all ten zero-input shrink captures are exactly 3,458 bytes, the established full-black
  signature, with zero page errors and zero WebGPU rejects. The legacy result file does not carry
  product hashes, retained PNGs, counters, or console traces, so it is not a canonical receipt and
  cannot identify whether the barrier omitted its surface copy or copied an empty backbuffer. It is
  nevertheless a hard pixel rejection: the current candidate must not be promoted. `1419943` now
  writes failure-only `NN-diagnostics.json` sidecars from the repository producer with pre/post WM
  tick, uncapped present, and redraw-episode counters plus all bounded resize/draw-plan/barrier
  lines. This changes no product byte and gives the next Apple run the missing discriminator before
  another runtime patch is attempted.
  **Frame-episode candidate 2026-08-27 (`5a48bb4`, patch 0290):** source tracing identifies the
  round-six all-black mechanism at the barrier's generation read. A replacement backbuffer can
  commit after a frame activates against the old drawable but before that frame reaches
  `end_frame()`; the old code labeled that old-backbuffer work as the completed replacement frame,
  then copied the untouched new backbuffer while holding the genuinely new-extent work behind the
  barrier. The window context now captures its episode at `begin_frame()` and schedules only when
  the same episode is still current at the tail; offscreen contexts are ineligible. The retained
  bounded trace snapshot remains printable if a slow barrier outlives the 180-tick capture episode.
  Fail-first/final source contracts, native/wasm32 queue integration, canonical replay, hardware
  producer/consumer self-checks, CAPTURE preflight, locked no-work, and REUSE are green. The exact
  fallback product reports ticks `246/519/607`, presents `16/17/18`, episodes `0/1/2`, one barrier
  present per extent, 18 complete/current/contained/VIEW_3D-bound traces, and zero rejection/loss
  (`20260827T141610-2103171`). **RELINKED windowed-opt @ `5a48bb4`:** `.wasm.orig` is
  119,152,955 bytes/136,772 defined functions at SHA-256
  `6fb76b7f760930385cb6be4b18f828c6fca1cfae02e65ce240e72ae78568cdfa`.
  **Frame-activation contract 2026-08-27:** the prior verifier allowed
  `WGPUContext::activate()` to omit `sync_backbuffer()`, so its frame-episode claim did not bind
  the actual replacement-texture adoption boundary. The fail-first mutation escapes at
  `20260827T143416-2117985`; the final 44-check/27-mutation source contract requires ordered
  activation/adoption and `wm_window_make_drawable()` before the context frame begins
  (`20260827T143522-2119087`). Native/wasm32 queue behavior and the draw-trace contract remain
  exact. This is contract-only: all five pending CAPTURE artifacts remain unchanged.
  **Atomic adoption candidate 2026-08-27 (`f5e1f19`, patch 0290):** the frame-episode fix still
  read texture/format/extent and generation through separate owner-lifetime entries, so an
  `AllowSpontaneous` resize commit could pair the previous texture with the replacement episode.
  GHOST now returns one lifetime-gated `BackbufferFrameSnapshot` and publishes its episode in the
  same protected callback that commits the replacement handle; `sync_backbuffer()` carries that
  episode through frame completion without a separate `begin_frame()` resample. Source 58/33,
  trace 35-mutation, native/wasm32 GPU integration, canonical replay, CAPTURE preflight,
  producer 37/17, consumer 2/13, fallback shrink/restore, and REUSE are green. **RELINKED
  windowed-opt @ `f5e1f19`:** `.wasm.orig` is 119,152,820 bytes at SHA-256
  `fbd46f816a418cf7b3c647df59f5b6ea7acf1f55ddcd66615f8780eedbe16e7c`.
  **Full-screen retry contract 2026-08-27 (`06732e5`):** the completed-frame source verifier now
  binds the ready barrier's synthetic `GHOST_kEventWindowUpdate` to Emscripten's ordered
  `NC_SCREEN | NA_EDITED` invalidation before the ordinary window notifier. The six-source
  contract reports 65 checks and rejects 36 mutations, including a missing screen notifier,
  wrong platform scope, and a chrome-before-screen ordering. The native/wasm32 GPU matrix,
  draw-trace self-check, and REUSE remain green. This is contract-only: the pending CAPTURE
  generation and its hardware-pixel boundary are unchanged.
  **Frame-tail trace binding 2026-08-27 (`131b153`):** post-barrier audit found the hardware
  diagnostic still sampled mutable draw plans during the later synthetic presentation frame.
  Those commands sit behind the ready barrier and are not the content being copied, so a failure
  log could falsely describe an unpresented frame as the completed backbuffer. `end_frame()` now
  stores one immutable draw-plan snapshot with the barrier; duplicate same-episode scheduling
  cannot overwrite it, supersession replaces it only with the newer episode, and completion or
  cancellation clears it. Fail-first/final source, 47-mutation redraw, 36-mutation trace,
  native/wasm32 GPU, canonical replay/self-check, patch reverse-check, CAPTURE preflight,
  producer 37/17, consumer 2/13, and REUSE are green. **RELINKED windowed-opt @ `131b153`:**
  `.wasm.orig` is 119,154,997 bytes at SHA-256
  `4b279e0e152fb2b0aca77701feac429090f3ae02920457d2e69ca801750d1b64`.
  The exact fallback shrink/restore reports ticks `246/526/619`, presents `17/18/19`, episodes
  `0/1/2`, one barrier present and one immutable trace per extent, and zero rejection/loss
  (`20260827T153238-2171940`). This corrects evidence attribution without claiming hardware
  pixels; no newer Apple result is present.
  **Failure-window diagnostic hardening 2026-08-27 (`58018fa`):** queue-tail completion alone
  cannot prove that no draw was abandoned before it created a queue entry. The hardware producer
  now opens its bounded diagnostic capture at the exact zero-input resize boundary instead of page
  load and retains post-resize bind-group completeness failures alongside the resize, immutable
  frame-tail, and barrier lines. Boot warmup cannot consume the 128-line failure budget, and a
  failing Apple sidecar can now show whether the admitted frame carried a known dropped draw
  without changing or relinking the candidate. Fail-first/final producer 40/17, independent
  consumer 2/13, syntax, CAPTURE preflight, locked no-work, and REUSE are green. All five product
  identities remain exact, including `.wasm.orig` `4b279e0e152f...`; this is diagnostic-only and
  supplies no pixels.
  **Diagnostic-priority hardening 2026-08-27 (`93fe263`):** the failure sidecar's fixed 128-line
  budget can no longer be exhausted by a post-resize bind-group warning storm before the decisive
  resize, immutable frame-tail trace, and barrier lines arrive. Mechanism lines displace the
  oldest completeness warnings without growing the cap; an all-mechanism buffer still fails
  closed. Producer self-check is 42/17, the independent consumer remains 2/13, the source/trace
  and native/wasm32 queue contracts are green, and the exact fallback shrink/restore reports
  episodes `0/1/2`, barriers `2`, immutable traces `2`, and zero rejection/loss. This changes no
  runtime byte; `.wasm.orig` remains `4b279e0e152f...`, and supplies no hardware pixels.
  **Commit-time barrier supersession 2026-08-27 (`f529943`):** source audit found a second
  replacement race after the old frame barrier becomes ready but before GHOST presents it. A
  newer coherent commit replaced the current backbuffer without immediately retiring that older
  barrier, so `swapBufferRelease()` could copy the new untouched texture under the old episode.
  The commit now returns and stores the replacement episode on the backbuffer before one atomic
  stale-barrier cancellation releases the queue. The fail-first target rejects the old API;
  final source 53-mutation and 48-case native/wasm32 GPU contracts, REUSE, CAPTURE preflight,
  producer 42/17, consumer 2/13, and profile self-checks are green. **RELINKED windowed-opt @
  `f529943`:** JS `5b6ed02286fd`, Wasm `71bfa062dada`, wasm.orig `fea3977234ce`
  (119,155,652 bytes), data `095d0ba748c3`, manifest `b45308a71527`. Exact fallback
  shrink/restore is green at ticks `246/523/617`, presents `17/18/19`, episodes `0/1/2`, one
  barrier/immutable trace per extent, and zero rejection/loss (`20260827T162824-2217652`),
  diagnostic only. Direct M4 remains hardware-pixel red; pinned-container regression restores M0
  6/6 and leaves the later named boundaries intact (`20260827T163137-2220736`).
  **Complete-frame admission candidate 2026-08-27 (`a8f6c43`, patches 0291–0293):** bounded
  diagnostics on the prior candidate showed every retry encoded roughly 331 advancing draws but
  the frame-tail snapshot retained only the final 23–25, always with `background=0`. The reset was
  incorrectly attached to `getBackbufferFrameSnapshot()`/context activation, which runs multiple
  times inside one WM window frame and erased the earlier `overlay_background` region draw before
  `end_frame()`. Episode adoption remains atomic in activation, but semantic frame facts now reset
  exactly once in the real `WGPUContext::begin_frame()`; later activations cannot erase them.
  `end_frame()` schedules only a same-episode snapshot containing the visible VIEW_3D offscreen
  background followed by its direct-window `OCIO_Display` composite, and GHOST withholds any
  unbarriered surface copy while that bounded resize episode is active. The synthetic WindowUpdate
  also carries a one-shot full-area redraw through `ED_screen_ensure_updated()` so relayout cannot
  consume its tags. Fail-first/final source, 61-mutation redraw, native/wasm32 integrated GPU,
  canonical 270-patch replay, REUSE, CAPTURE preflight, producer/consumer/profile self-checks, and
  locked committed-state no-work are green. **RELINKED windowed-opt @ `a8f6c43`:** JS
  `52a9a0257830`, Wasm `69b2f10ebac7`, wasm.orig `505702dbf41c` (119,157,853 bytes), data
  `095d0ba748c3`, manifest `10b181385e60`. The exact fallback product shrinks and restores at ticks
  `246/525/618`, presents `16/17/18`, episodes `0/1/2`, with two accepted complete-frame barriers,
  zero incomplete admissions, two exact VIEW_3D-bound traces, and zero WebGPU rejection/loss
  (`20260827T174508-2288582`). This proves the runtime mechanism only; direct M4 remains red for
  the absent exact-generation Apple binding (`20260827T175006-2293663`), and pinned-container
  regression restores M0 6/6 while retaining every named later boundary
  (`20260827T175010-2293716`).
  **Hardware closure 2026-08-27:** the driver bound the preceding generation to exact
  `.wasm.orig` SHA-256 `505702dbf41c...` and ran the standing Apple M4 Pro acceptance bar. Ten
  independent fresh contexts repaint the full grid, shaded Cube, camera, light, panels, and gizmo
  after a 1280x720 -> 1100x640 shrink with zero post-resize input (10/10, about 10.8–11.1 seconds,
  zero page errors/rejections). A harder six-cycle 1100x640/1280x720/900x550/1280x720/700x500/
  1280x720 stress run also repaints every extent without input, and a final orbit changes pixels.
  Commit `7ea0093` removes the untested successor and restores the exact accepted source tree; the
  locked relink reproduces all five accepted CAPTURE identities byte-for-byte, including
  `blender_browser.wasm.orig` 119,157,853 bytes at
  `505702dbf41ce0a9552f47e6a78ff9f10562c068c9471a35031835b33e9c062c`
  (`20260827T183234-2327996`). P0-E is closed. This is still a nonshipping CAPTURE generation:
  fresh success+terminal Apple profiles bound to this exact original remain mandatory before
  APPLY/public packaging. See
  `notes/p0-window-resize-recovery-20260826.md` and
  `notes/p0-window-resize-idle-redraw-20260826.md` and
  `notes/p0-window-resize-commit-redraw-20260827.md` and
  `notes/p0-window-resize-draw-trace-20260827.md` and
  `notes/p0-window-resize-backbuffer-reactivation-20260827.md` and
  `notes/p0-window-resize-trace-consumer-20260827.md` and
  `notes/p0-window-resize-ordered-present-20260827.md` and
  `notes/p0-window-resize-present-barrier-20260827.md` and
  `notes/p0-window-resize-commit-supersession-20260827.md` and
  `notes/p0-window-resize-complete-frame-admission-20260827.md`.
- [x] **P0-F-M4-POINTER-LOCK-PROMISE-REJECTION [ghost-web] (`34bad47`):** both sanctioned Apple
  CAPTURE scenarios otherwise pass but report `WrongDocumentError` page errors when trusted MMB
  orbit reaches Emscripten's discarded `requestPointerLock()` Promise. The first-script shell now
  calls the native method in the same activation stack, consumes its rejected Promise, emits one
  bounded diagnostic, and routes failure through GHOST's existing `pointerlockerror` retirement so
  orbit degrades to unlocked motion. Fail-first/final 28-mutation source coverage, two repeated
  real-worker Chromium rejections with zero page errors, the aggregate native/wasm32 matrix, locked
  CAPTURE no-work, and REUSE are green. P0-E's required C++ relink supersedes that generation; the
  current 119,142,918-byte `.wasm.orig` is exact at SHA-256
  `c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`. **Not resolved:** the Apple
  rig reran both CAPTURE scenarios with `pageErrors.length === 0`; both receipts are PASS and
  close the pointer-lock defect. Any later relink still requires fresh hash-bound profiles before
  APPLY, independently of P0-F. See
  `notes/p0-pointer-lock-promise-rejection-20260826.md`.
- [~] **P0-G-M4-WIDGET-SHADOW-DEFINED-RGB [gpu-shader, patch 0284] (`6145c46`,
  hardware-verified 2026-08-27):** Pre-fix Apple hardware screenshots showed correctly
  shaped/faded transient-widget shadows with bright white RGB.
  Diagnostic interception of the exact CAPTURE artifact disproved a missing sampler, incomplete
  bind group, wrong target clear, or wrong blend descriptor: this shader has no sampled resource,
  its sole 144-byte push UBO is bound, the target is transparent-black RGBA8, and the browser sees
  standard source-alpha blending. The remaining cross-backend hazard was the fragment result's
  split `vec4()` initialization followed by an alpha-only component write. Patch 0284 emits one
  complete `float4(0,0,0,alpha)` value. Six negative source mutations, the 20,258-entry canonical
  freeze, locked CAPTURE relink/no-work, and live interception of the baked WGSL are green at
  `.wasm.orig` SHA-256 `5a9d0944007313bed75ac3deaf24d3c48e443a423c93918dbb561abb76d0d65b`.
  **Original defect hardware-fixed; discovery reopened:** on the driver-operated Apple M4 Pro, a
  toolbar tooltip, the Shift+A Add-menu flyout, and the F9 Adjust Last Operation panel all render
  soft dark shadows with no white fill.
  Those cover the three originally filed acceptance surfaces. The post-v0.1.1 modal-artifact audit
  reopens final closure until a text tooltip and cascading submenu are checked. P0-I's instrumented
  modal extrusion contains no widget-shadow pass and is tracked separately rather than weakening
  the validated RGB fix. See
  `notes/p0-widget-shadow-defined-rgb-20260826.md`.
- [~] **P0-I-M4-MODAL-TRANSIENT-FRAME-COHERENCE [gpu-webgpu, driver,
  claimed_by: root, blocked-by: none]:** Apple v0.1.1 pixels show three thick retained
  constraint-guide trails during `Tab -> E -> move` and three stable overlapping grey HUD bars
  3-6 seconds after confirmation. The first live real-product diagnostic attests a genuine
  8-to-16-vertex extrusion, then exercises constrained move/rotate/scale, and falsifies the initial
  bind/extent hypotheses: all 35 six-vertex constraint draws use the live 1048x621 target/viewport,
  line width 2, distinct immediate buffers, shader-cache HITs, and zero completeness warnings/page
  errors. No widget-shadow pass occurs during extrusion (one appears later during move), separating
  its spindle artifact from P0-G. Five logical extrusion redraw clusters reach persistent
  attachments without an extrusion-phase surface copy; after confirmation, at least 160 widget
  draws and 73 window-region composites drain before the captured settle surface copy. The
  composites precede that copy in actual submit order, so a blanket "present overtakes all draws"
  claim is also rejected. Later constrained move/rotate/scale reach 10/10/13 surface copies after
  the backlog drains. **Candidate implemented (`8ce1a23`, patch 0295):** an ordinary-frame version
  of resize's barrier was tested and rejected locally because it suppressed almost every surface
  copy while preserving the artifact; it is fully removed. The lower-level gap was that browser
  command-buffer submits and buffer/texture writes entered the queue only after asynchronous
  `PopErrorScope` settlement, while synchronous GHOST presentation could already copy the shared
  backbuffer. Emscripten now issues those mutations in JavaScript call order and retains scopes only
  for later diagnostics; native Dawn remains validation-ordered and no async GHOST present callback
  was introduced. The exact fallback rerun has surface copies in all four modal phases, zero page
  errors/rejections, a thin guide, intact icons, and byte-identical clean 0.5/3/6-second settles.
  **Not resolved:** Apple must show thin constraint guides and clean six-second settles for
  extrude/move/rotate/scale, then retain boot/orbit and P0-E 10x resize/stress. The fallback trace
  binds no pixels. **Receipt gate corrected (`3056f7c`):** patch 0281's backend warning already
  named every shader and printed exact surviving/assembled/missing/extra sets, but the hardware
  capture accepted only four hard-coded shader names. The accepted success-r2 Apple log therefore
  ignored 18 real failures: `draw_resource_finalize` (1), `draw_visibility_compute` (9), and
  `draw_command_generate` (8), each missing binding 1. Both capture scenarios now aggregate and
  fail on every incomplete shader signature, including arbitrary future names and malformed
  diagnostics. **Pending-resource candidate implemented (`af0ebe3`, patch 0296):** the three
  signatures bind lazily allocated draw-manager buffers, but storage/uniform bind previously
  returned before recording the slot while browser allocation validation was pending. Bind intent
  now survives that window; assembly carries exact pending IDs separately and accepts `Pending`
  only when they account for every missing surviving ID with no live/pending extra. Every genuine
  missing/extra set retains the hard warning. Pending draws remain bounded drops, while successful
  buffer publication emits exactly one redraw-readiness edge (rejection emits none), avoiding an
  indefinitely rearmed recovery ceiling. Focused native/Wasm buffer and full pipeline parity,
  canonical replay, final CAPTURE relink, and a zero-page-error/zero-hard-warning fallback modal
  run are green. This makes the receipt honest and provides a hardware candidate; it does not
  hardware-close P0-I. **Typed-geometry candidate implemented (patch 0297):** the cumulative
  10-orbit/10-pan/10-zoom diagnostic first proves that the exact Modeling-tab coordinate works,
  then binds screenshots to Blender-native workspace/region/Cube state. Before the candidate it
  emitted six `gpu_shader_3D_polyline_flat_color` hard drops with surviving `[0,1,2,3]`, assembled
  `[3]`, and missing `[0,1,2]`. Those three IDs are the polyline vertex/index storage resources:
  their typed frontends repeated patch 0296's ordering bug by returning before recording SSBO
  intent while first-use allocation was pending. Vertex and index binds now preserve that exact
  pending intent. The relinked unchanged stress sequence has zero hard warnings/page errors,
  coherent semantic pixels through Frame Selected plus final orbit, and a stable 3-to-6-second
  settle. The predecessor's reported 0/8 post-stress workspace result was investigated separately
  as P0-J: it combined a real missing initial-window-activation defect with an automation tooltip
  artifact, and the corrected candidate now passes 9/9 state-changing transitions device-free.
  That does not hardware-close either item. Apple pixels remain required for both the filed transient
  artifact battery and closure. Current-generation acceptance additionally requires
  `incompleteBindGroups=[]`. **Buffer-texture sibling candidate implemented (patch 0298):** the
  final binding-frontend audit found `WGPUVertexBuffer::bind_as_texture()` still discarded intent
  while its first-use primary allocation was pending. Float1-3 sampler buffers cannot simply bind
  that primary resource because their surviving layout requires a separately expanded float4
  backing. The context now records the eventual correctly shaped buffer plus a distinct pending
  dependency, classifies only that exact mapped ID as `Pending`, and still requires the eventual
  buffer to be valid before emitting a bind-group entry. Rejection or a genuinely absent final
  backing remains hard `Incomplete`; the completeness gate is unchanged. Fail-first/final exact
  native/Wasm behavior, source mutations, canonical replay, affected archive build, CAPTURE relink,
  and the 41-step fallback interaction replay are green with an empty hard-warning census. The
  broader buffer suite's adjacent stale `readback submit ordering` expectation is now reconciled:
  native validates before submit while browser Wasm submits in-turn and joins later diagnostics;
  both paths require balanced scopes and exactly-once completion. **Staged-update sibling candidate
  implemented (patch 0299):** the newly reachable aggregate case then exposed a real fail-closed
  gap: browser same-turn copy submission bypassed the staging resource's scheduler gate, so its
  payload transaction could accept independently of a rejected non-null staging-buffer creation.
  Resource and command validation now form one two-leg completion join; either rejection retains
  the exact bytes for a clean retry without delaying browser submission. The aggregate native/Wasm
  suite, canonical replay, affected object build, CAPTURE relink, and unchanged cumulative/modal/
  resize fallback diagnostics are green. **Auxiliary-cache readiness candidate implemented (patch
  0300):** a full audit then found 13 persistent first-use caches whose callers abandon work while
  browser validation is pending but whose successful publication emitted no redraw edge: seven
  context dummy/blit/upload producers, five framebuffer attachment/clear producers, and the
  triangle-fan compute pipeline. Every producer now requests one coalescible bounded retry only
  after a non-null accepted publication; pending work, rejection, null publication, and cache hits
  emit none. An 18-mutation census, seven-case native/Wasm behavior contract, canonical replay, and
  the three real windowed object builds are green. This is a device-free candidate for partial or
  stale first-use frames, not Apple pixel closure. The exact relinked patch-0300 candidate is
  `.wasm.orig` SHA-256 `32881203c7ba` (118,977,585 bytes). Neither device-free result
  hardware-closes P0-I/J. **Buffer-texture readback-readiness candidate implemented (patch
  0301):** float1-3 sampler buffers have a second first-use window after their primary allocation
  becomes valid: the browser cache begins `MapAsync`, returns no bytes, and formerly gave the
  frontend neither an exact Pending classification nor a retry after settlement. The read path now
  reports that dependency, the context retains the eventual expanded float4 binding, and only this
  opted-in successful cache settlement requests one coalescible retry. Default/exact-ticket
  readbacks, failure, cancellation, and cache hits emit none. Distinct pending shader/set
  signatures are logged once under a 128-signature ceiling; the hard missing/extra gate remains
  unchanged. Source mutations, canonical replay, exact native/Wasm buffer parity, affected archive,
  CAPTURE preflight/relink/no-work, the final 41-step fallback interaction replay, modal retry, and
  shrink/restore recovery are green with zero hard warnings/page errors. The exact candidate is
  `.wasm.orig` SHA-256 `2ba96011987aeeca87b3ab84052e3dcdeaf7098eaf5809c268399ae9d69b0d6f`
  (118,983,520 bytes). A strengthened camera canary caught one earlier fallback run retaining stale
  pixels until the next input despite native CAMERA state; the instrumented final run emitted no
  pending/readback signature, so that observation is not attributed to patch 0301. **Suppressed-
  present settlement candidate implemented (`868bd86`):** two clean fallback loads then reproduced
  that stale camera frame deterministically. The draw-drop and resize-barrier generations stayed
  unchanged while every synthetic WindowUpdate reached a full WM draw, proving the loss was after
  encoding. `presentBackbuffer()` silently returned while its prior asynchronous validation scopes
  were pending; the prior surface command had already sampled the older persistent backbuffer, and
  settlement neither presented the newer retained frame nor scheduled a retry. A small latch now
  coalesces every suppressed swap and, from the completion's fresh browser turn, synchronously
  acquires/submits one new surface blit of the latest backbuffer. Only a failed direct start falls
  back to the bounded redraw path; device loss clears both latch states. This preserves the
  hardware-safe synchronous surface boundary and does not revive rejected patch 0288's deferred
  cross-frame callback. Exact native/Wasm latch parity and source ordering are green. The cleaned
  relink passes the complete 41-step fallback battery twice, including native CAMERA pixels before
  the cancelled no-op, 9/9 workspaces, two pixel-exact known poses, move/undo, empty hard-warning
  census, and zero page errors; modal four-operator and shrink/restore regressions also pass. The
  exact candidate is `.wasm.orig` SHA-256
  `96cb55a627071c9cbcfcdeb6926c79d78bddf0dafb972eb437f37bee2f73afe8`
  (118,983,629 bytes). **Rapid suppressed-present canary implemented (`56bd212`):** the same
  producer now drives two back-to-back Numpad3/7/0/1 native view cycles without waiting for
  intermediate pixel settlement, then requires the final known pose to settle within 12 seconds,
  hold for three seconds, advance both validated presentation and input-retry generations, and
  match a third same-pose region diff. The exact fallback generation passes eight trusted DOM/native
  transitions, settles in 5,037 ms, and has zero changed pixels in all three known-pose canaries.
  No product byte changed. **WM-owned settlement replay candidate implemented/pending hardware:**
  exact suppression/replay telemetry then reproduced one stale camera frame despite three
  callback-side direct replays. Patch 0302's 12-stage dashed-line witness proved the camera draw
  encoded and validated with zero bind/pass/rejection failures; only the retained surface image was
  stale. Settlement now publishes a distinct generation that is consumed only after an ordinary
  WM WindowUpdate passes any resize barrier, keeping surface acquire/submit inside the synchronous
  swap boundary and outside the generic heartbeat ceiling. Two independent unchanged fallback
  batteries pass with identical camera/no-op pixels, positive rapid suppression/WM-replay deltas,
  three exact known poses, and zero hard warnings/page errors; shrink/restore remains green. Two
  modal-probe attempts hit the same context-close blocker at `armed-probe-8` and are recorded, not
  promoted. **Unified modal/overlap-present candidate implemented/pending hardware:** a fresh
  dedicated modal run falsifies the context close as a current deterministic blocker, and the
  exact cumulative producer now owns `E Z` confirm plus constrained move/rotate/scale, native
  topology `8 -> 16`, 0.5/3/6-second settle captures, and a structural detector for the filed
  full-width neutral bar. That extension found the WM replay candidate could still suppress 13
  newer swaps while one popped error-scope callback lagged and retain a stale camera frame.
  One transaction now owns diagnostic scopes while overlapping WM frames submit their surface
  copies unscoped in-turn; settlement retains one final scoped WM replay. The final 53-step
  fallback battery passes all same-pose and modal checks, with zero wide retained rows, hard
  completeness warnings, or page/lifecycle errors. Exact `.wasm.orig` is `5fea52ef8bc9`
  (118,985,639 bytes). Apple must rerun it as a repeated hardware series; device-free pixels
  still cannot close P0-I/J. See
  `notes/p0-modal-extrude-frame-coherence-20260827.md` and
  `notes/p0-cumulative-input-window-activation-20260828.md`.
- [ ] **P0-J-M4-CUMULATIVE-WORKSPACE-HIT-TEST [ghost-web/input, driver, blocked-by: none]:**
  the exact Modeling-tab coordinate changed Blender's native active workspace before navigation,
  while the original post-stress automation observed 0/8 later transitions. **Initial-activation
  candidate implemented/pending hardware:** DOM capture and a pass-through Blender modal probe
  proved worker-batched button presses were assigned later queued cursor coordinates. The shell had
  already focused the canvas when callbacks registered, so `browser_focus_active_` was seeded true
  without emitting `GHOST_kEventWindowActivate`; Blender kept `wmWindow::active == 0` and every
  button-down re-queried GHOST's later global cursor instead of consuming the ordered cursor event.
  `createWindow()` now publishes the seeded activation only after window-manager admission, and
  button events no longer overwrite mouse-move-owned cursor state. The original 0/8 result was also
  amplified by waiting on an already-active Layout no-op until its tooltip consumed the next click;
  the corrected fail-closed diagnostic dismisses transient tooltips, waits for each real workspace
  construction, and requires nine native transitions plus exact DOM/GHOST press coordinates. The
  relinked fallback product passes 9/9 after 10 orbit + 10 Shift-pan + 10 zoom, stable settle plus a
  pixel-changing final orbit, and zero hard warnings/page/lifecycle errors. Integrated focus,
  pointer, lifecycle, and WebGPU/GHOST regressions are green. **Bounded input-recovery candidate
  implemented (`8f2e09b`):** accepted move, supported button, nonzero wheel, and key callbacks now
  publish the existing redraw-retry generation, never the resize-only drawable episode. Queued
  callbacks coalesce at the WM poll; active bursts retain their hard ceiling, while the first input
  after a completed burst starts one fresh bounded WindowUpdate retry. A 9-mutation bridge contract,
  68-case native/Wasm model, exact cumulative fallback battery, four-operator modal pass, and
  shrink/restore regression are green. This is resilience behind the initial-activation fix, not a
  hardware closure or a substitute for the pending-resource fixes. **Exact hardware producer
  implemented (`f63dc77`):** the same stress lane now rejects non-Apple execution, fallback/software
  adapters, stack drift, stale local/served CAPTURE generations, and pre-existing evidence output
  before allocation. It restores one deterministic native VIEW_3D pose before/after cumulative
  interaction and after the final orbit, compares real full-region plus viewport-header/toolbar/
  Outliner/workspace-label pixels, and requires a post-stress native `G X 2` plus undo. The exact
  fallback product passes with pixel-exact VIEW_3D/detail regions, 9/9 workspace transitions,
  move/undo, and zero hard warnings/page/lifecycle errors; this binds no hardware pixels.
  **Original-freeze replay v2 implemented (`c8ef725`):** before the broad
  battery the same producer now executes the driver's exact Numpad view/select/deselect/orbit/
  click/transform/undo/orbit isolation, binds every action to settled native state plus pixels,
  samples the shipped input-retry generation, and requires both orbits to repaint within the
  bounded recovery window. Hardware keeps a strict trusted viewport Cube selection and five-second
  input receipt; the software-only failed-pick fallback is explicitly canceled and returns to
  Cube-only selection with a coordinate-checked Outliner click. The exact fallback CAPTURE product
  passes 41 steps, both orbit recoveries, 9/9 transitions, two exact same-pose comparisons, and an
  empty all-shader census. **Full input-tail correction implemented (`fe7bbf3`):** the original
  input hook shared resource-readiness semantics, so input arriving on tick 179/180 could spend the
  old burst's final tick and leave its dropped frame stale. Accepted input now advances a distinct
  generation plus the existing aggregate diagnostic counter; callbacks coalesce at the WM poll and
  restart one complete bounded tail, while resource readiness retains its active-burst ceiling and
  ordinary input remains outside resize's drawable barrier. The fail-first tick-179 case, 70-mutation
  source contract, 68-case byte-identical native/Wasm model, exact original-freeze/cumulative replay,
  modal four-operator settle, resize recovery, loader-content adjacency, committed-state relink, and
  REUSE are green. The exact candidate is `.wasm.orig` SHA-256 `dbfad903a2be` (118,978,050 bytes).
  **Repeated-hardware gate implemented (`3d1d799`):** the analyzer now accepts an explicit
  `--hardware-series` of at least two immutable diagnostics, reruns the complete single-run contract
  for each, and rejects duplicate evidence paths/run labels/timestamps or any producer, pinned
  browser stack, accepted Apple adapter, local/served generation, or five-file product-identity
  drift. The 3-positive/49-negative self-check and existing single-run diagnostic remain green.
  This strengthens the already-required repeated Apple closure without binding a receipt itself;
  the then-current CAPTURE product and `dbfad903a2be` identity were unchanged. **Latest-frame
  presentation candidate (`868bd86`):** precise fallback tracing found the remaining camera/freeze
  seam below the input tail: full WM draws completed while `presentBackbuffer()` discarded their
  swaps behind one still-validating surface transaction. Settlement now coalesces and directly
  presents the retained newest backbuffer in its fresh browser turn, with bounded redraw only as a
  failed-start fallback. The final committed generation passes the 41-step original-freeze plus
  cumulative battery (98 states, 292 presents, 9/9 workspaces, two exact same-pose comparisons,
  move/undo, no hard warning/page error), the modal four-operator analyzer, and coherent
  shrink/restore. It is bound by `.wasm.orig` `96cb55a62707` (118,983,629 bytes).
  **Rapid hardware canary implemented (`56bd212`):** two immediate Numpad3/7/0/1 cycles now stress
  the coalesced suppressed-present path and bind eight trusted DOM inputs to strictly increasing
  native transitions, advancing presentation/retry counters, a bounded held final frame, and a
  third same-pose pixel comparison. The unchanged fallback product passes; this is a stronger
  pending-hardware candidate, not closure. Closure still requires repeated
  trusted Apple input on the original total-freeze and navigation/workspace sequences, with
  scene/text pixels intact and P0-D/E/F plus P0-I regressions green. **WM-owned replay correction
  implemented/pending hardware:** positive per-path counters exposed that callback-side direct
  replay still retained a stale camera frame in one repeat even though its dashed draw encoded and
  validated. Settlement now queues a distinct, non-heartbeat-capped WM WindowUpdate and consumes it
  only after barrier admission. Two fresh fallback runs pass the full 43-step battery with exact
  camera/no-op and all same-pose pixels, positive rapid suppression/replay deltas, and empty hard
  warning/page-error censuses. **Overlapping-validation correction implemented/pending hardware:**
  the unified modal extension reproduced a remaining stale camera frame while presents,
  suppression, and WM replay all advanced. Error-scope results can lag multiple WM frames after
  the scopes have already been popped; those callbacks no longer block later surface copies.
  Overlapping WM presents submit unscoped in their own synchronous turns, and the owning scoped
  transaction still schedules one final WM replay. The final exact 53-step/150-state fallback run
  passes 9/9 workspaces, all known-pose checks, modal topology and settle checks, move/undo, and
  empty hard-warning/page-error censuses. CAPTURE `.wasm.orig` is `5fea52ef8bc9`
  (118,985,639 bytes). **Same-generation hardware gauntlet implemented/pending hardware:** the
  composer reruns at least two complete Apple interaction/modal consumers, rehashes every captured
  PNG and exact inventory, invokes the independent 10-attempt P0-E consumer, and requires the
  current producer, all five product bytes, local/served CAPTURE generation, pinned browser stack,
  and accepted Apple adapter to match across both evidence families. Its 3-positive/23-negative
  self-check is green; no product byte or hardware verdict changed. P0-I/J closure now requires
  that composed PASS rather than separately described evidence that could mix generations.
  **Rapid-drain discriminator implemented (`32692ee`):** the driver's deterministic screenshot
  sequence samples actions only 350 ms apart, which can preserve a genuine WM-worker backlog as
  identical frames without establishing permanent liveness loss. A focused producer now preserves
  that exact Numpad/select/deselect/orbit/click/orbit/move cadence, then waits at most 12 seconds and
  requires pixels, WM ticks, validated presents, and the input-redraw diagnostic generation to all
  advance; one independent recovery orbit must satisfy the same predicate. Apple mode rejects any
  absent, fallback, incomplete-info, or software-token adapter, and a timeout preserves every
  sample, the final counters, pointer-lock diagnostics, and native GHOST event tail. The exact
  fallback product passes; its independent recovery orbit took 6,555 ms, proving only that the
  350 ms cadence is not a sufficient drain verdict. This changes no runtime byte and does not
  contradict or close the driver's 5/5 Apple observation. Hardware must run the discriminator and
  the existing same-generation gauntlet before P0-I/J can close. **Terminal GHOST-edge
  discriminator implemented (`5cad54c`):** the first focused producer could falsely accept an
  earlier click while the opposite orbit and G/confirm remained queued, and a pass-through Blender
  modal probe cannot observe releases consumed by an active rotate operator. Transition-only
  worker-side button/key counters plus a held-button mask now require both complete MMB pairs, both
  complete left-click pairs, G down/up, a cleared left/middle mask, clean modal stack, changed
  pixels, and advancing WM/present/retry counters before action drain can pass. The independent
  recovery orbit is separately baselined. The relinked fallback product reproduces all five
  byte-identical rapid frames, then drains after 5,725 ms with balanced GHOST edges and repaints a
  fresh orbit after 1,744 ms with zero page/lifecycle errors. This is diagnostic software evidence,
  not a hardware closure; Apple retains the strict 12-second bound and must run this exact
  generation plus the composed gauntlet. **Native-state drain gate implemented (`f27df7e`):** the
  terminal-edge predicate could still false-pass on a tooltip or unrelated redraw after every
  callback arrived. Apple action drain now additionally requires Blender-native Cube selection, a
  second-orbit view-rotation transition, and a confirmed `G` location change; the independent
  recovery orbit must change rotation again without moving Cube. The hardware-only semantic gate
  leaves SwiftShader's known failed GPU-pick lane explicitly diagnostic. The exact fallback control,
  33-mutation source contract, and integrated native/Wasm suite are green without changing or
  relinking the current product. Apple must run this strengthened discriminator against exact
  `.wasm.orig` `b326a3be5331` before P0-I/J can close. **Terminal-redraw admission discriminator
  implemented/relinked (`8177420`):** the next filed hypothesis is now split at its real boundary.
  Completed button/key/wheel callbacks publish a terminal input generation; the WM records that
  generation only after its synthetic `WindowUpdate` passes the resize barrier, while bounded
  terminal/admitted/withheld lines record the unchanged resize-episode generation. The exact
  fallback replay admits every terminal (`50/50`, recovery `63/63`) with episode fixed at 1,
  advancing pixels/presents, and zero page/lifecycle errors. Thus ordinary input does not call the
  resize-only episode, but the source and fallback both prove its distinct bounded retry is rearmed
  and admitted; Apple must now determine whether the deterministic freeze is above or below that
  admission boundary. CAPTURE `.wasm.orig` is `1caec08e9582` (118,987,074 bytes). Device-free
  resize source/trace remain green, but two live fallback runs retain a RED legacy present-churn
  check (`5/2`, `5/4`) despite two coherent barriers and zero WebGPU rejects/loss; no P0-E
  regression is claimed green until Apple pixels rerun. **Terminal-present discriminator
  implemented/relinked (`ebb602a`):** the admitted generation is now sampled before each browser
  surface transaction and published only after that transaction validates cleanly. Monotonic
  publication prevents a delayed scoped callback from moving the evidence behind a newer unscoped
  frame. The exact producer now requires `presented >= terminal` in addition to delivery,
  admission, native state, and changed pixels. Native/wasm32 behavior covers newer, duplicate, and
  out-of-order callbacks. The fallback control drains at terminal/admitted/presented `51/51/51`
  and recovers at `64/65/65`, but this binds no Apple pixels. CAPTURE `.wasm.orig` is
  `f396b0ea7950` (118,987,372 bytes). Apple must run this exact generation: terminal > admitted
  locates the loss at the barrier, admitted > presented locates it between WM admission and clean
  surface presentation, and matching generations with stale native state/pixels puts the defect
  downstream. **WM-dispatch discriminator implemented/relinked (`9942dd9`):** admitted previously
  meant only that `processEvents()` pushed a synthetic WindowUpdate; a later unrelated frame could
  sample that generation without proving Blender's WM consumer ever processed the event. Each web
  WindowUpdate now owns its input generation, and a GHOST consumer installed after Blender's WM
  consumer publishes a distinct monotonic dispatched edge. Surface validation carries only that
  dispatched edge, and the rapid producer requires terminal/admitted/dispatched/presented in order.
  The exact fallback retains the five 350 ms samples, then drains in 6,579 ms at `49/49/49/49` and
  repaints an independent orbit in 1,412 ms at `62/62/62/62`, with balanced input and zero page/
  lifecycle errors. Exact CAPTURE `.wasm.orig` is `31c7a6bab76a` (118,988,169 bytes). Apple must run
  this generation: admitted > dispatched isolates GHOST/WM dispatch; dispatched > presented
  isolates surface presentation; matching generations with stale native state/pixels places the
  loss downstream. **Bounded input-burst candidate implemented/relinked (`5721ba7`):** paired
  input/aggregate retry deltas no longer misclassify every motion sample as new asynchronous GPU
  readiness. The first input after idle opens one bounded recovery burst, nonterminal motion inside
  that burst neither injects another full-screen update nor resets its hard ceiling, and a distinct
  button/key/wheel terminal edge restarts exactly one complete coalesced tail. Two exact fallback
  runs drain in 5,545/5,566 ms and repaint an independent orbit in 2,513/1,551 ms with terminal,
  admitted, dispatched, and presented generations converged and zero page/lifecycle errors; the
  53-step cumulative/modal battery also passes 9/9 workspace transitions and its full warning
  census. Exact CAPTURE `.wasm.orig` is `aa374938f2b8` (118,988,326 bytes). The software fallback
  binds no pixel verdict, and its resize probe still fails only the filed legacy `5/2` present-churn
  heuristic despite coherent barriers, so Apple must run the exact freeze discriminator and
  same-generation gauntlet plus P0-E regression. **Frame-bound presentation discriminator
  implemented/relinked (`430c8f5`):** `presentBackbuffer()` no longer samples a newer global
  dispatched generation after Blender's frame has already been encoded. `swapBufferAcquire()`
  binds the generation immediately before `GPU_context_begin_frame()`, and resize-barrier snapshots
  retain the completed frame's generation until its delayed surface transaction validates. Native/
  wasm32 behavior proves later dispatch cannot relabel an older frame, and the exact fallback drains
  at terminal/admitted/dispatched/presented `49/49/49/49` then recovers at `62/62/62/62`, with
  `frame-bound=1`, balanced input, and zero page/lifecycle errors. The exact 53-step cumulative/
  modal battery also passes 9/9 workspaces, three same-pose comparisons, and an empty warning/error
  census. CAPTURE `.wasm.orig` is
  `025682159147` (118,988,932 bytes). This changes evidence provenance only; Apple must still run
  the exact deterministic freeze and same-generation gauntlet plus P0-E regression. P0-I/J remain
  open. **Strict VIEW_3D content-presentation discriminator implemented/relinked (`d90aee1`):** a
  clean frame-bound surface copy can still carry a persistent backbuffer that never encoded the
  input's real 3D region. A separate bounded trace now follows the exact dispatched input
  generation through successful overlay-background, stock-grid, and final OCIO-display encoding;
  only validation of that surface transaction advances `contentPresented`. The focused producer
  requires this stronger edge in addition to terminal/admitted/dispatched/presented. The exact
  Xvfb SwiftShader control reaches action-drain `51/51/51/51/51` and recovery
  `64/65/65/64/64` across terminal/admitted/dispatched/presented/content-presented with balanced
  input, episode 1, and zero page/lifecycle errors. CAPTURE `.wasm.orig` is
  `f6a096b53f13` (118,990,678 bytes). This is diagnostic provenance, not a redraw-policy change or
  a software pixel receipt; Apple must run this exact generation and the composed 10/10 gauntlet.
  **Content-stage miss classifier implemented/relinked (`1355506`):** a clean surface validation
  that still lacks the strict input-content receipt now emits one bounded line per distinct stage
  transition, including the exact input/terminal/trace generations, completeness mask, draw counts,
  and background/grid/display/last-pass identities. The six mask bits are derived from the unchanged
  strict predicate, so this adds diagnosis without accepting a weaker frame. Native/wasm32 behavior
  covers background-only `0x09` and complete `0x3f`; source mutations remove the predicate or miss
  line fail closed. The exact fallback replay converges at terminal/admitted/dispatched/presented/
  content `49/49/49/49/49` and recovery `62/62/62/62/62`, with no miss line on its successful path.
  CAPTURE `.wasm.orig` is `e5629d6d0867` (118,991,633 bytes). Apple must run this generation: a
  timeout's first `content-miss` line now distinguishes absent background, grid, display, ordering,
  or trace-generation provenance in one hardware pass. **Content-retired input-tail candidate
  implemented/relinked (`b4c04d1`):** the strict content edge then exposed avoidable queue pressure:
  every terminal input retained all 180 ticks of synthetic full-screen recovery even after that
  exact generation had already encoded and presented background + grid + final display. The shared
  recovery helper now retires only that input-owned tail on the exact content receipt; a resize,
  lazy-resource readiness edge, or any dropped draw clears input ownership and retains the original
  bounded generic burst. The 101-case native/wasm32 model and 79-mutation source contract are green.
  The exact fallback sequence converges at terminal/admitted/dispatched/presented/content
  `49/49/49/49/49`, then repaints its independent recovery orbit in 748 ms; the 53-step battery
  passes 181 native states, 724 presents, 9/9 workspaces, three same-pose checks, and zero hard
  warnings/page errors. CAPTURE `.wasm.orig` is `e61df1b64f7b` (118,991,717 bytes). This is a
  hardware candidate, not closure: Apple must run the exact deterministic freeze 10/10 plus the
  same-generation composed P0-D/E/F/I gauntlet. **Slow/sparse discriminator implemented
  (`adb8e79`):** the prior producer sampled a 350 ms burst, while the filed Apple claim now describes
  one isolated orbit with no later input queued. `BW_P0_SPARSE=1` leaves 650 ms between the prelude
  inputs, then withholds all later input until the first orbit reaches balanced GHOST delivery,
  WM admission/dispatch, validated surface presentation, strict same-generation VIEW_3D content,
  changed native view state, and changed pixels; it repeats that contract for a second isolated
  orbit and retains every 250 ms stage sample. The unchanged fallback product passes at terminal/
  admitted/dispatched/presented/content `29/29/29/29/29` then `40/40/40/40/40` in 317/1,606 ms.
  The unchanged rapid mode still shows five immediate identical frames but drains fully in 8,425 ms,
  proving that immediate identity alone is not a liveness verdict on this lane. No runtime byte or
  receipt changed. Apple must run this exact sparse discriminator; its timeout timeline now locates
  delivery vs WM vs surface vs content vs native-state/pixel loss before any seventh runtime patch.
  **WM-worker focus/grab discriminator implemented/relinked (`3f2a13c`):** the sparse drain now also
  requires browser focus active plus inactive pointer lock, disabled requested grab, and disabled
  effective GHOST grab, read through shared atomics published only by the owning worker paths. The
  exact fallback candidate reaches those settled values on both isolated orbits at generations
  `29` and `40`; CAPTURE `.wasm.orig` is `61d81e10c406` (118,992,442 bytes). This is read-only
  diagnosis, not an input/redraw fix or hardware closure. Apple must run this generation: stale
  focus/grab state isolates worker callback retirement, while settled ownership with later stale
  native state/pixels moves the defect downstream. **WM-queue input discriminator implemented/
  relinked (`1fcd7ba`):** callback delivery still did not prove that the real MMB press, motion, and
  release entered Blender's WM queue; the prior `dispatched` edge covered only the synthetic redraw
  event. A GHOST consumer registered after Blender's consumer now publishes separate WM-queue
  button/key/motion counters and held mask, and both sparse orbits require callback and WM stages to
  balance before any later surface/native/pixel stage may pass. The 30-mutation source contract,
  104-case native/wasm32 behavior model, real Wasm objects, and exact isolated-X control are green;
  the control reaches MMB `1/1` then `2/2`, motion `10` then `20`, both masks zero, and drains in
  421/1,291 ms. CAPTURE `.wasm.orig` is `838e6312ef3d` (118,993,252 bytes). This changes diagnosis
  only. Apple must run this exact generation: callback > WM localizes loss before Blender's queue;
  balanced WM with a retained navigation modal localizes operator completion; balanced/clean WM
  plus stale native state or pixels moves the loss downstream. **Selection stream continuation
  implemented/relinked/pending hardware (patches 0304/0305):** the next exact trace found that the
  orbit retired normally, but the following click's `VIEW3D_OT_select` opened a modal error popup
  after `GPU_READBACK_ERROR_SOURCE_UNAVAILABLE`; that popup captured every later action and created
  the apparent total freeze. The one-draw selection output now preserves `GPU_USAGE_STREAM`, uses
  its same-epoch provisional allocation through update/readback, and retains ordinary input in a
  bounded FIFO until the valid asynchronous map completes. The focused producer rejects any
  selection-readback report and requires exact rotate retirement. Rapid and slow/sparse software
  controls now have zero selection/page/lifecycle errors and retire the queued recovery orbits;
  canonical replay, mutation checks, real Wasm relink, CAPTURE/profile/gauntlet self-checks, and
  REUSE are green. CAPTURE `.wasm.orig` is `cccb4f50e28a` (118,995,705 bytes). This is the first
  candidate aimed at the observed error source, not hardware closure: Apple must pass the exact
  slow/sparse repro 10/10 and the same-generation composed gauntlet. P0-I/J remain open. See
  `notes/p0-cumulative-input-window-activation-20260828.md` and
  `notes/p0-selection-stream-continuation-20260829.md`. **Selection draw retry implemented/relinked/
  pending hardware (patch 0306):** the exact projected viewport click then proved the stream could
  map a semantically false cleared result: four live IDs, four `0xffffffff` words, and zero hits
  while `overlay_depth_mesh_conservative_selectable` plus related selectable shaders returned at
  the pending-module gate without incrementing the draw-drop generation. Module and pipeline
  deferral now participate in the existing drop signal; select-next cancels only attempts whose
  generation changed and retries after a later readiness edge. Buffers first created by the
  one-draw `G_FLAG_PICKSEL` manager share its ordered transient epoch instead of recreating
  never-published persistent allocations. The exact cold SwiftShader slow/sparse control now
  selects Cube and retires its independent recovery orbit in 13,514/2,116 ms with zero selection,
  page, or lifecycle errors; the rapid control also passes. RELINKED CAPTURE `.wasm.orig` is
  `5b95408deafe` (artifact SHA-256 prefix), canonical replay and REUSE are green. This software lane
  binds no pixel verdict: P0-I/J remain open until the driver passes the unchanged Apple 10/10 and
  same-generation composed P0-E interaction gauntlet. See
  `notes/p0-selection-draw-retry-20260829.md`. **Ten-run software stability verified/pending
  hardware:** the exact `5b95408deafe` candidate completed 10/10 fresh slow/sparse SwiftShader
  runs after four separately rejected WSLg target-page closures. Every completed run selected
  exactly Cube through the projected viewport click, retired both isolated orbits, converged the
  terminal/admitted/dispatched/presented/content generations, and had zero page, lifecycle, or
  selection-readback errors. Selection took 9,944-15,164 ms on cold software and exercised 36
  selectable shader-cache misses each time. This binds software retry stability only: the Apple
  10/10 pixel and same-generation gauntlet gates are unchanged. See
  `notes/p0-selection-draw-retry-software-stability-20260829.md`. **Selection draw admission
  hardened/relinked/pending hardware (patch 0307):** the retry signal still covered only named
  module/pipeline deferrals; direct and indirect batch draws could return later while resolving
  geometry, bind groups, load actions, or render passes without changing the generation that
  protects the cleared pick buffer. A browser-only `G_FLAG_PICKSEL` admission guard now remains
  armed across every synchronous pre-encode exit and disarms only after a real direct or indirect
  draw command is encoded. Ordinary draws and native builds are unchanged. The nine-mutation
  source/model contract, canonical replay, integrated native/wasm32 suite, real CAPTURE relink,
  locked no-work, product preflight, and REUSE are green. The exact slow/sparse software control
  selects Cube and retires its two isolated orbits in 317/12,165/1,878 ms with zero page,
  lifecycle, or selection-readback errors; bounded diagnostics census the expected first-use
  module/pipeline exits. RELINKED CAPTURE `.wasm.orig` is `a42be64bbc1c` (118,997,196 bytes).
  This is fail-closed hardening and software diagnosis, not pixel closure: the driver still must
  pass this exact inventory 10/10 on Apple and compose it with the same-generation P0-E gauntlet.
  **Exact-generation software stability verified/pending hardware:** `a42be64bbc1c` then completed
  10/10 fresh slow/sparse software runs: every completed run retired both isolated orbits, selected
  exactly Cube through the live projected viewport click, and recorded zero page, lifecycle, or
  selection-readback errors. Action/selection/recovery drains were 317-434/10,918-12,657/732-2,181
  ms. Four separately rejected WSLg target-page closures had zero page errors; five clean runs used
  WSLg and five used fresh isolated Xvfb. No runtime byte changed. This binds software stability
  only; the exact Apple 10/10 pixel and same-generation P0-E gauntlet gates remain unchanged. See
  `notes/p0-selection-draw-admission-20260829.md`. **Asynchronous draw-validation candidate
  implemented/relinked/pending hardware (`ad1877b`, patch 0308):** the synchronous admission guard still
  disarmed at `Draw*` encoding before browser command scopes produced their later terminal verdict.
  Each selection command now owns a balanced validation ticket; select-next keeps mapped bytes
  private until all tickets settle and cancels only the exact attempt when its dedicated failure
  generation advances. The rejecting completion publishes the retry edge, while unrelated UI draw
  drops cannot invalidate a genuine pick. Fail-first/final 8-mutation, native/wasm32 readback,
  integrated WebGPU, adjacent selection, canonical replay, product preflight, relink/no-work, and
  exact slow/sparse software controls are green. The control selects Cube and retires both isolated
  orbits in 332/11,875/bounded milliseconds with zero selection/page/lifecycle errors. RELINKED
  CAPTURE `.wasm.orig` is `fb5223a06ee9` (119,001,291 bytes). This remains device-free evidence:
  P0-I/J require this exact inventory to pass Apple 10/10 plus the same-generation composed P0-E
  gauntlet. See `notes/p0-selection-draw-validation-20260829.md`. **Browser selection failure
  teardown made non-modal/relinked/pending hardware (patch 0309):** source tracing confirmed that
  every `BKE_report` on a canceled operator becomes a popup, so the prior readback error report
  captured the continuation's correctly replayed input and presented as a total freeze. All seven
  browser asynchronous selection failure exits now use one 16-line-capped console diagnostic,
  replay retained input, and leave `op->reports` empty; native reports are unchanged. The Apple
  producer rejects either failure spelling, so this fail-safe cannot manufacture a pass. Focused
  mutation/replay, canonical source, native/Wasm compile, CAPTURE preflight, adjacent selection,
  and exact slow/sparse software controls are green. RELINKED CAPTURE `.wasm.orig` is
  `c22cc2e373d5` (119,001,697 bytes); the control selects Cube and retires both orbits with zero
  selection-fallback/page/lifecycle errors. P0-I/J remain open for this exact inventory to pass
  Apple 10/10 and the same-generation composed P0-E gauntlet. **External-cancel replay hardened/
  relinked/pending hardware (`da29c42`, patch 0310):** teardown audit found the registered WM
  `cancel` callback was the only terminal selection-continuation path that freed its retained input
  FIFO without replaying it first. It now restores that FIFO through the existing same-manager/
  window guard before releasing the timer and GPU sessions. The fail-first/final 20-mutation
  contract, native/Wasm editor compiles, canonical replay, CAPTURE preflight, adjacent selection
  contracts, exact slow/sparse software control, and REUSE are green. RELINKED CAPTURE `.wasm.orig`
  is `63e188ba4232` (119,001,717 bytes); the control selects Cube and retires both orbits with zero
  selection-fallback/page/lifecycle errors. This closes one input-loss teardown seam, not the Apple
  pixel gate: P0-I/J remain open for exact Apple 10/10 plus the same-generation P0-E gauntlet. See
  `notes/p0-selection-failure-nonmodal-20260829.md` and
  `notes/p0-selection-cancel-replay-20260829.md`. **Exact-generation software stability verified/
  pending hardware:** the unchanged `63e188ba4232` CAPTURE generation completed 10/10 fresh
  slow/sparse isolated-X runs. Every completed run retired both orbits, selected exactly Cube via
  the live projected viewport click, balanced GHOST/WM delivery, and recorded zero selection-
  fallback/page/lifecycle errors. One separate WSLg page/context closure had zero product errors
  and was rejected rather than counted. Stream/retry/admission/validation mutation contracts,
  locked no-work, and REUSE remain green. This binds software stability only: P0-I/J stay open for
  exact Apple 10/10 plus the same-generation P0-E gauntlet; no runtime byte or receipt changed.
  **Selection-validation boundary exported/relinked/pending hardware (`e2bac4a`):** the sparse
  timeline now samples the existing global draw-drop generation plus selection command-validation
  pending/failure counters on every 250 ms poll and rejects a served product that lacks any export.
  This is read-only observability: selection, retry, redraw, and timeout behavior are unchanged.
  The exact cold software control demonstrates the discriminator by peaking at 19 pending tickets,
  zero validation failures, and 68 additional draw drops before selecting Cube and retiring both
  isolated orbits. RELINKED CAPTURE `.wasm.orig` is `0c3eda918085` (119,001,878 bytes). P0-I/J
  remain open for this exact inventory to pass Apple 10/10 plus the same-generation P0-E gauntlet;
  no hardware receipt, profile, APPLY/public bundle, tag, result, promise, or launch claim changed.
  See `notes/p0-selection-validation-boundary-20260829.md`. **Exact-generation software stability
  verified/pending hardware:** the unchanged candidate then completed 10/10 fresh isolated-X
  slow/sparse runs. Every run retired both isolated orbits, selected exactly Cube, and recorded
  zero validation failures, selection fallbacks, page errors, or lifecycle errors. Validation
  pending peaked at 19 and returned to zero; selection drained in 10,429-15,451 ms. This binds only
  repeatable software behavior: the exact Apple 10/10 and same-generation P0-E gauntlet remain
  mandatory, and no runtime byte or product claim changed.
- [x] **P1-RELEASE-FIRST-PIXEL-LOADER-COHERENCE [shell] (`125f552`):** the release shell's
  nominal printf-based first-pixel path was correct, but its 2.5-second `WM_main` fallback hid the
  loader with the uncapped presentation counter still at zero. Exact-product tracing measures an
  18,638 ms exposed warmup interval before the first successful frame. The fallback now polls the
  existing uncapped counter, requires a finite positive value, and stops after a hard 120-second
  ceiling with the loader still visible on failure. The faithful legacy mutation hides at
  `presents=0`; current and masked-marker paths both hide at `presents=1` with zero page errors.
  Eight source mutations, loader source/browser checks, public hardening/minification/assembly,
  staged provenance, release freezes, compliance, and REUSE are green. This is shell-only and the
  CAPTURE Wasm identity remains unchanged. The later Apple shadow gauntlet closes the remaining
  transient-widget pixel question; the software-adapter path still binds no pixel claim. See
  `notes/m4-first-pixel-loader-coherence-20260826.md`.
- [x] **P1-RELEASE-LOADER-REDESIGN [shell, public-bundle] (`1040ac7`, boot correction `824686b`):** the windowed loader now
  uses the owner-specified `#17181b` surface, one thin ring, one 2-pixel determinate bar and percent,
  plus one single-line GPL source/trademark footer. The proof/marketing copy moved to `README.md`;
  `#bw-diag`, `?gate=`, and the existing generic first-presentation dismissal are preserved. A reproducible renamed
  Inter 4.001 subset initially shipped locally at 9,500 bytes; the Stage-0 bootstrap pass later
  expanded it to a layout-preserving 22,480 bytes (SHA-256
  `47d56ba06d6380e40f49201b85421b5f8a22bc2b83ed7a257c9ab49fdc66421f`) with OFL metadata,
  immutable MIME/cache policy, precache, monolithic/staged inventory, provenance, and exact-tree
  coverage. The release relink exposed one stale call to the removed `setIndeterminate()` helper;
  `824686b` replaces it with a truthful `setProgress(0)` reset and makes both loader and P0-G
  diagnostics fail closed on that real startup path. Final same-artifact fallback boot reaches
  `WM_main` with 261 ticks, 18 uncapped presentations, zero page errors, and black-RGB widget WGSL.
  Public-shell consumers, REUSE, and M0 6/6 regression checks are green. **Boundary:** the clean
  CAPTURE relink is nonshipping; Apple P0-E pixels and fresh exact-generation profiles remain
  mandatory before APPLY or publication. See
  `notes/m4-release-loader-redesign-20260826.md`.
- [x] **P1-RELEASE-TWO-PHASE-LOADER [shell] (`f9dfb78`):** the same minimal loader now labels
  Stage-0 byte progress `Downloading`, then switches at Emscripten's post-run-dependency
  `Running...` boundary to `Launching` with the percentage retired and the same two-pixel bar
  honestly indeterminate. Controlled Chromium proves both states, one ring/bar, local font,
  single-line footer, hidden diagnostics, and zero external requests; public hardening,
  monolithic/staged assembler, provenance/minifier, technical receipt, first-presentation
  fallback, and REUSE contracts are green. This shell-only commit does not relink or invalidate
  P0-E's pending Apple candidate. See `notes/m4-loader-two-phase-20260827.md`.
- [~] **P1-RELEASE-VIEWPORT-CONTENT-LOADER-DISMISSAL [driver, claimed_by: root,
  blocked-by: none]:** replace the generic
  first-presentation hide signal with a distinct marker proving successful visible
  `SPACE_VIEW3D` content (grid/gizmo/scene), then require the loader to remain visible through
  every chrome-only/clear viewport frame. Do not infer readiness from elapsed time or present
  count. This requires a C++ relink and same-rig cold-boot pixel verification; keep the current
  P0-E candidate stable until its filed acceptance run completes.
  **Source candidate 2026-08-27 (`2c82c19`):** cold boot now starts a bounded semantic episode; successful
  `overlay_background` plus `overlay_grid_next` encoding before `OCIO_Display`, together with the matching
  validated surface submission publishes a one-shot browser export, and the shell has no generic
  present fallback. Native/wasm32 behavior, controlled Chromium, canonical replay, public-shell
  consumers, compliance, and REUSE are green. The Apple-accepted `v0.1.1-rc.1` CAPTURE bytes were
  deliberately not relinked and remain the exact profile handoff. **Not resolved:** relink this
  successor separately and require Apple cold-boot pixels before closing; no device-free result
  binds that receipt.
  **Exact-product order correction and relink 2026-08-27 (`e369b6e`):** the first relink exposed
  a source-only contract error before hardware handoff: all real frames encoded grid before
  background, so the candidate withheld every present despite advancing WM ticks. The predicate
  now requires both offscreen passes before the display composite without inventing an order
  between separate targets; a fail-first case binds the measured order and the native/wasm model
  is green across 66 cases. The exact fallback product presents qualified content and hides the
  loader afterward with zero page errors. **RELINKED windowed-opt @ `e369b6e`:** JS
  `8d05e8c8f0c4`, Wasm `9b0cbb993e16`, `.wasm.orig` `f3251f948449` (119,160,136 bytes), data
  `095d0ba748c3`, manifest `eefd2418dbf9`; CAPTURE preflight and committed-state no-work are green.
  **Not resolved:** Apple cold-boot pixels and a P0-E regression check remain mandatory; this new
  generation needs fresh accepted success+terminal profiles before APPLY. See
  `notes/m4-viewport-content-loader-dismissal-20260827.md`.
- [x] **P1-RELEASE-PUBLICATION-METADATA-SCRUB [compliance] (`a920bfd`):** the two public-facing
  migration comments no longer publish the private host runbook name, and the preserved
  outer-worktree recovery patch is regenerated from its exact `0577f7f` anchor without private
  user paths in either the carrier or its 178-path reconstructed postimage. Path-bearing historical
  preimages use replay-safe Git binary deltas; the new SHA-256 is
  `563dfe303d9e401c73938d733e118d3f0e21dbeec5e4216a3b43154031b8e4b1`. The fail-closed contract
  binds the checksum, applies the patch, scans the postimage, reverse-applies it, and proves every
  touched path returns to its exact anchor state. Exact-commit verification, REUSE 6.2.0,
  technical compliance, and pinned-container M0 6/6 regression are green; M1-M8 retain their
  existing receipt/APPLY/product boundaries. No public snapshot, bundle, profile, receipt, or
  result was produced. See `notes/release-publication-metadata-scrub-20260826.md`.
- [x] **P1-M8-PUBLIC-PARITY-DASHBOARD [compliance] (`d22c195`):** `PARITY.md` now publishes all
  nine strict milestone receipt rows plus all 53 named deferral-registry rows directly from a Git
  index/commit view. Missing receipts stay `UNAVAILABLE`; raw check details, fleet activity, local
  paths, host names, and ledger evidence paths never enter the public page. The generator rejects
  private-path and unnamed-blocker mutations, reproduces byte-for-byte from committed HEAD at input
  SHA-256 `ba4db8ab0b414d055ededc69759910f1de509d0dac4113dbb9fff8f416a11dfe`, and the public README
  links it. Focused verification, REUSE, technical compliance, and container-backed regression are
  green at their applicable boundaries; refreshed M8 remains honestly RED at its pre-existing 23
  APPLY/browser/tier failures. No public deployment, product, profile, receipt, result, or promise
  was promoted. See `notes/m8-public-parity-dashboard-20260826.md`.
- [x] **P1-M8-PUBLIC-PARITY-STAGING-FRESHNESS [compliance] (`3742064`):** refresh the
  public size/latency row from the superseded provisional Stage-0 accounting to the current
  shader-seed plus layout-preserving UI-font projection, and fail closed if the public page
  regresses to stale profile-generation language or byte totals. The page now reports the
  14,742,104-byte projection, its 257,896-byte provisional margin and small-Wasm-delta caveat,
  current `b8b2a682ff09` CAPTURE identity, and fresh-profile requirement without promoting APPLY.
- [x] **P1-RELEASE-TAGGED-BUILD-CORRESPONDENCE [driver] (`2946f0e`):** the
  deterministic packager now binds an annotated release tag at clean `HEAD`, the strict successful
  APPLY inventory/preflight, the canonical pinned-upstream source replay, independently replayed
  full staged provenance, and every exact public
  bundle byte into a normalized USTAR/gzip archive plus source/artifact sidecar. It rejects eleven
  tag/tree/inventory/archive mutations, refuses overwrite/symlinks/extras, strips local receipt
  paths, and explicitly rejects the current CAPTURE artifact. Both programs are required by the
  two-root release freeze and the public README documents the invocation. **Boundary:** this closes
  the reproducibility contract, not the release: P0-E pixels are now Apple-verified for the exact
  `505702dbf41c...` CAPTURE generation, while accepted same-generation success+terminal profiles
  remain mandatory before APPLY, final tagging, or publication. See
  `notes/release-tagged-build-correspondence-20260826.md`.
- [x] **P1-RELEASE-V0.1.1-RC1-CAPTURE-HANDOFF [driver] (`7ea0093`):** the release line drops the
  unverified post-acceptance runtime experiment and reconstructs the exact `72dde88` source tree
  exercised by Apple hardware. A locked relink reproduces the accepted five-file CAPTURE set
  byte-for-byte: JS `52a9a0257830`, Wasm `69b2f10ebac7`, 119,157,853-byte `.wasm.orig`
  `505702dbf41c`, data `095d0ba748c3`, and manifest `10b181385e60`. The driver reports 10/10
  zero-input shrink recovery plus a six-extent stress run on Apple M4 Pro, closing P0-E. Source,
  trace, native/wasm32 queue, hardware-producer/consumer self-checks, canonical replay, CAPTURE
  preflight/no-work, tagged-release contract, and REUSE 6.2.0 are green; the containing clean
  source state is annotated `v0.1.1-rc.1`. **Boundary:** this immutable tag is the driver's
  profile/final-gauntlet input, not a public archive. CAPTURE remains nonshipping and the existing
  profiles are hash-incompatible; fresh exact-generation success+terminal profiles remain the
  only authority for APPLY, the staged public bundle, and the final `v0.1.1` package. See
  `notes/release-v0.1.1-rc1-capture-20260827.md`.
- [~] **P1-M4-M8-SPLIT-CAPTURE-PRODUCT [driver, claimed_by: root]:** the current windowed build is
  relinked from the hardware-accepted `a8f6c43` runtime and release restoration `7ea0093` as a
  strict CAPTURE generation with 120,511,178-byte instrumented Wasm and 119,157,853-byte
  `.wasm.orig` at SHA-256
  `505702dbf41ce0a9552f47e6a78ff9f10562c068c9471a35031835b33e9c062c`, and a schema-1 PASS
  clean-build manifest. Inventory preflight, the strict producer self-check, two-phase source
  contract, canonical replay, committed-state locked no-work, and exact-artifact fallback
  shrink/restore are green; Apple hardware passes the 10/10 zero-input shrink bar and six-cycle
  extent stress run against these exact bytes. **Not resolved:**
  CAPTURE is non-shipping and has no deferred shard. The driver-operated Apple hardware rig must
  produce the exact success plus terminal-error profiles; only their accepted union can authorize
  the hash-bound APPLY relink. Any intervening relink requires new profiles. See
  `notes/m4-split-capture-product-20260826.md`.
- [x] **P1-M8-PROVISIONAL-SPLIT-SHAPE [driver]:** an isolated, explicitly non-receipt use of the
  failed Apple success+terminal profiles proves the production Binaryen checksum rejects the
  12-byte-newer CAPTURE generation, then measures the structurally compatible provisional split
  without touching the build tree. The primary is 12,292,157 bytes Brotli q11 versus 24,212,144
  unsplit, but primary + current stage-0 data + glue totals 17,917,410 bytes, still 2,917,410 over
  LAUNCH.md's 15 MB bar. The exact 48-function controller closure remains PASS. This does not
  authorize APPLY; accepted hash-bound Apple profiles remain mandatory. See
  `notes/m8-provisional-split-shape-20260826.md`.
- [x] **P1-M8-STAGE0-MONO-FONT-BOOTSTRAP [driver]:** Stage 0 now carries an exact-hash
  18,272-byte DejaVu Sans Mono subset and Stage 1 restores the pinned 145,192-byte source before
  one shared UI/mono/fallback-stack refresh. Chromium proves identical Basic-Latin advances and
  raster at six console sizes, identical Latin-1 advances, exact initial monolith/staged pixels,
  exact full-font restoration, trusted console input, and zero page/serious errors. The bounded
  two-bootstrap loader rejects duplicate/excess/identity mutations; provenance, licensing, and
  release inventories bind both fonts. Same-codec accounting recovers 125,123 net critical bytes,
  revising the provisional complete-wire shape to 14,616,981 bytes. **Boundary:** no Wasm was
  relinked and no APPLY, hardware-pixel, <=8-second, <=15-MB, or launch receipt was promoted. See
  `notes/m8-stage0-mono-font-bootstrap-20260826.md`.
- [x] **P1-M8-PTHREAD-SINGLE-TRANSFER [driver] (`0155397`):** the public product now fetches one
  exact, separately inventoried Stage-0 worker source and supplies its hashed Blob through pinned
  Emscripten's supported `mainScriptUrlOrBlob` seam. The relinked CAPTURE browser reaches `WM_main`
  with one page-glue response, one worker-source response, 32 unique same-origin Blob dedicated
  workers, and zero page errors, replacing the measured 34 repeated main-glue requests. Public
  assembly, exact tree/Brotli/cache/provenance, M7/M8 receipt consumers, and both release freezes
  fail closed on the source identity, singleton factory, origin, worker kind, uniqueness, and
  pre-semantic timing. Exact q11 cost is 61,066 bytes for the staged worker source plus 750 bytes
  for the minified bootstrap, moving the provisional lower-bound wire shape to ~14,678,797 bytes
  before generated-control and small-Wasm deltas. **Boundary:** CAPTURE remains nonshipping; fresh
  current-generation Apple profiles, APPLY, exact <=15 MB/<=8 s receipts, and hardware pixels are
  still mandatory. See `notes/m8-pthread-single-transfer-20260827.md`.
- [x] **P1-M8-CURRENT-COMPLETE-WIRE-PROJECTION [root]:** the canonical public assembler and
  independent full-stage provenance replay now close the generated-control uncertainty against
  the current `b8b2a682ff09` shell/data tree. The exact current non-Wasm/control subtotal is
  2,397,124 Brotli bytes. Combined only as a cross-generation planning fixture with the earlier
  12,292,157-byte c9 provisional primary, complete critical wire is 14,689,281 bytes, 310,719
  under the decimal ceiling; the current primary must therefore be <=12,602,876 bytes. The
  accepted r2 profiles have 136,751 counters/20,447 union hits while current b8 has 136,754
  defined functions and shifted controller ordinals, so checksum rewriting or counter padding is
  explicitly rejected. **Boundary:** this is not APPLY, a current primary, a size receipt, or a
  hardware timing result; fresh exact-generation Apple profiles remain mandatory. See
  `notes/m8-current-complete-wire-projection-20260827.md`.
- [x] **P1-M8-PTHREAD-SHARED-MAIN-CACHE [root] (`653ebe0`):** the public page and pthread
  bootstrap now consume one immutable, content-addressed Stage-0 page-glue URL. Pinned Chromium
  reaches `WM_main` with one origin body, exact `script` + cached `fetch` Resource Timing entries,
  all 8/8 configured same-origin Blob pthreads, strict CSP, and zero page errors. The producer and
  independent composer bind the cache hit, decoded identity, per-run origin delta, unique workers,
  service-worker inventory, and one-artifact critical-wire accounting. Canonical assembly plus an
  independent full-tree q11 replay remove the 61,066-byte duplicate at a measured 214-byte control
  cost: current non-Wasm/control bytes fall from 2,397,124 to 2,336,272 and the cross-generation
  planning total falls from 14,689,281 to 14,628,429, leaving 371,571 bytes of provisional margin.
  **Boundary:** no build artifact, profile, APPLY/public bundle, hardware receipt, milestone result,
  or launch claim changed; a current primary must be <=12,663,728 bytes and fresh exact-generation
  Apple profiles remain mandatory. See `notes/m8-pthread-shared-main-cache-20260827.md`.
- [x] **P1-M8-STAGED-PACKER-RECONCILIATION [driver] (`cb459b9`):** the fail-closed manifest
  parser and post-first-pixel partition behind the provisional measurement are now committed and
  covered by the staged provenance and release-freeze consumers. Product probing found and fixed
  two fidelity hazards before landing: Cycles is factory-enabled and must remain in Stage 0, and
  the selected solid-light `.sl` presets cannot be zero-length placeholders. The exact CAPTURE
  data now partitions to 2,554 keep files / 28,741,042 bytes, 887 deferred files / 136,614,483
  bytes, and one dropped wheel / 1,787,723 bytes. Same-encoder q11 measures primary + rewritten
  glue + Stage 0 at 18,120,796 bytes, still 3,120,796 over the 15 MB bar. A fallback-software
  Stage-0/monolith A/B reaches the same 254 ticks/14 presents with no relevant console or page
  errors, but both captures are uniformly dark and bind no pixel receipt. Accepted Apple profiles,
  APPLY, and a hardware staged-pixel run remain mandatory. See
  `notes/m8-staged-packer-reconciliation-20260826.md`.
- [x] **P1-M8-STAGE0-UNSELECTED-APP-TEMPLATES [driver] (`0fd49fa`):** the pinned native oracle
  proves factory startup selects no application template, so the nine alternate template
  `__init__.py`/`startup.blend` files now ride Stage 1 with byte-exact placeholder restoration.
  Exact CAPTURE Stage-0 data falls from 5,615,715 to 5,123,738 Brotli-q11 bytes; primary + glue +
  data falls from 18,120,796 to 17,628,735 bytes, still honestly 2,628,735 over LAUNCH.md's 15 MB
  bar. Fail-first/final packer coverage, exact derivation, provenance/assembler, pinned oracle,
  fallback-software product boot/input, and REUSE are green. Hardware staged pixels remain
  mandatory; no profile, APPLY artifact, or receipt changed. See
  `notes/m8-stage0-app-templates-20260826.md`.
- [x] **P1-M8-STAGE0-NUMPY [driver] (`d8de1d2`):** the pinned native oracle and real windowed
  CAPTURE product both load zero NumPy modules before the first stable WM state, so the complete
  520-file package now rides Stage 1 instead of keeping a partial 203-file core in Stage 0. A
  monolith/candidate browser contract proves exact version/add-on/area/default-object state,
  trusted-input progress, zero serious/page errors, zero-byte Stage-0 placeholders, then uses the
  production Stage-1 loader to restore all 141,182,163 deferred bytes and import 86 NumPy modules
  with real array arithmetic. Stage-0 data q11 falls 5,123,738 -> 4,432,412 bytes and rewritten
  glue falls 86,578 -> 85,524; unchanged provisional primary + glue + data is 16,936,355 bytes,
  still honestly 1,936,355 over LAUNCH.md's 15 MB bar. Accepted Apple profiles, APPLY, and
  hardware staged pixels remain mandatory. See `notes/m8-stage0-numpy-20260826.md`.
- [x] **P1-M8-STAGE0-COMPILED-SOURCES [driver] (`4a43751`):** 833 icon/cursor SVGs,
  embedded-font inputs, compiled theme source, and generator scripts now ride Stage 1 while their
  linked runtime data stays in the primary/Stage-0 product. A real monolith/candidate browser A/B
  preserves version/add-ons/editors/default objects and trusted-input progress, proves eight
  zero-length source placeholders plus the retained runtime icon, and restores all 1,932 deferred
  files / 142,757,962 bytes with exact representative hashes and zero serious/page errors.
  Stage-0 data/glue q11 falls 4,432,412+85,524 -> 4,028,170+81,589; provisional critical wire
  falls 16,936,355 -> 16,528,178, still honestly 1,528,178 over LAUNCH.md. Accepted Apple
  profiles, APPLY, and hardware staged pixels remain mandatory. See
  `notes/m8-stage0-compiled-sources-20260826.md`.
- [x] **P1-M8-STAGE0-FORMAT-IMPLEMENTATIONS [driver] (`515630b`):** native factory startup and
  a ten-second post-WM windowed census agree on the exact eight-file registration/UI closure for
  the enabled BVH/SVG/UV Layout/FBX/glTF add-ons. Their 140 lazy operator implementations now ride
  Stage 1; a real monolith/candidate A/B preserves startup and trusted input, restores all
  2,072 deferred files / 144,682,014 bytes, imports seven representative implementations, and
  completes glTF export/import with zero serious/page errors. Stage-0 data/glue q11 falls
  4,028,170+81,589 -> 3,748,720+80,933; provisional critical wire falls 16,528,178 ->
  16,248,072 bytes, still honestly 1,248,072 over LAUNCH.md. Accepted Apple profiles, APPLY, and
  hardware staged pixels remain mandatory. See `notes/m8-stage0-format-addons-20260826.md`.
- [x] **P1-M8-STAGE0-PYTHON-ENCODINGS [driver] (`11a4afd`):** pinned native factory startup and
  the exact windowed CAPTURE product agree on the five-file encoding registry/UTF-8 union, so the
  other 117 Python codec sources now ride Stage 1. A real monolith/candidate browser A/B preserves
  startup, UTF-8, and trusted input, restores all 2,189 deferred files / 146,061,813 bytes, then
  proves byte-exact CP1252, Latin-1, and Shift-JIS imports and round-trips with zero serious/page
  errors. Stage-0 data/glue q11 falls 3,748,720+80,933 -> 3,699,553+80,383; provisional critical
  wire falls 16,248,072 -> 16,198,355 bytes, still honestly 1,198,355 over LAUNCH.md. Accepted
  Apple profiles, APPLY, and hardware staged pixels remain mandatory. See
  `notes/m8-stage0-python-encodings-20260826.md`.
- [x] **P1-M8-STAGE0-PYTHON-SUPPORT [driver] (`8ea65f3`):** the pinned native oracle and exact
  windowed CAPTURE product load none of the help, translation-tooling, Freestyle, template, test,
  or inactive-preset sources before the stable main loop. The packer explicitly retains the two
  indirectly executed active Blender-keymap files rather than trusting `sys.modules`. A real
  monolith/candidate browser A/B preserves the complete active keymap, startup state, and trusted
  viewport input before Stage 1, then restores all 2,477 files / 147,569,290 bytes, imports and
  compiles representative support paths, and reports zero serious/page errors. Stage-0 data/glue
  q11 falls 3,699,553+80,383 -> 3,521,872+78,953; provisional critical wire falls 16,198,355 ->
  16,019,244 bytes, still honestly 1,019,244 over LAUNCH.md. Accepted Apple profiles, APPLY, and
  hardware staged pixels remain mandatory. See `notes/m8-stage0-python-support-20260826.md`.
- [x] **P1-M8-STAGE0-PYTHON-RUNTIME [driver] (`6bc7cab`):** 203 exact browser-cold CPython and
  site-package sources now ride Stage 1 behind a fail-closed allowlist; new paths stay in Stage 0.
  The zero-error monolith/candidate A/B forced `ssl.py` and urllib3's PyOpenSSL bridge back into
  Stage 0 for the enabled `bl_pkg` startup path, preserves trusted viewport input, restores all
  2,680 files / 150,810,264 bytes, and exercises six lazy runtime subsystems after restoration.
  Stage-0 data/glue q11 falls 3,521,872+78,953 -> 2,941,058+78,104; provisional critical wire
  falls 16,019,244 -> 15,437,581 bytes, still honestly 437,581 over LAUNCH.md. Accepted Apple
  profiles, APPLY, and hardware staged pixels remain mandatory. See
  `notes/m8-stage0-python-runtime-20260826.md`.
- [x] **P1-M8-STAGE0-LAUNCH-ASSETS [driver] (`5169fa6`):** 72 measured-cold Blender Python
  sources, 57 package-support files, 12 authoring/reference files, and 142 lazy toolbar icons now
  ride Stage 1 behind exact fail-closed inventories. A fail-first real-browser candidate restored
  `_bl_rna_utils/data_path.py` and DejaVu Sans Mono to Stage 0 before landing. The final
  monolith/candidate A/B preserves startup, active keymap, default toolbar icons, and trusted input,
  then restores all 2,963 files / 152,238,870 bytes and exercises lazy imports, Requests metadata,
  CA data, deferred icons, and Console initialization with zero serious/page errors. Stage-0
  data/glue q11 falls 2,941,058+78,104 -> 2,595,374+76,803; provisional critical wire falls
  15,437,581 -> 15,090,596 bytes, still honestly 90,596 over LAUNCH.md. Accepted Apple profiles,
  APPLY, and hardware staged pixels remain mandatory. See
  `notes/m8-stage0-launch-assets-20260826.md`.
- [x] **P1-M8-CRITICAL-BROTLI-WINDOW [driver] (`99d7fd2`):** public-bundle Brotli-q11 encoding
  is reproducible on pinned Node 22.16.0 with the standard 16 MiB window (`lgwin=24`), and the
  exact codec is bound through assembly, provenance, transport, receipt, M7/M8, and release-freeze
  contracts. Exact recompression of the unchanged provisional primary/data/glue trio is
  14,963,658 bytes, but that historical projection omitted the parser/worker shell overhead and
  is superseded for launch accounting by the complete-wire item below. This remains a projection,
  not an APPLY/public-bundle receipt. See `notes/m8-critical-brotli-window-20260826.md`.
- [x] **P1-M8-COMPLETE-CRITICAL-WIRE [driver] (`b1474cd`):** the 15 MB receipt now counts all
  responses fetched before semantic interaction: HTML, diagnostics, file/boot shell, Stage-1 and
  service-worker controls, Emscripten glue/data, and manifest-critical Wasm. Browser-context
  request evidence prevents worker traffic disappearing; deterministic q11/lgwin-24 siblings,
  exact-tree identity, provenance, and Python/JavaScript consumers share the same complete set.
  Current contract-shaped provisional wire is approximately 14,994,702 bytes, only 5,298 under
  the bar; accepted Apple profiles, exact APPLY assembly, <=8 second hardware timing, and the real
  receipt remain mandatory. See `notes/m8-complete-critical-wire-20260826.md`.
- [x] **P1-M8-STAGE0-PRELOAD-MANIFEST [driver] (`9db6040`):** deferred files are now absent
  from the critical preload manifest instead of repeated as 2,962 zero-byte entries. The packer
  fail-closes unless Emscripten's 448 baked `FS_createPath` calls cover all 335 deferred parents.
  The first absent-file browser candidate exposed a masked urllib3 startup access, so its 3,655-byte
  Emscripten fetch worker returned to Stage 0 before landing. Six real monolith/candidate browser
  A/B contracts preserve startup, trusted input, lazy formats, compiled sources, support scripts,
  codecs, NumPy, and byte-exact Stage 1 with zero serious/page errors. Exact q11 data/glue is
  2,595,747 + 60,806 bytes, a net 14,948-byte improvement; complete provisional wire is now
  approximately 14,979,754 bytes, 20,246 under the bar. Accepted profiles, APPLY, exact public
  assembly, hardware pixels, and <=8 second timing remain mandatory. See
  `notes/m8-stage0-preload-manifest-20260826.md`.
- [x] **P1-M8-STAGE0-STUDIOLIGHT-DISCOVERY [driver] (`d2e890f`):** the absent-file rewrite
  exposed a one-time-registry exception: `BKE_studiolight_init()` enumerates matcap/world names
  before Stage 1, so restoring bytes later could not restore the missing choices. Exactly 35 image
  names now remain as zero-byte discovery entries while all payload bytes stay deferred; eager
  `.sl` presets remain real. The pinned oracle proves 6/27/8 StudioLight types, and the real
  browser A/B preserves all 41 entries before Stage 1, restores 2,963 files byte-exactly, then
  selects `forest.exr` and `basic_bright.exr` with trusted input and zero serious/page errors.
  The 218-byte compressed glue cost leaves provisional complete wire approximately 14,979,291,
  still 20,709 under LAUNCH.md. Accepted profiles, APPLY, hardware staged pixels, and <=8 second
  timing remain mandatory. See `notes/m8-stage0-studiolight-discovery-20260826.md`.
- [x] **P1-M8-PUBLIC-SHELL-MINIFICATION [driver] (`faff477`):** the public assembler now
  minifies diagnostics, file bridge, the already-hardened boot shell, and the Stage-1 loader with
  repository-owned deterministic Terser 5.39.0 on pinned Node 22.16.0. Exact package-lock and
  executable-bundle identities, SPDX preservation, source-freeze coverage, independent
  provenance replay, minified Stage-1 execution, and six identity/syntax negatives fail closed;
  generated service-worker controls stay readable for their exact transactional audit. Pinned
  q11/lgwin-24 replay reduces those four public programs from 22,880 to 10,911 bytes, saving
  11,969 bytes. Applied conservatively to the current StudioLight projection, complete critical
  wire is approximately 14,967,322 bytes, 32,678 under LAUNCH.md. This is still not an exact APPLY
  bundle, hardware timing, or launch receipt; accepted Apple profiles, APPLY assembly, staged
  pixels, and the <=8-second interaction bar remain mandatory. See
  `notes/m8-public-shell-minification-20260826.md`.
- [x] **P1-M8-STAGE0-FALSE-COLOR-LUT [driver] (`a5ab84c`):** the pinned native oracle and
  exact windowed CAPTURE product both select `sRGB / AgX / None` at factory startup, so the
  127,040-byte non-default `AgX_False_Color.spi1d` LUT now rides Stage 1 while the default AgX
  display inputs remain in Stage 0. A real monolith/candidate browser A/B preserves startup and
  trusted input, restores all 2,963 deferred files / 152,362,255 bytes byte-exactly, switches the
  live scene to False Color, and reports zero OCIO/page/GPU errors. Pinned q11/lgwin-24 data/glue
  is 2,595,052 + 60,820 bytes; complete provisional wire falls 681 bytes to approximately
  14,979,073, or 20,927 under LAUNCH.md. Accepted profiles, APPLY, exact public assembly,
  hardware staged pixels, and <=8 second timing remain mandatory. See
  `notes/m8-stage0-false-color-lut-20260826.md`.
- [~] **P1-M8-PUBLIC-QUERY-HOOK-HARDENING [driver] (`8867ebb`):** the development/public
  capability seam is now committed, public assembly and independent provenance share one
  fail-closed byte transformer, and the real boot-shell prefix rejects Python, argv, gate, and
  keepalive query/global controls in the public variant. Focused execution rejects six mutations;
  staged assembly/provenance/producer, M8 consumer, release-freeze, and compliance self-checks are
  green. **Not resolved:** no public bundle can be assembled or browser-attacked until the current
  CAPTURE generation receives the two Apple profiles and is relinked to a hash-bound APPLY
  primary/deferred product. See `notes/m8-public-query-hardening-20260826.md`.
- [x] **P1-M8-STAGE1-LOADER-SOURCE-RECONCILIATION [driver] (`ba0ceee`):** the public
  assembler's Stage-1 loader is now a committed input with visible phase/MB progress, streamed
  byte accounting, exact short/oversize rejection, and development-marker guards around query
  gate/manual controls. The timing producer uses trusted pre-navigation state instead of the
  disabled public query. The committed predecessor fails first; final seven-case/eight-mutation
  execution, assembly/provenance/transport/CAPTURE consumers, release-freeze contracts, REUSE,
  M8 scope, and container regression preserve their strict boundaries. CAPTURE remains unchanged
  at `.wasm.orig` SHA-256 `c9dbae361ec1`; no APPLY/public receipt was manufactured. See
  `notes/m8-stage1-loader-source-reconciliation-20260826.md`.
- [x] **P1-RELEASE-SHIPPING-SOURCE-RECONCILIATION [driver] (`410e7ad` + `559b106` +
  `5426e76`):** the four named runtime sources that the optimized CAPTURE product was built from
  are now direct committed inputs: the ten-limit WebGPU device requests, persistent and
  activation-safe file bridge with bounded share/inspection operations, and byte-level loader
  progress. All four paths are clean against HEAD, the optimized `blender_browser` target is exact
  Ninja no-work, focused source/mutation contracts and REUSE 6.2.0 are green, and container-backed
  regression restores M0 6/6. No artifact, profile, receipt, or milestone result changed; unrelated
  shared-worktree residue remains unclaimed. See
  `notes/release-shipping-source-reconciliation-20260826.md`.
- [x] **P1-RELEASE-BUILD-PROFILE-RECONCILIATION [driver] (`5246f7b`):** the exact
  `blender_web.cmake` and `platform_wasm.cmake` bytes used by the optimized CAPTURE artifact are now
  direct committed inputs. Current cache/manifest semantics, stack and two-phase split contracts,
  strict CAPTURE inventory, locked no-work, and REUSE are green; the artifact remains unchanged at
  `.wasm.orig` SHA-256 `c9dbae361ec1`. M8/regression retain their strict APPLY/browser/receipt
  boundaries. See `notes/release-build-profile-reconciliation-20260826.md`.
- [x] **P1-RELEASE-METADATA-RECONCILIATION [compliance] (`c5ad9ab`):** the five remaining dirty
  shipping metadata files are committed without generated result/sandbox residue. The dependency
  record now identifies `libosdGPU.a` as the real two-object GLSL patch-source archive, and both
  OpenSubdiv/OpenUSD custom TOST-1.0 compatibility decisions remain unresolved for GPL-literate
  human review. Strict dependency inventory, dependency self-check, deferral/S7 contracts, all
  nine technical compliance facts, and REUSE 2,640/2,640 are green; pinned-container regression
  restores M0 6/6 while M1-M8 retain their strict existing boundaries. See
  `notes/release-metadata-reconciliation-20260826.md`.
- [x] **P1-M8-DEFERRAL-REGISTRY-COMPLETENESS [compliance] (`0e7f2ec`):** sixteen named
  launch-visible feature rows now bind 33 forced-OFF build flags, covering IK, Bullet/physics,
  Ocean, remesh/Quadriflow, exact boolean, SLIM UV, video, audio, FBX, Alembic, Grease Pencil
  vector IO, OIDN, Freestyle, motion tracking, OpenXR, and JPEG2000/WebP/DPX. The six hardware
  rows now say the evidence is unavailable only on this WSL2 host, name the driver-operated Apple
  M4 Pro path, and reject the falsified Windows-reboot route. The focused contract passes 16/33/6
  with 57 fail-closed mutations; its exact staged candidate, the updated S7 contract, REUSE, and
  container-backed M0 regression are green. M8 and M1-M8 retain their existing strict receipt,
  APPLY, browser, performance, and release boundaries. See
  `notes/m8-deferral-registry-completeness-20260826.md`.
- [x] **AUDIT-20260825-R12 [driver] (`5256369..debb502`):** adversarial review of the exact
  25-commit range found no parity theater, receipt promotion, upstream mutation, dependency drift,
  or P0 regression. It found three major device-free M4 defects: ordinary text keys disappear while
  the IME textarea owns focus; focus-loss generations do not order the boundary before later queued
  input; and a simultaneous second window creates split manager/canvas ownership. One low M8 soak
  debt and two minor process/documentation findings are also recorded. See
  `reports/audit-20260825-r12.md`.
- [x] **AUDIT-R12-M4-IME-NONCOMPOSING-KEY-BRIDGE [ghost-web] (`cc2a844`):** the shipping IME
  profile transactionally registers raw key-down/up on both Blender-owned focus elements, while an
  earlier textarea listener suppresses active-composition process keys before Emscripten can proxy
  them. Trusted ASCII/navigation/control/clipboard input, composition nonduplication, external-focus
  suppression, and replacement lifecycle pass the real worker; the relinked Blender product commits
  `BWKEY_012X` through its stock object-name editor and reads it back through Python/GHOST clipboard.
  Seventeen source mutations, baked-runtime coverage, the 16-listener native/wasm matrix, CAPTURE
  inventory, and REUSE are green. Physical OS IME/dead-key evidence remains separately blocked.
  See `notes/m4-ime-noncomposing-key-bridge-20260826.md`.
- [x] **AUDIT-R12-M4-FOCUS-INPUT-BARRIER [ghost-web] (`4056b2a`):** queued canvas focus callbacks
  now consume the capture-time loss before consulting the later live DOM, placing the boundary and
  later keyboard/pointer input in Emscripten's existing worker callback order. The fail-first exact
  inversion becomes deactivate/activate before immediate key and mouse down/up; 20 source mutations,
  adjacent focus/IME/input/lifecycle contracts, native/wasm32 integration, locked CAPTURE relink,
  exact-artifact fallback boot, split producer checks, and REUSE are green. Required M4 remains
  hardware-pixel RED. See `notes/m4-focus-input-barrier-20260826.md`.
- [x] **AUDIT-R12-M4-SINGLE-CANVAS-SECOND-WINDOW [ghost-web] (`bbe7d27`):** a simultaneous second
  valid `createWindow()` is rejected before context construction, preserving the original system,
  callback, manager, hit-test, and presentation owner; disposal still permits a replacement. The
  fail-first real-worker case reproduced the split as bitmask 75, while the final seven-bit case,
  38-mutation contract, native/wasm32 matrix, CAPTURE product, and fallback boot are green. The
  named multi-window deferral remains truthful. See
  `notes/m4-single-canvas-second-window-20260826.md`.
- [x] **AUDIT-R12-M8-CALLBACK-REGISTRATION-SOAK [ghost-web] COMPLETE:** the unbounded retained
  record vector is replaced by a fixed 4,096-byte pool of never-recycled opaque tokens; all failed
  and successful attempts consume the hard process budget and exhaustion fails closed. A real
  worker soak holds stale delivery across 128 rolled-back prefixes plus 256 window replacements,
  proves exact token accounting and listener balance, rejects the stale callback, and retains fresh
  input. Native/wasm32 integration, adjacent browser paths, locked CAPTURE relink/no-work, split
  producer checks, fallback product boot, REUSE, and regression preserve their strict boundaries.
  See `notes/m8-callback-registration-soak-20260826.md`.
- [x] **AUDIT-20260826-R13 [driver] (`f5a2d2a`; range `4a437519..1ba4cea`):** adversarial review of the exact
  25-commit range found one high M8 receipt false-green path, three medium Stage-1
  recovery/integrity/memory defects, and two low process findings. It found no upstream/harness/
  oracle/golden/result mutation, promise promotion, dependency-provenance loss, or hidden
  deferral. See `reports/audit-20260826-r13.md`.
- [x] **AUDIT-R13-M8-OBSERVED-CRITICAL-WIRE [driver] (`88bac1b`):** the performance producer now
  records every same-origin request/response through semantic interaction and maps queryless
  GET/200+Brotli responses to exact raw bundle artifacts. Known extra paths enter the critical set;
  unknown, duplicate, queried, unmapped, missing, or non-Brotli responses fail closed. The composer
  independently derives each cold-run set, counts their union, and the final verifier recomputes
  that union plus exact `.br` sizes. Fail-first/final producer, composer, consumer, aggregate, and
  freeze contracts are green. Existing Apple CAPTURE evidence contains 28 `blender_browser.js`
  requests, so the old unique-file projection is no longer treated as a launch receipt; only a
  future exact public-bundle run can establish the real <=15 MB verdict.
- [x] **AUDIT-R13-M8-STAGE1-FAILURE-RECOVERY [driver] (`0147a12`):** the Stage-1 loader now
  shares one in-flight Promise, makes three bounded automatic attempts with clean accounting,
  leaves exhausted operations explicitly retryable, and publishes honest retry/error progress.
  The exact predecessor fails first; final 11-case/12-mutation execution proves concurrent
  single-flight, 503/interrupted-stream recovery, bounded persistent failure, and a later explicit
  retry in the same page. Public minification/provenance, assembly, transport, CAPTURE producer,
  M8 consumer, release-freeze, syntax, REUSE, and container regression preserve their boundaries.
  See `notes/m8-stage1-failure-recovery-20260826.md`.
- [x] **AUDIT-R13-M8-STAGE1-FALLBACK-INTEGRITY [driver] (`288d233`):** the manifest now requires
  an exact non-negative byte total and integral, bounded, contiguous spans covering that total;
  the non-streaming `arrayBuffer()` must match it before any WasmFS write. The exact predecessor
  reports `done` for a truncated fallback; final 16-case/16-mutation execution rejects short,
  long, gapped, out-of-bounds, and uncovered-tail inputs without reaching `Assets ready`.
  Minified provenance, assembly, transport, CAPTURE, M8, freeze, syntax, compliance, and REUSE
  consumers are green. See `notes/m8-stage1-fallback-integrity-20260826.md`.
- [x] **AUDIT-R13-M8-STAGE1-PEAK-MEMORY [driver] (`39b40d7`):** the loader now streams the
  152,362,255-byte/2,963-file payload through one <=16 MiB file buffer plus one <=16 MiB response
  chunk, stages complete files under `/tmp`, and publishes them by zero-copy WasmFS rename only
  after exact response completion. Staged and soak receipts fail closed on the 16/16/32 MiB
  limits, retained buffers, exact peaks, JS heap, and browser RSS. The canonical largest file is
  11,425,316 bytes; the real APPLY browser receipt remains required. See
  `notes/m8-stage1-peak-memory-20260826.md`.
- [ ] **AUDIT-R11-M4-TRUSTED-IME-DEAD-KEY-EVIDENCE [driver -> HUMAN, claimed_by: none,
  blocked-by: AUDIT-R12-M4-IME-NONCOMPOSING-KEY-BRIDGE then trusted physical input session]:** on
  a supported headed browser/OS, exercise a browser-generated OS IME composition and a physical
  dead-key sequence through the real product;
  bind trusted-event evidence and Blender text state before resolving `ime-dead-keys`.
- [ ] **AUDIT-20260820-HISTORY [driver -> HUMAN]:** coordinate preservation-equivalent author
  repair for the eight `Hivemind Agent` commits in the audit range; three also need the required
  `Assisted-by:` trailer. R11 additionally found human-authored commits `0aa45be` and `62ca5fb`
  missing that trailer. R13 adds human-authored commits `11a4afd` and `61258e3`, whose literal
  `\\n\\nAssisted-by` text is not a parseable trailer. **blocked-by external-mirror/history-rewrite
  coordination.**

## M6 — RENDER PARITY: pre-work COMPLETE (2026-08-06, both driver-verified)

- [x] **M6.pre-a Cycles-CPU compile probe (96e3a0f):** COMPILES CLEAN wasm32, zero source
  changes, EMPTY dep shopping list (scalar KERNEL_ARCH auto-selected — SIMD flag checks fail
  under emcc; Embree/OIDN/PGL gated off, BVH2 fallback). M1.3 revisit = CLOSED compile-clear.
  Remaining M6-render: link + kernel execution under -pthread + parity (~4-8d est).
  -Wpthreads-mem-growth flagged as runtime posture item. notes/m6-cycles-probe.md.
- [x] **M6.pre-b oracle goldens staged (1fe4360+b279bd9):** 77 tests (workbench 20, EEVEE 30,
  Cycles-CPU 27), oracle 72/77 on pin-accurate binary (self-reports fbe6228 — also resolves
  the m5-prep release-vs-pin caveat); the 5 fails validated = adapter deltas, 2 verbatim in
  upstream's own EEVEE BLOCKLIST (comparator proven faithful). Thresholds verbatim-cited,
  determinism DET_ALL_PASS, blacklist mechanism proven + committed empty (M6 re-derives on
  the pinned WebGPU adapter). EEVEE oracle = native macOS Metal headless (mirrors Blender
  CI). Runner: sandbox/m6-prep/run_oracle_renders.sh (exit-code-primary, m2b pattern).
  M6 wasm entry: Cycles-CPU first (no GPU needed), then workbench/EEVEE offscreen PNG path.

- [x] **M6.gpu Phase A clean 50-scene rescore (99a83d2):** fresh headed-browser manifests,
  zero reuse/RIG-FAIL/crash/duplicates. Workbench is 12 PASS / 8 FAIL. EEVEE is 28
  NO-CAPTURE / 2 render-start timeouts, with zero readback kicks and zero captured device
  bytes across all 30 scenes. The exact residual split is recorded above; the census holds
  149 PASS / 7 FAIL / 2 CRASH and static_shaders 956/973.

- [x] **M3-GATE [driver, technical-contract reconciliation]:** the accepted successor rounds
  closed the stale r16 shader/family queue and froze the literal release contract: exact
  checked-in 197-test and 1,003-shader identities, 197/197 plus DrawWebGPU 2/2 and cold/warm
  1,003/1,003 historical Dawn/Metal proof, raw-evidence and no-work verification, and canonical
  clean-pin source reconstruction. `ledger/deferred.json` records the five named census
  dispositions (four active, signed-I10 resolved), `notes/gpu-gate-blacklist.md` separately
  justifies the three blacklist groups, `patches/series` retains the ordered development history,
  and `harness/run.sh` routes M3 through the fail-closed strict-final adapter. This closes only the
  obsolete implementation/accounting queue. The existing **M3-LINUX-REPLAY** item owns the fresh
  Dawn/Vulkan exact-identity receipt, aggregate run, and `<promise>M3_GPU_BACKEND</promise>`;
  those remain blocked by s7's llvmpipe-only adapter and must not be inferred from this checkbox.
- [x] **M3-boundary [driver]** CLOSED (`d7dcebf`, current accounting reverified): all five
  census dispositions are registered in `ledger/deferred.json` with named blockers, impacts,
  revisit conditions, and evidence: storage-texture atomics, vertex-stage read-write storage,
  depth-aspect buffer uploads, signed I10 vertex data, and subpass inputs. Patch 0119 later
  resolved I10 and its ledger row remains as an explicit resolved audit trail; the other four
  remain deferred. `notes/gpu-gate-blacklist.md` separately justifies the R32F, runtime-generated
  OpenSubdiv, and Metal-only census exclusions. This closes stale boundary accounting only; a
  fresh Linux M3 receipt remains blocked by the named s7 hardware-adapter condition.
- Remaining shader-coverage tail after 0050 (492 fail): Tint env/capability buckets 100+93,
  gl_PointSize 54, textureSample 32, nan-f32 30 (=F3b), uniform-control-flow 25. Lane A queue.

**ROUND 8 RESULT (lane B, 2026-08-05):** REAL-PATH BLEND GREEN — `GPUWebGPUTest.blend_*`
**12/12 PASS** on the native Dawn/Metal backend (lane A F1 populate_builtins + F2 codegen
`gl_Position.y=-gl_Position.y`@wgpu_shader.cc:787, together with the lane-B halves below).
Evidence: `sandbox/gpu-render-harness/evidence/real_path_frames_blend.{png,txt}`.
- **M3.F2 lane-B halves DONE:** patch 0044 (10498c0) pipeline front-face swap; patch 0045
  (2acb81b) framebuffer render-target readback row-flip (texture_* gate held 64/64, path
  untouched). Lane A's codegen flip also landed → F2 fully satisfied for blend.
- **M3.F4 lane-B attachment view DONE:** patch 0046 (cc355c1) — single-layer attachment view;
  the Dawn "layer count (256)… greater than 1" error is gone. Remainder is NOT lane-B code:
  (a) immediate_* CRASH = `imm` never constructed — needs 3-line wiring in wgpu_context.cc
  (LANE A): ctor `imm=new WGPUImmediate()` + activate/deactivate immActivate/immDeactivate
  (WGPUImmediate class is complete). (b) framebuffer_multi_viewport CRASH root cause is now a
  lane-A shader gap (`'gpu_ViewportIndex' : undeclared identifier`@wgpu_shader.cc:1108) +
  fundamental multi-pass layer/viewport emulation (no viewport-array / no gl_Layer in WebGPU)
  — driver decision. (c) push_constants (10 fail) = `WGPUBackend::compute_dispatch` empty stub
  @wgpu_backend.cc:62 (LANE A) — compute pass unimplemented. Full detail +
  characterizations in notes/gpu-laneB-integration.md "ROUND 8".
