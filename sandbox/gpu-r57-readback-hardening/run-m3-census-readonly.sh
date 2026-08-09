#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Read-only copy of harness/run.sh's M3 process-exit census. It intentionally
# writes no ledger/results file and no GATE_RED marker in the shared checkout.
set -u

bin="${M3_TEST_BIN:-build-native-gpu/bin/tests/blender_test}"
list="$($bin --gtest_list_tests --gtest_filter='GPUWebGPUTest.*' 2>/dev/null | \
  grep -E '^  ' | sed 's/^  *//')"
ntests="$(printf '%s\n' "$list" | grep -c .)"
npass=0
nfail=0
ncrash=0
nonpass=""

while IFS= read -r test_name; do
  [ -z "$test_name" ] && continue
  bash -c '"$1" --gtest_filter="GPUWebGPUTest.$2" >/dev/null 2>&1' \
    _ "$bin" "$test_name" 2>/dev/null
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
  if [ "$verdict" != PASS ]; then
    nonpass="${nonpass}${test_name} ${verdict}\n"
  fi
done <<< "$list"

shader_output="$($bin --gtest_filter='GPUWebGPUTest.static_shaders' 2>&1)"
shader_summary="$(printf '%s\n' "$shader_output" | grep -m1 'Shader Test compilation result:')"
shader_ratio="$(printf '%s' "$shader_summary" | grep -oE '[0-9]+ / [0-9]+' | head -1)"
i10_rc=0
$bin --gtest_filter='GPUWebGPUTest.vertex_buffer_fetch_mode__GPU_COMP_I10__GPU_FETCH_INT_TO_FLOAT_UNIT' \
  >/dev/null 2>&1 || i10_rc=$?

printf 'GPUWebGPUTest census: %d PASS / %d FAIL / %d CRASH / %d tests\n' \
  "$npass" "$nfail" "$ncrash" "$ntests"
printf 'Non-PASS tests:\n%b' "$nonpass"
printf 'static_shaders: %s\n' "$shader_ratio"
printf 'I10 control exit: %d (%s)\n' "$i10_rc" "$([ "$i10_rc" = 0 ] && printf PASS || printf NONPASS)"

if [ "$npass" = 149 ] && [ "$nfail" = 7 ] && [ "$ncrash" = 2 ] && \
   [ "$ntests" = 158 ] && [ "$shader_ratio" = '956 / 973' ] && [ "$i10_rc" = 0 ]; then
  printf 'R57_M3_CENSUS PASS expected=149/7/2 static=956/973 I10-only-spurious-red=confirmed\n'
  exit 0
fi

printf 'R57_M3_CENSUS FAIL expected=149/7/2 static=956/973 I10-pass\n'
exit 1
