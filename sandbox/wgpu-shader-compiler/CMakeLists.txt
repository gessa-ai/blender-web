# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M3.T7.pre — standalone WebGPU shader-compiler module + end-to-end harness.
# EXTENDS the sandbox/dawn-probe build baseline: consumes the SAME pinned Dawn
# checkout via add_subdirectory (minimal target set, EXCLUDE_FROM_ALL) and the
# SAME Dawn/Tint link libs, then adds:
#   - the module (wgpu_shader_compiler + wgpu_shader_interface_map)
#   - libshaderc (Blender's OWN precompiled shaderc from lib/<platform>) for the
#     in-process GLSL->SPIR-V(1.3) step — the same lib the in-tree backend links.
#   - the end-to-end test driver.
#
# Pass -DDAWN_SRC_DIR=<pinned Dawn checkout> and (optionally) -DLIBDIR=<blender
# precompiled libs> (default: <repo>/lib/macos_arm64). See build.sh / README.md.

cmake_minimum_required(VERSION 3.16)
project(wgpu_shader_compiler CXX C)

# Dawn's webgpu_cpp.h + Tint headers require C++20 (see dawn-probe/CMakeLists.txt).
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED DAWN_SRC_DIR)
  message(FATAL_ERROR "Pass -DDAWN_SRC_DIR=/path/to/dawn (the pinned checkout)")
endif()
if(NOT DEFINED LIBDIR)
  set(LIBDIR "${CMAKE_CURRENT_SOURCE_DIR}/../../lib/macos_arm64")
endif()

set(SHADERC_DIR "${LIBDIR}/shaderc")
if(NOT EXISTS "${SHADERC_DIR}/include/shaderc/shaderc.hpp")
  message(FATAL_ERROR "shaderc headers not found at ${SHADERC_DIR}/include (set -DLIBDIR)")
endif()
# Blender ships several shaderc archives; the shared dylib keeps its bundled
# glslang/SPIRV-Tools symbols PRIVATE, so they cannot clash with Tint's static
# SPIRV-Tools on the same link line (a real T7 integration hazard — see notes).
find_library(SHADERC_LIB NAMES shaderc_shared PATHS "${SHADERC_DIR}/lib" NO_DEFAULT_PATH)
if(NOT SHADERC_LIB)
  message(FATAL_ERROR "libshaderc_shared not found in ${SHADERC_DIR}/lib")
endif()

# --- Dawn build options: identical to the dawn-probe baseline -----------------
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

set(_dawn_libs
  dawn::webgpu_dawn        # monolithic native device + wgpu* + C++ headers
  tint_lang_spirv_reader   # SPIR-V -> IR (not in the monolithic bundle)
  tint_lang_wgsl_writer    # IR -> WGSL
  tint_api
)

# --- The module (drop-in for source/blender/gpu/webgpu/) ----------------------
add_library(wgpu_shader_compiler_mod STATIC
  wgpu_shader_interface_map.cc
  wgpu_shader_compiler.cc
)
target_include_directories(wgpu_shader_compiler_mod PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}
  ${DAWN_SRC_DIR}                 # Tint "src/tint/..." headers
  ${SHADERC_DIR}/include
)
target_link_libraries(wgpu_shader_compiler_mod PUBLIC ${_dawn_libs} ${SHADERC_LIB})

# --- End-to-end harness -------------------------------------------------------
add_executable(wgpu_shader_compiler_test tests/wgpu_shader_compiler_test.cc)
target_link_libraries(wgpu_shader_compiler_test PRIVATE wgpu_shader_compiler_mod)
# libshaderc_shared's install name is @rpath/libshaderc_shared.1.dylib.
set_target_properties(wgpu_shader_compiler_test PROPERTIES
  BUILD_RPATH "${SHADERC_DIR}/lib")
