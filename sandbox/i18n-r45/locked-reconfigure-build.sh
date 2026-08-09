#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# r45 Phase 2: reconfigure build-wasm-windowed-opt with WITH_INTERNATIONAL=ON and relink
# blender_browser, holding the shared ninja lock across BOTH the cmake reconfigure (which
# regenerates build.ninja) and the ninja build, so a concurrent gpu-lane ninja never reads
# a half-written build.ninja. Same lock file as scripts/ninja-locked.sh.
set -uo pipefail
ROOT="/Users/paws/blender-web"
cd "$ROOT"
export EMSDK_PYTHON="$ROOT/tools/emsdk/python/3.13.3_64bit/bin/python3"
LOCK="/tmp/blender-web-ninja.lock"
STALE=3600

acquire() {
  while ! mkdir "$LOCK" 2>/dev/null; do
    if [ -f "$LOCK/pid" ]; then
      PID=$(cat "$LOCK/pid" 2>/dev/null || echo "")
      NOW=$(date +%s); TS=$(cat "$LOCK/ts" 2>/dev/null || echo "$NOW")
      if [ -n "$PID" ] && ! kill -0 "$PID" 2>/dev/null; then
        echo "[locked] removing stale lock (dead pid $PID)"; rm -rf "$LOCK"; continue
      fi
      if [ $((NOW - TS)) -gt $STALE ]; then
        echo "[locked] removing stale lock (age > ${STALE}s)"; rm -rf "$LOCK"; continue
      fi
    fi
    echo "[locked] waiting for ninja lock (gpu lane building)..."; sleep 5
  done
  echo "$$" > "$LOCK/pid"; date +%s > "$LOCK/ts"
}

acquire
trap 'rm -rf "$LOCK"' EXIT INT TERM
echo "[locked] lock acquired (pid $$)"

echo "[locked] === reconfigure (WITH_INTERNATIONAL ON) ==="
BLENDER_WEB_WINDOWED=1 cmake -S upstream -B build-wasm-windowed-opt -G Ninja \
  -C patches/blender_web.cmake \
  -DCMAKE_TOOLCHAIN_FILE="$ROOT/tools/emsdk/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake" \
  -DCMAKE_BUILD_TYPE=Release -DWITH_BLENDER_WEB_BROWSER=ON -DCMAKE_EXE_LINKER_FLAGS=-g0
echo "[locked] reconfigure rc=$?"
echo "[locked] cache WITH_INTERNATIONAL now: $(grep 'WITH_INTERNATIONAL:' build-wasm-windowed-opt/CMakeCache.txt)"
date +%s > "$LOCK/ts"

echo "[locked] === ninja blender_browser ==="
ninja -C build-wasm-windowed-opt blender_browser
rc=$?
echo "[locked] ninja rc=$rc"
echo "[locked] === post-build payload ==="
ls -la build-wasm-windowed-opt/bin/blender_browser.data 2>/dev/null | awk '{print "data:", $5}'
exit $rc
