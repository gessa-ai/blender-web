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
- [ ] **M0.9 [harness]** CI skeleton — deferred until a GitHub repo exists; revisit at M1 exit.
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
  - [~] **M4.T29/M8 boot-latency: shader-compile block [gpu]: warm path fixed by r51/0128.**
    The OPFS WGSL translation cache cuts retained clean zero-input first-UI timing from
    ~16.3s cold to ~3.0s warm, with 101/101 cached shaders byte-identical and exact shaderc
    v2025.4 plus Tint/Dawn 36cf1fae invalidation pins. Cache format v2 adds bounded payloads
    and a checksum. Cold first draw still compiles inline on the WM worker; async/off-thread
    translation or faithful lazy per-object engine loading remains the cold lever. Feeds the
    M8 30-second bar directly (staged loading is at 27.8s TTFP cold).
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
- [ ] **AUDIT-20260820-HISTORY [driver -> HUMAN]:** coordinate preservation-equivalent author
  repair for the eight `Hivemind Agent` commits in the audit range; three also need the required
  `Assisted-by:` trailer. **blocked-by external-mirror/history-rewrite coordination.**

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
