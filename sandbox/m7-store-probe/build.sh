#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build the M7 project-store prototype (browser half) under the SAME flag family the
# real browser Blender binary links (patches/platform_wasm.cmake:287-289 — the
# _bw_browser_flags WASMFS profile). A REAL corpus .blend is embedded read-only so
# the probe writes/reads genuine .blend bytes through the OPFS store. Plain emcc, no
# ninja. Invoke through the harness:
#     harness/buildwrap.sh sandbox/m7-store-probe/build.sh
#
# Allocator note: real browser link uses -sMALLOC=dlmalloc (mimalloc overridden due
# to the CPython mimalloc duplicate-symbol clash, platform_wasm.cmake:134-139). This
# probe links no CPython but matches the real browser binary => dlmalloc. Allocator
# is orthogonal to OPFS/WasmFS semantics.
set -euo pipefail
ROOT="/Users/paws/blender-web"
SRC="$ROOT/sandbox/m7-store-probe"
OUT="$SRC/web"
# Real, uncompressed 5.2 .blend from the M1 corpus (magic "BLENDER"), ~2.6 MB.
EMBED_SRC="$ROOT/sandbox/corpus-prep/corpus/mesh_dense.blend"
mkdir -p "$OUT"
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

[ -f "$EMBED_SRC" ] || { echo "MISSING corpus .blend: $EMBED_SRC" >&2; exit 1; }

# Canonical browser profile (platform_wasm.cmake:287-289), minus the preload payload
# and re-homed EXPORT_NAME. This is the profile under test.
PROFILE="-pthread -fexceptions -sMALLOC=dlmalloc -sWASM_BIGINT -sALLOW_MEMORY_GROWTH \
-sINITIAL_MEMORY=536870912 -sPROXY_TO_PTHREAD -sEXIT_RUNTIME=1 -sSTACK_SIZE=8388608 \
-sPTHREAD_POOL_SIZE=8 -sWASMFS -sFORCE_FILESYSTEM=1"
PROFILE_STR="$PROFILE"

echo "== build m7_store_probe (profile: $PROFILE) =="
# shellcheck disable=SC2086
em++ -std=c++20 -funsigned-char $PROFILE \
  -DM7_STORE_PROFILE="\"$PROFILE_STR\"" \
  -DM7_EMBED_BLEND="\"/embed/sample.blend\"" \
  --embed-file "$EMBED_SRC@/embed/sample.blend" \
  -sMODULARIZE=1 -sEXPORT_NAME=createStoreProbe \
  -sEXPORTED_RUNTIME_METHODS=callMain,FS \
  --profiling-funcs \
  "$SRC/m7_store_probe.cc" \
  -o "$OUT/m7_store_probe.js"

echo "LINK OK: $(du -h "$OUT/m7_store_probe.wasm" | awk '{print $1}') wasm -> $OUT/m7_store_probe.js"
