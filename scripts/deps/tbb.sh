#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: Apache-2.0
#
# M1.7 — build oneTBB (Blender's pinned v2022.3.0) static for wasm and install to
# lib/wasm. Idempotent: skips if libtbb.a already present (pass --force to rebuild,
# --test to (re)run the parallel_for smoke test). See notes/deps-tbb.md for the
# load-bearing consumer flags (-pthread -fexceptions -sPROXY_TO_PTHREAD ...).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="$ROOT/lib/wasm"
SCRATCH="$ROOT/build-deps/tbb"
VER="v2022.3.0"
MD5="2b242c465b194ac8e1451ea1354873ae"
URL="https://github.com/uxlfoundation/oneTBB/archive/refs/tags/${VER}.tar.gz"
SRC="$SCRATCH/oneTBB-${VER#v}"

FORCE=0; DOTEST=0
for a in "$@"; do case "$a" in --force) FORCE=1;; --test) DOTEST=1;; esac; done

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

run_test() {
  local t="$SCRATCH/tbb_smoke.js"
  local max_concurrency sum expected chunks shared_memories
  em++ -std=c++17 -pthread -fexceptions -I "$PREFIX/include" \
    "$ROOT/sandbox/tbb_smoke.cpp" "$PREFIX/lib/libtbb.a" \
    -sPROXY_TO_PTHREAD -sPTHREAD_POOL_SIZE=8 -sEXIT_RUNTIME=1 \
    -sINITIAL_MEMORY=134217728 -sWASM_BIGINT -o "$t"
  "${EMSDK_NODE:?emsdk_env.sh did not set EMSDK_NODE}" "$t" | tee "$SCRATCH/tbb_smoke.out"
  max_concurrency="$(sed -n 's/^max_concurrency=//p' "$SCRATCH/tbb_smoke.out")"
  read -r sum expected chunks < <(
    sed -n 's/^sum=\([0-9][0-9]*\) expected=\([0-9][0-9]*\) chunks=\([0-9][0-9]*\)$/\1 \2 \3/p' \
      "$SCRATCH/tbb_smoke.out"
  )
  [[ "$max_concurrency" =~ ^[0-9]+$ ]] && [ "$max_concurrency" -gt 1 ]
  [ "$sum" = "499999500000" ] && [ "$expected" = "$sum" ] && [ "$chunks" -gt 1 ]
  [ "$(grep -c -x TBB_WASM_OK "$SCRATCH/tbb_smoke.out")" -eq 1 ]
  grep -q 'SharedArrayBuffer' "$t"
  grep -q 'var entryFunction = __emscripten_proxy_main;' "$t"
  shared_memories="$("$ROOT/tools/emsdk/upstream/bin/wasm-dis" "${t%.js}.wasm" | grep -c ' shared')"
  [ "$shared_memories" -gt 0 ]
  rm -f "$t" "${t%.js}.wasm"
}

if [ "$FORCE" = 0 ] && [ -f "$PREFIX/lib/libtbb.a" ]; then
  echo "tbb: already installed at $PREFIX/lib/libtbb.a (skip; --force to rebuild)"
  [ "$DOTEST" = 1 ] && run_test
  exit 0
fi

mkdir -p "$SCRATCH"
cd "$SCRATCH"
if [ ! -f "oneTBB-${VER}.tar.gz" ]; then
  curl -sL -o "oneTBB-${VER}.tar.gz" "$URL"
fi
GOT="$(md5 -q "oneTBB-${VER}.tar.gz" 2>/dev/null || md5sum "oneTBB-${VER}.tar.gz" | awk '{print $1}')"
[ "$GOT" = "$MD5" ] || { echo "tbb: MD5 mismatch got=$GOT want=$MD5"; exit 1; }
rm -rf "$SRC"; tar xzf "oneTBB-${VER}.tar.gz"

mkdir -p "$SRC/build"; cd "$SRC/build"
emcmake cmake .. \
  -DCMAKE_C_COMPILER=emcc -DCMAKE_CXX_COMPILER=em++ \
  -DTBB_STRICT=OFF \
  -DCMAKE_C_FLAGS="-pthread -Wno-unused-command-line-argument" \
  -DCMAKE_CXX_FLAGS="-pthread -Wno-unused-command-line-argument" \
  -DTBB_DISABLE_HWLOC_AUTOMATIC_SEARCH=ON \
  -DBUILD_SHARED_LIBS=OFF \
  -DTBBMALLOC_BUILD=ON -DTBBMALLOC_PROXY_BUILD=OFF \
  -DTBB_TEST=OFF -DTBB_EXAMPLES=OFF \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX"
emmake cmake --build . --target install -j4

[ -f "$PREFIX/lib/libtbb.a" ] || { echo "tbb: install produced no libtbb.a"; exit 1; }
echo "tbb: installed $PREFIX/lib/libtbb.a"

run_test

# Clean scratch source/build tree; keep only installed artifacts + the tarball cache.
rm -rf "$SRC"
echo "tbb: done (scratch source tree removed)"
