<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# M1 Configure Map — first Emscripten `cmake configure` of Blender

Pin: `blender-v5.2-release` @ `fbe6228777e7`. Toolchain: emcmake / emcc 6.0.5
(emsdk). Invocation under test:

```
emcmake cmake -S upstream -B build-wasm -C patches/blender_web.cmake \
  -DCMAKE_MODULE_PATH=patches/cmake_wasm -DCMAKE_BUILD_TYPE=Release
```

## Headline result

**The CMake spine configures end-to-end for wasm.** With the mandatory deps
faked as placeholder targets, cmake reaches `Configuring done (60.6s)` +
`Generating done (2.8s)`. There is **no Emscripten-specific platform wall**
beyond Blender's Linux platform file, and **no emcc compiler/feature-check
failure** — every `C_WARN_*` / `CXX_WARN_*` / `_has_cxxflag_*` probe and the
`try_compile`s (malloc_stats, execinfo.h) succeed under emcc. Therefore M1/M2's
real long-pole is **cross-compiling the mandatory dependency set to `lib/wasm`
plus a genuine `platform_web.cmake`** — not Blender's own build logic.

Category legend: (a) platform detection, (b) missing precompiled libs,
(c) hard-required deps that can't be turned off, (d) emcc feature checks,
(e) other.

## Ranked blockers (order encountered = order to solve)

### 1. Git-LFS pointer for `startup.blend` — (e), SOLVED here
`CMakeLists.txt:96 (message)`:
> Detected incomplete startup blend, likely due to missing Git LFS checkout.

The pinned checkout left `release/datafiles/startup.blend` as a 131-byte LFS
pointer (`size 121384`). Configure fatals at line 93-100 (`file(SIZE ...) LESS
1024`). **Fix:** complete the pinned LFS content —
`git -C upstream lfs pull --include "release/datafiles/*"` (done; file now
121384 bytes). This is realizing the pin, not editing it. M0 checkout should run
`git lfs pull` so every worker starts from complete data.

### 2. `platform_unix.cmake` is force-included and hard-requires the full Linux lib set — (a)+(c), THE central blocker
Emscripten is CMake `UNIX AND NOT APPLE`, so `CMakeLists.txt:1542` does
`include(platform_unix)` unconditionally (no Emscripten/WASM branch exists). It
mis-detects arch as x86, points `LIBDIR` at `lib/linux_x86` (empty), then fires
a wall of `find_package_wrapper(<X> REQUIRED)`. First failure:
`FindJPEG.cmake … Could NOT find JPEG (missing: JPEG_LIBRARY JPEG_INCLUDE_DIR)`
(`platform_unix.cmake:123`).
The full REQUIRED set reached before it aborts: **JPEG, PNG, ZLIB, Zstd, Epoxy,
fmt, Vulkan, ShaderC, Freetype, Brotli, PythonLibsUnix, OpenEXR, OpenImageIO,
OpenColorIO≥2.0, Threads, Eigen3** (Embree/manifold/Ceres/draco/X11 etc. are
WITH_-gated OFF by our config).
**Fix:** ship a real `build_files/cmake/config` companion + a dedicated
**`platform_web.cmake`** that the port selects instead of `platform_unix`.
Upstream can't be edited to add an `elseif(EMSCRIPTEN)` branch, so the port must
**shadow the include**: put `platform_web` logic in a file named
`platform_unix.cmake` on a dir prepended to `CMAKE_MODULE_PATH`
(`list(APPEND)` at CMakeLists.txt:38-39 places a `-DCMAKE_MODULE_PATH=` entry
first, so it wins `include(platform_unix)`). That shadow file `find_package`s the
harvested `lib/wasm` deps once they exist. (This experiment's stub proves the
mechanism: `patches/cmake_wasm/platform_unix.cmake`.)

### 3. Mandatory dep alias targets in `dependency_targets.cmake` — (c)
Included unconditionally at `CMakeLists.txt:1681`; it `ALIAS`es dep targets that
`platform_unix` was supposed to have created:
`dependency_targets.cmake:93/143/185/464/82`:
> add_library cannot create ALIAS target "bf::dependencies::opencolorio" because
> target "OpenColorIO::OpenColorIO" does not already exist.

Same for `OpenImageIO::OpenImageIO` (+ `get_target_property … OpenImageIO::oiiotool
LOCATION`, needs the built oiiotool binary), `OpenEXR::OpenEXR`, `fmt::fmt`,
`Eigen3::Eigen`, and it consumes `${TBB_LIBRARIES}`. These are the **now-mandatory,
non-optional** deps (no WITH_ switch): **OpenColorIO, OpenImageIO(+oiiotool),
OpenEXR, fmt, Eigen3, TBB, Zlib, Zstd, Freetype/Brotli, JPEG, PNG**.
**Fix:** they are satisfied automatically once `platform_web.cmake` `find_package`s
the real `lib/wasm` builds — i.e. this blocker == the M2 superbuild. `oiiotool`
must be a runnable host tool (it runs at build time to make data files); harvest a
**native** oiiotool alongside the wasm libs, or stub the data-gen steps.

### 4. Python is mandatory and header-checked — (c)
`CMakeLists.txt:2267`:
> Missing: "…/Python.h", Set the cache entry 'PYTHON_INCLUDE_DIR' … python
> version ""

`WITH_PYTHON=ON` (required — the UI layer is Python). Needs `PYTHON_INCLUDE_DIR`
(Python.h), `PYTHON_LIBRARY`, `PYTHON_VERSION` (3.13), and later
`PYTHON_EXECUTABLE` (`source/creator/CMakeLists.txt:1013`
`get_filename_component(... ${PYTHON_EXECUTABLE} NAME)` fatals if empty).
**Fix:** cross-compile CPython 3.13 to wasm (Pyodide precedent) and have
`platform_web.cmake` set these vars; that is the M2 Python task.

### 5. `TEST_PYTHON_EXE` unset — (e), trivial
`tests/python/CMakeLists.txt:166`: `No Python configured for running tests, set
TEST_PYTHON_EXE.` (via `add_render_test` at :872). Only when `WITH_PYTHON` + the
python test suite are added. **Fix:** pass `-DTEST_PYTHON_EXE=<host python3>`
(the render tests shell out to a host interpreter), or disable that test subset.
Not a build blocker.

### 6. `source/creator/CMakeLists.txt` empty-var aborts — (c), artifacts of #3/#4
`:42 list(INSERT LIB 0 ${TBB_LIBRARIES})` → "list sub-command INSERT requires at
least three arguments" (empty `TBB_LIBRARIES`); `:1013 get_filename_component`
(empty `PYTHON_EXECUTABLE`). Both vanish once TBB and Python are real. Listed
only to show they are downstream of #3/#4, not independent walls.

## What each iteration bought (6 configure runs)

1. Baseline → blocker #1 (LFS), 1s.
2. After LFS pull → blocker #2 (platform_unix / JPEG), 4s.
3. Shadow-stub `platform_unix` (empty) → jumped past the whole lib wall to
   blocker #3 (dependency_targets aliases) + #4 (Python), 51s.
4. + placeholder imported targets (OCIO/OIIO/oiiotool/OpenEXR/fmt) + fake
   Python.h/vars → reached blocker #5 (TEST_PYTHON_EXE), 68s (whole platform
   check + warning probes pass).
5. + `-DTEST_PYTHON_EXE` → reached blocker #6 (creator TBB/PYTHON_EXECUTABLE), 68s.
6. + placeholder `TBB_LIBRARIES` + `PYTHON_EXECUTABLE` → **Configuring done +
   Generating done**; only a generate-time missing `Eigen3::Eigen` link-interface
   remains (same dep class as #3).

## Ordered plan to a real completing configure (headless wasm Blender)

1. **M0 hygiene:** `git lfs pull` the pinned datafiles (blocker #1).
2. **Write `platform_web.cmake`** shadowing `platform_unix` via
   `CMAKE_MODULE_PATH` (blocker #2 mechanism proven).
3. **Cross-compile & harvest `lib/wasm`** (blockers #3/#4/#6 collapse into this):
   priority order = **zlib/zstd → OpenEXR/Imath → OpenImageIO(+native oiiotool)
   → OpenColorIO → fmt → Eigen3 (header-only, cheapest) → Freetype/Brotli →
   libjpeg/libpng → TBB → CPython 3.13**. Point `platform_web.cmake`'s
   `find_package`s at them.
4. **Shader/GPU deps:** `platform_unix` also REQUIREs **Vulkan + ShaderC** (for
   the Vulkan backend). For the WebGPU port these must be handled in
   `platform_web.cmake` — either provide emcc ShaderC/SPIRV for the
   BSL→SPIR-V→Tint chain, or gate the Vulkan `find_package` off and route through
   the new `gpu/webgpu/` backend. **Epoxy** (GL loader) is likewise REQUIRED and
   must be neutralized for a GL-less WebGPU build.
5. **Test glue:** set `TEST_PYTHON_EXE` (host python) or trim the render-test
   subset (blocker #5).

After step 3 the configure completes; step 4 is where the port's genuine
architecture (WebGPU replacing Vulkan/Epoxy) first has to assert itself in CMake.
