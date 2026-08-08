# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
# Standalone proof of the name-section-strip gate copied verbatim from
# patches/platform_wasm.cmake (no shared-tree reconfigure).
cmake_minimum_required(VERSION 3.20)
project(namestrip_gate_test NONE)
set(_bw_browser_flags "...-sEXPORTED_RUNTIME_METHODS=ENV,FS,callMain")
if(CMAKE_BUILD_TYPE STREQUAL "Release")
  string(APPEND _bw_browser_flags " -g0")
else()
  string(APPEND _bw_browser_flags " --profiling-funcs")
endif()
message(STATUS "BUILD_TYPE=[${CMAKE_BUILD_TYPE}] FLAGS_TAIL=[...${CMAKE_MATCH_0}]")
string(REGEX REPLACE "^.*callMain" "callMain" _tail "${_bw_browser_flags}")
message(STATUS "RESULT BUILD_TYPE=[${CMAKE_BUILD_TYPE}] TAIL=[${_tail}]")
