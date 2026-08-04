#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# M1.12 WASM-SIDE corpus state-dump parity (closes M1_CORE_BOOTS).
#
# Runs sandbox/corpus-prep/state_dump.py on the WASM `blender` build (node +
# NODERAWFS) over each of the 9 corpus .blend files, producing dumps to
# dumps-wasm/, then compares each against the oracle candidate goldens with the
# host python3 compare_dumps.py (EXACT mode, --tolerance 0). Also proves wasm-side
# determinism: startup.blend dumped twice in separate node processes must be
# byte-identical. Each open_mainfile exercises the real wasm readfile/DNA path, so
# a divergence here is a genuine readfile/DNA FINDING, not noise.
#
# Boot recipe from notes/m2-python-boot.md (trampoline + fstat shim baked in).
# Usage: bash sandbox/corpus-prep/run_dumps_wasm.sh
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"

PREP=sandbox/corpus-prep
DUMP="$ROOT/$PREP/state_dump.py"
GOLD="$ROOT/$PREP/goldens-candidate"
WASMDUMP="$ROOT/$PREP/dumps-wasm"
CMP="$ROOT/$PREP/compare_dumps.py"
mkdir -p "$WASMDUMP"

NODE="$ROOT/tools/emsdk/node/22.16.0_64bit/bin/node"
BLENDER_JS="$ROOT/build-wasm/bin/blender.js"
export BLENDER_SYSTEM_RESOURCES="$ROOT/upstream"
export BLENDER_SYSTEM_PYTHON="$ROOT/lib/wasm"
export BLENDER_SYSTEM_DATAFILES="$ROOT/upstream/release/datafiles"

# label | source .blend path (same set + order as the oracle run_dumps.sh)
CORPUS=(
  "startup|$ROOT/upstream/release/datafiles/startup.blend"
  "mesh_dense|$ROOT/$PREP/corpus/mesh_dense.blend"
  "modifiers|$ROOT/$PREP/corpus/modifiers.blend"
  "animation|$ROOT/$PREP/corpus/animation.blend"
  "materials_nodes|$ROOT/$PREP/corpus/materials_nodes.blend"
  "curves_text|$ROOT/$PREP/corpus/curves_text.blend"
  "armature|$ROOT/$PREP/corpus/armature.blend"
  "collections_instancing|$ROOT/$PREP/corpus/collections_instancing.blend"
  "stress_mixed|$ROOT/$PREP/corpus/stress_mixed.blend"
)

# $1=src .blend  $2=out .json  -> runs the wasm dumper; returns node exit code.
wasm_dump() {
  "$NODE" "$BLENDER_JS" --background --factory-startup \
    --python "$DUMP" -- "$1" "$2" >/dev/null 2>&1
}

overall_ok=1
echo "== wasm state-dump parity =="
for entry in "${CORPUS[@]}"; do
  label="${entry%%|*}"; src="${entry#*|}"
  out="$WASMDUMP/$label.json"
  goldenf="$GOLD/$label.json"
  if [ ! -f "$src" ];    then echo "MISSING_BLEND  $label ($src)"; overall_ok=0; continue; fi
  if [ ! -f "$goldenf" ]; then echo "MISSING_GOLDEN $label"; overall_ok=0; continue; fi
  rm -f "$out"
  wasm_dump "$src" "$out"
  if [ ! -s "$out" ]; then echo "FAIL $label  (wasm produced no dump)"; overall_ok=0; continue; fi
  if grep -q '_dump_error' "$out"; then echo "FAIL $label  (_dump_error in wasm dump)"; overall_ok=0; continue; fi
  # EXACT compare vs oracle golden (tolerance 0 = the gate).
  if python3 "$CMP" "$goldenf" "$out" --max 8 >"$WASMDUMP/$label.cmp.txt" 2>&1; then
    h=$(shasum -a 256 "$out" | cut -d' ' -f1)
    echo "PASS $label  wasm_dump=$h"
  else
    overall_ok=0
    echo "FAIL $label  (divergence vs golden) — first paths:"
    sed 's/^/    /' "$WASMDUMP/$label.cmp.txt"
  fi
done

# Wasm-side determinism: startup.blend twice in separate node processes.
echo "== wasm determinism (startup.blend x2 separate processes) =="
D1="$WASMDUMP/_det1.json"; D2="$WASMDUMP/_det2.json"
wasm_dump "$ROOT/upstream/release/datafiles/startup.blend" "$D1"
wasm_dump "$ROOT/upstream/release/datafiles/startup.blend" "$D2"
if [ -s "$D1" ] && [ -s "$D2" ] && cmp -s "$D1" "$D2"; then
  echo "DETERMINISM_PASS  $(shasum -a 256 "$D1" | cut -d' ' -f1)"
else
  echo "DETERMINISM_FAIL"; overall_ok=0
  [ -s "$D1" ] && [ -s "$D2" ] && diff <(head -40 "$D1") <(head -40 "$D2") | head -20
fi
rm -f "$D1" "$D2"

if [ "$overall_ok" -eq 1 ]; then echo "ALL_PASS"; else echo "SOME_FAIL"; exit 1; fi
