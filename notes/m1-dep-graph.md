# M1 Dependency Graph — Minimal Mandatory Set for Headless wasm Blender

Evidence base (pin `fbe6228777e7`, Blender 5.2 LTS):
- `upstream/build_files/cmake/platform/platform_unix.cmake` — the `find_package(... REQUIRED)` calls that are NOT gated by any `WITH_*`.
- `upstream/build_files/cmake/platform/dependency_targets.cmake` — which deps become real link targets.
- `upstream/source/blender/blenlib/CMakeLists.txt` — the `LIB` list the tier-(a) gtests transitively link.
- `upstream/extern/CMakeLists.txt`, `upstream/intern/` — what is bundled/always-built.
- `upstream/build_files/build_environment/cmake/{versions,<dep>}.cmake` — native superbuild recipes + pinned versions.

## Key finding (changes the plan)

**OpenImageIO is on the M1 critical path, not M2.** `blenlib/CMakeLists.txt` PUBLIC-links
`bf::dependencies::openimageio` (= `OpenImageIO::OpenImageIO`, a real import lib — dependency_targets.cmake:143), plus `fmt`, `zlib`, `zstd`, and (default-ON) `tbb`. So the tier-(a) blenlib + bmesh_core gtests will NOT LINK until the whole Imath→OpenEXR→OIIO image stack exists in `lib/wasm`. Only OCIO, freetype, Python, and epoxy are deferrable past the first gtest link.

## Non-gated HARD requirements in stock 5.2 (all optional WITH_* OFF)

Unconditional `find_package(... REQUIRED)` in platform_unix.cmake:
JPEG(137), PNG(138), ZLIB(139), Zstd(140), Epoxy(141), fmt(142), OpenEXR(265)→pulls Imath,
OpenImageIO(449), OpenColorIO 2.0.0(455), Threads/pthreads(604), Eigen3(652).
Freetype(195) is `find_package(... REQUIRED)` gated only by `NOT WITH_SYSTEM_FREETYPE` → always resolved → mandatory; it requires **brotli** (woff2, fatal-errors without it, line 188/202).
Python(234) gated by `WITH_PYTHON` (option default ON, kept ON per GOAL — mandatory for UI).
TBB(499) gated by `WITH_TBB` (option default ON, line 756; Eigen also opts into `EIGEN_HAS_TBB`).

Verified NON-mandatory (all gated, forced OFF for us): OpenVDB, USD, MaterialX, Alembic, OSL, LLVM, Embree, OpenSubdiv, OpenJPEG, WebP, FFmpeg, SDL3, GMP, Potrace, Haru, manifold, NanoVDB, OpenImageDenoise, XR, Vulkan/ShaderC, Harfbuzz, Fribidi, Ceres/libmv.

## Dependency table

| dep | mandatory? | class | wasm diff (1-5) | notes / precedent |
|---|---|---|---|---|
| zlib 1.3.1 | yes (REQ) | **emscripten port** | 1 | `--use-port=zlib` / `-sUSE_ZLIB`; also transitive via EXR/OIIO/OCIO/minizip/tiff/png |
| zstd 1.5.7 | yes (REQ) | external | 1 | plain CMake, no SIMD blockers |
| fmt 12.1.0 | yes (REQ) | external | 1 | header+small lib, trivial |
| Imath 3.2.2 | yes (via EXR/OIIO/OCIO) | external | 2 | CMake; half/float math, portable |
| Eigen | yes (REQ) | external (headers) | 1 | header-only; wrapper `intern/eigen` builds w/ tree |
| robin-map v1.3.0 | yes (OIIO dep) | external (headers) | 1 | header-only |
| pugixml 1.10 | yes (OIIO dep) | external | 1 | single-TU, trivial |
| brotli 1.0.9 | yes (freetype/woff2) | external | 1 | plain CMake |
| yaml-cpp 0.8.0 | yes (OCIO dep) | external | 1 | plain CMake |
| expat 2.7.5 | yes (OCIO dep) | external | 1 | plain CMake |
| pystring 1.1.3 | yes (OCIO dep) | external | 1 | tiny |
| libjpeg-turbo 2.1.3 | yes (REQ + OIIO/tiff) | external | 2 | disable NASM/SIMD for wasm (`WITH_SIMD=OFF`) |
| libpng 1.6.58 | yes (REQ + OIIO) | **port**/external | 2 | `-sUSE_LIBPNG`; needs zlib |
| libtiff | yes (OIIO required dep) | external | 2 | needs zlib+jpeg; OIIO `REQUIRED_DEPS` lists TIFF |
| minizip-ng 4.0.10 | yes (OCIO dep) | external | 2 | needs zlib/zstd; disable iconv/bzip2/openssl |
| TBB 2022.3.0 | yes (WITH_TBB ON) | external | 3-4 | oneTBB over emscripten `-pthread`+SharedArrayBuffer; threading is the risk, not the build |
| freetype 2.13.3 | yes (REQ) | **port**/external | 2 | `--use-port=freetype`; but must be brotli-enabled or platform check FATALs → likely build external w/ brotli |
| OpenEXR 3.4.10 | yes (REQ) | external | 3 | needs Imath+zlib; big but portable CMake |
| OpenColorIO 2.5.0 | yes (REQ) | external | 3 | deps: Imath, yaml-cpp, expat, pystring, zlib, minizip-ng (opencolorio.cmake:92-99). Python/pybind bindings NOT needed for core link |
| OpenImageIO 3.1.13.1 | yes (REQ) | external | 4 | deps (trimmable): OpenEXR/Imath, fmt, robin-map, pugixml, TIFF, jpeg, png, zlib, TBB. No Boost in 3.x. Biggest single build |
| CPython 3.13.13 | yes (WITH_PYTHON ON) | external | 5 | Pyodide precedent; long pole; needs libffi; deferrable past M1 gtest link |
| Epoxy 1.5.10 | stock-yes / **us: patch-out** | n/a | — | GL/EGL loader; only used by GL backend + GHOST GL. WebGPU-only build has no consumer → patch `platform_web.cmake` to drop the REQUIRED, do NOT cross-compile |
| pthreads | yes (REQ) | emscripten builtin | 1 | `-pthread -sPROXY_TO_PTHREAD`; no lib to build |

### Bundled in `extern/` — always built with the tree (no cross-compile task; cheap)
`curve_fit_nd`, `fast_float`, `json`, `rangetree`, `nanosvg`, `wcwidth`, `xxhash` (unconditional `add_subdirectory` in extern/CMakeLists.txt:6-50). `gtest`/`gmock`/`gflags`/`glog` built under `WITH_GTESTS` (needed for tier-(a)). `vulkan_memory_allocator` only under WITH_VULKAN_BACKEND (N/A).

### `intern/` — Blender's own, always compiled with the tree
`guardedalloc`, `atomic`, `clog`, `ghost`, `mikktspace`, `memutil`, `utfconv`, `libc_compat`, `eigen` wrapper, `profile`, `sky`. Not third-party cross-compile targets.

## Recommended build order (topological)

**Wave 0 — leaves, fully parallel** (no inter-dep):
zlib(port), zstd, fmt, Imath, brotli, robin-map, pugixml, yaml-cpp, expat, pystring, Eigen(headers), libjpeg-turbo, libpng(port), TBB.
Kick off Python here too (independent, long pole; deferrable to M2).

**Wave 1 — one hop:**
OpenEXR (Imath,zlib) · libtiff (zlib,jpeg) · minizip-ng (zlib,zstd) · freetype (brotli,zlib,png; deferrable to M2).

**Wave 2 — top of stack:**
OpenImageIO (OpenEXR,Imath,fmt,robin-map,pugixml,tiff,jpeg,png,zlib,TBB) · OpenColorIO (Imath,yaml-cpp,expat,pystring,zlib,minizip-ng; deferrable to M2).

**Critical path to first M1 tier-(a) gtest link** (blenlib/bmesh):
Imath → {OpenEXR, libtiff} → **OpenImageIO**, alongside fmt + zlib + zstd + TBB.
NOT required for that link: OCIO, freetype, Python, epoxy — defer them to the M2 (`import bpy` / full binary) push.

**Deps-superbuild strategy:** cross-compile the `build_files/build_environment/` ExternalProjects with emcc, harvest to `lib/wasm` via `-DHARVEST_TARGET`, disabling every optional sub-feature (OIIO: only EXR/TIFF/PNG/JPEG format readers; OCIO: no Python bindings; minizip-ng: no bzip2/iconv/openssl; jpeg-turbo: `WITH_SIMD=OFF`). Prefer emscripten ports for zlib/libpng/freetype where the brotli constraint allows.
