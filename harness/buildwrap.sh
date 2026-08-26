#!/usr/bin/env bash
# All builds go through this wrapper. Success -> one line. Failure -> first 50 error lines.
# Full log always at ledger/buildlogs/<ts>-<pid>[-<collision>].log
# (grep it for more; never cat it whole).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/ledger/buildlogs"
STAMP="$(date -u +%Y%m%dT%H%M%S)"
LOG_BASE="$ROOT/ledger/buildlogs/$STAMP-$$"
LOG="$LOG_BASE.log"
LOG_SUFFIX=0
while ! (set -o noclobber; : >"$LOG") 2>/dev/null; do
  LOG_SUFFIX=$((LOG_SUFFIX + 1))
  if [ "$LOG_SUFFIX" -gt 1000 ]; then
    echo "BUILDWRAP FAIL: unable to allocate a unique log under ledger/buildlogs/" >&2
    exit 73
  fi
  LOG="$LOG_BASE-$LOG_SUFFIX.log"
done
START=$(date +%s)
"$@" >>"$LOG" 2>&1
RC=$?
DUR=$(( $(date +%s) - START ))
if [ $RC -eq 0 ]; then
  echo "BUILD OK ($DUR s): $* [log: ${LOG#$ROOT/}]"
else
  echo "BUILD FAIL rc=$RC ($DUR s): $* [full log: ${LOG#$ROOT/}]"
  grep -nE "error:|Error|ERROR|undefined symbol|FAILED" "$LOG" | head -50
fi
exit $RC
