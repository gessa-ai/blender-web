#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
#
# DRY-RUN harness for the DRAFT m3 scope — validates scope_m3.fragment.sh BEFORE
# the driver installs it into the locked harness/run.sh.
#
# It reproduces run.sh's runner scaffolding VERBATIM (the `record` helper, the
# JSON emitter, the per-check summary + green/red line) so the fragment executes
# completely unchanged from what gets pasted into run.sh. The ONLY differences
# from run.sh are deliberate and isolating:
#   - ROOT is discovered as the repo root (two levels up from this staging dir);
#   - the result JSON is written to THIS staging dir (m3.json), never to
#     ledger/results/ (harness output is driver-owned; a dry-run must not touch it).
#
# Usage:   bash sandbox/m3-scope-draft/dryrun.sh
#   optional: M3_TEST_BIN=/path/to/blender_test bash sandbox/m3-scope-draft/dryrun.sh
# Exit 0 iff all checks pass (same gate semantics as run.sh --scope m3).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT"

# --- runner scaffolding, copied from harness/run.sh (keep byte-identical) ------
record() {  # record NAME PASS(0|1) DETAIL...   (detail forced to one line)
  local name="$1" pass="$2"; shift 2
  local detail="$*"
  detail="${detail//$'\t'/ }"; detail="${detail//$'\n'/ }"
  printf '%s\t%s\t%s\n' "$name" "$pass" "$detail" >>"$TSV"
}

# --- load the DRAFT scope fragment (the exact block destined for run.sh) -------
# shellcheck source=/dev/null
source "$HERE/scope_m3.fragment.sh"

TSV="$(mktemp)"
echo "dryrun: running scope_m3 against ${M3_TEST_BIN:-build-native-gpu/bin/tests/blender_test} ..." >&2
scope_m3

# --- emit result JSON to the STAGING dir (NOT ledger/results/) -----------------
OUTF="$HERE/m3.dryrun.json"   # NOT ledger/results/m3.json — a dry-run must not touch driver-owned harness output
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)" python3 - "$TSV" "$OUTF" m3 <<'PY'
import json, os, sys
tsv, outp, scope = sys.argv[1], sys.argv[2], sys.argv[3]
checks = {}
with open(tsv) as f:
    for line in f:
        line = line.rstrip("\n")
        if not line:
            continue
        name, pas, detail = line.split("\t", 2)
        checks[name] = {"pass": pas == "1", "detail": detail}
doc = {
    "scope": scope,
    "pass": bool(checks) and all(c["pass"] for c in checks.values()),
    "ts": os.environ.get("TS", ""),
    "checks": checks,
}
with open(outp, "w") as f:
    json.dump(doc, f, indent=2)
    f.write("\n")
PY

# --- per-check summary + gate line (copied from run.sh) ------------------------
NTOTAL="$(awk 'END{print NR}' "$TSV")"
NPASS="$(awk -F'\t' '$2==1{c++} END{print c+0}' "$TSV")"
while IFS=$'\t' read -r n p d; do
  [ "$p" = 1 ] && printf '  PASS  %-20s %s\n' "$n" "$d" || printf '  FAIL  %-20s %s\n' "$n" "$d"
done <"$TSV"
rm -f "$TSV"

echo "dryrun: result JSON -> $OUTF"
if [ "$NPASS" = "$NTOTAL" ] && [ "$NTOTAL" -gt 0 ]; then
  echo "dryrun: scope=m3 ALL GREEN ($NPASS/$NTOTAL)"
  exit 0
fi
echo "dryrun: scope=m3 RED ($NPASS/$NTOTAL)" >&2
exit 1
