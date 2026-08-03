#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build OpenColorIO for wasm, static, -pthread. Version pinned from
# upstream/build_files/build_environment/cmake/versions.cmake (OPENCOLORIO_VERSION).
#
# OCIO is a HARD dependency of OpenImageIO 3.1 (color_ocio.cpp includes
# <OpenColorIO/OpenColorIO.h> unconditionally — there is no USE_OPENCOLORIO=OFF
# path), so it is on the M1 tier-(a) gtest critical path via OIIO<-blenlib.
# See notes/deps-oiio.md.
#
# No apps/python/nuke/java/docs/tests/GPU; static; SIMD off (wasm stack is
# -pthread only). External deps only (OCIO_INSTALL_EXT_PACKAGES=NONE):
# Imath, yaml-cpp, expat, pystring, minizip-ng, zlib — all from the shared prefix.
# Idempotent.
set -euo pipefail

ROOT="/Users/paws/blender-web"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/opencolorio"
CACHE="$ROOT/build-deps/_cache"
NPROC="$(sysctl -n hw.ncpu)"

OCIO_VERSION="2.5.0"
OCIO_URL="https://github.com/AcademySoftwareFoundation/OpenColorIO/archive/v${OCIO_VERSION}.tar.gz"
OCIO_MD5="41d6b62ac672ed333ebfdcc1108407e0"
TARBALL="$CACHE/OpenColorIO-${OCIO_VERSION}.tar.gz"

CONFIG_MARKER="$PREFIX/lib/cmake/OpenColorIO/OpenColorIOConfig.cmake"
if [ -f "$CONFIG_MARKER" ]; then echo "opencolorio: already installed — skip"; exit 0; fi

# --- prerequisites ---
[ -f "$PREFIX/lib/cmake/Imath/ImathConfig.cmake" ] || bash "$ROOT/scripts/deps/imath.sh"
EXPAT_CFG="$(ls "$PREFIX"/lib/cmake/expat-*/expat-config.cmake 2>/dev/null | head -1)"
[ -n "$EXPAT_CFG" ] || { bash "$ROOT/scripts/deps/expat.sh"; EXPAT_CFG="$(ls "$PREFIX"/lib/cmake/expat-*/expat-config.cmake | head -1)"; }
[ -f "$PREFIX/lib/cmake/yaml-cpp/yaml-cpp-config.cmake" ] || bash "$ROOT/scripts/deps/yamlcpp.sh"
[ -f "$PREFIX/lib/libpystring.a" ] || bash "$ROOT/scripts/deps/pystring.sh"
[ -f "$PREFIX/lib/libminizip.a" ] || bash "$ROOT/scripts/deps/minizipng.sh"
[ -f "$PREFIX/lib/libz.a" ] || bash "$ROOT/scripts/deps/zlib.sh"
EXPAT_DIR="$(dirname "$EXPAT_CFG")"

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"
mkdir -p "$CACHE" "$SCRATCH"
[ -f "$TARBALL" ] || curl -fL --retry 3 -o "$TARBALL" "$OCIO_URL"
GOT="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
[ "$GOT" = "$OCIO_MD5" ] || { echo "opencolorio: MD5 mismatch ($GOT)"; exit 1; }

SRC="$SCRATCH/OpenColorIO-${OCIO_VERSION}"
rm -rf "$SRC"
tar -xzf "$TARBALL" -C "$SCRATCH"

BUILD="$SCRATCH/build"; rm -rf "$BUILD"

# -fexceptions: OCIO throws/catches. CMAKE_FIND_ROOT_PATH lets the module-based
# finders (pystring/minizip) locate archives in the prefix despite the
# emscripten toolchain rooting finds at its own sysroot.
CFLAGS="-pthread -fexceptions"

emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DCMAKE_PREFIX_PATH="$PREFIX" \
  -DCMAKE_FIND_ROOT_PATH="$PREFIX" \
  -DBUILD_SHARED_LIBS=OFF \
  -DOCIO_BUILD_APPS=OFF \
  -DOCIO_BUILD_PYTHON=OFF \
  -DOCIO_BUILD_NUKE=OFF \
  -DOCIO_BUILD_JAVA=OFF \
  -DOCIO_BUILD_DOCS=OFF \
  -DOCIO_BUILD_FROZEN_DOCS=OFF \
  -DOCIO_BUILD_TESTS=OFF \
  -DOCIO_BUILD_GPU_TESTS=OFF \
  -DOCIO_USE_SIMD=OFF \
  -DOCIO_USE_SSE=OFF \
  -DOCIO_INSTALL_EXT_PACKAGES=NONE \
  -DImath_DIR="$PREFIX/lib/cmake/Imath" \
  -Dexpat_DIR="$EXPAT_DIR" \
  -Dexpat_ROOT="$PREFIX" \
  -Dyaml-cpp_DIR="$PREFIX/lib/cmake/yaml-cpp" \
  -Dyaml-cpp_VERSION="0.8.0" \
  -Dpystring_ROOT="$PREFIX" \
  -Dpystring_INCLUDE_DIR="$PREFIX/include" \
  -Dpystring_LIBRARY="$PREFIX/lib/libpystring.a" \
  -Dminizip-ng_ROOT="$PREFIX" \
  -Dminizip-ng_INCLUDE_DIR="$PREFIX/include/minizip-ng/minizip" \
  -Dminizip-ng_LIBRARY="$PREFIX/lib/libminizip.a" \
  -Dminizip_LIBRARY="$PREFIX/lib/libminizip.a" \
  -DZLIB_ROOT="$PREFIX" \
  -DZLIB_INCLUDE_DIR="$PREFIX/include" \
  -DZLIB_LIBRARY="$PREFIX/lib/libz.a" \
  -DCMAKE_C_FLAGS="$CFLAGS" \
  -DCMAKE_CXX_FLAGS="$CFLAGS"

emmake cmake --build "$BUILD" --target install -j"$NPROC"

[ -f "$CONFIG_MARKER" ] || { echo "opencolorio: config not installed ($CONFIG_MARKER)"; exit 1; }
rm -rf "$SCRATCH"
echo "opencolorio ${OCIO_VERSION}: installed ($CONFIG_MARKER)"
