#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# M4-golden-prep — M4 first-pixels comparator (the M4 gate command).
#
# Compares a wasm-side candidate PNG against the staged native golden for a given
# state+size with Blender's OWN pinned oiiotool tolerance. PASS/FAIL is the
# oiiotool EXIT CODE (exit-code-primary — the same m2b/m6-prep pattern the wasm
# side reuses). The core idiff invocation is byte-for-byte the m6-prep /
# upstream modules/render_report.py:138-145 form:
#     oiiotool <golden> <candidate> --fail 0.016 --failpercent 1 --diff
# (exit 0 => within tolerance). Thresholds are Blender's own defaults
# (fail_threshold=0.016, fail_percent=1); NOT weakened for M4.
#
# The only wrap over the verbatim m6-prep invocation: both inputs are reduced to
# R,G,B first (`--ch R,G,B`). The native golden is 3-channel RGB (the screenshot
# operator writes RGB, screendump.cc:120); a browser canvas.toDataURL('image/png')
# is 4-channel RGBA. Without this, oiiotool diffs the golden's absent alpha as 0
# and reports 100% of pixels over threshold — a spurious fail. `--ch R,G,B` is a
# no-op on RGB and drops alpha on RGBA, so the comparison is channel-agnostic
# without touching the thresholds or the exit-code verdict. (A size mismatch —
# e.g. the wasm canvas not exactly WxH — makes oiiotool error => FAIL, correctly.)
#
# Usage:
#   bash sandbox/m4-golden-prep/compare_m4.sh <candidate.png> <splash|workspace> <WxH>
#   bash sandbox/m4-golden-prep/compare_m4.sh --selftest
#
# Exit: 0 = PASS (within tolerance), 1 = FAIL, 2 = usage/missing input.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"
MP=sandbox/m4-golden-prep
GOLD="$ROOT/$MP/goldens"
OIIO="${OIIOTOOL:-oiiotool}"
THR=0.016; FP=1

command -v "$OIIO" >/dev/null || { echo "OIIOTOOL_MISSING $OIIO"; exit 2; }

# core comparison: golden vs candidate, exit-code-primary. echoes PASS/FAIL line,
# returns oiiotool's exit code.
idiff() { # $1=golden $2=candidate $3=label
  local golden="$1" cand="$2" label="$3"
  [ -f "$golden" ] || { echo "FAIL $label  (missing golden $golden)"; return 2; }
  [ -f "$cand" ]   || { echo "FAIL $label  (missing candidate $cand)"; return 2; }
  local out ec
  out="$("$OIIO" "$golden" --ch R,G,B "$cand" --ch R,G,B --fail "$THR" --failpercent "$FP" --diff 2>&1)"; ec=$?
  local maxe stat
  maxe="$(echo "$out" | grep -aoE 'Max error *= *[0-9.e+-]+' | head -1)"
  stat="$(echo "$out" | grep -aoE '[0-9]+ pixels \([0-9.]+%\) over '"$THR" | tail -1)"
  if [ "$ec" = 0 ]; then echo "PASS $label  ${maxe:-} ${stat:+over: $stat}"
  else echo "FAIL $label  ${maxe:-} ${stat:+over: $stat}"; fi
  return $ec
}

if [ "${1:-}" = "--selftest" ]; then
  echo "== M4 comparator self-test (the comparator must have teeth) =="
  rc=0
  shopt -s nullglob 2>/dev/null || true
  any=0
  for g in "$GOLD"/*.png; do
    any=1
    base="$(basename "$g" .png)"          # e.g. workspace_1280x720
    state="${base%%_*}"; size="${base#*_}"
    # (1) identity: golden vs itself MUST PASS
    idiff "$g" "$g" "identity $base"; [ $? -eq 0 ] || { echo "  !! identity should PASS"; rc=1; }
    # (2) teeth: this state vs the OTHER state at the same size MUST FAIL
    other="workspace"; [ "$state" = "workspace" ] && other="splash"
    og="$GOLD/${other}_${size}.png"
    if [ -f "$og" ]; then
      idiff "$g" "$og" "cross $base vs ${other}_${size}"
      [ $? -ne 0 ] && echo "  ok cross-state correctly FAILS" || { echo "  !! cross-state should FAIL"; rc=1; }
    fi
  done
  [ "$any" = 1 ] || { echo "NO GOLDENS staged in $GOLD"; exit 2; }
  [ "$rc" = 0 ] && echo "SELFTEST_PASS" || echo "SELFTEST_FAIL"
  exit $rc
fi

CAND="${1:?usage: compare_m4.sh <candidate.png> <splash|workspace> <WxH>}"
STATE="${2:?usage: compare_m4.sh <candidate.png> <splash|workspace> <WxH>}"
SIZE="${3:?usage: compare_m4.sh <candidate.png> <splash|workspace> <WxH>}"
GOLDEN="$GOLD/${STATE}_${SIZE}.png"
if [ ! -f "$GOLDEN" ]; then
  echo "FAIL no golden for ${STATE}_${SIZE} — available:"
  ls "$GOLD" 2>/dev/null | sed 's/^/    /'
  exit 2
fi
idiff "$GOLDEN" "$CAND" "${STATE}_${SIZE}"
exit $?
