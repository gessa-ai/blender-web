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

SCOPES_REGISTERED="m0 m1 m2b"
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
      # Third honest state: the patch's target files are being actively extended by an
      # in-flight lane (working tree ahead of the captured patch). Not a conflict — the
      # lane regenerates the patch at its own commit gate; a TRUE conflict is a patch
      # failing both ways while touching files nobody has modified.
      local PFILES MODOK=1 F
      PFILES="$(grep -E '^\+\+\+ b/' "$P" | sed 's|^+++ b/||' | sort -u)"
      for F in $PFILES; do
        git -C upstream status --porcelain -- "$F" 2>/dev/null | grep -q . || { MODOK=0; break; }
      done
      if [ "$MODOK" = 1 ] && [ -n "$PFILES" ]; then
        STATE="$STATE ${P##*/}:in-development"
      else
        BAD="$BAD ${P##*/}"
      fi
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

  # 4) .blend corpus state-dump parity (M1.12): live single-file proof + static 9-file
  #    fingerprint check. Full re-run: bash sandbox/corpus-prep/run_dumps_wasm.sh
  local PREP=sandbox/corpus-prep
  if [ ! -f build-wasm/bin/blender.js ] || [ ! -f "$PREP/state_dump.py" ]; then
    record corpus_parity 0 "blender.js or corpus tooling missing; see $PREP/"
  else
    local TMPD; TMPD="$(mktemp -d)"
    ( export BLENDER_SYSTEM_RESOURCES="$PWD/upstream" BLENDER_SYSTEM_PYTHON="$PWD/lib/wasm" \
             BLENDER_SYSTEM_DATAFILES="$PWD/upstream/release/datafiles"; \
      "$NODE" build-wasm/bin/blender.js --background --factory-startup \
        --python "$PREP/state_dump.py" -- upstream/release/datafiles/startup.blend \
        "$TMPD/startup.json" >/dev/null 2>&1 )
    local LIVE_OK=0 STATIC_OK=0
    if [ -s "$TMPD/startup.json" ] && cmp -s "$TMPD/startup.json" "$PREP/goldens-candidate/startup.json"; then
      LIVE_OK=1
    fi
    STATIC_OK="$(python3 - "$PREP" <<'PY'
import hashlib, json, pathlib, sys
prep = pathlib.Path(sys.argv[1])
man = json.load(open(prep / "goldens-candidate" / "MANIFEST.json"))["files"]
ok = 0
try:
    for label, meta in man.items():
        d = prep / "dumps-wasm" / f"{label}.json"
        if hashlib.sha256(d.read_bytes()).hexdigest() != meta["dump_sha256"]:
            raise SystemExit(print(0))
    ok = 1
except Exception:
    ok = 0
print(ok)
PY
)"
    rm -rf "$TMPD"
    if [ "$LIVE_OK" = 1 ] && [ "$STATIC_OK" = 1 ]; then
      record corpus_parity 1 "live startup re-dump byte==golden + all 9 committed wasm dumps sha256==MANIFEST (exact mode, tolerance 0)"
    else
      record corpus_parity 0 "live_startup_ok=$LIVE_OK static_9file_ok=$STATIC_OK — rerun bash $PREP/run_dumps_wasm.sh for detail"
    fi
  fi
}

# ---------------------------------------------------------------- scope: m2b
# Tier-(b): Blender's stock --background --factory-startup Python operator/bpy-API CORE suite
# (75 rows of sandbox/tierb-prep/suites.tsv) run on the wasm build (build-wasm/bin/blender.js
# under emsdk node) and matched to the native oracle. EXIT-CODE is the gate signal: wasm threaded
# stdout drops lines at exit (H-4/H-5), exactly like the tier-(a) gtests, so counts come from the
# process exit code (--python-exit-code 1 + --debug-exit-on-error make any failing assert nonzero),
# never from scraped stdout. Full evidence + running scoreboard: notes/m2-tierb-prep.md §6/§6b.
scope_m2b() {
  local PREP=sandbox/tierb-prep
  local NODE; NODE="$(ls -d tools/emsdk/node/*/bin/node 2>/dev/null | head -1)"

  # --- config: bump these ONE-LINE flags as pending deps land (moves a named group to must-pass)
  local ESSENTIALS_LANDED=1   # §6a asset-storage fix -> object_edit,bl_brush,bl_sculpt_brushes (+3)
  local NUMPY_HARVESTED=1     # numpy in lib/wasm    -> the 8 sculpt/paint numpy suites          (+8)

  # --- suite classification (everything NOT listed here defaults to MUST-PASS) -----------------
  # DEFERRED (deterministic): expected to FAIL on the current build; each MUST have a matching
  #   ledger/deferred.json id. A deterministic-deferred suite that PASSES => un-defer candidate
  #   (flagged, never silently green).  suite -> deferred.json id:
  local -A DEFERRED=(
    [script_pyapi_mathutils]=float32-ulp-mathutils
    [script_pyapi_bmesh]=float32-ulp-mathutils
    [bl_constraints]=float32-ulp-mathutils
    [bl_node_structure_type_inference]=wasm32-64bit-blend-collision
    # feature compiled OFF per GOAL (OpenVDB / OpenSubdiv / Cycles engine / AVIF codec):
    [bl_voxel_remesh]=feature-off-openvdb
    [bl_voxel_remesh_compare]=feature-off-openvdb
    [bl_multires]=feature-off-opensubdiv
    [bl_sculpt_brushes]=feature-off-opensubdiv
    [bl_node_link_drag]=feature-off-cycles-engine
    [imbuf_py_api]=feature-off-avif
  )
  # FLAKY: deferred heisenbug — EITHER outcome is consistent (no un-defer flag on a pass); id req'd.
  local -A FLAKY=( [bl_node_copy_operators]=node-ungroup-socket-flake )
  # PENDING: promise-held; allowed-fail until its dep lands, then the flag above makes it must-pass.
  local PENDING_ESSENTIALS="object_edit bl_brush"
  local PENDING_NUMPY="script_pyapi_prop_array bl_sculpt_brush_curve_presets bl_sculpt_mask \
bl_sculpt_face_set bl_sculpt_mesh_filter bl_sculpt_automasking bl_vertex_paint_brushes \
bl_weight_paint_brushes"

  # --- preflight artifacts (FAIL with rebuild recipe; a rebuild is a worker action, not a side effect)
  if [ -z "$NODE" ]; then
    record wasm_runtime 0 "no emsdk node under tools/emsdk/node/*/bin/node"; return
  fi
  if [ ! -f build-wasm/bin/blender.js ]; then
    record wasm_runtime 0 "build-wasm/bin/blender.js missing; rebuild: flip WITH_PYTHON ON + \
blender_web_node_binary(blender) + ninja -C build-wasm blender (see notes/m2-python-boot.md)"; return
  fi
  if [ ! -d lib/wasm/lib/python3.13 ]; then
    record wasm_runtime 0 "lib/wasm python harvest missing; rebuild: bash scripts/deps/python.sh"; return
  fi
  record wasm_runtime 1 "$NODE ($("$NODE" --version 2>/dev/null)); blender.js + lib/wasm present"

  # --- run the 75 CORE suites (EXIT-CODE per suite -> $PREP/results-wasm.tsv). ~150 s. -----------
  # run_core_wasm.sh runs exactly the CORE set (it skips the 5 AMBER + 1 design-excluded) and
  # composes the datafiles payload idempotently. If it is absent the scope cannot proceed.
  if [ ! -x "$PREP/run_core_wasm.sh" ]; then
    record m2b_manifest 0 "$PREP/run_core_wasm.sh missing (tier-b harness kit not present)"; return
  fi
  "$PREP/run_core_wasm.sh" >/dev/null 2>&1
  local RES="$PREP/results-wasm.tsv"
  local NROWS; NROWS="$(grep -cvE '^#' "$RES" 2>/dev/null || echo 0)"
  if [ "$NROWS" != 75 ]; then
    record m2b_manifest 0 "expected 75 CORE rows, got $NROWS (suites.tsv drift?) [$RES]"; return
  fi
  record m2b_manifest 1 "75 CORE rows executed [$RES]"

  # --- classify each row by EXIT CODE (col 3). verdict col 2 is advisory; exit is the gate. -----
  local mustpass_total=0 mustpass_green=0 mustfail=""     # must-pass set
  local undefer=""                                        # deterministic-deferred that PASSED
  local undoc=""                                          # deferred/flaky suite w/o deferred.json id
  local pending_ready=""                                  # a not-yet-landed PENDING suite that PASSED
  local DEF_IDS; DEF_IDS="$(python3 -c "import json;print(' '.join(e['id'] for e in json.load(open('ledger/deferred.json'))['deferred']))" 2>/dev/null)"
  in_set() { case " $2 " in *" $1 "*) return 0;; *) return 1;; esac; }

  local name exit rest
  while IFS=$'\t' read -r name _verdict exit rest; do
    case "$name" in ''|\#*) continue;; esac
    local passed=0; [ "$exit" = 0 ] && passed=1

    if [ -n "${DEFERRED[$name]:-}" ]; then
      in_set "${DEFERRED[$name]}" "$DEF_IDS" || undoc="$undoc $name(${DEFERRED[$name]})"
      [ "$passed" = 1 ] && undefer="$undefer $name(${DEFERRED[$name]})"
    elif [ -n "${FLAKY[$name]:-}" ]; then
      in_set "${FLAKY[$name]}" "$DEF_IDS" || undoc="$undoc $name(${FLAKY[$name]})"
      # either outcome consistent -> no gate effect
    elif in_set "$name" "$PENDING_ESSENTIALS"; then
      if [ "$ESSENTIALS_LANDED" = 1 ]; then
        mustpass_total=$((mustpass_total+1)); [ "$passed" = 1 ] && mustpass_green=$((mustpass_green+1)) || mustfail="$mustfail $name"
      elif [ "$passed" = 1 ]; then pending_ready="$pending_ready $name(flip ESSENTIALS_LANDED=1)"; fi
    elif in_set "$name" "$PENDING_NUMPY"; then
      if [ "$NUMPY_HARVESTED" = 1 ]; then
        mustpass_total=$((mustpass_total+1)); [ "$passed" = 1 ] && mustpass_green=$((mustpass_green+1)) || mustfail="$mustfail $name"
      elif [ "$passed" = 1 ]; then pending_ready="$pending_ready $name(flip NUMPY_HARVESTED=1)"; fi
    else
      # default: MUST-PASS (also auto-requires any new deterministic-green suite added to the manifest)
      mustpass_total=$((mustpass_total+1)); [ "$passed" = 1 ] && mustpass_green=$((mustpass_green+1)) || mustfail="$mustfail $name"
    fi
  done < <(grep -vE '^#' "$RES")

  # --- CHECK 1: core green — every must-pass suite exits 0 (fast-fail: names the reds) ----------
  if [ "$mustpass_green" = "$mustpass_total" ] && [ "$mustpass_total" -ge 64 ]; then
    record core_green 1 "$mustpass_green/$mustpass_total must-pass CORE suites exit 0 \
(ESSENTIALS_LANDED=$ESSENTIALS_LANDED NUMPY_HARVESTED=$NUMPY_HARVESTED)"
  else
    record core_green 0 "must-pass RED $mustpass_green/$mustpass_total; failing:${mustfail:- none} \
(min-expected 54; if a suite regressed, that is the gate)"
  fi

  # --- CHECK 2: deferral consistency vs ledger/deferred.json (honest, no silent green) ----------
  local dc_detail="" dc_ok=1
  [ -n "$undoc" ] && { dc_ok=0; dc_detail="$dc_detail undocumented-deferral:$undoc (add to deferred.json);"; }
  [ -n "$undefer" ] && { dc_ok=0; dc_detail="$dc_detail UN-DEFER-candidate (deterministic-deferred now PASSES):$undefer;"; }
  [ -n "$pending_ready" ] && { dc_ok=0; dc_detail="$dc_detail PENDING-now-green:$pending_ready;"; }
  if [ "$dc_ok" = 1 ]; then
    record deferral_consistency 1 "all deferred/flaky suites map to a deferred.json id and behave as classified"
  else
    record deferral_consistency 0 "${dc_detail# }"
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
