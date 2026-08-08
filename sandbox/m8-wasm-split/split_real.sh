#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Measure a REAL wasm-split of the shipped Blender module by a concrete cold-at-boot
# subsystem set. Tool-only, NO relink: operates on the RelWithDebInfo twin
# (build-wasm-windowed) which carries the name section wasm-split needs to match by
# symbol. HONEST CAVEAT: the twin is -O2 -g (asserts present, no -DNDEBUG); its CODE
# is ~86.98 MB vs the shipped Release wire's 78.11 MB (~+11%), so the primary/
# secondary brotli here is a CONSERVATIVE OVERESTIMATE of the real wire. Cross-checked
# against RANKING.md's independent per-subsystem attribution of the actual opt module.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/sandbox/m8-wasm-split"
WS="$ROOT/tools/emsdk/upstream/bin/wasm-split"
NM="$ROOT/tools/emsdk/upstream/bin/llvm-nm"
TWIN="$ROOT/build-wasm-windowed/bin/blender_browser.wasm"
OUT="$HERE/real-split"; mkdir -p "$OUT"; cd "$OUT"
FEATURES="--enable-sign-ext --enable-mutable-globals --enable-nontrapping-float-to-int \
--enable-bulk-memory --enable-bulk-memory-opt --enable-threads --enable-multivalue \
--enable-reference-types --enable-call-indirect-overlong --enable-extended-const"

br() { brotli -q 11 -c "$1" | wc -c; }
row() { printf "  %-30s raw=%-11s brotli=%s\n" "$1" "$(wc -c < "$2")" "$(br "$2")"; }

echo "== 1. strip DWARF from the twin (keep name section) =="
python3 "$HERE/wasm_section_filter.py" "$TWIN" namebearing.wasm --drop-prefix .debug_ 2>&1 | sed 's/^/  /'

echo "== 2. nm listings (mangled + demangled) =="
"$NM" --print-size namebearing.wasm > nm_plain.txt 2>/dev/null || true
"$NM" --print-size --demangle namebearing.wasm > nm_demangled.txt 2>/dev/null || true
echo "  nm_plain lines: $(wc -l < nm_plain.txt), nm_demangled lines: $(wc -l < nm_demangled.txt)"

echo "== 3. cold-at-boot function set =="
python3 "$HERE/cold_set.py" nm_plain.txt nm_demangled.txt coldfuncs.txt | sed 's/^/  /'

echo "== 4. baseline: whole module stripped to -g0 wire (twin, cross-check vs 21.27 MB shipped) =="
python3 "$HERE/wasm_section_filter.py" namebearing.wasm whole_g0.wasm --drop-name name --drop-prefix .debug_ 2>/dev/null
row "whole (twin, -g0 wire)" whole_g0.wasm

echo "== 5. wasm-split: cold set -> secondary =="
# shellcheck disable=SC2086
"$WS" --split $FEATURES -g --split-funcs @coldfuncs.txt \
  namebearing.wasm -o1 primary.wasm -o2 secondary.wasm 2>&1 | sed 's/^/  wasm-split: /' | tail -5 || true

echo "== 6. strip name section from primary & secondary -> wire binaries =="
python3 "$HERE/wasm_section_filter.py" primary.wasm   primary_g0.wasm   --drop-name name 2>/dev/null
python3 "$HERE/wasm_section_filter.py" secondary.wasm secondary_g0.wasm --drop-name name 2>/dev/null

echo "== 7. RESULT (raw + brotli-q11) =="
row "primary  (boot wasm, -g0)"   primary_g0.wasm
row "secondary(deferred, -g0)"    secondary_g0.wasm
PB=$(br primary_g0.wasm); SB=$(br secondary_g0.wasm); WB=$(br whole_g0.wasm)
echo "  ---"
printf "  whole=%s  primary=%s  secondary=%s  (brotli-q11 bytes)\n" "$WB" "$PB" "$SB"
python3 - "$WB" "$PB" "$SB" <<'PY'
import sys
w,p,s=map(int,sys.argv[1:4]); MB=1e6
print(f"  whole {w/MB:.2f} MB -> primary {p/MB:.2f} MB + secondary {s/MB:.2f} MB")
print(f"  primary is {p/MB - 15:.2f} MB {'OVER' if p/MB>15 else 'UNDER'} the 15 MB bar (twin/RelWithDebInfo; real wire ~11% smaller)")
print(f"  cold-cut removed {(w-p)/MB:.2f} MB brotli from the boot wasm")
PY
echo "DONE"
