# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M3.T1 Dawn+Tint native probe. Consumes the Dawn checkout via add_subdirectory
# so all include dirs / transitive static libs come from Dawn's own CMake target
# graph. EXCLUDE_FROM_ALL means ninja only builds the Dawn/Tint subset the probe
# actually links against (the "minimal target set").
#
# Pass -DDAWN_SRC_DIR=<path to the pinned Dawn checkout> (see README.md).

cmake_minimum_required(VERSION 3.16)
project(dawn_probe CXX C)

# Dawn's generated webgpu_cpp.h and the Tint headers (src/tint/...) require
# C++20 (std::span / std::type_identity / std::to_array / concepts). Compiling
# the probe at C++17 fails inside those headers, so match Dawn's own standard.
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED DAWN_SRC_DIR)
  message(FATAL_ERROR "Pass -DDAWN_SRC_DIR=/path/to/dawn (the pinned checkout)")
endif()

# --- Dawn build options: the M3.T1 flag set + a lean macOS link surface -------
set(DAWN_FETCH_DEPENDENCIES ON  CACHE BOOL "" FORCE)  # python dep fetcher, no depot_tools
set(TINT_BUILD_SPV_READER   ON  CACHE BOOL "" FORCE)  # SPIR-V -> IR  (the chain)
set(TINT_BUILD_WGSL_WRITER  ON  CACHE BOOL "" FORCE)  # IR -> WGSL    (the chain)
set(DAWN_ENABLE_METAL       ON  CACHE BOOL "" FORCE)
set(DAWN_BUILD_SAMPLES      OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_TESTS        OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_CMD_TOOLS    ON  CACHE BOOL "" FORCE)  # bonus: the `tint` CLI

# Keep the backend/link surface minimal on this host.
set(DAWN_ENABLE_VULKAN      OFF CACHE BOOL "" FORCE)
set(DAWN_ENABLE_OPENGLES    OFF CACHE BOOL "" FORCE)
set(DAWN_ENABLE_DESKTOP_GL  OFF CACHE BOOL "" FORCE)
set(DAWN_USE_GLFW           OFF CACHE BOOL "" FORCE)  # headless: no windowing
set(DAWN_BUILD_PROTOBUF     OFF CACHE BOOL "" FORCE)

add_subdirectory(${DAWN_SRC_DIR} ${CMAKE_BINARY_DIR}/dawn EXCLUDE_FROM_ALL)

set(_dawn_probe_libs
  # Dawn native device + wgpu* impl + C++ headers (the documented external target).
  dawn::webgpu_dawn
  # Tint shader chain. The monolithic bundle does NOT include the SPIR-V reader
  # (Dawn never consumes SPIR-V), so it is linked explicitly here; the writer/api
  # libs are separate static archives and resolve lazily without duplication.
  tint_lang_spirv_reader
  tint_lang_wgsl_writer
  tint_api
)

# T1 probe (shader-chain smoke).
add_executable(dawn_probe probe.cc)
target_include_directories(dawn_probe PRIVATE ${DAWN_SRC_DIR})  # Tint "src/tint/..." headers
target_link_libraries(dawn_probe PRIVATE ${_dawn_probe_libs})

# T2 probe (combined-sampler binding audit + render-pipeline composition).
add_executable(dawn_bindmap_probe probe_bindmap.cc)
target_include_directories(dawn_bindmap_probe PRIVATE ${DAWN_SRC_DIR})
target_link_libraries(dawn_bindmap_probe PRIVATE ${_dawn_probe_libs})
