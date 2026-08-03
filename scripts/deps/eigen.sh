#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Install Eigen3 (header-only) for wasm. "Building" is installing headers plus
# the CMake config package (lib/wasm/share/eigen3/cmake) so find_package(Eigen3)
# resolves. Commit pinned from upstream versions.cmake (Blender uses a specific
# commit, not a release tag). TBB threadpool support patch is intentionally
# skipped — it is optional and TBB is a separate dep.
# Idempotent: re-running is a no-op once the config package is present.
set -euo pipefail

ROOT="/Users/paws/blender-web"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/eigen"
CACHE="$ROOT/build-deps/_cache"

EIGEN_VERSION="8a1083e9bf41b91fdea6546681f806154efdc25a"
EIGEN_URL="https://gitlab.com/libeigen/eigen/-/archive/${EIGEN_VERSION}/eigen-${EIGEN_VERSION}.tar.gz"
EIGEN_SHA256="cc28a84fdec496c6777596350ea805519bf10f717d21044ae6ba3dd562183a26"
TARBALL="$CACHE/eigen-${EIGEN_VERSION}.tar.gz"

CONFIG_MARKER="$PREFIX/share/eigen3/cmake/Eigen3Config.cmake"
if [ -f "$CONFIG_MARKER" ]; then
  echo "eigen: already installed ($CONFIG_MARKER) — skip"
  exit 0
fi

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"

mkdir -p "$CACHE" "$SCRATCH"

# --- download (cached) + verify ---
if [ ! -f "$TARBALL" ]; then
  curl -fL --retry 3 -o "$TARBALL" "$EIGEN_URL"
fi
GOT_SHA="$(shasum -a 256 "$TARBALL" | awk '{print $1}')"
if [ "$GOT_SHA" != "$EIGEN_SHA256" ]; then
  echo "eigen: SHA256 mismatch (got $GOT_SHA want $EIGEN_SHA256)" >&2
  exit 1
fi

# --- extract ---
SRC="$SCRATCH/eigen-${EIGEN_VERSION}"
rm -rf "$SRC"
tar -xzf "$TARBALL" -C "$SCRATCH"

# --- configure + install (header-only; installs headers + cmake config) ---
BUILD="$SCRATCH/build"
rm -rf "$BUILD"
emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DBUILD_TESTING=OFF \
  -DEIGEN_BUILD_DOC=OFF \
  -DEIGEN_BUILD_BLAS=OFF \
  -DEIGEN_BUILD_LAPACK=OFF \
  -DEIGEN_BUILD_TESTING=OFF
cmake --install "$BUILD"

# --- verify config package landed ---
if [ ! -f "$CONFIG_MARKER" ]; then
  echo "eigen: install did not produce $CONFIG_MARKER" >&2
  exit 1
fi

# --- tiny compile-only test: include <Eigen/Dense>, instantiate a Matrix ---
VDIR="$SCRATCH/verify"
mkdir -p "$VDIR"
cat > "$VDIR/t.cpp" <<'EOF'
#include <Eigen/Dense>
int main() {
  Eigen::Matrix3f m = Eigen::Matrix3f::Identity();
  Eigen::Vector3f v(1.f, 2.f, 3.f);
  Eigen::Vector3f r = m * v;
  return (r.sum() > 0.f) ? 0 : 1;
}
EOF
em++ -c -pthread -std=c++17 -I"$PREFIX/include/eigen3" "$VDIR/t.cpp" -o "$VDIR/t.o"
test -f "$VDIR/t.o"
echo "eigen: verify compile OK"

# --- clean scratch, keep only installed headers/config ---
rm -rf "$SCRATCH"
echo "eigen ${EIGEN_VERSION:0:8}: installed to $PREFIX (config: share/eigen3/cmake)"
