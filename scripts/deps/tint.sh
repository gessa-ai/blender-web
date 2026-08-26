#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Cross-compile the Tint subset (SPIR-V reader + WGSL writer) to WebAssembly.
# This is the browser half of the runtime shader chain: the in-tree backend
# (source/blender/gpu/webgpu/wgpu_shader_compiler.cc) does
#   shaderc(GLSL->SPIR-V 1.3) -> Tint(ReadIR -> ProgramFromIR -> Generate) -> WGSL
# Natively it links Dawn's precompiled Tint; the wasm link needs Tint as
# cross-compiled static archives, harvested here.
#
# Pin: Dawn chromium/7989 @ 36cf1fae (build-dawn/dawn); the SAME source tree the
# native probe uses (notes/gpu-dawn-probe.md). Dawn's CMake is Emscripten-aware
# (CMakeLists.txt:66,89,266-269), so an emcmake configure with every device
# backend OFF builds the Tint archives cleanly.
#
# Posture: emcc 6.0.5, -pthread, static archives, JS-EH at the final link
# (ADR-001/003). Tint itself is -fno-exceptions (its own CMake) — EH-model-neutral
# objects, so the -fexceptions final link is unaffected.
#
# Everything OFF except SPV reader + WGSL writer: no CMD tools, no tests, no
# SPV/GLSL/HLSL/MSL/NULL writers, no protobuf/IR-binary.
#
# Harvest: lib/wasm/tint/{lib/*.a, tint-archives.txt (ordered link list),
# include/ (public API header pointers)}. Idempotent: re-running with the
# archives already present is a no-op.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DAWN_SRC="$ROOT/build-dawn/dawn"
BUILD="$ROOT/build-deps/tint"
PREFIX="$ROOT/lib/wasm/tint"
MARKER="$PREFIX/lib/libtint_lang_spirv_reader.a"

if [ -f "$MARKER" ] && [ -f "$PREFIX/tint-archives.txt" ]; then
  echo "tint: already harvested ($MARKER) — skip"
  exit 0
fi

if [ ! -d "$DAWN_SRC" ]; then
  echo "tint: Dawn checkout not found at $DAWN_SRC" >&2
  echo "  git clone --depth 1 --branch chromium/7989 https://dawn.googlesource.com/dawn \"$DAWN_SRC\"" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"

# Dawn's SPIR-V grammar codegen runs host Python; it needs a working pyexpat.
PYBIN=""
for cand in /opt/homebrew/bin/python3.13 "$(command -v python3 || true)" /usr/bin/python3; do
  [ -n "$cand" ] || continue
  if "$cand" -c 'import pyexpat, xml.etree.ElementTree' >/dev/null 2>&1; then PYBIN="$cand"; break; fi
done
[ -n "$PYBIN" ] || { echo "tint: no python3 with working pyexpat (Dawn codegen)" >&2; exit 1; }
echo "tint: using Python for Dawn codegen: $PYBIN"

# --- wrapper CMake: Dawn's third_party/CMakeLists.txt does `if(EMSCRIPTEN)
#     return()` (dawn/third_party/CMakeLists.txt:119) BEFORE adding SPIRV-Tools
#     — Dawn only ever expected emscripten for its JS-binding samples, which
#     never need Tint's SPIR-V reader. So under emcmake, SPIRV-Tools (which the
#     SPV reader hard-links, and whose `core_tables` codegen the parser needs)
#     is never configured. Fix WITHOUT touching the shared Dawn checkout: add
#     SPIRV-Headers + SPIRV-Tools as targets in a wrapper BEFORE add_subdirectory
#     (dawn), replicating Dawn's own flags (dawn/third_party/CMakeLists.txt:126-145).
#     Tint's `target_link_libraries(PRIVATE SPIRV-Tools / SPIRV-Tools-opt)` then
#     resolves and the target propagates the generated-header include dir. ------
WRAP="$ROOT/build-deps/tint-wrap"
mkdir -p "$WRAP"
cat > "$WRAP/CMakeLists.txt" <<EOF
cmake_minimum_required(VERSION 3.16)
project(tint_wasm CXX C)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(DAWN_SRC "$DAWN_SRC")

# Tint-only posture: every device backend + non-target writer OFF.
set(DAWN_FETCH_DEPENDENCIES OFF CACHE BOOL "" FORCE)
foreach(b METAL VULKAN D3D11 D3D12 NULL DESKTOP_GL OPENGLES)
  set(DAWN_ENABLE_\${b} OFF CACHE BOOL "" FORCE)
endforeach()
set(DAWN_USE_GLFW OFF CACHE BOOL "" FORCE)
set(DAWN_BUILD_SAMPLES OFF CACHE BOOL "" FORCE)
set(DAWN_BUILD_PROTOBUF OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_SPV_READER  ON  CACHE BOOL "" FORCE)
set(TINT_BUILD_WGSL_WRITER ON  CACHE BOOL "" FORCE)
set(TINT_BUILD_SPV_WRITER  OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_GLSL_WRITER OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_HLSL_WRITER OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_MSL_WRITER  OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_NULL_WRITER OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_GLSL_VALIDATOR OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_CMD_TOOLS   OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_TESTS       OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_BENCHMARKS  OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_FUZZERS     OFF CACHE BOOL "" FORCE)
set(TINT_BUILD_IR_BINARY   OFF CACHE BOOL "" FORCE)
# Internal debug self-checks. Dawn defaults both ON (CMakeLists.txt:275-276).
# The IR validator runs INSIDE ReadIR and, under wasm, traps with a "null
# function or function signature mismatch" in its Switch/Castable type-dispatch
# (a wasm strict-function-table fault absent natively). It only CHECKS the IR,
# never shapes the output, so a shipping browser runtime must not carry it —
# disabling it is the correct production posture, not a workaround.
set(TINT_ENABLE_IR_VALIDATION_ASSERTS OFF CACHE BOOL "" FORCE)
set(TINT_ENABLE_IR_DUMPING            OFF CACHE BOOL "" FORCE)

# SPIRV-Headers + SPIRV-Tools, exactly as dawn/third_party/CMakeLists.txt:126-145
set(SPIRV_HEADERS_SKIP_EXAMPLES ON CACHE BOOL "" FORCE)
set(SPIRV_HEADERS_SKIP_INSTALL  ON CACHE BOOL "" FORCE)
add_subdirectory(\${DAWN_SRC}/third_party/spirv-headers/src
                 \${CMAKE_BINARY_DIR}/spirv-headers)
set(SPIRV_SKIP_TESTS       ON  CACHE BOOL "" FORCE)
set(SPIRV_SKIP_EXECUTABLES ON  CACHE BOOL "" FORCE)
set(SKIP_SPIRV_TOOLS_INSTALL ON CACHE BOOL "" FORCE)
set(SPIRV_WERROR OFF CACHE BOOL "" FORCE)
set(ENABLE_RTTI ON CACHE BOOL "" FORCE)
add_subdirectory(\${DAWN_SRC}/third_party/spirv-tools/src
                 \${CMAKE_BINARY_DIR}/spirv-tools EXCLUDE_FROM_ALL)

add_subdirectory(\${DAWN_SRC} \${CMAKE_BINARY_DIR}/dawn EXCLUDE_FROM_ALL)
EOF

# --- configure (fresh: source dir is the wrapper, not Dawn) ------------------
rm -rf "$BUILD"
emcmake cmake -S "$WRAP" -B "$BUILD" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DPython3_EXECUTABLE="$PYBIN" \
  -DCMAKE_C_FLAGS="-pthread" -DCMAKE_CXX_FLAGS="-pthread"

# --- build SPIRV-Tools FIRST (runs core_tables codegen; defeats the generated-
#     header race), then the reader + writer + api closure. ------------------
emmake ninja -C "$BUILD" SPIRV-Tools-static SPIRV-Tools-opt \
  || emmake ninja -C "$BUILD" SPIRV-Tools SPIRV-Tools-opt
emmake ninja -C "$BUILD" \
  tint_lang_spirv_reader tint_lang_wgsl_writer tint_api

# --- harvest every produced archive in the closure ---------------------------
mkdir -p "$PREFIX/lib" "$PREFIX/include"
rm -f "$PREFIX"/lib/*.a
find "$BUILD" \( -name 'libtint_*.a' -o -name 'libSPIRV-Tools*.a' \
  -o -name 'libabsl_*.a' -o -name 'libdawn_*.a' \) -exec cp {} "$PREFIX/lib/" \;

# --- ordered link list: the native probe's proven order, filtered to what we
#     actually built (device-backend + MSL/NULL writers are absent for wasm). --
NATIVE_ORDER="$ROOT/build-dawn/t7pre-build"
{
  if [ -d "$NATIVE_ORDER" ]; then
    ninja -C "$NATIVE_ORDER" -t commands wgpu_shader_compiler_test 2>/dev/null \
      | tail -1 | tr ' ' '\n' | sed -nE 's#.*/(lib(tint_|SPIRV-Tools|absl_|dawn_).*\.a)$#\1#p'
  fi
} > "$BUILD/_native_order.txt" || true
: > "$PREFIX/tint-archives.txt"
if [ -s "$BUILD/_native_order.txt" ]; then
  while IFS= read -r a; do
    [ -f "$PREFIX/lib/$a" ] && echo "$a" >> "$PREFIX/tint-archives.txt"
  done < "$BUILD/_native_order.txt"
fi
# append any harvested archive not covered by the native order (safety)
for f in "$PREFIX"/lib/*.a; do
  b="$(basename "$f")"
  grep -qxF "$b" "$PREFIX/tint-archives.txt" || echo "$b" >> "$PREFIX/tint-archives.txt"
done

# --- public API header pointer (consumer includes src/tint/... from DAWN_SRC) -
cat > "$PREFIX/include/README.txt" <<EOF
Tint public headers are consumed from the pinned Dawn source checkout, not copied
here (they span src/tint/** plus build-tree generated tables). Consumer include
roots for source/blender/gpu/webgpu/wgpu_shader_compiler.cc:
  -I$DAWN_SRC
  -I$BUILD/gen/include        (generated, if present)
Public API used: src/tint/lang/spirv/reader/reader.h,
  src/tint/lang/wgsl/{program/program.h,writer/writer.h},
  src/tint/lang/core/ir/module.h, src/tint/api/common/binding_point.h.
EOF

N=$(wc -l < "$PREFIX/tint-archives.txt" | tr -d ' ')
SZ=$(du -sh "$PREFIX/lib" | awk '{print $1}')
echo "tint: harvested $N archives ($SZ) to $PREFIX/lib; order in tint-archives.txt"
