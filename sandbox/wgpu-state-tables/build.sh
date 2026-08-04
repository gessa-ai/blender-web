#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M3.T10.pre — build + run the WebGPU state-table harness.
#   DAWN_SRC  Dawn checkout (default: <repo>/build-dawn/dawn — shared with dawn-probe)
#   BUILD     build dir     (default: <repo>/build-dawn/t10pre-build)
# Run through the harness:  harness/buildwrap.sh bash sandbox/wgpu-state-tables/build.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
DAWN_SRC="${DAWN_SRC:-$REPO/build-dawn/dawn}"
BUILD="${BUILD:-$REPO/build-dawn/t10pre-build}"
[ -d "$DAWN_SRC" ] || { echo "ERROR: Dawn checkout not found at $DAWN_SRC" >&2; exit 1; }
PYBIN=""
for cand in /opt/homebrew/bin/python3.13 "$(command -v python3 || true)" /usr/bin/python3; do
  [ -n "$cand" ] || continue
  if "$cand" -c 'import pyexpat, xml.etree.ElementTree' >/dev/null 2>&1; then PYBIN="$cand"; break; fi
done
[ -n "$PYBIN" ] || { echo "ERROR: no python3 with working pyexpat" >&2; exit 1; }
echo "Using Python for Dawn codegen: $PYBIN"
echo "== [1/2] configure + build =="
cmake -G Ninja -S "$HERE" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release \
  -DDAWN_SRC_DIR="$DAWN_SRC" -DPython3_EXECUTABLE="$PYBIN"
ninja -C "$BUILD" wgpu_state_table_test
echo "== [2/2] run harness =="
"$BUILD/wgpu_state_table_test"
