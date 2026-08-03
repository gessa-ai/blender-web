<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Checkpoint 01 — M0 complete, first Emscripten configure mapped

Date: 2026-08-03 · Pin: `blender-v5.2-release` @ `fbe6228777e7` · emcc 6.0.5 · Blender 5.2.0 oracle

## Outcome first

M0 (toolchain + oracle) is done and green. The first Emscripten configure of Blender has been
attempted and fully mapped: **Blender's own CMake spine configures end-to-end for wasm** —
there is no Emscripten platform wall to fight. The remaining M1/M2 work is a **dependency
cross-compile problem**, and it is currently **blocked by disk space**, not by code.

## What M0 delivered (receipts)

- Pinned checkout at `fbe6228777e7` (tip of `blender-v5.2-release`); LFS datafiles now pulled
  (`startup.blend` 121384 B).
- emsdk / emcc **6.0.5** at `tools/emsdk`; `hello.c`→wasm runs in node; `--use-port=emdawnwebgpu`
  resolves + compiles. Recorded in `oracle/TOOLCHAIN`.
- Native oracle: `Blender 5.2.0 LTS (hash fbe6228777e7)` at `oracle/blender-5.2.0/`; `oracle/bpy.sh`
  headless works; oiiotool 3.1.16 for idiff.
- `harness/buildwrap.sh` (one-line success / first-50-errors fail), `harness/run.sh --scope m0`
  **6/6 GREEN** → `ledger/results/m0.json`; harness+oracle write-locked (`.claude/harness.lock`).
- `patches/blender_web.cmake` drafted (77 `WITH_*`, verified vs upstream). Compliance skeleton
  green: `reuse lint` 39/39.
- Commits: `858cd86` (configure map), `081f2e5` (fleet coordination), `975f38e` (compliance),
  `c3d23f0` (dep set), `7fd4fc3` (python strategy).

## What the first configure proved

With mandatory deps faked as placeholder targets, `emcmake cmake` reaches **`Configuring done
(60.6s)` + `Generating done`**. Every emcc feature/warning probe and `try_compile` passes. So:

- **The port's CMake risk is low.** No `elseif(EMSCRIPTEN)` gap in Blender's logic blocks us; a
  single shim file routes around `platform_unix`. A working patch (`patches/0001-platform-wasm.patch`
  + `platform_wasm.cmake`) already exists and applies with upstream left pristine.
- **The dep set is the whole game.** Non-negotiable REQUIRED deps even headless: JPEG, PNG, zlib,
  zstd, fmt, Freetype(+brotli), OpenEXR(+Imath), **OpenImageIO**, OpenColorIO, Eigen3, TBB, pthreads
  (Vulkan/ShaderC/Epoxy are REQUIRED in stock but we neutralize them — WebGPU build has no consumer).
- **Plan-changer: OpenImageIO is on the tier-(a) critical path.** `blenlib` PUBLIC-links
  `OpenImageIO::OpenImageIO` (`dependency_targets.cmake:143`), so blenlib/bmesh gtests will not
  *link* until Imath→OpenEXR→OIIO exist in `lib/wasm`. The "free oracle" is not free of the dep build.
- **De-risking move applied to the plan:** M1 will build with `WITH_PYTHON OFF` and `WITH_CYCLES
  OFF`. Python is verified NOT on the gtest link path, so this keeps CPython — and the unresolved
  emcc-version toolchain decision — entirely off the M1 critical path.

## Ranked blocking list

1. **DISK — CRITICAL.** `/Users/paws` is **100% full, 4.9 GiB free**. The M1 dep superbuild
   (OIIO+EXR+TBB trees + EM_CACHE) will not fit. GOAL wants ≥40 GB before M2. **Hard-blocks M1.4→M1.12.**
2. **OIIO stack cross-compile** (Imath→OpenEXR→OIIO + native host oiiotool) — the long pole; blocks
   the real configure and every gtest link. Blocked by #1.
3. **TBB over emscripten -pthread + SharedArrayBuffer** — highest build-risk mandatory dep (wasm-diff 4).
4. **CPython 3.13 toolchain ABI decision** (emcc 6.0.5 vs pin 4.0.9) — M2 gate; deferred off M1 by the
   WITH_PYTHON-OFF move, but must be answered before M2.1.
5. **Harness H-2:** no `--regress` mode, so cross-scope regression is currently a no-op. Reconcile at
   the M1 boundary before M1.10 lands.

## Honest next-gate estimate

M1_CORE_BOOTS (blenlib+bmesh gtests green on wasm) is gated behind the full OIIO dep stack, not just
a compile grind — a substantial chunk of what looked like "M2" is actually pre-M1. **It cannot start
until the disk blocker clears.** Once disk is resolved, the path is: platform shim finalize (fast) →
Wave-0/1/2 dep builds (the bulk of the effort, OIIO dominant) → real configure → core compile → gtest
link/run.

## Needs a human decision

- **[PAGE] Disk.** Reclaim space or attach an external volume for `lib/wasm` build trees + `EM_CACHE`.
  Nothing on the M1 dep path can proceed until this is answered.
- **[M2 gate] CPython toolchain ABI:** forward-port Pyodide patches to emcc 6.0.5, or pin emsdk to
  Pyodide's validated 4.0.9. Sets the ABI for the whole port; needed before the M2 Python build, not before M1.
