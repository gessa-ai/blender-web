#!/usr/bin/env bash
# Harness v1 (M0.5). `run.sh --scope m0` runs the toolchain+oracle smokes, writes a
# JSON array of {name,pass,detail} to ledger/results/<scope>.json, and gates:
#   - exit 0 iff ALL checks pass
#   - on any failure, write harness/GATE_RED with a one-line summary
#   - remove harness/GATE_RED when all green
# Token thrift: builds go through harness/buildwrap.sh (one line ok / capped errors on fail,
# full log under ledger/buildlogs/). This script prints a short per-check summary only.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SCOPE="m0"
while [ $# -gt 0 ]; do
  case "$1" in
    --scope) SCOPE="${2:?--scope needs a value}"; shift 2 ;;
    --scope=*) SCOPE="${1#*=}"; shift ;;
    -h|--help) echo "usage: run.sh [--scope m0]"; exit 0 ;;
    *) echo "run.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ "$SCOPE" != "m0" ]; then
  echo "run.sh: only --scope m0 is implemented (got: $SCOPE)" >&2
  exit 2
fi

mkdir -p ledger/results
TSV="$(mktemp)"; trap 'rm -f "$TSV"' EXIT
EMSDK_ENV="tools/emsdk/emsdk_env.sh"

# record NAME PASS(0|1) DETAIL...   (detail is forced to a single line)
record() {
  local name="$1" pass="$2"; shift 2
  local detail="$*"
  detail="${detail//$'\t'/ }"; detail="${detail//$'\n'/ }"
  printf '%s\t%s\t%s\n' "$name" "$pass" "$detail" >>"$TSV"
}

# $1 >= $2 for dotted versions -> prints 1 or 0
ver_ge() {
  awk -v a="$1" -v b="$2" 'BEGIN{
    na=split(a,A,"."); nb=split(b,B,"."); n=(na>nb)?na:nb;
    for(i=1;i<=n;i++){x=(i<=na?A[i]+0:0);y=(i<=nb?B[i]+0:0);
      if(x>y){print 1;exit} if(x<y){print 0;exit}} print 1}'
}

# 1) toolchain: oracle/TOOLCHAIN exists and records emcc >= 4.0.10
if [ -f oracle/TOOLCHAIN ]; then
  EMV="$(grep -oE 'emcc [0-9]+\.[0-9]+\.[0-9]+' oracle/TOOLCHAIN | head -1 | awk '{print $2}')"
  if [ -n "$EMV" ] && [ "$(ver_ge "$EMV" 4.0.10)" = 1 ]; then
    record toolchain 1 "oracle/TOOLCHAIN records emcc $EMV (>= 4.0.10)"
  else
    record toolchain 0 "emcc '$EMV' < 4.0.10 or unparseable in oracle/TOOLCHAIN"
  fi
else
  record toolchain 0 "oracle/TOOLCHAIN missing"
fi

# 2) hello_wasm: compile sandbox/hello.c via buildwrap, run in node, expect 'hello'
TMPD="$(mktemp -d)"
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

# 3) emdawnwebgpu: emcc --use-port=emdawnwebgpu -c compiles via buildwrap
if harness/buildwrap.sh bash -c "source $EMSDK_ENV >/dev/null 2>&1 && emcc --use-port=emdawnwebgpu -c sandbox/hello.c -o /tmp/hw.o" >/dev/null 2>&1; then
  record emdawnwebgpu 1 "emcc --use-port=emdawnwebgpu -c ok (/tmp/hw.o)"
else
  record emdawnwebgpu 0 "emdawnwebgpu port compile failed (see ledger/buildlogs/)"
fi

# 4) oracle_version: bpy.sh --version contains 'Blender 5.2.0' AND the pin hash
OV="$(oracle/bpy.sh --version 2>&1)"; OV1="$(printf '%s' "$OV" | grep -m1 -i blender | head -1)"
if printf '%s' "$OV" | grep -q "Blender 5.2.0" && printf '%s' "$OV" | grep -q "fbe6228777e7"; then
  record oracle_version 1 "${OV1:-Blender 5.2.0 fbe6228777e7}"
else
  record oracle_version 0 "missing 'Blender 5.2.0' and/or 'fbe6228777e7': ${OV1}"
fi

# 5) oracle_bpy: default scene has Camera, Cube, Light
OB="$(oracle/bpy.sh --python-expr "import bpy; print(sorted(bpy.data.objects.keys()))" 2>&1)"
if printf '%s' "$OB" | grep -q Camera && printf '%s' "$OB" | grep -q Cube && printf '%s' "$OB" | grep -q Light; then
  record oracle_bpy 1 "default objects present: Camera, Cube, Light"
else
  record oracle_bpy 0 "default objects missing (Camera/Cube/Light)"
fi

# 6) oiiotool: --version exits 0
if OIIO="$(oiiotool --version 2>&1)"; then
  record oiiotool 1 "$(printf '%s' "$OIIO" | head -1)"
else
  record oiiotool 0 "oiiotool --version nonzero or not on PATH"
fi

# --- emit JSON array + tally ---
OUTF="ledger/results/${SCOPE}.json"
python3 - "$TSV" "$OUTF" <<'PY'
import json, sys
tsv, outp = sys.argv[1], sys.argv[2]
rows = []
with open(tsv) as f:
    for line in f:
        line = line.rstrip("\n")
        if not line:
            continue
        name, pas, detail = line.split("\t", 2)
        rows.append({"name": name, "pass": pas == "1", "detail": detail})
with open(outp, "w") as f:
    json.dump(rows, f, indent=2)
    f.write("\n")
PY

NTOTAL="$(awk 'END{print NR}' "$TSV")"
NPASS="$(awk -F'\t' '$2==1{c++} END{print c+0}' "$TSV")"
while IFS=$'\t' read -r n p d; do
  [ "$p" = 1 ] && printf '  PASS  %-14s %s\n' "$n" "$d" || printf '  FAIL  %-14s %s\n' "$n" "$d"
done <"$TSV"

if [ "$NPASS" = "$NTOTAL" ] && [ "$NTOTAL" -gt 0 ]; then
  rm -f harness/GATE_RED
  echo "run.sh: scope=$SCOPE ALL GREEN ($NPASS/$NTOTAL) -> $OUTF"
  exit 0
else
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) GATE_RED scope=$SCOPE $NPASS/$NTOTAL passed — see $OUTF" > harness/GATE_RED
  echo "run.sh: scope=$SCOPE GATE_RED ($NPASS/$NTOTAL) -> $OUTF" >&2
  exit 1
fi
