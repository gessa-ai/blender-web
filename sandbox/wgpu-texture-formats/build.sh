#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M3.T9.pre — build + run the WebGPU texture-format + data-conversion harness.
#
# Env overrides:
#   DAWN_SRC  Dawn checkout (default: <repo>/build-dawn/dawn — shared with dawn-probe)
#   BUILD     build dir     (default: <repo>/build-dawn/t9pre-build)
#
# Run through the harness so logs stay off-context:
#   harness/buildwrap.sh bash sandbox/wgpu-texture-formats/build.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
DAWN_SRC="${DAWN_SRC:-$REPO/build-dawn/dawn}"
BUILD="${BUILD:-$REPO/build-dawn/t9pre-build}"

if [ ! -d "$DAWN_SRC" ]; then
  echo "ERROR: Dawn checkout not found at $DAWN_SRC" >&2
  echo "  git clone --depth 1 --branch chromium/7989 https://dawn.googlesource.com/dawn \"$DAWN_SRC\"" >&2
  exit 1
fi

# Dawn's SPIRV-Tools codegen needs a Python whose pyexpat loads (see dawn-probe).
PYBIN=""
for cand in /opt/homebrew/bin/python3.13 "$(command -v python3 || true)" /usr/bin/python3; do
  [ -n "$cand" ] || continue
  if "$cand" -c 'import pyexpat, xml.etree.ElementTree' >/dev/null 2>&1; then
    PYBIN="$cand"; break
  fi
done
if [ -z "$PYBIN" ]; then
  echo "ERROR: no python3 with a working pyexpat found (needed by Dawn codegen)" >&2
  exit 1
fi
echo "Using Python for Dawn codegen: $PYBIN"

echo "== [1/2] configure + build (Dawn via add_subdirectory) =="
cmake -G Ninja -S "$HERE" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DPython3_EXECUTABLE="$PYBIN"
ninja -C "$BUILD" wgpu_texture_format_test

echo "== [2/2] run harness =="
"$BUILD/wgpu_texture_format_test"
