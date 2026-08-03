# SPDX-FileCopyrightText: 2011-2023 Blender Authors
# SPDX-FileCopyrightText: 2011-2022 Blender Authors
# SPDX-FileCopyrightText: 2026 blender-web contributors
#
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Ported for the web from build_files/cmake/config/blender_lite.cmake @ fbe6228777e7
# and build_files/cmake/config/blender_headless.cmake @ fbe6228777e7

# blender-web build configuration — WebAssembly + WebGPU target (Blender 5.2 LTS,
# pin fbe6228777e7).
#
# Purpose: a headless, dependency-minimal Blender configuration for the browser
# port. Content is the union of the blender_lite + blender_headless option sets,
# with GOAL.md's standing decisions applied on top:
#   * WITH_CYCLES stays ON but CPU-only (every GPU device path forced OFF; no OSL
#     JIT, no Embree, no path guiding).
#   * every heavyweight or native-only subsystem with no wasm path is forced OFF.
#   * native windowing (X11/Wayland/SDL) is forced OFF; the port ships its own
#     GHOST_SystemWeb, so WITH_HEADLESS stays ON for bring-up.
#   * WITH_PYTHON and WITH_TBB are held ON — Python is mandatory (the entire
#     menu/panel UI layer is Python); TBB is the task scheduler.
# OpenEXR / OpenImageIO / OpenColorIO are now mandatory (non-optional) upstream
# and therefore carry no WITH_* switch here.
#
# Every option name below is verified to exist in upstream/CMakeLists.txt at the
# pin. WITH_BOOST (present in blender_lite) is intentionally omitted: it is no
# longer declared as an option in Blender 5.2's root CMakeLists.txt.
#
# Example usage:
#   emcmake cmake -C../blender/patches/blender_web.cmake ../blender

# ---- Locate the port's platform layer --------------------------------------
# patches/0001-platform-wasm.patch adds an `if(EMSCRIPTEN) include(platform_wasm)`
# branch to upstream/CMakeLists.txt. That include resolves platform_wasm.cmake via
# CMAKE_MODULE_PATH, to which the patch appends BLENDER_WEB_PATCH_DIR. Set it here
# to this config file's own directory (patches/) so the canonical configure
#   emcmake cmake -S upstream -B build-wasm -C patches/blender_web.cmake ...
# is self-contained (no extra -D needed).
set(BLENDER_WEB_PATCH_DIR "${CMAKE_CURRENT_LIST_DIR}" CACHE PATH
    "Directory holding platform_wasm.cmake (the blender-web patches/ dir)" FORCE)

# ---- Web platform: headless core, no native windowing ----------------------
set(WITH_HEADLESS            ON  CACHE BOOL "" FORCE)  # ship GHOST_SystemWeb instead
set(WITH_GHOST_SDL          OFF CACHE BOOL "" FORCE)
set(WITH_GHOST_X11          OFF CACHE BOOL "" FORCE)
set(WITH_GHOST_WAYLAND      OFF CACHE BOOL "" FORCE)
set(WITH_GHOST_XDND         OFF CACHE BOOL "" FORCE)
set(WITH_X11_XINPUT         OFF CACHE BOOL "" FORCE)
set(WITH_INPUT_IME          OFF CACHE BOOL "" FORCE)
set(WITH_INPUT_NDOF         OFF CACHE BOOL "" FORCE)

# ---- M1 core-boots ONLY: Python + Cycles forced OFF ------------------------
# TEMPORARY, milestone-scoped override (checkpoint-01). Both WITH_PYTHON and
# WITH_CYCLES RETURN in M2 and are NOT standing decisions:
#   * WITH_PYTHON is MANDATORY for the UI — the entire menu/panel layer is Python
#     (scripts/startup/bl_ui). It is OFF here purely to keep cross-compiled CPython
#     3.13 off the M1 "core boots + free oracle" critical path (blenlib/bmesh gtests
#     don't need the interpreter).
#   * WITH_CYCLES (CPU-only) is a launch-tier feature; OFF here to keep the
#     OIIO/render dependency stack off the M1 configure/link path.
# When flipping these back ON in M2, restore the CPU-only Cycles device block below.
set(WITH_PYTHON             OFF CACHE BOOL "" FORCE)  # M1-only — MANDATORY again in M2 (Python UI)

# ---- Held ON (mandatory for the port) --------------------------------------
set(WITH_TBB                 ON  CACHE BOOL "" FORCE)
set(WITH_TBB_MALLOC_PROXY   OFF CACHE BOOL "" FORCE)   # emscripten uses -sMALLOC=mimalloc

# ---- Cycles: OFF for M1, returns CPU-only in M2 ----------------------------
set(WITH_CYCLES                      OFF CACHE BOOL "" FORCE)  # M1-only — returns (CPU-only) in M2
set(WITH_CYCLES_OSL                  OFF CACHE BOOL "" FORCE)  # no JIT in the sandbox
set(WITH_CYCLES_EMBREE               OFF CACHE BOOL "" FORCE)  # x86/arm SIMD, no wasm
set(WITH_CYCLES_PATH_GUIDING         OFF CACHE BOOL "" FORCE)  # OpenPGL, unported
set(WITH_CYCLES_HYDRA_RENDER_DELEGATE OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_DEVICE_CUDA          OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_DEVICE_HIP           OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_DEVICE_HIPRT         OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_DEVICE_METAL         OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_DEVICE_ONEAPI        OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_DEVICE_OPTIX         OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_CUDA_BINARIES        OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_HIP_BINARIES         OFF CACHE BOOL "" FORCE)
set(WITH_CYCLES_ONEAPI_BINARIES      OFF CACHE BOOL "" FORCE)

# ---- USD / Hydra / MaterialX (heavyweight, unported) -----------------------
set(WITH_USD                OFF CACHE BOOL "" FORCE)
set(WITH_HYDRA              OFF CACHE BOOL "" FORCE)
set(WITH_MATERIALX          OFF CACHE BOOL "" FORCE)

# ---- Volumes / simulation / heavy geometry (unported) ----------------------
set(WITH_OPENVDB            OFF CACHE BOOL "" FORCE)
set(WITH_OPENVDB_BLOSC      OFF CACHE BOOL "" FORCE)
set(WITH_NANOVDB            OFF CACHE BOOL "" FORCE)
set(WITH_MOD_FLUID          OFF CACHE BOOL "" FORCE)  # Mantaflow, no wasm port
set(WITH_MOD_OCEANSIM       OFF CACHE BOOL "" FORCE)
set(WITH_MOD_REMESH         OFF CACHE BOOL "" FORCE)
set(WITH_UV_SLIM            OFF CACHE BOOL "" FORCE)
set(WITH_QUADRIFLOW         OFF CACHE BOOL "" FORCE)
set(WITH_MANIFOLD           OFF CACHE BOOL "" FORCE)
set(WITH_OPENSUBDIV         OFF CACHE BOOL "" FORCE)
set(WITH_OPENIMAGEDENOISE   OFF CACHE BOOL "" FORCE)

# ---- Other native / heavyweight dependencies (unported) --------------------
set(WITH_ALEMBIC            OFF CACHE BOOL "" FORCE)
set(WITH_LLVM               OFF CACHE BOOL "" FORCE)  # no JIT in the sandbox
set(WITH_XR_OPENXR          OFF CACHE BOOL "" FORCE)  # no VR hardware in a tab
set(WITH_GMP                OFF CACHE BOOL "" FORCE)
set(WITH_HARU               OFF CACHE BOOL "" FORCE)
set(WITH_POTRACE            OFF CACHE BOOL "" FORCE)
set(WITH_PUGIXML            OFF CACHE BOOL "" FORCE)
set(WITH_FFTW3              OFF CACHE BOOL "" FORCE)
set(WITH_BULLET             OFF CACHE BOOL "" FORCE)
set(WITH_LIBMV              OFF CACHE BOOL "" FORCE)
set(WITH_FREESTYLE          OFF CACHE BOOL "" FORCE)
set(WITH_DRACO              OFF CACHE BOOL "" FORCE)
set(WITH_MESHOPTIMIZER      OFF CACHE BOOL "" FORCE)
set(WITH_IK_ITASC           OFF CACHE BOOL "" FORCE)
set(WITH_IK_SOLVER          OFF CACHE BOOL "" FORCE)

# ---- Image codecs (unported / out of launch tier) --------------------------
set(WITH_CODEC_FFMPEG       OFF CACHE BOOL "" FORCE)
set(WITH_IMAGE_CINEON       OFF CACHE BOOL "" FORCE)
set(WITH_IMAGE_OPENJPEG     OFF CACHE BOOL "" FORCE)
set(WITH_IMAGE_WEBP         OFF CACHE BOOL "" FORCE)

# ---- File IO not in the initial launch tier --------------------------------
set(WITH_IO_WAVEFRONT_OBJ   OFF CACHE BOOL "" FORCE)
set(WITH_IO_PLY             OFF CACHE BOOL "" FORCE)
set(WITH_IO_STL             OFF CACHE BOOL "" FORCE)
set(WITH_IO_FBX             OFF CACHE BOOL "" FORCE)
set(WITH_IO_GREASE_PENCIL   OFF CACHE BOOL "" FORCE)

# ---- Audio (all OFF — no browser audio device in scope) --------------------
set(WITH_AUDASPACE          OFF CACHE BOOL "" FORCE)
set(WITH_CODEC_SNDFILE      OFF CACHE BOOL "" FORCE)
set(WITH_OPENAL             OFF CACHE BOOL "" FORCE)
set(WITH_JACK               OFF CACHE BOOL "" FORCE)
set(WITH_PULSEAUDIO         OFF CACHE BOOL "" FORCE)
set(WITH_PIPEWIRE           OFF CACHE BOOL "" FORCE)
set(WITH_SDL_AUDIO          OFF CACHE BOOL "" FORCE)
set(WITH_COREAUDIO          OFF CACHE BOOL "" FORCE)
set(WITH_WASAPI             OFF CACHE BOOL "" FORCE)
set(WITH_RUBBERBAND         OFF CACHE BOOL "" FORCE)

# ---- Localization / misc (INTERNATIONAL off initially — size) --------------
set(WITH_INTERNATIONAL      OFF CACHE BOOL "" FORCE)
set(WITH_BLENDER_THUMBNAILER OFF CACHE BOOL "" FORCE)
set(WITH_BUILDINFO          OFF CACHE BOOL "" FORCE)

# ---- Keep asserts firing during bring-up (from blender_lite) ---------------
set(WITH_ASSERT_RELEASE      ON  CACHE BOOL "" FORCE)

# ---- Tier-(a) free oracle: build the gtest suites (M1.9) -------------------
# blenlib + bmesh_core gtests compiled to wasm are the M1 parity gate. gflags/glog
# come from bundled extern/ (root CMakeLists.txt L1654/L1669), gtest/gmock from
# extern too — no external dep. OFF by default upstream (root L778).
set(WITH_GTESTS              ON  CACHE BOOL "" FORCE)
