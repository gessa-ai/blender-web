#!/usr/bin/env bash
# Driver loop — runs GOAL.md iterations via `claude -p` until promise tag, budget cap, or max iterations.
# Usage: ./loop.sh [MAX_ITER] [BUDGET_USD]   (defaults: 200 iterations, $200)
# Designed to run from a terminal OR as a background task inside a Claude Code session.
set -uo pipefail
cd "$(dirname "$0")"
MAX=${1:-200}; CAP=${2:-200}; total=0
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
  if python3 -c "exit(0 if $total > $CAP else 1)"; then echo "BUDGET CAP \$$CAP hit at \$$total" | tee -a ledger/loop.log; break; fi
  sleep 8
done
echo "loop exit: iter=$i total=\$$total" | tee -a ledger/loop.log
