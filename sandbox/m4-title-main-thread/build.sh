#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/sandbox/m4-title-main-thread"
OUT="$(mktemp -d /tmp/bw-title-main-thread.XXXXXX)"
trap 'rm -rf -- "$OUT"' EXIT

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null
export EM_CACHE="${EM_CACHE:-$ROOT/.ci-cache/emscripten}"
em++ -std=c++17 -pthread -sPROXY_TO_PTHREAD -sPTHREAD_POOL_SIZE=1 -sEXIT_RUNTIME=1 \
  --pre-js "$HERE/pre.js" "$HERE/probe.cc" -o "$OUT/probe.js"
"$EMSDK_NODE" "$OUT/probe.js" >"$OUT/result.txt"
grep -qx \
  'TITLE_MAIN_THREAD_PROBE PASS worker=proxied values=unicode,empty unicode=preserved' \
  "$OUT/result.txt"
