#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build OpenEXR for wasm, static, -pthread. Version pinned from
# upstream/build_files/build_environment/cmake/versions.cmake (OPENEXR_VERSION).
# find_package(Imath CONFIG) resolves from the shared prefix; OpenEXR 3.4 core
# also needs libdeflate (its zlib replacement) and openjph (HTJ2K codec) — both
# built+installed externally (see scripts/deps/{libdeflate,openjph}.sh) and passed
# by *_DIR so they are discoverable static archives (OpenEXR links them PUBLIC in
# the static case; the vendored copies are EXCLUDE_FROM_ALL and never installed).
# Installs a CMake config package (lib/wasm/lib/cmake/OpenEXR) for OIIO/Blender.
# Idempotent: no-op once the config package is present.
set -euo pipefail

ROOT="/Users/paws/blender-web"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/openexr"
CACHE="$ROOT/build-deps/_cache"
NPROC="$(sysctl -n hw.ncpu)"

OPENEXR_VERSION="3.4.10"
OPENEXR_URL="https://github.com/AcademySoftwareFoundation/openexr/archive/v${OPENEXR_VERSION}.tar.gz"
OPENEXR_MD5="8926ba09c4e4cd21c7a0fa2d2b39fa82"
TARBALL="$CACHE/openexr-${OPENEXR_VERSION}.tar.gz"

CONFIG_MARKER="$PREFIX/lib/cmake/OpenEXR/OpenEXRConfig.cmake"
if [ -f "$CONFIG_MARKER" ]; then
  echo "openexr: already installed ($CONFIG_MARKER) — skip"
  exit 0
fi

# --- prerequisites from the shared prefix (build them if missing) ---
[ -f "$PREFIX/lib/cmake/Imath/ImathConfig.cmake" ]        || bash "$ROOT/scripts/deps/imath.sh"
[ -f "$PREFIX/lib/cmake/libdeflate/libdeflate-config.cmake" ] || bash "$ROOT/scripts/deps/libdeflate.sh"
[ -f "$PREFIX/lib/cmake/openjph/openjph-config.cmake" ]   || bash "$ROOT/scripts/deps/openjph.sh"

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"

mkdir -p "$CACHE" "$SCRATCH"

if [ ! -f "$TARBALL" ]; then
  curl -fL --retry 3 -o "$TARBALL" "$OPENEXR_URL"
fi
GOT_MD5="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
if [ "$GOT_MD5" != "$OPENEXR_MD5" ]; then
  echo "openexr: MD5 mismatch (got $GOT_MD5 want $OPENEXR_MD5)" >&2
  exit 1
fi

SRC="$SCRATCH/openexr-${OPENEXR_VERSION}"
rm -rf "$SRC"
tar -xzf "$TARBALL" -C "$SCRATCH"

BUILD="$SCRATCH/build"
rm -rf "$BUILD"
# Static, -pthread (IlmThread uses pthreads; matches TBB/platform threading).
# External Imath/libdeflate/openjph via *_DIR; no tools/examples/tests/python.
emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DCMAKE_PREFIX_PATH="$PREFIX" \
  -DBUILD_SHARED_LIBS=OFF \
  -DOPENEXR_BUILD_BOTH_STATIC_SHARED=OFF \
  -DBUILD_TESTING=OFF \
  -DOPENEXR_BUILD_TOOLS=OFF \
  -DOPENEXR_INSTALL_TOOLS=OFF \
  -DOPENEXR_BUILD_EXAMPLES=OFF \
  -DOPENEXR_BUILD_PYTHON=OFF \
  -DOPENEXR_FORCE_INTERNAL_IMATH=OFF \
  -DOPENEXR_FORCE_INTERNAL_DEFLATE=OFF \
  -DOPENEXR_FORCE_INTERNAL_OPENJPH=OFF \
  -DImath_DIR="$PREFIX/lib/cmake/Imath" \
  -Dlibdeflate_DIR="$PREFIX/lib/cmake/libdeflate" \
  -Dopenjph_DIR="$PREFIX/lib/cmake/openjph" \
  -DCMAKE_C_FLAGS="-pthread" \
  -DCMAKE_CXX_FLAGS="-pthread"

emmake cmake --build "$BUILD" --target install -j"$NPROC"

if [ ! -f "$CONFIG_MARKER" ]; then
  echo "openexr: install did not produce $CONFIG_MARKER" >&2
  exit 1
fi

# --- link test: compile+link a TU that opens/writes an EXR through emcc ---
VDIR="$SCRATCH/verify"
mkdir -p "$VDIR"
cat > "$VDIR/t.cpp" <<'EOF'
#include <ImfHeader.h>
#include <ImfChannelList.h>
#include <ImfCompression.h>
int main() {
  using namespace Imf;
  Header h(4, 4);
  h.channels().insert("R", Channel(HALF));
  h.compression() = ZIP_COMPRESSION; // exercises the libdeflate-backed path
  return (h.displayWindow().max.x == 3 && h.channels().findChannel("R")) ? 0 : 1;
}
EOF
# Gather all OpenEXR + Imath + deflate + openjph static archives.
LIBS=$(ls "$PREFIX"/lib/libOpenEXR*.a "$PREFIX"/lib/libIlmThread*.a "$PREFIX"/lib/libIex*.a "$PREFIX"/lib/libImath*.a "$PREFIX"/lib/libdeflate.a "$PREFIX"/lib/libopenjph.a 2>/dev/null)
em++ -pthread -std=c++17 -I"$PREFIX/include" -I"$PREFIX/include/OpenEXR" -I"$PREFIX/include/Imath" \
  "$VDIR/t.cpp" $LIBS -o "$VDIR/t.js"
test -f "$VDIR/t.wasm"
echo "openexr: verify link OK"

rm -rf "$SCRATCH"
echo "openexr ${OPENEXR_VERSION}: installed to $PREFIX (config: lib/cmake/OpenEXR)"
