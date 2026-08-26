#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: Apache-2.0
#
# Build OpenUSD 26.03's official core-only Emscripten profile and harvest its
# relocatable static consumer package into lib/wasm. Imaging, USD Imaging,
# Python bindings, tools and dynamic plugins are intentionally disabled.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/openusd"
CACHE="$ROOT/build-deps/_cache"
VERSION="26.03"
URL="https://github.com/PixarAnimationStudios/OpenUSD/archive/v${VERSION}.tar.gz"
MD5="cc6d6bffdcdd038f60e2fe4726b08673"
SHA256="590ea75ffa3ac0c35fdd080df04d61a696733b8f3d6a79bdc3f13f8077162d36"
TARBALL="$CACHE/openusd-v${VERSION}.tar.gz"
SRC="$SCRATCH/src"
BUILD="$SCRATCH/build"
STAGE="$SCRATCH/install"
JOBS="$(sysctl -n hw.logicalcpu 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
FORCE=0
DOTEST=0

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --test) DOTEST=1 ;;
    --jobs=*) JOBS="${arg#--jobs=}" ;;
    *) echo "openusd: unknown argument: $arg" >&2; exit 2 ;;
  esac
done
case "$JOBS" in ''|*[!0-9]*) echo "openusd: --jobs must be a positive integer" >&2; exit 2 ;; esac
[ "$JOBS" -gt 0 ] || { echo "openusd: --jobs must be positive" >&2; exit 2; }

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

run_test() {
  local usd_root="$1"
  local smoke_build="$SCRATCH/smoke-build"
  if [ -d "$smoke_build" ]; then
    find "$smoke_build" -depth -delete
  fi
  emcmake cmake -S "$ROOT/sandbox/m7-usd-prep/smoke" -B "$smoke_build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DOPENUSD_ROOT="$usd_root" \
    -DWASM_DEPS_ROOT="$PREFIX"
  "$ROOT/scripts/ninja-locked.sh" -C "$smoke_build" -j "$JOBS"
  node "$smoke_build/usd_core_smoke.js" | tee "$SCRATCH/smoke.out"
  grep -q "USD_CORE_SMOKE_OK format=usda prim=/Triangle points=3" "$SCRATCH/smoke.out"
}

if [ "$FORCE" = 0 ] && \
   [ -f "$PREFIX/lib/libusd_m.a" ] && \
   [ -f "$PREFIX/lib/libusdShaders.a" ] && \
   [ -f "$PREFIX/pxrConfig.cmake" ]; then
  echo "openusd: already installed at $PREFIX (skip; --force to rebuild)"
  [ "$DOTEST" = 1 ] && run_test "$PREFIX"
  exit 0
fi

[ -f "$PREFIX/lib/libtbb.a" ] || {
  echo "openusd: missing Wasm oneTBB; run scripts/deps/tbb.sh first" >&2
  exit 1
}
[ -f "$PREFIX/lib/cmake/TBB/TBBConfig.cmake" ] || {
  echo "openusd: missing TBBConfig.cmake in the Wasm prefix" >&2
  exit 1
}

mkdir -p "$CACHE" "$SCRATCH"
if [ ! -f "$TARBALL" ]; then
  curl -fL --retry 3 -o "$TARBALL" "$URL"
fi
got_md5="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
got_sha256="$(shasum -a 256 "$TARBALL" | awk '{print $1}')"
[ "$got_md5" = "$MD5" ] || { echo "openusd: MD5 mismatch got=$got_md5 want=$MD5" >&2; exit 1; }
[ "$got_sha256" = "$SHA256" ] || {
  echo "openusd: SHA256 mismatch got=$got_sha256 want=$SHA256" >&2
  exit 1
}

for owned in "$SRC" "$BUILD" "$STAGE" "$SCRATCH/smoke-build"; do
  case "$owned" in "$SCRATCH"/*) ;; *) echo "openusd: refusing unsafe cleanup path: $owned" >&2; exit 1 ;; esac
  [ ! -d "$owned" ] || find "$owned" -depth -delete
done
mkdir -p "$SRC" "$BUILD" "$STAGE"
tar -xzf "$TARBALL" -C "$SRC" --strip-components=1

emcmake cmake -S "$SRC" -B "$BUILD" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$STAGE" \
  -DCMAKE_FIND_ROOT_PATH="$PREFIX" \
  -DCMAKE_PREFIX_PATH="$PREFIX" \
  -DCMAKE_C_FLAGS="-pthread --use-port=zlib" \
  -DCMAKE_CXX_FLAGS="-pthread --use-port=zlib" \
  -DCMAKE_EXE_LINKER_FLAGS="-pthread" \
  -DBUILD_SHARED_LIBS=OFF \
  -DPXR_BUILD_MONOLITHIC=ON \
  -DPXR_FIND_TBB_IN_CONFIG=ON \
  -DTBB_DIR="$PREFIX/lib/cmake/TBB" \
  -DPXR_SET_INTERNAL_NAMESPACE=pxrBlender_v26_03 \
  -DPXR_PREFER_SAFETY_OVER_SPEED=ON \
  -DPXR_ENABLE_PYTHON_SUPPORT=OFF \
  -DPXR_BUILD_IMAGING=OFF \
  -DPXR_BUILD_USD_IMAGING=OFF \
  -DPXR_BUILD_USDVIEW=OFF \
  -DPXR_BUILD_USD_TOOLS=OFF \
  -DPXR_BUILD_USD_VALIDATION=OFF \
  -DPXR_BUILD_TESTS=OFF \
  -DPXR_BUILD_EXAMPLES=OFF \
  -DPXR_BUILD_TUTORIALS=OFF \
  -DPXR_BUILD_DOCUMENTATION=OFF \
  -DPXR_BUILD_PYTHON_DOCUMENTATION=OFF \
  -DPXR_ENABLE_PRECOMPILED_HEADERS=OFF \
  -DPXR_ENABLE_MATERIALX_SUPPORT=OFF \
  -DPXR_ENABLE_OPENVDB_SUPPORT=OFF \
  -DPXR_ENABLE_PTEX_SUPPORT=OFF \
  -DPXR_ENABLE_GL_SUPPORT=OFF \
  -DPXR_ENABLE_METAL_SUPPORT=OFF \
  -DPXR_ENABLE_VULKAN_SUPPORT=OFF \
  -DPXR_BUILD_ALEMBIC_PLUGIN=OFF \
  -DPXR_BUILD_DRACO_PLUGIN=OFF \
  -DPXR_BUILD_EMBREE_PLUGIN=OFF \
  -DPXR_BUILD_OPENIMAGEIO_PLUGIN=OFF \
  -DPXR_BUILD_OPENCOLORIO_PLUGIN=OFF \
  -DPXR_BUILD_PRMAN_PLUGIN=OFF \
  -DPXR_VALIDATE_GENERATED_CODE=OFF

"$ROOT/scripts/ninja-locked.sh" -C "$BUILD" install -j "$JOBS"
for required in \
  "$STAGE/include/pxr/pxr.h" \
  "$STAGE/lib/libusd_m.a" \
  "$STAGE/lib/libusdShaders.a" \
  "$STAGE/lib/usd/usdGeom/resources/generatedSchema.usda" \
  "$STAGE/cmake/pxrTargets.cmake" \
  "$STAGE/pxrConfig.cmake"; do
  [ -f "$required" ] || { echo "openusd: install missing $required" >&2; exit 1; }
done

run_test "$STAGE"

# Harvest only OpenUSD-owned paths. pxrConfig.cmake is copied explicitly because
# OpenUSD's install rule binds that root file to CMAKE_INSTALL_PREFIX and ignores
# a later `cmake --install --prefix` relocation; the remaining targets are
# relocatable relative to PREFIX/cmake.
for owned in "$PREFIX/include/pxr" "$PREFIX/lib/usd" "$PREFIX/plugin/usd"; do
  case "$owned" in "$PREFIX"/*) ;; *) echo "openusd: refusing unsafe harvest path: $owned" >&2; exit 1 ;; esac
  [ ! -d "$owned" ] || find "$owned" -depth -delete
done
mkdir -p "$PREFIX/include" "$PREFIX/lib" "$PREFIX/plugin" "$PREFIX/cmake" \
  "$PREFIX/share/licenses/OpenUSD-26.03"
cp -R "$STAGE/include/pxr" "$PREFIX/include/pxr"
cp "$STAGE/lib/libusd_m.a" "$PREFIX/lib/libusd_m.a"
cp "$STAGE/lib/libusdShaders.a" "$PREFIX/lib/libusdShaders.a"
cp -R "$STAGE/lib/usd" "$PREFIX/lib/usd"
cp -R "$STAGE/plugin/usd" "$PREFIX/plugin/usd"
cp "$STAGE/cmake/pxrTargets.cmake" "$PREFIX/cmake/pxrTargets.cmake"
cp "$STAGE/cmake/pxrTargets-release.cmake" "$PREFIX/cmake/pxrTargets-release.cmake"
cp "$STAGE/pxrConfig.cmake" "$PREFIX/pxrConfig.cmake"
cp "$SRC/LICENSE.txt" "$PREFIX/share/licenses/OpenUSD-26.03/LICENSE.txt"
cp "$SRC/NOTICE.txt" "$PREFIX/share/licenses/OpenUSD-26.03/NOTICE.txt"

echo "openusd ${VERSION}: core + usdShaders installed to $PREFIX"
shasum -a 256 "$PREFIX/lib/libusd_m.a" "$PREFIX/lib/libusdShaders.a" "$PREFIX/pxrConfig.cmake"

# Preserve the pin, test output, licenses and installed harvest; reclaim the
# large reproducible source/object/staging trees.
for owned in "$SRC" "$BUILD" "$STAGE" "$SCRATCH/smoke-build"; do
  [ ! -d "$owned" ] || find "$owned" -depth -delete
done
echo "openusd: done (source/build/stage removed; archive and smoke.out retained)"
