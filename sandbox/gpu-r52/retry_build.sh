#!/opt/homebrew/bin/bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# r52 build retry: lane r53 is actively iterating on wgpu_texture.cc/wgpu_buffer.cc
# (shared checkout), flipping them broken/working. We must NOT touch r53's files, so
# retry the full windowed-opt link until we catch a moment where the shared tree
# compiles; ninja-locked serializes so once our locked build starts with a good
# wgpu_texture.cc.o it links to completion regardless of r53's later edits.
set -uo pipefail
cd /Users/paws/blender-web
export EMSDK_PYTHON=/Users/paws/blender-web/tools/emsdk/python/3.13.3_64bit/bin/python3
WASM=build-wasm-windowed-opt/bin/blender_browser.wasm
# baseline: our source edit time. Success = wasm strictly newer than this marker.
MARK=/tmp/bw_r52_build_marker
touch "$MARK"
for i in $(seq 1 40); do
  echo "=== attempt $i $(date +%H:%M:%S) ==="
  scripts/ninja-locked.sh -C build-wasm-windowed-opt blender_browser > /tmp/bw_r52_ninja.log 2>&1
  rc=$?
  if [ $rc -eq 0 ] && [ "$WASM" -nt "$MARK" ]; then
    echo "BUILD-OK attempt $i $(date +%H:%M:%S) rc=$rc"
    ls -la "$WASM"
    tail -3 /tmp/bw_r52_ninja.log
    exit 0
  fi
  echo "  not yet (rc=$rc); r53 tree transiently broken. tail:"
  grep -m1 "error:" /tmp/bw_r52_ninja.log | head -1
  sleep 25
done
echo "GAVE-UP after 40 attempts"
exit 1
