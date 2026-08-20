#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# M6 Cycles-CPU suite — WASM SIDE runner (host driver, ONE BLEND PER node INVOCATION).
#
# Weans the Cycles-CPU render subset off cycles_render_tests.py (which spawns
# Blender subprocesses + multiprocessing, unavailable in single-process wasm
# python). Iterates manifest.tsv's `cycles` rows; per test drives ONE node
# invocation of the wasm Blender binary rendering frame 1 of the blend on
# Cycles-CPU (render_test.py), then compares the wasm PNG against the staged
# golden with Blender's OWN pinned oiiotool threshold for that dir. PASS/FAIL is
# the oiiotool EXIT CODE (exit-code-primary, the m2b/first-render pattern):
#   oiiotool <golden> <wasm.png> --fail <thr> --failpercent <fp> --diff   (exit 0 => within tolerance)
# Crash isolation is by construction: one OS process per test.
#
# Emits one immutable, artifact-bound run tree. Every row is rendered and its
# PNG/comparator receipt is retained, including blacklist candidates. A measured
# comparator failure may become SKIP; a blacklisted row that now passes is STALE
# and fails the run.
#
# Usage:
#   bash sandbox/m6-prep/run_wasm_cycles.sh <unique-label> [--filter <substr>] [--limit N] [--threads N]
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"
MP=sandbox/m6-prep

NODE="${NODE:-$ROOT/tools/emsdk/node/22.16.0_64bit/bin/node}"
BIN="${WASM_BLENDER:-$ROOT/build-wasm-cycles/bin/blender.js}"
OIIO="${OIIOTOOL:-oiiotool}"
DRIVER="$ROOT/$MP/wasm-first-render/render_test.py"
ADDON_PARENT="$ROOT/$MP/wasm-first-render/addon"
MAN="$ROOT/$MP/manifest.tsv"
BLK="$ROOT/$MP/blacklist.txt"
RUNNER="$ROOT/$MP/run_wasm_cycles.sh"
if [[ "${1:-}" == "--selfcheck" ]]; then
  rows=$(awk -F '\t' '$1 == "cycles" {count++} END {print count+0}' "$MAN")
  exclusions=$(awk '$1 == "cycles" {count++} END {print count+0}' "$BLK")
  [[ "$rows" == 27 && "$exclusions" == 2 ]] || {
    echo "SELF_CHECK_FAIL rows=$rows exclusions=$exclusions" >&2
    exit 1
  }
  echo "SELF_CHECK_PASS runner=cycles-wasm-suite immutable=1 rows=27 measured_blacklist=2 retained_comparators=1"
  exit 0
fi
LABEL="${1:-}"
if [[ -z "$LABEL" || ! "$LABEL" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "usage: $0 <unique-label> [--filter <substr>] [--limit N] [--threads N]" >&2
  exit 2
fi
shift
RUNS_ROOT="$ROOT/$MP/cycles-runs"
RUN_ROOT="$RUNS_ROOT/$LABEL"
RESULTS="$RUN_ROOT/results.tsv"
RENDERS="$RUN_ROOT/renders"
LOGS="$RUN_ROOT/logs"
COMPARATORS="$RUN_ROOT/comparators"

# Blender source-tree resource env (source tree, not an installed prefix); same
# as the first-wasm-render invocation (notes/m6-first-wasm-render.md).
export BLENDER_SYSTEM_RESOURCES="$ROOT/upstream"
export BLENDER_SYSTEM_PYTHON="$ROOT/lib/wasm"
export BLENDER_SYSTEM_DATAFILES="$ROOT/upstream/release/datafiles"
export M6_CYCLES_ADDON_PARENT="$ADDON_PARENT"

FILT_SUB=""; LIMIT=0; THREADS="${M6_THREADS:-1}"
while [ $# -gt 0 ]; do case "$1" in
  --filter) FILT_SUB="$2"; shift 2;;
  --limit)  LIMIT="$2"; shift 2;;
  --threads) THREADS="$2"; shift 2;;
  *) echo "unknown arg: $1"; exit 2;;
esac; done
export M6_THREADS="$THREADS"

[ -f "$NODE" ] || { echo "NODE_MISSING $NODE"; exit 2; }
[ -f "$BIN" ]  || { echo "WASM_BIN_MISSING $BIN"; exit 2; }
WASM="${BIN%.js}.wasm"
[ -f "$WASM" ] || { echo "WASM_BINARY_MISSING $WASM"; exit 2; }
command -v "$OIIO" >/dev/null || { echo "OIIOTOOL_MISSING $OIIO"; exit 2; }
[ -f "$MAN" ]  || { echo "NO_MANIFEST"; exit 2; }

# blacklist match (same rules as run_oracle_renders.sh): engine==field or '*', re.match on <test>.blend
is_blacklisted() { # $1=engine $2=test
  [ -f "$BLK" ] || return 1
  local eng test line be re
  eng="$1"; test="$2.blend"
  while IFS= read -r line; do
    case "$line" in ''|\#*) continue;; esac
    be="${line%%[[:space:]]*}"; re="$(echo "${line#"$be"}" | sed -E 's/^[[:space:]]+//; s/[[:space:]]*#.*$//')"
    [ "$be" = "$eng" ] || [ "$be" = "*" ] || continue
    [ -n "$re" ] || continue
    echo "$test" | grep -Eq "^$re" && return 0
  done < "$BLK"
  return 1
}

# is a blend materialized (not an LFS pointer)?
have_input() { # $1=blend(rel)
  local f="$ROOT/$1"
  [ -f "$f" ] || return 1
  head -c 64 "$f" | grep -qa 'git-lfs' && return 1
  return 0
}

now() { python3 -c 'import time;print(time.time())'; }
sha() { shasum -a 256 "$1" | awk '{print $1}'; }

# Bind the exact executable pair before the first row; the final receipt also
# rejects any mid-run artifact drift.
START_JS_SHA=$(sha "$BIN")
START_JS_BYTES=$(wc -c < "$BIN" | tr -d ' ')
START_WASM_SHA=$(sha "$WASM")
START_WASM_BYTES=$(wc -c < "$WASM" | tr -d ' ')

mkdir -p "$RUNS_ROOT"
if [[ -e "$RUN_ROOT" ]]; then
  echo "refusing to overwrite existing Cycles run: $RUN_ROOT" >&2
  exit 3
fi
if ! mkdir "$RUN_ROOT"; then
  echo "refusing concurrent/reused Cycles run: $RUN_ROOT" >&2
  exit 3
fi
mkdir "$RENDERS" "$LOGS" "$COMPARATORS"

printf 'test\trender_s\tnode_exit\tdiff_exit\tverdict\tmax_err\tpct_over\tnote\tinput_sha256\tgolden_sha256\trender_sha256\tthreshold\tfail_percent\tcomparator_sha256\n' > "$RESULTS"

pass=0; fail=0; skip=0; stale=0; blocked=0; n=0
echo "== M6 wasm Cycles-CPU comparator (threads=$THREADS) =="
while IFS=$'\t' read -r engine dir test blend golden thr fp; do
  case "$engine" in ''|\#*) continue;; esac
  [ "$engine" = cycles ] || continue
  [ -z "$FILT_SUB" ] || case "$dir/$test" in *"$FILT_SUB"*) : ;; *) continue;; esac
  [ "$LIMIT" = 0 ] || [ "$n" -lt "$LIMIT" ] || break
  n=$((n+1))

  blacklisted=0
  is_blacklisted "$engine" "$test" && blacklisted=1
  if ! have_input "$blend"; then
    echo "BLOCKED $dir/$test (LFS pointer/missing)"; blocked=$((blocked+1))
    printf '%s\t-\t-\t-\tBLOCKED\t-\t-\tinput-not-materialized\t-\t-\t-\t%s\t%s\t-\n' "$dir/$test" "$thr" "$fp" >> "$RESULTS"; continue
  fi

  mkdir -p "$RENDERS/$dir" "$LOGS/$dir" "$COMPARATORS/$dir"
  base="$RENDERS/$dir/$test"
  log="$LOGS/$dir/$test.log"
  # write_still saves render.filepath + ext verbatim (no frame padding) -> <base>.png
  png="${base}.png"
  rm -f "$png"
  export M6_OUT_BASE="$base"

  t0=$(now)
  "$NODE" "$BIN" --background --factory-startup "$ROOT/$blend" --python "$DRIVER" > "$log" 2>&1
  nec=$?
  t1=$(now)
  rt=$(python3 -c "print(f'{$t1-$t0:.1f}')")

  if [ ! -s "$png" ]; then
    # render failed — extract ONE short reason token (no raw logs)
    note=$(grep -aoE 'M6T_ENGINE_FAIL|ModuleNotFoundError|MemoryError|Aborted\(|RuntimeError|out of memory|Segmentation|Error: |unable to open|Calling abort' "$log" | head -1)
    [ -n "$note" ] || note="no-png"
    echo "FAIL $dir/$test (render: ${note}) ${rt}s"
    printf '%s\t%s\t%s\t-\tFAIL\t-\t-\trender:%s\t%s\t%s\t-\t%s\t%s\t-\n' \
      "$dir/$test" "$rt" "$nec" "$note" "$(sha "$ROOT/$blend")" "$(sha "$ROOT/$golden")" "$thr" "$fp" >> "$RESULTS"
    fail=$((fail+1)); continue
  fi

  diffout=$("$OIIO" "$ROOT/$golden" "$png" --fail "$thr" --failpercent "$fp" --diff 2>&1); dec=$?
  comparator="$COMPARATORS/$dir/$test.txt"
  printf '%s\n' "$diffout" > "$comparator"
  maxe=$(echo "$diffout" | grep -aoE 'Max error *= *[0-9.e+-]+' | head -1 | grep -aoE '[0-9.e+-]+$')
  over=$(echo "$diffout" | grep -aoE '\([0-9.]+% *\) *over' | grep -aoE '[0-9.]+%' | tail -1)
  [ -n "$maxe" ] || maxe="-"; [ -n "$over" ] || over="-"
  if [ "$dec" = 0 ]; then
    if [ "$blacklisted" = 1 ]; then
      echo "STALE $dir/$test (blacklist now passes) max=$maxe over=$over ${rt}s"
      verdict=STALE; note=blacklist-stale; stale=$((stale+1))
    else
      echo "PASS $dir/$test  max=$maxe over=$over  ${rt}s"
      verdict=PASS; note=-; pass=$((pass+1))
    fi
  else
    if [ "$blacklisted" = 1 ]; then
      echo "SKIP $dir/$test  max=$maxe over=$over  ${rt}s (measured blacklist)"
      verdict=SKIP; note=blacklist; skip=$((skip+1))
    else
      echo "FAIL $dir/$test  max=$maxe over=$over  ${rt}s (pixel drift)"
      verdict=FAIL; note=pixel-drift; fail=$((fail+1))
    fi
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$dir/$test" "$rt" "$nec" "$dec" "$verdict" "$maxe" "$over" "$note" \
    "$(sha "$ROOT/$blend")" "$(sha "$ROOT/$golden")" "$(sha "$png")" "$thr" "$fp" "$(sha "$comparator")" >> "$RESULTS"
done < "$MAN"

artifact_stable=1
[[ "$(sha "$BIN")" == "$START_JS_SHA" && "$(wc -c < "$BIN" | tr -d ' ')" == "$START_JS_BYTES" \
   && "$(sha "$WASM")" == "$START_WASM_SHA" && "$(wc -c < "$WASM" | tr -d ' ')" == "$START_WASM_BYTES" ]] \
  || artifact_stable=0

python3 - "$RUN_ROOT/provenance.json" "$LABEL" "$BIN" "$MAN" "$BLK" "$RUNNER" "$DRIVER" "$ADDON_PARENT" "$RESULTS" \
  "$START_JS_SHA" "$START_JS_BYTES" "$START_WASM_SHA" "$START_WASM_BYTES" "$artifact_stable" \
  "$pass" "$fail" "$skip" "$stale" "$blocked" <<'PY'
import hashlib, json, pathlib, sys

out, label, binary_js, manifest, blacklist, runner, driver, addon, results = map(pathlib.Path, sys.argv[1:10])
label = str(label)
start_js_sha, start_js_bytes, start_wasm_sha, start_wasm_bytes = sys.argv[10:14]
artifact_stable = sys.argv[14] == "1"
counts = dict(zip(("pass", "fail", "skip", "stale", "blocked"), map(int, sys.argv[15:20])))
def receipt(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
def tree_receipt(path):
    digest = hashlib.sha256()
    count = 0
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        relative = item.relative_to(path).as_posix().encode()
        digest.update(relative); digest.update(b"\0"); digest.update(item.read_bytes()); digest.update(b"\0")
        count += 1
    return {"path": str(path), "fileCount": count, "sha256Tree": digest.hexdigest()}
binary_wasm = binary_js.with_suffix(".wasm")
payload = {
    "schema": "blender-web.cycles-wasm-suite.v2",
    "label": label,
    "immutable": True,
    "artifacts": {
        "javascript": {"path": str(binary_js), "bytes": int(start_js_bytes), "sha256": start_js_sha},
        "wasm": {"path": str(binary_wasm), "bytes": int(start_wasm_bytes), "sha256": start_wasm_sha},
    },
    "artifactStable": artifact_stable,
    "sources": {
        "manifest": receipt(manifest), "blacklist": receipt(blacklist),
        "runner": receipt(runner), "driver": receipt(driver), "addon": tree_receipt(addon),
    },
    "results": receipt(results),
    "counts": counts,
    "status": "PASS" if artifact_stable and counts["fail"] == counts["stale"] == counts["blocked"] == 0 else "FAIL",
}
with out.open("x") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")
PY
echo "-- summary: PASS=$pass FAIL=$fail SKIP=$skip STALE=$stale BLOCKED=$blocked  (results: ${RESULTS#$ROOT/}) --"
[ "$artifact_stable" = 1 ] && [ "$fail" = 0 ] && [ "$stale" = 0 ] && [ "$blocked" = 0 ] \
  && echo "ALL_PASS" || { echo "SOME_FAIL artifact_stable=$artifact_stable"; exit 1; }
