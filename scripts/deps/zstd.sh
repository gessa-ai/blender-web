#!/usr/bin/env bash
# Cross-compile zstd (Blender-pinned 1.5.7) to wasm, static, into lib/wasm.
# zstd ships its CMake build under build/cmake. Static only, programs/tests off.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/zstd"
VERSION="1.5.7"
URL="https://github.com/facebook/zstd/releases/download/v${VERSION}/zstd-${VERSION}.tar.gz"
SHA256="eb33e51f49a15e023950cd7825ca74a4a2b43db8354825ac24fc1b7ee09e6fa3"

if [ -f "$PREFIX/lib/libzstd.a" ] && [ -f "$PREFIX/include/zstd.h" ]; then
  echo "zstd $VERSION already installed at $PREFIX — skipping."
  exit 0
fi

source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

mkdir -p "$SCRATCH" "$PREFIX"
cd "$SCRATCH"

TARBALL="zstd-${VERSION}.tar.gz"
if [ ! -f "$TARBALL" ]; then
  curl -fL --retry 3 -o "$TARBALL" "$URL"
fi
GOT_SHA="$(shasum -a 256 "$TARBALL" | awk '{print $1}')"
if [ "$GOT_SHA" != "$SHA256" ]; then
  echo "zstd tarball SHA256 mismatch: got $GOT_SHA want $SHA256" >&2
  exit 1
fi

rm -rf "zstd-${VERSION}" build
tar xf "$TARBALL"
cd "zstd-${VERSION}/build/cmake"

emcmake cmake -S . -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF \
  -DZSTD_BUILD_STATIC=ON \
  -DZSTD_BUILD_SHARED=OFF \
  -DZSTD_BUILD_PROGRAMS=OFF \
  -DZSTD_BUILD_TESTS=OFF \
  -DZSTD_BUILD_CONTRIB=OFF \
  -DZSTD_MULTITHREAD_SUPPORT=OFF \
  -DCMAKE_C_FLAGS="-pthread -O2" \
  -DCMAKE_INSTALL_PREFIX="$PREFIX"

emmake ninja -C build
emmake ninja -C build install

rm -f "$PREFIX"/lib/libzstd*.so* "$PREFIX"/lib/libzstd*.dylib 2>/dev/null || true

cd "$ROOT"
rm -rf "$SCRATCH"

echo "zstd $VERSION installed: $PREFIX/lib/libzstd.a"
