<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# OpenImageIO 3.1.13.1 — wasm cross-build notes (M1.6)

Status: **built OK**, static, `-pthread -fexceptions`, installed to `lib/wasm`
(`libOpenImageIO.a` 26 MB, `libOpenImageIO_Util.a` 3 MB, config
`lib/cmake/OpenImageIO`). emcc link test constructs a real `OIIO::ImageSpec` and
calls `serialize()` — links + produces wasm.

Script: `scripts/deps/openimageio.sh` (idempotent). Trimmed readers only:
**EXR, TIFF, PNG, JPEG**. Everything else OFF (WebP, OpenJPEG, HEIF, Raw, JXL,
GIF, DICOM, Ptex, FFmpeg, OpenVDB, Nuke, OpenCV, Qt, Freetype, Python bindings,
TBB, tools/tests/docs). `USE_SIMD=0`, `EMBEDPLUGINS=ON` (static formats, no DSO),
`USE_EXTERNAL_PUGIXML=OFF` (bundled pugixml — avoids building it).

## HEADLINE FINDING — OpenColorIO is a HARD dependency of OIIO 3.x

`USE_OPENCOLORIO=OFF` does **not** yield a buildable library.
`src/libOpenImageIO/color_ocio.cpp` `#include`s `<OpenColorIO/OpenColorIO.h>`
**unconditionally** (0 `USE_OPENCOLORIO` guards) and `libOpenImageIO`
unconditionally links `OpenColorIO::OpenColorIO`. OIIO 3.0 made OCIO mandatory.

Consequence: because `blenlib` PUBLIC-links `OpenImageIO::OpenImageIO`, the ENTIRE
OCIO subtree is on the **M1 tier-(a) gtest critical path**:

    expat, pystring, yaml-cpp, minizip-ng  ->  OpenColorIO  ->  OpenImageIO  ->  blenlib

This **corrects `ledger/deps.json`**, which classified `opencolorio` (and its
leaves) as `deferrable_past_m1` / `wave2`. They are NOT deferrable. All six were
built this milestone (scripts: `expat.sh`, `pystring.sh`, `yamlcpp.sh`,
`minizipng.sh`, `opencolorio.sh`, plus `robinmap.sh`).

We still pass `USE_TBB=OFF` to OIIO (its internal std::thread pool is fine under
pthreads) and OCIO is built with `OCIO_USE_SIMD=OFF`.

## Host-tool / cross-compile trap analysis (the thing M2 will hit again)

The brief warned OIIO may try to run host tools it just built. **It does not**,
with our option set:
- `OIIO_BUILD_TOOLS=OFF` — oiiotool/iconvert/idiff/maketx are the only OIIO
  executables; none are built, so none are run. (The native brew oiiotool 3.1.16
  was therefore NOT needed as a workaround — noted in case a future config with
  tools ON needs it.)
- `OIIO_BUILD_TESTS=OFF`, `BUILD_TESTING=OFF`, `INSTALL_FONTS=OFF`.
- No codegen step executes a wasm binary. OCIO likewise builds no host tool
  (`OCIO_BUILD_APPS/PYTHON/TESTS/GPU_TESTS=OFF`).

So OIIO/OCIO are pure library cross-builds — no emulator, no host-run step.

## The emscripten `find_package` re-rooting gotcha (recurring, document once)

The emscripten toolchain roots `find_path`/`find_library`/`find_package` at its
own sysroot, so deps in `lib/wasm` are invisible to a plain `find_package`.
Two working remedies, used throughout:
1. **CONFIG packages** (Imath/OpenEXR/fmt/TIFF/PNG/OpenColorIO/...): pass the exact
   `<Pkg>_DIR=lib/wasm/lib/cmake/<Pkg>` — an explicit path bypasses the search.
   Transitive `find_dependency` inside a config also needs its own `_DIR` passed
   at the consumer (e.g. OpenEXR's config pulls `libdeflate`/`openjph`).
3. **Standard/module finds** (ZLIB, JPEG, and OCIO's bundled Find modules for
   pystring/expat/minizip-ng): pass explicit `<PKG>_INCLUDE_DIR` + `<PKG>_LIBRARY`
   cache vars so the find is a no-op.

### OCIO's bundled Find modules have a `*_ROOT`-defined trap
`share/OpenColorIO/cmake/modules/Find{expat,minizip-ng}.cmake`: when
`<pkg>_ROOT` is **defined**, they read the (nonexistent, in module mode) imported
target via `get_target_property`, which sets `<pkg>_INCLUDE_DIR/_LIBRARY` to
NOTFOUND and clobbers any value you passed. Fix: **do NOT define `expat_ROOT` /
`minizip-ng_ROOT`**; define only `<pkg>_INCLUDE_DIR` + `<pkg>_LIBRARY`.
`Findpystring.cmake` has no such guard — `pystring_ROOT` + include/lib is fine.

## CONSUMER REQUIREMENT for the Blender build (M1 gtest link / M2)

`find_package(OpenImageIO)` in Blender's CMake will chase the same transitive
chain (OIIO config -> OpenColorIO config -> expat/pystring/yaml-cpp/minizip-ng/
Imath/ZLIB). Blender's platform CMake MUST supply these cache vars (the same set
`openimageio.sh` passes), or the OIIO find fails at configure. Minimal set:

    OpenImageIO_DIR, OpenColorIO_DIR, Imath_DIR, OpenEXR_DIR, fmt_DIR, TIFF_DIR,
    PNG_DIR, libjpeg-turbo_DIR, tsl-robin-map_DIR, yaml-cpp_DIR, expat_DIR,
    libdeflate_DIR, openjph_DIR,
    ZLIB_INCLUDE_DIR/ZLIB_LIBRARY, JPEG_INCLUDE_DIR/JPEG_LIBRARY,
    ROBINMAP_INCLUDE_DIR,
    expat_INCLUDE_DIR/expat_LIBRARY, pystring_ROOT/pystring_INCLUDE_DIR/pystring_LIBRARY,
    minizip-ng_INCLUDE_DIR/minizip-ng_LIBRARY   (NOT minizip-ng_ROOT / expat_ROOT)

This is a request to the `build-deps`/driver owner of `patches/platform_wasm.cmake`
to fold these into the find_package_wrapper for OIIO.

## OIIO source patches applied by the script (fresh source each run, idempotent)

1. `externalpackages.cmake`: guard the `OPENCOLORIO_INCLUDES` `get_target_property`
   with `AND TARGET OpenColorIO::OpenColorIO` (defensive; no-op now OCIO is ON).
2. `libOpenImageIO/CMakeLists.txt`: make the OCIO link
   `$<TARGET_NAME_IF_EXISTS:...>` (defensive; no-op now OCIO is ON).
3. **wasm platform port of `libutil`** (musl / `__EMSCRIPTEN__` not in OIIO's
   platform branches):
   - `strutil.cpp`: add `__EMSCRIPTEN__` to every `__GLIBC__`-family guard (the
     `c_loc` locale def AND the `strcasecmp_l`/`strncasecmp_l` branches must flip
     together); add `<strings.h>` + `<locale.h>`.
   - `sysutil.cpp`: add `<unistd.h>`/`<sys/ioctl.h>` for `isatty()`/`usleep()`
     (the `__linux__` include block is skipped); fold `__EMSCRIPTEN__` into the
     `__GNU__`/`_WIN32` `this_program_path() -> r=0` elif (no /proc or dyld in the
     sandbox; returns empty path).

## Sibling fix: libjpeg-turbo CMake config pointed at the deleted build tree

`lib/cmake/libjpeg-turbo/libjpeg-turboTargets-release.cmake` had
`IMPORTED_LOCATION_RELEASE` = the scratch `build-deps/libjpeg/build/lib/libjpeg.a`
(harvested, never installed), so `find_package(libjpeg-turbo)` CONFIG failed the
existence check. Fixed durably in `scripts/deps/libjpeg.sh` (rewrite the exported
path to the installed archive after harvest) and patched the installed file.

## Harmless noise
- `ERRORclang minimum version is 5.0` — OIIO can't parse emcc's clang version
  string; cosmetic, build succeeds.
- `libuhdr library not found` — Ultra HDR, not requested; optional, ignored.
