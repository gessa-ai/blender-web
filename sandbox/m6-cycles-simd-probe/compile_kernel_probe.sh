#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/sandbox/m6-cycles-simd-probe"
TARGET="intern/cycles/kernel/device/cpu/CMakeFiles/cycles_kernel_cpu.dir/kernel.cpp.o"
HEADER="$HERE/force_wasm_simd.h"
OBJECT="$HERE/kernel-wasm-simd.o"

command_line="$($ROOT/scripts/ninja-locked.sh -C "$ROOT/build-wasm-cycles" -t commands "$TARGET")"
[[ "$command_line" == *"/em++ "* && "$command_line" == *"/kernel.cpp"* ]] || {
  echo "KERNEL_PROBE_FAIL unexpected Ninja command" >&2
  exit 1
}

# Ninja's command is trusted repository build metadata. Re-tokenize its quoted
# definitions, then replace dependency/output bookkeeping so the production
# object and Ninja state remain untouched.
eval "set -- $command_line"
args=()
skip_next=0
for arg in "$@"; do
  if [[ "$skip_next" == 1 ]]; then
    skip_next=0
    continue
  fi
  case "$arg" in
    -MD) ;;
    -MT|-MF|-o) skip_next=1 ;;
    *) args+=("$arg") ;;
  esac
done

rm -f "$OBJECT"
"${args[@]}" \
  -msimd128 -msse -msse2 -msse3 -mssse3 -msse4.1 -msse4.2 \
  -include "$HEADER" \
  -o "$OBJECT"

[[ -s "$OBJECT" ]] || {
  echo "KERNEL_PROBE_FAIL no output object" >&2
  exit 1
}

simd_ops="$($ROOT/tools/emsdk/upstream/bin/llvm-objdump -d "$OBJECT" | grep -Ec 'v128|f32x4|i32x4' || true)"
[[ "$simd_ops" -gt 0 ]] || {
  echo "KERNEL_PROBE_FAIL object contains no wasm SIMD instructions" >&2
  exit 1
}

bytes="$(wc -c < "$OBJECT" | tr -d ' ')"
sha="$(sha256sum "$OBJECT" | awk '{print $1}')"
echo "KERNEL_PROBE_PASS bytes=$bytes simd_ops=$simd_ops sha256=$sha production_object_untouched=1"
