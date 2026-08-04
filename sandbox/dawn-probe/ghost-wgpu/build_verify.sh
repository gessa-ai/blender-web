#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M3.T3 verify: compile GHOST_ContextWGPU against Blender's REAL GHOST headers
# (upstream/intern/ghost) + Dawn, link the monolithic libwebgpu_dawn.a, and run
# a standalone main that obtains a live WGPUDevice through the class. Proves the
# GHOST integration is header-compatible and yields a working device on Metal.
#
#   harness/buildwrap.sh bash sandbox/dawn-probe/ghost-wgpu/build_verify.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
UP="$REPO/upstream"
DAWN_SRC="$REPO/build-dawn/dawn"
DAWN_BUILD="$REPO/build-dawn/probe-build"
OUT="$REPO/build-dawn/ghost-wgpu-verify"
mkdir -p "$OUT"

GHOST_INC="-I$UP/intern/ghost/intern -I$UP/intern/ghost -I$UP/intern/guardedalloc -I$UP/intern/atomic"
DAWN_INC="-I$DAWN_SRC/include -I$DAWN_BUILD/dawn/gen/include"
WEBGPU_LIB="$DAWN_BUILD/dawn/src/dawn/native/libwebgpu_dawn.a"
FW="-framework Cocoa -framework CoreGraphics -framework Foundation \
    -framework IOKit -framework IOSurface -framework Metal -framework QuartzCore"

# Blender's allocator (linked into every real Blender binary; here we compile the
# small self-contained guardedalloc TUs so the standalone verify links).
GUARDED_SRC=$(ls "$UP"/intern/guardedalloc/intern/*.cc)

echo "== compile + link (C++20, -DWITH_WEBGPU_BACKEND) =="
clang++ -std=c++20 -DWITH_WEBGPU_BACKEND $GHOST_INC $DAWN_INC \
  "$HERE/GHOST_ContextWGPU.cc" "$HERE/verify_main.cc" \
  $GUARDED_SRC \
  "$WEBGPU_LIB" $FW \
  -o "$OUT/ghost_wgpu_verify"

echo "== run =="
"$OUT/ghost_wgpu_verify"
