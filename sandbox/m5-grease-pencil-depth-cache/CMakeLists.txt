# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

cmake_minimum_required(VERSION 3.20)
project(m5_grease_pencil_depth_cache_contract LANGUAGES CXX)

add_executable(m5_grease_pencil_depth_cache_contract contract_test.cc)
target_compile_features(m5_grease_pencil_depth_cache_contract PRIVATE cxx_std_20)
target_compile_options(m5_grease_pencil_depth_cache_contract PRIVATE -Wall -Wextra -Werror)
