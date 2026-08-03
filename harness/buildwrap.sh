#!/usr/bin/env bash
# All builds go through this wrapper. Success -> one line. Failure -> first 50 error lines.
# Full log always at ledger/buildlogs/<ts>.log (grep it for more; never cat it whole).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/ledger/buildlogs"
LOG="$ROOT/ledger/buildlogs/$(date -u +%Y%m%dT%H%M%S).log"
START=$(date +%s)
"$@" >"$LOG" 2>&1
RC=$?
DUR=$(( $(date +%s) - START ))
if [ $RC -eq 0 ]; then
  echo "BUILD OK ($DUR s): $* [log: ${LOG#$ROOT/}]"
else
  echo "BUILD FAIL rc=$RC ($DUR s): $* [full log: ${LOG#$ROOT/}]"
  grep -nE "error:|Error|ERROR|undefined symbol|FAILED" "$LOG" | head -50
fi
exit $RC
