# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

cmake_minimum_required(VERSION 3.20)
project(m5_screenshot_readback_contract LANGUAGES CXX)

if(NOT BW_UPSTREAM_DIR)
  message(FATAL_ERROR "BW_UPSTREAM_DIR is required")
endif()

add_executable(m5_screenshot_readback_contract
  contract_test.cc
  "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_readback.cc"
)

target_compile_features(m5_screenshot_readback_contract PRIVATE cxx_std_20)
target_compile_definitions(m5_screenshot_readback_contract PRIVATE NDEBUG)
target_include_directories(m5_screenshot_readback_contract PRIVATE
  "${BW_UPSTREAM_DIR}/source/blender/gpu"
  "${BW_UPSTREAM_DIR}/source/blender/gpu/intern"
  "${BW_UPSTREAM_DIR}/intern/guardedalloc"
)

if(EMSCRIPTEN)
  target_compile_options(m5_screenshot_readback_contract PRIVATE -pthread)
  target_link_options(m5_screenshot_readback_contract PRIVATE
    -pthread
    -sALLOW_MEMORY_GROWTH=1
    -sENVIRONMENT=node
    -sEXIT_RUNTIME=1
  )
  set_target_properties(m5_screenshot_readback_contract PROPERTIES SUFFIX ".js")
endif()
