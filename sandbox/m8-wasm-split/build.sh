#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build the M8 wasm-split reduced harness with the shipped windowed constraint set
# (-pthread + -sPROXY_TO_PTHREAD + -sMODULARIZE + -fexceptions/JS-EH + no JSPI),
# then split cold_subsystem out to a secondary module with binaryen's wasm-split.
#
# Faithful to patches/platform_wasm.cmake browser target on the load-bearing axes:
#   PROXY_TO_PTHREAD (main on a worker), MODULARIZE/EXPORT_NAME, WASM_BIGINT,
#   -fexceptions (JS-EH, NOT JSPI/Asyncify), ALLOW_MEMORY_GROWTH, dlmalloc.
# Deliberately OMITS WASMFS/emdawnwebgpu: those are orthogonal linked code that
# share memory with the split modules and do not exercise the split mechanism.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/sandbox/m8-wasm-split"
EMCC="$ROOT/tools/emsdk/upstream/emscripten/emcc"
WASM_SPLIT="$ROOT/tools/emsdk/upstream/bin/wasm-split"
WASM_DIS="$ROOT/tools/emsdk/upstream/bin/wasm-dis"
export EMSDK_PYTHON="$ROOT/tools/emsdk/python/3.13.3_64bit/bin/python3"

OUT="$HERE/build"
mkdir -p "$OUT"
cd "$OUT"

echo "== link with SPLIT_MODULE (mirrors windowed constraint set, NO JSPI) =="
# -sSPLIT_MODULE makes emcc emit the loadSplitModule/placeholder JS runtime and
# (via do_split_module) leaves harness.wasm.orig = the full pre-split module.
"$EMCC" "$HERE/harness.c" -O2 -g2 \
  -pthread -fexceptions -sMALLOC=dlmalloc \
  -sWASM_BIGINT -sALLOW_MEMORY_GROWTH -sINITIAL_MEMORY=67108864 \
  -sPROXY_TO_PTHREAD -sSTACK_SIZE=8388608 -sPTHREAD_POOL_SIZE=4 \
  -sMODULARIZE=1 -sEXPORT_NAME=createBlenderModule \
  -sEXPORTED_RUNTIME_METHODS=ccall,cwrap \
  -sEXPORTED_FUNCTIONS=_main,_bw_set_cmd,_bw_get_done_seq,_bw_get_result,_bw_get_boot_done,_bw_get_cold_runs \
  -sSPLIT_MODULE=1 \
  -o harness.js
echo "linked: harness.js / harness.wasm(.orig)"
ls -la harness.wasm harness.wasm.orig 2>/dev/null || true

echo "== split cold_subsystem -> secondary (binaryen wasm-split, --all-features) =="
# Split the ORIGINAL (pre-instrument) module. Keep names (-g) so wasm-split matches
# by symbol. Everything but cold_subsystem stays in the primary.
# (NOTE: --placeholdermap/--symbolmap are parsed as no-arg flags by this binaryen
#  build, so their value becomes a stray second input -> "more than one input
#  file". We read the placeholder namespace from wasm-dis instead.)
# The module carries NO target_features section, so binaryen defaults to MVP; we
# must name the features explicitly. Use exactly the standard, browser-shipped set
# emcc 6.0.5 emits (NOT --all-features, which enables experimental proposals like
# compact-imports = import kind 127 that browsers reject by default).
FEATURES="--enable-sign-ext --enable-mutable-globals --enable-nontrapping-float-to-int \
--enable-bulk-memory --enable-bulk-memory-opt --enable-threads --enable-multivalue \
--enable-reference-types --enable-call-indirect-overlong --enable-extended-const"
# shellcheck disable=SC2086
"$WASM_SPLIT" --split $FEATURES -g \
  --split-funcs cold_subsystem \
  harness.wasm.orig \
  -o1 harness.wasm -o2 harness.SECONDARY.wasm 2>&1 | sed 's/^/  wasm-split: /' || true

echo "== placeholder import namespace (determines the runtime's secondary filename) =="
"$WASM_DIS" harness.wasm 2>/dev/null | grep -m4 'import.*placeholder' | sed 's/^/  /' || true

# The emscripten runtime (src/preamble.js splitModuleProxyHandler) computes the
# secondary URL from the placeholder module name:
#   name == 'placeholder'      -> <base>.deferred.wasm   (old format)
#   name == 'placeholder.<ID>' -> <base>.<ID>.wasm       (new format, split on '.')
# Detect and place the secondary at the exact name the runtime will fetch.
PH_NS="$("$WASM_DIS" harness.wasm 2>/dev/null | grep -o 'import "placeholder[^"]*"' | head -1 | sed 's/import "//;s/"//')"
echo "detected placeholder namespace: '${PH_NS:-<none>}'"
rm -f harness.deferred.wasm harness.*.wasm.SECDROP 2>/dev/null || true
if [ "$PH_NS" = "placeholder" ]; then
  cp harness.SECONDARY.wasm harness.deferred.wasm
  echo "secondary -> harness.deferred.wasm"
elif [ -n "${PH_NS:-}" ]; then
  ID="${PH_NS#placeholder}"; ID="${ID#.}"
  cp harness.SECONDARY.wasm "harness.${ID}.wasm"
  echo "secondary -> harness.${ID}.wasm"
else
  echo "WARN: no placeholder namespace found (no split happened?)"
fi

# --- REQUIRED GLUE PATCH (pthread x SPLIT_MODULE gap in emscripten 6.0.5) ---
# Stock bug: pthread workers instantiate the (placeholder-importing) primary via
# `new WebAssembly.Instance(wasmModule, getWasmImports())` WITHOUT ever running the
# main thread's `wasmBinaryFile ??= findWasmBinary()`. The splitModuleProxyHandler
# then dereferences an undefined `wasmBinaryFile` at instantiation -> every worker
# crashes at boot. findWasmBinary() (=locateFile("harness.wasm")) works on workers
# (scriptDirectory from self.location.href), so a 1-line guard in the proxy handler
# fixes it on every thread. This is the minimal upstream-shaped fix.
python3 - "$OUT/harness.js" <<'PY'
import sys
f=sys.argv[1]; s=open(f).read()
needle="      let secondaryFile;\n"
guard="      let secondaryFile;\n      if (typeof wasmBinaryFile == 'undefined' || !wasmBinaryFile) wasmBinaryFile = findWasmBinary(); // BW pthread-split glue fix\n"
if "BW pthread-split glue fix" in s:
    print("  glue patch already present")
elif needle in s:
    s=s.replace(needle, guard, 1); open(f,'w').write(s); print("  glue patch applied (wasmBinaryFile guard in splitModuleProxyHandler)")
else:
    print("  WARN: proxy handler anchor not found; glue patch NOT applied"); sys.exit(2)
PY

cp "$HERE/shell.html" "$OUT/index.html"
echo "shell -> build/index.html"

echo "== sizes (raw + brotli-q11) =="
for f in harness.wasm.orig harness.wasm harness.SECONDARY.wasm; do
  [ -f "$f" ] || continue
  raw=$(wc -c < "$f")
  br=$(brotli -q 11 -c "$f" | wc -c)
  printf "  %-26s raw=%-10s brotli=%s\n" "$f" "$raw" "$br"
done
echo "DONE"
