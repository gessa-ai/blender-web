#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build FreeType for wasm, static, -pthread, WITH BROTLI (mandatory: Blender's
# platform check_freetype_for_brotli() FATALs otherwise via check_symbol_exists
# on FT_CONFIG_OPTION_USE_BROTLI). Version + build flags pinned from
# upstream/build_files/build_environment/cmake/{versions,freetype}.cmake.
# Links against our lib/wasm zlib (1.3.1) and brotli (1.0.9). Idempotent.
set -euo pipefail

ROOT="/Users/paws/blender-web"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/freetype"
CACHE="$ROOT/build-deps/_cache"
NPROC="$(sysctl -n hw.ncpu)"

FT_VERSION="2.13.3"
FT_URL="https://downloads.sourceforge.net/project/freetype/freetype2/${FT_VERSION}/freetype-${FT_VERSION}.tar.gz"
FT_MD5="ac1f0b517f62bd40d50bc995faa5741d"
TARBALL="$CACHE/freetype-${FT_VERSION}.tar.gz"

MARKER="$PREFIX/lib/libfreetype.a"
if [ -f "$MARKER" ] && [ -f "$PREFIX/include/freetype2/freetype/config/ftconfig.h" ]; then
  echo "freetype: already installed — skip"; exit 0
fi

# brotli + zlib are prerequisites.
[ -f "$PREFIX/lib/libbrotlicommon-static.a" ] || { echo "freetype: brotli missing (run brotli.sh first)"; exit 1; }
[ -f "$PREFIX/lib/libz.a" ] || { echo "freetype: zlib missing (run zlib.sh first)"; exit 1; }

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"
mkdir -p "$CACHE" "$SCRATCH"
[ -f "$TARBALL" ] || curl -fL --retry 3 -o "$TARBALL" "$FT_URL"
GOT="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
[ "$GOT" = "$FT_MD5" ] || { echo "freetype: MD5 mismatch ($GOT)"; exit 1; }

SRC="$SCRATCH/freetype-${FT_VERSION}"
rm -rf "$SRC"
tar -xzf "$TARBALL" -C "$SCRATCH"

BUILD="$SCRATCH/build"; rm -rf "$BUILD"
emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DBUILD_SHARED_LIBS=OFF \
  -DFT_DISABLE_BZIP2=ON \
  -DFT_DISABLE_HARFBUZZ=ON \
  -DFT_DISABLE_PNG=ON \
  -DFT_REQUIRE_BROTLI=ON \
  -DFT_REQUIRE_ZLIB=ON \
  -DBROTLIDEC_INCLUDE_DIRS="$PREFIX/include" \
  -DBROTLIDEC_LIBRARIES="$PREFIX/lib/libbrotlidec-static.a;$PREFIX/lib/libbrotlicommon-static.a" \
  -DZLIB_LIBRARY="$PREFIX/lib/libz.a" \
  -DZLIB_INCLUDE_DIR="$PREFIX/include" \
  -DCMAKE_C_FLAGS="-pthread"
emmake cmake --build "$BUILD" --target install -j"$NPROC"

[ -f "$MARKER" ] || { echo "freetype: libfreetype.a not installed"; exit 1; }
# Sanity: brotli option must be baked into the installed ftoption.h/ftconfig.h.
grep -rq 'FT_CONFIG_OPTION_USE_BROTLI' "$PREFIX/include/freetype2/freetype/config/" \
  || { echo "freetype: FT_CONFIG_OPTION_USE_BROTLI not enabled"; exit 1; }
rm -rf "$SCRATCH"
echo "freetype ${FT_VERSION}: installed ($MARKER, brotli enabled)"
