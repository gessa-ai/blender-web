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

# ---- Web platform: headless core vs windowed profile (M4 T1) ---------------
# The proven default is the HEADLESS --background boot (BPY_OK in a tab). The
# WINDOWED web build flips WITH_HEADLESS OFF + WITH_WEBGPU_BACKEND ON + WITH_GHOST_WEB
# ON so the GHOST factory constructs GHOST_SystemWeb (patch 0025), the WebGPU
# drawing-context maps (0023), icons_init runs (0024), and WM_main hooks the
# emscripten main loop (0026). Gated behind WITH_BLENDER_WEB_WINDOWED (default OFF)
# so the shared headless build is untouched; a dedicated windowed build opts in with
#   -DWITH_BLENDER_WEB_WINDOWED=ON
# NOTE: the windowed LINK requires the M3 WebGPU backend — WITH_WEBGPU_BACKEND ON
# compiles source/blender/gpu/webgpu/ and needs --use-port=emdawnwebgpu on the
# windowed target's compile/link flags (platform_wasm.cmake browser target; tasks
# 6-7). See notes/m4-integration.md.
option(WITH_BLENDER_WEB_WINDOWED
  "blender-web: build the windowed web target (HEADLESS off, WebGPU + GHOST_WEB on)" OFF)
option(WITH_GHOST_WEB
  "blender-web: compile the browser GHOST back-end (platform_web/ghost)" OFF)
option(WITH_BLENDER_WEB_SCULPT_PAINT
  "blender-web: register non-launch sculpt and paint operators/keymaps" ON)
option(WITH_BLENDER_WEB_GREASE_PENCIL
  "blender-web: register non-launch Grease Pencil editing operators/keymaps" ON)
option(WITH_BLENDER_WEB_COMPOSITOR
  "blender-web: register non-launch compositor execution nodes" ON)
option(WITH_BLENDER_WEB_VSE
  "blender-web: register non-launch VSE editing" ON)
option(WITH_BLENDER_WEB_SPREADSHEET
  "blender-web: register non-launch Spreadsheet editor" ON)
option(WITH_BLENDER_WEB_CLIP
  "blender-web: register non-launch Clip editor" ON)
option(WITH_BLENDER_WEB_NLA
  "blender-web: register non-launch NLA editor" ON)

# This file is loaded as a `-C` INITIAL CACHE, which CMake processes BEFORE `-D`
# command-line options — so a `-DWITH_BLENDER_WEB_WINDOWED=ON` is not visible here.
# Honor an environment knob (evaluated at -C time) as the reliable windowed switch:
#   BLENDER_WEB_WINDOWED=1 cmake -S upstream -B build-wasm-windowed -C patches/blender_web.cmake ...
if("$ENV{BLENDER_WEB_WINDOWED}")
  set(WITH_BLENDER_WEB_WINDOWED ON CACHE BOOL "" FORCE)
endif()

if(WITH_BLENDER_WEB_WINDOWED)
  set(WITH_HEADLESS        OFF CACHE BOOL "" FORCE)  # run the windowed GHOST/UI/DRW path
  set(WITH_WEBGPU_BACKEND  ON  CACHE BOOL "" FORCE)  # the wasm GPU backend (M3)
  set(WITH_GHOST_WEB       ON  CACHE BOOL "" FORCE)  # GHOST_SystemWeb + GHOST_ContextWGPUWeb
  set(WITH_BLENDER_WEB_SCULPT_PAINT OFF CACHE BOOL "" FORCE)  # M8 critical-path DCE
  set(WITH_BLENDER_WEB_GREASE_PENCIL OFF CACHE BOOL "" FORCE)  # M8 critical-path DCE
  set(WITH_BLENDER_WEB_COMPOSITOR OFF CACHE BOOL "" FORCE)  # M8 critical-path DCE
  set(WITH_BLENDER_WEB_VSE OFF CACHE BOOL "" FORCE)  # M8 critical-path DCE
  set(WITH_BLENDER_WEB_SPREADSHEET OFF CACHE BOOL "" FORCE)  # M8 critical-path DCE
  set(WITH_BLENDER_WEB_CLIP OFF CACHE BOOL "" FORCE)  # M8 critical-path DCE
  set(WITH_BLENDER_WEB_NLA OFF CACHE BOOL "" FORCE)  # M8 critical-path DCE
else()
  set(WITH_HEADLESS        ON  CACHE BOOL "" FORCE)  # proven --background BPY_OK default
  set(WITH_GHOST_WEB       OFF CACHE BOOL "" FORCE)
endif()
set(WITH_GHOST_SDL          OFF CACHE BOOL "" FORCE)
set(WITH_GHOST_X11          OFF CACHE BOOL "" FORCE)
set(WITH_GHOST_WAYLAND      OFF CACHE BOOL "" FORCE)
set(WITH_GHOST_XDND         OFF CACHE BOOL "" FORCE)
set(WITH_X11_XINPUT         OFF CACHE BOOL "" FORCE)
set(WITH_INPUT_IME          OFF CACHE BOOL "" FORCE)
set(WITH_INPUT_NDOF         OFF CACHE BOOL "" FORCE)

# ---- Python: ON for M2.3 (mandatory for the UI + bpy) ----------------------
# M2.3 flip (2026-08-04): WITH_PYTHON returns ON. The entire menu/panel UI layer
# is Python (scripts/startup/bl_ui); `import bpy` is the M2 "core boots" gate.
# libpython3.13.a (JS-EH) + include/python3.13 + stdlib are harvested to lib/wasm
# (scripts/deps/python.sh); PYTHON_* discovery is wired in platform_wasm.cmake to
# resolve there (NOT the host python — the host interpreter for build-time codegen
# scripts stays native and is set separately in platform_wasm.cmake).
set(WITH_PYTHON             ON  CACHE BOOL "" FORCE)  # M2.3 — mandatory (Python UI + bpy)
#   * WITH_CYCLES (CPU-only) is a launch-tier feature; OFF here to keep the
#     OIIO/render dependency stack off the M2 configure/link path (revisit M6).
#     When flipping it back ON later, restore the CPU-only Cycles device block below.
# ---- Python build sub-options (cross build: no install, no numpy, no module) ---
#   * WITH_PYTHON_INSTALL defaults ON (root CMakeLists.txt:553) and would try to
#     COPY a *system* Python into the install dir — wrong for the wasm mono-module
#     (the stdlib is served from lib/wasm via NODERAWFS). Force OFF.
#   * WITH_PYTHON_MODULE stays OFF: we build the `blender` executable, not a `bpy`
#     python-extension module (module+WITH_GTESTS is incompatible, root L1643).
#   * WITH_PYTHON_NUMPY is only *declared* when audaspace/mod_fluid are ON (both
#     OFF here, root L561) so it never exists — no action needed, noted for audit.
#   * WITH_PYTHON_SECURITY keeps its upstream default (ON).
set(WITH_PYTHON_INSTALL     OFF CACHE BOOL "" FORCE)  # no system-Python copy (stdlib via lib/wasm)
set(WITH_PYTHON_MODULE      OFF CACHE BOOL "" FORCE)  # build the executable, not the bpy module
# The *_INSTALL_* bundling sub-options run find_python_package() even with
# WITH_PYTHON_INSTALL OFF (root CMakeLists.txt:2288/2299/2305 use bare elseif),
# emitting harmless "package not found / will be ignored" warnings against the
# harvest. Force OFF so configure is clean and nothing tries to bundle host pkgs.
set(WITH_PYTHON_INSTALL_NUMPY     OFF CACHE BOOL "" FORCE)
set(WITH_PYTHON_INSTALL_REQUESTS  OFF CACHE BOOL "" FORCE)
set(WITH_PYTHON_INSTALL_ZSTANDARD OFF CACHE BOOL "" FORCE)

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
set(WITH_OPENSUBDIV         ON  CACHE BOOL "" FORCE)  # CPU-only OSD in lib/wasm (scripts/deps/opensubdiv.sh); Subsurf/Multires + Cycles subdiv
# OpenSubdiv discovery. platform_wasm.cmake REPLACES platform_unix.cmake, so
# platform_unix:488-493's `find_package(OpenSubdiv)` never runs; with the dep now
# ON we seed, from this -C initial cache, the two variables that
# build_files/cmake/platform/dependency_targets.cmake:178-179 consume directly to
# wire bf::dependencies::optional::opensubdiv (used by BOTH intern/opensubdiv and
# intern/cycles/subd). CPU-only harvest from scripts/deps/opensubdiv.sh at
# lib/wasm; both osdCPU (real) and osdGPU (empty, see the script) are listed to
# honor FindOpenSubdiv's two-component contract. This -C file lives in patches/, so
# lib/wasm is patches/../lib/wasm.
get_filename_component(_bw_libwasm "${CMAKE_CURRENT_LIST_DIR}/../lib/wasm" ABSOLUTE)
if(EXISTS "${_bw_libwasm}/lib/libosdCPU.a")
  set(OPENSUBDIV_INCLUDE_DIRS "${_bw_libwasm}/include" CACHE PATH   "" FORCE)
  set(OPENSUBDIV_LIBRARIES
      "${_bw_libwasm}/lib/libosdCPU.a;${_bw_libwasm}/lib/libosdGPU.a"
      CACHE STRING "" FORCE)
  set(OPENSUBDIV_FOUND ON CACHE BOOL "" FORCE)
endif()
unset(_bw_libwasm)
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

# ---- File IO: native C++ exporters (launch-tier "OBJ/USD IO") --------------
# OBJ/PLY/STL are pure-C++ mesh IO (no native-only deps) and part of the launch
# tier; turned ON now that the M7 io-smoke proved they were merely compiled out.
# FBX (needs libfbx), grease-pencil IO, and USD stay OFF (USD is a heavyweight
# unported dep; GOAL launch-tier OBJ half only).
set(WITH_IO_WAVEFRONT_OBJ   ON  CACHE BOOL "" FORCE)
set(WITH_IO_PLY             ON  CACHE BOOL "" FORCE)
set(WITH_IO_STL             ON  CACHE BOOL "" FORCE)
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

# ---- Localization / misc ---------------------------------------------------
# WITH_INTERNATIONAL restored (r45, decision D-10): native-parity splash "Language"
# row + real UI translations. The .po -> .mo catalogs are compiled by the native host
# msgfmt (ADR-002; scripts/build-hosttools.sh + patch 0127) into build-hosttools/locale,
# preloaded at /bw/datafiles/locale (platform_wasm.cmake), and staged to stage-1 with the
# CJK fonts (stage_pack.py). English is the source language and loads no catalog, so boot
# is unaffected. See notes/i18n-restore-r45.md.
set(WITH_INTERNATIONAL      ON  CACHE BOOL "" FORCE)
set(WITH_BLENDER_THUMBNAILER OFF CACHE BOOL "" FORCE)
set(WITH_BUILDINFO          OFF CACHE BOOL "" FORCE)

# ---- Keep asserts firing during bring-up (from blender_lite) ---------------
set(WITH_ASSERT_RELEASE      ON  CACHE BOOL "" FORCE)

# ---- Tier-(a) free oracle: build the gtest suites (M1.9) -------------------
# blenlib + bmesh_core gtests compiled to wasm are the M1 parity gate. gflags/glog
# come from bundled extern/ (root CMakeLists.txt L1654/L1669), gtest/gmock from
# extern too — no external dep. OFF by default upstream (root L778).
set(WITH_GTESTS              ON  CACHE BOOL "" FORCE)

# ---- wasm libc gap: malloc_stats declared but not linkable -----------------
# have_features.cmake `check_symbol_exists(malloc_stats "malloc.h" ...)` returns
# TRUE under emscripten because musl's <malloc.h> *declares* malloc_stats(), but
# emscripten provides no definition -> guardedalloc's HAVE_MALLOC_STATS path is a
# link error (undefined symbol: malloc_stats). Pre-defining the cache var makes
# CheckSymbolExists skip its probe, so HAVE_MALLOC_STATS stays undefined and the
# stats-print falls back to the portable path. GLIBC-only feature; honest to omit.
set(HAVE_MALLOC_STATS_H "" CACHE INTERNAL "wasm: malloc_stats not linkable" FORCE)
