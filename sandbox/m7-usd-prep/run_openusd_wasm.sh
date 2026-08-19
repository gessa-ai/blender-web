#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: Apache-2.0
#
# Isolated OpenUSD 26.03 Wasm32 configure/build/smoke driver.
# It never writes to lib/wasm or a shipping bundle: --work must be a new directory.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ARCHIVE=""
WORK=""
MODE="configure"
JOBS="$(sysctl -n hw.logicalcpu 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
DEPS="$ROOT/lib/wasm"

usage() {
  cat <<'EOF'
usage: run_openusd_wasm.sh --archive /path/to/usd-v26.03.tar.gz --work /new/path
                            [--mode configure|build|smoke] [--jobs N]
                            [--deps /path/to/wasm-prefix]

configure  verify the pin and configure only (default)
build      build and install the complete core profile into WORK/install
smoke      build/install, then compile and run the .usda mesh round-trip smoke

The dependency prefix is read-only. The work directory must not already exist.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --archive) ARCHIVE="${2:?missing archive path}"; shift 2 ;;
    --work) WORK="${2:?missing work path}"; shift 2 ;;
    --mode) MODE="${2:?missing mode}"; shift 2 ;;
    --jobs) JOBS="${2:?missing job count}"; shift 2 ;;
    --deps) DEPS="${2:?missing dependency prefix}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$MODE" in configure|build|smoke) ;; *) echo "invalid --mode: $MODE" >&2; exit 2 ;; esac
[ -n "$ARCHIVE" ] || { echo "--archive is required" >&2; exit 2; }
[ -f "$ARCHIVE" ] || { echo "archive not found: $ARCHIVE" >&2; exit 2; }
[ -n "$WORK" ] || { echo "--work is required" >&2; exit 2; }
[ ! -e "$WORK" ] || { echo "refusing existing --work path: $WORK" >&2; exit 2; }
case "$JOBS" in ''|*[!0-9]*) echo "--jobs must be a positive integer" >&2; exit 2 ;; esac
[ "$JOBS" -gt 0 ] || { echo "--jobs must be positive" >&2; exit 2; }

want_md5="cc6d6bffdcdd038f60e2fe4726b08673"
if command -v md5 >/dev/null 2>&1; then
  got_md5="$(md5 -q "$ARCHIVE")"
else
  got_md5="$(md5sum "$ARCHIVE" | awk '{print $1}')"
fi
[ "$got_md5" = "$want_md5" ] || {
  echo "OpenUSD archive MD5 mismatch: got=$got_md5 want=$want_md5" >&2
  exit 1
}

for required in \
  "$DEPS/include/oneapi/tbb.h" \
  "$DEPS/lib/libtbb.a" \
  "$DEPS/lib/cmake/TBB/TBBConfig.cmake"; do
  [ -f "$required" ] || { echo "missing Wasm dependency: $required" >&2; exit 1; }
done

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1
command -v emcmake >/dev/null || { echo "emsdk did not provide emcmake" >&2; exit 1; }
command -v ninja >/dev/null || { echo "ninja is required" >&2; exit 1; }

mkdir -p "$WORK/src" "$WORK/build" "$WORK/install"
tar -xzf "$ARCHIVE" -C "$WORK/src" --strip-components=1
[ -f "$WORK/src/pxr/pxr.h.in" ] || { echo "archive is not an OpenUSD source tree" >&2; exit 1; }
cp "$WORK/src/LICENSE.txt" "$WORK/LICENSE.OpenUSD.txt"
cp "$WORK/src/NOTICE.txt" "$WORK/NOTICE.OpenUSD.txt"

emcmake cmake -S "$WORK/src" -B "$WORK/build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$WORK/install" \
  -DCMAKE_FIND_ROOT_PATH="$DEPS" \
  -DCMAKE_PREFIX_PATH="$DEPS" \
  -DCMAKE_C_FLAGS="-pthread --use-port=zlib" \
  -DCMAKE_CXX_FLAGS="-pthread --use-port=zlib" \
  -DCMAKE_EXE_LINKER_FLAGS="-pthread" \
  -DBUILD_SHARED_LIBS=OFF \
  -DPXR_BUILD_MONOLITHIC=ON \
  -DPXR_FIND_TBB_IN_CONFIG=ON \
  -DTBB_DIR="$DEPS/lib/cmake/TBB" \
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

echo "OPENUSD_WASM_CONFIG_OK build=$WORK/build target=usd_m"
[ "$MODE" = configure ] && exit 0

# The install target builds libusd_m.a plus the statically linked usdShaders plugin,
# installs headers/CMake targets, and stages every plugInfo/schema resource needed by
# the imported targets' Emscripten --embed-file interface.
cmake --build "$WORK/build" --target install -j "$JOBS"
[ -f "$WORK/install/lib/libusd_m.a" ] || { echo "install produced no libusd_m.a" >&2; exit 1; }
[ -f "$WORK/install/pxrConfig.cmake" ] || { echo "install produced no pxrConfig.cmake" >&2; exit 1; }
echo "OPENUSD_WASM_BUILD_OK archive=$WORK/install/lib/libusd_m.a"
[ "$MODE" = build ] && exit 0

emcmake cmake -S "$ROOT/sandbox/m7-usd-prep/smoke" -B "$WORK/smoke-build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DOPENUSD_ROOT="$WORK/install" \
  -DWASM_DEPS_ROOT="$DEPS"
cmake --build "$WORK/smoke-build" -j "$JOBS"
node "$WORK/smoke-build/usd_core_smoke.js"

