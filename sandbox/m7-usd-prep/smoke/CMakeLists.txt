# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.28)
project(openusd_wasm_core_smoke LANGUAGES CXX)

if(NOT EMSCRIPTEN)
  message(FATAL_ERROR "This smoke must be configured through emcmake")
endif()
if(NOT OPENUSD_ROOT OR NOT WASM_DEPS_ROOT)
  message(FATAL_ERROR "OPENUSD_ROOT and WASM_DEPS_ROOT are required")
endif()

list(PREPEND CMAKE_PREFIX_PATH "${OPENUSD_ROOT}" "${WASM_DEPS_ROOT}")
set(TBB_DIR "${WASM_DEPS_ROOT}/lib/cmake/TBB")
set(PXR_FIND_TBB_IN_CONFIG ON)
# The OpenUSD install puts pxrConfig.cmake directly in its prefix. Emscripten's
# cross-compile root-path policy otherwise prepends the sysroot and hides it.
set(pxr_DIR "${OPENUSD_ROOT}")
find_package(pxr CONFIG REQUIRED NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)

add_executable(usd_core_smoke usd_core_smoke.cc)
set_target_properties(usd_core_smoke PROPERTIES
  CXX_STANDARD 17
  CXX_STANDARD_REQUIRED ON
  SUFFIX ".js"
)
target_compile_options(usd_core_smoke PRIVATE -pthread --use-port=zlib)
target_link_options(usd_core_smoke PRIVATE
  -pthread
  --use-port=zlib
  -sWASM_BIGINT=1
  -sPROXY_TO_PTHREAD=1
  -sPTHREAD_POOL_SIZE=4
  -sEXIT_RUNTIME=1
  -sALLOW_MEMORY_GROWTH=1
)

# usdShaders is a static Emscripten plugin in this profile. Its imported target
# whole-archives usd_m and propagates all /usd plugInfo/schema --embed-file flags.
# Linking the target instead of a bare archive is a load-bearing part of the proof.
target_link_libraries(usd_core_smoke PRIVATE usdShaders)
