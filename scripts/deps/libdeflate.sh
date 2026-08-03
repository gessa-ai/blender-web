#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build libdeflate (OpenEXR 3.4 compression backend, replaces zlib in EXR core)
# for wasm, static, -pthread. Version pinned from
# upstream/build_files/build_environment/cmake/versions.cmake (DEFLATE_VERSION).
# Installs to shared prefix lib/wasm with a CMake config package
# (lib/wasm/lib/cmake/libdeflate) so OpenEXR can find_package(libdeflate CONFIG).
# Idempotent: no-op once the config package is present.
set -euo pipefail

ROOT="/Users/paws/blender-web"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/libdeflate"
CACHE="$ROOT/build-deps/_cache"

DEFLATE_VERSION="1.18"
DEFLATE_URL="https://github.com/ebiggers/libdeflate/archive/refs/tags/v${DEFLATE_VERSION}.tar.gz"
DEFLATE_MD5="a29d9dd653cbe03f2d5cd83972063f9e"
TARBALL="$CACHE/libdeflate-${DEFLATE_VERSION}.tar.gz"

CONFIG_MARKER="$PREFIX/lib/cmake/libdeflate/libdeflate-config.cmake"
if [ -f "$CONFIG_MARKER" ]; then
  echo "libdeflate: already installed ($CONFIG_MARKER) — skip"
  exit 0
fi

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"

mkdir -p "$CACHE" "$SCRATCH"

if [ ! -f "$TARBALL" ]; then
  curl -fL --retry 3 -o "$TARBALL" "$DEFLATE_URL"
fi
GOT_MD5="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
if [ "$GOT_MD5" != "$DEFLATE_MD5" ]; then
  echo "libdeflate: MD5 mismatch (got $GOT_MD5 want $DEFLATE_MD5)" >&2
  exit 1
fi

SRC="$SCRATCH/libdeflate-${DEFLATE_VERSION}"
rm -rf "$SRC"
tar -xzf "$TARBALL" -C "$SCRATCH"

BUILD="$SCRATCH/build"
rm -rf "$BUILD"
emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DLIBDEFLATE_BUILD_STATIC_LIB=ON \
  -DLIBDEFLATE_BUILD_SHARED_LIB=OFF \
  -DLIBDEFLATE_BUILD_GZIP=OFF \
  -DLIBDEFLATE_BUILD_TESTS=OFF \
  -DCMAKE_C_FLAGS="-pthread" \
  -DCMAKE_CXX_FLAGS="-pthread"

emmake cmake --build "$BUILD" --target install -j"$(sysctl -n hw.ncpu)"

if [ ! -f "$CONFIG_MARKER" ]; then
  echo "libdeflate: install did not produce $CONFIG_MARKER" >&2
  exit 1
fi

rm -rf "$SCRATCH"
echo "libdeflate ${DEFLATE_VERSION}: installed to $PREFIX (config: lib/cmake/libdeflate)"
