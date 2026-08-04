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
#   DAWN_SRC  Dawn checkout            (default: <repo>/build-dawn/dawn — shared with dawn-probe)
#   LIBDIR    Blender precompiled libs (default: <repo>/lib/macos_arm64 — has shaderc/)
#   BUILD     build dir               (default: <repo>/build-dawn/t7pre-build)
#
# Run through the harness so logs stay off-context:
#   harness/buildwrap.sh bash sandbox/wgpu-shader-compiler/build.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
DAWN_SRC="${DAWN_SRC:-$REPO/build-dawn/dawn}"
LIBDIR="${LIBDIR:-$REPO/lib/macos_arm64}"
BUILD="${BUILD:-$REPO/build-dawn/t7pre-build}"

if [ ! -d "$DAWN_SRC" ]; then
  echo "ERROR: Dawn checkout not found at $DAWN_SRC" >&2
  echo "  git clone --depth 1 --branch chromium/7989 https://dawn.googlesource.com/dawn \"$DAWN_SRC\"" >&2
  exit 1
fi
if [ ! -f "$LIBDIR/shaderc/include/shaderc/shaderc.hpp" ]; then
  echo "ERROR: shaderc not found under $LIBDIR/shaderc (Blender precompiled libs)" >&2
  exit 1
fi

# Dawn's SPIRV-Tools codegen needs a Python whose pyexpat loads (see dawn-probe).
PYBIN=""
for cand in /opt/homebrew/bin/python3.13 "$(command -v python3 || true)" /usr/bin/python3; do
  [ -n "$cand" ] || continue
  if "$cand" -c 'import pyexpat, xml.etree.ElementTree' >/dev/null 2>&1; then
    PYBIN="$cand"; break
  fi
done
if [ -z "$PYBIN" ]; then
  echo "ERROR: no python3 with a working pyexpat found (needed by Dawn codegen)" >&2
  exit 1
fi
echo "Using Python for Dawn codegen: $PYBIN"

echo "== [1/2] configure + build (Dawn+Tint via add_subdirectory, + libshaderc) =="
cmake -G Ninja -S "$HERE" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DLIBDIR="$LIBDIR" \
  -DPython3_EXECUTABLE="$PYBIN"
ninja -C "$BUILD" wgpu_shader_compiler_test

echo "== [2/2] run end-to-end harness =="
"$BUILD/wgpu_shader_compiler_test"
