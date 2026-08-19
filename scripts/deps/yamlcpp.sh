#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build yaml-cpp for wasm, static, -pthread. Version pinned from
# upstream/build_files/build_environment/cmake/versions.cmake (YAMLCPP_VERSION).
# OpenColorIO dep. Idempotent.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/yamlcpp"
CACHE="$ROOT/build-deps/_cache"
NPROC="$(getconf _NPROCESSORS_ONLN)"

YAMLCPP_VERSION="0.8.0"
YAMLCPP_URL="https://github.com/jbeder/yaml-cpp/archive/refs/tags/${YAMLCPP_VERSION}.tar.gz"
YAMLCPP_MD5="1d2c7975edba60e995abe3c4af6480e5"
TARBALL="$CACHE/yaml-cpp-${YAMLCPP_VERSION}.tar.gz"

CONFIG_MARKER="$PREFIX/lib/cmake/yaml-cpp/yaml-cpp-config.cmake"
if [ -f "$CONFIG_MARKER" ]; then echo "yamlcpp: already installed — skip"; exit 0; fi

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"
mkdir -p "$CACHE" "$SCRATCH"
[ -f "$TARBALL" ] || curl -fL --retry 3 -o "$TARBALL" "$YAMLCPP_URL"
GOT="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
[ "$GOT" = "$YAMLCPP_MD5" ] || { echo "yamlcpp: MD5 mismatch ($GOT)"; exit 1; }

SRC="$SCRATCH/yaml-cpp-${YAMLCPP_VERSION}"
rm -rf "$SRC"
tar -xzf "$TARBALL" -C "$SCRATCH"

BUILD="$SCRATCH/build"; rm -rf "$BUILD"
emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DBUILD_SHARED_LIBS=OFF \
  -DYAML_BUILD_SHARED_LIBS=OFF \
  -DYAML_CPP_BUILD_TESTS=OFF \
  -DYAML_CPP_BUILD_TOOLS=OFF \
  -DYAML_CPP_BUILD_CONTRIB=OFF \
  -DYAML_CPP_INSTALL=ON \
  -DCMAKE_CXX_FLAGS="-pthread"
emmake cmake --build "$BUILD" --target install -j"$NPROC"

[ -f "$CONFIG_MARKER" ] || { echo "yamlcpp: config not installed"; exit 1; }
rm -rf "$SCRATCH"
echo "yamlcpp ${YAMLCPP_VERSION}: installed ($CONFIG_MARKER)"
