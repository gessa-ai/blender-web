#!/usr/bin/env bash
# Cross-compile zlib (Blender-pinned 1.3.1) to wasm, static, into lib/wasm.
#
# Approach note: Emscripten ships a zlib port (-sUSE_ZLIB=1 / --use-port=zlib),
# but that only satisfies compile/link for consumers that ask emcc for it. The
# downstream superbuild (OpenEXR, OIIO, libpng, minizip-ng) all run
# find_package(ZLIB) / find ZLIB::ZLIB and need a REAL static libz.a + zlib.h +
# a CMake/pkgconfig config discoverable under the shared prefix. So we build
# zlib from Blender's pinned source into lib/wasm. The emcc port stays available
# as a fallback for trivial consumers, but the harvested static lib is the one
# downstream find_package resolves against.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/zlib"
VERSION="1.3.1"
URL="https://github.com/madler/zlib/releases/download/v${VERSION}/zlib-${VERSION}.tar.gz"
MD5="9855b6d802d7fe5b7bd5b196a2271655"

# Idempotent: skip if already installed.
if [ -f "$PREFIX/lib/libz.a" ] && [ -f "$PREFIX/include/zlib.h" ]; then
  echo "zlib $VERSION already installed at $PREFIX — skipping."
  exit 0
fi

source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

mkdir -p "$SCRATCH" "$PREFIX"
cd "$SCRATCH"

TARBALL="zlib-${VERSION}.tar.gz"
if [ ! -f "$TARBALL" ]; then
  curl -fL --retry 3 -o "$TARBALL" "$URL"
fi
# Verify pinned hash (matches Blender versions.cmake ZLIB_HASH / MD5).
GOT_MD5="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
if [ "$GOT_MD5" != "$MD5" ]; then
  echo "zlib tarball MD5 mismatch: got $GOT_MD5 want $MD5" >&2
  exit 1
fi

rm -rf "zlib-${VERSION}" build
tar xf "$TARBALL"
cd "zlib-${VERSION}"

emcmake cmake -S . -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF \
  -DZLIB_BUILD_EXAMPLES=OFF \
  -DCMAKE_C_FLAGS="-pthread -O2" \
  -DCMAKE_INSTALL_PREFIX="$PREFIX"

emmake ninja -C build
emmake ninja -C build install

# zlib's CMake install also drops a shared/import stub name on some platforms;
# ensure the static archive is the resolved one and no stray .so/.dylib remain.
rm -f "$PREFIX"/lib/libz*.so* "$PREFIX"/lib/libz*.dylib 2>/dev/null || true

# Clean scratch on success (keep only installed artifacts).
cd "$ROOT"
rm -rf "$SCRATCH"

echo "zlib $VERSION installed: $PREFIX/lib/libz.a"
