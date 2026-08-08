#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Re-score EVERY manifest row from its persisted capture (no re-render), writing a fresh
# authoritative results.tsv (one row per test) with the current score.py. Dedup-safe.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"; R35="$ROOT/sandbox/gpu-r35"; MAN="$ROOT/sandbox/m6-prep/manifest.tsv"
TSV="$R35/results.tsv"
echo -e "# engine\tdir\ttest\tverdict\tcluster\tmean_err\tmax_err\tpct_over\tgpuErr\tgpu_sig" > "$TSV"
while IFS=$'\t' read -r engine dir test blend golden thr fp; do
  case "$engine" in ''|\#*) continue;; esac
  [ "$engine" = "cycles" ] && continue
  out="${engine}_${dir}_${test}"; cap="$R35/caps/$out"
  if [ ! -s "$cap/manifest.json" ]; then
    echo -e "$engine\t$dir\t$test\tNO-CAP\tno-capture\t\t\t\t\t"; echo -e "$engine\t$dir\t$test\tNO-CAP\tno-capture\t\t\t\t\t" >> "$TSV"; continue
  fi
  python3 "$R35/score.py" "$cap" "$ROOT/$golden" "$thr" "$fp" --colorspace linear --json "$cap/score.json" >/dev/null 2>&1
  v=$(python3 -c "import json;d=json.load(open('$cap/score.json'));print(d.get('verdict','?'))")
  c=$(python3 -c "import json;d=json.load(open('$cap/score.json'));print(d.get('cluster','') or '')")
  me=$(python3 -c "import json;d=json.load(open('$cap/score.json'));print(d.get('mean_error') or '')")
  mx=$(python3 -c "import json;d=json.load(open('$cap/score.json'));print(d.get('max_error') or '')")
  pc=$(python3 -c "import json;d=json.load(open('$cap/score.json'));print((d.get('pct_over') or '').replace(chr(9),' '))")
  ge=$(python3 -c "import json;d=json.load(open('$cap/score.json'));print(d.get('gpuErrorCount',0))")
  gs=$(python3 -c "import json;d=json.load(open('$cap/score.json'));print(d.get('gpu_sig','') or '')")
  echo -e "$engine\t$dir\t$test\t$v\t$c\t$me\t$mx\t$pc\t$ge\t$gs" >> "$TSV"
  echo "$engine/$dir/$test -> $v [$c]"
done < "$MAN"
echo "rescore complete -> $TSV"
