# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

cmake_minimum_required(VERSION 3.16)
project(wgpu_query_wasm_smoke CXX)

if(NOT EMSCRIPTEN)
  message(FATAL_ERROR "This project builds only the WebAssembly parity leg")
endif()
if(NOT DEFINED BW_INTEGRATED_QUERY_SOURCE_DIR OR
   NOT IS_ABSOLUTE "${BW_INTEGRATED_QUERY_SOURCE_DIR}" OR
   NOT IS_DIRECTORY "${BW_INTEGRATED_QUERY_SOURCE_DIR}")
  message(FATAL_ERROR
    "BW_INTEGRATED_QUERY_SOURCE_DIR must name the absolute canonical WebGPU source directory")
endif()
if(NOT DEFINED BW_UPSTREAM_DIR OR
   NOT IS_ABSOLUTE "${BW_UPSTREAM_DIR}" OR
   NOT IS_DIRECTORY "${BW_UPSTREAM_DIR}")
  message(FATAL_ERROR "BW_UPSTREAM_DIR must name the absolute pinned Blender checkout")
endif()

set(_bw_integrated_query_test
  "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-query-integrated-smoke/integrated_query_test.cc"
)
foreach(_bw_source
    "${_bw_integrated_query_test}"
    "${BW_INTEGRATED_QUERY_SOURCE_DIR}/wgpu_query.cc"
    "${BW_INTEGRATED_QUERY_SOURCE_DIR}/wgpu_query.hh"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_query.hh"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib/BLI_assert.h"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib/BLI_span.hh")
  if(NOT IS_ABSOLUTE "${_bw_source}" OR NOT EXISTS "${_bw_source}")
    message(FATAL_ERROR "integrated WebGPU query input is missing: ${_bw_source}")
  endif()
endforeach()

add_executable(wgpu_query_integrated_smoke
  "${_bw_integrated_query_test}"
  "${BW_INTEGRATED_QUERY_SOURCE_DIR}/wgpu_query.cc"
)
set_target_properties(wgpu_query_integrated_smoke PROPERTIES
  CXX_STANDARD 20
  CXX_STANDARD_REQUIRED ON
  OUTPUT_NAME integrated_query
  SUFFIX .js
)
target_include_directories(wgpu_query_integrated_smoke PRIVATE
  "${BW_INTEGRATED_QUERY_SOURCE_DIR}"
  "${BW_UPSTREAM_DIR}/source/blender/gpu/intern"
  "${BW_UPSTREAM_DIR}/source/blender/blenlib"
)
target_compile_options(wgpu_query_integrated_smoke PRIVATE
  -pthread
  -fexceptions
)
target_link_options(wgpu_query_integrated_smoke PRIVATE
  -pthread
  -fexceptions
  "-sENVIRONMENT=node"
  "-sEXIT_RUNTIME=1"
  "-sSTACK_SIZE=8388608"
  "-sINITIAL_MEMORY=33554432"
  "-sALLOW_MEMORY_GROWTH=1"
  "-sPTHREAD_POOL_SIZE=1"
)
