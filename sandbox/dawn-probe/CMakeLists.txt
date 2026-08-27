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

# Audit-only control: prove the native Dawn API's synchronous return-value
# semantics for validation failures. This target intentionally accepts a
# software Vulkan adapter and therefore cannot bind any M3/M4 receipt.
add_executable(dawn_error_handle_probe probe_error_handles.cc)
target_include_directories(dawn_error_handle_probe PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/../../platform_web/ghost
  ${BW_INTEGRATED_BUFFER_SOURCE_DIR}
  ${CMAKE_CURRENT_SOURCE_DIR}/../../upstream/source/blender/gpu/webgpu
)
target_link_libraries(dawn_error_handle_probe PRIVATE dawn::webgpu_dawn)

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

# T3 native GHOST-context verification. The driver requires patches 0149 and
# 0167's integrated postimage and stages the exact current Blender source outside
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

  if(NOT DEFINED BW_GHOST_WGPU_FEATURE_SOURCE_DIR OR
     NOT IS_ABSOLUTE "${BW_GHOST_WGPU_FEATURE_SOURCE_DIR}" OR
     NOT EXISTS "${BW_GHOST_WGPU_FEATURE_SOURCE_DIR}/ghost_wgpu_optional_features.inc")
    message(FATAL_ERROR
      "BW_GHOST_WGPU_FEATURE_SOURCE_DIR must name the extracted optional-feature contract")
  endif()
  add_executable(ghost_wgpu_feature_contract
    "${CMAKE_CURRENT_SOURCE_DIR}/ghost-wgpu/feature_contract_test.cc"
  )
  target_include_directories(ghost_wgpu_feature_contract PRIVATE
    "${BW_GHOST_WGPU_FEATURE_SOURCE_DIR}"
  )
endif()

# Optional device-free contract for the canonical in-tree buffer wrapper,
# pixel-upload buffer, and readback registry. This compiles the shipping
# postimages directly and reuses Dawn's native target graph, but deliberately
# never creates an instance, adapter, or device at runtime.
if(DEFINED BW_INTEGRATED_BUFFER_SOURCE_DIR)
  if(NOT DEFINED BW_UPSTREAM_DIR)
    message(FATAL_ERROR "BW_UPSTREAM_DIR is required with BW_INTEGRATED_BUFFER_SOURCE_DIR")
  endif()
  if(NOT DEFINED BW_WGPU_INDEX_STRIP_SOURCE OR
     NOT IS_ABSOLUTE "${BW_WGPU_INDEX_STRIP_SOURCE}" OR
     NOT EXISTS "${BW_WGPU_INDEX_STRIP_SOURCE}")
    message(FATAL_ERROR
      "BW_WGPU_INDEX_STRIP_SOURCE must name the extracted canonical method")
  endif()
  if(NOT DEFINED BW_WGPU_INDEX_UPLOAD_SOURCE OR
     NOT IS_ABSOLUTE "${BW_WGPU_INDEX_UPLOAD_SOURCE}" OR
     NOT EXISTS "${BW_WGPU_INDEX_UPLOAD_SOURCE}")
    message(FATAL_ERROR
      "BW_WGPU_INDEX_UPLOAD_SOURCE must name the extracted canonical method")
  endif()
  if(NOT DEFINED BW_WGPU_BUFFER_UPDATE_SOURCE OR
     NOT IS_ABSOLUTE "${BW_WGPU_BUFFER_UPDATE_SOURCE}" OR
     NOT EXISTS "${BW_WGPU_BUFFER_UPDATE_SOURCE}")
    message(FATAL_ERROR
      "BW_WGPU_BUFFER_UPDATE_SOURCE must name the extracted canonical method")
  endif()
  if(NOT DEFINED BW_WGPU_BUFFER_CREATE_SOURCE OR
     NOT IS_ABSOLUTE "${BW_WGPU_BUFFER_CREATE_SOURCE}" OR
     NOT EXISTS "${BW_WGPU_BUFFER_CREATE_SOURCE}")
    message(FATAL_ERROR
      "BW_WGPU_BUFFER_CREATE_SOURCE must name the extracted canonical method")
  endif()
  if(NOT DEFINED BW_WGPU_PENDING_PAYLOAD_FRONTEND_SOURCE OR
     NOT IS_ABSOLUTE "${BW_WGPU_PENDING_PAYLOAD_FRONTEND_SOURCE}" OR
     NOT EXISTS "${BW_WGPU_PENDING_PAYLOAD_FRONTEND_SOURCE}")
    message(FATAL_ERROR
      "BW_WGPU_PENDING_PAYLOAD_FRONTEND_SOURCE must name the extracted canonical methods")
  endif()
  if(NOT DEFINED BW_WGPU_VERTEX_UPLOAD_FRONTEND_SOURCE OR
     NOT IS_ABSOLUTE "${BW_WGPU_VERTEX_UPLOAD_FRONTEND_SOURCE}" OR
     NOT EXISTS "${BW_WGPU_VERTEX_UPLOAD_FRONTEND_SOURCE}")
    message(FATAL_ERROR
      "BW_WGPU_VERTEX_UPLOAD_FRONTEND_SOURCE must name the extracted canonical methods")
  endif()
  if(NOT DEFINED BW_NATIVE_FMT_INCLUDE_DIR OR
     NOT IS_ABSOLUTE "${BW_NATIVE_FMT_INCLUDE_DIR}" OR
     NOT EXISTS "${BW_NATIVE_FMT_INCLUDE_DIR}/fmt/ranges.h")
    message(FATAL_ERROR
      "BW_NATIVE_FMT_INCLUDE_DIR must name the pinned native fmt include root")
  endif()
  set(_bw_integrated_buffer_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-buffer-integrated-smoke/integrated_buffer_test.cc"
  )
  set(_bw_integrated_index_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-buffer-integrated-smoke/integrated_index_test.cc"
  )
  set(_bw_integrated_buffer_update_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-buffer-integrated-smoke/integrated_buffer_update_test.cc"
  )
  set(_bw_integrated_buffer_create_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-buffer-integrated-smoke/integrated_buffer_create_test.cc"
  )
  set(_bw_integrated_vertex_upload_generation_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-buffer-integrated-smoke/integrated_vertex_upload_generation_test.cc"
  )
  set(_bw_integrated_buffer_sources
    wgpu_buffer.cc
    wgpu_buffer.hh
    wgpu_common.hh
    wgpu_pixel_buffer.cc
    wgpu_pixel_buffer.hh
    wgpu_readback.cc
    wgpu_readback.hh
    wgpu_index_buffer.cc
    wgpu_index_buffer.hh
  )
  foreach(_bw_source IN LISTS _bw_integrated_buffer_sources)
    set(_bw_source_path "${BW_INTEGRATED_BUFFER_SOURCE_DIR}/${_bw_source}")
    if(NOT IS_ABSOLUTE "${_bw_source_path}" OR NOT EXISTS "${_bw_source_path}")
      message(FATAL_ERROR
        "integrated WebGPU buffer input is missing or non-absolute: ${_bw_source_path}")
    endif()
  endforeach()
  foreach(_bw_source
      "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_texture_private.hh"
      "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_index_buffer.cc"
      "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_index_buffer.hh"
      "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_texture.hh"
      "${BW_UPSTREAM_DIR}/intern/guardedalloc/MEM_guardedalloc.h"
      "${_bw_integrated_index_test}"
      "${_bw_integrated_buffer_create_test}"
      "${_bw_integrated_vertex_upload_generation_test}"
      "${_bw_integrated_buffer_update_test}")
    if(NOT IS_ABSOLUTE "${_bw_source}" OR NOT EXISTS "${_bw_source}")
      message(FATAL_ERROR
        "integrated WebGPU buffer dependency is missing: ${_bw_source}")
    endif()
  endforeach()
  set(_bw_buffer_guardedalloc_sources
    "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/leak_detector.cc"
    "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/mallocn.cc"
    "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/mallocn_guarded_impl.cc"
    "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/mallocn_lockfree_impl.cc"
    "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern/memory_usage.cc"
  )
  foreach(_bw_source IN LISTS _bw_buffer_guardedalloc_sources)
    if(NOT IS_ABSOLUTE "${_bw_source}" OR NOT EXISTS "${_bw_source}")
      message(FATAL_ERROR
        "integrated WebGPU pixel-buffer allocator input is missing: ${_bw_source}")
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
    "${_bw_integrated_index_test}"
    "${_bw_integrated_buffer_create_test}"
    "${_bw_integrated_vertex_upload_generation_test}"
    "${_bw_integrated_buffer_update_test}"
    "${BW_INTEGRATED_BUFFER_SOURCE_DIR}/wgpu_buffer.cc"
    "${BW_INTEGRATED_BUFFER_SOURCE_DIR}/wgpu_pixel_buffer.cc"
    "${BW_INTEGRATED_BUFFER_SOURCE_DIR}/wgpu_readback.cc"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_index_buffer.cc"
    ${_bw_buffer_guardedalloc_sources}
  )
  target_compile_definitions(wgpu_buffer_integrated_test PRIVATE
    BW_WGPU_INDEX_STRIP_SOURCE="${BW_WGPU_INDEX_STRIP_SOURCE}"
    BW_WGPU_INDEX_UPLOAD_SOURCE="${BW_WGPU_INDEX_UPLOAD_SOURCE}"
    BW_WGPU_BUFFER_CREATE_SOURCE="${BW_WGPU_BUFFER_CREATE_SOURCE}"
    BW_WGPU_BUFFER_UPDATE_SOURCE="${BW_WGPU_BUFFER_UPDATE_SOURCE}"
    BW_WGPU_PENDING_PAYLOAD_FRONTEND_SOURCE="${BW_WGPU_PENDING_PAYLOAD_FRONTEND_SOURCE}"
    BW_WGPU_VERTEX_UPLOAD_FRONTEND_SOURCE="${BW_WGPU_VERTEX_UPLOAD_FRONTEND_SOURCE}"
  )
  target_include_directories(wgpu_buffer_integrated_test PRIVATE
    "${BW_INTEGRATED_BUFFER_SOURCE_DIR}"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern"
    "${BW_UPSTREAM_DIR}/source/blender/gpu"
    "${BW_UPSTREAM_DIR}/source/blender/blenkernel"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib"
    "${BW_UPSTREAM_DIR}/source/blender/makesdna"
    "${BW_UPSTREAM_DIR}/source/blender/makesrna"
    "${BW_UPSTREAM_DIR}/intern/guardedalloc"
    "${BW_UPSTREAM_DIR}/intern/guardedalloc/intern"
    "${BW_UPSTREAM_DIR}/intern/atomic"
    "${BW_UPSTREAM_DIR}/intern/clog"
    "${BW_UPSTREAM_DIR}/intern/ghost"
    "${BW_UPSTREAM_DIR}/intern/profile"
    "${BW_NATIVE_FMT_INCLUDE_DIR}"
  )
  target_compile_options(wgpu_buffer_integrated_test PRIVATE
    -ffunction-sections
    -fdata-sections
  )
  target_link_options(wgpu_buffer_integrated_test PRIVATE -Wl,--gc-sections)
  target_link_libraries(wgpu_buffer_integrated_test PRIVATE
    dawn::webgpu_dawn
    Threads::Threads
  )
endif()

# Optional device-free contract for the canonical in-tree texture-format table
# and RGB-to-RGBA conversion module. This compiles the shipping postimages
# directly, including Blender's real TextureFormat enum, but deliberately never
# creates a WebGPU instance, adapter, device, or texture at runtime.
if(DEFINED BW_INTEGRATED_TEXTURE_SOURCE_DIR)
  if(NOT DEFINED BW_UPSTREAM_DIR)
    message(FATAL_ERROR "BW_UPSTREAM_DIR is required with BW_INTEGRATED_TEXTURE_SOURCE_DIR")
  endif()
  if(NOT DEFINED BW_NATIVE_FMT_INCLUDE_DIR OR
     NOT IS_ABSOLUTE "${BW_NATIVE_FMT_INCLUDE_DIR}" OR
     NOT EXISTS "${BW_NATIVE_FMT_INCLUDE_DIR}/fmt/ranges.h")
    message(FATAL_ERROR
      "BW_NATIVE_FMT_INCLUDE_DIR must name the pinned native fmt include root")
  endif()
  set(_bw_integrated_texture_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-texture-integrated-smoke/integrated_texture_test.cc"
  )
  set(_bw_integrated_mipmap_transaction_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-texture-integrated-smoke/integrated_mipmap_transaction_test.cc"
  )
  if(NOT DEFINED BW_WGPU_MIPMAP_SOURCE OR
     NOT IS_ABSOLUTE "${BW_WGPU_MIPMAP_SOURCE}" OR
     NOT EXISTS "${BW_WGPU_MIPMAP_SOURCE}")
    message(FATAL_ERROR
      "BW_WGPU_MIPMAP_SOURCE must name the extracted canonical mipmap method")
  endif()
  set(_bw_integrated_texture_sources
    wgpu_texture_format.cc
    wgpu_texture_format.hh
    wgpu_texture_format_list.h
    wgpu_common.hh
    wgpu_data_conversion.cc
    wgpu_data_conversion.hh
  )
  foreach(_bw_source IN LISTS _bw_integrated_texture_sources)
    set(_bw_source_path "${BW_INTEGRATED_TEXTURE_SOURCE_DIR}/${_bw_source}")
    if(NOT IS_ABSOLUTE "${_bw_source_path}" OR NOT EXISTS "${_bw_source_path}")
      message(FATAL_ERROR
        "integrated WebGPU texture input is missing or non-absolute: ${_bw_source_path}")
    endif()
  endforeach()
  foreach(_bw_source
      "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_format.hh"
      "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_texture.hh"
      "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern/BLI_assert.cc"
      "${_bw_integrated_texture_test}"
      "${_bw_integrated_mipmap_transaction_test}")
    if(NOT IS_ABSOLUTE "${_bw_source}" OR NOT EXISTS "${_bw_source}")
      message(FATAL_ERROR "integrated WebGPU texture dependency is missing: ${_bw_source}")
    endif()
  endforeach()

  add_executable(wgpu_texture_integrated_test
    "${_bw_integrated_texture_test}"
    "${_bw_integrated_mipmap_transaction_test}"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern/BLI_assert.cc"
    "${BW_INTEGRATED_TEXTURE_SOURCE_DIR}/wgpu_texture_format.cc"
    "${BW_INTEGRATED_TEXTURE_SOURCE_DIR}/wgpu_data_conversion.cc"
  )
  target_compile_definitions(wgpu_texture_integrated_test PRIVATE
    BW_WGPU_MIPMAP_SOURCE="${BW_WGPU_MIPMAP_SOURCE}"
  )
  target_include_directories(wgpu_texture_integrated_test PRIVATE
    "${DAWN_SRC_DIR}"
    "${BW_INTEGRATED_TEXTURE_SOURCE_DIR}"
    "${BW_UPSTREAM_DIR}/source/blender/gpu"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern"
    "${BW_UPSTREAM_DIR}/intern/guardedalloc"
    "${BW_NATIVE_FMT_INCLUDE_DIR}"
  )
  target_link_libraries(wgpu_texture_integrated_test PRIVATE
    dawn::webgpu_dawn
    tint_lang_wgsl_reader
  )
endif()

# Optional device-free contract for the canonical in-tree fixed-function state
# table. This compiles the shipping postimage directly against Blender's real
# GPU state enums, but deliberately never creates an instance, adapter, device,
# or render pipeline at runtime.
if(DEFINED BW_INTEGRATED_STATE_SOURCE_DIR)
  if(NOT DEFINED BW_UPSTREAM_DIR)
    message(FATAL_ERROR "BW_UPSTREAM_DIR is required with BW_INTEGRATED_STATE_SOURCE_DIR")
  endif()
  set(_bw_integrated_state_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-state-integrated-smoke/integrated_state_test.cc"
  )
  foreach(_bw_source wgpu_state_table.cc wgpu_state_table.hh)
    set(_bw_source_path "${BW_INTEGRATED_STATE_SOURCE_DIR}/${_bw_source}")
    if(NOT IS_ABSOLUTE "${_bw_source_path}" OR NOT EXISTS "${_bw_source_path}")
      message(FATAL_ERROR
        "integrated WebGPU state input is missing or non-absolute: ${_bw_source_path}")
    endif()
  endforeach()
  foreach(_bw_source
      "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_state.hh"
      "${BW_UPSTREAM_DIR}/source/blender/blenlib/BLI_enum_flags.hh"
      "${BW_UPSTREAM_DIR}/source/blender/blenlib/BLI_sys_types.h"
      "${_bw_integrated_state_test}")
    if(NOT IS_ABSOLUTE "${_bw_source}" OR NOT EXISTS "${_bw_source}")
      message(FATAL_ERROR "integrated WebGPU state dependency is missing: ${_bw_source}")
    endif()
  endforeach()

  add_executable(wgpu_state_integrated_test
    "${_bw_integrated_state_test}"
    "${BW_INTEGRATED_STATE_SOURCE_DIR}/wgpu_state_table.cc"
  )
  target_include_directories(wgpu_state_integrated_test PRIVATE
    "${BW_INTEGRATED_STATE_SOURCE_DIR}"
    "${BW_UPSTREAM_DIR}/source/blender/gpu"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib"
  )
  target_link_libraries(wgpu_state_integrated_test PRIVATE dawn::webgpu_dawn)
endif()

# Optional device-free contract for the canonical in-tree render-pipeline enum
# mappings. Unused live pipeline/cache functions are section-collected at link;
# the executable never creates an instance, adapter, device, or pipeline.
if(DEFINED BW_INTEGRATED_PIPELINE_SOURCE_DIR)
  if(NOT DEFINED BW_UPSTREAM_DIR)
    message(FATAL_ERROR "BW_UPSTREAM_DIR is required with BW_INTEGRATED_PIPELINE_SOURCE_DIR")
  endif()
  if(NOT DEFINED BW_GHOST_PRESENT_TRANSACTION_HEADER OR
     NOT IS_ABSOLUTE "${BW_GHOST_PRESENT_TRANSACTION_HEADER}" OR
     NOT EXISTS "${BW_GHOST_PRESENT_TRANSACTION_HEADER}")
    message(FATAL_ERROR
      "BW_GHOST_PRESENT_TRANSACTION_HEADER must name the shipping GHOST transaction header")
  endif()
  if(NOT DEFINED BW_GHOST_DISPLAY_STATE_HEADER OR
     NOT IS_ABSOLUTE "${BW_GHOST_DISPLAY_STATE_HEADER}" OR
     NOT EXISTS "${BW_GHOST_DISPLAY_STATE_HEADER}")
    message(FATAL_ERROR
      "BW_GHOST_DISPLAY_STATE_HEADER must name the shipping web display-state header")
  endif()
  get_filename_component(_bw_ghost_display_state_dir
    "${BW_GHOST_DISPLAY_STATE_HEADER}" DIRECTORY)
  if(NOT DEFINED BW_NATIVE_FMT_INCLUDE_DIR OR
     NOT IS_ABSOLUTE "${BW_NATIVE_FMT_INCLUDE_DIR}" OR
     NOT EXISTS "${BW_NATIVE_FMT_INCLUDE_DIR}/fmt/ranges.h")
    message(FATAL_ERROR
      "BW_NATIVE_FMT_INCLUDE_DIR must name the pinned native fmt include root")
  endif()
  set(_bw_integrated_pipeline_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-pipeline-integrated-smoke/integrated_pipeline_test.cc"
  )
  foreach(_bw_source wgpu_pipeline.cc wgpu_pipeline.hh)
    set(_bw_source_path "${BW_INTEGRATED_PIPELINE_SOURCE_DIR}/${_bw_source}")
    if(NOT IS_ABSOLUTE "${_bw_source_path}" OR NOT EXISTS "${_bw_source_path}")
      message(FATAL_ERROR
        "integrated WebGPU pipeline input is missing or non-absolute: ${_bw_source_path}")
    endif()
  endforeach()
  foreach(_bw_source
      "${BW_UPSTREAM_DIR}/source/blender/blenlib/BLI_assert.h"
      "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern/BLI_assert.cc")
    if(NOT IS_ABSOLUTE "${_bw_source}" OR NOT EXISTS "${_bw_source}")
      message(FATAL_ERROR "integrated WebGPU pipeline dependency is missing: ${_bw_source}")
    endif()
  endforeach()
  if(NOT IS_ABSOLUTE "${_bw_integrated_pipeline_test}" OR
     NOT EXISTS "${_bw_integrated_pipeline_test}")
    message(FATAL_ERROR
      "integrated WebGPU pipeline test is missing: ${_bw_integrated_pipeline_test}")
  endif()

  add_executable(wgpu_pipeline_integrated_test
    "${_bw_integrated_pipeline_test}"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern/BLI_assert.cc"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_vertex_format.cc"
  )
  target_compile_definitions(wgpu_pipeline_integrated_test PRIVATE
    BW_WGPU_PIPELINE_SOURCE="${BW_INTEGRATED_PIPELINE_SOURCE_DIR}/wgpu_pipeline.cc"
    BW_GHOST_PRESENT_TRANSACTION_HEADER="${BW_GHOST_PRESENT_TRANSACTION_HEADER}"
    BW_GHOST_DISPLAY_STATE_HEADER="${BW_GHOST_DISPLAY_STATE_HEADER}"
  )
  target_include_directories(wgpu_pipeline_integrated_test PRIVATE
    "${BW_INTEGRATED_PIPELINE_SOURCE_DIR}"
    "${BW_UPSTREAM_DIR}/source/blender/gpu"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern"
    "${BW_UPSTREAM_DIR}/source/blender/makesdna"
    "${BW_UPSTREAM_DIR}/intern/guardedalloc"
    "${BW_NATIVE_FMT_INCLUDE_DIR}"
    "${_bw_ghost_display_state_dir}"
  )
  target_compile_options(wgpu_pipeline_integrated_test PRIVATE
    -ffunction-sections
    -fdata-sections
  )
  target_link_options(wgpu_pipeline_integrated_test PRIVATE -Wl,--gc-sections)
  target_link_libraries(wgpu_pipeline_integrated_test PRIVATE dawn::webgpu_dawn)

  add_executable(ghost_first_pixel_settle_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-pipeline-integrated-smoke/first_pixel_settle_test.cc"
  )
  target_compile_definitions(ghost_first_pixel_settle_test PRIVATE
    BW_GHOST_DISPLAY_STATE_HEADER="${BW_GHOST_DISPLAY_STATE_HEADER}"
  )
  set_target_properties(ghost_first_pixel_settle_test PROPERTIES
    CXX_STANDARD 17
    CXX_STANDARD_REQUIRED ON
  )

  # Focused delayed-callback lifetime seam. AddressSanitizer makes the unsafe
  # raw-owner control observable while the accepted path includes only the
  # shipping owner-lifetime primitive and creates no Dawn device.
  set(_bw_ghost_acquisition_lifetime_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-pipeline-integrated-smoke/ghost_acquisition_lifetime_test.cc"
  )
  if(NOT IS_ABSOLUTE "${_bw_ghost_acquisition_lifetime_test}" OR
     NOT EXISTS "${_bw_ghost_acquisition_lifetime_test}")
    message(FATAL_ERROR "GHOST acquisition lifetime test is missing")
  endif()
  add_executable(ghost_acquisition_lifetime_asan "${_bw_ghost_acquisition_lifetime_test}")
  target_compile_definitions(ghost_acquisition_lifetime_asan PRIVATE
    BW_GHOST_PRESENT_TRANSACTION_HEADER="${BW_GHOST_PRESENT_TRANSACTION_HEADER}"
  )
  target_compile_options(ghost_acquisition_lifetime_asan PRIVATE
    -O1
    -g
    -fsanitize=address
    -fno-omit-frame-pointer
  )
  target_link_options(ghost_acquisition_lifetime_asan PRIVATE -fsanitize=address)
endif()

# Optional device-free contract for the canonical in-tree vertex-buffer CPU
# conversion helpers. The test includes the shipping translation unit so its
# private signed-I10 path is exercised directly; live-device sections are
# collected at link and no WebGPU object is created at runtime.
if(DEFINED BW_INTEGRATED_VERTEX_SOURCE_DIR)
  if(NOT DEFINED BW_UPSTREAM_DIR)
    message(FATAL_ERROR "BW_UPSTREAM_DIR is required with BW_INTEGRATED_VERTEX_SOURCE_DIR")
  endif()
  if(NOT DEFINED BW_NATIVE_FMT_INCLUDE_DIR OR
     NOT IS_ABSOLUTE "${BW_NATIVE_FMT_INCLUDE_DIR}" OR
     NOT EXISTS "${BW_NATIVE_FMT_INCLUDE_DIR}/fmt/ranges.h")
    message(FATAL_ERROR
      "BW_NATIVE_FMT_INCLUDE_DIR must name the pinned native fmt include root")
  endif()
  set(_bw_integrated_vertex_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-vertex-integrated-smoke/integrated_vertex_test.cc"
  )
  foreach(_bw_source wgpu_vertex_buffer.cc wgpu_vertex_buffer.hh wgpu_buffer.hh wgpu_common.hh)
    set(_bw_source_path "${BW_INTEGRATED_VERTEX_SOURCE_DIR}/${_bw_source}")
    if(NOT IS_ABSOLUTE "${_bw_source_path}" OR NOT EXISTS "${_bw_source_path}")
      message(FATAL_ERROR
        "integrated WebGPU vertex input is missing or non-absolute: ${_bw_source_path}")
    endif()
  endforeach()
  foreach(_bw_source
      "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_vertex_format.hh"
      "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_vertex_format.cc"
      "${BW_UPSTREAM_DIR}/source/blender/blenlib/BLI_assert.h"
      "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern/BLI_assert.cc")
    if(NOT IS_ABSOLUTE "${_bw_source}" OR NOT EXISTS "${_bw_source}")
      message(FATAL_ERROR "integrated WebGPU vertex dependency is missing: ${_bw_source}")
    endif()
  endforeach()
  if(NOT IS_ABSOLUTE "${_bw_integrated_vertex_test}" OR
     NOT EXISTS "${_bw_integrated_vertex_test}")
    message(FATAL_ERROR
      "integrated WebGPU vertex test is missing: ${_bw_integrated_vertex_test}")
  endif()

  add_executable(wgpu_vertex_integrated_test
    "${_bw_integrated_vertex_test}"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_vertex_format.cc"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern/BLI_assert.cc"
  )
  target_include_directories(wgpu_vertex_integrated_test PRIVATE
    "${BW_INTEGRATED_VERTEX_SOURCE_DIR}"
    "${BW_UPSTREAM_DIR}/source/blender/gpu"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern"
    "${BW_UPSTREAM_DIR}/source/blender/blenkernel"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern"
    "${BW_UPSTREAM_DIR}/source/blender/makesdna"
    "${BW_UPSTREAM_DIR}/source/blender/makesrna"
    "${BW_UPSTREAM_DIR}/intern/atomic"
    "${BW_UPSTREAM_DIR}/intern/clog"
    "${BW_UPSTREAM_DIR}/intern/ghost"
    "${BW_UPSTREAM_DIR}/intern/guardedalloc"
    "${BW_NATIVE_FMT_INCLUDE_DIR}"
  )
  target_compile_options(wgpu_vertex_integrated_test PRIVATE
    -ffunction-sections
    -fdata-sections
  )
  target_link_options(wgpu_vertex_integrated_test PRIVATE -Wl,--gc-sections)
  target_link_libraries(wgpu_vertex_integrated_test PRIVATE dawn::webgpu_dawn)
endif()

# Optional device-free contract for the canonical in-tree shader frontend. The
# test includes the shipping translation unit so its private GLSL type/format
# helpers are exercised directly; all live-device sections are collected at
# link and no WebGPU object is created at runtime.
if(DEFINED BW_INTEGRATED_SHADER_FRONTEND_SOURCE_DIR)
  if(NOT DEFINED BW_UPSTREAM_DIR)
    message(FATAL_ERROR
      "BW_UPSTREAM_DIR is required with BW_INTEGRATED_SHADER_FRONTEND_SOURCE_DIR")
  endif()
  if(NOT DEFINED BW_NATIVE_FMT_INCLUDE_DIR OR
     NOT IS_ABSOLUTE "${BW_NATIVE_FMT_INCLUDE_DIR}" OR
     NOT EXISTS "${BW_NATIVE_FMT_INCLUDE_DIR}/fmt/ranges.h")
    message(FATAL_ERROR
      "BW_NATIVE_FMT_INCLUDE_DIR must name the pinned native fmt include root")
  endif()
  if(NOT DEFINED BW_WGPU_PUSH_CONSTANT_SET_SOURCE OR
     NOT IS_ABSOLUTE "${BW_WGPU_PUSH_CONSTANT_SET_SOURCE}" OR
     NOT EXISTS "${BW_WGPU_PUSH_CONSTANT_SET_SOURCE}")
    message(FATAL_ERROR
      "BW_WGPU_PUSH_CONSTANT_SET_SOURCE must name the extracted canonical method")
  endif()
  set(_bw_integrated_shader_frontend_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-shader-frontend-integrated-smoke/integrated_shader_frontend_test.cc"
  )
  foreach(_bw_source wgpu_shader.cc wgpu_shader.hh wgpu_texture_format.hh)
    set(_bw_source_path "${BW_INTEGRATED_SHADER_FRONTEND_SOURCE_DIR}/${_bw_source}")
    if(NOT IS_ABSOLUTE "${_bw_source_path}" OR NOT EXISTS "${_bw_source_path}")
      message(FATAL_ERROR
        "integrated WebGPU shader-frontend input is missing or non-absolute: ${_bw_source_path}")
    endif()
  endforeach()
  if(NOT IS_ABSOLUTE "${_bw_integrated_shader_frontend_test}" OR
     NOT EXISTS "${_bw_integrated_shader_frontend_test}")
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
    if(NOT IS_ABSOLUTE "${_bw_source}" OR NOT EXISTS "${_bw_source}")
      message(FATAL_ERROR
        "integrated WebGPU shader-frontend runtime input is missing: ${_bw_source}")
    endif()
  endforeach()

  find_package(Threads REQUIRED)
  add_executable(wgpu_shader_frontend_integrated_test
    "${_bw_integrated_shader_frontend_test}"
    "${BW_UPSTREAM_DIR}/intern/clog/clog.cc"
    ${_bw_shader_frontend_guardedalloc_sources}
  )
  target_compile_definitions(wgpu_shader_frontend_integrated_test PRIVATE
    BW_WGPU_SHADER_SOURCE="${BW_INTEGRATED_SHADER_FRONTEND_SOURCE_DIR}/wgpu_shader.cc"
    BW_WGPU_PUSH_CONSTANT_SET_SOURCE="${BW_WGPU_PUSH_CONSTANT_SET_SOURCE}"
    WITH_CLOG_PTHREADS
  )
  target_include_directories(wgpu_shader_frontend_integrated_test PRIVATE
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
    "${BW_NATIVE_FMT_INCLUDE_DIR}"
  )
  target_compile_options(wgpu_shader_frontend_integrated_test PRIVATE
    -ffunction-sections
    -fdata-sections
  )
  target_link_options(wgpu_shader_frontend_integrated_test PRIVATE -Wl,--gc-sections)
  target_link_libraries(wgpu_shader_frontend_integrated_test PRIVATE
    dawn::webgpu_dawn
    Threads::Threads
  )
endif()

# Optional device-free contract for the canonical in-tree conservative
# occlusion-query fallback. This compiles the shipping implementation directly
# and exercises only its CPU state machine; no WebGPU object is created.
if(DEFINED BW_INTEGRATED_QUERY_SOURCE_DIR)
  if(NOT DEFINED BW_UPSTREAM_DIR)
    message(FATAL_ERROR "BW_UPSTREAM_DIR is required with BW_INTEGRATED_QUERY_SOURCE_DIR")
  endif()
  set(_bw_integrated_query_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-query-integrated-smoke/integrated_query_test.cc"
  )
  foreach(_bw_source wgpu_query.cc wgpu_query.hh)
    set(_bw_source_path "${BW_INTEGRATED_QUERY_SOURCE_DIR}/${_bw_source}")
    if(NOT IS_ABSOLUTE "${_bw_source_path}" OR NOT EXISTS "${_bw_source_path}")
      message(FATAL_ERROR
        "integrated WebGPU query input is missing or non-absolute: ${_bw_source_path}")
    endif()
  endforeach()
  foreach(_bw_source
      "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_query.hh"
      "${BW_UPSTREAM_DIR}/source/blender/blenlib/BLI_assert.h"
      "${BW_UPSTREAM_DIR}/source/blender/blenlib/BLI_span.hh")
    if(NOT IS_ABSOLUTE "${_bw_source}" OR NOT EXISTS "${_bw_source}")
      message(FATAL_ERROR "integrated WebGPU query dependency is missing: ${_bw_source}")
    endif()
  endforeach()
  if(NOT IS_ABSOLUTE "${_bw_integrated_query_test}" OR
     NOT EXISTS "${_bw_integrated_query_test}")
    message(FATAL_ERROR
      "integrated WebGPU query test is missing: ${_bw_integrated_query_test}")
  endif()

  add_executable(wgpu_query_integrated_test
    "${_bw_integrated_query_test}"
    "${BW_INTEGRATED_QUERY_SOURCE_DIR}/wgpu_query.cc"
  )
  target_include_directories(wgpu_query_integrated_test PRIVATE
    "${BW_INTEGRATED_QUERY_SOURCE_DIR}"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib"
  )
endif()

# Optional device-free contract for the canonical in-tree state-manager bind
# spaces, sampler-descriptor policy, and queue-ordered fence lifecycle. The real
# base StateManager constructor is retained from gpu_state.cc while its unrelated
# frontend/device sections are collected at link.
if(DEFINED BW_INTEGRATED_BINDSPACE_SOURCE_DIR)
  if(NOT DEFINED BW_UPSTREAM_DIR)
    message(FATAL_ERROR
      "BW_UPSTREAM_DIR is required with BW_INTEGRATED_BINDSPACE_SOURCE_DIR")
  endif()
  if(NOT DEFINED BW_NATIVE_FMT_INCLUDE_DIR OR
     NOT IS_ABSOLUTE "${BW_NATIVE_FMT_INCLUDE_DIR}" OR
     NOT EXISTS "${BW_NATIVE_FMT_INCLUDE_DIR}/fmt/ranges.h")
    message(FATAL_ERROR
      "BW_NATIVE_FMT_INCLUDE_DIR must name the pinned native fmt include root")
  endif()
  if(NOT DEFINED BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE OR
     NOT IS_ABSOLUTE "${BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE}" OR
     NOT EXISTS "${BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE}")
    message(FATAL_ERROR
      "BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE must name the extracted canonical policy")
  endif()
  if(NOT DEFINED BW_WGPU_DUMMY_VERTEX_SOURCE OR
     NOT IS_ABSOLUTE "${BW_WGPU_DUMMY_VERTEX_SOURCE}" OR
     NOT EXISTS "${BW_WGPU_DUMMY_VERTEX_SOURCE}")
    message(FATAL_ERROR
      "BW_WGPU_DUMMY_VERTEX_SOURCE must name the extracted canonical policy")
  endif()
  set(_bw_integrated_bindspace_test
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-bindspace-integrated-smoke/integrated_bindspace_test.cc"
  )
  foreach(_bw_source wgpu_state_manager.cc wgpu_state_manager.hh)
    set(_bw_source_path "${BW_INTEGRATED_BINDSPACE_SOURCE_DIR}/${_bw_source}")
    if(NOT IS_ABSOLUTE "${_bw_source_path}" OR NOT EXISTS "${_bw_source_path}")
      message(FATAL_ERROR
        "integrated WebGPU bind-space input is missing or non-absolute: ${_bw_source_path}")
    endif()
  endforeach()
  foreach(_bw_source
      "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_state.cc"
      "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_state_private.hh"
      "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_texture_private.hh"
      "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_state.hh"
      "${BW_UPSTREAM_DIR}/source/blender/gpu/GPU_texture.hh")
    if(NOT IS_ABSOLUTE "${_bw_source}" OR NOT EXISTS "${_bw_source}")
      message(FATAL_ERROR
        "integrated WebGPU bind-space dependency is missing: ${_bw_source}")
    endif()
  endforeach()
  if(NOT IS_ABSOLUTE "${_bw_integrated_bindspace_test}" OR
     NOT EXISTS "${_bw_integrated_bindspace_test}")
    message(FATAL_ERROR
      "integrated WebGPU bind-space test is missing: ${_bw_integrated_bindspace_test}")
  endif()

  add_executable(wgpu_bindspace_integrated_test
    "${_bw_integrated_bindspace_test}"
    "${BW_INTEGRATED_BINDSPACE_SOURCE_DIR}/wgpu_state_manager.cc"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern/gpu_state.cc"
  )
  target_compile_definitions(wgpu_bindspace_integrated_test PRIVATE
    GPU_STANDALONE
    BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE="${BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE}"
    BW_WGPU_DUMMY_VERTEX_SOURCE="${BW_WGPU_DUMMY_VERTEX_SOURCE}"
  )
  target_include_directories(wgpu_bindspace_integrated_test PRIVATE
    "${BW_INTEGRATED_BINDSPACE_SOURCE_DIR}"
    "${BW_UPSTREAM_DIR}/source/blender/blenkernel"
    "${BW_UPSTREAM_DIR}/source/blender/gpu"
    "${BW_UPSTREAM_DIR}/source/blender/gpu/intern"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib"
    "${BW_UPSTREAM_DIR}/source/blender/blenlib/intern"
    "${BW_UPSTREAM_DIR}/source/blender/makesdna"
    "${BW_UPSTREAM_DIR}/intern/ghost"
    "${BW_UPSTREAM_DIR}/intern/ghost/intern"
    "${BW_UPSTREAM_DIR}/intern/guardedalloc"
    "${BW_NATIVE_FMT_INCLUDE_DIR}"
  )
  target_compile_options(wgpu_bindspace_integrated_test PRIVATE
    -ffunction-sections
    -fdata-sections
  )
  target_link_options(wgpu_bindspace_integrated_test PRIVATE -Wl,--gc-sections)
endif()
