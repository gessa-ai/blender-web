#!/usr/bin/env bash
# Area worker: ./worker.sh <area> [claude|codex] [MAX_ITER]
# Runs GOAL.md iterations scoped to one path-owned area, in its own git worktree.
set -uo pipefail
cd "$(dirname "$0")"
AREA=${1:?area}; ENGINE=${2:-claude}; MAX=${3:-50}
WT="../blender-web-wt/$AREA"
[ -d "$WT" ] || { mkdir -p ../blender-web-wt; git worktree add "$WT" -b "agent/$AREA"; }
cd "$WT"
for ((i=1; i<=MAX; i++)); do
  PROMPT=$(printf 'WORKER_SCOPE=%s — you may only modify files owned by this area (see GOAL.md fleet mode). Do ONE task for this area from fix_plan.md.\n\n%s' "$AREA" "$(cat GOAL.md)")
  case "$ENGINE" in
    claude) out=$(printf '%s' "$PROMPT" | claude -p --permission-mode acceptEdits \
              --allowedTools "Bash,Read,Edit,Write,Grep,Glob" --max-turns 60 \
              --output-format json --model sonnet 2>>../worker-$AREA.err) || true
            echo "$out" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("result","")[:2000])' ;;
    codex)  # Flags verified once by M0.8 into notes/codex-cli.md; adapter kept minimal.
            printf '%s' "$PROMPT" | codex exec - 2>>../worker-$AREA.err || true ;;
  esac
  sleep 5
done
