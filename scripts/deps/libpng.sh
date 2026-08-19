#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Build libpng (static) to wasm for blender-web.
# Version pinned to Blender 5.2.0 @ fbe6228777e7:
#   build_files/build_environment/cmake/versions.cmake -> PNG_VERSION 1.6.58
# Depends on zlib (lib/wasm/lib/libz.a, built by the zlib worker).
# Hardware optimizations (Intel SSE / ARM NEON intrinsics) are disabled: no SIMD under wasm.
# Idempotent: skips if lib/wasm/lib/libpng16.a already installed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="$ROOT/lib/wasm"
VERSION="1.6.58"
# Pinned sourceforge URI (versions.cmake) first, github release as fallback.
URL_PRIMARY="https://download.sourceforge.net/libpng/libpng-${VERSION}.tar.xz"
URL_FALLBACK="https://github.com/pnggroup/libpng/releases/download/v${VERSION}/libpng-${VERSION}.tar.xz"
SHA256="28eb403f51f0f7405249132cecfe82ea5c0ef97f1b32c5a65828814ae0d34775"
SCRATCH="$ROOT/build-deps/libpng"
SRC="$SCRATCH/libpng-${VERSION}"
BUILD="$SCRATCH/build"
TARBALL="$SCRATCH/libpng-${VERSION}.tar.xz"

if [ -f "$PREFIX/lib/libpng16.a" ] && [ -f "$PREFIX/include/png.h" ]; then
  echo "libpng $VERSION already installed at $PREFIX -- skip"
  exit 0
fi

if [ ! -f "$PREFIX/lib/libz.a" ] || [ ! -f "$PREFIX/include/zlib.h" ]; then
  echo "ERROR: zlib not present at $PREFIX (libz.a/zlib.h) -- libpng needs it; sequence zlib first" >&2
  exit 2
fi

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

mkdir -p "$SCRATCH"
if [ ! -d "$SRC" ]; then
  [ -f "$TARBALL" ] || curl -fL --retry 3 -o "$TARBALL" "$URL_PRIMARY" || \
    curl -fL --retry 3 -o "$TARBALL" "$URL_FALLBACK"
  GOT_SHA256="$(shasum -a 256 "$TARBALL" 2>/dev/null | awk '{print $1}' || \
    sha256sum "$TARBALL" | awk '{print $1}')"
  if [ "$GOT_SHA256" != "$SHA256" ]; then
    echo "libpng: SHA256 mismatch (got $GOT_SHA256 want $SHA256)" >&2
    exit 1
  fi
  tar -xf "$TARBALL" -C "$SCRATCH"
fi

rm -rf "$BUILD"; mkdir -p "$BUILD"; cd "$BUILD"

FLAGS="-pthread -O2"
emcmake cmake "$SRC" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DBUILD_SHARED_LIBS=OFF \
  -DPNG_SHARED=OFF \
  -DPNG_STATIC=ON \
  -DPNG_FRAMEWORK=OFF \
  -DPNG_TESTS=OFF \
  -DPNG_TOOLS=OFF \
  -DPNG_HARDWARE_OPTIMIZATIONS=OFF \
  -DZLIB_LIBRARY="$PREFIX/lib/libz.a" \
  -DZLIB_INCLUDE_DIR="$PREFIX/include" \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DCMAKE_INSTALL_LIBDIR=lib \
  -DCMAKE_C_FLAGS="$FLAGS"

emmake cmake --build . --target install -j"$(getconf _NPROCESSORS_ONLN)"

# Ensure a plain libpng.a alias exists next to the versioned archive.
if [ -f "$PREFIX/lib/libpng16.a" ] && [ ! -e "$PREFIX/lib/libpng.a" ]; then
  cp "$PREFIX/lib/libpng16.a" "$PREFIX/lib/libpng.a"
fi

if [ ! -f "$PREFIX/lib/libpng16.a" ]; then
  echo "ERROR: libpng16.a not produced" >&2
  exit 1
fi

rm -rf "$SCRATCH"
echo "libpng $VERSION installed -> $PREFIX/lib/libpng16.a"
