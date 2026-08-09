#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# M6 r35 render-result bridge -- full GPU suite runner (workbench + EEVEE).
# For each manifest row: boot the .blend as the startup file (bridge_boot.mjs, clean
# GPU context, no open_mainfile), pull the render-result dump via the BW_DIAG hook
# (patch 0125), decode + oiiotool-compare to the golden (score.py). Appends a TSV row
# and rewrites the checkpoint after EVERY test so a session wall never loses progress.
#
# Usage: run_suite.sh <workbench|eevee|all> [testFilterSubstr] [settleMs]
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"
R35="$ROOT/sandbox/gpu-r35"
MAN="$ROOT/sandbox/m6-prep/manifest.tsv"
NODE="$ROOT/tools/emsdk/node/22.16.0_64bit/bin/node"
export NODE_PATH=/Users/paws/plushly/game-platform/node_modules
PORT="${M6_PORT:-8126}"
CASE_TIMEOUT="${M6_CASE_TIMEOUT:-480}"

ENGINE_FILT="${1:-all}"
TEST_FILT="${2:-}"
SETTLE="${3:-}"
TSV="$R35/results.tsv"
mkdir -p "$R35/caps"
if [ ! -f "$TSV" ]; then
  {
    echo "# SPDX-FileCopyrightText: 2026 blender-web contributors"
    echo "# SPDX-License-Identifier: CC0-1.0"
    echo -e "# engine\tdir\ttest\tverdict\tcluster\tmean_err\tmax_err\tpct_over\tgpuErr\tgpu_sig"
  } > "$TSV"
fi

engine_arg() { case "$1" in workbench) echo BLENDER_WORKBENCH;; eevee) echo BLENDER_EEVEE;; esac; }

while IFS=$'\t' read -r engine dir test blend golden thr fp; do
  case "$engine" in ''|\#*) continue;; esac
  [ "$engine" = "cycles" ] && continue      # Cycles is CPU, out of this GPU lane
  [ "$ENGINE_FILT" = "all" ] || [ "$ENGINE_FILT" = "$engine" ] || continue
  [ -z "$TEST_FILT" ] || case "$dir/$test" in *"$TEST_FILT"*) : ;; *) continue;; esac

  # skip already-scored rows (resume support)
  if awk -F '\t' -v engine="$engine" -v dir="$dir" -v test="$test" '
      $1 == engine && $2 == dir && $3 == test { found = 1; exit }
      END { exit !found }
    ' "$TSV"; then
    echo "SKIP (already scored) $engine/$dir/$test"; continue
  fi

  bpath="$ROOT/$blend"
  if [ ! -f "$bpath" ]; then
    echo -e "$engine\t$dir\t$test\tMISSING-INPUT\tinput\t\t\t\t\t" >> "$TSV"; continue
  fi
  if head -c 40 "$bpath" | grep -qa 'git-lfs'; then
    echo -e "$engine\t$dir\t$test\tLFS-POINTER\tinput\t\t\t\t\t" >> "$TSV"; continue
  fi

  eng=$(engine_arg "$engine")
  out="${engine}_${dir}_${test}"
  cap="$R35/caps/$out"
  if [ "${REUSE:-0}" != "1" ] && [ -e "$cap" ]; then
    echo "REFUSE stale capture directory: $cap" >&2
    echo "Move it aside before a fresh run so an interrupted boot cannot reuse a manifest." >&2
    exit 4
  fi
  st="$SETTLE"
  [ -n "$st" ] || { [ "$engine" = "eevee" ] && st=200000 || st=150000; }

  if [ "${REUSE:-0}" = "1" ] && [ -s "$cap/manifest.json" ]; then
    echo "== REUSE cap $engine/$dir/$test =="
  else
    echo "== RUN $engine/$dir/$test =="
    # hard per-test timeout so a hung/crashed tab never stalls the batch
    timeout "$CASE_TIMEOUT" "$NODE" "$R35/bridge_boot.mjs" "$bpath" "$eng" "$out" "$PORT" "$st" 128 128 \
      > "$R35/caps/${out}.log" 2>&1
    tc=$?
    [ $tc -eq 124 ] && echo "   (bridge_boot TIMED OUT after ${CASE_TIMEOUT}s)"
  fi

  if [ ! -f "$cap/manifest.json" ]; then
    echo -e "$engine\t$dir\t$test\tRIG-FAIL\trig\t\t\t\t\t" >> "$TSV"
    tail -3 "$R35/caps/${out}.log"
    continue
  fi
  res=$(python3 "$R35/score.py" "$cap" "$ROOT/$golden" "$thr" "$fp" --colorspace linear \
        --json "$cap/score.json" 2>&1)
  verdict=$(python3 -c "import json,sys; d=json.load(open('$cap/score.json')); print(d.get('verdict','?'))" 2>/dev/null)
  cluster=$(python3 -c "import json; d=json.load(open('$cap/score.json')); print(d.get('cluster','') or '')" 2>/dev/null)
  mean=$(python3 -c "import json; d=json.load(open('$cap/score.json')); print(d.get('mean_error') or '')" 2>/dev/null)
  maxe=$(python3 -c "import json; d=json.load(open('$cap/score.json')); print(d.get('max_error') or '')" 2>/dev/null)
  pct=$(python3 -c "import json; d=json.load(open('$cap/score.json')); print((d.get('pct_over') or '').replace(chr(9),' '))" 2>/dev/null)
  gerr=$(python3 -c "import json; d=json.load(open('$cap/score.json')); print(d.get('gpuErrorCount',0))" 2>/dev/null)
  gsig=$(python3 -c "import json; d=json.load(open('$cap/score.json')); print(d.get('gpu_sig','') or '')" 2>/dev/null)
  echo -e "$engine\t$dir\t$test\t$verdict\t$cluster\t$mean\t$maxe\t$pct\t$gerr\t$gsig" >> "$TSV"
  echo "   -> $verdict [$cluster] mean=$mean gpuErr=$gerr sig=$gsig"

  # checkpoint the note after every test
  python3 "$R35/make_note.py" "$TSV" > "$ROOT/notes/m6-gpu-suite-real-scores.md" 2>/dev/null || true
done < "$MAN"

echo "== suite run complete for filter=$ENGINE_FILT =="
