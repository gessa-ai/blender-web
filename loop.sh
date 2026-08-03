#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Driver loop — runs GOAL.md iterations via `claude -p` until promise tag or max iterations.
# Subscription billing: iteration-gated, not dollar-gated; backs off through rate-limit windows.
# Usage: ./loop.sh [MAX_ITER]   (default: 200)
set -uo pipefail
cd "$(dirname "$0")"
MAX=${1:-200}; CAP=${2:-999999}; total=0
PROMISE=${PROMISE:-M8_LAUNCH_GATE}
MODEL=${MODEL:-opus}
mkdir -p ledger
for ((i=1; i<=MAX; i++)); do
  echo "── iter $i  $(date -u +%FT%TZ)  spent=\$$total ──" | tee -a ledger/loop.log
  out=$(claude -p \
        --permission-mode acceptEdits \
        --allowedTools "Bash,Read,Edit,Write,Grep,Glob,WebFetch,WebSearch" \
        --max-turns 80 \
        --output-format json \
        --model "$MODEL" \
        < GOAL.md 2>>ledger/loop.err) || true
  echo "$out" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("result","")[:4000])' >> ledger/loop.log 2>/dev/null
  cost=$(echo "$out" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("total_cost_usd",0) or 0)' 2>/dev/null || echo 0)
  total=$(python3 -c "print(round($total+$cost,2))")
  date -u +%s > .claude/heartbeat
  if echo "$out" | grep -q "<promise>${PROMISE}</promise>"; then echo "PROMISE ${PROMISE} — done." | tee -a ledger/loop.log; break; fi
  if [ -z "$out" ] || tail -1 ledger/loop.err 2>/dev/null | grep -qiE "rate.?limit|overloaded|usage limit|authenticate"; then
    echo "empty/limited iteration — backing off 300s" | tee -a ledger/loop.log; sleep 300
  else
    sleep 8
  fi
done
echo "loop exit: iter=$i total=\$$total" | tee -a ledger/loop.log
