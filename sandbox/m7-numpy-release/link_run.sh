#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Link + run the numpy release-mode verification gate (embed_zeros.c) against a given
# libnumpy.a archive, under either the single-threaded (st) or the blender-matching threaded
# (mt: -pthread -sPROXY_TO_PTHREAD -sMALLOC=mimalloc) profile. The mt profile reproduces the
# m7 abort condition (PyGILState_Check false-fires on the proxied main). Args:
#   link_run.sh <archive.a> <st|mt> <tag>
set -uo pipefail
ROOT=/Users/paws/blender-web
cd "$ROOT/sandbox/m7-numpy-release"
# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1
ARCHIVE="$1"; MODE="$2"; TAG="$3"
NODE="$(ls -d "$ROOT"/tools/emsdk/node/*/bin/node | head -1)"

COMMON=(-O1 -fexceptions -matomics -mbulk-memory
  -I"$ROOT/lib/wasm/include/python3.13"
  embed_zeros.c "$ARCHIVE" "$ROOT/lib/wasm/lib/libpython3.13.a"
  -sWASM_BIGINT -sALLOW_MEMORY_GROWTH -sINITIAL_MEMORY=536870912
  -sSTACK_SIZE=8388608 -sNODERAWFS -sEXIT_RUNTIME=1
  -sERROR_ON_UNDEFINED_SYMBOLS=1 --use-port=zlib
  --pre-js "$ROOT/patches/node-fstat-shim.js")
if [ "$MODE" = mt ]; then
  # -sPROXY_TO_PTHREAD (main proxied to a worker) is what makes PyGILState_Check false-fire —
  # the m7 abort condition. Malloc impl is irrelevant to it; use dlmalloc to avoid clashing with
  # the mimalloc CPython 3.13 vendors inside libpython3.13.a.
  EXTRA=(-pthread -sPROXY_TO_PTHREAD -sPTHREAD_POOL_SIZE=8 -sMALLOC=dlmalloc)
else
  EXTRA=(-sMALLOC=dlmalloc)
fi

echo "=== linking embed_${TAG} (mode=$MODE, archive=$(basename "$ARCHIVE")) ==="
emcc "${COMMON[@]}" "${EXTRA[@]}" -o "embed_${TAG}.js" || { echo "LINK FAIL ($TAG)"; exit 2; }
echo "linked embed_${TAG}.wasm ($(ls -la embed_${TAG}.wasm | awk '{print $5}') bytes)"
echo "=== running embed_${TAG} under node ==="
"$NODE" "embed_${TAG}.js"; rc=$?
echo "EXIT_${TAG}=$rc"
