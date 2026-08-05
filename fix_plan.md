<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# fix_plan.md — active milestone: M1 CORE BOOTS + FREE ORACLE

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
- [ ] **M0-hygiene [harness]** Fold `git -C upstream lfs pull --include "release/datafiles/*"`
  into the pinned-checkout step so every worker starts with complete data (recon blocker #1:
  `startup.blend` was a 131 B LFS pointer → `CMakeLists.txt:96` fatal; pulled ad-hoc this round,
  not yet in the setup script). Harness-locked — reconcile at the M1 boundary.
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

- [ ] **M1.1 [build-deps]** Make `patches/0001-platform-wasm.patch` (an `if(EMSCRIPTEN)` branch
  placed *before* the `UNIX AND NOT APPLE` branch at `CMakeLists.txt:~1541`, → `include(platform_wasm)`)
  + `patches/platform_wasm.cmake` the **canonical** shim; **retire the throwaway
  `patches/cmake_wasm/platform_unix.cmake` shadow-stub** (two competing mechanisms exist from
  round 1 — keep the auditable patch, delete the shadow). Verify `git apply --check
  --directory=upstream` clean + upstream `status --porcelain` empty.
- [ ] **M1.2 [build-deps]** In `platform_wasm.cmake`: drop `find_package(Epoxy REQUIRED)` (no GL
  consumer in a WebGPU build); gate `Vulkan`/`ShaderC` `find_package` **OFF for headless M1**
  (shader chain is M3, no GPU in tier-a); set C++ exceptions posture globally (`-fexceptions` —
  OIIO/CPython need it). Verify configure passes the Epoxy/Vulkan stage with no libs present.
- [ ] **M1.3 [build-deps]** In `blender_web.cmake` force **`WITH_CYCLES OFF`** for M1 core-boots
  (avoid Embree/OSL find drag through empty LIBDIR; revisit at M6) AND **`WITH_PYTHON OFF`**
  (verified: Python is NOT on the tier-(a) gtest link path — this keeps CPython + the emcc-version
  toolchain decision off the M1 critical path entirely; re-enabled in M2.3). Verify configure
  reaches neither Embree nor `Python.h` checks.

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
- [ ] **M2.8 [compliance]** `ledger/deps.json` complete: license + rationale for every harvested
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
- [ ] **M3.T4 [gpu-backend]** Backend registration + skeleton + NATIVE gpu-suite link:
  GPU_BACKEND_WEBGPU (1<<2 + DNA userpref mirror), gpu_context.cc 7 switch arms, gpu/webgpu/
  WGPUBackend (21 pure-virtual stubs, context_alloc → real WGPUContext holding the GHOST
  device) + WGPUContext, gpu/CMakeLists WITH_WEBGPU block, configure build-native-gpu with
  -DWITH_WEBGPU_BACKEND=ON, link the `gpu` suite binary; VERIFY selection_set(WEBGPU) →
  SetUpTestSuite reaches a live context. **DISPATCHED (same worker).**
- [x] **M3.T7.pre [gpu-backend]** COMPLETE (4f36210, notes/gpu-t7pre-findings.md): shader-
  compiler module standalone-proven 4/4 on live Dawn (bindmap re-validated; type-inference
  table COMPLETE + live-validated for Float/Shadow/Uint arms; compute+SSBO+atomic pipeline
  created → **T8's R6 pre-cleared**; negative control holds). Sampler arrays: **broken in
  Tint's reader itself** ("arrays of handle types are not supported", parser.cc:200, pre-
  split) → **T7 must unroll sampler arrays at GLSL codegen**; map is per-element-ready.
  **Integration hazard caught: shaderc's bundled SPIRV-Tools vs Tint's static one must not
  meet in a link — use Blender's shaderc shared dylib.** T7 = wiring, not development.
- [ ] **M3.T4–T10 [gpu-backend]** Skeleton→context→buffers→shader-pipeline→compute→textures→
  framebuffer/state/immediate/batch, each gated on Blender's own gpu tests vs native Dawn
  (full list + verify criteria: notes/gpu-webgpu-architecture.md §7). Gate: full gpu suite
  green on Dawn → `<promise>M3_GPU_BACKEND</promise>`. T4 in flight; **T9.pre dispatched**
  (format tables + data conversion standalone, the other development-heavy chunk).

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
- [ ] **M3.F4 [gpu-backend laneB]** framebuffer_multi_viewport: attachment_view builds a
  256-layer view — needs single-layer 2D view (+ characterize multi-viewport emulation, no
  viewport-array in WebGPU); immediate_* CRASH(139) — WGPUImmediate not GPU_init-safe;
  push_constants fails on values only (compute dispatch writes nothing — compute path, may
  defer to T8 proper). DISPATCHED round 8.
- [ ] **M3.F5 [driver → worker]** The instant-green vehicle: rebuild `sandbox/gpu-render-harness`
  for FIRST IN-TAB PIXELS (closure list in notes/gpu-wasm-render-harness.md; comment-strip
  blocker + pthread pool noted there). **DISPATCHED 2026-08-05 (blend green landed).**
- [ ] **M3.F6 [gpu-backend laneA r10]** Draw-set completion: (a) imm wiring — 3 lines in
  wgpu_context.cc (ctor imm=new WGPUImmediate(); activate/deactivate immActivate/Deactivate,
  vk_context.cc:43/141/60 pattern) → immediate_*; (b) compute_dispatch real implementation
  (wgpu_backend.cc:62 empty stub; T7.pre proved compute+SSBO+atomic pipeline on live Dawn) →
  push_constants 10 tests; (c) gpu_ViewportIndex declared in codegen (wgpu_shader.cc:1108) so
  multi_viewport compiles — CRASH→honest fail only. DISPATCHED round 10.
- [ ] **M3.F7 [driver DECISION, deferred]** multi_viewport faithful pass needs layer/viewport
  emulation (WebGPU: no viewport-array, no gl_Layer) — decide approach (multi-pass per
  viewport vs instance+clip) AFTER F6 lands; one test, not gate-critical yet.
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
