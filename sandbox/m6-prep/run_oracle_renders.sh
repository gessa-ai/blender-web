#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# M6-prep — ORACLE-SIDE render comparator (workbench + EEVEE + Cycles-CPU).
#
# For each test in manifest.tsv: render the .blend on the native pinned oracle with
# the EXACT upstream engine invocation, then compare the render against the staged
# golden with Blender's OWN pinned oiiotool threshold for that engine+dir. PASS/FAIL
# is the oiiotool EXIT CODE (exit-code-primary, the m2b pattern the wasm side reuses):
#   oiiotool <golden> <render> --fail <thr> --failpercent <fp> --diff   (exit 0 => within tolerance)
# This is byte-for-byte the invocation in upstream modules/render_report.py:138-145
# (fail_threshold=0.016, fail_percent=1 defaults; per-engine/-dir overrides in the manifest).
#
# Blacklisted tests (blacklist.txt) report SKIP, mirroring render_report.blend_list
# dropping native BLOCKLIST matches. No raw logs surfaced — one line per test + a tally.
#
# ENGINE ORACLES (see notes/m6-prep.md): workbench + EEVEE render on the native
# macOS Metal oracle (--gpu-backend metal; GPU backends work headless on macOS,
# which is why the host binary — not a Linux Docker — is the EEVEE oracle, mirroring
# Blender CI generating GPU references on real adapters). Cycles renders on CPU.
#
# Usage:
#   bash sandbox/m6-prep/run_oracle_renders.sh [--engine workbench|eevee|cycles] [--filter <substr>]
#   bash sandbox/m6-prep/run_oracle_renders.sh --determinism   # 3 samples x2, threshold-identical
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"
MP=sandbox/m6-prep
BIN="${BLENDER_BIN:-$ROOT/oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender}"
OIIO="${OIIOTOOL:-oiiotool}"
MAN="$ROOT/$MP/manifest.tsv"
BLK="$ROOT/$MP/blacklist.txt"
OUT="$ROOT/$MP/oracle_renders"
SCR="${TMPDIR:-/tmp}/m6oracle.$$"
WB_SCRIPT="$ROOT/upstream/tests/python/workbench_render_tests.py"
EE_SCRIPT="$ROOT/upstream/tests/python/eevee_render_tests.py"
CY_SCRIPT="$ROOT/upstream/tests/python/cycles_render_tests.py"
COMMON=(--background --factory-startup --enable-autoexec --debug-memory --console-crash-handler --debug-exit-on-error)
mkdir -p "$OUT" "$SCR"

FILT_ENGINE=""; FILT_SUB=""; MODE=run
while [ $# -gt 0 ]; do case "$1" in
  --engine) FILT_ENGINE="$2"; shift 2;;
  --filter) FILT_SUB="$2"; shift 2;;
  --determinism) MODE=determinism; shift;;
  *) echo "unknown arg: $1"; exit 2;;
esac; done

[ -x "$BIN" ] || { echo "ORACLE_MISSING $BIN"; exit 2; }
command -v "$OIIO" >/dev/null || { echo "OIIOTOOL_MISSING $OIIO"; exit 2; }
[ -f "$MAN" ] || { echo "NO_MANIFEST — run stage_goldens.sh first"; exit 2; }

# blacklist match: is <engine>/<test> skipped? (engine field == engine or '*', regex re.match on <test>.blend)
is_blacklisted() { # $1=engine $2=test
  [ -f "$BLK" ] || return 1
  local eng test line be re
  eng="$1"; test="$2.blend"
  while IFS= read -r line; do
    case "$line" in ''|\#*) continue;; esac
    be="${line%%[[:space:]]*}"; re="$(echo "${line#"$be"}" | sed -E 's/^[[:space:]]+//; s/[[:space:]]*#.*$//')"
    [ "$be" = "$eng" ] || [ "$be" = "*" ] || continue
    [ -n "$re" ] || continue
    echo "$test" | grep -Eq "^$re" && return 0
  done < "$BLK"
  return 1
}

# render one test -> writes <dst_base>0001.png ; echoes exit code
render() { # $1=engine $2=blend(abs) $3=dst_base
  local engine="$1" blend="$2" base="$3"
  rm -f "${base}0001.png"
  case "$engine" in
    workbench) timeout 300 "$BIN" "${COMMON[@]}" --gpu-backend metal "$blend" -E BLENDER_WORKBENCH -P "$WB_SCRIPT" -o "$base" -F PNG -f 1 >/dev/null 2>&1;;
    eevee)     timeout 300 "$BIN" "${COMMON[@]}" --gpu-backend metal "$blend" -E BLENDER_EEVEE     -P "$EE_SCRIPT" -o "$base" -F PNG -f 1 >/dev/null 2>&1;;
    cycles)    timeout 300 "$BIN" "${COMMON[@]}" "$blend" -E CYCLES -P "$CY_SCRIPT" -o "$base" -F PNG -f 1 -- --cycles-device CPU >/dev/null 2>&1;;
  esac
}

# ensure a blend input is materialized (not an LFS pointer); print pull cmd if not
need_input() { # $1=blend(rel)
  local f="$ROOT/$1"
  [ -f "$f" ] || { echo "MISSING_INPUT $1"; return 1; }
  if head -c 64 "$f" | grep -qa '^version https://git-lfs'; then
    echo "LFS_POINTER $1 — materialize with:"
    echo "  ( cd upstream && git lfs pull --include=\"${1#upstream/}\" )"
    return 1
  fi
  return 0
}

if [ "$MODE" = determinism ]; then
  # One sample per engine: render twice, assert renders are threshold-identical (0.016/1)
  echo "== M6 oracle determinism (3 samples x2) =="
  samples=$(awk -F'\t' 'NR>1 && !seen[$1]++ {print $1"\t"$3"\t"$4}' "$MAN")   # engine test blend
  ok=1
  while IFS=$'\t' read -r engine test blend; do
    need_input "$blend" || { ok=0; continue; }
    b1="$SCR/det_${engine}_${test}.1"; b2="$SCR/det_${engine}_${test}.2"
    render "$engine" "$ROOT/$blend" "$b1"; render "$engine" "$ROOT/$blend" "$b2"
    if [ ! -s "${b1}0001.png" ] || [ ! -s "${b2}0001.png" ]; then echo "FAIL $engine/$test (no render)"; ok=0; continue; fi
    h1=$(shasum -a256 < "${b1}0001.png"|cut -d' ' -f1); h2=$(shasum -a256 < "${b2}0001.png"|cut -d' ' -f1)
    if [ "$h1" = "$h2" ]; then echo "PASS $engine/$test  byte-identical  $h1"
    else
      "$OIIO" "${b1}0001.png" "${b2}0001.png" --fail 0.016 --failpercent 1 --diff >/dev/null 2>&1 \
        && echo "PASS $engine/$test  threshold-identical (0.016/1), sha differ ($h1 vs $h2)" \
        || { echo "FAIL $engine/$test  NON-DETERMINISTIC beyond 0.016/1"; ok=0; }
    fi
  done <<< "$samples"
  rm -rf "$SCR"; [ "$ok" = 1 ] && echo "DET_ALL_PASS" || { echo "DET_SOME_FAIL"; exit 1; }
  exit 0
fi

# Full comparator run
pass=0; fail=0; skip=0; blocked=0
echo "== M6 oracle render comparator =="
while IFS=$'\t' read -r engine dir test blend golden thr fp; do
  case "$engine" in ''|\#*) continue;; esac
  [ -z "$FILT_ENGINE" ] || [ "$FILT_ENGINE" = "$engine" ] || continue
  [ -z "$FILT_SUB" ] || case "$dir/$test" in *"$FILT_SUB"*) : ;; *) continue;; esac
  if is_blacklisted "$engine" "$test"; then echo "SKIP $engine/$dir/$test  (blacklist)"; skip=$((skip+1)); continue; fi
  if ! need_input "$blend"; then blocked=$((blocked+1)); continue; fi
  base="$SCR/${engine}_${dir}_${test}"
  render "$engine" "$ROOT/$blend" "$base"
  new="${base}0001.png"
  if [ ! -s "$new" ]; then echo "FAIL $engine/$dir/$test  (NO OUTPUT)"; fail=$((fail+1)); continue; fi
  # persist the oracle render as a same-adapter baseline
  odst="$OUT/$engine/$dir"; mkdir -p "$odst"; cp "$new" "$odst/$test.png"
  # exact upstream idiff — exit code is the verdict
  diffout=$("$OIIO" "$ROOT/$golden" "$new" --fail "$thr" --failpercent "$fp" --diff 2>&1); ec=$?
  stat=$(echo "$diffout" | grep -aoE '[0-9.]+% *\) over [0-9.e-]+' | tail -1)
  maxe=$(echo "$diffout" | grep -aoE 'Max error *= *[0-9.e-]+' | head -1)
  if [ "$ec" = 0 ]; then echo "PASS $engine/$dir/$test  ${maxe:-} ${stat:+over: $stat}"; pass=$((pass+1))
  else echo "FAIL $engine/$dir/$test  ${maxe:-} ${stat:+over: $stat}"; fail=$((fail+1)); fi
done < "$MAN"

rm -rf "$SCR"
echo "-- summary: PASS=$pass FAIL=$fail SKIP=$skip BLOCKED=$blocked --"
[ "$fail" = 0 ] && [ "$blocked" = 0 ] && echo "ALL_PASS" || { echo "SOME_FAIL"; exit 1; }
