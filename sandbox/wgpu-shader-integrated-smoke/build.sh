#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Device-free native/Wasm parity contract for the canonical in-tree WebGPU
# shader compiler module. No adapter or device is requested and no M3 receipt is
# allocated.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WEBGPU_SOURCE="$ROOT/upstream/source/blender/gpu/webgpu"
DAWN_SRC="${DAWN_SRC:-$ROOT/build-dawn/dawn}"
DAWN_PIN="36cf1fae0cd8a81a4fb4580751648b80b2e6255c"
NATIVE_BUILD="${NATIVE_BUILD:-$ROOT/build-dawn/t7pre-build}"
WASM_BUILD="${WASM_BUILD:-$ROOT/build-deps/shader-smoke/wasm-build}"
SHADERC_SRC="${SHADERC_SRC:-$ROOT/build-deps/shaderc-src}"
SHADERC_BUILD="${SHADERC_BUILD:-$ROOT/build-deps/shader-smoke/native-shaderc-build}"
SHADERC_TARBALL="${SHADERC_TARBALL:-$ROOT/build-deps/_cache/shaderc-2025.4.tar.gz}"
SHADERC_MD5="02208e374e610808c4ca3b1e7627b82d"
OUT="${OUT:-$ROOT/build-deps/t7-integrated/evidence}"
EMSDK="${EMSDK:-$ROOT/tools/emsdk}"
NODE="${NODE:-$EMSDK/node/22.16.0_64bit/bin/node}"
PYBIN="$ROOT/.host-tools/bin/python3.13"
HOST_CMAKE="${HOST_CMAKE:-cmake}"

case "$(uname -s):$(uname -m)" in
  Linux:x86_64)
    SHADERC_LIBRARY="${SHADERC_LIBRARY:-$SHADERC_BUILD/libshaderc/libshaderc_shared.so.1}"
    CMAKE_HOST_ARGS=(-U CMAKE_OSX_DEPLOYMENT_TARGET)
    ;;
  Darwin:arm64)
    SHADERC_LIBRARY="${SHADERC_LIBRARY:-$SHADERC_BUILD/libshaderc/libshaderc_shared.1.dylib}"
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

source_digest()
{
  local files=(
    wgpu_shader_interface_map.cc
    wgpu_shader_interface_map.hh
    wgpu_shader_compiler.cc
    wgpu_shader_compiler.hh
    wgpu_shader_cache.cc
    wgpu_shader_cache.hh
  )
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$WEBGPU_SOURCE" && sha256sum "${files[@]}" | sha256sum | awk '{print $1}')
  else
    (cd "$WEBGPU_SOURCE" && shasum -a 256 "${files[@]}" | shasum -a 256 | awk '{print $1}')
  fi
}

cache_manifest()
{
  local cache_dir="$1"
  local output="$2"
  (
    cd "$cache_dir"
    find . -type f -name '*.wgslc' -print | LC_ALL=C sort |
      while IFS= read -r relative; do
        printf '%s  %s\n' "$(sha256_file "$cache_dir/${relative#./}")" "$relative"
      done
  ) >"$output"
}

require_file "$PYBIN"
require_file "$ROOT/sandbox/series-replay/verify.py"
require_file "$ROOT/sandbox/wgpu-shader-compiler/tests/wgpu_shader_integrated_test.cc"
for source_name in \
  wgpu_shader_interface_map.cc wgpu_shader_interface_map.hh \
  wgpu_shader_compiler.cc wgpu_shader_compiler.hh \
  wgpu_shader_cache.cc wgpu_shader_cache.hh
do
  require_file "$WEBGPU_SOURCE/$source_name"
done
require_file "$EMSDK/emsdk_env.sh"
require_file "$EMSDK/upstream/emscripten/emcmake"
require_file "$NODE"
require_file "$SHADERC_TARBALL"
require_file "$SHADERC_SRC/CMakeLists.txt"
require_file "$SHADERC_SRC/CHANGES"
require_file "$SHADERC_SRC/libshaderc/include/shaderc/shaderc.hpp"
require_file "$ROOT/lib/wasm/shaderc/shaderc-archives.txt"
require_file "$ROOT/lib/wasm/tint/tint-archives.txt"

if [ ! -d "$DAWN_SRC/.git" ]; then
  echo "ERROR: Dawn checkout missing at $DAWN_SRC" >&2
  exit 1
fi
ACTUAL_DAWN_PIN="$(git -C "$DAWN_SRC" rev-parse HEAD)"
if [ "$ACTUAL_DAWN_PIN" != "$DAWN_PIN" ]; then
  echo "ERROR: Dawn pin mismatch: expected $DAWN_PIN, got $ACTUAL_DAWN_PIN" >&2
  exit 1
fi
if [ "$(md5_file "$SHADERC_TARBALL")" != "$SHADERC_MD5" ]; then
  echo "ERROR: shaderc v2025.4 tarball MD5 mismatch" >&2
  exit 1
fi
if ! grep -qx 'v2025.4' "$SHADERC_SRC/CHANGES"; then
  echo "ERROR: shaderc source does not identify v2025.4: $SHADERC_SRC" >&2
  exit 1
fi
if ! "$PYBIN" -c 'import pyexpat, xml.etree.ElementTree' >/dev/null 2>&1; then
  echo "ERROR: pinned host Python lacks working XML modules" >&2
  exit 1
fi

# Bind every integrated source byte to the canonical clean-pin replay before
# allocating build evidence.
SOURCE_PROOF="$("$PYBIN" "$ROOT/sandbox/series-replay/verify.py" --canonical-only)"
case "$SOURCE_PROOF" in
  CANONICAL_REPLAY_PASS\ *) ;;
  *)
    echo "ERROR: canonical source replay did not produce its exact verdict" >&2
    exit 1
    ;;
esac

# Bind the extracted shaderc source byte-for-byte to the pinned archive before
# configuring either target.
VERIFY_SHADERC_SRC="$(mktemp -d "${TMPDIR:-/tmp}/bw-t7-integrated-source.XXXXXX")"
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

NODE_VERSION="$("$NODE" --version)"
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

mkdir -p "$SHADERC_BUILD" "$NATIVE_BUILD" "$WASM_BUILD" "$OUT"
printf '%s\n' "$SOURCE_PROOF" >"$OUT/source-replay.txt"

CCACHE_ARGS=()
if command -v ccache >/dev/null 2>&1; then
  CCACHE_ARGS=(-DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache)
fi

echo "== [1/4] exact native shaderc v2025.4 =="
"$HOST_CMAKE" -G Ninja -S "$SHADERC_SRC" -B "$SHADERC_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CCACHE_ARGS[@]}" \
  -DPython3_EXECUTABLE="$PYBIN" \
  -DPython_EXECUTABLE="$PYBIN" \
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
"$ROOT/scripts/ninja-locked.sh" -C "$SHADERC_BUILD" shaderc_shared
require_file "$SHADERC_LIBRARY"

echo "== [2/4] canonical native compiler module =="
"$HOST_CMAKE" -G Ninja -S "$ROOT/sandbox/wgpu-shader-compiler" -B "$NATIVE_BUILD" \
  -U LIBDIR -U SHADERC_DIR -U SHADERC_LIB \
  -DCMAKE_BUILD_TYPE=Release \
  "${CMAKE_HOST_ARGS[@]}" \
  "${CCACHE_ARGS[@]}" \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DSHADERC_INCLUDE_DIR="$SHADERC_SRC/libshaderc/include" \
  -DSHADERC_LIBRARY="$SHADERC_LIBRARY" \
  -DBW_INTEGRATED_SOURCE_DIR="$WEBGPU_SOURCE" \
  -DPython3_EXECUTABLE="$PYBIN"
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" wgpu_shader_integrated_test

echo "== [3/4] canonical Wasm compiler module =="
"$EMSDK/upstream/emscripten/emcmake" "$HOST_CMAKE" -G Ninja \
  -S "$ROOT/sandbox/wgpu-shader-wasm-smoke" -B "$WASM_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CCACHE_ARGS[@]}" \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DSHADERC_PREFIX="$ROOT/lib/wasm/shaderc" \
  -DTINT_PREFIX="$ROOT/lib/wasm/tint" \
  -DBW_INTEGRATED_SOURCE_DIR="$WEBGPU_SOURCE"
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" wgpu_shader_integrated_smoke

echo "== [4/4] cold/warm cache + exact native/Wasm parity =="
NATIVE_CACHE="$(mktemp -d "${TMPDIR:-/tmp}/bw-t7-integrated-native.XXXXXX")"
WASM_CACHE="$(mktemp -d "${TMPDIR:-/tmp}/bw-t7-integrated-wasm.XXXXXX")"
cleanup_caches()
{
  local cache_dir
  for cache_dir in "$NATIVE_CACHE" "$WASM_CACHE"; do
    if [ -d "$cache_dir" ]; then
      case "$(basename "$cache_dir")" in
        bw-t7-integrated-native.*|bw-t7-integrated-wasm.*)
          find "$cache_dir" -depth -delete
          ;;
        *)
          echo "ERROR: refusing to clean unexpected cache directory: $cache_dir" >&2
          return 1
          ;;
      esac
    fi
  done
}
trap cleanup_caches EXIT

NATIVE_STDOUT="$OUT/native.stdout"
NATIVE_STDERR="$OUT/native.stderr"
WASM_STDOUT="$OUT/wasm.stdout"
WASM_STDERR="$OUT/wasm.stderr"
(
  unset BW_SHADER_CACHE_CENSUS_DIR
  export BW_SHADER_CACHE_DIR="$NATIVE_CACHE"
  "$NATIVE_BUILD/wgpu_shader_integrated_test"
) >"$NATIVE_STDOUT" 2>"$NATIVE_STDERR"
(
  unset BW_SHADER_CACHE_CENSUS_DIR
  export BW_SHADER_CACHE_DIR="$WASM_CACHE"
  "$NODE" "$WASM_BUILD/integrated_smoke.js"
) >"$WASM_STDOUT" 2>"$WASM_STDERR"

for stderr_file in "$NATIVE_STDERR" "$WASM_STDERR"; do
  if [ -s "$stderr_file" ]; then
    echo "ERROR: integrated compiler contract wrote stderr: $stderr_file" >&2
    exit 1
  fi
done
for stdout_file in "$NATIVE_STDOUT" "$WASM_STDOUT"; do
  if ! grep -qx 'INTEGRATED_SHADER_COMPILER_PASS contracts=6 cache_entries=4' "$stdout_file"; then
    echo "ERROR: integrated compiler PASS verdict missing: $stdout_file" >&2
    exit 1
  fi
  if [ "$(grep -c '^CONTRACT .* PASS$' "$stdout_file")" -ne 6 ] ||
     [ "$(grep -c '^BW_SHADER_CACHE_RESULT MISS ' "$stdout_file")" -ne 4 ] ||
     [ "$(grep -c '^BW_SHADER_CACHE_RESULT HIT bindmap_integrated$' "$stdout_file")" -ne 1 ]; then
    echo "ERROR: integrated compiler evidence census differs: $stdout_file" >&2
    exit 1
  fi
done
if ! cmp -s "$NATIVE_STDOUT" "$WASM_STDOUT"; then
  echo "ERROR: native and Wasm integrated compiler evidence differs" >&2
  diff -u "$NATIVE_STDOUT" "$WASM_STDOUT" | head -n 40 >&2
  exit 1
fi

NATIVE_CACHE_MANIFEST="$OUT/native-cache.sha256"
WASM_CACHE_MANIFEST="$OUT/wasm-cache.sha256"
cache_manifest "$NATIVE_CACHE" "$NATIVE_CACHE_MANIFEST"
cache_manifest "$WASM_CACHE" "$WASM_CACHE_MANIFEST"
if [ "$(wc -l <"$NATIVE_CACHE_MANIFEST" | tr -d ' ')" -ne 4 ] ||
   [ "$(wc -l <"$WASM_CACHE_MANIFEST" | tr -d ' ')" -ne 4 ]; then
  echo "ERROR: expected four exact cache entries per runtime" >&2
  exit 1
fi
if ! cmp -s "$NATIVE_CACHE_MANIFEST" "$WASM_CACHE_MANIFEST"; then
  echo "ERROR: native and Wasm cache manifests differ" >&2
  diff -u "$NATIVE_CACHE_MANIFEST" "$WASM_CACHE_MANIFEST" >&2
  exit 1
fi
while read -r _digest relative; do
  if ! cmp -s "$NATIVE_CACHE/${relative#./}" "$WASM_CACHE/${relative#./}"; then
    echo "ERROR: native and Wasm cache bytes differ: $relative" >&2
    exit 1
  fi
done <"$NATIVE_CACHE_MANIFEST"

"$ROOT/scripts/ninja-locked.sh" -C "$SHADERC_BUILD" -n shaderc_shared
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" -n wgpu_shader_integrated_test
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" -n wgpu_shader_integrated_smoke

OUTPUT_BYTES="$(wc -c <"$WASM_STDOUT" | tr -d ' ')"
OUTPUT_SHA256="$(sha256_file "$WASM_STDOUT")"
CACHE_SHA256="$(sha256_file "$WASM_CACHE_MANIFEST")"
SOURCE_SHA256="$(source_digest)"
echo "PASS integrated-shader native/wasm bytes=$OUTPUT_BYTES sha256=$OUTPUT_SHA256 cache_sha256=$CACHE_SHA256 source_sha256=$SOURCE_SHA256 dawn=$DAWN_PIN shaderc=v2025.4 emcc=$EMCC_VERSION node=$NODE_VERSION"
