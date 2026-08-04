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
- [ ] **M1.11 [harness]** Link + run the **bmesh_core gtest** suite under node → tier-(a) gate 2⁄2.
  **blocked-by M1.13, M1.14, M1.15, M1.15b.** DECIDED (recon 2026-08-03, notes/m1-closure-recon.md):
  standalone `bmesh_core_test` via `WITH_TESTS_SINGLE_BINARY OFF` flip — NOT hand-link, NOT
  combined blender_test.
- [ ] **M1.12 [harness]** `.blend` corpus loads with state-dump parity vs the native oracle →
  completes **`<promise>M1_CORE_BOOTS</promise>`**. **blocked-by M1.11.**

### M1 remainder — port the core libs bmesh needs (dispatched 2026-08-03, post-disk-clear)

- [ ] **M1.13 [build-deps]** `bf_blenkernel` compiles to wasm32. ROUND-1 RESULT (2026-08-03):
  0/4 targets, ALL order-only-gated on GPU shader codegen; shader_tool-as-wasm mis-tokenizes
  ~6 EEVEE shaders (notes/m1-shader-codegen-wasm.md). Wiring fixes proven (906 rc-126→0).
  → **ADR-002 decided: shader_tool+datatoc run NATIVE** (ABI-baking makesdna/makesrna stay
  wasm). **blocked-by M1.13a.** claimed_by: worker-1 (continuing).
- [ ] **M1.13a [build-deps]** ADR-002 implementation: native shader_tool+datatoc in
  build-hosttools/ (clang/NEON path); wasm tree's custom commands invoke them under
  EMSCRIPTEN; byte-identity audit (wasm-generated outputs == native outputs for the clean
  subset + all datatoc); rework wip-0007 accordingly (drop simd.hh widening from series).
- [ ] **M1.14 [build-deps]** `bf_depsgraph` + `bf_blentranslation` + `bf_animrig` to wasm32
  (same worker, serial in one build tree; patch 0008+). **blocked-by M1.13** (shared tree).
- [ ] **M1.15 [build-deps]** Host tools verified under node on the real path: makesrna executes
  (first verification — forced by bf_rna before blenkernel) + datatoc/shader_tool two-half fixes
  (exact lines in notes/m1-closure-recon.md). (In worker scope when hit during M1.13/14.)
- [ ] **M1.15b [build-deps]** **The wide grind (recon-sized):** `WITH_TESTS_SINGLE_BINARY OFF`
  in blender_web.cmake, then `ninja bmesh_core_test` drives the remaining **~150-archive**
  closure (gpu frontend w/ backends OFF, draw, nodes, imbuf+codecs, modifiers, render,
  sequencer, windowmanager, ~18 bf_editor_*, blenloader, blenfont, asset_system, functions,
  ikplugin, shader_fx, simulation, small intern/extern leaves). All hazard-scanned CLEAN —
  expect mechanical fixes, not ABI work. **blocked-by M1.13, M1.14.**
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
- [ ] **M2.3 [python-wasm]** Harvest `libpython3.13.a` + `include/python3.13/` + `Lib/` → `lib/wasm`;
  **re-enable `WITH_PYTHON ON`** in `blender_web.cmake`, wire PYTHON_* vars. **blocked-by M2.2.**
- [x] **M2.4 [build-deps]** Already done during M1: OCIO subtree forced by OIIO 3.x hard-dep
  (M1.6, commit 5e379cd), freetype+brotli forced by no-off-switch (M1.8, 25ad33a). Verified
  present in lib/wasm/lib (driver, 2026-08-03): libOpenColorIO/libfreetype/libbrotli*/
  libyaml-cpp/libexpat/libpystring/libminizip.
- [ ] **M2.5 [python-wasm]** `import bpy` headless in node/worker (tier-(b) entry). **blocked-by M2.3, M2.4.**
- [ ] **M2.6 [harness]** Stock `--background --factory-startup` operator/bpy suite subset passes vs
  oracle → tier-(b) gate → **`<promise>M2_DEPS_PYTHON</promise>`**. **blocked-by M2.5.**
- [x] **M2.7 [python-wasm]** DONE 2026-08-03 (7c1722f, notes/python-emcc605-probe.md §M2.7):
  JSPI links clean with BOTH EH models (no emcc refusals); setjmp/longjmp survives
  suspend/resume under the Asyncify proxy in both (libjpeg error path + libpython embed PASS
  baseline). RESIDUAL: emsdk node v22 lacks the new `WebAssembly.Suspending` API → any -sJSPI
  module aborts at init under node<23; true-JSPI runtime validation = tools-local node≥23
  (follow-up dispatched) + mandatory M4 browser smoke (Chrome ≥137/Playwright, suspending).
  Python stays synchronous on the proxied main thread per ADR-001.
- [ ] **M2.8 [compliance]** `ledger/deps.json` complete: license + rationale for every harvested
  dep, runtime deps GPL-compatible only. **blocked-by M1.6, M2.3.**

---

## M3 — WEBGPU BACKEND (native Dawn) — architecture DONE (notes/gpu-webgpu-architecture.md
## + notes/gpu-shader-chain.md, 2026-08-03); T-tasks runnable in parallel with M1/M2 tails

Measured basis: Vulkan backend = 28,062 LOC; webgpu/ estimate **13–17k** (render_graph 6,658
LOC eliminated by WebGPU's implicit model; skeleton = 30 wgpu_ file-pairs ≈ 14.3k). Backend
surface = 19 pure-virtuals; StateManager/Immediate come from Context, not backend factories.
Top risks: R1 combined-sampler binding remap (T2 probes), R2 Dawn+Tint native build (T1
probes), R3 geometry-stage gap (ZERO geometry create-infos at pin → M6 concern, not M3).

- [ ] **M3.T1 [gpu-backend]** Dawn+Tint native toolchain probe (R2): build Dawn (pinned commit,
  SPV reader ON) on this Mac; standalone .cc: GLSL→shaderc→SPIR-V→Tint→WGSL→CreateShaderModule.
  Verify: WGSL prints, module validates, exit 0. **Blocks T2+. DISPATCHED 2026-08-03.**
- [ ] **M3.T2 [gpu-backend]** Combined-sampler binding audit (R1): sampler2D+push-const+UBO
  create-info through T1 harness; document deterministic @group/@binding map. **blocked-by T1.**
- [ ] **M3.T3 [gpu-backend]** GHOST_ContextWGPU offscreen (native Dawn, no surface) +
  WITH_WEBGPU_BACKEND option; headless bin gets live WGPUDevice. **blocked-by T1.**
- [ ] **M3.T4–T10 [gpu-backend]** Skeleton→context→buffers→shader-pipeline→compute→textures→
  framebuffer/state/immediate/batch, each gated on Blender's own gpu tests vs native Dawn
  (full list + verify criteria: notes/gpu-webgpu-architecture.md §7). Gate: full gpu suite
  green on Dawn → `<promise>M3_GPU_BACKEND</promise>`.
