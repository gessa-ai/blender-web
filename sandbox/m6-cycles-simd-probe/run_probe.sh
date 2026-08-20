#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
EMXX="$ROOT/tools/emsdk/upstream/emscripten/em++"
NODE="$ROOT/tools/emsdk/node/22.16.0_64bit/bin/node"
SOURCE="$ROOT/sandbox/m6-cycles-simd-probe/sse42_probe.cc"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

COMMON=(
  -std=c++20
  -O2
  -I"$ROOT/upstream/intern/cycles"
  "$SOURCE"
)

if "$EMXX" -msse4.2 "${COMMON[@]}" -c -o "$TMP_DIR/negative.o" >"$TMP_DIR/negative.log" 2>&1; then
  echo "PROBE_FAIL missing-msimd128 negative control unexpectedly compiled" >&2
  exit 1
fi
if ! grep -Fq "also requires passing -msimd128" "$TMP_DIR/negative.log"; then
  echo "PROBE_FAIL missing-msimd128 negative control changed signature" >&2
  exit 1
fi

"$EMXX" -msimd128 -msse4.2 "${COMMON[@]}" -c -o "$TMP_DIR/probe.o"
# Deliberately omit -msimd128 at link: this proves the target-feature metadata
# on the object is sufficient for Blender's parent executable link.
"$EMXX" "$TMP_DIR/probe.o" -o "$TMP_DIR/probe.js"
output="$($NODE "$TMP_DIR/probe.js")"
expected="CYCLES_WASM_SIMD_PROBE 6.250000 -2.500000 0.000000 4.500000 mask=2"
if [[ "$output" != "$expected" ]]; then
  echo "PROBE_FAIL runtime output: $output" >&2
  exit 1
fi

echo "PROBE_PASS negative=missing-msimd128 positive=cycles-float4-sse42 runtime=exact"
