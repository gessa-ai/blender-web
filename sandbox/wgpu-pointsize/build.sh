#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M3.pointsize.pre — build + run the gl_PointSize expansion prototype.
#   DAWN_SRC  Dawn checkout (default: <repo>/build-dawn/dawn)
#   LIBDIR    Blender libs  (default: <repo>/lib/macos_arm64 — has shaderc/)
#   BUILD     build dir     (default: <repo>/build-dawn/pointsize-build)
# Run:  harness/buildwrap.sh bash sandbox/wgpu-pointsize/build.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
DAWN_SRC="${DAWN_SRC:-$REPO/build-dawn/dawn}"
LIBDIR="${LIBDIR:-$REPO/lib/macos_arm64}"
BUILD="${BUILD:-$REPO/build-dawn/pointsize-build}"
[ -d "$DAWN_SRC" ] || { echo "ERROR: Dawn checkout not found at $DAWN_SRC" >&2; exit 1; }
[ -f "$LIBDIR/shaderc/include/shaderc/shaderc.hpp" ] || { echo "ERROR: shaderc not under $LIBDIR" >&2; exit 1; }
PYBIN=""
for cand in /opt/homebrew/bin/python3.13 "$(command -v python3 || true)" /usr/bin/python3; do
  [ -n "$cand" ] || continue
  if "$cand" -c 'import pyexpat, xml.etree.ElementTree' >/dev/null 2>&1; then PYBIN="$cand"; break; fi
done
[ -n "$PYBIN" ] || { echo "ERROR: no python3 with working pyexpat" >&2; exit 1; }
echo "Using Python for Dawn codegen: $PYBIN"
echo "== [1/2] configure + build =="
cmake -G Ninja -S "$HERE" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release \
  -DDAWN_SRC_DIR="$DAWN_SRC" -DLIBDIR="$LIBDIR" -DPython3_EXECUTABLE="$PYBIN"
ninja -C "$BUILD" wgpu_pointsize_test
echo "== [2/2] run prototype =="
"$BUILD/wgpu_pointsize_test"
