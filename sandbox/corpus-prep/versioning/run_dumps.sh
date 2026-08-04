#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Versioning corpus — ORACLE-SIDE candidate goldens (blo_do_versions surface).
#
# For each old-version .blend in corpus.list: dump state TWICE in SEPARATE
# oracle invocations (same determinism discipline as the original M1.12 corpus),
# assert byte-identical output, stage the golden, accumulate a MANIFEST row.
# Files the pinned 5.2 oracle REFUSES to load (e.g. big-endian, removed in 5.0)
# are recorded as verdict=ORACLE_REFUSE with a one-line reason — a documented
# versioning finding, not a hidden failure. No raw oracle logs are surfaced
# (TOKEN THRIFT): only verdict + hashes + short refuse-reason.
#
# Usage: bash sandbox/corpus-prep/versioning/run_dumps.sh
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"

PREP=sandbox/corpus-prep
VDIR="$PREP/versioning"
DUMP="$PREP/state_dump.py"
GOLD="$VDIR/goldens"
LIST="$VDIR/corpus.list"
SCR="${TMPDIR:-/tmp}/m1vers.$$"
mkdir -p "$GOLD" "$SCR/r1" "$SCR/r2"

MANIFEST="$GOLD/MANIFEST.json"
: > "$SCR/rows.txt"
overall_ok=1

# short refuse-reason extractor: first meaningful line, trimmed, no paths.
refuse_reason() {  # $1 = stderr file
  grep -aoE '(Big Endian[^"]*removed[^"]*|created by a [^"]*version[^"]*|pointer-size[^"]*|sub-8[^"]*|refus[^"]*|failed:[^"]*)' "$1" 2>/dev/null \
    | head -1 | sed -E 's#/[^ ]*/##g; s/[[:space:]]+/ /g' | cut -c1-160
}

while IFS='|' read -r label src ver ptr endian; do
  case "$label" in \#*|"") continue;; esac
  if [ ! -f "$src" ]; then echo "MISSING $label ($src)"; overall_ok=0; continue; fi
  out1="$SCR/r1/$label.json"; out2="$SCR/r2/$label.json"
  err1="$SCR/r1/$label.err"
  rm -f "$out1" "$out2"
  oracle/bpy.sh --python "$DUMP" -- "$src" "$out1" >/dev/null 2>"$err1" || true
  oracle/bpy.sh --python "$DUMP" -- "$src" "$out2" >/dev/null 2>/dev/null || true
  blob=$(shasum -a 256 "$src" | cut -d' ' -f1)
  bytes=$(stat -f %z "$src")

  # REFUSE: oracle produced no (or empty) dump — the loader rejected the file.
  if [ ! -s "$out1" ] || [ ! -s "$out2" ]; then
    reason=$(refuse_reason "$err1"); [ -z "$reason" ] && reason="load produced no dump"
    echo "ORACLE_REFUSE $label (v$ver ptr$ptr $endian) — $reason"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\tORACLE_REFUSE\t%s\n' \
      "$label" "$src" "$ver" "$ptr" "$endian" "$bytes" "$blob" "" "$reason" >> "$SCR/rows.txt"
    continue
  fi
  h1=$(shasum -a 256 "$out1" | cut -d' ' -f1)
  h2=$(shasum -a 256 "$out2" | cut -d' ' -f1)
  nerr=$(grep -c '_dump_error' "$out1" || true)
  if [ "$h1" = "$h2" ] && [ "$nerr" -eq 0 ]; then
    cp "$out1" "$GOLD/$label.json"
    echo "PASS $label (v$ver ptr$ptr $endian) dump=$h1 (blend=${bytes}B)"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\tPASS\t\n' \
      "$label" "$src" "$ver" "$ptr" "$endian" "$bytes" "$blob" "$h1" >> "$SCR/rows.txt"
  else
    overall_ok=0
    echo "NONDET $label run1=$h1 run2=$h2 dump_errors=$nerr"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\tNONDET\t\n' \
      "$label" "$src" "$ver" "$ptr" "$endian" "$bytes" "$blob" "$h1" >> "$SCR/rows.txt"
  fi
done < "$LIST"

python3 - "$SCR/rows.txt" "$MANIFEST" <<'PY'
import json, sys
rows_path, manifest_path = sys.argv[1], sys.argv[2]
files = {}
with open(rows_path) as f:
    for line in f:
        line = line.rstrip("\n")
        if not line: continue
        label, src, ver, ptr, endian, size, blob, dump, verdict, reason = line.split("\t")
        rec = {
            "source_path": src,
            "header_version": ver,
            "ptr_bytes": int(ptr),
            "endian": endian,
            "blend_bytes": int(size),
            "blend_sha256": blob,
            "oracle_verdict": verdict,
        }
        if dump: rec["dump_sha256"] = dump
        if reason: rec["refuse_reason"] = reason
        files[label] = rec
manifest = {
    "schema_version": 1,
    "note": "Versioning corpus candidate goldens (blo_do_versions readfile surface). "
            "Deterministic bpy state-dumps, verified byte-identical across two "
            "independent oracle invocations. Oracle: Blender 5.2.0 LTS build "
            "fbe6228777e7 (matches upstream/PIN). ORACLE_REFUSE rows are files the "
            "pinned 5.2 loader rejects (documented versioning finding).",
    "quant_scale": 1000000,
    "files": {k: files[k] for k in sorted(files)},
}
with open(manifest_path, "w", newline="\n") as f:
    f.write(json.dumps(manifest, sort_keys=True, indent=1)); f.write("\n")
npass = sum(1 for v in files.values() if v["oracle_verdict"] == "PASS")
print("MANIFEST %s files=%d pass=%d" % (manifest_path, len(files), npass))
PY

rm -rf "$SCR"
if [ "$overall_ok" -eq 1 ]; then echo "ALL_OK"; else echo "SOME_NONDET"; exit 1; fi
