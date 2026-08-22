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
if(NOT DEFINED BW_WGPU_INDEX_STRIP_SOURCE OR
   NOT IS_ABSOLUTE "${BW_WGPU_INDEX_STRIP_SOURCE}" OR
   NOT EXISTS "${BW_WGPU_INDEX_STRIP_SOURCE}")
  message(FATAL_ERROR
    "BW_WGPU_INDEX_STRIP_SOURCE must name the extracted canonical method")
endif()

set(_bw_integrated_buffer_sources
  wgpu_buffer.cc
  wgpu_buffer.hh
  wgpu_common.hh
  wgpu_pixel_buffer.cc
  wgpu_pixel_buffer.hh
  wgpu_readback.cc
  wgpu_readback.hh
  wgpu_index_buffer.cc
  wgpu_index_buffer.hh
)
foreach(_bw_source IN LISTS _bw_integrated_buffer_sources)
  set(_bw_source_path "${BW_INTEGRATED_BUFFER_SOURCE_DIR}/${_bw_source}")
  if(NOT EXISTS "${_bw_source_path}")
    message(FATAL_ERROR "integrated WebGPU buffer input is missing: ${_bw_source_path}")
  endif()
endforeach()
foreach(_bw_source
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_texture_private.hh"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_index_buffer.cc"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_index_buffer.hh"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_texture.hh"
    "${BW_UPSTREAM_DIR}/intern/guardedalloc/MEM_guardedalloc.h")
  if(NOT EXISTS "${_bw_source}")
    message(FATAL_ERROR "integrated WebGPU pixel-buffer dependency is missing: ${_bw_source}")
  endif()
endforeach()
set(_bw_buffer_guardedalloc_sources
  "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/leak_detector.cc"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/mallocn.cc"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/mallocn_guarded_impl.cc"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/mallocn_lockfree_impl.cc"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/memory_usage.cc"
)
foreach(_bw_source IN LISTS _bw_buffer_guardedalloc_sources)
  if(NOT EXISTS "${_bw_source}")
    message(FATAL_ERROR
      "integrated WebGPU pixel-buffer allocator input is missing: ${_bw_source}")
  endif()
endforeach()

set(_bw_integrated_buffer_test
  "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-buffer-integrated-smoke/integrated_buffer_test.cc"
)
set(_bw_integrated_index_test
  "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-buffer-integrated-smoke/integrated_index_test.cc"
)
foreach(_bw_test "${_bw_integrated_buffer_test}" "${_bw_integrated_index_test}")
  if(NOT EXISTS "${_bw_test}")
    message(FATAL_ERROR "integrated WebGPU buffer test is missing: ${_bw_test}")
  endif()
endforeach()

add_executable(wgpu_buffer_integrated_smoke
  "${_bw_integrated_buffer_test}"
  "${_bw_integrated_index_test}"
  "${BW_INTEGRATED_BUFFER_SOURCE_DIR}/wgpu_buffer.cc"
  "${BW_INTEGRATED_BUFFER_SOURCE_DIR}/wgpu_pixel_buffer.cc"
  "${BW_INTEGRATED_BUFFER_SOURCE_DIR}/wgpu_readback.cc"
  "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_index_buffer.cc"
  ${_bw_buffer_guardedalloc_sources}
)
set_target_properties(wgpu_buffer_integrated_smoke PROPERTIES
  CXX_STANDARD 20
  CXX_STANDARD_REQUIRED ON
  OUTPUT_NAME integrated_buffer
  SUFFIX .js
)
target_compile_definitions(wgpu_buffer_integrated_smoke PRIVATE
  BW_WGPU_INDEX_STRIP_SOURCE="${BW_WGPU_INDEX_STRIP_SOURCE}"
)
target_include_directories(wgpu_buffer_integrated_smoke PRIVATE
  "${BW_INTEGRATED_BUFFER_SOURCE_DIR}"
  "${BW_UPSTREAM_DIR}/source/blender/gpu/intern"
  "${BW_UPSTREAM_DIR}/source/blender/gpu"
  "${BW_UPSTREAM_DIR}/source/blender/blenkernel"
  "${BW_UPSTREAM_DIR}/source/blender/blenlib"
  "${BW_UPSTREAM_DIR}/source/blender/makesdna"
  "${BW_UPSTREAM_DIR}/source/blender/makesrna"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern"
  "${BW_UPSTREAM_DIR}/intern/atomic"
  "${BW_UPSTREAM_DIR}/intern/clog"
  "${BW_UPSTREAM_DIR}/intern/ghost"
  "${BW_UPSTREAM_DIR}/intern/profile"
  "${BW_WASM_INCLUDE_DIR}"
)
target_compile_options(wgpu_buffer_integrated_smoke PRIVATE
  -pthread
  -fexceptions
  -ffunction-sections
  -fdata-sections
  "--use-port=emdawnwebgpu"
)
target_link_options(wgpu_buffer_integrated_smoke PRIVATE
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
