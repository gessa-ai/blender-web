# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

cmake_minimum_required(VERSION 3.20)
project(m5_particle_edit_depth_cache_contract LANGUAGES CXX)

add_executable(m5_particle_edit_depth_cache_contract contract_test.cc)
target_compile_features(m5_particle_edit_depth_cache_contract PRIVATE cxx_std_20)
target_compile_definitions(m5_particle_edit_depth_cache_contract PRIVATE NDEBUG)
target_compile_options(m5_particle_edit_depth_cache_contract PRIVATE
  -Wall -Wextra -Werror
)

if(EMSCRIPTEN)
  target_compile_options(m5_particle_edit_depth_cache_contract PRIVATE -pthread)
  target_link_options(m5_particle_edit_depth_cache_contract PRIVATE
    -pthread
    -sENVIRONMENT=node
    -sEXIT_RUNTIME=1
  )
  set_target_properties(m5_particle_edit_depth_cache_contract PROPERTIES SUFFIX ".js")
endif()
