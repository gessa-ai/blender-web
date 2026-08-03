# SPDX-FileCopyrightText: 2016 Blender Authors
# SPDX-FileCopyrightText: 2026 blender-web contributors
#
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Ported for the web from build_files/cmake/platform/platform_unix.cmake @ fbe6228777e7
#
# Emscripten / WebAssembly platform layer for the blender-web port (Blender 5.2
# LTS, pin fbe6228777e7). This is the wasm equivalent of platform_unix.cmake /
# platform_apple.cmake: it stubs out the native lib/<platform> precompiled-library
# discovery (which has no wasm equivalent yet) and sets the Emscripten compiler /
# linker flags mandated by GOAL.md's "Emscripten posture" standing decision.
#
# Included from upstream/CMakeLists.txt's "Main Platform Checks" block via the
# `if(EMSCRIPTEN)` branch added by patches/0001-platform-wasm.patch. It runs in the
# top-level CMake scope, so it appends to the CMAKE_*_FLAGS / PLATFORM_LINKFLAGS
# variables initialised there (root CMakeLists.txt ~L1455-1464).

if(NOT EMSCRIPTEN)
  message(FATAL_ERROR "platform_wasm.cmake included on a non-Emscripten toolchain")
endif()

# find_package_wrapper is defined by platform_unix.cmake, which this file replaces
# for the Emscripten branch. A handful of downstream listfiles still reference it
# (e.g. tests/python/CMakeLists.txt, gated behind WITH_ALEMBIC). Provide the same
# thin shim so those paths don't hit an undefined-macro error.
macro(find_package_wrapper)
  find_package(${ARGV})
endmacro()

# -----------------------------------------------------------------------------
# Precompiled library discovery
#
# There is no `lib/wasm` harvest until M2 (the build_environment superbuild has
# not been cross-compiled yet). Unlike platform_unix.cmake we do NOT glob a
# glibc-ABI LIBDIR; instead we point LIBDIR at lib/wasm only if it has been
# populated, and otherwise disable precompiled libs entirely so find_package()
# falls through cleanly during headless core bring-up.

if(NOT DEFINED LIBDIR)
  set(LIBDIR "${CMAKE_SOURCE_DIR}/lib/wasm")
endif()

file(GLOB _wasm_libdir_contents "${LIBDIR}/*")
if(_wasm_libdir_contents)
  set(WITH_LIBS_PRECOMPILED ON)
  set(CMAKE_PREFIX_PATH "${LIBDIR}" ${CMAKE_PREFIX_PATH})
  if(FIRST_RUN)
    message(STATUS "blender-web: using wasm LIBDIR: ${LIBDIR}")
  endif()
else()
  # M1 headless-core bring-up: no harvested deps yet.
  set(WITH_LIBS_PRECOMPILED OFF)
  unset(LIBDIR)
  if(FIRST_RUN)
    message(STATUS "blender-web: no wasm LIBDIR populated yet (pre-M2); "
                   "WITH_LIBS_PRECOMPILED forced OFF.")
  endif()
endif()
unset(_wasm_libdir_contents)

# Prefer static libraries (there is no shared-object loading in mono-wasm).
set(WITH_STATIC_LIBS ON)

# -----------------------------------------------------------------------------
# GPU backend selection — WebGPU only (no GL, no Vulkan, no Epoxy)
#
# On non-Apple platforms upstream defaults WITH_OPENGL_BACKEND=ON and
# WITH_VULKAN_BACKEND=ON (root CMakeLists.txt L933/L941), and platform_unix.cmake
# then `find_package_wrapper(Epoxy REQUIRED)` (GL loader) and, under Vulkan,
# `find_package_wrapper(ShaderC REQUIRED)` / FindVulkan. This port bypasses
# platform_unix, so those REQUIRED finds never run — but the option defaults would
# still switch on the GL and Vulkan backend code in source/blender/gpu. The port
# ships its own `gpu/webgpu/` backend instead, so force both legacy backends OFF:
#
#   * OpenGL OFF  -> drops the Epoxy dependency entirely (its only REQUIRED find
#                    lived in platform_unix; no WebGPU consumer of GL exists).
#   * Vulkan OFF  -> drops Vulkan + ShaderC. The BSL->SPIR-V->WGSL shader chain
#                    (M3) will re-introduce shaderc/Tint through the WebGPU backend,
#                    not through WITH_VULKAN_BACKEND.
#
# These run after the option() declarations (root L933/L941) but before the gpu
# subdirectory is added, so FORCE wins.
set(WITH_OPENGL_BACKEND OFF CACHE BOOL "" FORCE)  # no GL in a WebGPU-only build (drops Epoxy)
set(WITH_VULKAN_BACKEND OFF CACHE BOOL "" FORCE)  # WebGPU backend replaces Vulkan/ShaderC

# Neutralize Epoxy so nothing downstream can hard-require it. dependency_targets.cmake
# still builds an INTERFACE bf_deps_epoxy from these vars (harmless when empty); the
# only find_package(Epoxy REQUIRED) was in platform_unix, which we do not include.
set(EPOXY_INCLUDE_DIRS "" CACHE STRING "" FORCE)
set(EPOXY_LIBRARIES    "" CACHE STRING "" FORCE)

# -----------------------------------------------------------------------------
# M1 pre-M2 mandatory-dependency PLACEHOLDERS (TEMPORARY — deleted at M2)
#
# Blender 5.2 made OpenColorIO / OpenImageIO(+oiiotool) / OpenEXR / fmt / Eigen3
# non-optional: build_files/cmake/platform/dependency_targets.cmake ALIASes them
# unconditionally (lines 82,93,143-144,185,464 @ fbe6228777e7), and
# source/creator/CMakeLists.txt:42 splices ${TBB_LIBRARIES} with no WITH_ guard.
# In a native build platform_unix.cmake's find_package_wrapper() creates these
# imported targets; there is no lib/wasm harvest until M2, so with WITH_LIBS_PRECOMPILED
# OFF we define empty INTERFACE placeholders purely so the CMAKE configure completes
# and can be regression-checked (proving the CMake spine, not building anything).
#
# This is NOT parity theater and NOT a test/harness stub: it satisfies configure-time
# target existence only, is fenced behind `NOT WITH_LIBS_PRECOMPILED`, and is
# superseded automatically the moment lib/wasm is populated (then real find_package()
# results supply these targets). Delete this whole block when the M2 superbuild lands.
if(NOT WITH_LIBS_PRECOMPILED)
  foreach(_bw_iface
      OpenColorIO::OpenColorIO
      OpenImageIO::OpenImageIO
      OpenEXR::OpenEXR
      fmt::fmt
      Eigen3::Eigen
      TBB::tbb)
    if(NOT TARGET ${_bw_iface})
      add_library(${_bw_iface} INTERFACE IMPORTED GLOBAL)
    endif()
  endforeach()
  unset(_bw_iface)

  # oiiotool is consumed via get_target_property(... LOCATION) at
  # dependency_targets.cmake:144; the property only has to READ at configure time
  # (data-gen steps that would actually RUN it are build-time, and M1 does not build).
  if(NOT TARGET OpenImageIO::oiiotool)
    add_executable(OpenImageIO::oiiotool IMPORTED GLOBAL)
    set_target_properties(OpenImageIO::oiiotool PROPERTIES
      IMPORTED_LOCATION "${CMAKE_BINARY_DIR}/bw_m1_placeholder/oiiotool")
  endif()

  # TBB: WITH_TBB is ON; source/creator splices ${TBB_LIBRARIES} into LIB, so an
  # empty var aborts. Placeholder path only (never linked in an M1 configure).
  set(TBB_LIBRARIES    "${CMAKE_BINARY_DIR}/bw_m1_placeholder/libtbb.a" CACHE STRING "" FORCE)
  set(TBB_INCLUDE_DIRS "${CMAKE_BINARY_DIR}/bw_m1_placeholder"          CACHE PATH   "" FORCE)

  if(FIRST_RUN)
    message(STATUS "blender-web: M1 placeholder dep targets active "
                   "(OCIO/OIIO/oiiotool/OpenEXR/fmt/Eigen3/TBB) — replaced by lib/wasm at M2.")
  endif()
endif()

# -----------------------------------------------------------------------------
# Toolchain sanity: mono-wasm, no LTO on dev/iteration builds
#
# GOAL.md: "mono-wasm (no dynamic linking ... kills DCE)"; "Dev links at -O0/-O1,
# never LTO on iteration builds". The -O level is driven by CMAKE_BUILD_TYPE; here
# we only guarantee LTO stays off so incremental links stay fast. Flip these to a
# release profile in a later ADR, not by hand.

set(WITH_COMPILER_LTO OFF CACHE BOOL "" FORCE)

# -----------------------------------------------------------------------------
# Compiler flags (C and C++)
#
# -pthread enables atomics + bulk-memory and shared-memory codegen; it must be
# present at BOTH compile and link. Everything else memory/GPU-related is a
# link-time -s option (below).

set(_WASM_COMPILE_FLAGS "-pthread")
string(APPEND CMAKE_C_FLAGS   " ${_WASM_COMPILE_FLAGS}")
string(APPEND CMAKE_CXX_FLAGS " ${_WASM_COMPILE_FLAGS}")
string(APPEND PLATFORM_CFLAGS " ${_WASM_COMPILE_FLAGS}")
unset(_WASM_COMPILE_FLAGS)

# -----------------------------------------------------------------------------
# Linker flags
#
# Per GOAL.md "Emscripten posture". Applied to every linked target through the
# root CMakeLists.txt's setup_platform_linker_flags (PLATFORM_LINKFLAGS ->
# CMAKE_EXE_LINKER_FLAGS).
#
#   -pthread                         threads (must match compile side)
#   -sPROXY_TO_PTHREAD               run main() off the browser main thread
#   -sMALLOC=mimalloc                thread-scalable allocator (TBB malloc proxy OFF)
#   -sWASM_BIGINT                    i64 <-> BigInt at the JS boundary, no legalization
#   -sALLOW_MEMORY_GROWTH            growable heap (Blender scenes are unbounded)
#
# Note: `-pthread` on the link line is what pulls in the shared-memory + worker
# runtime; PTHREAD_POOL_SIZE / INITIAL_MEMORY tuning is deferred to the runtime
# launcher, not baked here.

string(APPEND PLATFORM_LINKFLAGS
  " -pthread"
  " -sPROXY_TO_PTHREAD"
  " -sMALLOC=mimalloc"
  " -sWASM_BIGINT"
  " -sALLOW_MEMORY_GROWTH"
)

# Fast-path guard for dev/iteration links only: fail loudly if a post-link pass
# would rewrite the wasm (which would silently invalidate the incremental cache).
# Not safe for optimized release links, so gate it on non-Release build types.
if(NOT CMAKE_BUILD_TYPE STREQUAL "Release")
  string(APPEND PLATFORM_LINKFLAGS " -sERROR_ON_WASM_CHANGES_AFTER_LINK")
endif()

# -----------------------------------------------------------------------------
# Reserved for later milestones (intentionally NOT enabled yet)
#
#   --use-port=emdawnwebgpu   GPU backend (M3/M4). webgpu_cpp.h is unstable; the
#                             port version is pinned when the WebGPU backend lands.
#   -sJSPI                    JS Promise Integration for the event loop (M4+),
#                             replacing Asyncify's ~50% size tax. Chrome 137 floor.
#
# string(APPEND PLATFORM_LINKFLAGS " --use-port=emdawnwebgpu -sJSPI")

# No system link libraries on wasm (everything is static or a -s runtime option).
# PLATFORM_LINKLIBS is left as initialised (empty) by the root CMakeLists.txt.
