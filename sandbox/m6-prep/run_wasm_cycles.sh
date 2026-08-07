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
# Emits one TSV row per test to results-wasm-cycles.tsv (committed):
#   test  render_s  node_exit  diff_exit  verdict  max_err  pct_over  note
# Failure render PNGs are copied to wasm-cycles-fails/ (evidence); passes rely on
# the comparator receipt (no 27-render dump). No raw logs surfaced.
#
# Usage:
#   bash sandbox/m6-prep/run_wasm_cycles.sh [--filter <substr>] [--limit N] [--threads N]
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
RESULTS="$ROOT/$MP/results-wasm-cycles.tsv"
FAILDIR="$ROOT/$MP/wasm-cycles-fails"
SCR="${TMPDIR:-/tmp}/m6wasm.$$"
mkdir -p "$SCR"

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

printf 'test\trender_s\tnode_exit\tdiff_exit\tverdict\tmax_err\tpct_over\tnote\n' > "$RESULTS"

pass=0; fail=0; skip=0; blocked=0; n=0
echo "== M6 wasm Cycles-CPU comparator (threads=$THREADS) =="
while IFS=$'\t' read -r engine dir test blend golden thr fp; do
  case "$engine" in ''|\#*) continue;; esac
  [ "$engine" = cycles ] || continue
  [ -z "$FILT_SUB" ] || case "$dir/$test" in *"$FILT_SUB"*) : ;; *) continue;; esac
  [ "$LIMIT" = 0 ] || [ "$n" -lt "$LIMIT" ] || break
  n=$((n+1))

  if is_blacklisted "$engine" "$test"; then
    echo "SKIP $dir/$test (blacklist)"; skip=$((skip+1))
    printf '%s\t-\t-\t-\tSKIP\t-\t-\tblacklist\n' "$dir/$test" >> "$RESULTS"; continue
  fi
  if ! have_input "$blend"; then
    echo "BLOCKED $dir/$test (LFS pointer/missing)"; blocked=$((blocked+1))
    printf '%s\t-\t-\t-\tBLOCKED\t-\t-\tinput-not-materialized\n' "$dir/$test" >> "$RESULTS"; continue
  fi

  base="$SCR/${dir}_${test}"
  log="$SCR/${dir}_${test}.log"
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
    printf '%s\t%s\t%s\t-\tFAIL\t-\t-\trender:%s\n' "$dir/$test" "$rt" "$nec" "$note" >> "$RESULTS"
    mkdir -p "$FAILDIR/$dir"; cp "$log" "$FAILDIR/$dir/$test.log" 2>/dev/null
    fail=$((fail+1)); continue
  fi

  diffout=$("$OIIO" "$ROOT/$golden" "$png" --fail "$thr" --failpercent "$fp" --diff 2>&1); dec=$?
  maxe=$(echo "$diffout" | grep -aoE 'Max error *= *[0-9.e+-]+' | head -1 | grep -aoE '[0-9.e+-]+$')
  over=$(echo "$diffout" | grep -aoE '\([0-9.]+% *\) *over' | grep -aoE '[0-9.]+%' | tail -1)
  [ -n "$maxe" ] || maxe="-"; [ -n "$over" ] || over="-"
  if [ "$dec" = 0 ]; then
    echo "PASS $dir/$test  max=$maxe over=$over  ${rt}s"
    printf '%s\t%s\t%s\t%s\tPASS\t%s\t%s\t-\n' "$dir/$test" "$rt" "$nec" "$dec" "$maxe" "$over" >> "$RESULTS"
    pass=$((pass+1))
  else
    echo "FAIL $dir/$test  max=$maxe over=$over  ${rt}s (pixel drift)"
    printf '%s\t%s\t%s\t%s\tFAIL\t%s\t%s\tpixel-drift\n' "$dir/$test" "$rt" "$nec" "$dec" "$maxe" "$over" >> "$RESULTS"
    mkdir -p "$FAILDIR/$dir"; cp "$png" "$FAILDIR/$dir/$test.png"
    fail=$((fail+1))
  fi
done < "$MAN"

echo "-- summary: PASS=$pass FAIL=$fail SKIP=$skip BLOCKED=$blocked  (results: ${RESULTS#$ROOT/}) --"
rm -rf "$SCR"
[ "$fail" = 0 ] && [ "$blocked" = 0 ] && echo "ALL_PASS" || echo "SOME_FAIL"
