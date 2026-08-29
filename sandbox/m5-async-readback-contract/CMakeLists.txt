# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

cmake_minimum_required(VERSION 3.20)
project(m5_async_readback_contract LANGUAGES CXX)

if(NOT BW_UPSTREAM_DIR)
  message(FATAL_ERROR "BW_UPSTREAM_DIR is required")
endif()
if(NOT BW_FMT_INCLUDE_DIR)
  message(FATAL_ERROR "BW_FMT_INCLUDE_DIR is required")
endif()

add_executable(m5_async_readback_contract
  contract_test.cc
  "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_readback.cc"
  "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_select_next.cc"
)

target_compile_features(m5_async_readback_contract PRIVATE cxx_std_20)
target_compile_definitions(m5_async_readback_contract PRIVATE NDEBUG)
target_include_directories(m5_async_readback_contract PRIVATE
  "${BW_UPSTREAM_DIR}/source/blender/gpu"
  "${BW_UPSTREAM_DIR}/source/blender/gpu/intern"
  "${BW_UPSTREAM_DIR}/source/blender/blenlib"
  "${BW_UPSTREAM_DIR}/source/blender/makesdna"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc"
  "${CMAKE_CURRENT_LIST_DIR}/../../platform_web/ghost"
  "${BW_FMT_INCLUDE_DIR}"
)

if(EMSCRIPTEN)
  target_compile_options(m5_async_readback_contract PRIVATE -pthread)
  target_link_options(m5_async_readback_contract PRIVATE
    -pthread
    -sALLOW_MEMORY_GROWTH=1
    -sENVIRONMENT=node
    -sEXIT_RUNTIME=1
    -sSTACK_SIZE=262144
  )
  set_target_properties(m5_async_readback_contract PROPERTIES SUFFIX ".js")
endif()
