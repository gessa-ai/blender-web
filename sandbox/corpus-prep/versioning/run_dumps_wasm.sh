#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Versioning corpus — WASM-SIDE state-dump parity (blo_do_versions surface).
#
# Runs sandbox/corpus-prep/state_dump.py on the WASM `blender` build (node +
# NODERAWFS) over each old-version .blend in corpus.list, then classifies:
#   PASS             wasm dump == oracle golden, byte-exact (--tolerance 0)
#   DIVERGENCE       wasm dump differs from golden (real readfile/versioning finding)
#   DETECTOR_REFUSED wasm32 ADR-004 pointer-collision detector (patch 0018) refused
#   BE_REFUSE_BOTH   big-endian file; wasm refuses same as the 5.2 oracle (BE removed 5.0)
#   LOAD_FAIL        other load failure (a finding to investigate)
# Every open_mainfile exercises the real wasm readfile + blo_do_versions path, so a
# divergence here is a genuine versioning FINDING, not noise. No raw logs surfaced.
#
# Usage: bash sandbox/corpus-prep/versioning/run_dumps_wasm.sh
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"

PREP=sandbox/corpus-prep
VDIR="$PREP/versioning"
DUMP="$ROOT/$PREP/state_dump.py"
GOLD="$ROOT/$VDIR/goldens"
WOUT="$ROOT/$VDIR/dumps-wasm"
CMP="$ROOT/$PREP/compare_dumps.py"
LIST="$ROOT/$VDIR/corpus.list"
mkdir -p "$WOUT"

NODE="$ROOT/tools/emsdk/node/22.16.0_64bit/bin/node"
BLENDER_JS="$ROOT/build-wasm/bin/blender.js"
export BLENDER_SYSTEM_RESOURCES="$ROOT/upstream"
export BLENDER_SYSTEM_PYTHON="$ROOT/lib/wasm"
export BLENDER_SYSTEM_DATAFILES="$ROOT/upstream/release/datafiles"

# $1=src .blend  $2=out .json  $3=stderr file
wasm_dump() {
  "$NODE" "$BLENDER_JS" --background --factory-startup \
    --python "$DUMP" -- "$1" "$2" >/dev/null 2>"$3"
}
short() { head -1 "$1" 2>/dev/null | sed -E 's#/[^ ]*/##g; s/[[:space:]]+/ /g' | cut -c1-150; }

n_pass=0; n_div=0; n_det=0; n_be=0; n_fail=0
overall_ok=1
echo "== wasm versioning state-dump parity =="
while IFS='|' read -r label src ver ptr endian; do
  case "$label" in \#*|"") continue;; esac
  [ "${src:0:1}" = "/" ] || src="$ROOT/$src"
  out="$WOUT/$label.json"; err="$WOUT/$label.err"; golden="$GOLD/$label.json"
  rm -f "$out"
  if [ ! -f "$src" ]; then echo "MISSING_BLEND $label"; overall_ok=0; continue; fi
  wasm_dump "$src" "$out" "$err"

  detector=$(grep -aiE 'ADR-004|32-bit WebAssembly|wasm32-pointer-collision' "$err" 2>/dev/null | head -1)
  be_msg=$(grep -aiE 'Big Endian|created by a Big' "$err" 2>/dev/null | head -1)

  if [ ! -f "$golden" ]; then
    # No golden (oracle refused — big-endian). Confirm wasm refuses the same way.
    if [ -n "$be_msg" ] && [ ! -s "$out" ]; then
      echo "BE_REFUSE_BOTH  $label (v$ver ptr$ptr $endian) — wasm refuses BE, matches oracle"
      n_be=$((n_be+1))
    else
      echo "UNEXPECTED      $label (v$ver ptr$ptr $endian) — no golden but wasm did not BE-refuse: $(short "$err")"
      overall_ok=0; n_fail=$((n_fail+1))
    fi
    continue
  fi

  # Golden exists (oracle loaded it). Expect wasm to load + match.
  if [ ! -s "$out" ] || grep -q '_dump_error' "$out" 2>/dev/null; then
    if [ -n "$detector" ]; then
      echo "DETECTOR_REFUSED $label (v$ver ptr$ptr $endian) — ADR-004 wasm32 pointer-collision"
      n_det=$((n_det+1))
    else
      echo "LOAD_FAIL       $label (v$ver ptr$ptr $endian) — $(short "$err")"
      overall_ok=0; n_fail=$((n_fail+1))
    fi
    continue
  fi
  if python3 "$CMP" "$golden" "$out" --max 8 >"$WOUT/$label.cmp.txt" 2>&1; then
    h=$(shasum -a 256 "$out" | cut -d' ' -f1)
    echo "PASS            $label (v$ver ptr$ptr $endian) wasm_dump=$h"
    n_pass=$((n_pass+1))
  else
    echo "DIVERGENCE      $label (v$ver ptr$ptr $endian) — first paths:"
    sed 's/^/    /' "$WOUT/$label.cmp.txt" | head -12
    overall_ok=0; n_div=$((n_div+1))
  fi
done < "$LIST"

echo "== summary =="
echo "PASS=$n_pass  DIVERGENCE=$n_div  DETECTOR_REFUSED=$n_det  BE_REFUSE_BOTH=$n_be  LOAD_FAIL=$n_fail"
# DIVERGENCE and LOAD_FAIL are the only non-expected outcomes; DETECTOR_REFUSED and
# BE_REFUSE_BOTH are documented expected-refuse (ADR-004 / BE removed in 5.0).
if [ "$overall_ok" -eq 1 ]; then echo "ALL_EXPECTED"; else echo "HAS_FINDINGS"; exit 1; fi
