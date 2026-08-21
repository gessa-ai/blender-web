#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Device-free native/Wasm parity driver for the canonical in-tree WebGPU
# vertex-buffer CPU conversion helpers. Invoke through harness/buildwrap.sh.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WEBGPU_SOURCE="$ROOT/upstream/source/blender/gpu/webgpu"
DAWN_SRC="${DAWN_SRC:-$ROOT/build-dawn/dawn}"
DAWN_PIN="36cf1fae0cd8a81a4fb4580751648b80b2e6255c"
NATIVE_BUILD="${NATIVE_BUILD:-$ROOT/build-dawn/probe-build}"
WASM_BUILD="${WASM_BUILD:-$ROOT/build-deps/t6-vertex-integrated/wasm-build}"
OUT="${OUT:-$ROOT/build-deps/t6-vertex-integrated/evidence}"
EMSDK="${EMSDK:-$ROOT/tools/emsdk}"
NODE="${NODE:-$EMSDK/node/22.16.0_64bit/bin/node}"
PYBIN="$ROOT/.host-tools/bin/python3.13"
HOST_CMAKE="${HOST_CMAKE:-$ROOT/.host-tools/bin/cmake}"
WASM_INCLUDE="$ROOT/lib/wasm/include"

case "$(uname -s):$(uname -m)" in
  Linux:x86_64)
    CMAKE_HOST_ARGS=(-U CMAKE_OSX_DEPLOYMENT_TARGET)
    NATIVE_FMT_INCLUDE="$ROOT/lib/linux_x64/fmt/include"
    ;;
  Darwin:arm64)
    CMAKE_HOST_ARGS=(-DCMAKE_OSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-11.2}")
    NATIVE_FMT_INCLUDE="$ROOT/lib/macos_arm64/fmt/include"
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
    source/blender/gpu/webgpu/wgpu_vertex_buffer.cc
    source/blender/gpu/webgpu/wgpu_vertex_buffer.hh
    source/blender/gpu/webgpu/wgpu_buffer.hh
    source/blender/gpu/webgpu/wgpu_common.hh
    source/blender/gpu/webgpu/wgpu_context.hh
    source/blender/gpu/GPU_vertex_buffer.hh
    source/blender/gpu/GPU_vertex_format.hh
    source/blender/gpu/GPU_format.hh
    source/blender/gpu/intern/gpu_vertex_format.cc
    source/blender/gpu/intern/gpu_context_private.hh
    source/blender/blenlib/BLI_assert.h
    source/blender/blenlib/intern/BLI_assert.cc
    intern/guardedalloc/MEM_guardedalloc.h
  )
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$ROOT/upstream" && sha256sum "${files[@]}" | sha256sum | awk '{print $1}')
  else
    (cd "$ROOT/upstream" && shasum -a 256 "${files[@]}" | shasum -a 256 | awk '{print $1}')
  fi
}

require_file "$PYBIN"
require_file "$HOST_CMAKE"
require_file "$ROOT/scripts/ninja-locked.sh"
require_file "$ROOT/harness/buildwrap.sh"
require_file "$HERE/integrated_vertex_test.cc"
require_file "$ROOT/sandbox/wgpu-vertex-wasm-smoke/CMakeLists.txt"
for source_name in \
  wgpu_vertex_buffer.cc \
  wgpu_vertex_buffer.hh \
  wgpu_buffer.hh \
  wgpu_common.hh \
  wgpu_context.hh
do
  require_file "$WEBGPU_SOURCE/$source_name"
done
for source_path in \
  source/blender/gpu/GPU_vertex_buffer.hh \
  source/blender/gpu/GPU_vertex_format.hh \
  source/blender/gpu/GPU_format.hh \
  source/blender/gpu/intern/gpu_vertex_format.cc \
  source/blender/gpu/intern/gpu_context_private.hh \
  source/blender/blenlib/BLI_assert.h \
  source/blender/blenlib/intern/BLI_assert.cc \
  intern/guardedalloc/MEM_guardedalloc.h
do
  require_file "$ROOT/upstream/$source_path"
done
require_file "$NATIVE_FMT_INCLUDE/fmt/ranges.h"
require_file "$WASM_INCLUDE/fmt/ranges.h"
if ! cmp -s "$NATIVE_FMT_INCLUDE/fmt/ranges.h" "$WASM_INCLUDE/fmt/ranges.h"; then
  echo "ERROR: native and Wasm fmt/ranges.h inputs differ" >&2
  exit 1
fi
FMT_SHA256="$(sha256_file "$WASM_INCLUDE/fmt/ranges.h")"

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

echo "== [1/3] canonical native vertex-buffer CPU contract =="
"$HOST_CMAKE" -G Ninja -S "$ROOT/sandbox/dawn-probe" -B "$NATIVE_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CMAKE_HOST_ARGS[@]}" \
  "${CCACHE_ARGS[@]}" \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DBW_UPSTREAM_DIR="$ROOT/upstream" \
  -DBW_INTEGRATED_VERTEX_SOURCE_DIR="$WEBGPU_SOURCE" \
  -DBW_NATIVE_FMT_INCLUDE_DIR="$NATIVE_FMT_INCLUDE" \
  -DPython3_EXECUTABLE="$PYBIN"
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" wgpu_vertex_integrated_test

echo "== [2/3] canonical Wasm vertex-buffer CPU contract =="
"$EMSDK/upstream/emscripten/emcmake" "$HOST_CMAKE" -G Ninja \
  -S "$ROOT/sandbox/wgpu-vertex-wasm-smoke" -B "$WASM_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CCACHE_ARGS[@]}" \
  -DBW_UPSTREAM_DIR="$ROOT/upstream" \
  -DBW_INTEGRATED_VERTEX_SOURCE_DIR="$WEBGPU_SOURCE" \
  -DBW_WASM_INCLUDE_DIR="$WASM_INCLUDE"
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" wgpu_vertex_integrated_smoke

echo "== [3/3] exact native/Wasm parity =="
NATIVE_STDOUT="$OUT/native.stdout"
NATIVE_STDERR="$OUT/native.stderr"
WASM_STDOUT="$OUT/wasm.stdout"
WASM_STDERR="$OUT/wasm.stderr"
"$NATIVE_BUILD/wgpu_vertex_integrated_test" >"$NATIVE_STDOUT" 2>"$NATIVE_STDERR"
"$NODE" "$WASM_BUILD/integrated_vertex.js" >"$WASM_STDOUT" 2>"$WASM_STDERR"

for stdout_file in "$NATIVE_STDOUT" "$WASM_STDOUT"; do
  if [ "$(wc -l <"$stdout_file" | tr -d ' ')" -ne 7 ] ||
     ! grep -qx 'CONTRACT component PASS cases=1024 range=-127:127' "$stdout_file" ||
     ! grep -qx 'CONTRACT detection PASS cases=19 slots=16 legacy-alias=1' "$stdout_file" ||
     ! grep -qx \
       'CONTRACT interleaved PASS vertices=1024 fields=1024 preserved=8192' "$stdout_file" ||
     ! grep -qx \
       'CONTRACT deinterleaved PASS vertices=17 fields=34 preserved=204' "$stdout_file" ||
     ! grep -qx 'CONTRACT bounds PASS nbytes=13 transformed=1 guarded=12' "$stdout_file" ||
     ! grep -qx 'CONTRACT usage PASS cases=8 masked-flags=4' "$stdout_file" ||
     ! grep -qx \
       'INTEGRATED_VERTEX_PASS contracts=6 components=1024 vertices=1041 fields=1059 usage=8' \
       "$stdout_file"
  then
    echo "ERROR: integrated vertex evidence differs: $stdout_file" >&2
    exit 1
  fi
done
for stderr_file in "$NATIVE_STDERR" "$WASM_STDERR"; do
  if [ -s "$stderr_file" ]; then
    echo "ERROR: integrated vertex stderr is not empty: $stderr_file" >&2
    exit 1
  fi
done
if ! cmp -s "$NATIVE_STDOUT" "$WASM_STDOUT" ||
   ! cmp -s "$NATIVE_STDERR" "$WASM_STDERR"
then
  echo "ERROR: native and Wasm integrated vertex evidence differs" >&2
  exit 1
fi

"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" -n wgpu_vertex_integrated_test
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" -n wgpu_vertex_integrated_smoke

OUTPUT_BYTES="$(wc -c <"$WASM_STDOUT" | tr -d ' ')"
OUTPUT_SHA256="$(sha256_file "$WASM_STDOUT")"
SOURCE_SHA256="$(source_digest)"
printf 'PASS integrated-vertex native/wasm bytes=%s sha256=%s source_sha256=%s fmt_sha256=%s dawn=%s emcc=%s node=%s\n' \
  "$OUTPUT_BYTES" "$OUTPUT_SHA256" "$SOURCE_SHA256" "$FMT_SHA256" \
  "$DAWN_PIN" "$EMCC_VERSION" "$NODE_VERSION"
