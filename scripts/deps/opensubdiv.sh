#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build OpenSubdiv (CPU-only, TBB-backed) static for wasm and harvest to lib/wasm.
# Version + hash pinned from
# upstream/build_files/build_environment/cmake/versions.cmake (OPENSUBDIV_VERSION
# v3_7_0, MD5 470d53c4d4335a601c33a052ce7c33b4). Options mirror the Blender
# superbuild's cmake/opensubdiv.cmake, adapted for the browser target: every GPU
# backend (OpenGL/Metal/CUDA/OpenCL/DX) is disabled — there is no GPU API under
# Emscripten — leaving Far/Sdc/Vtr/Bfr + the CPU (incl. TBB) evaluators. TBB comes
# from the shared prefix (scripts/deps/tbb.sh) via TBB_DIR.
#
# GOTCHA (consumer contract): Blender's build_files/cmake/Modules/FindOpenSubdiv.cmake
# resolves TWO components, osdCPU AND osdGPU, and dependency_targets.cmake does
#   target_link_libraries(bf_deps_optional_opensubdiv INTERFACE ${OPENSUBDIV_LIBRARIES})
# so a missing osdGPU injects a literal "-NOTFOUND" link token and breaks configure.
# With all GPU backends off OpenSubdiv emits no GPU object code at all
# (opensubdiv/osd/CMakeLists.txt:404 `if(GPU_SOURCE_FILES)` and
# opensubdiv/CMakeLists.txt:136 `if(OSD_GPU)` are both false), so no libosdGPU.a is
# produced. We therefore harvest the real libosdCPU.a and, when the build emits no
# libosdGPU.a, a VALID EMPTY libosdGPU.a to satisfy the two-component find. This is
# not a stub of behaviour: Blender's GPU-subdivision path (intern/opensubdiv's
# gpu_compute_evaluator.cc / eval_output_gpu.cc) is driven by Blender's own bf::gpu
# module and references NO OpenSubdiv osdGPU symbols, so the empty archive links
# cleanly and nothing that runs depends on GPU-side OpenSubdiv code.
#
# Idempotent: no-op once lib/wasm/lib/libosdCPU.a is present (--force to rebuild,
# --test to (re)run the Far cube-refine smoke). Deletes the build tree after harvest.
set -euo pipefail

ROOT="/Users/paws/blender-web"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/opensubdiv"
CACHE="$ROOT/build-deps/_cache"
NPROC="$(sysctl -n hw.ncpu)"

OSD_VERSION="v3_7_0"
OSD_URL="https://github.com/PixarAnimationStudios/OpenSubdiv/archive/${OSD_VERSION}.tar.gz"
OSD_MD5="470d53c4d4335a601c33a052ce7c33b4"
TARBALL="$CACHE/opensubdiv-${OSD_VERSION}.tar.gz"
SRC="$SCRATCH/OpenSubdiv-3_7_0"

FORCE=0; DOTEST=0
for a in "$@"; do case "$a" in --force) FORCE=1;; --test) DOTEST=1;; esac; done

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

run_test() {
  local v="$SCRATCH/verify"
  mkdir -p "$v"
  # Far-only functional test: Catmull-Clark refine a cube one level and print the
  # vertex count. A cube (8v/6 quads) at level 1 -> 8 orig + 12 edge-pts + 6
  # face-pts = 26 verts. Exercises far/vtr/sdc from libosdCPU.a on wasm+node.
  cat > "$v/t.cpp" <<'EOF'
#include <cstdio>
#include <opensubdiv/far/topologyRefinerFactory.h>
#include <opensubdiv/far/topologyDescriptor.h>
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
  printf("OSD_WASM_REFINE nverts_level1=%d\n", nv);
  return nv == 26 ? 0 : 1;
}
EOF
  em++ -std=c++17 -pthread -fexceptions -I "$PREFIX/include" \
    "$v/t.cpp" "$PREFIX/lib/libosdCPU.a" "$PREFIX/lib/libtbb.a" \
    -sPROXY_TO_PTHREAD -sPTHREAD_POOL_SIZE=4 -sEXIT_RUNTIME=1 \
    -sINITIAL_MEMORY=134217728 -sWASM_BIGINT -o "$v/t.js"
  test -f "$v/t.wasm"
  node "$v/t.js" | tee "$v/t.out"
  grep -q "OSD_WASM_REFINE nverts_level1=26" "$v/t.out"
  echo "opensubdiv: Far cube-refine smoke OK (level-1 verts=26)"
}

if [ "$FORCE" = 0 ] && [ -f "$PREFIX/lib/libosdCPU.a" ] && [ -f "$PREFIX/lib/libosdGPU.a" ]; then
  echo "opensubdiv: already installed ($PREFIX/lib/libosdCPU.a) — skip (--force to rebuild)"
  [ "$DOTEST" = 1 ] && run_test
  exit 0
fi

# --- disk guard (need headroom for the source + object tree) ---
FREE_G="$(df -g / | awk 'NR==2{print $4}')"
if [ "${FREE_G:-0}" -lt 8 ]; then
  echo "opensubdiv: ABORT — only ${FREE_G} GiB free on / (need >= 8 GiB)" >&2
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

# CPU-only, TBB-backed, no GPU/GL/GLFW/examples/tests/doc. Flags mirror the Blender
# superbuild opensubdiv.cmake with every GPU backend forced OFF for wasm. -pthread
# + -fexceptions match the TBB consumer flags (notes/deps-tbb.md).
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
if [ -n "$GPU_LIB" ] && [ -f "$GPU_LIB" ]; then
  cp "$GPU_LIB" "$PREFIX/lib/libosdGPU.a"
  echo "opensubdiv: harvested real libosdGPU.a (a GPU backend was enabled)"
else
  # No GPU object code exists in a CPU-only build; emit a valid empty archive so the
  # two-component FindOpenSubdiv resolves (see GOTCHA note above). Nothing at runtime
  # references osdGPU symbols in this headless build.
  rm -f "$PREFIX/lib/libosdGPU.a"
  emar rcs "$PREFIX/lib/libosdGPU.a"
  echo "opensubdiv: emitted empty libosdGPU.a (CPU-only build; no GPU object code)"
fi

[ -f "$PREFIX/lib/libosdCPU.a" ] || { echo "opensubdiv: harvest missing libosdCPU.a" >&2; exit 1; }
[ -f "$PREFIX/lib/libosdGPU.a" ] || { echo "opensubdiv: harvest missing libosdGPU.a" >&2; exit 1; }
[ -f "$PREFIX/include/opensubdiv/osd/mesh.h" ] || { echo "opensubdiv: harvest missing headers" >&2; exit 1; }
echo "opensubdiv ${OSD_VERSION}: harvested libosdCPU.a + libosdGPU.a + include/opensubdiv to $PREFIX"

run_test

# --- clean the build tree; keep only the harvest + tarball cache ---
rm -rf "$SCRATCH"
echo "opensubdiv: done (build tree removed)"
