#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Build libjpeg-turbo (static, no SIMD) to wasm for blender-web.
# Version pinned to Blender 5.2.0 @ fbe6228777e7:
#   build_files/build_environment/cmake/versions.cmake -> JPEG_VERSION 2.1.3
# SIMD is x86/ARM assembly and cannot compile under wasm -> WITH_SIMD=OFF.
# Idempotent: skips if lib/wasm/lib/libjpeg.a already installed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="$ROOT/lib/wasm"
VERSION="2.1.3"
URL="https://github.com/libjpeg-turbo/libjpeg-turbo/archive/${VERSION}.tar.gz"
MD5="627b980fad0573e08e4c3b80b290fc91"
SCRATCH="$ROOT/build-deps/libjpeg"
SRC="$SCRATCH/libjpeg-turbo-${VERSION}"
BUILD="$SCRATCH/build"
TARBALL="$SCRATCH/libjpeg-turbo-${VERSION}.tar.gz"

if [ -f "$PREFIX/lib/libjpeg.a" ] && [ -f "$PREFIX/include/jpeglib.h" ]; then
  echo "libjpeg $VERSION already installed at $PREFIX -- skip"
  exit 0
fi

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

mkdir -p "$SCRATCH"
if [ ! -d "$SRC" ]; then
  [ -f "$TARBALL" ] || curl -fL --retry 3 -o "$TARBALL" "$URL"
  GOT_MD5="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
  if [ "$GOT_MD5" != "$MD5" ]; then
    echo "libjpeg: MD5 mismatch (got $GOT_MD5 want $MD5)" >&2
    exit 1
  fi
  tar -xzf "$TARBALL" -C "$SCRATCH"
fi

rm -rf "$BUILD"; mkdir -p "$BUILD"; cd "$BUILD"

# -pthread to match platform_wasm link posture; static only; no SIMD; JPEG8 to match Blender.
FLAGS="-pthread -O2"
emcmake cmake "$SRC" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DBUILD_SHARED_LIBS=OFF \
  -DENABLE_SHARED=OFF \
  -DENABLE_STATIC=ON \
  -DWITH_SIMD=OFF \
  -DWITH_JPEG8=ON \
  -DWITH_TURBOJPEG=OFF \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DCMAKE_INSTALL_LIBDIR=lib \
  -DCMAKE_C_FLAGS="$FLAGS"

emmake cmake --build . --target install -j"$(getconf _NPROCESSORS_ONLN)"

# libjpeg-turbo 2.1.3 ships a bundled GNUInstallDirs.cmake that resolves
# CMAKE_INSTALL_LIBDIR into the build tree, so the static archive + cmake
# config land under $BUILD/lib instead of the prefix. Headers/bin/share are
# placed correctly. Harvest the archive (and cmake config) into the prefix.
mkdir -p "$PREFIX/lib/cmake"
cp "$BUILD/lib/libjpeg.a" "$PREFIX/lib/libjpeg.a"
if [ -d "$BUILD/lib/cmake/libjpeg-turbo" ]; then
  cp -R "$BUILD/lib/cmake/libjpeg-turbo" "$PREFIX/lib/cmake/"
  # The exported target's IMPORTED_LOCATION points at the (soon-deleted) build
  # tree because the archive was harvested, not `install`-ed to lib/. Rewrite it
  # to the installed archive so downstream find_package(libjpeg-turbo) CONFIG
  # (OpenImageIO, Blender) resolves a file that actually exists.
  for f in "$PREFIX"/lib/cmake/libjpeg-turbo/libjpeg-turboTargets-*.cmake; do
    [ -f "$f" ] && sed -i "s#${BUILD}/lib/libjpeg.a#${PREFIX}/lib/libjpeg.a#g" "$f"
  done
fi
[ -f "$BUILD/lib/pkgconfig/libjpeg.pc" ] && \
  { mkdir -p "$PREFIX/lib/pkgconfig"; cp "$BUILD/lib/pkgconfig/libjpeg.pc" "$PREFIX/lib/pkgconfig/"; }

if [ ! -f "$PREFIX/lib/libjpeg.a" ]; then
  echo "ERROR: libjpeg.a not produced" >&2
  exit 1
fi

# Clean scratch, keep only installed artifacts.
rm -rf "$SCRATCH"
echo "libjpeg $VERSION installed -> $PREFIX/lib/libjpeg.a"
