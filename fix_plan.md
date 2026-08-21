<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# fix_plan.md — active milestones: M3 WEBGPU BACKEND (technical contract frozen; fresh Linux receipt blocked by s7) + M4 FIRST PIXELS (UI renders in-tab, polish rounds)

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

### Dep superbuild (BLOCKED-BY M0.8-CRIT disk)

- [ ] **M1.4 [build-deps]** Cross-compile Wave-0 leaves → `lib/wasm`: zlib, zstd, fmt, Imath,
  Eigen(hdr), robin-map(hdr), pugixml, libjpeg-turbo (`WITH_SIMD=OFF`), libpng, TBB. Harvest via
  `-DHARVEST_TARGET`. **blocked-by M0.8-CRIT.** Verify each `.a` + headers land under `lib/wasm`.
- [ ] **M1.5 [build-deps]** Cross-compile Wave-1: OpenEXR (Imath,zlib), libtiff (zlib,jpeg).
  **blocked-by M1.4.**
- [ ] **M1.6 [build-deps]** Cross-compile Wave-2: **OpenImageIO** trimmed to EXR/TIFF/PNG/JPEG
  readers only (deps: EXR,Imath,fmt,robin-map,pugixml,tiff,jpeg,png,zlib,TBB), PLUS build a
  **native host `oiiotool`** (runs at Blender build time for data-gen). **blocked-by M1.5.**
- [ ] **M1.7 [build-deps]** TBB threading smoke over emscripten `-pthread` + SharedArrayBuffer
  (highest-risk mandatory dep, wasm-diff 4). **blocked-by M1.4** (TBB build). Verify a parallel_for
  runs in a node worker.

### Real configure → compile → link → run

- [ ] **M1.8 [build-deps]** Point `platform_wasm.cmake` `find_package()`s at the populated
  `lib/wasm`; run `emcmake cmake … -C patches/blender_web.cmake` to **Configuring done +
  Generating done with REAL deps (zero placeholder targets)**. **blocked-by M1.6, M1.2, M1.3.**
- [ ] **M1.9 [build-deps]** `ninja` the headless core (blenlib, bmesh, intern/*, extern/*, DNA/RNA,
  blenkernel, depsgraph; GPU/UI stubbed) to wasm; fix compile errors at root cause, log recurring
  fixes in `notes/porting-patterns.md`. **blocked-by M1.8.**
- [x] **M1.10 [harness]** blenlib gtests GREEN on wasm/node: **1655/1665**, 10 non-passes all
  characterized non-faithfulness (9 fenv deferral + 1 macOS-host chdir). `ledger/results/m1.json`.
  Harness `m1` scope registration deferred to the M1-boundary reconcile (H-4).
- [x] **M1.11 [harness]** **TIER-(a) GATE 2/2 GREEN** (2026-08-04, driver): bmesh_core_test.js
  linked (62.1MB, ~200 archives, SINGLE_BINARY=OFF standalone route) + runs under node: **1/1
  PASSED, exit 0, 116ms** — verified = the FULL upstream suite (bmesh_core_test.cc has exactly
  one TEST_F, BMVertCreate). One link fix: patch 0009 (unguarded WITH_PYTHON=OFF BPY_ call
  sites in interface_handlers.cc — latent upstream bug). m1.json 5/5, gate green. Warts
  recorded: OIIO physical_memory assert-print, OCIO fallback (both environmental, non-fatal).
- [ ] **M1.12 [harness]** `.blend` corpus loads with state-dump parity vs the native oracle →
  completes **`<promise>M1_CORE_BOOTS</promise>`**. **blocked-by M1.11.** ORACLE-SIDE DONE
  (0121ea3): 9-file corpus (LFS corpus is ALL pointer stubs — 1965 files; only startup.blend
  real; corpus self-authored via oracle), deterministic dumps (floats quantized out, 9/9
  two-process byte-identical), compare tool self-tested; candidates staged sandbox/corpus-prep/
  (tests/golden install = driver, at boundary, + reuse dep5 entries for fixtures). SEQUENCING
  DECIDED: wasm-side runs the SAME bpy dump under wasm right after M2.3's WITH_PYTHON flip
  (no duplicate C++ dumper); LFS corpus pull = post-gate coverage extension (versioning/GP3/
  physics), boundary decision.

### M1 remainder — port the core libs bmesh needs (dispatched 2026-08-03, post-disk-clear)

- [x] **M1.13 + M1.13a + M1.14 [build-deps]** ALL GREEN (01ddce3, driver-verified): blenkernel
  34.4MB/288 obj + depsgraph + blentranslation + animrig on wasm32. ADR-002 executed: native
  shader_tool+datatoc (scripts/build-hosttools.sh, FATAL_ERROR guard in platform_wasm.cmake);
  **byte-identity audit PASS** — 752+25 datatoc + 66+466 shader_tool identical, all 44 stale
  diffs = wasm-tool bugs (20 crash, 24 SILENT-CORRUPT → native tools necessary, not just
  convenient), 0 target-dependence. Fixes: 1 LP64 shift (image.cc 1<<32, patch 0008) + host
  PYTHON_EXECUTABLE for discover_nodes.py (Class-3b, porting-patterns.md). Series 0001-0008.
  makesrna first-execution confirmed. **→ CODEGEN-GREEN: wave-2 fan-out FIRED.**
- [ ] **M1.15 [build-deps]** Host tools verified under node on the real path: makesrna executes
  (first verification — forced by bf_rna before blenkernel) + datatoc/shader_tool two-half fixes
  (exact lines in notes/m1-closure-recon.md). (In worker scope when hit during M1.13/14.)
- [ ] **M1.15b [build-deps]** **The wide grind — PARTITIONED (45ed7ab,
  notes/m1-wave2-partition.md):** 90 unbuilt archives / 2147 TU, PROVEN compile-independent
  (object rules order-depend only on codegen, never sibling .a) → **5-way fan-out fires on
  CODEGEN-GREEN (M1.13a), not blenkernel-green.** P1 gpu/draw/wm/render/imbuf (341 TU,
  HIGH-novel → strongest worker) | P2 kernel hub incl. blenkernel (453, current worker
  continues) | P3 bmesh/nodes/modifiers (479, codex candidate) | P4 editor tools (430) |
  P5 editor spaces (444). Patch ranges reserved P1:0100-0119 … P5:0180-0199. Cross-partition
  escalations: DNA/RNA-regen fixes → driver-only; ED_*.hh shared-header seam (P4/P5) → P4
  owns, P5 requests. Driver's serialized tail: SINGLE_BINARY OFF flip + `ninja
  bmesh_core_test`. **blocked-by M1.13a (tree in use until then).**
- [ ] **M1.16 [driver]** M1-boundary harness reconcile: lift lock, register `m1` scope per H-4
  (blenlib assert 1655/10-characterized), add bmesh check once M1.11 lands, re-lock, re-run
  `--scope m0` + `--regress`. **blocked-by M1.11.**

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
- [ ] **M2.5b [DRIVER-DECIDED FIX, dispatched]** Single-source-of-truth: reconstruct consumes
  makesdna's verified padded offsets (check generated dna_type_offsets.h first — may already
  carry them) instead of re-accumulating, `__EMSCRIPTEN__`-guarded, native byte-identical.
  REJECTED: duplicating the alignment model in dna_genfile (model duplication caused this);
  Scene special-case (forbidden); wasm64 flip (invalidates the built world). Patch **0014**.
  Verify: full-table runtime-vs-compiled scan → 0 divergence incl. Scene; boot smoke → BPY_OK;
  corpus load regression once bpy is up.
- [x] **M2.4 [build-deps]** Already done during M1: OCIO subtree forced by OIIO 3.x hard-dep
  (M1.6, commit 5e379cd), freetype+brotli forced by no-off-switch (M1.8, 25ad33a). Verified
  present in lib/wasm/lib (driver, 2026-08-03): libOpenColorIO/libfreetype/libbrotli*/
  libyaml-cpp/libexpat/libpystring/libminizip.
- [ ] **M2.5 [python-wasm]** `import bpy` headless in node/worker (tier-(b) entry). **blocked-by M2.3, M2.4.**
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
- [x] **M2.7 [python-wasm]** DONE 2026-08-03 (7c1722f, notes/python-emcc605-probe.md §M2.7):
  JSPI links clean with BOTH EH models (no emcc refusals); setjmp/longjmp survives
  suspend/resume under the Asyncify proxy in both (libjpeg error path + libpython embed PASS
  baseline). RESIDUAL: emsdk node v22 lacks the new `WebAssembly.Suspending` API → any -sJSPI
  module aborts at init under node<23; true-JSPI runtime validation = tools-local node≥23
  (follow-up dispatched) + mandatory M4 browser smoke (Chrome ≥137/Playwright, suspending).
  Python stays synchronous on the proxied main thread per ADR-001.
  **REAL-JSPI UPDATE (26025bd): proxy was FALSE-POSITIVE for the B-shape — JS-EH cannot
  suspend across setjmp frames (SuspendError); Wasm-EH can. EH sub-decision RE-OPENED for
  M4+ (ADR-001 appendix); M2's no-suspension posture unaffected.**
- [x] **M2.7c [python-wasm PROBE]** DONE (cb4258c) → **ADR-003 ACCEPTED**: active-try breaks
  JS-EH suspension (F1/F3), dormant doesn't (F2); mechanism = invoke_* (7-8 vs Wasm-EH 0);
  CENSUS: libpython static image has ZERO setjmp regions (ctypes/libffi unbuilt), libjpeg's
  setjmp is app-side. DECISION: keep JS-EH stack-wide + hard invariant (suspends only at
  top-level async boundaries, never under active try / live jpeg setjmp) + mandatory M4
  Chrome≥137 topology smoke; Wasm-EH = declared fallback (proven viable, scheduled
  machine-day if triggered).
- [x] **M2.8 [compliance]** `ledger/deps.json` complete: license + rationale for every harvested
  dep, runtime deps GPL-compatible only. **blocked-by M1.6, M2.3.**

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
- [x] **M3.T2 [gpu-backend]** **PASS** (4671835, notes/gpu-binding-map-spec.md = NORMATIVE for
  T7): Blender's scheme = single set-0, dense sequential bindings (vk_shader_interface.cc:205).
  Default Tint per-stage renumbering BREAKS cross-stage layouts (negative control: Dawn REJECTS
  pipeline — R1 confirmed real). Fix: sampler_mappings keyed by original {0,N} → {0,256+N};
  pipeline creation PASSES with explicit BGL. **T7 HARD RULE: non-empty map disables the
  conflict pass — EVERY combined sampler must be mapped.** Open for T7: sampler arrays
  (probe first), SAMPLER_BASE policy, sampler/texture type inference for BGL.
- [x] **M3.T3 [gpu-backend]** **DEVICE-LIVE PROVEN** (66500f0 patch 0011 + 8607fac sandbox
  proof): GHOST_ContextWGPU (130 LOC — half the estimate, WebGPU implicit model) brings up a
  live WGPUDevice+queue on Dawn/Metal via the same createOffscreenContext path; patch 0011 =
  context class + enum + SystemHeadless case + ghost CMake + WITH_WEBGPU_BACKEND option
  (default OFF). Native harness VIABLE: lib/macos_arm64 at pin SHA 5a140a8 out-of-tree (2.4GB,
  upstream untouched), native headless configure 11s. Dawn link = monolithic libwebgpu_dawn.a
  + 7 frameworks; **Tint NOT needed until T7**; C++20 native (no shim). Remaining half folded
  into T4 (notes/gpu-t3-harness.md has the cited edit list + DAWN_ROOT mechanism).
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
  meet in a link — use Blender's shaderc shared dylib.** T7 = wiring, not development.
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
    GPU errors. Next is the frozen 0144 Phase A-prime rebase and its EEVEE acceptance matrix,
    followed by the public async API and caller continuation. No EEVEE pixel-pass claim until a
    non-black result reaches the pinned comparator.
  - [ ] **M6.EEVEE-B [gpu-backend, L2, own lane]:** virtual-shadow-map atlas SSBO-atomic
    emulation (0089-class GPU_WEBGPU-guarded restructure + atlas-as-SSBO bind), yield the
    4 shadow scenes -> 30/30. Gate on shadow goldens; atlas addressing must match exactly.
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
