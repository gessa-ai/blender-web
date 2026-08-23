#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Device-free native/Wasm parity driver for the canonical in-tree WebGPU
# shader frontend. Invoke through harness/buildwrap.sh.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WEBGPU_SOURCE="$ROOT/upstream/source/blender/gpu/webgpu"
DAWN_SRC="${DAWN_SRC:-$ROOT/build-dawn/dawn}"
DAWN_PIN="36cf1fae0cd8a81a4fb4580751648b80b2e6255c"
NATIVE_BUILD="${NATIVE_BUILD:-$ROOT/build-dawn/probe-build}"
WASM_BUILD="${WASM_BUILD:-$ROOT/build-deps/t7-frontend-integrated/wasm-build}"
OUT="${OUT:-$ROOT/build-deps/t7-frontend-integrated/evidence}"
GENERATED_DIR="${GENERATED_DIR:-$ROOT/build-deps/t7-frontend-integrated/generated}"
PUSH_CONSTANT_SET_SOURCE="$GENERATED_DIR/wgpu_push_constant_set.inc"
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
    source/blender/gpu/webgpu/wgpu_shader.cc
    source/blender/gpu/webgpu/wgpu_shader.hh
    source/blender/gpu/webgpu/wgpu_texture_format.hh
    source/blender/gpu/webgpu/wgpu_buffer.hh
    source/blender/gpu/webgpu/wgpu_shader_compiler.hh
    source/blender/gpu/webgpu/wgpu_shader_interface_map.hh
    source/blender/gpu/intern/gpu_shader_create_info.hh
    source/blender/gpu/intern/gpu_shader_private.hh
    source/blender/gpu/shaders/infos/gpu_shader_sequencer_infos.hh
    source/blender/gpu/shaders/infos/gpu_shader_simple_lighting_infos.hh
    source/blender/gpu/shaders/infos/gpu_srgb_to_framebuffer_space_infos.hh
    source/blender/gpu/GPU_common_types.hh
    source/blender/gpu/GPU_texture.hh
    source/blender/blenlib/BLI_map.hh
    source/blender/blenlib/BLI_string_ref.hh
    intern/guardedalloc/MEM_guardedalloc.h
    intern/guardedalloc/intern/leak_detector.cc
    intern/guardedalloc/intern/mallocn.cc
    intern/guardedalloc/intern/mallocn_guarded_impl.cc
    intern/guardedalloc/intern/mallocn_lockfree_impl.cc
    intern/guardedalloc/intern/memory_usage.cc
    intern/clog/clog.cc
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
require_file "$ROOT/sandbox/series-replay/verify.py"
require_file "$HERE/integrated_shader_frontend_test.cc"
require_file "$HERE/extract_push_constant_set.py"
require_file "$ROOT/sandbox/wgpu-shader-frontend-wasm-smoke/CMakeLists.txt"
for source_name in \
  wgpu_shader.cc \
  wgpu_shader.hh \
  wgpu_texture_format.hh \
  wgpu_buffer.hh \
  wgpu_shader_compiler.hh \
  wgpu_shader_interface_map.hh
do
  require_file "$WEBGPU_SOURCE/$source_name"
done
if [ "$(grep -F -c \
  'storage_image_format(res.image.format, res.image.qualifiers)' \
  "$WEBGPU_SOURCE/wgpu_shader.cc")" -ne 3 ]
then
  echo "ERROR: storage-image format promotion is not bound to all three shipping interfaces" >&2
  exit 1
fi
if [ "$(grep -F -c \
       'static bool explicit_layout_handles_create_if_valid(' \
       "$WEBGPU_SOURCE/wgpu_shader.cc")" -ne 0 ] ||
   [ "$(grep -F -c \
       'if (!build_explicit_layout(device,' \
       "$WEBGPU_SOURCE/wgpu_shader.cc")" -ne 0 ] ||
   [ "$(grep -F -c \
       'bool build_explicit_layout(const wgpu::Device &device,' \
       "$WEBGPU_SOURCE/wgpu_shader.hh")" -ne 0 ] ||
   [ "$(grep -F -c \
       'explicit_layout_cache_.get_or_create(' \
       "$WEBGPU_SOURCE/wgpu_shader.cc")" -ne 1 ] ||
   [ "$(grep -F -c \
       'bool WGPUShader::ensure_explicit_layout(const wgpu::Instance &instance,' \
       "$WEBGPU_SOURCE/wgpu_shader.cc")" -ne 1 ] ||
   [ "$(grep -F -c \
       'webgpu::ScopedHandleCache<uint8_t, ExplicitLayoutHandles> explicit_layout_cache_;' \
       "$WEBGPU_SOURCE/wgpu_shader.hh")" -ne 1 ] ||
   [ "$(grep -F -c \
       'bool build_explicit_layout(const wgpu::Instance &instance,' \
       "$WEBGPU_SOURCE/wgpu_shader.hh")" -ne 1 ]
then
  echo "ERROR: scoped explicit shader-layout publication is not wired exactly once" >&2
  exit 1
fi
for source_path in \
  source/blender/gpu/intern/gpu_shader_create_info.hh \
  source/blender/gpu/intern/gpu_shader_private.hh \
  source/blender/gpu/shaders/infos/gpu_shader_sequencer_infos.hh \
  source/blender/gpu/shaders/infos/gpu_shader_simple_lighting_infos.hh \
  source/blender/gpu/shaders/infos/gpu_srgb_to_framebuffer_space_infos.hh \
  source/blender/gpu/GPU_common_types.hh \
  source/blender/gpu/GPU_texture.hh \
  source/blender/blenlib/BLI_map.hh \
  source/blender/blenlib/BLI_string_ref.hh \
  intern/guardedalloc/MEM_guardedalloc.h \
  intern/guardedalloc/intern/leak_detector.cc \
  intern/guardedalloc/intern/mallocn.cc \
  intern/guardedalloc/intern/mallocn_guarded_impl.cc \
  intern/guardedalloc/intern/mallocn_lockfree_impl.cc \
  intern/guardedalloc/intern/memory_usage.cc \
  intern/clog/clog.cc
do
  require_file "$ROOT/upstream/$source_path"
done
EXPECTED_MAT3_CREATE_INFOS='source/blender/gpu/shaders/infos/gpu_shader_sequencer_infos.hh:PUSH_CONSTANT(float3x3, scope_gamut_to_rec709)
source/blender/gpu/shaders/infos/gpu_shader_sequencer_infos.hh:PUSH_CONSTANT(float3x3, scope_yuv_matrix)
source/blender/gpu/shaders/infos/gpu_shader_simple_lighting_infos.hh:PUSH_CONSTANT(float3x3, NormalMatrix)
source/blender/gpu/shaders/infos/gpu_srgb_to_framebuffer_space_infos.hh:PUSH_CONSTANT(float3x3, gpu_scene_linear_to_rec709)'
ACTUAL_MAT3_CREATE_INFOS="$(grep -RH '^PUSH_CONSTANT(float3x3, ' \
  "$ROOT/upstream/source/blender/gpu/shaders/infos" | \
  sed "s#^$ROOT/upstream/##" | LC_ALL=C sort)"
if [ "$ACTUAL_MAT3_CREATE_INFOS" != "$EXPECTED_MAT3_CREATE_INFOS" ]; then
  echo "ERROR: pinned float3x3 push-constant create-info census differs" >&2
  exit 1
fi
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

# Bind the shipping source to the canonical clean-pin reconstruction before
# allocating an evidence directory.
SOURCE_PROOF="$("$PYBIN" "$ROOT/sandbox/series-replay/verify.py" --canonical-only)"
case "$SOURCE_PROOF" in
  CANONICAL_REPLAY_PASS\ *) ;;
  *)
    echo "ERROR: canonical source replay did not produce its exact verdict" >&2
    exit 1
    ;;
esac

"$PYBIN" "$HERE/extract_push_constant_set.py" \
  --source "$WEBGPU_SOURCE/wgpu_shader.cc" \
  --output "$PUSH_CONSTANT_SET_SOURCE"
require_file "$PUSH_CONSTANT_SET_SOURCE"

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

echo "== [1/3] canonical native shader-frontend contract =="
"$HOST_CMAKE" -G Ninja -S "$ROOT/sandbox/dawn-probe" -B "$NATIVE_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CMAKE_HOST_ARGS[@]}" \
  "${CCACHE_ARGS[@]}" \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DBW_UPSTREAM_DIR="$ROOT/upstream" \
  -DBW_INTEGRATED_SHADER_FRONTEND_SOURCE_DIR="$WEBGPU_SOURCE" \
  -DBW_WGPU_PUSH_CONSTANT_SET_SOURCE="$PUSH_CONSTANT_SET_SOURCE" \
  -DBW_NATIVE_FMT_INCLUDE_DIR="$NATIVE_FMT_INCLUDE" \
  -DPython3_EXECUTABLE="$PYBIN"
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" wgpu_shader_frontend_integrated_test

echo "== [2/3] canonical Wasm shader-frontend contract =="
"$EMSDK/upstream/emscripten/emcmake" "$HOST_CMAKE" -G Ninja \
  -S "$ROOT/sandbox/wgpu-shader-frontend-wasm-smoke" -B "$WASM_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CCACHE_ARGS[@]}" \
  -DBW_UPSTREAM_DIR="$ROOT/upstream" \
  -DBW_INTEGRATED_SHADER_FRONTEND_SOURCE_DIR="$WEBGPU_SOURCE" \
  -DBW_WGPU_PUSH_CONSTANT_SET_SOURCE="$PUSH_CONSTANT_SET_SOURCE" \
  -DBW_WASM_INCLUDE_DIR="$WASM_INCLUDE"
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" wgpu_shader_frontend_integrated_smoke

echo "== [3/3] exact native/Wasm parity =="
NATIVE_STDOUT="$OUT/native.stdout"
NATIVE_STDERR="$OUT/native.stderr"
WASM_STDOUT="$OUT/wasm.stdout"
WASM_STDERR="$OUT/wasm.stderr"
"$NATIVE_BUILD/wgpu_shader_frontend_integrated_test" >"$NATIVE_STDOUT" 2>"$NATIVE_STDERR"
"$NODE" "$WASM_BUILD/integrated_shader_frontend.js" >"$WASM_STDOUT" 2>"$WASM_STDERR"

for stdout_file in "$NATIVE_STDOUT" "$WASM_STDOUT"; do
  if [ "$(wc -l <"$stdout_file" | tr -d ' ')" -ne 12 ] ||
     ! grep -qx \
       'CONTRACT image-types PASS cases=39 bindings=78 signed-atomic-array=1' "$stdout_file" ||
     ! grep -qx \
       'CONTRACT storage-formats PASS formats=63 qualifiers=8 helper-cases=504 promotions=18 spellings=32 shipping-call-sites=3' "$stdout_file" ||
     ! grep -qx \
       'CONTRACT qualifiers PASS bit-patterns=8 outputs=16 writeonly-promoted=1' "$stdout_file" ||
     ! grep -qx \
       'CONTRACT explicit-layout-scoped-publication PASS cases=7 attempts=4 pending=deduplicated error-object=rejected retry=published nulls=atomic' \
       "$stdout_file" ||
     ! grep -qx 'CONTRACT std140 PASS cases=30 scalars=15 arrays=15' "$stdout_file" ||
     ! grep -qx \
       'CONTRACT push-array-packing PASS arrays=5 elements=19 payload=148 padding=156 block=304' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT push-mat3-packing PASS create-infos=4 matrices=4 columns=12 payload=144 padding=48 block=192' \
       "$stdout_file" ||
     ! grep -qx 'CONTRACT buffer-helper-rewrite PASS cases=3 nested-passes=1' "$stdout_file" ||
     ! grep -qx \
       'CONTRACT integer-sampler-rewrite PASS cases=9 rewritten=7 controls=2' "$stdout_file" ||
     ! grep -qx \
       'CONTRACT 1d-array-rewrite PASS cases=23 sampled=10 image=11 controls=2' "$stdout_file" ||
     ! grep -qx \
       'CONTRACT finite-builtin-rewrite PASS cases=4 overloads=8 controls=2' "$stdout_file" ||
     ! grep -qx 'INTEGRATED_SHADER_FRONTEND_PASS contracts=11 cases=653' "$stdout_file"
  then
    echo "ERROR: integrated shader-frontend evidence differs: $stdout_file" >&2
    exit 1
  fi
done
for stderr_file in "$NATIVE_STDERR" "$WASM_STDERR"; do
  if [ -s "$stderr_file" ]; then
    echo "ERROR: integrated shader-frontend stderr is not empty: $stderr_file" >&2
    exit 1
  fi
done
if ! cmp -s "$NATIVE_STDOUT" "$WASM_STDOUT" ||
   ! cmp -s "$NATIVE_STDERR" "$WASM_STDERR"
then
  echo "ERROR: native and Wasm integrated shader-frontend evidence differs" >&2
  exit 1
fi

"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" -n wgpu_shader_frontend_integrated_test
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" -n wgpu_shader_frontend_integrated_smoke

OUTPUT_BYTES="$(wc -c <"$WASM_STDOUT" | tr -d ' ')"
OUTPUT_SHA256="$(sha256_file "$WASM_STDOUT")"
SOURCE_SHA256="$(source_digest)"
PACKING_SHA256="$(sha256_file "$PUSH_CONSTANT_SET_SOURCE")"
printf 'PASS integrated-shader-frontend native/wasm bytes=%s sha256=%s source_sha256=%s packing_sha256=%s fmt_sha256=%s dawn=%s emcc=%s node=%s\n' \
  "$OUTPUT_BYTES" "$OUTPUT_SHA256" "$SOURCE_SHA256" "$PACKING_SHA256" "$FMT_SHA256" \
  "$DAWN_PIN" "$EMCC_VERSION" "$NODE_VERSION"
