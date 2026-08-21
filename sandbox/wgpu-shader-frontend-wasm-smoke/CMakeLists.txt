# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

cmake_minimum_required(VERSION 3.16)
project(wgpu_shader_frontend_wasm_smoke CXX)

if(NOT EMSCRIPTEN)
  message(FATAL_ERROR "This project builds only the WebAssembly parity leg")
endif()
if(NOT DEFINED BW_INTEGRATED_SHADER_FRONTEND_SOURCE_DIR OR
   NOT IS_ABSOLUTE "${BW_INTEGRATED_SHADER_FRONTEND_SOURCE_DIR}" OR
   NOT IS_DIRECTORY "${BW_INTEGRATED_SHADER_FRONTEND_SOURCE_DIR}")
  message(FATAL_ERROR
    "BW_INTEGRATED_SHADER_FRONTEND_SOURCE_DIR must name the absolute canonical WebGPU source directory")
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
if(NOT DEFINED BW_WGPU_PUSH_CONSTANT_SET_SOURCE OR
   NOT IS_ABSOLUTE "${BW_WGPU_PUSH_CONSTANT_SET_SOURCE}" OR
   NOT EXISTS "${BW_WGPU_PUSH_CONSTANT_SET_SOURCE}")
  message(FATAL_ERROR
    "BW_WGPU_PUSH_CONSTANT_SET_SOURCE must name the extracted canonical method")
endif()

foreach(_bw_source wgpu_shader.cc wgpu_shader.hh wgpu_texture_format.hh)
  set(_bw_source_path "${BW_INTEGRATED_SHADER_FRONTEND_SOURCE_DIR}/${_bw_source}")
  if(NOT EXISTS "${_bw_source_path}")
    message(FATAL_ERROR
      "integrated WebGPU shader-frontend input is missing: ${_bw_source_path}")
  endif()
endforeach()

set(_bw_integrated_shader_frontend_test
  "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-shader-frontend-integrated-smoke/integrated_shader_frontend_test.cc"
)
if(NOT EXISTS "${_bw_integrated_shader_frontend_test}")
  message(FATAL_ERROR
    "integrated WebGPU shader-frontend test is missing: ${_bw_integrated_shader_frontend_test}")
endif()
set(_bw_shader_frontend_guardedalloc_sources
  "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/leak_detector.cc"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/mallocn.cc"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/mallocn_guarded_impl.cc"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/mallocn_lockfree_impl.cc"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/memory_usage.cc"
)
foreach(_bw_source
    "${BW_UPSTREAM_DIR}/intern/clog/clog.cc"
    ${_bw_shader_frontend_guardedalloc_sources})
  if(NOT EXISTS "${_bw_source}")
    message(FATAL_ERROR
      "integrated WebGPU shader-frontend runtime input is missing: ${_bw_source}")
  endif()
endforeach()

add_executable(wgpu_shader_frontend_integrated_smoke
  "${_bw_integrated_shader_frontend_test}"
  "${BW_UPSTREAM_DIR}/intern/clog/clog.cc"
  ${_bw_shader_frontend_guardedalloc_sources}
)
set_target_properties(wgpu_shader_frontend_integrated_smoke PROPERTIES
  CXX_STANDARD 20
  CXX_STANDARD_REQUIRED ON
  OUTPUT_NAME integrated_shader_frontend
  SUFFIX .js
)
target_compile_definitions(wgpu_shader_frontend_integrated_smoke PRIVATE
  BW_WGPU_SHADER_SOURCE="${BW_INTEGRATED_SHADER_FRONTEND_SOURCE_DIR}/wgpu_shader.cc"
  BW_WGPU_PUSH_CONSTANT_SET_SOURCE="${BW_WGPU_PUSH_CONSTANT_SET_SOURCE}"
  WITH_CLOG_PTHREADS
)
target_include_directories(wgpu_shader_frontend_integrated_smoke PRIVATE
  "${BW_INTEGRATED_SHADER_FRONTEND_SOURCE_DIR}"
  "${BW_UPSTREAM_DIR}/source/blender/gpu"
  "${BW_UPSTREAM_DIR}/source/blender/gpu/intern"
  "${BW_UPSTREAM_DIR}/source/blender/blenkernel"
  "${BW_UPSTREAM_DIR}/source/blender/blenlib"
  "${BW_UPSTREAM_DIR}/source/blender/makesdna"
  "${BW_UPSTREAM_DIR}/source/blender/makesrna"
  "${BW_UPSTREAM_DIR}/intern/atomic"
  "${BW_UPSTREAM_DIR}/intern/clog"
  "${BW_UPSTREAM_DIR}/intern/ghost"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern"
  "${BW_WASM_INCLUDE_DIR}"
)
target_compile_options(wgpu_shader_frontend_integrated_smoke PRIVATE
  -pthread
  -fexceptions
  -ffunction-sections
  -fdata-sections
  "--use-port=emdawnwebgpu"
)
target_link_options(wgpu_shader_frontend_integrated_smoke PRIVATE
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
