#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M3.T7.pre — build + run the standalone WebGPU shader-compiler harness.
#
# Unlike dawn-probe (which pre-bakes SPIR-V with glslangValidator), this harness
# compiles GLSL -> SPIR-V IN-PROCESS via Blender's own libshaderc, exactly as the
# in-tree wgpu_shader_compiler.cc will. So there is NO offline shader step: the
# whole chain (shaderc -> Tint -> Dawn) runs inside the test binary.
#
# Env overrides:
#   DAWN_SRC              exact Dawn checkout (default: <repo>/build-dawn/dawn)
#   BUILD                 build dir (default: <repo>/build-dawn/t7pre-build)
#   BW_T7_EXPECT_ADAPTER  hardware | blocked (default: hardware)
#
# Run through the harness so logs stay off-context:
#   harness/buildwrap.sh bash sandbox/wgpu-shader-compiler/build.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
DAWN_SRC="${DAWN_SRC:-$REPO/build-dawn/dawn}"
BUILD="${BUILD:-$REPO/build-dawn/t7pre-build}"
OUT="${OUT:-$REPO/build-deps/t7pre/evidence}"
SHADERC_SRC="${SHADERC_SRC:-$REPO/build-deps/shaderc-src}"
SHADERC_BUILD="${SHADERC_BUILD:-$REPO/build-deps/shader-smoke/native-shaderc-build}"
SHADERC_TARBALL="${SHADERC_TARBALL:-$REPO/build-deps/_cache/shaderc-2025.4.tar.gz}"
SHADERC_MD5="02208e374e610808c4ca3b1e7627b82d"
DAWN_PIN="36cf1fae0cd8a81a4fb4580751648b80b2e6255c"
EXPECT_ADAPTER="${BW_T7_EXPECT_ADAPTER:-hardware}"
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

case "$EXPECT_ADAPTER" in
  hardware|blocked) ;;
  *)
    echo "ERROR: BW_T7_EXPECT_ADAPTER must be hardware or blocked" >&2
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
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

if [ ! -d "$DAWN_SRC/.git" ]; then
  echo "ERROR: Dawn checkout not found at $DAWN_SRC" >&2
  exit 1
fi
ACTUAL_DAWN_PIN="$(git -C "$DAWN_SRC" rev-parse HEAD)"
if [ "$ACTUAL_DAWN_PIN" != "$DAWN_PIN" ]; then
  echo "ERROR: Dawn pin mismatch: expected $DAWN_PIN, got $ACTUAL_DAWN_PIN" >&2
  exit 1
fi

require_file "$REPO/.host-tools/bin/python3.13"
require_file "$SHADERC_TARBALL"
require_file "$SHADERC_SRC/CMakeLists.txt"
require_file "$SHADERC_SRC/CHANGES"
require_file "$SHADERC_SRC/libshaderc/include/shaderc/shaderc.hpp"
if [ "$(md5_file "$SHADERC_TARBALL")" != "$SHADERC_MD5" ]; then
  echo "ERROR: shaderc v2025.4 tarball MD5 mismatch" >&2
  exit 1
fi
if ! grep -qx 'v2025.4' "$SHADERC_SRC/CHANGES"; then
  echo "ERROR: shaderc source does not identify v2025.4: $SHADERC_SRC" >&2
  exit 1
fi

# Bind the extracted source byte-for-byte to the checksum-verified archive
# before any build or evidence directory is allocated.
VERIFY_SHADERC_SRC="$(mktemp -d "${TMPDIR:-/tmp}/bw-t7pre-shaderc.XXXXXX")"
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

# Dawn's SPIRV-Tools codegen needs a Python whose pyexpat loads (see dawn-probe).
PYBIN="$REPO/.host-tools/bin/python3.13"
if ! "$PYBIN" -c 'import pyexpat, xml.etree.ElementTree' >/dev/null 2>&1; then
  echo "ERROR: no python3 with a working pyexpat found (needed by Dawn codegen)" >&2
  exit 1
fi

mkdir -p "$SHADERC_BUILD" "$BUILD" "$OUT"

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
"$REPO/scripts/ninja-locked.sh" -C "$SHADERC_BUILD" shaderc_shared
require_file "$SHADERC_LIBRARY"

echo "== [2/4] configure + build T7.pre through pinned Dawn/Tint =="
"$HOST_CMAKE" -G Ninja -S "$HERE" -B "$BUILD" \
  -U LIBDIR -U SHADERC_DIR -U SHADERC_LIB -U BW_INTEGRATED_SOURCE_DIR \
  -DCMAKE_BUILD_TYPE=Release \
  "${CMAKE_HOST_ARGS[@]}" \
  "${CCACHE_ARGS[@]}" \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DSHADERC_INCLUDE_DIR="$SHADERC_SRC/libshaderc/include" \
  -DSHADERC_LIBRARY="$SHADERC_LIBRARY" \
  -DPython3_EXECUTABLE="$PYBIN"
"$REPO/scripts/ninja-locked.sh" -C "$BUILD" wgpu_shader_compiler_test

echo "== [3/4] device-free compiler/interface contract =="
COMPILE_STDOUT="$OUT/compile-only.stdout"
COMPILE_STDERR="$OUT/compile-only.stderr"
"$BUILD/wgpu_shader_compiler_test" --compile-only >"$COMPILE_STDOUT" 2>"$COMPILE_STDERR"
if [ -s "$COMPILE_STDERR" ]; then
  echo "ERROR: compile-only contract wrote stderr: $COMPILE_STDERR" >&2
  exit 1
fi
if ! grep -qx 'T7.PRE COMPILE_ONLY PASS: 6/6 contracts' "$COMPILE_STDOUT"; then
  echo "ERROR: compile-only verdict missing: $COMPILE_STDOUT" >&2
  exit 1
fi

echo "== [4/4] live adapter boundary ($EXPECT_ADAPTER) =="
LIVE_OUTPUT="$OUT/live-adapter.txt"
case "$EXPECT_ADAPTER" in
  hardware)
    "$BUILD/wgpu_shader_compiler_test" --live >"$LIVE_OUTPUT" 2>&1
    if ! grep -q '^T7.PRE HARNESS PASS:' "$LIVE_OUTPUT"; then
      echo "ERROR: hardware run lacks the T7.pre PASS verdict: $LIVE_OUTPUT" >&2
      exit 1
    fi
    ;;
  blocked)
    set +e
    "$BUILD/wgpu_shader_compiler_test" --live >"$LIVE_OUTPUT" 2>&1
    LIVE_RC=$?
    set -e
    if [ "$LIVE_RC" -ne 5 ]; then
      echo "ERROR: expected software-adapter rc=5, got rc=$LIVE_RC: $LIVE_OUTPUT" >&2
      exit 1
    fi
    if [ "$(grep -c '^PROBE_BLOCKED: refusing non-hardware ' "$LIVE_OUTPUT")" -ne 1 ]; then
      echo "ERROR: expected exactly one strict adapter rejection: $LIVE_OUTPUT" >&2
      exit 1
    fi
    if grep -q '^T7.PRE HARNESS PASS:' "$LIVE_OUTPUT"; then
      echo "ERROR: blocked adapter emitted a live PASS verdict: $LIVE_OUTPUT" >&2
      exit 1
    fi
    ;;
esac

"$REPO/scripts/ninja-locked.sh" -C "$SHADERC_BUILD" -n shaderc_shared
"$REPO/scripts/ninja-locked.sh" -C "$BUILD" -n wgpu_shader_compiler_test
COMPILE_BYTES="$(wc -c <"$COMPILE_STDOUT" | tr -d ' ')"
COMPILE_SHA256="$(sha256_file "$COMPILE_STDOUT")"
echo "PASS T7.pre compile-only bytes=$COMPILE_BYTES sha256=$COMPILE_SHA256 dawn=$DAWN_PIN shaderc=v2025.4 adapter=$EXPECT_ADAPTER"
