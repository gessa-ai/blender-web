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

# check_freetype_for_brotli() is defined in platform_unix.cmake, which this file
# replaces for the Emscripten branch. Reproduced verbatim (per
# platform_unix.cmake @ fbe6228777e7, L173-191): the Freetype-with-brotli assert
# is run against our own cross-compiled FreeType (built FT_REQUIRE_BROTLI=ON).
function(check_freetype_for_brotli)
  if((DEFINED HAVE_BROTLI) AND (DEFINED HAVE_BROTLI_INC))
    if(HAVE_BROTLI AND ("${HAVE_BROTLI_INC}" STREQUAL "${FREETYPE_INCLUDE_DIRS}"))
      # Pass, the includes didn't change, use the cached value.
      return()
    endif()
  endif()

  unset(HAVE_BROTLI CACHE)
  include(CheckSymbolExists)
  set(CMAKE_REQUIRED_INCLUDES ${FREETYPE_INCLUDE_DIRS})
  check_symbol_exists(FT_CONFIG_OPTION_USE_BROTLI "freetype/config/ftconfig.h" HAVE_BROTLI)
  unset(CMAKE_REQUIRED_INCLUDES)
  if(NOT HAVE_BROTLI)
    unset(HAVE_BROTLI CACHE)
    message(FATAL_ERROR "Freetype needs to be compiled with brotli support!")
  endif()
  set(HAVE_BROTLI_INC "${FREETYPE_INCLUDE_DIRS}" CACHE INTERNAL "")
endfunction()

# -----------------------------------------------------------------------------
# Host codegen tools (makesdna / makesrna / ...) — run under node at build time
#
# Blender's build compiles several C++ "host tools" and then EXECUTES them during
# the build to GENERATE source (DNA structs, RNA bindings; later milestones: glsl
# datatoc, icons, locale). Under Emscripten those tools are .wasm/.js, not native
# binaries, so two things must change versus the browser link profile:
#
#   1. Invocation. The tool's add_custom_command must run `node <tool>.js ...`, not
#      the .js file directly (which fails "permission denied"). The Emscripten
#      toolchain sets CMAKE_CROSSCOMPILING_EMULATOR to node (Emscripten.cmake
#      @ L373-378). CMake applies that emulator automatically ONLY when a custom
#      command's COMMAND is a bare target name; Blender invokes the tool via
#      `cmake -E env "$<TARGET_FILE:tool>"`, which bypasses that path. So each such
#      custom_command is patched to prepend ${CMAKE_CROSSCOMPILING_EMULATOR} before
#      the tool path (patches/0002-hosttools-node.patch). On native builds the var
#      is empty, so the prefix is a no-op.
#
#   2. Link profile. The default browser profile (PLATFORM_LINKFLAGS) proxies main()
#      to a worker (-sPROXY_TO_PTHREAD) and gives the module no host filesystem —
#      both wrong for a build-time CLI. blender_web_host_tool() below overwrites the
#      target's LINK_FLAGS with a node-runnable profile: main() on the main thread,
#      -sEXIT_RUNTIME so the process exits, -sNODERAWFS so the absolute host paths
#      passed as argv read/write the real filesystem. This is the exact mechanism
#      proven manually in notes/m1-integrate.md (blocker #1, "FIX PATH PROVEN").
#
# Later milestones that add host tools (shader/glsl codegen, icon and locale
# generation) MUST reuse BOTH halves — see notes/m1-hosttools.md.
function(blender_web_host_tool target)
  if(NOT EMSCRIPTEN)
    return()
  endif()
  # OVERWRITE (not append) the LINK_FLAGS that setup_platform_linker_flags() set
  # from PLATFORM_LINKFLAGS: -sPROXY_TO_PTHREAD, -sMALLOC=mimalloc and the
  # changes-after-link guard are all wrong for a node CLI. -pthread stays — the
  # tool's objects were compiled with it (shared-memory ABI must match).
  set_target_properties(${target} PROPERTIES
    LINK_FLAGS
      "-pthread -sNODERAWFS -sEXIT_RUNTIME=1 -sALLOW_MEMORY_GROWTH -sWASM_BIGINT -sPROXY_TO_PTHREAD=0")
endfunction()

# -----------------------------------------------------------------------------
# Native host codegen tools (ADR-002)
#
# shader_tool and datatoc emit target-INDEPENDENT text (byte-identity verified,
# native == wasm wherever the wasm tool functions — notes/m1-shader-codegen-wasm.md).
# The wasm build of shader_tool mis-tokenizes some shaders (silent corruption /
# hangs), so per ADR-002 these two tools run as NATIVE host binaries built with the
# host compiler into build-hosttools/bin-native/. macros.cmake's data_to_c* and
# shader-info custom commands pick these up via BLENDER_WEB_HOST_TOOLS_DIR. (Unlike
# makesdna/makesrna, which bake target ABI and MUST stay wasm-under-node.)
if(NOT DEFINED BLENDER_WEB_HOST_TOOLS_DIR)
  get_filename_component(BLENDER_WEB_HOST_TOOLS_DIR
    "${BLENDER_WEB_PATCH_DIR}/../build-hosttools/bin-native" ABSOLUTE)
  set(BLENDER_WEB_HOST_TOOLS_DIR "${BLENDER_WEB_HOST_TOOLS_DIR}" CACHE PATH
    "Directory of native host codegen tools (shader_tool, datatoc) per ADR-002")
endif()
if(NOT EXISTS "${BLENDER_WEB_HOST_TOOLS_DIR}/shader_tool"
   OR NOT EXISTS "${BLENDER_WEB_HOST_TOOLS_DIR}/datatoc")
  message(FATAL_ERROR
    "blender-web ADR-002: native host tools not found in "
    "${BLENDER_WEB_HOST_TOOLS_DIR} (need shader_tool + datatoc). "
    "Build them first: see notes/m1-shader-codegen-wasm.md.")
endif()

# Host Python interpreter for build-time codegen SCRIPTS (e.g. discover_nodes.py,
# which generates the node-registration .cc). These are pure-Python and run on the
# BUILD host — unrelated to the embedded interpreter (WITH_PYTHON=OFF for M1). The
# Emscripten toolchain does not set PYTHON_EXECUTABLE, and discover_nodes.py is not
# executable / has no shebang, so Blender's add_node_discovery() would invoke it
# directly and fail with rc 126 ("Permission denied"). Prefer the emsdk-bundled
# python (pinned with the toolchain); else fall back to a host python3, bypassing the
# Emscripten find-root so we resolve a HOST (not target) binary.
if(NOT PYTHON_EXECUTABLE)
  file(GLOB _bw_host_python "${BLENDER_WEB_PATCH_DIR}/../tools/emsdk/python/*/bin/python3")
  if(_bw_host_python)
    list(GET _bw_host_python 0 PYTHON_EXECUTABLE)
  else()
    find_program(PYTHON_EXECUTABLE NAMES python3 python NO_CMAKE_FIND_ROOT_PATH)
  endif()
  set(PYTHON_EXECUTABLE "${PYTHON_EXECUTABLE}" CACHE FILEPATH
    "Host Python for blender-web build-time codegen scripts")
  unset(_bw_host_python)
  message(STATUS "blender-web: host PYTHON_EXECUTABLE = ${PYTHON_EXECUTABLE}")
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
  # The wasm harvest prefix lives at the PORT repo root (lib/wasm), which is the
  # PARENT of the upstream Blender tree passed as -S. CMAKE_SOURCE_DIR is that
  # upstream tree, so anchor LIBDIR on BLENDER_WEB_PATCH_DIR (the port's patches/
  # dir, set by blender_web.cmake) whose parent is the repo root. Fall back to the
  # CMAKE_SOURCE_DIR sibling if the patch dir var is somehow unset.
  if(DEFINED BLENDER_WEB_PATCH_DIR)
    get_filename_component(LIBDIR "${BLENDER_WEB_PATCH_DIR}/../lib/wasm" ABSOLUTE)
  else()
    get_filename_component(LIBDIR "${CMAKE_SOURCE_DIR}/../lib/wasm" ABSOLUTE)
  endif()
endif()

file(GLOB _wasm_libdir_contents "${LIBDIR}/*")
if(_wasm_libdir_contents)
  set(WITH_LIBS_PRECOMPILED ON)
  set(CMAKE_PREFIX_PATH "${LIBDIR}" ${CMAKE_PREFIX_PATH})
  # The Emscripten toolchain re-roots find_library()/find_path()/find_package()
  # at its own sysroot (CMAKE_FIND_ROOT_PATH_MODE_{LIBRARY,INCLUDE}=ONLY), so a
  # bare find_* cannot see lib/wasm. Appending LIBDIR to CMAKE_FIND_ROOT_PATH
  # makes the wasm prefix a first-class search root — the same remedy the dep
  # cross-build scripts used (e.g. opencolorio.sh passes -DCMAKE_FIND_ROOT_PATH).
  # Belt-and-suspenders: the resolution block below also seeds explicit
  # <Pkg>_DIR / <PKG>_LIBRARY hint vars so every find is deterministic.
  list(APPEND CMAKE_FIND_ROOT_PATH "${LIBDIR}")
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
# Dependency resolution against the real lib/wasm prefix (M1.8)
#
# This file REPLACES platform_unix.cmake for the Emscripten branch, so none of
# platform_unix's find_package_wrapper() calls run. We reproduce here exactly the
# subset that the M1 headless core needs — the mandatory, non-optional deps that
# dependency_targets.cmake wires into bf::dependencies::* aliases and that
# blenlib PUBLIC-links (OpenImageIO -> OpenColorIO -> OpenEXR/Imath, fmt, TBB,
# Eigen3, zlib/zstd, plus the JPEG/PNG/Freetype/Brotli mandated finds).
#
# The hint-var set below is the proven consumer contract from the dep cross-build
# scripts (see notes/deps-oiio.md): CONFIG packages get an explicit <Pkg>_DIR;
# module-found libs (ZLIB/JPEG/PNG/Zstd/Freetype/Brotli) get <PKG>_LIBRARY +
# include hints so the emscripten-rerooted find_library() is a deterministic
# no-op. OpenColorIO's installed config chases pystring/minizip-ng through its
# OWN bundled Find modules — those need *_INCLUDE_DIR/_LIBRARY (NOT *_ROOT for
# minizip-ng: the ROOT path hits a get_target_property trap).
#
# Optional/gated deps (Python, Cycles/OSL/Embree, USD, OpenVDB, audio, ...) are
# resolved by their own WITH_-guarded blocks in Blender's tree and are forced OFF
# in patches/blender_web.cmake, so they need nothing here.
if(WITH_LIBS_PRECOMPILED)
  # ---- CONFIG-package location hints ----------------------------------------
  set(fmt_DIR            "${LIBDIR}/lib/cmake/fmt")
  set(Imath_DIR          "${LIBDIR}/lib/cmake/Imath")
  set(OpenEXR_DIR        "${LIBDIR}/lib/cmake/OpenEXR")
  set(libdeflate_DIR     "${LIBDIR}/lib/cmake/libdeflate")   # OpenEXR core find_dependency
  set(openjph_DIR        "${LIBDIR}/lib/cmake/openjph")      # OpenEXR core find_dependency
  set(OpenColorIO_DIR    "${LIBDIR}/lib/cmake/OpenColorIO")
  set(OpenImageIO_DIR    "${LIBDIR}/lib/cmake/OpenImageIO")
  set(TBB_DIR            "${LIBDIR}/lib/cmake/TBB")
  set(Eigen3_DIR         "${LIBDIR}/share/eigen3/cmake")
  set(yaml-cpp_DIR       "${LIBDIR}/lib/cmake/yaml-cpp")     # OCIO find_dependency
  set(yaml-cpp_VERSION   "0.8.0")
  set(tsl-robin-map_DIR  "${LIBDIR}/share/cmake/tsl-robin-map")
  set(TIFF_DIR           "${LIBDIR}/lib/cmake/tiff")
  set(PNG_DIR            "${LIBDIR}/lib/cmake/PNG")
  set(libjpeg-turbo_DIR  "${LIBDIR}/lib/cmake/libjpeg-turbo")
  # expat ships its config under lib/cmake/expat-<version>/ (version-suffixed dir).
  file(GLOB _bw_expat_cfg_dir "${LIBDIR}/lib/cmake/expat-*")
  if(_bw_expat_cfg_dir)
    set(expat_DIR "${_bw_expat_cfg_dir}")
  endif()
  unset(_bw_expat_cfg_dir)

  # ---- Module-found libraries: seed the search results so find_* is a no-op --
  set(ZLIB_ROOT          "${LIBDIR}")
  set(ZLIB_INCLUDE_DIR   "${LIBDIR}/include")
  set(ZLIB_LIBRARY       "${LIBDIR}/lib/libz.a")
  set(JPEG_ROOT          "${LIBDIR}")
  set(JPEG_INCLUDE_DIR   "${LIBDIR}/include")
  set(JPEG_LIBRARY       "${LIBDIR}/lib/libjpeg.a")
  set(PNG_ROOT           "${LIBDIR}")
  set(PNG_PNG_INCLUDE_DIR "${LIBDIR}/include")
  set(PNG_LIBRARY        "${LIBDIR}/lib/libpng16.a")
  set(TIFF_INCLUDE_DIR   "${LIBDIR}/include")
  set(TIFF_LIBRARY       "${LIBDIR}/lib/libtiff.a")
  set(ZSTD_ROOT_DIR      "${LIBDIR}")
  set(ZSTD_INCLUDE_DIR   "${LIBDIR}/include")
  set(ZSTD_LIBRARY       "${LIBDIR}/lib/libzstd.a")
  set(BROTLI_ROOT_DIR    "${LIBDIR}")
  set(FREETYPE_LIBRARY              "${LIBDIR}/lib/libfreetype.a")
  set(FREETYPE_INCLUDE_DIR_ft2build "${LIBDIR}/include/freetype2")
  set(FREETYPE_INCLUDE_DIR_freetype2 "${LIBDIR}/include/freetype2")
  # OCIO bundled Find modules for pystring / minizip-ng (module mode, no config).
  set(pystring_ROOT        "${LIBDIR}")
  set(pystring_INCLUDE_DIR "${LIBDIR}/include")
  set(pystring_LIBRARY     "${LIBDIR}/lib/libpystring.a")
  set(minizip-ng_INCLUDE_DIR "${LIBDIR}/include/minizip-ng/minizip")
  set(minizip-ng_LIBRARY     "${LIBDIR}/lib/libminizip.a")

  # ---- Resolve, leaves first so downstream find_dependency() sees the targets -
  find_package(Threads REQUIRED)
  find_package(fmt REQUIRED)                       # -> fmt::fmt
  find_package(Imath REQUIRED)                     # -> Imath::Imath
  find_package(OpenEXR REQUIRED)                   # -> OpenEXR::OpenEXR
  find_package(ZLIB REQUIRED)                      # -> ZLIB_INCLUDE_DIRS/ZLIB_LIBRARIES
  find_package(Zstd REQUIRED)                      # Blender module -> ZSTD_*
  find_package(JPEG REQUIRED)                      # -> JPEG_INCLUDE_DIR/JPEG_LIBRARIES
  find_package(PNG REQUIRED)                       # -> PNG_INCLUDE_DIRS/PNG_LIBRARIES
  find_package(TIFF REQUIRED)                      # OIIO find_dependency
  find_package(TBB REQUIRED)                       # -> TBB::tbb
  find_package(OpenColorIO 2.0.0 REQUIRED)         # -> OpenColorIO::OpenColorIO
  find_package(OpenImageIO REQUIRED)               # -> OpenImageIO::OpenImageIO
  find_package(Eigen3 REQUIRED)                    # -> Eigen3::Eigen
  find_package(Freetype REQUIRED)                  # -> FREETYPE_INCLUDE_DIRS/FREETYPE_LIBRARIES
  find_package(Brotli REQUIRED)                    # -> BROTLI_LIBRARIES
  check_freetype_for_brotli()

  # ---- Derive the raw vars dependency_targets.cmake consumes ----------------
  # It reads ${TBB_LIBRARIES}/${TBB_INCLUDE_DIRS} (not the TBB::tbb target),
  # mirroring platform_unix.cmake's TBB block.
  if(WITH_TBB AND TARGET TBB::tbb)
    get_target_property(TBB_LIBRARIES    TBB::tbb LOCATION)
    get_target_property(TBB_INCLUDE_DIRS TBB::tbb INTERFACE_INCLUDE_DIRECTORIES)
  endif()

  # OpenImageIO was cross-built with OIIO_BUILD_TOOLS=OFF, so its config does NOT
  # export the OpenImageIO::oiiotool target. dependency_targets.cmake:144 reads its
  # LOCATION unconditionally (a build-time datafiles/icon generator that M1 never
  # runs; a wasm oiiotool could not run on the host anyway). Provide the imported
  # executable so the configure-time get_target_property() resolves. M2 supplies a
  # real NATIVE oiiotool here when it wires up the datafiles generation step.
  if(NOT TARGET OpenImageIO::oiiotool)
    add_executable(OpenImageIO::oiiotool IMPORTED GLOBAL)
    set_target_properties(OpenImageIO::oiiotool PROPERTIES
      IMPORTED_LOCATION "${CMAKE_BINARY_DIR}/bw_no_wasm_oiiotool")
  endif()

  if(FIRST_RUN)
    message(STATUS "blender-web: resolved wasm deps from ${LIBDIR} "
                   "(OIIO/OCIO/OpenEXR/Imath/fmt/TBB/Eigen3/JPEG/PNG/TIFF/zlib/zstd/Freetype/Brotli)")
  endif()
else()
  # ---------------------------------------------------------------------------
  # Pre-M2 fallback ONLY (lib/wasm empty): empty INTERFACE placeholders so a bare
  # CMake spine still configures for regression-checking. This branch is DEAD once
  # the superbuild has populated lib/wasm (WITH_LIBS_PRECOMPILED flips ON above).
  # Not parity theater: fenced behind an empty prefix, builds nothing.
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
  if(NOT TARGET OpenImageIO::oiiotool)
    add_executable(OpenImageIO::oiiotool IMPORTED GLOBAL)
    set_target_properties(OpenImageIO::oiiotool PROPERTIES
      IMPORTED_LOCATION "${CMAKE_BINARY_DIR}/bw_m1_placeholder/oiiotool")
  endif()
  set(TBB_LIBRARIES    "${CMAKE_BINARY_DIR}/bw_m1_placeholder/libtbb.a" CACHE STRING "" FORCE)
  set(TBB_INCLUDE_DIRS "${CMAKE_BINARY_DIR}/bw_m1_placeholder"          CACHE PATH   "" FORCE)
  if(FIRST_RUN)
    message(STATUS "blender-web: lib/wasm empty — empty placeholder dep targets (pre-M2).")
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

# -funsigned-char is MANDATORY, not stylistic: Blender's DNA declares fixed
# underlying-type enums like `enum X : char { ... = 1 << 7 }` (== 128) that only
# compile where `char` is unsigned. Every native platform sets it (platform_unix
# L895, platform_apple L161, platform_win32 via /clang:); Emscripten defaults
# `char` to SIGNED, so without this makesdna.cc et al. fail -Wc++11-narrowing.
# -fno-strict-aliasing and -ffp-contract=off match native for correctness + FP
# determinism (tier-(a) parity depends on the latter). -pthread: atomics + shared
# memory, required at compile and link.
# -fexceptions (emscripten JS-based EH) is MANDATORY, not optional: TBB, OpenImageIO
# and gflags all throw C++ exceptions, and gtest itself throws on assertion in some
# modes. Emscripten DISABLES exception catching by default, so a throw calls abort()
# instead of unwinding -> the gtest runner aborts at startup (verified: ___cxa_throw
# -> Aborted). Must be uniform across every object AND the link (see notes/deps-tbb.md
# "consume TBB under wasm" table). Whole-build commit to -fwasm-exceptions is the
# faster later alternative once every dep is rebuilt with it uniformly.
set(_WASM_COMPILE_FLAGS "-pthread -fexceptions -funsigned-char -fno-strict-aliasing -ffp-contract=off")
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
  " -fexceptions"
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

# ---- M1 tier-(a) test-runner profile (gtest builds only) -------------------
# The blenlib/bmesh gtest binaries run under node, not a browser, and must:
#   * -sNODERAWFS      map argv paths straight to node's real filesystem, so the
#                      fstream/fileops suites can open the real UTF-8 asset files
#                      under `--test-assets-dir` (verified: fileops.fstream_open_*
#                      go RED->GREEN with NODERAWFS + a real assets dir). Native
#                      CI likewise requires --test-assets-dir; this is faithful,
#                      not a weakening.
#   * -sEXIT_RUNTIME=1 make the process exit with RUN_ALL_TESTS()'s return code
#                      (a PROXY_TO_PTHREAD runner otherwise keeps node's worker
#                      pool alive after main returns -> the harness would hang).
# Gated on WITH_GTESTS so the eventual browser `blender` target never inherits
# NODERAWFS. Host codegen tools (makesdna/makesrna) set their own LINK_FLAGS via
# blender_web_host_tool() and already carry both flags, so this is a harmless
# duplicate for them.
if(WITH_GTESTS)
  string(APPEND PLATFORM_LINKFLAGS " -sNODERAWFS -sEXIT_RUNTIME=1")
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
