#!/usr/bin/env bash
# Harness v1 status board: current milestone, per-scope pass counts, upstream pin.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# --- current milestone: first markdown heading in fix_plan.md (skips SPDX/comment preamble) ---
MILE="$(grep -m1 -E '^#[[:space:]]+' fix_plan.md 2>/dev/null | sed -E 's/^#[[:space:]]*//')"
echo "milestone: ${MILE:-unknown}"

# --- per-scope pass counts from ledger/results/*.json ---
# Schema (H-1): {"scope","pass","ts","checks":{name:{pass,detail}}}. Legacy array form tolerated.
if ls ledger/results/*.json >/dev/null 2>&1; then
  echo "suites:"
  for f in ledger/results/*.json; do
    python3 - "$f" <<'PY'
import json, os, sys
f = sys.argv[1]
scope = os.path.splitext(os.path.basename(f))[0]
try:
    doc = json.load(open(f))
    if isinstance(doc, dict) and "checks" in doc:          # current schema
        checks = doc["checks"]
        scope = doc.get("scope", scope)
        items = [(n, bool(c.get("pass"))) for n, c in checks.items()]
        ts = doc.get("ts", "")
    else:                                                   # legacy array
        items = [(r.get("name", "?"), bool(r.get("pass"))) for r in doc]
        ts = ""
    npass = sum(1 for _, p in items if p)
    total = len(items)
    fails = [n for n, p in items if not p]
    tag = "GREEN" if total and npass == total else "RED"
    line = f"  {scope:<8} {npass}/{total} {tag}"
    if fails:
        line += "  fail: " + ",".join(fails)
    if ts:
        line += f"  ({ts})"
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
