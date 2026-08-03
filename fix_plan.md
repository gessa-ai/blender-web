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
  **blocked-by M1.13, M1.14, M1.15.** Approach (hand-link vs combined blender_test) per recon verdict.
- [ ] **M1.12 [harness]** `.blend` corpus loads with state-dump parity vs the native oracle →
  completes **`<promise>M1_CORE_BOOTS</promise>`**. **blocked-by M1.11.**

### M1 remainder — port the core libs bmesh needs (dispatched 2026-08-03, post-disk-clear)

- [ ] **M1.13 [build-deps]** `bf_blenkernel` compiles to wasm32 (claimed_by: sonnet-worker-1,
  IN FLIGHT). Expect documented error classes (notes/porting-patterns.md); new fixes → patch 0007.
- [ ] **M1.14 [build-deps]** `bf_depsgraph` + `bf_blentranslation` + `bf_animrig` to wasm32
  (same worker, serial in one build tree; patch 0008+). **blocked-by M1.13** (shared tree).
- [ ] **M1.15 [build-deps]** Host tools verified under node on the real path: makesrna generates
  RNA sources; datatoc rc-126 fixed via blender_web_host_tool() pattern. (In worker scope if hit
  during M1.13/14; else follow-up per recon findings.)
- [ ] **M1.16 [driver]** M1-boundary harness reconcile: lift lock, register `m1` scope per H-4
  (blenlib assert 1655/10-characterized), add bmesh check once M1.11 lands, re-lock, re-run
  `--scope m0` + `--regress`. **blocked-by M1.11.**

---

## M2 — DEPS + PYTHON BOOTS

- [ ] **M2.0 [driver GATE → decision]** Resolve toolchain ABI: **forward-port Pyodide's CPython
  patches to emcc 6.0.5** vs **pin emsdk to Pyodide-validated 4.0.9**. One emcc governs Blender +
  libpython + every dep. Must be settled before M2.1. (Decoupled from M1 by M1.3's WITH_PYTHON OFF.)
- [ ] **M2.1 [python-wasm]** Fetch `Python-3.13.13.tar.xz` (hash `versions.cmake:385`); record in
  `deps.json` (PSF, GPL-compat). **blocked-by M2.0.**
- [ ] **M2.2 [python-wasm]** Build static `libpython3.13.a` (`--disable-shared
  --with-emscripten-target=browser --with-build-python`, `-sSUPPORT_LONGJMP=wasm`); apply the
  minimal Pyodide patch subset where 6.0.5 breaks (SPDX+provenance in `patches/`). **blocked-by M2.1.**
- [ ] **M2.3 [python-wasm]** Harvest `libpython3.13.a` + `include/python3.13/` + `Lib/` → `lib/wasm`;
  **re-enable `WITH_PYTHON ON`** in `blender_web.cmake`, wire PYTHON_* vars. **blocked-by M2.2.**
- [ ] **M2.4 [build-deps]** Cross-compile the M1-deferred deps: OpenColorIO (yaml-cpp, expat,
  pystring, minizip-ng, Imath, zlib) + freetype (brotli-enabled, zlib, png) + brotli. **blocked-by M1.6.**
- [ ] **M2.5 [python-wasm]** `import bpy` headless in node/worker (tier-(b) entry). **blocked-by M2.3, M2.4.**
- [ ] **M2.6 [harness]** Stock `--background --factory-startup` operator/bpy suite subset passes vs
  oracle → tier-(b) gate → **`<promise>M2_DEPS_PYTHON</promise>`**. **blocked-by M2.5.**
- [ ] **M2.7 [python-wasm]** Verify setjmp/longjmp × `-sJSPI` interaction; gate `PyGILState_Ensure`
  off-main-thread jobs to the main thread for now. **blocked-by M2.2.**
- [ ] **M2.8 [compliance]** `ledger/deps.json` complete: license + rationale for every harvested
  dep, runtime deps GPL-compatible only. **blocked-by M1.6, M2.3.**
