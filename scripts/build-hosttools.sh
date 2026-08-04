#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# ADR-002: build the text-codegen host tools shader_tool + datatoc as NATIVE host
# binaries (host compiler) into build-hosttools/bin-native/. The wasm build's
# custom commands invoke these via BLENDER_WEB_HOST_TOOLS_DIR (patches/platform_wasm.cmake)
# instead of a wasm-under-node build, because shader_tool's wasm lexer mis-tokenizes
# some shaders (silent corruption / hangs) while its output is target-INDEPENDENT text
# (byte-identity verified — notes/m1-shader-codegen-wasm.md). makesdna/makesrna stay
# wasm (they bake target ABI) and are NOT built here.
#
# Idempotent. Run before configuring/building build-wasm. Both tools are fully
# self-contained (datatoc: stdlib only; shader_tool: only its own headers), so a
# direct host-compiler invocation suffices — no Blender deps, no CMake needed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/upstream/source/blender"
OUT="$ROOT/build-hosttools/bin-native"
CXX="${CXX:-c++}"
mkdir -p "$OUT"

echo "[build-hosttools] host compiler: $($CXX --version | head -1)"

echo "[build-hosttools] datatoc"
"$CXX" -std=c++20 -O2 -o "$OUT/datatoc" "$SRC/datatoc/datatoc.cc"

echo "[build-hosttools] shader_tool"
ST="$SRC/gpu/shader_tool"
"$CXX" -std=c++20 -O2 \
  -I "$ST" -I "$ST/lexit" \
  -o "$OUT/shader_tool" \
  "$ST"/*.cc "$ST"/lexit/lexit.cc

echo "[build-hosttools] done:"
ls -la "$OUT/datatoc" "$OUT/shader_tool"
