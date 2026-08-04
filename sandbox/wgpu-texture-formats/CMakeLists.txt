# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M3.T9.pre — standalone WebGPU texture-format + data-conversion module + harness.
# EXTENDS the sandbox/dawn-probe build baseline: consumes the SAME pinned Dawn
# checkout via add_subdirectory (minimal target set, EXCLUDE_FROM_ALL). Unlike the
# shader-compiler module this needs neither shaderc nor Tint — only the WebGPU
# device (dawn::webgpu_dawn).
#
# Pass -DDAWN_SRC_DIR=<pinned Dawn checkout>. See build.sh / README.md.

cmake_minimum_required(VERSION 3.16)
project(wgpu_texture_format CXX C)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED DAWN_SRC_DIR)
  message(FATAL_ERROR "Pass -DDAWN_SRC_DIR=/path/to/dawn (the pinned checkout)")
endif()

# --- Dawn build options: identical to the dawn-probe baseline -----------------
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

# --- The module (drop-in for source/blender/gpu/webgpu/) ----------------------
add_library(wgpu_texture_format_mod STATIC
  wgpu_texture_format.cc
  wgpu_data_conversion.cc
)
target_include_directories(wgpu_texture_format_mod PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(wgpu_texture_format_mod PUBLIC dawn::webgpu_dawn)

# --- Live harness -------------------------------------------------------------
add_executable(wgpu_texture_format_test tests/wgpu_texture_format_test.cc)
target_link_libraries(wgpu_texture_format_test PRIVATE wgpu_texture_format_mod)
