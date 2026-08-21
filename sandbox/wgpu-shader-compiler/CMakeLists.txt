# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M3.T7.pre — standalone WebGPU shader-compiler module + end-to-end harness.
# EXTENDS the sandbox/dawn-probe build baseline: consumes the SAME pinned Dawn
# checkout via add_subdirectory (minimal target set, EXCLUDE_FROM_ALL) and the
# SAME Dawn/Tint link libs, then adds:
#   - the module (wgpu_shader_compiler + wgpu_shader_interface_map)
#   - exact pinned libshaderc for the in-process GLSL->SPIR-V(1.3) step — the
#     same shaderc version the in-tree backend links.
#   - the end-to-end test driver.
#
# Pass the exact Dawn checkout, shaderc include directory, and shared library.
# See build.sh / README.md.

cmake_minimum_required(VERSION 3.16)
project(wgpu_shader_compiler CXX C)

# Dawn's webgpu_cpp.h + Tint headers require C++20 (see dawn-probe/CMakeLists.txt).
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED DAWN_SRC_DIR)
  message(FATAL_ERROR "Pass -DDAWN_SRC_DIR=/path/to/dawn (the pinned checkout)")
endif()
foreach(_shaderc_input SHADERC_INCLUDE_DIR SHADERC_LIBRARY)
  if(NOT DEFINED ${_shaderc_input})
    message(FATAL_ERROR "Pass -D${_shaderc_input}=<exact pinned path>")
  endif()
  if(NOT IS_ABSOLUTE "${${_shaderc_input}}" OR NOT EXISTS "${${_shaderc_input}}")
    message(FATAL_ERROR "${_shaderc_input} is missing or non-absolute: ${${_shaderc_input}}")
  endif()
endforeach()
if(NOT EXISTS "${SHADERC_INCLUDE_DIR}/shaderc/shaderc.hpp")
  message(FATAL_ERROR "shaderc.hpp not found under ${SHADERC_INCLUDE_DIR}")
endif()

# --- Dawn build options: identical to the dawn-probe baseline -----------------
set(DAWN_FETCH_DEPENDENCIES ON  CACHE BOOL "" FORCE)
set(TINT_BUILD_SPV_READER   ON  CACHE BOOL "" FORCE)
set(TINT_BUILD_WGSL_WRITER  ON  CACHE BOOL "" FORCE)
set(DAWN_BUILD_SAMPLES      OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_TESTS        OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_CMD_TOOLS    OFF CACHE BOOL "" FORCE)
if(APPLE)
  set(DAWN_ENABLE_METAL     ON  CACHE BOOL "" FORCE)
  set(DAWN_ENABLE_VULKAN    OFF CACHE BOOL "" FORCE)
elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  set(DAWN_ENABLE_METAL     OFF CACHE BOOL "" FORCE)
  set(DAWN_ENABLE_VULKAN    ON  CACHE BOOL "" FORCE)
else()
  message(FATAL_ERROR "wgpu_shader_compiler supports macOS/Metal or Linux/Vulkan only")
endif()
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
  ${SHADERC_INCLUDE_DIR}
)
target_link_libraries(wgpu_shader_compiler_mod PUBLIC ${_dawn_libs} ${SHADERC_LIBRARY})

# --- End-to-end harness -------------------------------------------------------
add_executable(wgpu_shader_compiler_test tests/wgpu_shader_compiler_test.cc)
target_include_directories(wgpu_shader_compiler_test PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/../dawn-probe
)
target_link_libraries(wgpu_shader_compiler_test PRIVATE wgpu_shader_compiler_mod)
get_filename_component(_shaderc_library_dir "${SHADERC_LIBRARY}" DIRECTORY)
set_target_properties(wgpu_shader_compiler_test PROPERTIES
  BUILD_RPATH "${_shaderc_library_dir}")

# Optional device-free contract for the canonical in-tree compiler module. The
# standalone T7.pre sources above remain an immutable design probe; this target
# compiles the evolved shipping postimage (cache + reflection included) without
# creating a Dawn device.
if(DEFINED BW_INTEGRATED_SOURCE_DIR)
  set(_bw_integrated_sources
    wgpu_shader_interface_map.cc
    wgpu_shader_interface_map.hh
    wgpu_shader_compiler.cc
    wgpu_shader_compiler.hh
    wgpu_shader_cache.cc
    wgpu_shader_cache.hh
  )
  foreach(_bw_source IN LISTS _bw_integrated_sources)
    set(_bw_source_path "${BW_INTEGRATED_SOURCE_DIR}/${_bw_source}")
    if(NOT IS_ABSOLUTE "${_bw_source_path}" OR NOT EXISTS "${_bw_source_path}")
      message(FATAL_ERROR
        "integrated WebGPU compiler input is missing or non-absolute: ${_bw_source_path}")
    endif()
  endforeach()

  add_executable(wgpu_shader_integrated_test
    tests/wgpu_shader_integrated_test.cc
    "${BW_INTEGRATED_SOURCE_DIR}/wgpu_shader_interface_map.cc"
    "${BW_INTEGRATED_SOURCE_DIR}/wgpu_shader_compiler.cc"
    "${BW_INTEGRATED_SOURCE_DIR}/wgpu_shader_cache.cc"
  )
  target_include_directories(wgpu_shader_integrated_test PRIVATE
    "${BW_INTEGRATED_SOURCE_DIR}"
    "${CMAKE_CURRENT_SOURCE_DIR}"
    "${DAWN_SRC_DIR}"
    "${SHADERC_INCLUDE_DIR}"
  )
  target_link_libraries(wgpu_shader_integrated_test PRIVATE
    ${_dawn_libs}
    "${SHADERC_LIBRARY}"
  )
  set_target_properties(wgpu_shader_integrated_test PROPERTIES
    BUILD_RPATH "${_shaderc_library_dir}")
endif()
