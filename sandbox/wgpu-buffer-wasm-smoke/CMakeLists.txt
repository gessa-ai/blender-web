# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

cmake_minimum_required(VERSION 3.16)
project(wgpu_buffer_wasm_smoke CXX)

if(NOT EMSCRIPTEN)
  message(FATAL_ERROR "This project builds only the WebAssembly parity leg")
endif()
if(NOT DEFINED BW_INTEGRATED_BUFFER_SOURCE_DIR OR
   NOT IS_ABSOLUTE "${BW_INTEGRATED_BUFFER_SOURCE_DIR}" OR
   NOT IS_DIRECTORY "${BW_INTEGRATED_BUFFER_SOURCE_DIR}")
  message(FATAL_ERROR
    "BW_INTEGRATED_BUFFER_SOURCE_DIR must name the absolute canonical WebGPU source directory")
endif()

set(_bw_integrated_buffer_sources
  wgpu_buffer.cc
  wgpu_buffer.hh
  wgpu_common.hh
  wgpu_readback.cc
  wgpu_readback.hh
)
foreach(_bw_source IN LISTS _bw_integrated_buffer_sources)
  set(_bw_source_path "${BW_INTEGRATED_BUFFER_SOURCE_DIR}/${_bw_source}")
  if(NOT EXISTS "${_bw_source_path}")
    message(FATAL_ERROR "integrated WebGPU buffer input is missing: ${_bw_source_path}")
  endif()
endforeach()

set(_bw_integrated_buffer_test
  "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-buffer-integrated-smoke/integrated_buffer_test.cc"
)
if(NOT EXISTS "${_bw_integrated_buffer_test}")
  message(FATAL_ERROR "integrated WebGPU buffer test is missing: ${_bw_integrated_buffer_test}")
endif()

add_executable(wgpu_buffer_integrated_smoke
  "${_bw_integrated_buffer_test}"
  "${BW_INTEGRATED_BUFFER_SOURCE_DIR}/wgpu_buffer.cc"
  "${BW_INTEGRATED_BUFFER_SOURCE_DIR}/wgpu_readback.cc"
)
set_target_properties(wgpu_buffer_integrated_smoke PROPERTIES
  CXX_STANDARD 20
  CXX_STANDARD_REQUIRED ON
  OUTPUT_NAME integrated_buffer
  SUFFIX .js
)
target_include_directories(wgpu_buffer_integrated_smoke PRIVATE
  "${BW_INTEGRATED_BUFFER_SOURCE_DIR}"
)
target_compile_options(wgpu_buffer_integrated_smoke PRIVATE
  -pthread
  -fexceptions
  "--use-port=emdawnwebgpu"
)
target_link_options(wgpu_buffer_integrated_smoke PRIVATE
  -pthread
  -fexceptions
  "--use-port=emdawnwebgpu"
  "-sENVIRONMENT=node"
  "-sEXIT_RUNTIME=1"
  "-sSTACK_SIZE=8388608"
  "-sINITIAL_MEMORY=67108864"
  "-sALLOW_MEMORY_GROWTH=1"
  "-sPTHREAD_POOL_SIZE=1"
)
