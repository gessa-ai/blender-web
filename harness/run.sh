#!/usr/bin/env bash
# Harness v1.1. Reconciles H-1/H-2/H-3 from notes/harness-issues.md.
#
#   run.sh --scope <name>   run one scope's checks
#   run.sh --regress        re-run EVERY scope that has a prior result file
#   run.sh --list           list registered scopes
#
# Result schema (H-1) — ledger/results/<scope>.json:
#   {"scope":..., "pass":bool, "ts":ISO8601, "checks":{"<name>":{"pass":bool,"detail":"..."}}}
# Scope exit: 0 iff that invocation's checks pass. The global harness/GATE_RED is
# reconciled from every registered scope with a current result, so one green scope
# cannot erase another scope's stored red state.
# Token thrift: builds go through harness/buildwrap.sh (one line ok / capped errors on fail,
# full log under ledger/buildlogs/). This script prints a short per-check summary only.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SCOPES_REGISTERED="m0 m1 m2b m3 m4 m5 m6 m7 m8"
EMSDK_ENV="tools/emsdk/emsdk_env.sh"
TSV=""

record() {  # record NAME PASS(0|1) DETAIL...   (detail forced to one line)
  local name="$1" pass="$2"; shift 2
  local detail="$*"
  detail="${detail//$'\t'/ }"; detail="${detail//$'\n'/ }"
  printf '%s\t%s\t%s\n' "$name" "$pass" "$detail" >>"$TSV"
}

ver_ge() {  # $1 >= $2 for dotted versions -> prints 1 or 0
  awk -v a="$1" -v b="$2" 'BEGIN{
    na=split(a,A,"."); nb=split(b,B,"."); n=(na>nb)?na:nb;
    for(i=1;i<=n;i++){x=(i<=na?A[i]+0:0);y=(i<=nb?B[i]+0:0);
      if(x>y){print 1;exit} if(x<y){print 0;exit}} print 1}'
}

# ---------------------------------------------------------------- scope: m0
scope_m0() {
  # 1) toolchain (H-3): probe emcc LIVE, don't trust the recorded oracle/TOOLCHAIN file.
  local EMV
  EMV="$(bash -c "source $EMSDK_ENV >/dev/null 2>&1 && emcc --version 2>/dev/null" \
         | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
  if [ -n "$EMV" ] && [ "$(ver_ge "$EMV" 4.0.10)" = 1 ]; then
    local RECORDED
    RECORDED="$(grep -oE 'emcc [0-9]+\.[0-9]+\.[0-9]+' oracle/TOOLCHAIN 2>/dev/null | head -1 | awk '{print $2}')"
    if [ -n "$RECORDED" ] && [ "$RECORDED" != "$EMV" ]; then
      record toolchain 0 "live emcc $EMV != oracle/TOOLCHAIN $RECORDED (toolchain drift)"
    else
      record toolchain 1 "live emcc $EMV (>= 4.0.10)"
    fi
  else
    record toolchain 0 "live emcc probe failed or '$EMV' < 4.0.10"
  fi

  # 2) hello_wasm: compile via buildwrap, run in node, expect 'hello'
  local TMPD OUT; TMPD="$(mktemp -d)"
  if harness/buildwrap.sh bash -c "source $EMSDK_ENV >/dev/null 2>&1 && emcc sandbox/hello.c -o \"$TMPD/hello.js\"" >/dev/null 2>&1; then
    OUT="$(node "$TMPD/hello.js" 2>&1)"
    if printf '%s' "$OUT" | grep -qi hello; then
      record hello_wasm 1 "compiled + node output: $(printf '%s' "$OUT" | tr '\n' ' ')"
    else
      record hello_wasm 0 "ran but no 'hello' in output: $(printf '%s' "$OUT" | tr '\n' ' ')"
    fi
  else
    record hello_wasm 0 "buildwrap emcc sandbox/hello.c failed (see ledger/buildlogs/)"
  fi
  rm -rf "$TMPD"

  # 3) emdawnwebgpu port compiles
  local OBJ; OBJ="$(mktemp -u /tmp/hw_XXXX.o)"
  if harness/buildwrap.sh bash -c "source $EMSDK_ENV >/dev/null 2>&1 && emcc --use-port=emdawnwebgpu -c sandbox/hello.c -o $OBJ" >/dev/null 2>&1; then
    record emdawnwebgpu 1 "emcc --use-port=emdawnwebgpu -c ok"
  else
    record emdawnwebgpu 0 "emdawnwebgpu port compile failed (see ledger/buildlogs/)"
  fi
  rm -f "$OBJ"

  # 4) oracle_version: 'Blender 5.2.0' AND the pin hash
  local OV OV1
  OV="$(oracle/bpy.sh --version 2>&1)"; OV1="$(printf '%s' "$OV" | grep -m1 -i blender | head -1)"
  if printf '%s' "$OV" | grep -q "Blender 5.2.0" && printf '%s' "$OV" | grep -q "fbe6228777e7"; then
    record oracle_version 1 "${OV1:-Blender 5.2.0 fbe6228777e7}"
  else
    record oracle_version 0 "missing 'Blender 5.2.0' and/or 'fbe6228777e7': ${OV1}"
  fi

  # 5) oracle_bpy: default scene objects
  local OB
  OB="$(oracle/bpy.sh --python-expr "import bpy; print(sorted(bpy.data.objects.keys()))" 2>&1)"
  if printf '%s' "$OB" | grep -q Camera && printf '%s' "$OB" | grep -q Cube && printf '%s' "$OB" | grep -q Light; then
    record oracle_bpy 1 "default objects present: Camera, Cube, Light"
  else
    record oracle_bpy 0 "default objects missing (Camera/Cube/Light)"
  fi

  # 6) oiiotool present
  local OIIO
  if OIIO="$(oiiotool --version 2>&1)"; then
    record oiiotool 1 "$(printf '%s' "$OIIO" | head -1)"
  else
    record oiiotool 0 "oiiotool --version nonzero or not on PATH"
  fi
}

# ----------------------------------------------------- strict final M1/M2b/M3
# These harness scopes are ledger adapters, not evidence producers. The raw
# runners under sandbox/final-m0-m3/ must finish first and compose one immutable
# final manifest. Re-running the historical mutable tier-b/gpu drivers here
# would overwrite source-frozen evidence and could reintroduce stale expected
# failures.
scope_strict_final() {
  local SCOPE="$1" CHECK="$2"
  local ADAPTER=sandbox/final-m0-m3/strict_final_adapter.py
  if [ -z "${FINAL_M0_M3_MANIFEST:-}" ] || [ -z "${FINAL_RUN_LABEL:-}" ]; then
    record "$CHECK" 0 "set FINAL_RUN_LABEL and FINAL_M0_M3_MANIFEST to the fresh strict final candidate"
    return
  fi
  if [ ! -f "$ADAPTER" ]; then
    record "$CHECK" 0 "missing strict receipt adapter: $ADAPTER"
    return
  fi
  local OUT
  if OUT="$(python3 "$ADAPTER" --root "$ROOT" \
      --manifest "$FINAL_M0_M3_MANIFEST" --run-label "$FINAL_RUN_LABEL" \
      --scope "$SCOPE" 2>&1)"; then
    record "$CHECK" 1 "$OUT"
  else
    record "$CHECK" 0 "$OUT"
  fi
}

scope_m1() {
  scope_strict_final m1 strict_m1_receipt
}

scope_m2b() {
  scope_strict_final m2b strict_m2_receipt
}

scope_m3() {
  scope_strict_final m3 strict_m3_receipt
}

# ---------------------------------------------------------------- scope: m4
# Current-artifact headed-browser binding for the two M4 pixel gates. The
# verifier re-hashes the shipping JS/primary-Wasm/deferred-Wasm/data set,
# receipts, screenshots, and
# pinned native goldens, then reruns the unchanged oiiotool thresholds. It is a
# receipt verifier, not a browser launcher, so regress remains deterministic.
scope_m4() {
  local VERIFY=sandbox/m4-d9-gate/verify_current_binding.py
  if [ ! -x "$VERIFY" ]; then
    record browser_pixels 0 "missing executable verifier: $VERIFY"
    return
  fi
  local OUT
  if OUT="$(python3 "$VERIFY" 2>&1)"; then
    record browser_pixels 1 "$OUT"
  else
    record browser_pixels 0 "$OUT"
  fi
}

# ---------------------------------------------------------------- scope: m5
# Deterministic current-artifact interaction closeout. The verifier re-hashes
# all immutable browser receipts and shipping artifacts, rechecks seven native/
# Wasm state+trace parity sessions, and enforces the published latency budgets.
# It never launches a browser or performs a build.
scope_m5() {
  local VERIFY=sandbox/m5-final/verify_m5.py
  if [ ! -x "$VERIFY" ]; then
    record interaction_parity 0 "missing executable verifier: $VERIFY"
    return
  fi
  local OUT
  if OUT="$(python3 "$VERIFY" 2>&1)"; then
    record interaction_parity 1 "$OUT"
  else
    record interaction_parity 0 "$OUT"
  fi
}

# ---------------------------------------------------------------- scope: m6
# Current shipping-artifact render matrices. Comparator failures are accepted
# only as explicit measured SKIPs matched by sandbox/m6-prep/blacklist.txt; the
# verifier rejects stale exclusions, unlisted failures, browser/GPU errors, and
# artifact-hash drift.
scope_m6() {
  local VERIFY=sandbox/m6-prep/verify_render_closeout.py
  if [ ! -x "$VERIFY" ]; then
    record render_parity 0 "missing executable verifier: $VERIFY"
    return
  fi
  local OUT
  if OUT="$(python3 "$VERIFY" 2>&1)"; then
    record render_parity 1 "$OUT"
  else
    record render_parity 0 "$OUT"
  fi
}

# ---------------------------------------------------------------- scope: m7
# Strict GOAL.md M7 gate. The verifier also offers `--subset` for the explicitly
# caveated public-preview subset, but the harness never substitutes it for the
# milestone promise (real USD and the stated launch/cross-browser bars remain hard).
scope_m7() {
  local VERIFY=sandbox/m7-product-gate/run.sh
  if [ ! -x "$VERIFY" ]; then
    record files_pipeline 0 "missing executable verifier: $VERIFY"
    return
  fi
  local OUT
  if OUT="$($VERIFY 2>&1)"; then
    record files_pipeline 1 "$OUT"
  else
    record files_pipeline 0 "$OUT"
  fi
}

# ---------------------------------------------------------------- scope: m8
# Locally verifiable technical-release closeout. The default M8 verifier is
# deliberately pre-receipt and non-circular: it consumes exact M0-M7 plus
# staged/performance, product, browser, soak, and compliance evidence. Public
# launch/legal/hosting/publication are not part of this harness scope; the
# post-receipt dashboard is checked separately by `verify_m8.py --post-receipt`.
scope_m8() {
  local VERIFY=sandbox/m8-launch-gate/verify_m8.py
  if [ ! -x "$VERIFY" ]; then
    record technical_release 0 "missing executable verifier: $VERIFY"
    return
  fi
  local OUT
  if OUT="$(python3 "$VERIFY" 2>&1)"; then
    record technical_release 1 "$OUT"
  else
    record technical_release 0 "$OUT"
  fi
}

# ------------------------------------------------------------- scope runner
run_one_scope() {
  local scope="$1"
  case " $SCOPES_REGISTERED " in
    *" $scope "*) : ;;
    *) echo "run.sh: unknown scope '$scope' (registered: $SCOPES_REGISTERED)" >&2; return 2 ;;
  esac

  mkdir -p ledger/results
  TSV="$(mktemp)"
  "scope_${scope}"

  local OUTF="ledger/results/${scope}.json"
  TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)" python3 - "$TSV" "$OUTF" "$scope" <<'PY'
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

  local NTOTAL NPASS
  NTOTAL="$(awk 'END{print NR}' "$TSV")"
  NPASS="$(awk -F'\t' '$2==1{c++} END{print c+0}' "$TSV")"
  while IFS=$'\t' read -r n p d; do
    [ "$p" = 1 ] && printf '  PASS  %-14s %s\n' "$n" "$d" || printf '  FAIL  %-14s %s\n' "$n" "$d"
  done <"$TSV"
  rm -f "$TSV"; TSV=""

  if [ "$NPASS" = "$NTOTAL" ] && [ "$NTOTAL" -gt 0 ]; then
    echo "run.sh: scope=$scope ALL GREEN ($NPASS/$NTOTAL) -> $OUTF"
    return 0
  fi
  echo "run.sh: scope=$scope RED ($NPASS/$NTOTAL) -> $OUTF" >&2
  return 1
}

# ------------------------------------------------------------------- main
MODE="scope"; SCOPE="m0"
while [ $# -gt 0 ]; do
  case "$1" in
    --scope) SCOPE="${2:?--scope needs a value}"; MODE="scope"; shift 2 ;;
    --scope=*) SCOPE="${1#*=}"; MODE="scope"; shift ;;
    --regress) MODE="regress"; shift ;;
    --list) echo "registered scopes: $SCOPES_REGISTERED"; exit 0 ;;
    -h|--help) echo "usage: run.sh [--scope <name>] [--regress] [--list]"; exit 0 ;;
    *) echo "run.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Usage errors (unknown scope) must NOT paint the gate red — a typo would otherwise
# block every agent via the Stop hook. Validate before running anything.
if [ "$MODE" = "scope" ]; then
  case " $SCOPES_REGISTERED " in
    *" $SCOPE "*) : ;;
    *) echo "run.sh: unknown scope '$SCOPE' (registered: $SCOPES_REGISTERED)" >&2; exit 2 ;;
  esac
fi

FAILED=""
if [ "$MODE" = "regress" ]; then
  # H-2: re-run every scope that has a prior result file. No prior results => trivially green.
  shopt -s nullglob
  PRIOR=(ledger/results/*.json)
  shopt -u nullglob
  if [ ${#PRIOR[@]} -eq 0 ]; then
    echo "run.sh: --regress — no prior scope results; nothing to regress (green)"
    exit 0
  fi
  for f in "${PRIOR[@]}"; do
    s="$(basename "$f" .json)"
    echo "--- regress: $s ---"
    run_one_scope "$s" || FAILED="$FAILED $s"
  done
else
  run_one_scope "$SCOPE" || FAILED=" $SCOPE"
fi

# Reconcile the global gate from every registered scope that has a current result,
# not merely from the last scope invoked. A green M5 run must never erase a stored
# red M1/M2/M4/M6 result. Missing result rows remain the responsibility of the
# explicit final --regress/full-closeout workflow.
LEDGER_FAILED="$(python3 - "$SCOPES_REGISTERED" <<'PY'
import json, pathlib, sys
registered = set(sys.argv[1].split())
failed = []
for path in pathlib.Path('ledger/results').glob('*.json'):
    if path.stem not in registered:
        continue
    try:
        value = json.loads(path.read_text())
        if value.get('scope') != path.stem or value.get('pass') is not True:
            failed.append(path.stem)
    except Exception:
        failed.append(path.stem)
print(' '.join(sorted(set(failed))))
PY
)"
if [ -n "$FAILED" ] || [ -n "$LEDGER_FAILED" ]; then
  ALL_FAILED="$(printf '%s\n' $FAILED $LEDGER_FAILED | awk 'NF && !seen[$0]++' | sort | paste -sd ' ' -)"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) GATE_RED failing scopes: $ALL_FAILED" > harness/GATE_RED
  echo "run.sh: GATE_RED — $ALL_FAILED" >&2
  [ -n "$FAILED" ] && exit 1
  exit 0
fi
rm -f harness/GATE_RED
exit 0
