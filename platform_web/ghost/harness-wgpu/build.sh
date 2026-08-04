#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build the standalone in-tab WebGPU harness: GHOST_ContextWGPUWeb + the triangle/
# readback test, against emdawnwebgpu (--use-port=emdawnwebgpu — the port proven in
# the m0 harness). Single-threaded; needs a WebGPU-capable browser to RUN.
#
# Usage: platform_web/ghost/harness-wgpu/build.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
WEB="$ROOT/platform_web/ghost"
OUT="$WEB/harness-wgpu/build"
mkdir -p "$OUT"

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

emcc \
  -std=c++17 -O1 -g2 --profiling-funcs -fexceptions \
  --use-port=emdawnwebgpu \
  -I"$WEB" \
  "$WEB/GHOST_ContextWGPUWeb.cc" \
  "$WEB/harness-wgpu/test_wgpu_web.cc" \
  -sMODULARIZE=1 -sEXPORT_NAME=createWgpuTest \
  -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=0 -sASYNCIFY=0 \
  -o "$OUT/wgpu_web_test.js"

echo "built: $OUT/wgpu_web_test.js ($(du -h "$OUT/wgpu_web_test.wasm" | cut -f1) wasm)"
