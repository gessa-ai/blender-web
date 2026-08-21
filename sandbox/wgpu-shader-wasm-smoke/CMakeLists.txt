# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

cmake_minimum_required(VERSION 3.16)
project(wgpu_shader_wasm_smoke CXX)

if(NOT EMSCRIPTEN)
  message(FATAL_ERROR "This project builds only the WebAssembly parity leg")
endif()

foreach(_required_var DAWN_SRC_DIR SHADERC_PREFIX TINT_PREFIX)
  if(NOT IS_ABSOLUTE "${${_required_var}}")
    message(FATAL_ERROR "${_required_var} must be an absolute path")
  endif()
  if(NOT IS_DIRECTORY "${${_required_var}}")
    message(FATAL_ERROR "${_required_var} is not a directory: ${${_required_var}}")
  endif()
endforeach()

function(read_archive_manifest manifest library_dir expected_count output_var)
  if(NOT EXISTS "${manifest}")
    message(FATAL_ERROR "archive manifest does not exist: ${manifest}")
  endif()
  file(STRINGS "${manifest}" _archive_names)
  list(LENGTH _archive_names _archive_count)
  if(NOT _archive_count EQUAL ${expected_count})
    message(FATAL_ERROR
      "${manifest} contains ${_archive_count} archives; expected ${expected_count}")
  endif()

  set(_archives "")
  foreach(_archive_name IN LISTS _archive_names)
    if(NOT _archive_name MATCHES "^lib[A-Za-z0-9_.+-]+\\.a$")
      message(FATAL_ERROR "invalid archive name in ${manifest}: ${_archive_name}")
    endif()
    set(_archive "${library_dir}/${_archive_name}")
    if(NOT EXISTS "${_archive}")
      message(FATAL_ERROR "manifest-listed archive does not exist: ${_archive}")
    endif()
    list(APPEND _archives "${_archive}")
  endforeach()
  set(${output_var} "${_archives}" PARENT_SCOPE)
endfunction()

read_archive_manifest(
  "${SHADERC_PREFIX}/shaderc-archives.txt"
  "${SHADERC_PREFIX}/lib"
  4
  _shaderc_archives)
read_archive_manifest(
  "${TINT_PREFIX}/tint-archives.txt"
  "${TINT_PREFIX}/lib"
  63
  _tint_archives)

function(configure_shader_smoke target output_name)
  set_target_properties(${target} PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
    OUTPUT_NAME "${output_name}"
    SUFFIX ".js"
  )
  target_include_directories(${target} PRIVATE
    "${SHADERC_PREFIX}/include"
    "${DAWN_SRC_DIR}"
  )
  target_compile_options(${target} PRIVATE
    -pthread
    -fexceptions
  )
  target_link_options(${target} PRIVATE
    -pthread
    -fexceptions
    "-sENVIRONMENT=node"
    "-sEXIT_RUNTIME=1"
    "-sSTACK_SIZE=33554432"
    "-sINITIAL_MEMORY=536870912"
    "-sPTHREAD_POOL_SIZE=4"
    "-sALLOW_MEMORY_GROWTH=1"
  )
  # shaderc/glslang and Tint/SPIRV-Tools retain cross-archive cycles. The two
  # checked manifests deliberately carry the single-SPIRV-Tools link closure.
  target_link_libraries(${target} PRIVATE
    "-Wl,--start-group"
    ${_shaderc_archives}
    ${_tint_archives}
    "-Wl,--end-group"
  )
endfunction()

add_executable(wgpu_shader_chain_smoke smoke.cc)
configure_shader_smoke(wgpu_shader_chain_smoke smoke)

add_executable(wgpu_shader_bindmap_smoke bindmap_smoke.cc)
configure_shader_smoke(wgpu_shader_bindmap_smoke bindmap_smoke)

# Optional Wasm leg for the canonical in-tree compiler module. It links the
# harvested CPU translation closure plus emdawnwebgpu's matching value types,
# but never creates a WebGPU adapter or device.
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

  add_executable(wgpu_shader_integrated_smoke
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-shader-compiler/tests/wgpu_shader_integrated_test.cc"
    "${BW_INTEGRATED_SOURCE_DIR}/wgpu_shader_interface_map.cc"
    "${BW_INTEGRATED_SOURCE_DIR}/wgpu_shader_compiler.cc"
    "${BW_INTEGRATED_SOURCE_DIR}/wgpu_shader_cache.cc"
  )
  target_include_directories(wgpu_shader_integrated_smoke PRIVATE
    "${BW_INTEGRATED_SOURCE_DIR}"
    "${CMAKE_CURRENT_SOURCE_DIR}/../wgpu-shader-compiler"
  )
  configure_shader_smoke(wgpu_shader_integrated_smoke integrated_smoke)
  # Native Dawn's generated headers deliberately reject __EMSCRIPTEN__. The
  # shipping product gets its matching C/C++ headers from this exact port flag;
  # use the same route for both compilation and link instead of smuggling native
  # generated headers into the Wasm target.
  target_compile_options(wgpu_shader_integrated_smoke PRIVATE
    "--use-port=emdawnwebgpu")
  target_link_options(wgpu_shader_integrated_smoke PRIVATE
    "--use-port=emdawnwebgpu"
    "-sNODERAWFS=1")
endif()
