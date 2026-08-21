#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Device-free native/Wasm parity smoke for the pinned shader translation chain:
# shaderc GLSL -> SPIR-V 1.3 -> Tint IR -> WGSL. Both binaries compile the
# identical smoke.cc and their WGSL must match byte-for-byte.
#
# Run through the harness so logs stay off-context:
#   harness/buildwrap.sh bash sandbox/wgpu-shader-wasm-smoke/build.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
DAWN_PIN="36cf1fae0cd8a81a4fb4580751648b80b2e6255c"
DAWN_SRC="${DAWN_SRC:-$ROOT/build-dawn/dawn}"
NATIVE_BUILD="${NATIVE_BUILD:-$ROOT/build-dawn/probe-build}"
SHADERC_SRC="${SHADERC_SRC:-$ROOT/build-deps/shaderc-src}"
NATIVE_SHADERC_BUILD="${NATIVE_SHADERC_BUILD:-$ROOT/build-deps/shader-smoke/native-shaderc-build}"
SHADERC_TARBALL="${SHADERC_TARBALL:-$ROOT/build-deps/_cache/shaderc-2025.4.tar.gz}"
SHADERC_MD5="02208e374e610808c4ca3b1e7627b82d"
WASM_BUILD="${WASM_BUILD:-$ROOT/build-deps/shader-smoke/wasm-build}"
OUT="${OUT:-$ROOT/build-deps/shader-smoke/evidence}"
EMSDK="${EMSDK:-$ROOT/tools/emsdk}"
NODE="${NODE:-$EMSDK/node/22.16.0_64bit/bin/node}"
HOST_CMAKE="${HOST_CMAKE:-cmake}"

case "$(uname -s):$(uname -m)" in
  Linux:x86_64)
    SHADERC_LIBRARY="${SHADERC_LIBRARY:-$NATIVE_SHADERC_BUILD/libshaderc/libshaderc_shared.so.1}"
    CMAKE_HOST_ARGS=(-U CMAKE_OSX_DEPLOYMENT_TARGET)
    ;;
  Darwin:arm64)
    SHADERC_LIBRARY="${SHADERC_LIBRARY:-$NATIVE_SHADERC_BUILD/libshaderc/libshaderc_shared.1.dylib}"
    CMAKE_HOST_ARGS=(-DCMAKE_OSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-11.2}")
    ;;
  *)
    echo "ERROR: supported hosts are Linux x86_64 and macOS arm64" >&2
    exit 1
    ;;
esac

require_file()
{
  if [ ! -f "$1" ]; then
    echo "ERROR: required file missing: $1" >&2
    exit 1
  fi
}

md5_file()
{
  if command -v md5sum >/dev/null 2>&1; then
    md5sum "$1" | awk '{print $1}'
  elif command -v md5 >/dev/null 2>&1; then
    md5 -q "$1"
  else
    echo "ERROR: no MD5 tool available" >&2
    return 1
  fi
}

sha256_file()
{
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo "ERROR: no SHA-256 tool available" >&2
    return 1
  fi
}

if [ ! -d "$DAWN_SRC/.git" ]; then
  echo "ERROR: Dawn checkout missing at $DAWN_SRC" >&2
  exit 1
fi
ACTUAL_DAWN_PIN="$(git -C "$DAWN_SRC" rev-parse HEAD)"
if [ "$ACTUAL_DAWN_PIN" != "$DAWN_PIN" ]; then
  echo "ERROR: Dawn pin mismatch: expected $DAWN_PIN, got $ACTUAL_DAWN_PIN" >&2
  exit 1
fi

require_file "$ROOT/.host-tools/bin/python3.13"
require_file "$EMSDK/emsdk_env.sh"
require_file "$EMSDK/upstream/emscripten/emcmake"
require_file "$NODE"
require_file "$SHADERC_TARBALL"
require_file "$SHADERC_SRC/CMakeLists.txt"
require_file "$SHADERC_SRC/CHANGES"
require_file "$SHADERC_SRC/libshaderc/include/shaderc/shaderc.hpp"
require_file "$ROOT/lib/wasm/shaderc/shaderc-archives.txt"
require_file "$ROOT/lib/wasm/tint/tint-archives.txt"

ACTUAL_SHADERC_MD5="$(md5_file "$SHADERC_TARBALL")"
if [ "$ACTUAL_SHADERC_MD5" != "$SHADERC_MD5" ]; then
  echo "ERROR: shaderc v2025.4 tarball MD5 mismatch: $ACTUAL_SHADERC_MD5" >&2
  exit 1
fi
if ! grep -qx 'v2025.4' "$SHADERC_SRC/CHANGES"; then
  echo "ERROR: shaderc source does not identify v2025.4: $SHADERC_SRC" >&2
  exit 1
fi

# Compare every extracted source path and byte against the checksum-bound
# archive. Metadata differences are irrelevant to compilation; additions,
# removals, symlink changes, and content changes are not.
VERIFY_SHADERC_SRC="$(mktemp -d "${TMPDIR:-/tmp}/bw-shaderc-source.XXXXXX")"
cleanup_source_check()
{
  find "$VERIFY_SHADERC_SRC" -depth -delete
}
trap cleanup_source_check EXIT
tar -xzf "$SHADERC_TARBALL" -C "$VERIFY_SHADERC_SRC" --strip-components=1
if ! SHADERC_SOURCE_DIFF="$(diff -qr "$VERIFY_SHADERC_SRC" "$SHADERC_SRC")"; then
  echo "ERROR: shaderc source differs from the checksum-bound v2025.4 archive" >&2
  printf '%s\n' "$SHADERC_SOURCE_DIFF" | sed -n '1,20p' >&2
  exit 1
fi
cleanup_source_check
trap - EXIT

NODE_VERSION="$($NODE --version)"
if [ "$NODE_VERSION" != "v22.16.0" ]; then
  echo "ERROR: expected Node v22.16.0, got $NODE_VERSION" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$EMSDK/emsdk_env.sh" >/dev/null
EMCC_VERSION="$(em++ --version | sed -n '1s/.* \([0-9][0-9.]*\) (.*/\1/p')"
if [ "$EMCC_VERSION" != "6.0.5" ]; then
  echo "ERROR: expected em++ 6.0.5, got ${EMCC_VERSION:-unknown}" >&2
  exit 1
fi

mkdir -p "$NATIVE_BUILD" "$NATIVE_SHADERC_BUILD" "$WASM_BUILD" "$OUT"
WGSL_NATIVE="$OUT/wgsl_native.txt"
WGSL_WASM="$OUT/wgsl_wasm.txt"
NATIVE_STDERR="$OUT/native.stderr"
WASM_STDERR="$OUT/wasm.stderr"

CCACHE_ARGS=()
if command -v ccache >/dev/null 2>&1; then
  CCACHE_ARGS=(-DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache)
fi

echo "== [1/4] native shaderc v2025.4 =="
"$HOST_CMAKE" -G Ninja -S "$SHADERC_SRC" -B "$NATIVE_SHADERC_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CCACHE_ARGS[@]}" \
  -DPython3_EXECUTABLE="$ROOT/.host-tools/bin/python3.13" \
  -DPython_EXECUTABLE="$ROOT/.host-tools/bin/python3.13" \
  -DSHADERC_SKIP_TESTS=ON \
  -DSHADERC_SKIP_EXAMPLES=ON \
  -DSHADERC_SKIP_EXECUTABLES=ON \
  -DSHADERC_SKIP_COPYRIGHT_CHECK=ON \
  -DSHADERC_ENABLE_WGSL_OUTPUT=OFF \
  -DSHADERC_SPIRV_TOOLS_DIR="$DAWN_SRC/third_party/spirv-tools/src" \
  -DSHADERC_SPIRV_HEADERS_DIR="$DAWN_SRC/third_party/spirv-headers/src" \
  -DSHADERC_GLSLANG_DIR="$DAWN_SRC/third_party/glslang/src" \
  -DBUILD_SHARED_LIBS=OFF \
  -DENABLE_CTEST=OFF
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_SHADERC_BUILD" shaderc_shared
require_file "$SHADERC_LIBRARY"

echo "== [2/4] native reference through Dawn's pinned Tint target graph =="
"$HOST_CMAKE" -G Ninja -S "$ROOT/sandbox/dawn-probe" -B "$NATIVE_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CMAKE_HOST_ARGS[@]}" \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DPython3_EXECUTABLE="$ROOT/.host-tools/bin/python3.13" \
  -DBW_SHADER_CHAIN_SMOKE_SOURCE="$HERE/smoke.cc" \
  -DBW_SHADERC_INCLUDE_DIR="$SHADERC_SRC/libshaderc/include" \
  -DBW_SHADERC_LIBRARY="$SHADERC_LIBRARY"
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" wgpu_shader_chain_smoke_native
"$NATIVE_BUILD/wgpu_shader_chain_smoke_native" >"$WGSL_NATIVE" 2>"$NATIVE_STDERR"

echo "== [3/4] Wasm chain through the harvested single-SPIRV-Tools closure =="
"$EMSDK/upstream/emscripten/emcmake" "$HOST_CMAKE" -G Ninja -S "$HERE" -B "$WASM_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CCACHE_ARGS[@]}" \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DSHADERC_PREFIX="$ROOT/lib/wasm/shaderc" \
  -DTINT_PREFIX="$ROOT/lib/wasm/tint"
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" wgpu_shader_chain_smoke
"$NODE" "$WASM_BUILD/smoke.js" >"$WGSL_WASM" 2>"$WASM_STDERR"

echo "== [4/4] exact output assertions =="
for output in "$WGSL_NATIVE" "$WGSL_WASM"; do
  if [ ! -s "$output" ]; then
    echo "ERROR: empty WGSL output: $output" >&2
    exit 1
  fi
  if ! grep -q '@group(0u) @binding(0u)' "$output"; then
    echo "ERROR: WGSL output lacks the expected group-0 binding: $output" >&2
    exit 1
  fi
done
if [ -s "$NATIVE_STDERR" ]; then
  echo "ERROR: native smoke wrote unexpected stderr: $NATIVE_STDERR" >&2
  exit 1
fi
if [ -s "$WASM_STDERR" ]; then
  echo "ERROR: Wasm smoke wrote unexpected stderr: $WASM_STDERR" >&2
  exit 1
fi
if ! cmp -s "$WGSL_NATIVE" "$WGSL_WASM"; then
  echo "ERROR: native and Wasm WGSL differ" >&2
  diff -u "$WGSL_NATIVE" "$WGSL_WASM" | head -n 40 >&2
  exit 1
fi

WGSL_BYTES="$(wc -c <"$WGSL_WASM" | tr -d ' ')"
WGSL_SHA256="$(sha256_file "$WGSL_WASM")"
echo "PASS shader-chain native/wasm parity bytes=$WGSL_BYTES sha256=$WGSL_SHA256 dawn=$DAWN_PIN emcc=$EMCC_VERSION node=$NODE_VERSION"
