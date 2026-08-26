#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build minizip-ng for wasm, static, -pthread. Version pinned from
# upstream/build_files/build_environment/cmake/versions.cmake (MINIZIPNG_VERSION).
# OpenColorIO dep. Compression methods disabled the same way OCIO/Blender do
# (zlib only) to avoid link errors. Header install path mirrors Blender's
# (include/minizip-ng) because OCIO hardcodes a non-standard include dir.
# Idempotent.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/minizipng"
CACHE="$ROOT/build-deps/_cache"
NPROC="$(getconf _NPROCESSORS_ONLN)"

MINIZIPNG_VERSION="4.0.10"
MINIZIPNG_URL="https://github.com/zlib-ng/minizip-ng/archive/${MINIZIPNG_VERSION}.tar.gz"
MINIZIPNG_MD5="9b4de14db78016419598d0f292fde244"
TARBALL="$CACHE/minizip-ng-${MINIZIPNG_VERSION}.tar.gz"

MARKER="$PREFIX/lib/libminizip.a"
if [ -f "$MARKER" ]; then echo "minizipng: already installed — skip"; exit 0; fi

[ -f "$PREFIX/lib/libz.a" ] || bash "$ROOT/scripts/deps/zlib.sh"

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"
mkdir -p "$CACHE" "$SCRATCH"
[ -f "$TARBALL" ] || curl -fL --retry 3 -o "$TARBALL" "$MINIZIPNG_URL"
GOT="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
[ "$GOT" = "$MINIZIPNG_MD5" ] || { echo "minizipng: MD5 mismatch ($GOT)"; exit 1; }

SRC="$SCRATCH/minizip-ng-${MINIZIPNG_VERSION}"
rm -rf "$SRC"
tar -xzf "$TARBALL" -C "$SCRATCH"

BUILD="$SCRATCH/build"; rm -rf "$BUILD"
emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DBUILD_SHARED_LIBS=OFF \
  -DMZ_FETCH_LIBS=OFF \
  -DMZ_LIBCOMP=OFF \
  -DMZ_PKCRYPT=OFF \
  -DMZ_WZAES=OFF \
  -DMZ_OPENSSL=OFF \
  -DMZ_SIGNING=OFF \
  -DMZ_LZMA=OFF \
  -DMZ_ZSTD=OFF \
  -DMZ_BZIP2=OFF \
  -DMZ_ICONV=OFF \
  -DMZ_ZLIB=ON \
  -DMZ_COMPAT=ON \
  -DZLIB_LIBRARY="$PREFIX/lib/libz.a" \
  -DZLIB_INCLUDE_DIR="$PREFIX/include" \
  -DZLIB_ROOT="$PREFIX" \
  -DCMAKE_INSTALL_INCLUDEDIR="$PREFIX/include/minizip-ng" \
  -DCMAKE_C_FLAGS="-pthread"
emmake cmake --build "$BUILD" --target install -j"$NPROC"

if [ ! -f "$MARKER" ]; then
  # some minizip-ng versions name the archive libminizip-ng.a; symlink to the
  # name OCIO expects.
  ALT="$(ls "$PREFIX"/lib/libminizip*.a 2>/dev/null | head -1)"
  [ -n "$ALT" ] && ln -sf "$(basename "$ALT")" "$MARKER"
fi
[ -f "$MARKER" ] || { echo "minizipng: libminizip.a not installed"; exit 1; }
rm -rf "$SCRATCH"
echo "minizipng ${MINIZIPNG_VERSION}: installed ($MARKER)"
