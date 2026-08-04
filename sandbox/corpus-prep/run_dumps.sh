#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# M1.12 candidate-golden pipeline (ORACLE-SIDE).
#
# For each corpus .blend: dump state TWICE in SEPARATE oracle invocations,
# assert byte-identical output (determinism proof), stage the golden, and
# accumulate MANIFEST rows.  No raw oracle logs are surfaced (TOKEN THRIFT):
# only PASS/FAIL and hashes are printed.
#
# Usage: bash sandbox/corpus-prep/run_dumps.sh
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

PREP=sandbox/corpus-prep
DUMP="$PREP/state_dump.py"
GOLD="$PREP/goldens-candidate"
SCR="${TMPDIR:-/tmp}/m1corpus.$$"
mkdir -p "$GOLD" "$SCR/r1" "$SCR/r2"

# corpus label | source .blend path
CORPUS=(
  "startup|upstream/release/datafiles/startup.blend"
  "mesh_dense|$PREP/corpus/mesh_dense.blend"
  "modifiers|$PREP/corpus/modifiers.blend"
  "animation|$PREP/corpus/animation.blend"
  "materials_nodes|$PREP/corpus/materials_nodes.blend"
  "curves_text|$PREP/corpus/curves_text.blend"
  "armature|$PREP/corpus/armature.blend"
  "collections_instancing|$PREP/corpus/collections_instancing.blend"
  "stress_mixed|$PREP/corpus/stress_mixed.blend"
)

MANIFEST="$GOLD/MANIFEST.json"
: > "$SCR/rows.txt"
overall_ok=1

for entry in "${CORPUS[@]}"; do
  label="${entry%%|*}"
  src="${entry#*|}"
  if [ ! -f "$src" ]; then
    echo "MISSING $label ($src)"; overall_ok=0; continue
  fi
  out1="$SCR/r1/$label.json"
  out2="$SCR/r2/$label.json"
  # Two independent oracle processes.
  oracle/bpy.sh --python "$DUMP" -- "$src" "$out1" >/dev/null 2>&1
  oracle/bpy.sh --python "$DUMP" -- "$src" "$out2" >/dev/null 2>&1
  h1=$(shasum -a 256 "$out1" | cut -d' ' -f1)
  h2=$(shasum -a 256 "$out2" | cut -d' ' -f1)
  blob=$(shasum -a 256 "$src" | cut -d' ' -f1)
  bytes=$(stat -f %z "$src")
  nerr=$(grep -c '_dump_error' "$out1" || true)
  if [ "$h1" = "$h2" ] && [ "$nerr" -eq 0 ]; then
    cp "$out1" "$GOLD/$label.json"
    echo "PASS $label  dump=$h1  (blend=${bytes}B)"
    printf '%s\t%s\t%s\t%s\t%s\n' "$label" "$src" "$bytes" "$blob" "$h1" >> "$SCR/rows.txt"
  else
    overall_ok=0
    echo "FAIL $label  run1=$h1 run2=$h2 dump_errors=$nerr"
  fi
done

# Emit MANIFEST.json (deterministic key order).
python3 - "$SCR/rows.txt" "$MANIFEST" <<'PY'
import json, sys, hashlib
rows_path, manifest_path = sys.argv[1], sys.argv[2]
files = {}
with open(rows_path) as f:
    for line in f:
        line = line.rstrip("\n")
        if not line:
            continue
        label, src, size, blob, dump = line.split("\t")
        files[label] = {
            "source_path": src,
            "blend_bytes": int(size),
            "blend_sha256": blob,
            "dump_sha256": dump,
        }
manifest = {
    "schema_version": 1,
    "note": "M1.12 candidate goldens. Deterministic bpy state-dumps, "
            "verified byte-identical across two independent oracle invocations. "
            "Oracle: Blender 5.2.0 LTS build fbe6228777e7 (matches upstream/PIN).",
    "quant_scale": 1000000,
    "files": {k: files[k] for k in sorted(files)},
}
with open(manifest_path, "w", newline="\n") as f:
    f.write(json.dumps(manifest, sort_keys=True, indent=1))
    f.write("\n")
print("MANIFEST", manifest_path, "files=%d" % len(files))
PY

rm -rf "$SCR"
if [ "$overall_ok" -eq 1 ]; then
  echo "ALL_PASS"
else
  echo "SOME_FAIL"; exit 1
fi
