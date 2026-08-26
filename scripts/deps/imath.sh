#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build Imath (base of the OpenEXR stack) for wasm, static, -pthread.
# Version pinned from upstream/build_files/build_environment/cmake/versions.cmake.
# Installs to the shared prefix lib/wasm and exports a CMake config package
# (lib/wasm/lib/cmake/Imath) so OpenEXR can find_package(Imath CONFIG).
# Idempotent: re-running is a no-op once the config package is present.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/imath"
CACHE="$ROOT/build-deps/_cache"

IMATH_VERSION="3.2.2"
IMATH_URL="https://github.com/AcademySoftwareFoundation/Imath/archive/v${IMATH_VERSION}.tar.gz"
IMATH_MD5="e29f25ce926ac53d8e0a52197299f61b"
TARBALL="$CACHE/imath-${IMATH_VERSION}.tar.gz"

CONFIG_MARKER="$PREFIX/lib/cmake/Imath/ImathConfig.cmake"
if [ -f "$CONFIG_MARKER" ]; then
  echo "imath: already installed ($CONFIG_MARKER) — skip"
  exit 0
fi

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"

mkdir -p "$CACHE" "$SCRATCH"

# --- download (cached) + verify ---
if [ ! -f "$TARBALL" ]; then
  curl -fL --retry 3 -o "$TARBALL" "$IMATH_URL"
fi
GOT_MD5="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
if [ "$GOT_MD5" != "$IMATH_MD5" ]; then
  echo "imath: MD5 mismatch (got $GOT_MD5 want $IMATH_MD5)" >&2
  exit 1
fi

# --- extract ---
SRC="$SCRATCH/Imath-${IMATH_VERSION}"
rm -rf "$SRC"
tar -xzf "$TARBALL" -C "$SCRATCH"

# --- configure (static, -pthread, matches platform_wasm.cmake) ---
BUILD="$SCRATCH/build"
rm -rf "$BUILD"
emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DBUILD_SHARED_LIBS=OFF \
  -DBUILD_TESTING=OFF \
  -DIMATH_INSTALL_PKG_CONFIG=ON \
  -DCMAKE_C_FLAGS="-pthread" \
  -DCMAKE_CXX_FLAGS="-pthread"

# --- build + install ---
emmake cmake --build "$BUILD" --target install -j"$(getconf _NPROCESSORS_ONLN)"

# --- verify config package landed ---
if [ ! -f "$CONFIG_MARKER" ]; then
  echo "imath: install did not produce $CONFIG_MARKER" >&2
  exit 1
fi

# --- tiny link test: compile+link a TU that uses Imath through emcc ---
VDIR="$SCRATCH/verify"
mkdir -p "$VDIR"
cat > "$VDIR/t.cpp" <<'EOF'
#include <Imath/ImathVec.h>
#include <Imath/half.h>
int main() {
  Imath::V3f a(1.f, 2.f, 3.f), b(4.f, 5.f, 6.f);
  half h(a.dot(b));
  return (float(h) > 0.f) ? 0 : 1;
}
EOF
IMATH_INC="$PREFIX/include"
IMATH_LIB="$(ls "$PREFIX"/lib/libImath*.a | head -1)"
em++ -pthread -std=c++17 -I"$IMATH_INC" "$VDIR/t.cpp" "$IMATH_LIB" -o "$VDIR/t.js"
test -f "$VDIR/t.wasm"
echo "imath: verify link OK ($IMATH_LIB)"

# --- clean scratch, keep only installed artifacts ---
rm -rf "$SCRATCH"
echo "imath ${IMATH_VERSION}: installed to $PREFIX (config: lib/cmake/Imath)"
