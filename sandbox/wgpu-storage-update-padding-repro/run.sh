#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${OUT:-/tmp/blender-web-storage-update-padding-repro}"
COMPILER="${CXX:-/usr/bin/clang++-17}"

"$COMPILER" -std=c++17 -O1 -g -fno-omit-frame-pointer -fsanitize=address \
  "$HERE/repro.cc" -o "$OUT"

set +e
ASAN_OPTIONS=abort_on_error=1:detect_leaks=0:symbolize=0 \
  "$OUT" >"$OUT.stdout" 2>"$OUT.stderr"
status=$?
set -e

if [ "$status" -eq 0 ] || ! grep -Fq 'heap-buffer-overflow' "$OUT.stderr"; then
  echo "STORAGE_UPDATE_PADDING_REPRO_FAIL expected ASan heap-buffer-overflow" >&2
  exit 1
fi

echo "STORAGE_UPDATE_PADDING_REPRO_PASS logical=3 attempted=4 asan=heap-buffer-overflow"
