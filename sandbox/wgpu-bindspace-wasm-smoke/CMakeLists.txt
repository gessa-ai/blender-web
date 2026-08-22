# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

cmake_minimum_required(VERSION 3.16)
project(wgpu_bindspace_wasm_smoke CXX)

if(NOT EMSCRIPTEN)
  message(FATAL_ERROR "This project builds only the WebAssembly parity leg")
endif()
if(NOT DEFINED BW_INTEGRATED_BINDSPACE_SOURCE_DIR OR
   NOT IS_ABSOLUTE "${BW_INTEGRATED_BINDSPACE_SOURCE_DIR}" OR
   NOT IS_DIRECTORY "${BW_INTEGRATED_BINDSPACE_SOURCE_DIR}")
  message(FATAL_ERROR
    "BW_INTEGRATED_BINDSPACE_SOURCE_DIR must name the absolute canonical WebGPU source directory")
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
if(NOT DEFINED BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE OR
   NOT IS_ABSOLUTE "${BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE}" OR
   NOT EXISTS "${BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE}")
  message(FATAL_ERROR
    "BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE must name the extracted canonical policy")
endif()
if(NOT DEFINED BW_WGPU_DUMMY_VERTEX_SOURCE OR
   NOT IS_ABSOLUTE "${BW_WGPU_DUMMY_VERTEX_SOURCE}" OR
   NOT EXISTS "${BW_WGPU_DUMMY_VERTEX_SOURCE}")
  message(FATAL_ERROR
    "BW_WGPU_DUMMY_VERTEX_SOURCE must name the extracted canonical policy")
endif()

foreach(_bw_source wgpu_state_manager.cc wgpu_state_manager.hh)
  set(_bw_source_path "${BW_INTEGRATED_BINDSPACE_SOURCE_DIR}/${_bw_source}")
  if(NOT EXISTS "${_bw_source_path}")
    message(FATAL_ERROR "integrated WebGPU bind-space input is missing: ${_bw_source_path}")
  endif()
endforeach()
foreach(_bw_source
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_state.cc"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_state_private.hh"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_texture_private.hh"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_state.hh"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_texture.hh")
  if(NOT EXISTS "${_bw_source}")
    message(FATAL_ERROR "integrated WebGPU bind-space dependency is missing: ${_bw_source}")
  endif()
endforeach()

set(_bw_integrated_bindspace_test
  "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-bindspace-integrated-smoke/integrated_bindspace_test.cc"
)
if(NOT EXISTS "${_bw_integrated_bindspace_test}")
  message(FATAL_ERROR
    "integrated WebGPU bind-space test is missing: ${_bw_integrated_bindspace_test}")
endif()

add_executable(wgpu_bindspace_integrated_smoke
  "${_bw_integrated_bindspace_test}"
  "${BW_INTEGRATED_BINDSPACE_SOURCE_DIR}/wgpu_state_manager.cc"
  "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_state.cc"
)
set_target_properties(wgpu_bindspace_integrated_smoke PROPERTIES
  CXX_STANDARD 20
  CXX_STANDARD_REQUIRED ON
  OUTPUT_NAME integrated_bindspace
  SUFFIX .js
)
target_compile_definitions(wgpu_bindspace_integrated_smoke PRIVATE
  GPU_STANDALONE
  BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE="${BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE}"
  BW_WGPU_DUMMY_VERTEX_SOURCE="${BW_WGPU_DUMMY_VERTEX_SOURCE}"
)
target_include_directories(wgpu_bindspace_integrated_smoke PRIVATE
  "${BW_INTEGRATED_BINDSPACE_SOURCE_DIR}"
  "${BW_UPSTREAM_DIR}/source/blender/blenkernel"
  "${BW_UPSTREAM_DIR}/source/blender/gpu"
  "${BW_UPSTREAM_DIR}/source/blender/gpu/intern"
  "${BW_UPSTREAM_DIR}/source/blender/blenlib"
  "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern"
  "${BW_UPSTREAM_DIR}/source/blender/makesdna"
  "${BW_UPSTREAM_DIR}/intern/ghost"
  "${BW_UPSTREAM_DIR}/intern/ghost/intern"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc"
  "${BW_WASM_INCLUDE_DIR}"
)
target_compile_options(wgpu_bindspace_integrated_smoke PRIVATE
  -pthread
  -fexceptions
  -ffunction-sections
  -fdata-sections
)
target_link_options(wgpu_bindspace_integrated_smoke PRIVATE
  -pthread
  -fexceptions
  -Wl,--gc-sections
  "-sENVIRONMENT=node"
  "-sEXIT_RUNTIME=1"
  "-sSTACK_SIZE=8388608"
  "-sINITIAL_MEMORY=67108864"
  "-sALLOW_MEMORY_GROWTH=1"
  "-sPTHREAD_POOL_SIZE=1"
)
