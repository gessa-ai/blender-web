#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Device-free native/Wasm parity driver for the canonical in-tree WebGPU
# texture-format table and RGB-to-RGBA conversion module. Invoke through
# harness/buildwrap.sh.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WEBGPU_SOURCE="$ROOT/upstream/source/blender/gpu/webgpu"
DAWN_SRC="${DAWN_SRC:-$ROOT/build-dawn/dawn}"
DAWN_PIN="36cf1fae0cd8a81a4fb4580751648b80b2e6255c"
NATIVE_BUILD="${NATIVE_BUILD:-$ROOT/build-dawn/probe-build}"
WASM_BUILD="${WASM_BUILD:-$ROOT/build-deps/t9-integrated/wasm-build}"
OUT="${OUT:-$ROOT/build-deps/t9-integrated/evidence}"
EMSDK="${EMSDK:-$ROOT/tools/emsdk}"
NODE="${NODE:-$EMSDK/node/22.16.0_64bit/bin/node}"
PYBIN="$ROOT/.host-tools/bin/python3.13"
HOST_CMAKE="${HOST_CMAKE:-$ROOT/.host-tools/bin/cmake}"

case "$(uname -s):$(uname -m)" in
  Linux:x86_64)
    CMAKE_HOST_ARGS=(-U CMAKE_OSX_DEPLOYMENT_TARGET)
    ;;
  Darwin:arm64)
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
    GPU_format.hh
    GPU_texture.hh
    webgpu/wgpu_texture_format.cc
    webgpu/wgpu_texture_format.hh
    webgpu/wgpu_texture_format_list.h
    webgpu/wgpu_texture.cc
    webgpu/wgpu_data_conversion.cc
    webgpu/wgpu_data_conversion.hh
    vulkan/vk_data_conversion.hh
    vulkan/tests/vk_data_conversion_test.cc
  )
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$ROOT/upstream/source/blender/gpu" && sha256sum "${files[@]}" | sha256sum | awk '{print $1}')
  else
    (cd "$ROOT/upstream/source/blender/gpu" && shasum -a 256 "${files[@]}" | shasum -a 256 | awk '{print $1}')
  fi
}

require_file "$PYBIN"
require_file "$HOST_CMAKE"
require_file "$ROOT/scripts/ninja-locked.sh"
require_file "$ROOT/sandbox/series-replay/verify.py"
require_file "$HERE/integrated_texture_test.cc"
require_file "$ROOT/sandbox/wgpu-texture-wasm-smoke/CMakeLists.txt"
require_file "$ROOT/upstream/source/blender/gpu/GPU_format.hh"
require_file "$ROOT/upstream/source/blender/gpu/GPU_texture.hh"
require_file "$ROOT/upstream/source/blender/gpu/vulkan/vk_data_conversion.hh"
require_file "$ROOT/upstream/source/blender/gpu/vulkan/tests/vk_data_conversion_test.cc"
require_file "$EMSDK/emsdk_env.sh"
require_file "$EMSDK/upstream/emscripten/emcmake"
require_file "$NODE"
for source_name in \
  wgpu_texture_format.cc \
  wgpu_texture_format.hh \
  wgpu_texture_format_list.h \
  wgpu_texture.cc \
  wgpu_data_conversion.cc \
  wgpu_data_conversion.hh
do
  require_file "$WEBGPU_SOURCE/$source_name"
done

RGB9E5_TEXTURE_SOURCE="$WEBGPU_SOURCE/wgpu_texture.cc"
if [ "$(grep -Fc 'PackedRGB9E5' "$RGB9E5_TEXTURE_SOURCE")" -ne 6 ] ||
   [ "$(grep -Fc 'case TextureFormat::UFLOAT_9_9_9_EXP_5:' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   [ "$(grep -Ec '(^|[^[:alnum:]_])pack_rgb9e5_ufloat\(' "$RGB9E5_TEXTURE_SOURCE")" -ne 2 ] ||
   [ "$(grep -Fc 'unpack_rgb9e5_ufloat(packed, rgb);' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   grep -Fq 'shared-exponent pack not implemented' "$RGB9E5_TEXTURE_SOURCE"
then
  echo "ERROR: canonical RGB9E5 texture wiring differs" >&2
  exit 1
fi

R11_CONVERSION_SOURCE="$WEBGPU_SOURCE/wgpu_data_conversion.cc"
R11_CONVERSION_HEADER="$WEBGPU_SOURCE/wgpu_data_conversion.hh"
if [ "$(grep -Ec '^uint32_t pack_r11g11b10_ufloat\(' "$R11_CONVERSION_SOURCE")" -ne 1 ] ||
   [ "$(grep -Ec '^void unpack_r11g11b10_ufloat\(' "$R11_CONVERSION_SOURCE")" -ne 1 ] ||
   [ "$(grep -Ec '^uint32_t pack_r11g11b10_ufloat\(' "$R11_CONVERSION_HEADER")" -ne 1 ] ||
   [ "$(grep -Ec '^void unpack_r11g11b10_ufloat\(' "$R11_CONVERSION_HEADER")" -ne 1 ] ||
   [ "$(grep -Ec '(^|[^[:alnum:]_])pack_r11g11b10_ufloat\(' "$RGB9E5_TEXTURE_SOURCE")" -ne 2 ] ||
   [ "$(grep -Ec '(^|[^[:alnum:]_])unpack_r11g11b10_ufloat\(' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   grep -Fq 'float_to_ufloat' "$RGB9E5_TEXTURE_SOURCE" ||
   grep -Fq 'static uint32_t pack_r11g11b10' "$RGB9E5_TEXTURE_SOURCE"
then
  echo "ERROR: canonical RG11B10 Vulkan-parity wiring differs" >&2
  exit 1
fi

VK_CONVERSION_HEADER="$ROOT/upstream/source/blender/gpu/vulkan/vk_data_conversion.hh"
VK_CONVERSION_TEST="$ROOT/upstream/source/blender/gpu/vulkan/tests/vk_data_conversion_test.cc"
if ! grep -Fq 'using FormatF11 = FloatingPointFormat<false, 6, 5>;' "$VK_CONVERSION_HEADER" ||
   ! grep -Fq 'using FormatF10 = FloatingPointFormat<false, 5, 5>;' "$VK_CONVERSION_HEADER" ||
   ! grep -Fq 'convert_float_formats<FormatF11, FormatF32, true>' "$VK_CONVERSION_TEST" ||
   ! grep -Fq 'convert_float_formats<FormatF10, FormatF32, true>' "$VK_CONVERSION_TEST"
then
  echo "ERROR: pinned Vulkan RG11B10 oracle differs" >&2
  exit 1
fi

if [ ! -d "$DAWN_SRC/.git" ]; then
  echo "ERROR: Dawn checkout missing at $DAWN_SRC" >&2
  exit 1
fi
ACTUAL_DAWN_PIN="$(git -C "$DAWN_SRC" rev-parse HEAD)"
if [ "$ACTUAL_DAWN_PIN" != "$DAWN_PIN" ]; then
  echo "ERROR: Dawn pin mismatch: expected $DAWN_PIN, got $ACTUAL_DAWN_PIN" >&2
  exit 1
fi
if [ -n "$(git -C "$DAWN_SRC" status --porcelain)" ]; then
  echo "ERROR: Dawn checkout is not clean at the pinned commit" >&2
  exit 1
fi
if ! "$PYBIN" -c 'import pyexpat, xml.etree.ElementTree' >/dev/null 2>&1; then
  echo "ERROR: pinned host Python lacks working XML modules" >&2
  exit 1
fi
if [ "$("$HOST_CMAKE" --version | sed -n '1s/^cmake version //p')" != "4.0.3" ]; then
  echo "ERROR: expected host CMake 4.0.3" >&2
  exit 1
fi

# Bind every shipping source byte to the canonical clean-pin reconstruction
# before any evidence directory is allocated.
SOURCE_PROOF="$("$PYBIN" "$ROOT/sandbox/series-replay/verify.py" --canonical-only)"
case "$SOURCE_PROOF" in
  CANONICAL_REPLAY_PASS\ *) ;;
  *)
    echo "ERROR: canonical source replay did not produce its exact verdict" >&2
    exit 1
    ;;
esac

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

mkdir -p "$NATIVE_BUILD" "$WASM_BUILD" "$OUT"
printf '%s\n' "$SOURCE_PROOF" >"$OUT/source-replay.txt"

CCACHE_ARGS=()
if command -v ccache >/dev/null 2>&1; then
  CCACHE_ARGS=(-DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache)
fi

echo "== [1/3] canonical native texture-format/conversion module =="
"$HOST_CMAKE" -G Ninja -S "$ROOT/sandbox/dawn-probe" -B "$NATIVE_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CMAKE_HOST_ARGS[@]}" \
  "${CCACHE_ARGS[@]}" \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DBW_UPSTREAM_DIR="$ROOT/upstream" \
  -DBW_INTEGRATED_TEXTURE_SOURCE_DIR="$WEBGPU_SOURCE" \
  -DPython3_EXECUTABLE="$PYBIN"
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" wgpu_texture_integrated_test

echo "== [2/3] canonical Wasm texture-format/conversion module =="
"$EMSDK/upstream/emscripten/emcmake" "$HOST_CMAKE" -G Ninja \
  -S "$ROOT/sandbox/wgpu-texture-wasm-smoke" -B "$WASM_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CCACHE_ARGS[@]}" \
  -DBW_UPSTREAM_DIR="$ROOT/upstream" \
  -DBW_INTEGRATED_TEXTURE_SOURCE_DIR="$WEBGPU_SOURCE"
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" wgpu_texture_integrated_smoke

echo "== [3/3] exact native/Wasm parity =="
NATIVE_STDOUT="$OUT/native.stdout"
NATIVE_STDERR="$OUT/native.stderr"
WASM_STDOUT="$OUT/wasm.stdout"
WASM_STDERR="$OUT/wasm.stderr"
"$NATIVE_BUILD/wgpu_texture_integrated_test" >"$NATIVE_STDOUT" 2>"$NATIVE_STDERR"
"$NODE" "$WASM_BUILD/integrated_texture.js" >"$WASM_STDOUT" 2>"$WASM_STDERR"

for stderr_file in "$NATIVE_STDERR" "$WASM_STDERR"; do
  if [ -s "$stderr_file" ]; then
    echo "ERROR: integrated texture contract wrote stderr: $stderr_file" >&2
    exit 1
  fi
done
for stdout_file in "$NATIVE_STDOUT" "$WASM_STDOUT"; do
  if ! grep -qx \
    'INTEGRATED_TEXTURE_PASS contracts=7 formats=63 promotions=13 view_pairs=10 rgb9e5=10 rg11b10=25' \
    "$stdout_file"
  then
    echo "ERROR: integrated texture PASS verdict missing: $stdout_file" >&2
    exit 1
  fi
  if [ "$(grep -c '^CONTRACT .* PASS ' "$stdout_file")" -ne 7 ]; then
    echo "ERROR: integrated texture evidence census differs: $stdout_file" >&2
    exit 1
  fi
done
if ! cmp -s "$NATIVE_STDOUT" "$WASM_STDOUT"; then
  echo "ERROR: native and Wasm integrated texture evidence differs" >&2
  diff -u "$NATIVE_STDOUT" "$WASM_STDOUT" | head -n 40 >&2
  exit 1
fi

"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" -n wgpu_texture_integrated_test
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" -n wgpu_texture_integrated_smoke

OUTPUT_BYTES="$(wc -c <"$WASM_STDOUT" | tr -d ' ')"
OUTPUT_SHA256="$(sha256_file "$WASM_STDOUT")"
SOURCE_SHA256="$(source_digest)"
echo "PASS integrated-texture native/wasm bytes=$OUTPUT_BYTES sha256=$OUTPUT_SHA256 source_sha256=$SOURCE_SHA256 dawn=$DAWN_PIN emcc=$EMCC_VERSION node=$NODE_VERSION"
