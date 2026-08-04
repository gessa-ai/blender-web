#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Cross-compile fmt (Blender-pinned 12.1.0) to wasm, static, into lib/wasm.
# fmt is header-heavy with a small compiled core (format.cc/os.cc). Static only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/fmt"
VERSION="12.1.0"
URL="https://github.com/fmtlib/fmt/archive/refs/tags/${VERSION}.tar.gz"
SHA256="ea7de4299689e12b6dddd392f9896f08fb0777ac7168897a244a6d6085043fea"

if [ -f "$PREFIX/lib/libfmt.a" ] && [ -f "$PREFIX/include/fmt/core.h" -o -f "$PREFIX/include/fmt/base.h" ]; then
  echo "fmt $VERSION already installed at $PREFIX — skipping."
  exit 0
fi

source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

mkdir -p "$SCRATCH" "$PREFIX"
cd "$SCRATCH"

TARBALL="fmt-${VERSION}.tar.gz"
if [ ! -f "$TARBALL" ]; then
  curl -fL --retry 3 -o "$TARBALL" "$URL"
fi
GOT_SHA="$(shasum -a 256 "$TARBALL" | awk '{print $1}')"
if [ "$GOT_SHA" != "$SHA256" ]; then
  echo "fmt tarball SHA256 mismatch: got $GOT_SHA want $SHA256" >&2
  exit 1
fi

rm -rf "fmt-${VERSION}" build
tar xf "$TARBALL"
cd "fmt-${VERSION}"

emcmake cmake -S . -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF \
  -DFMT_TEST=OFF \
  -DFMT_DOC=OFF \
  -DFMT_INSTALL=ON \
  -DCMAKE_CXX_FLAGS="-pthread -O2" \
  -DCMAKE_INSTALL_PREFIX="$PREFIX"

emmake ninja -C build
emmake ninja -C build install

cd "$ROOT"
rm -rf "$SCRATCH"

echo "fmt $VERSION installed: $PREFIX/lib/libfmt.a"
