#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build OpenSubdiv (TBB-backed with API-independent GLSL patch-source data) static
# for wasm and harvest to lib/wasm.
# Version + hash pinned from
# upstream/build_files/build_environment/cmake/versions.cmake (OPENSUBDIV_VERSION
# v3_7_0, MD5 470d53c4d4335a601c33a052ce7c33b4). Options mirror the Blender
# superbuild's cmake/opensubdiv.cmake, adapted for the browser target: every GPU
# backend (OpenGL/Metal/CUDA/OpenCL/DX) is disabled (there is no native GPU API
# under Emscripten), leaving Far/Sdc/Vtr/Bfr + the CPU evaluators. The independent
# GLSL patch-source generator remains enabled for Blender's WebGPU shader compiler.
# TBB comes from the shared prefix (scripts/deps/tbb.sh) via TBB_DIR.
#
# GOTCHA (consumer contract): Blender's build_files/cmake/Modules/FindOpenSubdiv.cmake
# resolves TWO components, osdCPU AND osdGPU, and dependency_targets.cmake does
#   target_link_libraries(bf_deps_optional_opensubdiv INTERFACE ${OPENSUBDIV_LIBRARIES})
# so a missing osdGPU injects a literal "-NOTFOUND" link token and breaks configure.
# Blender's WebGPU subdivision shaders call
# GLSLPatchShaderSource::GetPatchBasisShaderSource(), so the installed osdGPU
# component must contain that generated string implementation even though GL API
# support remains disabled. An empty compatibility archive is not sufficient.
#
# Idempotent: no-op once both archives and the GLSL header/symbol contract are
# present (--force to rebuild, --test to rerun the smoke). Deletes the build tree
# after harvest.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/opensubdiv"
CACHE="$ROOT/build-deps/_cache"
NPROC="$(getconf _NPROCESSORS_ONLN)"

OSD_VERSION="v3_7_0"
OSD_URL="https://github.com/PixarAnimationStudios/OpenSubdiv/archive/${OSD_VERSION}.tar.gz"
OSD_MD5="470d53c4d4335a601c33a052ce7c33b4"
TARBALL="$CACHE/opensubdiv-${OSD_VERSION}.tar.gz"
SRC="$SCRATCH/OpenSubdiv-3_7_0"

FORCE=0; DOTEST=0
for a in "$@"; do case "$a" in --force) FORCE=1;; --test) DOTEST=1;; esac; done

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

verify_gpu_shader_source_archive() {
  local gpu_lib="$PREFIX/lib/libosdGPU.a"
  local glsl_header="$PREFIX/include/opensubdiv/osd/glslPatchShaderSource.h"
  [ -f "$glsl_header" ] || return 1
  [ -f "$gpu_lib" ] || return 1
  [ "$(wc -c < "$gpu_lib")" -gt 8 ] || return 1
  emar t "$gpu_lib" | grep -q 'glslPatchShaderSource' || return 1
  emnm -C --defined-only "$gpu_lib" | \
    grep -Eq '[[:space:]][TtWw][[:space:]].*GLSLPatchShaderSource::GetPatchBasisShaderSource' || \
    return 1
  if emar t "$gpu_lib" | grep -Eq '(^|/)(glComputeEvaluator|glVertexBuffer|glPatchTable|glMesh)'; then
    echo "opensubdiv: osdGPU unexpectedly contains OpenGL API objects" >&2
    return 1
  fi
  if emnm -u "$gpu_lib" | grep -Eq '(^|[[:space:]])_?gl[A-Z]'; then
    echo "opensubdiv: osdGPU unexpectedly imports OpenGL API symbols" >&2
    return 1
  fi
}

run_test() {
  local v="$SCRATCH/verify"
  mkdir -p "$v"
  # Far + GLSL patch-source functional test: Catmull-Clark refine a cube one level
  # and verify generated basis-source markers. A cube (8v/6 quads) at level 1 ->
  # 8 orig + 12 edge-pts + 6 face-pts = 26 verts. Exercises far/vtr/sdc from
  # libosdCPU.a and the WebGPU shader-source dependency from libosdGPU.a.
  cat > "$v/t.cpp" <<'EOF'
#include <cstdio>
#include <string>
#include <opensubdiv/far/topologyRefinerFactory.h>
#include <opensubdiv/far/topologyDescriptor.h>
#include <opensubdiv/osd/glslPatchShaderSource.h>
using namespace OpenSubdiv;
static int   g_nverts = 8;
static int   g_nfaces = 6;
static int   g_vertsperface[6] = {4,4,4,4,4,4};
static int   g_vertIndices[24] = {0,1,3,2, 2,3,5,4, 4,5,7,6, 6,7,1,0, 1,7,5,3, 6,0,2,4};
int main() {
  typedef Far::TopologyDescriptor Descriptor;
  Sdc::SchemeType type = Sdc::SCHEME_CATMARK;
  Sdc::Options options;
  options.SetVtxBoundaryInterpolation(Sdc::Options::VTX_BOUNDARY_EDGE_ONLY);
  Descriptor desc;
  desc.numVertices = g_nverts;
  desc.numFaces = g_nfaces;
  desc.numVertsPerFace = g_vertsperface;
  desc.vertIndicesPerFace = g_vertIndices;
  Far::TopologyRefiner *refiner =
    Far::TopologyRefinerFactory<Descriptor>::Create(desc,
      Far::TopologyRefinerFactory<Descriptor>::Options(type, options));
  refiner->RefineUniform(Far::TopologyRefiner::UniformOptions(1));
  int nv = refiner->GetLevel(1).GetNumVertices();
  const std::string basis = Osd::GLSLPatchShaderSource::GetPatchBasisShaderSource();
  const bool has_param = basis.find("OsdPatchParamIsRegular") != std::string::npos;
  const bool has_evaluate = basis.find("OsdEvaluatePatchBasis") != std::string::npos;
  printf("OSD_WASM_REFINE nverts_level1=%d glsl_bytes=%zu param=%d evaluate=%d\n",
         nv,
         basis.size(),
         int(has_param),
         int(has_evaluate));
  return nv == 26 && has_param && has_evaluate ? 0 : 1;
}
EOF
  em++ -std=c++17 -pthread -fexceptions -I "$PREFIX/include" \
    "$v/t.cpp" "$PREFIX/lib/libosdCPU.a" "$PREFIX/lib/libosdGPU.a" \
    "$PREFIX/lib/libtbb.a" \
    -sPROXY_TO_PTHREAD -sPTHREAD_POOL_SIZE=4 -sEXIT_RUNTIME=1 \
    -sINITIAL_MEMORY=134217728 -sWASM_BIGINT -o "$v/t.js"
  test -f "$v/t.wasm"
  node "$v/t.js" | tee "$v/t.out"
  grep -Eq "OSD_WASM_REFINE nverts_level1=26 glsl_bytes=[1-9][0-9]* param=1 evaluate=1" "$v/t.out"
  echo "opensubdiv: Far refine + GLSL patch-basis smoke OK"
}

if [ "$FORCE" = 0 ] && [ -f "$PREFIX/lib/libosdCPU.a" ] && \
   verify_gpu_shader_source_archive; then
  echo "opensubdiv: already installed ($PREFIX/lib/libosdCPU.a); skip (--force to rebuild)"
  [ "$DOTEST" = 1 ] && run_test
  exit 0
fi

# --- disk guard (need headroom for the source + object tree) ---
FREE_G="$(df -Pk / | awk 'NR==2{print int($4/1048576)}')"
if [ "${FREE_G:-0}" -lt 8 ]; then
  echo "opensubdiv: ABORT: only ${FREE_G} GiB free on / (need >= 8 GiB)" >&2
  exit 1
fi

# --- prerequisite: TBB in the shared prefix ---
[ -f "$PREFIX/lib/cmake/TBB/TBBConfig.cmake" ] || bash "$ROOT/scripts/deps/tbb.sh"

mkdir -p "$CACHE" "$SCRATCH"
if [ ! -f "$TARBALL" ]; then
  curl -fL --retry 3 -o "$TARBALL" "$OSD_URL"
fi
GOT_MD5="$(md5 -q "$TARBALL" 2>/dev/null || md5sum "$TARBALL" | awk '{print $1}')"
if [ "$GOT_MD5" != "$OSD_MD5" ]; then
  echo "opensubdiv: MD5 mismatch (got $GOT_MD5 want $OSD_MD5)" >&2
  exit 1
fi
rm -rf "$SRC"
tar -xzf "$TARBALL" -C "$SCRATCH"

STAGE="$SCRATCH/install"
BUILD="$SCRATCH/build"
rm -rf "$BUILD" "$STAGE"

# TBB-backed with every native GPU API disabled, while retaining OpenSubdiv's
# API-independent GLSL patch-source data for Blender's WebGPU shader path. No
# GL/GLFW/examples/tests/doc are built. Flags otherwise mirror Blender's
# superbuild opensubdiv.cmake. -pthread + -fexceptions match the TBB consumer
# flags (notes/deps-tbb.md).
emcmake cmake -S "$SRC" -B "$BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$STAGE" \
  -DBUILD_SHARED_LIBS=OFF \
  -DNO_LIB=OFF \
  -DNO_EXAMPLES=ON \
  -DNO_TUTORIALS=ON \
  -DNO_REGRESSION=ON \
  -DNO_PTEX=ON \
  -DNO_DOC=ON \
  -DNO_OMP=ON \
  -DNO_TBB=OFF \
  -DNO_CUDA=ON \
  -DNO_OPENCL=ON \
  -DNO_CLEW=ON \
  -DNO_OPENGL=ON \
  -DOSD_PATCH_SHADER_SOURCE_GLSL=ON \
  -DNO_METAL=ON \
  -DNO_DX=ON \
  -DNO_TESTS=ON \
  -DNO_GLTESTS=ON \
  -DNO_GLEW=ON \
  -DNO_GLFW=ON \
  -DNO_GLFW_X11=ON \
  -DTBB_DIR="$PREFIX/lib/cmake/TBB" \
  -DCMAKE_C_FLAGS="-pthread -fexceptions -Wno-unused-command-line-argument" \
  -DCMAKE_CXX_FLAGS="-pthread -fexceptions -Wno-unused-command-line-argument"

emmake cmake --build "$BUILD" --target install -j"$NPROC"

# --- locate the built static archives in the staging install ---
CPU_LIB="$(find "$STAGE" -name 'libosdCPU.a' | head -1)"
GPU_LIB="$(find "$STAGE" -name 'libosdGPU.a' | head -1)"
INC_DIR="$(dirname "$(find "$STAGE" -path '*/opensubdiv/osd/mesh.h' | head -1)")"
if [ -z "$CPU_LIB" ] || [ ! -f "$CPU_LIB" ]; then
  echo "opensubdiv: build produced no libosdCPU.a under $STAGE" >&2
  exit 1
fi
if [ -z "$GPU_LIB" ] || [ ! -f "$GPU_LIB" ]; then
  echo "opensubdiv: build produced no GLSL patch-source libosdGPU.a under $STAGE" >&2
  exit 1
fi
# INC_DIR is .../include/opensubdiv/osd ; the harvest root is its grandparent.
OSD_INC_ROOT="$(cd "$INC_DIR/../.." && pwd)"   # .../include
if [ ! -f "$OSD_INC_ROOT/opensubdiv/osd/mesh.h" ]; then
  echo "opensubdiv: could not locate installed headers (opensubdiv/osd/mesh.h)" >&2
  exit 1
fi

# --- harvest to the shared prefix (opensubdiv-owned paths ONLY) ---
mkdir -p "$PREFIX/include" "$PREFIX/lib"
rm -rf "$PREFIX/include/opensubdiv"
cp -R "$OSD_INC_ROOT/opensubdiv" "$PREFIX/include/opensubdiv"
cp "$CPU_LIB" "$PREFIX/lib/libosdCPU.a"
cp "$GPU_LIB" "$PREFIX/lib/libosdGPU.a"

[ -f "$PREFIX/lib/libosdCPU.a" ] || { echo "opensubdiv: harvest missing libosdCPU.a" >&2; exit 1; }
[ -f "$PREFIX/lib/libosdGPU.a" ] || { echo "opensubdiv: harvest missing libosdGPU.a" >&2; exit 1; }
[ -f "$PREFIX/include/opensubdiv/osd/mesh.h" ] || { echo "opensubdiv: harvest missing headers" >&2; exit 1; }
verify_gpu_shader_source_archive || {
  echo "opensubdiv: harvested osdGPU fails GLSL-source/no-OpenGL contract" >&2
  exit 1
}
echo "opensubdiv ${OSD_VERSION}: harvested libosdCPU.a + libosdGPU.a + include/opensubdiv to $PREFIX"

run_test

# --- clean the build tree; keep only the harvest + tarball cache ---
rm -rf "$SCRATCH"
echo "opensubdiv: done (build tree removed)"
