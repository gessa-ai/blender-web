#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build libexpat for wasm, static, -pthread. Version pinned from
# upstream/build_files/build_environment/cmake/versions.cmake (EXPAT_VERSION).
# OpenColorIO dep. Idempotent.
set -euo pipefail

ROOT="/Users/paws/blender-web"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/expat"
CACHE="$ROOT/build-deps/_cache"
NPROC="$(sysctl -n hw.ncpu)"

EXPAT_TAG="R_2_7_5"
EXPAT_URL="https://github.com/libexpat/libexpat/archive/${EXPAT_TAG}.tar.gz"
EXPAT_MD5="aecc4366ab1a5189d8f027c369305c9a"
TARBALL="$CACHE/libexpat-${EXPAT_TAG}.tar.gz"

CONFIG_MARKER="$PREFIX/lib/cmake/expat-2.7.5/expat-config.cmake"
if [ -f "$CONFIG_MARKER" ]; then
  echo "expat: already installed — skip"; exit 0
fi

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"
mkdir -p "$CACHE" "$SCRATCH"
[ -f "$TARBALL" ] || curl -fL --retry 3 -o "$TARBALL" "$EXPAT_URL"
GOT="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
[ "$GOT" = "$EXPAT_MD5" ] || { echo "expat: MD5 mismatch ($GOT)"; exit 1; }

SRC="$SCRATCH/libexpat-${EXPAT_TAG}/expat"
rm -rf "$SCRATCH/libexpat-${EXPAT_TAG}"
tar -xzf "$TARBALL" -C "$SCRATCH"

BUILD="$SCRATCH/build"; rm -rf "$BUILD"
emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DBUILD_SHARED_LIBS=OFF \
  -DEXPAT_SHARED_LIBS=OFF \
  -DEXPAT_BUILD_TOOLS=OFF \
  -DEXPAT_BUILD_EXAMPLES=OFF \
  -DEXPAT_BUILD_TESTS=OFF \
  -DEXPAT_BUILD_DOCS=OFF \
  -DEXPAT_BUILD_PKGCONFIG=ON \
  -DCMAKE_C_FLAGS="-pthread"
emmake cmake --build "$BUILD" --target install -j"$NPROC"

# expat installs its config under lib/cmake/expat-<version>/
CFG="$(ls "$PREFIX"/lib/cmake/expat-*/expat-config.cmake 2>/dev/null | head -1)"
[ -n "$CFG" ] || { echo "expat: no config installed"; exit 1; }
rm -rf "$SCRATCH"
echo "expat 2.7.5: installed ($CFG)"
