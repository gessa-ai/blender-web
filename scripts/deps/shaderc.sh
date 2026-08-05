#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Cross-compile shaderc (with bundled glslang) to WebAssembly — the GLSL->SPIR-V
# front of the runtime shader chain for the BROWSER WebGPU backend:
#   shaderc(GLSL->SPIR-V 1.3) -> Tint(ReadIR->ProgramFromIR->Generate) -> WGSL
# Natively the in-tree wgpu_shader_compiler.cc links Blender's precompiled
# shaderc dylib; the wasm link needs shaderc as static archives.
#
# Version: shaderc v2025.4 — Blender's pin
# (upstream/build_files/build_environment/cmake/versions.cmake:1322).
#
# ############################################################################
# THE SPIRV-Tools SINGLE-COPY DISCIPLINE (the #1 integration hazard)
# ----------------------------------------------------------------------------
# shaderc bundles glslang + SPIRV-Tools; Tint's SPV reader ALSO links SPIRV-Tools
# (for its SplitCombinedImageSampler pass). Two static libSPIRV-Tools*.a on one
# wasm link line = duplicate `spvtools::*` symbols. Natively this is dodged by
# linking Blender's shaderc *shared* dylib (its bundled symbols are PRIVATE); a
# static wasm link has no such hiding.
#
# RESOLUTION (single shared SPIRV-Tools, by construction): build shaderc against
# the SAME SPIRV-Tools + SPIRV-Headers SOURCE that Tint used — Dawn's checkout at
# build-dawn/dawn/third_party/{spirv-tools,spirv-headers}/src — via shaderc's
# SHADERC_SPIRV_TOOLS_DIR / SHADERC_SPIRV_HEADERS_DIR knobs (the same knobs
# Blender's own shaderc.cmake uses). glslang is shaderc-only (Tint uses no
# glslang) so it stays on Dawn's matched glslang pin. shaderc's SPIRV-Tools
# object files are therefore byte-for-byte the same symbols as Tint's, so exactly
# ONE libSPIRV-Tools{,-opt}.a satisfies both consumers. That single copy already
# ships in lib/wasm/tint/lib — this script does NOT harvest a second one; it
# harvests only libshaderc + libshaderc_util + glslang. See notes/deps-shader-chain.md.
# ############################################################################
#
# Posture: emcc 6.0.5, -pthread, -fexceptions (JS-EH), static archives.
# Harvest: lib/wasm/shaderc/{lib/*.a, include/shaderc/*, shaderc-archives.txt}.
# Idempotent: re-running with libshaderc.a present is a no-op.
set -euo pipefail

ROOT="/Users/paws/blender-web"
DAWN_SRC="$ROOT/build-dawn/dawn"
SRC="$ROOT/build-deps/shaderc-src"
BUILD="$ROOT/build-deps/shaderc"
PREFIX="$ROOT/lib/wasm/shaderc"
CACHE="$ROOT/build-deps/_cache"
MARKER="$PREFIX/lib/libshaderc.a"

SHADERC_VERSION="v2025.4"
SHADERC_URL="https://github.com/google/shaderc/archive/${SHADERC_VERSION}.tar.gz"
SHADERC_MD5="02208e374e610808c4ca3b1e7627b82d"
TARBALL="$CACHE/shaderc-2025.4.tar.gz"

if [ -f "$MARKER" ] && [ -f "$PREFIX/shaderc-archives.txt" ]; then
  echo "shaderc: already harvested ($MARKER) — skip"
  exit 0
fi

# The single shared SPIRV-Tools must already be built by Tint.
if [ ! -f "$ROOT/lib/wasm/tint/lib/libSPIRV-Tools.a" ]; then
  echo "shaderc: lib/wasm/tint/lib/libSPIRV-Tools.a missing — run scripts/deps/tint.sh first" >&2
  exit 1
fi
for d in spirv-tools spirv-headers glslang; do
  [ -e "$DAWN_SRC/third_party/$d/src/CMakeLists.txt" ] || {
    echo "shaderc: Dawn shared dep $d not found under $DAWN_SRC/third_party" >&2; exit 1; }
done

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"

PYBIN=""
for cand in /opt/homebrew/bin/python3.13 "$(command -v python3 || true)" /usr/bin/python3; do
  [ -n "$cand" ] || continue
  if "$cand" -c 'import pyexpat, xml.etree.ElementTree' >/dev/null 2>&1; then PYBIN="$cand"; break; fi
done
[ -n "$PYBIN" ] || { echo "shaderc: no python3 with working pyexpat" >&2; exit 1; }

# --- download (cached) + verify ---
mkdir -p "$CACHE"
if [ ! -f "$TARBALL" ]; then
  curl -fL --retry 3 -o "$TARBALL" "$SHADERC_URL"
fi
GOT_MD5="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
[ "$GOT_MD5" = "$SHADERC_MD5" ] || { echo "shaderc: MD5 mismatch (got $GOT_MD5)" >&2; exit 1; }

# --- extract ---
rm -rf "$SRC"; mkdir -p "$SRC"
tar -xzf "$TARBALL" -C "$SRC" --strip-components=1

# --- configure: shaderc + glslang against Dawn's SHARED SPIRV-Tools source ---
rm -rf "$BUILD"
emcmake cmake -S "$SRC" -B "$BUILD" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DPython3_EXECUTABLE="$PYBIN" -DPython_EXECUTABLE="$PYBIN" \
  -DSHADERC_SKIP_TESTS=ON \
  -DSHADERC_SKIP_EXAMPLES=ON \
  -DSHADERC_SKIP_EXECUTABLES=ON \
  -DSHADERC_SKIP_COPYRIGHT_CHECK=ON \
  -DSHADERC_ENABLE_WGSL_OUTPUT=OFF \
  -DSHADERC_SPIRV_TOOLS_DIR="$DAWN_SRC/third_party/spirv-tools/src" \
  -DSHADERC_SPIRV_HEADERS_DIR="$DAWN_SRC/third_party/spirv-headers/src" \
  -DSHADERC_GLSLANG_DIR="$DAWN_SRC/third_party/glslang/src" \
  -DBUILD_SHARED_LIBS=OFF \
  -DENABLE_CTEST=OFF \
  -DCMAKE_C_FLAGS="-pthread -fexceptions" \
  -DCMAKE_CXX_FLAGS="-pthread -fexceptions"

# --- build the static shaderc lib (pulls glslang + spirv-tools) --------------
emmake ninja -C "$BUILD" shaderc

# --- harvest: shaderc + shaderc_util + glslang archives (NOT spirv-tools:
#     the single shared copy ships in lib/wasm/tint/lib) ---------------------
mkdir -p "$PREFIX/lib" "$PREFIX/include/shaderc"
rm -f "$PREFIX"/lib/*.a
# shaderc's own libs
find "$BUILD/libshaderc" "$BUILD/libshaderc_util" -name '*.a' -exec cp {} "$PREFIX/lib/" \; 2>/dev/null || true
# glslang's libs (glslang, MachineIndependent, GenericCodeGen, OSDependent,
# SPIRV (glslang's GLSL->SPV backend — NOT spirv-tools), SPVRemapper,
# glslang-default-resource-limits). Exclude any SPIRV-Tools archive.
find "$BUILD/third_party/glslang" -name 'lib*.a' 2>/dev/null \
  | grep -viE 'libSPIRV-Tools' | while IFS= read -r f; do cp "$f" "$PREFIX/lib/"; done

# --- public headers ---
cp "$SRC"/libshaderc/include/shaderc/*.h  "$PREFIX/include/shaderc/" 2>/dev/null || true
cp "$SRC"/libshaderc/include/shaderc/*.hpp "$PREFIX/include/shaderc/" 2>/dev/null || true

# --- ordered link list (shaderc -> shaderc_util -> glslang; spirv-tools comes
#     from the Tint bundle). Group at the consumer link defeats residual order. -
: > "$PREFIX/shaderc-archives.txt"
for a in libshaderc.a libshaderc_util.a \
         libglslang.a libMachineIndependent.a libGenericCodeGen.a \
         libglslang-default-resource-limits.a libSPIRV.a libSPVRemapper.a \
         libOSDependent.a libOGLCompiler.a libHLSL.a; do
  [ -f "$PREFIX/lib/$a" ] && echo "$a" >> "$PREFIX/shaderc-archives.txt"
done
# any harvested archive not covered above (safety)
for f in "$PREFIX"/lib/*.a; do
  b="$(basename "$f")"
  grep -qxF "$b" "$PREFIX/shaderc-archives.txt" || echo "$b" >> "$PREFIX/shaderc-archives.txt"
done

# --- guard: no SPIRV-Tools duplicate leaked into the shaderc bundle ----------
if ls "$PREFIX"/lib/libSPIRV-Tools*.a >/dev/null 2>&1; then
  echo "shaderc: ERROR — a SPIRV-Tools archive leaked into the shaderc bundle (breaks single-copy discipline)" >&2
  exit 1
fi

N=$(wc -l < "$PREFIX/shaderc-archives.txt" | tr -d ' ')
SZ=$(du -sh "$PREFIX/lib" | awk '{print $1}')
echo "shaderc ${SHADERC_VERSION}: harvested $N archives ($SZ) to $PREFIX/lib; spirv-tools SHARED with tint"
