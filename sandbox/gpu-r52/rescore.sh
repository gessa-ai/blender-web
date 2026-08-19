#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# r52 workbench 20-scene re-score against the m6 goldens on the namespace-fixed build.
# Boots each .blend as the startup file (own bridge_boot.mjs -> gpu-r46 caps, port 8128),
# pulls the render-result via the BW_DIAG bridge (0125), scores with the r35 score.py at the
# pinned per-scene thresholds. Writes sandbox/gpu-r46/results.tsv (does NOT touch r35's).
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"
R35="$ROOT/sandbox/gpu-r35"
R2="$ROOT/sandbox/gpu-r52"
MAN="$ROOT/sandbox/m6-prep/manifest.tsv"
NODE="$ROOT/tools/emsdk/node/22.16.0_64bit/bin/node"
export NODE_PATH=/Users/paws/plushly/game-platform/node_modules
PORT="${PORT:-8135}"
TSV="$R2/results.tsv"
echo -e "# engine\tdir\ttest\tverdict\tcluster\tmean_err\tmax_err\tpct_over\tgpuErr\tgpu_sig" > "$TSV"

while IFS=$'\t' read -r engine dir test blend golden thr fp; do
  case "$engine" in ''|\#*) continue;; esac
  [ "$engine" = "workbench" ] || continue           # workbench scenes only this round
  bpath="$ROOT/$blend"
  [ -f "$bpath" ] || { echo -e "$engine\t$dir\t$test\tMISSING-INPUT\tinput\t\t\t\t\t" >> "$TSV"; continue; }
  head -c 40 "$bpath" | grep -qa 'git-lfs' && { echo -e "$engine\t$dir\t$test\tLFS-POINTER\tinput\t\t\t\t\t" >> "$TSV"; continue; }
  out="${engine}_${dir}_${test}"
  cap="$R2/caps/$out"
  echo "== RUN $engine/$dir/$test =="
  pkill -f "bridge_boot.mjs" 2>/dev/null; sleep 1
  timeout 200 "$NODE" "$R2/bridge_boot.mjs" "$bpath" "BLENDER_WORKBENCH" "$out" "$PORT" 150000 128 128 \
    > "$R2/caps/${out}.log" 2>&1
  [ $? -eq 124 ] && echo "   (TIMED OUT)"
  if [ ! -f "$cap/manifest.json" ]; then
    echo -e "$engine\t$dir\t$test\tRIG-FAIL\trig\t\t\t\t\t" >> "$TSV"; tail -3 "$R2/caps/${out}.log"; continue
  fi
  python3 "$R35/score.py" "$cap" "$ROOT/$golden" "$thr" "$fp" --colorspace linear --json "$cap/score.json" >/dev/null 2>&1
  V=$(python3 -c "import json;d=json.load(open('$cap/score.json'));print(d.get('verdict','?'))" 2>/dev/null)
  C=$(python3 -c "import json;d=json.load(open('$cap/score.json'));print(d.get('cluster','') or '')" 2>/dev/null)
  M=$(python3 -c "import json;d=json.load(open('$cap/score.json'));print(d.get('mean_error') or '')" 2>/dev/null)
  X=$(python3 -c "import json;d=json.load(open('$cap/score.json'));print(d.get('max_error') or '')" 2>/dev/null)
  P=$(python3 -c "import json;d=json.load(open('$cap/score.json'));print((d.get('pct_over') or '').replace(chr(9),' '))" 2>/dev/null)
  G=$(python3 -c "import json;d=json.load(open('$cap/score.json'));print(d.get('gpuErrorCount',0))" 2>/dev/null)
  S=$(python3 -c "import json;d=json.load(open('$cap/score.json'));print(d.get('gpu_sig','') or '')" 2>/dev/null)
  echo -e "$engine\t$dir\t$test\t$V\t$C\t$M\t$X\t$P\t$G\t$S" >> "$TSV"
  echo "   -> $V [$C] mean=$M gpuErr=$G sig=$S"
done < "$MAN"
pkill -f "bridge_boot.mjs" 2>/dev/null
echo "== r44r2 workbench re-score complete =="
