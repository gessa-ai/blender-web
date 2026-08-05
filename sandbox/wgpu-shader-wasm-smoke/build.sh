#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Link-smoke for the wasm shader chain (shaderc + Tint in ONE binary).
#   [1] NATIVE reference: link Blender's precompiled shaderc dylib + the native
#       Tint archives (build-dawn/t7pre-build) -> smoke_native -> wgsl_native.txt
#   [2] WASM: link the cross-compiled archives from lib/wasm/{shaderc,tint} in a
#       single --start-group -> smoke.js -> run under node -> wgsl_wasm.txt
#   [3] Assert wasm WGSL is non-empty + contains "@binding", then byte-compare
#       native vs wasm (divergence is a reported finding, not a hard fail).
#
# Run through the harness so logs stay off-context:
#   harness/buildwrap.sh bash sandbox/wgpu-shader-wasm-smoke/build.sh
set -uo pipefail

ROOT="/Users/paws/blender-web"
HERE="$ROOT/sandbox/wgpu-shader-wasm-smoke"
DAWN_SRC="$ROOT/build-dawn/dawn"
NATIVE_BUILD="$ROOT/build-dawn/t7pre-build"
OUT="$ROOT/build-deps/shader-smoke"
mkdir -p "$OUT"

# shellcheck disable=SC1091
source "$ROOT/tools/emsdk/emsdk_env.sh"

WGSL_NATIVE="$OUT/wgsl_native.txt"
WGSL_WASM="$OUT/wgsl_wasm.txt"

########################################################################
# [1] NATIVE reference chain
########################################################################
echo "== [1] native reference (Blender shaderc dylib + native Tint) =="
NATIVE_SHADERC="$ROOT/lib/macos_arm64/shaderc"
# All native Tint + SPIRV-Tools + abseil + dawn util archives (order-insensitive
# under macOS ld64's iterative archive resolution).
NATIVE_ARCHIVES=$(find "$NATIVE_BUILD/dawn/src/tint" "$NATIVE_BUILD/dawn/third_party/spirv-tools" \
  "$NATIVE_BUILD/dawn/third_party/abseil" "$NATIVE_BUILD/dawn/src/utils" \
  -name '*.a' 2>/dev/null | tr '\n' ' ')
if [ -n "$NATIVE_ARCHIVES" ] && [ -f "$NATIVE_SHADERC/lib/libshaderc_shared.dylib" ]; then
  clang++ -std=c++20 -O2 "$HERE/smoke.cc" \
    -I"$NATIVE_SHADERC/include" -I"$DAWN_SRC" \
    $NATIVE_ARCHIVES "$NATIVE_SHADERC/lib/libshaderc_shared.dylib" \
    -Wl,-rpath,"$NATIVE_SHADERC/lib" \
    -o "$OUT/smoke_native" 2> "$OUT/native_link.err"
  if [ -x "$OUT/smoke_native" ]; then
    "$OUT/smoke_native" > "$WGSL_NATIVE" 2> "$OUT/native_run.err"
    echo "native WGSL bytes: $(wc -c < "$WGSL_NATIVE" | tr -d ' ')"
  else
    echo "native reference link FAILED (see $OUT/native_link.err) — continuing to wasm"
  fi
else
  echo "native reference inputs missing — skipping native leg"
fi

########################################################################
# [2] WASM chain — the deliverable
########################################################################
echo "== [2] wasm link (harvested shaderc + tint, single SPIRV-Tools) =="
SHADERC_LIB="$ROOT/lib/wasm/shaderc/lib"
TINT_LIB="$ROOT/lib/wasm/tint/lib"

# Ordered archive set: shaderc first, then tint (which carries the single shared
# SPIRV-Tools). Wrapped in one --start-group so residual cross-references between
# shaderc/glslang/tint/spirv-tools/absl all resolve regardless of order.
GROUP=""
while IFS= read -r a; do GROUP="$GROUP $SHADERC_LIB/$a"; done < "$ROOT/lib/wasm/shaderc/shaderc-archives.txt"
while IFS= read -r a; do GROUP="$GROUP $TINT_LIB/$a"; done < "$ROOT/lib/wasm/tint/tint-archives.txt"

# -sSTACK_SIZE=32MB is LOAD-BEARING: emscripten defaults to a 64 KB stack, which
# glslang's recursive preprocessor/parser and Tint's recursive IR passes overflow
# — the overflow corrupts the heap and surfaces as bogus "function signature
# mismatch" / "invalid free" traps far from the real cause. A shipping browser
# integration MUST give the shader-compile path a multi-MB stack. (Finding: see
# notes/deps-shader-chain.md.)
em++ -std=c++20 -O2 -pthread -fexceptions "$HERE/smoke.cc" \
  -I"$ROOT/lib/wasm/shaderc/include" -I"$DAWN_SRC" \
  -Wl,--start-group $GROUP -Wl,--end-group \
  -sENVIRONMENT=node -sEXIT_RUNTIME=1 \
  -sSTACK_SIZE=33554432 \
  -sINITIAL_MEMORY=536870912 -sPTHREAD_POOL_SIZE=4 -sALLOW_MEMORY_GROWTH=1 \
  -o "$OUT/smoke.js" 2> "$OUT/wasm_link.err"
if [ ! -f "$OUT/smoke.wasm" ]; then
  echo "WASM LINK FAILED — first errors:"
  grep -iE 'error|undefined|duplicate' "$OUT/wasm_link.err" | head -40
  exit 1
fi
echo "wasm link OK: smoke.wasm $(du -h "$OUT/smoke.wasm" | awk '{print $1}')"

echo "== run wasm under node =="
node "$OUT/smoke.js" > "$WGSL_WASM" 2> "$OUT/wasm_run.err"
RC=$?
if [ $RC -ne 0 ]; then
  echo "node run FAILED rc=$RC:"; tail -20 "$OUT/wasm_run.err"; exit 1
fi

########################################################################
# [3] Assertions + byte-compare
########################################################################
WBYTES=$(wc -c < "$WGSL_WASM" | tr -d ' ')
echo "wasm WGSL bytes: $WBYTES"
if [ "$WBYTES" -eq 0 ]; then echo "FAIL: wasm WGSL empty"; exit 1; fi
if ! grep -q '@binding' "$WGSL_WASM"; then echo "FAIL: wasm WGSL has no @binding"; sed -n '1,40p' "$WGSL_WASM"; exit 1; fi
echo "PASS: wasm WGSL non-empty and contains @binding"
echo "--- wasm WGSL ---"; cat "$WGSL_WASM"

if [ -s "$WGSL_NATIVE" ]; then
  if diff -q "$WGSL_NATIVE" "$WGSL_WASM" >/dev/null; then
    echo "PARITY: wasm WGSL is BYTE-IDENTICAL to the native chain"
  else
    echo "DIVERGENCE (finding): wasm vs native WGSL differ — diff:"
    diff "$WGSL_NATIVE" "$WGSL_WASM" | head -60
  fi
else
  echo "native reference unavailable — parity comparison skipped"
fi
