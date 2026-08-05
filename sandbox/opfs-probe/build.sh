#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build the M7-prep OPFS/WasmFS probe under the SAME flag family the real browser
# Blender binary links (patches/platform_wasm.cmake:287-289 — the _bw_browser_flags
# WASMFS profile). Plain emcc, no ninja. Invoke through the harness:
#     harness/buildwrap.sh sandbox/opfs-probe/build.sh
#
# Allocator note: the real browser link uses -sMALLOC=dlmalloc (mimalloc is
# overridden there because of the CPython mimalloc duplicate-symbol clash,
# platform_wasm.cmake:134-139; mimalloc is kept only for gtest/host-tool binaries).
# This probe links no CPython, but we match the real browser binary => dlmalloc.
# The allocator is orthogonal to OPFS/WasmFS semantics either way.
set -euo pipefail
ROOT="/Users/paws/blender-web"
SRC="$ROOT/sandbox/opfs-probe"
OUT="$SRC/web"
mkdir -p "$OUT"
source "$ROOT/tools/emsdk/emsdk_env.sh" >/dev/null 2>&1

# The canonical browser profile (platform_wasm.cmake:287-289), minus the preload
# payload (not needed) and re-homed EXPORT_NAME. This is the profile under test.
PROFILE="-pthread -fexceptions -sMALLOC=dlmalloc -sWASM_BIGINT -sALLOW_MEMORY_GROWTH \
-sINITIAL_MEMORY=536870912 -sPROXY_TO_PTHREAD -sEXIT_RUNTIME=1 -sSTACK_SIZE=8388608 \
-sPTHREAD_POOL_SIZE=8 -sWASMFS -sFORCE_FILESYSTEM=1"

# String form embedded in the binary so the probe reports its own tested flags.
PROFILE_STR="$PROFILE"

echo "== build opfs_probe (profile: $PROFILE) =="
# shellcheck disable=SC2086
em++ -std=c++20 -funsigned-char $PROFILE \
  -DOPFS_PROBE_PROFILE="\"$PROFILE_STR\"" \
  -sMODULARIZE=1 -sEXPORT_NAME=createOpfsProbe \
  -sEXPORTED_RUNTIME_METHODS=callMain,FS \
  --profiling-funcs \
  "$SRC/opfs_probe.cc" \
  -o "$OUT/opfs_probe.js"

echo "LINK OK: $(du -h "$OUT/opfs_probe.wasm" | awk '{print $1}') wasm -> $OUT/opfs_probe.js"
