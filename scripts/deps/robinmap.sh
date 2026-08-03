#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build Tessil robin-map for wasm. Header-only; version pinned from
# upstream/build_files/build_environment/cmake/versions.cmake (ROBINMAP_VERSION).
# OpenImageIO REQUIRED_DEP "Robinmap" (tsl::robin_map). Installs headers + the
# tsl-robin-map CMake config package so find_package(Robinmap)/(tsl-robin-map)
# resolves from the shared prefix. Idempotent.
set -euo pipefail

ROOT="/Users/paws/blender-web"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/robinmap"
CACHE="$ROOT/build-deps/_cache"
NPROC="$(sysctl -n hw.ncpu)"

ROBINMAP_VERSION="1.3.0"
ROBINMAP_URL="https://github.com/Tessil/robin-map/archive/refs/tags/v${ROBINMAP_VERSION}.tar.gz"
ROBINMAP_SHA256="a8424ad3b0affd4c57ed26f0f3d8a29604f0e1f2ef2089f497f614b1c94c7236"
TARBALL="$CACHE/robinmap-${ROBINMAP_VERSION}.tar.gz"

CONFIG_MARKER="$PREFIX/share/cmake/tsl-robin-map/tsl-robin-mapConfig.cmake"
if [ -f "$CONFIG_MARKER" ]; then
  echo "robinmap: already installed ($CONFIG_MARKER) — skip"
  exit 0
fi

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"

mkdir -p "$CACHE" "$SCRATCH"
if [ ! -f "$TARBALL" ]; then
  curl -fL --retry 3 -o "$TARBALL" "$ROBINMAP_URL"
fi
GOT="$(shasum -a 256 "$TARBALL" | awk '{print $1}')"
if [ "$GOT" != "$ROBINMAP_SHA256" ]; then
  echo "robinmap: SHA256 mismatch (got $GOT want $ROBINMAP_SHA256)" >&2
  exit 1
fi

SRC="$SCRATCH/robin-map-${ROBINMAP_VERSION}"
rm -rf "$SRC"
tar -xzf "$TARBALL" -C "$SCRATCH"

BUILD="$SCRATCH/build"
rm -rf "$BUILD"
emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_INSTALL_PREFIX="$PREFIX"
emmake cmake --build "$BUILD" --target install -j"$NPROC"

if [ ! -f "$CONFIG_MARKER" ]; then
  echo "robinmap: install did not produce $CONFIG_MARKER" >&2
  exit 1
fi

rm -rf "$SCRATCH"
echo "robinmap ${ROBINMAP_VERSION}: installed to $PREFIX (config: share/cmake/tsl-robin-map)"
