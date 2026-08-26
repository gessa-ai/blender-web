#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build libtiff for wasm, static, -pthread. Version pinned from
# upstream/build_files/build_environment/cmake/versions.cmake (TIFF_VERSION).
# Args mirror upstream tiff.cmake: explicit ZLIB + JPEG from the shared prefix,
# every optional codec off (lzma/jbig/zstd/webp/lerc). ZIP compression goes
# through zlib (libdeflate stays off, matching upstream tiff.cmake which passes
# no -Dlibdeflate). Needed by OIIO (REQUIRED_DEP).
# Idempotent: no-op once lib/wasm/lib/libtiff.a is present.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/libtiff"
CACHE="$ROOT/build-deps/_cache"
NPROC="$(getconf _NPROCESSORS_ONLN)"

TIFF_VERSION="4.7.1"
TIFF_URL="https://download.osgeo.org/libtiff/tiff-${TIFF_VERSION}.tar.gz"
TIFF_MD5="f1044dd3b4466cc53464210148e08146"
TARBALL="$CACHE/tiff-${TIFF_VERSION}.tar.gz"

LIB_MARKER="$PREFIX/lib/libtiff.a"
if [ -f "$LIB_MARKER" ]; then
  echo "libtiff: already installed ($LIB_MARKER) — skip"
  exit 0
fi

# --- prerequisites (zlib + jpeg) must exist in the prefix ---
MISSING=""
[ -f "$PREFIX/lib/libz.a" ]    || MISSING="$MISSING zlib"
[ -f "$PREFIX/lib/libjpeg.a" ] || MISSING="$MISSING jpeg"
if [ -n "$MISSING" ]; then
  echo "libtiff: BLOCKED — missing prerequisite(s) in prefix:$MISSING (build them first)" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"

mkdir -p "$CACHE" "$SCRATCH"

if [ ! -f "$TARBALL" ]; then
  curl -fL --retry 3 -o "$TARBALL" "$TIFF_URL"
fi
GOT_MD5="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
if [ "$GOT_MD5" != "$TIFF_MD5" ]; then
  echo "libtiff: MD5 mismatch (got $GOT_MD5 want $TIFF_MD5)" >&2
  exit 1
fi

SRC="$SCRATCH/tiff-${TIFF_VERSION}"
rm -rf "$SRC"
tar -xzf "$TARBALL" -C "$SCRATCH"

BUILD="$SCRATCH/build"
rm -rf "$BUILD"
emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DCMAKE_PREFIX_PATH="$PREFIX" \
  -DBUILD_SHARED_LIBS=OFF \
  -Dtiff-static=ON \
  -Dtiff-tools=OFF \
  -Dtiff-tests=OFF \
  -Dtiff-contrib=OFF \
  -Dtiff-docs=OFF \
  -Dsphinx=OFF \
  -DZLIB_LIBRARY="$PREFIX/lib/libz.a" \
  -DZLIB_INCLUDE_DIR="$PREFIX/include" \
  -DJPEG_LIBRARY="$PREFIX/lib/libjpeg.a" \
  -DJPEG_INCLUDE_DIR="$PREFIX/include" \
  -Dlzma=OFF \
  -Djbig=OFF \
  -Dzstd=OFF \
  -Dwebp=OFF \
  -Dlerc=OFF \
  -DCMAKE_C_FLAGS="-pthread" \
  -DCMAKE_CXX_FLAGS="-pthread"

emmake cmake --build "$BUILD" --target install -j"$NPROC"

if [ ! -f "$LIB_MARKER" ]; then
  echo "libtiff: install did not produce $LIB_MARKER" >&2
  exit 1
fi

# --- link test: compile+link a TU using the libtiff API through emcc ---
VDIR="$SCRATCH/verify"
mkdir -p "$VDIR"
cat > "$VDIR/t.c" <<'EOF'
#include <tiffio.h>
#include <string.h>
int main(void) {
  const char *v = TIFFGetVersion();
  return (v && strstr(v, "4.7")) ? 0 : 1;
}
EOF
DEFLATE_LIB=""
[ -f "$PREFIX/lib/libdeflate.a" ] && DEFLATE_LIB="$PREFIX/lib/libdeflate.a"
emcc -pthread -I"$PREFIX/include" "$VDIR/t.c" \
  "$PREFIX/lib/libtiff.a" "$PREFIX/lib/libjpeg.a" "$PREFIX/lib/libz.a" $DEFLATE_LIB \
  -o "$VDIR/t.js"
test -f "$VDIR/t.wasm"
echo "libtiff: verify link OK"

rm -rf "$SCRATCH"
echo "libtiff ${TIFF_VERSION}: installed to $PREFIX (libtiff.a)"
