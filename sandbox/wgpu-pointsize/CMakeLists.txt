# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M3.pointsize.pre — gl_PointSize → instanced-quad expansion prototype. Extends the
# dawn-probe baseline AND reuses the T7.pre shader-compiler chain
# (sandbox/wgpu-shader-compiler/), so the rewrite is proven to compile GLSL→WGSL
# through the same shaderc→Tint path it will use in-tree, then render on Dawn.
#
# Pass -DDAWN_SRC_DIR=<pinned Dawn checkout> and optionally -DLIBDIR=<blender libs>.

cmake_minimum_required(VERSION 3.16)
project(wgpu_pointsize CXX C)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED DAWN_SRC_DIR)
  message(FATAL_ERROR "Pass -DDAWN_SRC_DIR=/path/to/dawn (the pinned checkout)")
endif()
if(NOT DEFINED LIBDIR)
  set(LIBDIR "${CMAKE_CURRENT_SOURCE_DIR}/../../lib/macos_arm64")
endif()
set(SHADERC_DIR "${LIBDIR}/shaderc")
find_library(SHADERC_LIB NAMES shaderc_shared PATHS "${SHADERC_DIR}/lib" NO_DEFAULT_PATH)
if(NOT SHADERC_LIB)
  message(FATAL_ERROR "libshaderc_shared not found in ${SHADERC_DIR}/lib (set -DLIBDIR)")
endif()

set(T7_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-shader-compiler")

set(DAWN_FETCH_DEPENDENCIES ON  CACHE BOOL "" FORCE)
set(TINT_BUILD_SPV_READER   ON  CACHE BOOL "" FORCE)
set(TINT_BUILD_WGSL_WRITER  ON  CACHE BOOL "" FORCE)
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

set(_dawn_libs dawn::webgpu_dawn tint_lang_spirv_reader tint_lang_wgsl_writer tint_api)

add_library(wgpu_pointsize_mod STATIC
  wgpu_pointsize_expand.cc
  ${T7_DIR}/wgpu_shader_interface_map.cc
  ${T7_DIR}/wgpu_shader_compiler.cc
)
target_include_directories(wgpu_pointsize_mod PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR} ${T7_DIR} ${DAWN_SRC_DIR} ${SHADERC_DIR}/include)
target_link_libraries(wgpu_pointsize_mod PUBLIC ${_dawn_libs} ${SHADERC_LIB})

add_executable(wgpu_pointsize_test tests/wgpu_pointsize_test.cc)
target_link_libraries(wgpu_pointsize_test PRIVATE wgpu_pointsize_mod)
set_target_properties(wgpu_pointsize_test PROPERTIES BUILD_RPATH "${SHADERC_DIR}/lib")
