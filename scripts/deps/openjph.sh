#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build OpenJPH (HTJ2K codec used by OpenEXR 3.4 core) for wasm, static, -pthread.
# Version pinned from upstream/build_files/build_environment/cmake/versions.cmake
# (OPENJPH_VERSION). OpenEXR links openjph PRIVATE, so it must exist as a
# discoverable installed static archive (the vendored copy is EXCLUDE_FROM_ALL
# and never installed) — hence we build+install it externally, exactly as
# Blender's superbuild does, and pass openjph_DIR to OpenEXR.
# SIMD disabled for a portable generic build matching the -pthread-only stack.
# Installs a CMake config package (lib/wasm/lib/cmake/openjph).
# Idempotent: no-op once the config package is present.
set -euo pipefail

ROOT="/Users/paws/blender-web"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/openjph"
CACHE="$ROOT/build-deps/_cache"

OPENJPH_VERSION="0.25.2"
OPENJPH_URL="https://github.com/aous72/OpenJPH/archive/refs/tags/${OPENJPH_VERSION}.tar.gz"
OPENJPH_SHA256="ae5f09562cb811cb2fb881c5eb74583e18db941848cfa3c35787e2580f3defc6"
TARBALL="$CACHE/openjph-${OPENJPH_VERSION}.tar.gz"

# openjph installs its config dir as lib/cmake/openjph
CONFIG_MARKER="$PREFIX/lib/cmake/openjph/openjph-config.cmake"
if [ -f "$CONFIG_MARKER" ]; then
  echo "openjph: already installed ($CONFIG_MARKER) — skip"
  exit 0
fi

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"

mkdir -p "$CACHE" "$SCRATCH"

if [ ! -f "$TARBALL" ]; then
  curl -fL --retry 3 -o "$TARBALL" "$OPENJPH_URL"
fi
GOT_SHA="$(shasum -a256 "$TARBALL" | awk '{print $1}')"
if [ "$GOT_SHA" != "$OPENJPH_SHA256" ]; then
  echo "openjph: SHA256 mismatch (got $GOT_SHA want $OPENJPH_SHA256)" >&2
  exit 1
fi

SRC="$SCRATCH/OpenJPH-${OPENJPH_VERSION}"
rm -rf "$SRC"
tar -xzf "$TARBALL" -C "$SCRATCH"

BUILD="$SCRATCH/build"
rm -rf "$BUILD"
# OpenJPH's CMake auto-forces BUILD_SHARED_LIBS=OFF and TIFF=OFF under EMSCRIPTEN.
# OJPH_DISABLE_SIMD=ON => no -msimd128 (keeps the generic wasm codepath).
emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DBUILD_SHARED_LIBS=OFF \
  -DOJPH_DISABLE_SIMD=ON \
  -DOJPH_BUILD_EXECUTABLES=OFF \
  -DOJPH_BUILD_TESTS=OFF \
  -DOJPH_ENABLE_TIFF_SUPPORT=OFF \
  -DCMAKE_C_FLAGS="-pthread" \
  -DCMAKE_CXX_FLAGS="-pthread"

emmake cmake --build "$BUILD" --target install -j"$(sysctl -n hw.ncpu)"

if [ ! -f "$CONFIG_MARKER" ]; then
  echo "openjph: install did not produce $CONFIG_MARKER" >&2
  echo "openjph: cmake dir contents:" >&2
  ls -la "$PREFIX/lib/cmake/openjph" 2>/dev/null >&2 || true
  exit 1
fi

rm -rf "$SCRATCH"
echo "openjph ${OPENJPH_VERSION}: installed to $PREFIX (config: lib/cmake/openjph)"
