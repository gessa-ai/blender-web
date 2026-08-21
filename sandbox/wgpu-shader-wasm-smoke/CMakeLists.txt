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

add_executable(wgpu_shader_chain_smoke smoke.cc)
set_target_properties(wgpu_shader_chain_smoke PROPERTIES
  CXX_STANDARD 20
  CXX_STANDARD_REQUIRED ON
  OUTPUT_NAME smoke
  SUFFIX ".js"
)
target_include_directories(wgpu_shader_chain_smoke PRIVATE
  "${SHADERC_PREFIX}/include"
  "${DAWN_SRC_DIR}"
)
target_compile_options(wgpu_shader_chain_smoke PRIVATE
  -pthread
  -fexceptions
)
target_link_options(wgpu_shader_chain_smoke PRIVATE
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
target_link_libraries(wgpu_shader_chain_smoke PRIVATE
  "-Wl,--start-group"
  ${_shaderc_archives}
  ${_tint_archives}
  "-Wl,--end-group"
)
