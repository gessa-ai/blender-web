# SPDX-FileCopyrightText: 2026 blender-web contributors
#
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Ported for the web from build_files/cmake/platform/platform_unix.cmake @ fbe6228777e7
#
# SHADOW STUB for the M1 configure-mapping experiment.
#
# Emscripten is CMake-UNIX-AND-NOT-APPLE, so upstream CMakeLists.txt:1542
# unconditionally `include(platform_unix)`, which hard-requires the full Linux
# precompiled dependency set (JPEG/PNG/ZLIB/... all REQUIRED). None of those
# exist for wasm yet (no lib/wasm superbuild). This file is placed FIRST on
# CMAKE_MODULE_PATH (via -DCMAKE_MODULE_PATH=patches/cmake_wasm) so that
# `include(platform_unix)` resolves to THIS stub instead of the real one,
# letting us map what the REST of Blender's CMake demands after the platform
# block. It is NOT a real port target — the eventual fix is a genuine
# platform_web.cmake that find_package()s the harvested lib/wasm deps.

set(WITH_LIBS_PRECOMPILED OFF CACHE BOOL "" FORCE)
set(WITH_CPU_CHECK        OFF CACHE BOOL "" FORCE)
unset(LIBDIR)

# Provide the wrapper the rest of the tree references, as a plain find_package.
macro(find_package_wrapper)
  find_package(${ARGV})
endmacro()

message(STATUS "[blender-web] platform_unix SHADOW STUB active (no precompiled libs)")

# --- Placeholder imported targets for the now-mandatory deps -----------------
# dependency_targets.cmake (CMakeLists.txt:1681) unconditionally ALIASes these,
# so they must exist as real targets. These fakes let the configure proceed
# PAST the mandatory-dependency wall so we can map the source tree's demands.
# They will be replaced by genuine find_package() results once lib/wasm exists.
set(_BW_FAKE "$ENV{BW_FAKESYS}")
foreach(_t OpenColorIO::OpenColorIO OpenImageIO::OpenImageIO OpenEXR::OpenEXR fmt::fmt)
  if(NOT TARGET ${_t})
    add_library(${_t} INTERFACE IMPORTED GLOBAL)
  endif()
endforeach()
if(NOT TARGET OpenImageIO::oiiotool)
  add_executable(OpenImageIO::oiiotool IMPORTED GLOBAL)
  set_target_properties(OpenImageIO::oiiotool PROPERTIES
    IMPORTED_LOCATION "${_BW_FAKE}/bin/oiiotool")
endif()

# --- Python placeholder ------------------------------------------------------
# WITH_PYTHON is mandatory (Python UI layer). CMakeLists.txt:2267 fatals unless
# PYTHON_INCLUDE_DIR/Python.h exist. Point at a fake header for mapping.
set(PYTHON_VERSION      "3.13" CACHE STRING "" FORCE)
set(PYTHON_INCLUDE_DIR  "${_BW_FAKE}/pyinc" CACHE PATH "" FORCE)
set(PYTHON_INCLUDE_DIRS "${_BW_FAKE}/pyinc" CACHE PATH "" FORCE)
set(PYTHON_INCLUDE_CONFIG_DIR "${_BW_FAKE}/pyinc" CACHE PATH "" FORCE)
set(PYTHON_LIBRARY      "${_BW_FAKE}/pyinc/libpython3.13.a" CACHE FILEPATH "" FORCE)
set(PYTHON_LIBPATH      "${_BW_FAKE}/pyinc" CACHE PATH "" FORCE)
set(PYTHON_EXECUTABLE   "${_BW_FAKE}/bin/oiiotool" CACHE FILEPATH "" FORCE)  # placeholder exe

# --- TBB placeholder ---------------------------------------------------------
# WITH_TBB is mandatory (task scheduler). source/creator/CMakeLists.txt:42 does
# list(INSERT LIB 0 ${TBB_LIBRARIES}); an empty var aborts. Placeholder only.
set(TBB_LIBRARIES   "${_BW_FAKE}/pyinc/libtbb.a" CACHE STRING "" FORCE)
set(TBB_INCLUDE_DIRS "${_BW_FAKE}/pyinc" CACHE PATH "" FORCE)
if(NOT TARGET TBB::tbb)
  add_library(TBB::tbb INTERFACE IMPORTED GLOBAL)
endif()
