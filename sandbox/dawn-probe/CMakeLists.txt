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

# --- Dawn build options: the M3.T1 flag set + a lean host link surface --------
set(DAWN_FETCH_DEPENDENCIES ON  CACHE BOOL "" FORCE)  # python dep fetcher, no depot_tools
set(TINT_BUILD_SPV_READER   ON  CACHE BOOL "" FORCE)  # SPIR-V -> IR  (the chain)
set(TINT_BUILD_WGSL_WRITER  ON  CACHE BOOL "" FORCE)  # IR -> WGSL    (the chain)
set(DAWN_BUILD_SAMPLES      OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_TESTS        OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_CMD_TOOLS    ON  CACHE BOOL "" FORCE)  # bonus: the `tint` CLI

# Keep the backend/link surface minimal on this host. Metal is the established
# macOS probe backend; Linux replays the same probe through Vulkan.
if(APPLE)
  set(DAWN_ENABLE_METAL     ON  CACHE BOOL "" FORCE)
  set(DAWN_ENABLE_VULKAN    OFF CACHE BOOL "" FORCE)
elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  set(DAWN_ENABLE_METAL     OFF CACHE BOOL "" FORCE)
  set(DAWN_ENABLE_VULKAN    ON  CACHE BOOL "" FORCE)
else()
  message(FATAL_ERROR "dawn_probe supports the M3 Metal or Linux Vulkan host only")
endif()

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

# Optional device-free native halves of the cross-compiled shader-chain parity
# smokes. Keeping them in this project reuses Dawn's exact generated Tint target
# graph instead of rediscovering or manually ordering native archives.
function(bw_add_shader_smoke target source)
  foreach(_required_path "${source}" "${BW_SHADERC_INCLUDE_DIR}" "${BW_SHADERC_LIBRARY}")
    if(NOT IS_ABSOLUTE "${_required_path}")
      message(FATAL_ERROR "shader-smoke input must be an absolute path: ${_required_path}")
    endif()
    if(NOT EXISTS "${_required_path}")
      message(FATAL_ERROR "shader-smoke input does not exist: ${_required_path}")
    endif()
  endforeach()

  add_executable(${target} "${source}")
  target_include_directories(${target} PRIVATE
    "${DAWN_SRC_DIR}"
    "${BW_SHADERC_INCLUDE_DIR}"
  )
  target_link_libraries(${target} PRIVATE
    tint_lang_spirv_reader
    tint_lang_wgsl_writer
    tint_api
    "${BW_SHADERC_LIBRARY}"
  )
  get_filename_component(_bw_shaderc_library_dir "${BW_SHADERC_LIBRARY}" DIRECTORY)
  set_target_properties(${target} PROPERTIES
    BUILD_RPATH "${_bw_shaderc_library_dir}"
  )
endfunction()

if(DEFINED BW_SHADER_CHAIN_SMOKE_SOURCE)
  bw_add_shader_smoke(wgpu_shader_chain_smoke_native "${BW_SHADER_CHAIN_SMOKE_SOURCE}")
endif()
if(DEFINED BW_SHADER_BINDMAP_SMOKE_SOURCE)
  bw_add_shader_smoke(wgpu_shader_bindmap_smoke_native "${BW_SHADER_BINDMAP_SMOKE_SOURCE}")
endif()

# T3 native GHOST-context verification. The driver requires patch 0149's
# integrated postimage and stages the exact current Blender source outside
# upstream/, then supplies that directory here. Building it inside Dawn's target
# graph preserves the platform-specific Vulkan/Metal/system link closure without
# a handwritten library list.
if(DEFINED BW_GHOST_WGPU_SOURCE_DIR)
  if(NOT DEFINED BW_UPSTREAM_DIR)
    message(FATAL_ERROR "BW_UPSTREAM_DIR is required with BW_GHOST_WGPU_SOURCE_DIR")
  endif()
  foreach(_required_path
      "${BW_GHOST_WGPU_SOURCE_DIR}/GHOST_ContextWGPU.cc"
      "${BW_GHOST_WGPU_SOURCE_DIR}/GHOST_ContextWGPU.hh"
      "${BW_UPSTREAM_DIR}/intern/ghost/intern/GHOST_Context.hh"
      "${CMAKE_CURRENT_SOURCE_DIR}/ghost-wgpu/verify_main.cc")
    if(NOT IS_ABSOLUTE "${_required_path}" OR NOT EXISTS "${_required_path}")
      message(FATAL_ERROR "T3 GHOST verify input is missing or non-absolute: ${_required_path}")
    endif()
  endforeach()

  file(GLOB _bw_guardedalloc_sources
    "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/*.cc"
  )
  add_executable(ghost_wgpu_verify
    "${BW_GHOST_WGPU_SOURCE_DIR}/GHOST_ContextWGPU.cc"
    "${CMAKE_CURRENT_SOURCE_DIR}/ghost-wgpu/verify_main.cc"
    ${_bw_guardedalloc_sources}
  )
  target_compile_definitions(ghost_wgpu_verify PRIVATE WITH_WEBGPU_BACKEND)
  target_include_directories(ghost_wgpu_verify PRIVATE
    "${BW_GHOST_WGPU_SOURCE_DIR}"
    "${BW_UPSTREAM_DIR}/intern/ghost/intern"
    "${BW_UPSTREAM_DIR}/intern/ghost"
    "${BW_UPSTREAM_DIR}/intern/guardedalloc"
    "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern"
    "${BW_UPSTREAM_DIR}/intern/atomic"
    "${CMAKE_CURRENT_SOURCE_DIR}"
  )
  target_link_libraries(ghost_wgpu_verify PRIVATE dawn::webgpu_dawn)
endif()

# Optional device-free contract for the canonical in-tree buffer wrapper and
# readback registry. This compiles the shipping postimages directly and reuses
# Dawn's native target graph, but deliberately never creates an instance,
# adapter, or device at runtime.
if(DEFINED BW_INTEGRATED_BUFFER_SOURCE_DIR)
  set(_bw_integrated_buffer_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-buffer-integrated-smoke/integrated_buffer_test.cc"
  )
  set(_bw_integrated_buffer_sources
    wgpu_buffer.cc
    wgpu_buffer.hh
    wgpu_common.hh
    wgpu_readback.cc
    wgpu_readback.hh
  )
  foreach(_bw_source IN LISTS _bw_integrated_buffer_sources)
    set(_bw_source_path "${BW_INTEGRATED_BUFFER_SOURCE_DIR}/${_bw_source}")
    if(NOT IS_ABSOLUTE "${_bw_source_path}" OR NOT EXISTS "${_bw_source_path}")
      message(FATAL_ERROR
        "integrated WebGPU buffer input is missing or non-absolute: ${_bw_source_path}")
    endif()
  endforeach()
  if(NOT IS_ABSOLUTE "${_bw_integrated_buffer_test}" OR
     NOT EXISTS "${_bw_integrated_buffer_test}")
    message(FATAL_ERROR
      "integrated WebGPU buffer test is missing: ${_bw_integrated_buffer_test}")
  endif()

  find_package(Threads REQUIRED)
  add_executable(wgpu_buffer_integrated_test
    "${_bw_integrated_buffer_test}"
    "${BW_INTEGRATED_BUFFER_SOURCE_DIR}/wgpu_buffer.cc"
    "${BW_INTEGRATED_BUFFER_SOURCE_DIR}/wgpu_readback.cc"
  )
  target_include_directories(wgpu_buffer_integrated_test PRIVATE
    "${BW_INTEGRATED_BUFFER_SOURCE_DIR}"
  )
  target_link_libraries(wgpu_buffer_integrated_test PRIVATE
    dawn::webgpu_dawn
    Threads::Threads
  )
endif()
