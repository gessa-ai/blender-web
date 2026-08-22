# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

cmake_minimum_required(VERSION 3.16)
project(wgpu_texture_wasm_smoke CXX)

if(NOT EMSCRIPTEN)
  message(FATAL_ERROR "This project builds only the WebAssembly parity leg")
endif()
if(NOT DEFINED BW_INTEGRATED_TEXTURE_SOURCE_DIR OR
   NOT IS_ABSOLUTE "${BW_INTEGRATED_TEXTURE_SOURCE_DIR}" OR
   NOT IS_DIRECTORY "${BW_INTEGRATED_TEXTURE_SOURCE_DIR}")
  message(FATAL_ERROR
    "BW_INTEGRATED_TEXTURE_SOURCE_DIR must name the absolute canonical WebGPU source directory")
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

set(_bw_integrated_texture_sources
  wgpu_texture_format.cc
  wgpu_texture_format.hh
  wgpu_texture_format_list.h
  wgpu_common.hh
  wgpu_data_conversion.cc
  wgpu_data_conversion.hh
)
foreach(_bw_source IN LISTS _bw_integrated_texture_sources)
  set(_bw_source_path "${BW_INTEGRATED_TEXTURE_SOURCE_DIR}/${_bw_source}")
  if(NOT EXISTS "${_bw_source_path}")
    message(FATAL_ERROR "integrated WebGPU texture input is missing: ${_bw_source_path}")
  endif()
endforeach()
foreach(_bw_source
    "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_format.hh"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_texture.hh"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern/BLI_assert.cc")
  if(NOT EXISTS "${_bw_source}")
    message(FATAL_ERROR "integrated WebGPU texture dependency is missing: ${_bw_source}")
  endif()
endforeach()

set(_bw_integrated_texture_test
  "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-texture-integrated-smoke/integrated_texture_test.cc"
)
if(NOT EXISTS "${_bw_integrated_texture_test}")
  message(FATAL_ERROR "integrated WebGPU texture test is missing: ${_bw_integrated_texture_test}")
endif()

add_executable(wgpu_texture_integrated_smoke
  "${_bw_integrated_texture_test}"
  "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern/BLI_assert.cc"
  "${BW_INTEGRATED_TEXTURE_SOURCE_DIR}/wgpu_texture_format.cc"
  "${BW_INTEGRATED_TEXTURE_SOURCE_DIR}/wgpu_data_conversion.cc"
)
set_target_properties(wgpu_texture_integrated_smoke PROPERTIES
  CXX_STANDARD 20
  CXX_STANDARD_REQUIRED ON
  OUTPUT_NAME integrated_texture
  SUFFIX .js
)
target_include_directories(wgpu_texture_integrated_smoke PRIVATE
  "${BW_INTEGRATED_TEXTURE_SOURCE_DIR}"
  "${BW_UPSTREAM_DIR}/source/blender/gpu"
  "${BW_UPSTREAM_DIR}/source/blender/blenlib"
  "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc"
  "${BW_WASM_INCLUDE_DIR}"
)
target_compile_options(wgpu_texture_integrated_smoke PRIVATE
  -pthread
  -fexceptions
  "--use-port=emdawnwebgpu"
)
target_link_options(wgpu_texture_integrated_smoke PRIVATE
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
