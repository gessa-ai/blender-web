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
