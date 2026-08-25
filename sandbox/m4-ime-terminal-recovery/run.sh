#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="$ROOT/build-deps/m4-ime-terminal-recovery"
mkdir -p "$OUT"

source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

NATIVE_CXX="${NATIVE_CXX:-clang++-17}"
"$NATIVE_CXX" -std=c++17 -O2 -pthread \
  -I"$ROOT/platform_web/ghost" "$HERE/contract_test.cc" -o "$OUT/contract-native"
em++ -std=c++17 -O2 -pthread -sEXIT_RUNTIME=1 \
  -I"$ROOT/platform_web/ghost" "$HERE/contract_test.cc" -o "$OUT/contract-wasm.js"

"$OUT/contract-native" >"$OUT/native.txt"
"$EMSDK_NODE" "$OUT/contract-wasm.js" >"$OUT/wasm.txt"
cmp "$OUT/native.txt" "$OUT/wasm.txt"

DIGEST="$(sha256sum "$OUT/native.txt" | awk '{print $1}')"
printf 'PASS ime-terminal-recovery native/wasm bytes=%s sha256=%s\n' \
  "$(wc -c <"$OUT/native.txt")" "$DIGEST"
