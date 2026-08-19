#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

# Fresh, non-reusing 20-row Workbench matrix against an already-served shipping
# build. Every run gets its own capture tree and results TSV.
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel)"
HERE="$ROOT/sandbox/gpu-r61/workbench-preview"
MANIFEST="$ROOT/sandbox/m6-prep/manifest.tsv"
NODE="$ROOT/tools/emsdk/node/22.16.0_64bit/bin/node"
DRIVER="$HERE/drive_workbench_case.mjs"
SCORER="$HERE/score_workbench.py"
RUN_LABEL="${1:-}"
TEST_FILTER="${2:-}"
PORT="${M6_PORT:-8151}"
SETTLE_MS="${M6_SETTLE_MS:-150000}"
CASE_TIMEOUT="${M6_CASE_TIMEOUT:-480}"

if [[ -z "$RUN_LABEL" || ! "$RUN_LABEL" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "usage: M6_PORT=8151 $0 <unique-run-label> [test-filter]" >&2
  exit 2
fi

RUN_ROOT="$HERE/runs/$RUN_LABEL"
if [[ -e "$RUN_ROOT" ]]; then
  echo "refusing to reuse run directory: $RUN_ROOT" >&2
  exit 3
fi
if ! mkdir "$RUN_ROOT"; then
  echo "refusing concurrent/reused run directory: $RUN_ROOT" >&2
  exit 3
fi
mkdir "$RUN_ROOT/caps"

if ! BW_WORKBENCH_SELF_CHECK=1 BW_WORKBENCH_OUTDIR="$RUN_ROOT" \
  "$NODE" "$DRIVER" ignored BLENDER_WORKBENCH selfcheck; then
  echo "Workbench driver self-check failed before browser launch" >&2
  exit 4
fi
if ! python3 "$SCORER" --self-check; then
  echo "Workbench scorer self-check failed before browser launch" >&2
  exit 4
fi

RESULTS="$RUN_ROOT/results.tsv"
{
  echo "# SPDX-FileCopyrightText: 2026 blender-web contributors"
  echo "# SPDX-License-Identifier: CC0-1.0"
  printf '# engine\tdir\ttest\tverdict\tcluster\tmean_err\tmax_err\tpct_over\tgpuErr\tgpu_sig\n'
} > "$RESULTS"

while IFS=$'\t' read -r engine directory test blend golden threshold fail_percent; do
  case "$engine" in ''|'#'*) continue ;; esac
  [[ "$engine" == "workbench" ]] || continue
  if [[ -n "$TEST_FILTER" && "$directory/$test" != *"$TEST_FILTER"* ]]; then
    continue
  fi

  out_name="workbench_${directory}_${test}"
  cap="$RUN_ROOT/caps/$out_name"
  log="$RUN_ROOT/${out_name}.log"
  echo "== RUN $engine/$directory/$test =="

  BW_WORKBENCH_OUTDIR="$RUN_ROOT" timeout "$CASE_TIMEOUT" "$NODE" "$DRIVER" \
    "$ROOT/$blend" BLENDER_WORKBENCH "$out_name" "$PORT" "$SETTLE_MS" 128 128 \
    > "$log" 2>&1
  command_status=$?
  if [[ $command_status -eq 124 ]]; then
    echo "   bridge timed out after ${CASE_TIMEOUT}s"
  elif [[ $command_status -ne 0 ]]; then
    echo "   bridge product gate failed (status $command_status); scoring retained manifest"
  fi

  if [[ ! -s "$cap/manifest.json" ]]; then
    printf '%s\t%s\t%s\tRIG-FAIL\trig\t\t\t\t\t\n' \
      "$engine" "$directory" "$test" >> "$RESULTS"
    tail -n 5 "$log"
    continue
  fi

  python3 "$SCORER" "$cap" "$ROOT/$golden" "$threshold" "$fail_percent" \
    --json "$cap/score.json" > "$cap/score.log" 2>&1
  score_status=$?
  if [[ $score_status -ne 0 || ! -s "$cap/score.json" ]]; then
    printf '%s\t%s\t%s\tRIG-FAIL\tscorer\t\t\t\t\t\n' \
      "$engine" "$directory" "$test" >> "$RESULTS"
    tail -n 5 "$cap/score.log"
    continue
  fi

  python3 - "$cap/score.json" "$engine" "$directory" "$test" >> "$RESULTS" <<'PY'
import json
import sys

score_path, engine, directory, test = sys.argv[1:]
d = json.load(open(score_path))
fields = [
    engine,
    directory,
    test,
    d.get("verdict", "?"),
    d.get("cluster", ""),
    d.get("mean_error") or "",
    d.get("max_error") or "",
    (d.get("pct_over") or "").replace("\t", " "),
    str(d.get("gpuErrorCount", 0)),
    d.get("gpu_sig", "") or "",
]
print("\t".join(fields))
PY
  tail -n 1 "$RESULTS"
done < "$MANIFEST"

python3 - "$RESULTS" <<'PY'
from collections import Counter
import sys

rows = [line.rstrip("\n").split("\t") for line in open(sys.argv[1])
        if line.strip() and not line.startswith("#")]
counts = Counter(row[3] for row in rows)
gpu_rows = sum(int(row[8] or 0) > 0 for row in rows)
print("== Workbench matrix complete ==")
print("rows=%d verdicts=%s rows_with_gpu_errors=%d" %
      (len(rows), dict(sorted(counts.items())), gpu_rows))
print("results=%s" % sys.argv[1])
PY
