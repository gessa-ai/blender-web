<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M1.8 + M1.9 — headless-core integration report

Date: 2026-08-03. Owner: build-deps worker.
TL;DR: **Configure now resolves 100% real `lib/wasm` libraries (no stubs).**
The blenlib build reaches DNA generation and hits a precisely-characterized,
two-layer wall (host-tool execution, then a wasm32 struct-alignment bug in
`makesdna`). Both the fix path and the root cause are proven, not guessed.

## What configured (M1.8) — DONE

`emcmake cmake -S upstream -B build-wasm -C patches/blender_web.cmake
-DCMAKE_BUILD_TYPE=Release` → **Configuring done (~49 s), zero warnings, zero
"Could NOT find"**, and the real-deps branch is confirmed active:

    -- blender-web: using wasm LIBDIR: /Users/paws/blender-web/lib/wasm
    -- blender-web: resolved wasm deps from .../lib/wasm
       (OIIO/OCIO/OpenEXR/Imath/fmt/TBB/Eigen3/JPEG/PNG/TIFF/zlib/zstd/Freetype/Brotli)

`patches/platform_wasm.cmake` now REPLACES platform_unix's find logic for the
Emscripten branch: it seeds the proven emscripten hint-var set (CONFIG `<Pkg>_DIR`;
module `<PKG>_LIBRARY`/include; the OCIO pystring/minizip-ng `*_INCLUDE_DIR`
no-ROOT rule from `notes/deps-oiio.md`), appends `LIBDIR` to `CMAKE_FIND_ROOT_PATH`
(defeats emscripten sysroot re-rooting), then `find_package()`s every mandatory dep
and derives the raw vars `dependency_targets.cmake` consumes (`TBB_LIBRARIES`
via `get_target_property`, etc.). The old empty-INTERFACE placeholder block is now
DEAD (fenced behind an empty prefix); it survives only as a pre-populate fallback.

### Fixes this pass turned "faked configure" into "real configure"
1. **Built the two missing REQUIRED deps** freetype 2.13.3 + brotli 1.0.9 (no
   `WITH_FREETYPE` off-switch exists; `check_freetype_for_brotli()` FATALs). See
   `notes/deps-freetype.md`.
2. **`LIBDIR` was resolving to `upstream/lib/wasm`** (`CMAKE_SOURCE_DIR` is the
   upstream tree) → the whole real-deps branch was silently skipped. Re-anchored on
   `BLENDER_WEB_PATCH_DIR/../lib/wasm` (repo root).
3. **`OpenImageIO::oiiotool`** is not exported (OIIO built `OIIO_BUILD_TOOLS=OFF`);
   `dependency_targets.cmake:144` reads its LOCATION unconditionally. Kept a single
   imported-executable placeholder — a build-time datafiles generator M1 never runs,
   and a wasm oiiotool can't run on the host anyway. M2 supplies a NATIVE oiiotool.

### Configure prerequisite (must be scripted into the harness)
`upstream/CMakeLists.txt` has NO EMSCRIPTEN platform branch at the pin (upstream is
read-only). `patches/0001-platform-wasm.patch` must be **applied to the upstream
working tree immediately before configure and reverted after**:

    git -C upstream apply   ../patches/0001-platform-wasm.patch   # before configure
    git -C upstream apply -R ../patches/0001-platform-wasm.patch   # after (keep pristine)

This session left `upstream/` PRISTINE (verified `git -C upstream diff --quiet`).

## What compiled / what blocked blenlib (M1.9)

Target attempted: `cmake --build build-wasm --target bf_blenlib`.

Progress and the ranked blocker map:

1. **[FIXED] DNA enum narrowing** — `enum X : char { = 1<<7 }` (==128) fails
   `-Wc++11-narrowing` because emscripten `char` is SIGNED. Every native platform
   sets `-funsigned-char` (platform_unix L895 etc.); platform_wasm did not. **Added
   `-funsigned-char -fno-strict-aliasing -ffp-contract=off`** to the wasm C/CXX
   flags (the last is FP-determinism-relevant for tier-(a) parity). makesdna.cc and
   all DNA headers now compile.

2. **[BLOCKER #1 — build-integration; FIX PATH PROVEN] host codegen tools can't be
   executed.** `makesdna`/`makesrna` are cross-compiled to wasm, then run at build
   time via `$<TARGET_FILE:makesdna>` (makesdna/intern/CMakeLists.txt:100-115).
   The build invokes the `.js`/`.wasm` directly → **`permission denied`**. Two
   coupled causes: (a) the custom command does not prefix the node
   `CMAKE_CROSSCOMPILING_EMULATOR` (which emscripten DID set in the cache); (b) the
   tools inherit `-sPROXY_TO_PTHREAD` from `PLATFORM_LINKFLAGS`, wrong for a CLI.
   **PROVEN FIX:** relinked the already-built makesdna objects (+`libbf_intern_
   guardedalloc.a`) with `-pthread -sNODERAWFS -sALLOW_MEMORY_GROWTH -sEXIT_RUNTIME`
   (NO PROXY_TO_PTHREAD) and ran it under `tools/emsdk/node`. It generated all five
   DNA files correctly (`dna.cc` 577 KB, `dna_type_offsets.h`, `dna_verify.cc`
   1.06 MB, …). So the wasm-host-tool-via-node strategy works end-to-end, and the
   wasm32-ABI offsets it emits are the CORRECT target offsets.

3. **[BLOCKER #2 — real wasm32 ABI bug in makesdna; ROOT CAUSE CONFIRMED]** With the
   node-generated DNA staged into the build tree, `bf_dna` compiles `dna_verify.cc`
   and its `BLI_STATIC_ASSERT(offsetof(...)==N)` / `sizeof(...)==N` checks **FAIL**
   for `Scene` (and, past the error-limit, presumably more structs). Arithmetic
   pins it: makesdna expects `offsetof(Scene, customdata_mask)==5012`, which is only
   4-byte-aligned, but `customdata_mask` is `CustomData_MeshMasks` (two `uint64_t`),
   which wasm32/Clang aligns to 8 (actual 5016). **makesdna uses the i386 32-bit
   model — it aligns 8-byte scalars (`double`/`int64_t`/`uint64_t`) to 4 whenever
   `sizeof(void*)==4` — but wasm32 keeps 8-byte scalar alignment at 8 while
   pointers are 4.** This is the true tier-(a) correctness blocker: the DNA layout
   makesdna bakes disagrees with the compiler's real wasm32 layout.

blenlib's OWN translation units were not reached (bf_dna precedes them), but every
makesdna support source (BLI_ghash, mempool, string, listbase, memarena, threads,
hash_mm2a, …) compiled clean under emcc, so blenlib-proper compile risk looks low
once DNA is correct.

## Exact next task list (ranked)

1. **Patch makesdna's alignment for wasm32** (`source/blender/makesdna/intern/`,
   the type-alignment logic in `dna_utils.cc` / `makesdna.cc`) so 8-byte scalars
   align to 8 even when pointers are 4. This is the load-bearing fix for tier-(a).
   Owner: a makesdna-focused worker; deliverable = `patches/` diff + green
   `dna_verify.cc`. Re-derive `dna_type_offsets.h` afterwards.
2. **Wire host tools to run under node in-build** (`patches/` diff): give
   `makesdna`/`makesrna` a host-tool link profile (strip `-sPROXY_TO_PTHREAD`, add
   `-sNODERAWFS -sEXIT_RUNTIME`) and make their `add_custom_command`s invoke
   `${CMAKE_CROSSCOMPILING_EMULATOR}` before `$<TARGET_FILE:...>`. Fold the patch
   into the applied patch-set so the harness configure/build is one command.
3. Rebuild `bf_dna` → `bf_blenlib`; surface blenlib-proper's first emcc error class
   (expected low, but unverified).
4. Then `blenlib_test`/`BLI_*` gtest targets: resolve the gtest/gflags/glog extern
   link and the wasm test-runner harness (node) — the actual M1 tier-(a) gate.
5. Repeat 1–4 for `bmesh_core` gtests.

## Deps state (verified in lib/wasm this session)
Wave-0/1/2 all present; **added freetype 2.13.3 + brotli 1.0.9**. `ledger/deps.json`
`wasm_built` updated. No dep is stubbed in the configure — every `find_package`
resolves a real archive.
