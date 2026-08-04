# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M3.T10.pre — standalone WebGPU state-table module + harness. Extends the
# dawn-probe baseline: same pinned Dawn checkout via add_subdirectory. Dawn-only.
#
# Pass -DDAWN_SRC_DIR=<pinned Dawn checkout>. See build.sh / README.md.

cmake_minimum_required(VERSION 3.16)
project(wgpu_state_tables CXX C)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED DAWN_SRC_DIR)
  message(FATAL_ERROR "Pass -DDAWN_SRC_DIR=/path/to/dawn (the pinned checkout)")
endif()

set(DAWN_FETCH_DEPENDENCIES ON  CACHE BOOL "" FORCE)
set(DAWN_ENABLE_METAL       ON  CACHE BOOL "" FORCE)
set(DAWN_BUILD_SAMPLES      OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_TESTS        OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_CMD_TOOLS    OFF CACHE BOOL "" FORCE)
set(DAWN_ENABLE_VULKAN      OFF CACHE BOOL "" FORCE)
set(DAWN_ENABLE_OPENGLES    OFF CACHE BOOL "" FORCE)
set(DAWN_ENABLE_DESKTOP_GL  OFF CACHE BOOL "" FORCE)
set(DAWN_USE_GLFW           OFF CACHE BOOL "" FORCE)
set(DAWN_BUILD_PROTOBUF     OFF CACHE BOOL "" FORCE)

add_subdirectory(${DAWN_SRC_DIR} ${CMAKE_BINARY_DIR}/dawn EXCLUDE_FROM_ALL)

add_library(wgpu_state_tables_mod STATIC wgpu_state_table.cc)
target_include_directories(wgpu_state_tables_mod PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(wgpu_state_tables_mod PUBLIC dawn::webgpu_dawn)

add_executable(wgpu_state_table_test tests/wgpu_state_table_test.cc)
target_link_libraries(wgpu_state_table_test PRIVATE wgpu_state_tables_mod)
