#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

# Read-only M3 census runner. Unlike harness/run.sh, this writes receipts only to
# the M6 evidence directory and never updates ledger/results or harness/GATE_RED.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/sandbox/gpu-m6-rescore-final"
BIN="$ROOT/build-native-gpu/bin/tests/blender_test"
TSV="$OUT/native-census.tsv"
STATIC_LOG="$OUT/static-shaders.log"
SUMMARY="$OUT/native-census-summary.txt"

mkdir -p "$OUT"
test -x "$BIN"

LIST="$($BIN --gtest_list_tests --gtest_filter='GPUWebGPUTest.*' 2>/dev/null |
  grep -E '^  ' | sed 's/^  *//')"

printf '# test\tverdict\trc\n' > "$TSV"
npass=0
nfail=0
ncrash=0
while IFS= read -r test_name; do
  test -n "$test_name" || continue
  bash -c '"$1" --gtest_filter="GPUWebGPUTest.$2" >/dev/null 2>&1' \
    _ "$BIN" "$test_name" 2>/dev/null
  rc=$?
  if [ "$rc" = 0 ]; then
    verdict=PASS
    npass=$((npass + 1))
  elif [ "$rc" -gt 128 ]; then
    verdict=CRASH
    ncrash=$((ncrash + 1))
  else
    verdict=FAIL
    nfail=$((nfail + 1))
  fi
  printf '%s\t%s\t%s\n' "$test_name" "$verdict" "$rc" >> "$TSV"
done <<< "$LIST"

"$BIN" --gtest_filter='GPUWebGPUTest.static_shaders' > "$STATIC_LOG" 2>&1 || true
static_line="$(grep -m1 'Shader Test compilation result:' "$STATIC_LOG")"
static_counts="$(printf '%s' "$static_line" | grep -oE '[0-9]+ / [0-9]+' | head -1)"

{
  printf 'GPUWebGPUTest: %d PASS / %d FAIL / %d CRASH (%d total)\n' \
    "$npass" "$nfail" "$ncrash" "$((npass + nfail + ncrash))"
  printf 'static_shaders: %s\n' "$static_counts"
} > "$SUMMARY"
cat "$SUMMARY"
