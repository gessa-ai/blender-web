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

# msgfmt: WITH_INTERNATIONAL .po -> .mo catalog compiler. Runs NATIVE under the wasm
# cross-build (ADR-002): its binary GNU .mo output is target-independent (UTF-8, fixed
# little-endian magic 0x950412de), and patch 0127 wires macros.cmake's msgfmt_simple to
# ${BLENDER_WEB_HOST_TOOLS_DIR}/msgfmt. Unlike datatoc/shader_tool, msgfmt links a minimal
# slice of blenlib (file IO + strings + linklist) and guardedalloc, so its TU set is
# explicit below. Header deps beyond the source tree: BLI_string_ref.hh needs fmt/ (header-
# only) and blenlib/intern/fileops_c.cc needs <zstd.h>; both live in the repo-local wasm
# lib bundle (lib/wasm/include, the same headers the real wasm build uses via -isystem).
# The direct native link resolves fileops_c.cc's object-level closure with the host zlib
# and zstd libraries; the migration runbook installs their development packages. ld64
# spells dead-code stripping as -dead_strip; GNU ld spells it --gc-sections.
DEAD_STRIP="-Wl,--gc-sections"
[ "$(uname -s)" = Darwin ] && DEAD_STRIP="-Wl,-dead_strip"
echo "[build-hosttools] msgfmt"
BL="$SRC/blenlib"
GA="$ROOT/upstream/intern/guardedalloc"
MF="$SRC/blentranslation/msgfmt"
LIBWASM_INC="$ROOT/lib/wasm/include"
if [ ! -f "$LIBWASM_INC/fmt/ranges.h" ] || [ ! -f "$LIBWASM_INC/zstd.h" ]; then
  echo "[build-hosttools] ERROR: $LIBWASM_INC missing fmt/ or zstd.h (wasm lib bundle)." >&2
  echo "[build-hosttools]        msgfmt needs the same headers the wasm build uses." >&2
  exit 1
fi
"$CXX" -std=c++20 -O2 -DNDEBUG -funsigned-char \
  -I "$BL" -I "$GA" -I "$ROOT/upstream/intern/atomic" -I "$ROOT/upstream/intern/eigen" \
  -I "$SRC/makesdna" -I "$ROOT/upstream/extern/wcwidth" -include cstddef -Wno-conversion -Wno-sign-conversion -isystem "$LIBWASM_INC" \
  "$DEAD_STRIP" \
  -o "$OUT/msgfmt" \
  "$MF/msgfmt.cc" \
  "$BL/intern/string.cc" \
  "$BL/intern/BLI_linklist.cc" \
  "$BL/intern/storage.cc" \
  "$BL/intern/fileops_c.cc" \
  "$BL/intern/path_utils.cc" \
  "$BL/intern/BLI_assert.cc" \
  "$BL/intern/string_utils.cc" \
  "$BL/intern/string_utf8.cc" \
  "$BL/intern/BLI_dynstr.cc" \
  "$ROOT/upstream/extern/wcwidth/wcwidth.c" \
  "$BL/intern/BLI_memarena.cc" \
  "$BL/intern/BLI_mempool.cc" \
  "$GA/intern/mallocn.cc" \
  "$GA/intern/mallocn_lockfree_impl.cc" \
  "$GA/intern/mallocn_guarded_impl.cc" \
  "$GA/intern/memory_usage.cc" \
  "$GA/intern/leak_detector.cc" \
  -lz -lzstd

echo "[build-hosttools] done:"
ls -la "$OUT/datatoc" "$OUT/shader_tool" "$OUT/msgfmt"
