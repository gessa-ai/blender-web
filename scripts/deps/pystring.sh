#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build pystring for wasm, static, -pthread. Version pinned from
# upstream/build_files/build_environment/cmake/versions.cmake (PYSTRING_VERSION).
# pystring ships no CMake build; Blender supplies one (patches/cmakelists_pystring.txt)
# — we write the same minimal CMakeLists. OpenColorIO dep. Idempotent.
set -euo pipefail

ROOT="/Users/paws/blender-web"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/pystring"
CACHE="$ROOT/build-deps/_cache"
NPROC="$(sysctl -n hw.ncpu)"

PYSTRING_VERSION="1.1.3"
PYSTRING_URL="https://codeload.github.com/imageworks/pystring/tar.gz/refs/tags/v${PYSTRING_VERSION}"
PYSTRING_MD5="f2c68786b359f5e4e62bed53bc4fb86d"
TARBALL="$CACHE/pystring-v${PYSTRING_VERSION}.tar.gz"

MARKER="$PREFIX/lib/libpystring.a"
if [ -f "$MARKER" ]; then echo "pystring: already installed — skip"; exit 0; fi

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"
mkdir -p "$CACHE" "$SCRATCH"
[ -f "$TARBALL" ] || curl -fL --retry 3 -o "$TARBALL" "$PYSTRING_URL"
GOT="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
[ "$GOT" = "$PYSTRING_MD5" ] || { echo "pystring: MD5 mismatch ($GOT)"; exit 1; }

SRC="$SCRATCH/pystring-${PYSTRING_VERSION}"
rm -rf "$SRC"
tar -xzf "$TARBALL" -C "$SCRATCH"

cat > "$SRC/CMakeLists.txt" <<'EOF'
cmake_minimum_required(VERSION 3.10)
project(pystring CXX)
add_library(pystring STATIC pystring.cpp pystring.h)
install(TARGETS pystring ARCHIVE DESTINATION lib LIBRARY DESTINATION lib)
install(FILES pystring.h DESTINATION include)
EOF

BUILD="$SCRATCH/build"; rm -rf "$BUILD"
emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DCMAKE_CXX_FLAGS="-pthread"
emmake cmake --build "$BUILD" --target install -j"$NPROC"

[ -f "$MARKER" ] || { echo "pystring: libpystring.a not installed"; exit 1; }
rm -rf "$SCRATCH"
echo "pystring ${PYSTRING_VERSION}: installed ($MARKER)"
