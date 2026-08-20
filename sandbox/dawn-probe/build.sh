#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M3.T1 — build + run the Dawn+Tint native probe.
#
# Steps:
#   1. GLSL 450 (vertex+fragment) -> Vulkan-1.1 SPIR-V via glslangValidator.
#   2. Configure + build the probe; add_subdirectory pulls Dawn+Tint (with the
#      DAWN_FETCH_DEPENDENCIES python fetcher the first time — needs network).
#   3. Run the probe against a hardware Dawn/Metal or Dawn/Vulkan device.
#
# Env overrides:
#   DAWN_SRC  Dawn checkout   (default: <repo>/build-dawn/dawn)
#   BUILD     probe build dir (default: <repo>/build-dawn/probe-build)
#   MACOSX_DEPLOYMENT_TARGET  Minimum macOS version (default: 11.2, matching
#                            the canonical native Blender build)
#
# All heavy invocations are meant to run under harness/buildwrap.sh, e.g.:
#   harness/buildwrap.sh bash sandbox/dawn-probe/build.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
DAWN_SRC="${DAWN_SRC:-$REPO/build-dawn/dawn}"
BUILD="${BUILD:-$REPO/build-dawn/probe-build}"
MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-11.2}"

case "$(uname -s)" in
  Darwin)
    CMAKE_HOST_ARGS=(-DCMAKE_OSX_DEPLOYMENT_TARGET="$MACOSX_DEPLOYMENT_TARGET")
    ;;
  Linux)
    # A reused migration cache may carry the old unconditional macOS value.
    # Remove it explicitly so Linux configuration has no Apple cache residue.
    CMAKE_HOST_ARGS=(-U CMAKE_OSX_DEPLOYMENT_TARGET)
    ;;
  *)
    echo "ERROR: dawn_probe supports macOS/Metal or Linux/Vulkan only" >&2
    exit 1
    ;;
esac

if [ ! -d "$DAWN_SRC" ]; then
  echo "ERROR: Dawn checkout not found at $DAWN_SRC" >&2
  echo "  git clone --depth 1 --branch chromium/7989 https://dawn.googlesource.com/dawn \"$DAWN_SRC\"" >&2
  exit 1
fi

mkdir -p "$BUILD"

# Dawn's SPIRV-Tools / codegen scripts need a Python whose pyexpat actually
# loads. Some Homebrew CPythons (seen: 3.14.6) ship a pyexpat linked against a
# libexpat that lacks a needed symbol, which aborts codegen. Pick the first
# interpreter here whose `import pyexpat` succeeds and hand it to Dawn.
PYBIN=""
for cand in "$REPO/.host-tools/bin/python3.13" /opt/homebrew/bin/python3.13 \
  "$(command -v python3 || true)" /usr/bin/python3;
do
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

# Target Vulkan 1.1 => SPIR-V 1.3. Tint's IR SPIR-V reader HARDCODES its
# validation target env to SPV_ENV_VULKAN_1_1 (src/tint/lang/spirv/reader/
# parser/parser.cc:95, not exposed through reader::Options), so a Vulkan-1.2 /
# SPIR-V-1.5 binary is rejected ("Invalid SPIR-V binary version 1.5 for target
# environment SPIR-V 1.3"). Blender's Vulkan backend uses vulkan_1_2; the WebGPU
# shader compiler must therefore emit 1.1/1.3 for the Tint path. See
# notes/gpu-dawn-probe.md.
echo "== [1/3] GLSL -> SPIR-V (Vulkan 1.1 / SPIR-V 1.3) =="
glslangValidator -V --target-env vulkan1.1 "$HERE/shaders/probe.vert" -o "$BUILD/probe.vert.spv"
glslangValidator -V --target-env vulkan1.1 "$HERE/shaders/probe.frag" -o "$BUILD/probe.frag.spv"
glslangValidator -V --target-env vulkan1.1 "$HERE/shaders/bindmap.vert" -o "$BUILD/bindmap.vert.spv"
glslangValidator -V --target-env vulkan1.1 "$HERE/shaders/bindmap.frag" -o "$BUILD/bindmap.frag.spv"

echo "== [2/3] configure + build probes (Dawn+Tint via add_subdirectory) =="
cmake -G Ninja -S "$HERE" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CMAKE_HOST_ARGS[@]}" \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DPython3_EXECUTABLE="$PYBIN"
"$REPO/scripts/ninja-locked.sh" -C "$BUILD" dawn_probe dawn_bindmap_probe

echo "== [3/3] run probes =="
echo "---- T1: shader-chain smoke (dawn_probe) ----"
"$BUILD/dawn_probe" "$BUILD/probe.vert.spv" "$BUILD/probe.frag.spv"
echo "---- T2: combined-sampler binding audit (dawn_bindmap_probe) ----"
"$BUILD/dawn_bindmap_probe" "$BUILD/bindmap.vert.spv" "$BUILD/bindmap.frag.spv"
