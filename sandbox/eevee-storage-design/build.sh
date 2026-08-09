#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# r48 - build + run the EEVEE storage-texture BGL acceptance probe.
# Reuses the pinned Dawn checkout (build-dawn/dawn). Builds in an ISOLATED dir
# (build-dawn/eevee-storage-probe-build) so it never touches build-native-gpu or
# the other lane's census tree. The ninja step is serialized via ninja-locked.sh.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
DAWN_SRC="${DAWN_SRC:-$REPO/build-dawn/dawn}"
BUILD="${BUILD:-$REPO/build-dawn/eevee-storage-probe-build}"

[ -d "$DAWN_SRC" ] || { echo "ERROR: Dawn checkout not found at $DAWN_SRC" >&2; exit 1; }

PYBIN=""
for cand in /opt/homebrew/bin/python3.13 "$(command -v python3 || true)" /usr/bin/python3; do
  [ -n "$cand" ] || continue
  if "$cand" -c 'import pyexpat, xml.etree.ElementTree' >/dev/null 2>&1; then PYBIN="$cand"; break; fi
done
[ -n "$PYBIN" ] || { echo "ERROR: no python3 with working pyexpat" >&2; exit 1; }
echo "Using Python for Dawn codegen: $PYBIN"

mkdir -p "$BUILD"
cmake -G Ninja -S "$HERE" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DPython3_EXECUTABLE="$PYBIN"

if [ -x "$REPO/scripts/ninja-locked.sh" ]; then
  "$REPO/scripts/ninja-locked.sh" -C "$BUILD" eevee_storage_probe
else
  ninja -C "$BUILD" eevee_storage_probe
fi

echo "== run =="
"$BUILD/eevee_storage_probe"
