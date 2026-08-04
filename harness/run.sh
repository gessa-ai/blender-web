#!/usr/bin/env bash
# Harness v1.1. Reconciles H-1/H-2/H-3 from notes/harness-issues.md.
#
#   run.sh --scope <name>   run one scope's checks
#   run.sh --regress        re-run EVERY scope that has a prior result file
#   run.sh --list           list registered scopes
#
# Result schema (H-1) — ledger/results/<scope>.json:
#   {"scope":..., "pass":bool, "ts":ISO8601, "checks":{"<name>":{"pass":bool,"detail":"..."}}}
# Gate: exit 0 iff all checks pass; on failure write harness/GATE_RED, else remove it.
# Token thrift: builds go through harness/buildwrap.sh (one line ok / capped errors on fail,
# full log under ledger/buildlogs/). This script prints a short per-check summary only.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SCOPES_REGISTERED="m0 m1"
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

# ---------------------------------------------------------------- scope: m1
# Tier-(a): Blender's own blenlib + bmesh_core gtest suites on wasm32 under node.
# Runs the built artifacts (fast, ~3s). If artifacts are missing, FAILS with the rebuild
# recipe in the detail — rebuilding is a driver/worker action, not a harness side effect:
#   blenlib:    (WITH_TESTS_SINGLE_BINARY=ON tree)  ninja -C build-wasm BLI_test
#   bmesh_core: (WITH_TESTS_SINGLE_BINARY=OFF tree) ninja -C build-wasm bmesh_core_test
# Expected: blenlib 1655 PASSED / 10 FAILED (9x expr_pylike fenv deferral
# [ledger/deferred.json wasm-fp-exception-status] + 1x macOS-host CWD realpath);
# bmesh_core 1 PASSED / 0 FAILED (= the full upstream suite at this pin).
scope_m1() {
  local NODE
  NODE="$(ls -d tools/emsdk/node/*/bin/node 2>/dev/null | head -1)"
  if [ -z "$NODE" ]; then
    record node_runtime 0 "no emsdk node under tools/emsdk/node/*/bin/node"
    return
  fi
  record node_runtime 1 "$NODE ($("$NODE" --version 2>/dev/null))"

  # 1) patch series consistency: every patches/0*.patch either applies clean (pristine
  #    tree) or reverse-applies clean (= is currently applied). Mixed/conflicted = FAIL.
  local P BAD="" STATE=""
  for P in patches/0*.patch; do
    if git -C upstream apply --check "../$P" >/dev/null 2>&1; then
      STATE="$STATE ${P##*/}:clean"
    elif git -C upstream apply --check --reverse "../$P" >/dev/null 2>&1; then
      STATE="$STATE ${P##*/}:applied"
    else
      BAD="$BAD ${P##*/}"
    fi
  done
  if [ -z "$BAD" ]; then
    record patches_series 1 "all patches clean-or-applied:$STATE"
  else
    record patches_series 0 "patches neither apply nor reverse-apply (conflict):$BAD"
  fi

  # NOTE: stdout from these binaries is UNRELIABLE under capture (multi-thread wasm stdio
  # races drop lines at exit) — counts MUST come from --gtest_output=json (written via
  # NODERAWFS, relative path required; absolute paths silently fail).
  gtest_json_counts() {  # $1=artifact $2...=extra args; prints "tests failures" or "ERR"
    local ART="$1"; shift
    local J="harness_gtest_$$.json"
    "$NODE" "$ART" "$@" --gtest_output="json:$J" >/dev/null 2>&1
    if [ -f "$J" ]; then
      python3 -c "import json,sys; d=json.load(open('$J')); print(d['tests'], d['failures'])" 2>/dev/null || echo ERR
      rm -f "$J"
    else
      echo ERR
    fi
  }

  # 2) blenlib gtests (prefer the NODERAWFS artifact; both link profiles are equivalent)
  local BLI=""
  [ -f build-wasm/bin/tests/BLI_test_rawfs.js ] && BLI=build-wasm/bin/tests/BLI_test_rawfs.js
  [ -z "$BLI" ] && [ -f build-wasm/bin/tests/BLI_test.js ] && BLI=build-wasm/bin/tests/BLI_test.js
  if [ -z "$BLI" ]; then
    record blenlib_gtests 0 "artifact missing; rebuild: WITH_TESTS_SINGLE_BINARY=ON + ninja -C build-wasm BLI_test"
  else
    local CNT NT NF
    CNT="$(gtest_json_counts "$BLI" --test-assets-dir upstream/tests/files)"
    NT="${CNT% *}"; NF="${CNT#* }"
    if [ "$NT" = 1665 ] && [ "$NF" = 10 ]; then
      record blenlib_gtests 1 "1655/1665 PASSED, 10 characterized non-passes (9 fenv-deferral + 1 macOS-host chdir) [$BLI]"
    else
      record blenlib_gtests 0 "gtest json tests=$NT failures=$NF (expected 1665/10) [$BLI]"
    fi
  fi

  # 3) bmesh_core gtests (tier-(a) gate 2/2)
  if [ ! -f build-wasm/bin/tests/bmesh_core_test.js ]; then
    record bmesh_core_gtests 0 "artifact missing; rebuild: cmake -DWITH_TESTS_SINGLE_BINARY=OFF build-wasm + ninja -C build-wasm bmesh_core_test"
  else
    local CNTM NTM NFM
    CNTM="$(gtest_json_counts build-wasm/bin/tests/bmesh_core_test.js)"
    NTM="${CNTM% *}"; NFM="${CNTM#* }"
    if [ "$NTM" = 1 ] && [ "$NFM" = 0 ]; then
      record bmesh_core_gtests 1 "1/1 PASSED (= full upstream bmesh_core suite at this pin)"
    else
      record bmesh_core_gtests 0 "gtest json tests=$NTM failures=$NFM (expected 1/0)"
    fi
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

if [ -n "$FAILED" ]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) GATE_RED failing scopes:$FAILED" > harness/GATE_RED
  echo "run.sh: GATE_RED —$FAILED" >&2
  exit 1
fi
rm -f harness/GATE_RED
exit 0
