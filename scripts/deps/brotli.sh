#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build brotli (compression backend for freetype/woff2) for wasm, static,
# -pthread. Version pinned from
# upstream/build_files/build_environment/cmake/versions.cmake (BROTLI_VERSION).
# Required transitively: freetype must be compiled with brotli support
# (FT_REQUIRE_BROTLI=ON) or Blender's check_freetype_for_brotli() FATALs.
# Idempotent.
set -euo pipefail

ROOT="/Users/paws/blender-web"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/brotli"
CACHE="$ROOT/build-deps/_cache"
NPROC="$(sysctl -n hw.ncpu)"

BROTLI_VERSION="1.0.9"
BROTLI_URL="https://github.com/google/brotli/archive/refs/tags/v${BROTLI_VERSION}.tar.gz"
BROTLI_SHA256="f9e8d81d0405ba66d181529af42a3354f838c939095ff99930da6aa9cdf6fe46"
TARBALL="$CACHE/brotli-v${BROTLI_VERSION}.tar.gz"

MARKER="$PREFIX/lib/libbrotlicommon-static.a"
if [ -f "$MARKER" ] && [ -f "$PREFIX/include/brotli/decode.h" ]; then
  echo "brotli: already installed — skip"; exit 0
fi

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"
mkdir -p "$CACHE" "$SCRATCH"
[ -f "$TARBALL" ] || curl -fL --retry 3 -o "$TARBALL" "$BROTLI_URL"
GOT="$(shasum -a 256 "$TARBALL" | awk '{print $1}')"
[ "$GOT" = "$BROTLI_SHA256" ] || { echo "brotli: SHA256 mismatch ($GOT)"; exit 1; }

SRC="$SCRATCH/brotli-${BROTLI_VERSION}"
rm -rf "$SRC"
tar -xzf "$TARBALL" -C "$SCRATCH"

BUILD="$SCRATCH/build"; rm -rf "$BUILD"
emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DBUILD_SHARED_LIBS=OFF \
  -DBROTLI_DISABLE_TESTS=ON \
  -DCMAKE_C_FLAGS="-pthread"
emmake cmake --build "$BUILD" -j"$NPROC"

# brotli 1.0.9 gates its install() rules behind an auto-detected BROTLI_BUNDLED_MODE
# that resolves ON under emcmake, so `--target install` is a no-op / absent. Harvest
# the three static archives + the public headers directly (FindBrotli.cmake needs
# brotlicommon-static + brotlidec-static + brotli/decode.h).
mkdir -p "$PREFIX/lib" "$PREFIX/include/brotli"
cp "$BUILD"/libbrotlicommon-static.a \
   "$BUILD"/libbrotlidec-static.a \
   "$BUILD"/libbrotlienc-static.a "$PREFIX/lib/"
cp "$SRC"/c/include/brotli/*.h "$PREFIX/include/brotli/"

[ -f "$MARKER" ] || { echo "brotli: expected static lib not installed"; exit 1; }
rm -rf "$SCRATCH"
echo "brotli ${BROTLI_VERSION}: installed ($MARKER)"
