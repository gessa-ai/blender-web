# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

cmake_minimum_required(VERSION 3.16)
project(wgpu_state_wasm_smoke CXX)

if(NOT EMSCRIPTEN)
  message(FATAL_ERROR "This project builds only the WebAssembly parity leg")
endif()
if(NOT DEFINED BW_INTEGRATED_STATE_SOURCE_DIR OR
   NOT IS_ABSOLUTE "${BW_INTEGRATED_STATE_SOURCE_DIR}" OR
   NOT IS_DIRECTORY "${BW_INTEGRATED_STATE_SOURCE_DIR}")
  message(FATAL_ERROR
    "BW_INTEGRATED_STATE_SOURCE_DIR must name the absolute canonical WebGPU source directory")
endif()
if(NOT DEFINED BW_UPSTREAM_DIR OR
   NOT IS_ABSOLUTE "${BW_UPSTREAM_DIR}" OR
   NOT IS_DIRECTORY "${BW_UPSTREAM_DIR}")
  message(FATAL_ERROR "BW_UPSTREAM_DIR must name the absolute pinned Blender checkout")
endif()

foreach(_bw_source wgpu_state_table.cc wgpu_state_table.hh)
  set(_bw_source_path "${BW_INTEGRATED_STATE_SOURCE_DIR}/${_bw_source}")
  if(NOT EXISTS "${_bw_source_path}")
    message(FATAL_ERROR "integrated WebGPU state input is missing: ${_bw_source_path}")
  endif()
endforeach()
foreach(_bw_source
    "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_state.hh"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib/BLI_enum_flags.hh"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib/BLI_sys_types.h")
  if(NOT EXISTS "${_bw_source}")
    message(FATAL_ERROR "integrated WebGPU state dependency is missing: ${_bw_source}")
  endif()
endforeach()

set(_bw_integrated_state_test
  "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-state-integrated-smoke/integrated_state_test.cc"
)
if(NOT EXISTS "${_bw_integrated_state_test}")
  message(FATAL_ERROR "integrated WebGPU state test is missing: ${_bw_integrated_state_test}")
endif()

add_executable(wgpu_state_integrated_smoke
  "${_bw_integrated_state_test}"
  "${BW_INTEGRATED_STATE_SOURCE_DIR}/wgpu_state_table.cc"
)
set_target_properties(wgpu_state_integrated_smoke PROPERTIES
  CXX_STANDARD 20
  CXX_STANDARD_REQUIRED ON
  OUTPUT_NAME integrated_state
  SUFFIX .js
)
target_include_directories(wgpu_state_integrated_smoke PRIVATE
  "${BW_INTEGRATED_STATE_SOURCE_DIR}"
  "${BW_UPSTREAM_DIR}/source/blender/gpu"
  "${BW_UPSTREAM_DIR}/source/blender/blenlib"
)
target_compile_options(wgpu_state_integrated_smoke PRIVATE
  -pthread
  -fexceptions
  "--use-port=emdawnwebgpu"
)
target_link_options(wgpu_state_integrated_smoke PRIVATE
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
