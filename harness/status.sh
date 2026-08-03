#!/usr/bin/env bash
# Harness v1 status board: current milestone, per-scope pass counts, upstream pin.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# --- current milestone: first line of fix_plan.md ---
MILE="$(head -1 fix_plan.md 2>/dev/null | sed -E 's/^#[[:space:]]*//')"
echo "milestone: ${MILE:-unknown}"

# --- per-scope pass counts from ledger/results/*.json (array of {name,pass,detail}) ---
if ls ledger/results/*.json >/dev/null 2>&1; then
  echo "suites:"
  for f in ledger/results/*.json; do
    python3 - "$f" <<'PY'
import json, os, sys
f = sys.argv[1]
scope = os.path.splitext(os.path.basename(f))[0]
try:
    rows = json.load(open(f))
    npass = sum(1 for r in rows if r.get("pass"))
    total = len(rows)
    fails = [r["name"] for r in rows if not r.get("pass")]
    tag = "GREEN" if total and npass == total else "RED"
    line = f"  {scope:<8} {npass}/{total} {tag}"
    if fails:
        line += "  fail: " + ",".join(fails)
    print(line)
except Exception as e:
    print(f"  {scope:<8} unreadable ({e})")
PY
  done
else
  echo "suites: none yet (run harness/run.sh --scope m0)"
fi

# --- gate flag ---
[ -f harness/GATE_RED ] && echo "gate: RED — $(head -1 harness/GATE_RED)" || echo "gate: green"

# --- upstream pin status ---
PIN="$(awk 'NR==1{print $1; exit}' oracle/PIN 2>/dev/null)"
if [ -n "${PIN:-}" ] && git -C upstream rev-parse HEAD >/dev/null 2>&1; then
  HEAD="$(git -C upstream rev-parse HEAD)"
  case "$HEAD" in
    ${PIN}*) echo "upstream: pinned OK @ ${PIN} ($(awk 'NR==1{$1="";sub(/^ /,"");print}' oracle/PIN))" ;;
    *)       echo "upstream: DRIFT — checkout ${HEAD:0:12} != pin ${PIN}" ;;
  esac
else
  echo "upstream: pin ${PIN:-unknown} (checkout not a git repo)"
fi
