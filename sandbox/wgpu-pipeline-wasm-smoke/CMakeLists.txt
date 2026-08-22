# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

cmake_minimum_required(VERSION 3.16)
project(wgpu_pipeline_wasm_smoke CXX)

if(NOT EMSCRIPTEN)
  message(FATAL_ERROR "This project builds only the WebAssembly parity leg")
endif()
if(NOT DEFINED BW_INTEGRATED_PIPELINE_SOURCE_DIR OR
   NOT IS_ABSOLUTE "${BW_INTEGRATED_PIPELINE_SOURCE_DIR}" OR
   NOT IS_DIRECTORY "${BW_INTEGRATED_PIPELINE_SOURCE_DIR}")
  message(FATAL_ERROR
    "BW_INTEGRATED_PIPELINE_SOURCE_DIR must name the absolute canonical WebGPU source directory")
endif()
if(NOT DEFINED BW_UPSTREAM_DIR OR
   NOT IS_ABSOLUTE "${BW_UPSTREAM_DIR}" OR
   NOT IS_DIRECTORY "${BW_UPSTREAM_DIR}")
  message(FATAL_ERROR "BW_UPSTREAM_DIR must name the absolute pinned Blender checkout")
endif()
if(NOT DEFINED BW_WASM_INCLUDE_DIR OR
   NOT IS_ABSOLUTE "${BW_WASM_INCLUDE_DIR}" OR
   NOT EXISTS "${BW_WASM_INCLUDE_DIR}/fmt/ranges.h")
  message(FATAL_ERROR "BW_WASM_INCLUDE_DIR must name the harvested Wasm include root")
endif()

foreach(_bw_source wgpu_pipeline.cc wgpu_pipeline.hh)
  set(_bw_source_path "${BW_INTEGRATED_PIPELINE_SOURCE_DIR}/${_bw_source}")
  if(NOT EXISTS "${_bw_source_path}")
    message(FATAL_ERROR "integrated WebGPU pipeline input is missing: ${_bw_source_path}")
  endif()
endforeach()
foreach(_bw_source
    "${BW_UPSTREAM_DIR}/source/blender/blenlib/BLI_assert.h"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern/BLI_assert.cc")
  if(NOT EXISTS "${_bw_source}")
    message(FATAL_ERROR "integrated WebGPU pipeline dependency is missing: ${_bw_source}")
  endif()
endforeach()

set(_bw_integrated_pipeline_test
  "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-pipeline-integrated-smoke/integrated_pipeline_test.cc"
)
if(NOT EXISTS "${_bw_integrated_pipeline_test}")
  message(FATAL_ERROR "integrated WebGPU pipeline test is missing: ${_bw_integrated_pipeline_test}")
endif()

add_executable(wgpu_pipeline_integrated_smoke
  "${_bw_integrated_pipeline_test}"
  "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern/BLI_assert.cc"
  "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_vertex_format.cc"
)
target_compile_definitions(wgpu_pipeline_integrated_smoke PRIVATE
  BW_WGPU_PIPELINE_SOURCE="${BW_INTEGRATED_PIPELINE_SOURCE_DIR}/wgpu_pipeline.cc"
)
set_target_properties(wgpu_pipeline_integrated_smoke PROPERTIES
  CXX_STANDARD 20
  CXX_STANDARD_REQUIRED ON
  OUTPUT_NAME integrated_pipeline
  SUFFIX .js
)
target_include_directories(wgpu_pipeline_integrated_smoke PRIVATE
  "${BW_INTEGRATED_PIPELINE_SOURCE_DIR}"
  "${BW_UPSTREAM_DIR}/source/blender/gpu"
  "${BW_UPSTREAM_DIR}/source/blender/gpu/intern"
  "${BW_UPSTREAM_DIR}/source/blender/blenlib"
  "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern"
  "${BW_UPSTREAM_DIR}/source/blender/makesdna"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc"
  "${BW_WASM_INCLUDE_DIR}"
)
target_compile_options(wgpu_pipeline_integrated_smoke PRIVATE
  -pthread
  -fexceptions
  -ffunction-sections
  -fdata-sections
  "--use-port=emdawnwebgpu"
)
target_link_options(wgpu_pipeline_integrated_smoke PRIVATE
  -pthread
  -fexceptions
  "--use-port=emdawnwebgpu"
  "-Wl,--gc-sections"
  "-sENVIRONMENT=node"
  "-sEXIT_RUNTIME=1"
  "-sSTACK_SIZE=8388608"
  "-sINITIAL_MEMORY=67108864"
  "-sALLOW_MEMORY_GROWTH=1"
  "-sPTHREAD_POOL_SIZE=1"
)
