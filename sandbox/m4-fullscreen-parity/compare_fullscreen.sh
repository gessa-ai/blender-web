#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# M4-fullscreen-parity - full-window parity comparator.
#
# Mirrors sandbox/m4-golden-prep/compare_m4.sh VERBATIM on threshold discipline:
# PASS/FAIL is the oiiotool EXIT CODE of
#     oiiotool <golden> --ch R,G,B <candidate> --ch R,G,B --fail 0.016 --failpercent 1 --diff
# (exit 0 => within tolerance). Thresholds are Blender's OWN defaults
# (fail_threshold=0.016, fail_percent=1); NEVER weakened. Both inputs are reduced
# to R,G,B first: the native golden is 3-channel RGB (screendump.cc:120), a browser
# canvas capture is 4-channel RGBA; --ch R,G,B is a no-op on RGB and drops alpha on
# RGBA, so the comparison is channel-agnostic without touching the verdict. A size
# mismatch makes oiiotool error => FAIL, correctly.
#
# Subcommands:
#   compare_fullscreen.sh <candidate.png> <state> <WxH>        PASS/FAIL verdict (exit-code primary)
#   compare_fullscreen.sh --selftest                           identity PASS + perturbed FAIL (teeth)
#   compare_fullscreen.sh --regions <candidate.png> <state> <WxH>   per-region % over threshold
#   compare_fullscreen.sh --composite <candidate.png> <state> <WxH> [out.png]
#                                                              human-facing native|web|heatmap PNG (+ verdict)
#
# Exit: 0 = PASS (within tolerance), 1 = FAIL, 2 = usage/missing input.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"
MP=sandbox/m4-fullscreen-parity
GOLD="$ROOT/$MP/goldens"
ART="$ROOT/$MP/artifacts"
OIIO="${OIIOTOOL:-oiiotool}"
THR=0.016; FP=1

command -v "$OIIO" >/dev/null || { echo "OIIOTOOL_MISSING $OIIO"; exit 2; }

# core comparison: golden vs candidate, exit-code-primary. Echoes PASS/FAIL, returns oiiotool's code.
idiff() { # $1=golden $2=candidate $3=label
  local golden="$1" cand="$2" label="$3"
  [ -f "$golden" ] || { echo "FAIL $label  (missing golden $golden)"; return 2; }
  [ -f "$cand" ]   || { echo "FAIL $label  (missing candidate $cand)"; return 2; }
  local out ec
  out="$("$OIIO" "$golden" --ch R,G,B "$cand" --ch R,G,B --fail "$THR" --failpercent "$FP" --diff 2>&1)"; ec=$?
  local maxe stat mean
  maxe="$(echo "$out" | grep -aoE 'Max error *= *[0-9.e+-]+' | head -1)"
  mean="$(echo "$out" | grep -aoE 'Mean error *= *[0-9.e+-]+' | head -1)"
  stat="$(echo "$out" | grep -aoE '[0-9]+ pixels \([0-9.]+%\) over '"$THR" | tail -1)"
  if [ "$ec" = 0 ]; then echo "PASS $label  ${maxe:-}  ${mean:-} ${stat:+| $stat}"
  else echo "FAIL $label  ${maxe:-}  ${mean:-} ${stat:+| $stat}"; fi
  return $ec
}

# per-region diff of the SAME rect from both images (native-layout coordinates).
region_diff() { # $1=golden $2=cand $3=name $4=geom(WxH+X+Y)
  local golden="$1" cand="$2" name="$3" geom="$4" out ec pct mean
  out="$("$OIIO" "$golden" --cut "$geom" --ch R,G,B "$cand" --cut "$geom" --ch R,G,B \
         --fail "$THR" --failpercent "$FP" --diff 2>&1)"; ec=$?
  pct="$(echo "$out" | grep -aoE '\([0-9.]+%\) over '"$THR" | head -1 | grep -oE '[0-9.]+%')"
  mean="$(echo "$out" | grep -aoE 'Mean error *= *[0-9.e+-]+' | head -1 | grep -oE '[0-9.e-]+$')"
  local verdict; [ "$ec" = 0 ] && verdict=PASS || verdict=FAIL
  printf '  %-11s %-16s  %-4s  %6s over %s   mean %s\n' "$name" "$geom" "$verdict" "${pct:-0%}" "$THR" "${mean:-?}"
  return $ec
}

# native-layout region rects for the workspace state (approximate; characterization aid).
REGIONS=(
  "topbar     1600x52+0+0"
  "toolbar    60x763+0+52"
  "viewport   1262x763+60+52"
  "sidebar    278x763+1322+52"
  "statusbar  1600x85+0+815"
)

# ---- --selftest : identity MUST PASS, a perturbed copy MUST FAIL (teeth) --------
if [ "${1:-}" = "--selftest" ]; then
  echo "== fullscreen comparator self-test (the comparator must have teeth) =="
  rc=0; any=0
  tmp="${TMPDIR:-/tmp}/fscmp.$$"; mkdir -p "$tmp"
  shopt -s nullglob 2>/dev/null || true
  for g in "$GOLD"/*.png; do
    any=1
    base="$(basename "$g" .png)"
    # (1) identity: golden vs itself MUST PASS
    idiff "$g" "$g" "identity $base"; [ $? -eq 0 ] || { echo "  !! identity should PASS"; rc=1; }
    # (2) teeth: a deterministically perturbed copy (+0.1 to every channel) MUST FAIL
    pert="$tmp/${base}_perturbed.png"
    "$OIIO" "$g" --ch R,G,B --addc 0.1 -o "$pert" >/dev/null 2>&1
    idiff "$g" "$pert" "perturbed(+0.1) $base"
    if [ $? -ne 0 ]; then echo "  ok perturbed correctly FAILS"; else echo "  !! perturbed should FAIL"; rc=1; fi
  done
  rm -rf "$tmp"
  [ "$any" = 1 ] || { echo "NO GOLDENS staged in $GOLD"; exit 2; }
  [ "$rc" = 0 ] && echo "SELFTEST_PASS" || echo "SELFTEST_FAIL"
  exit $rc
fi

# ---- --regions <cand> <state> <WxH> : per-region breakdown ----------------------
if [ "${1:-}" = "--regions" ]; then
  CAND="${2:?usage: --regions <candidate.png> <state> <WxH>}"
  STATE="${3:?usage: --regions <candidate.png> <state> <WxH>}"
  SIZE="${4:?usage: --regions <candidate.png> <state> <WxH>}"
  GOLDEN="$GOLD/${STATE}_${SIZE}.png"
  [ -f "$GOLDEN" ] || { echo "FAIL no golden for ${STATE}_${SIZE}"; exit 2; }
  [ -f "$CAND" ]   || { echo "FAIL missing candidate $CAND"; exit 2; }
  echo "per-region ${STATE}_${SIZE}  (native-layout rects; fail=$THR failpercent=$FP)"
  for r in "${REGIONS[@]}"; do region_diff "$GOLDEN" "$CAND" $r; done
  idiff "$GOLDEN" "$CAND" "WHOLE ${STATE}_${SIZE}"
  exit $?
fi

# ---- --composite <cand> <state> <WxH> [out] : native|web|heatmap side-by-side ---
if [ "${1:-}" = "--composite" ]; then
  CAND="${2:?usage: --composite <candidate.png> <state> <WxH> [out.png]}"
  STATE="${3:?usage: --composite <candidate.png> <state> <WxH> [out.png]}"
  SIZE="${4:?usage: --composite <candidate.png> <state> <WxH> [out.png]}"
  OUT="${5:-$ART/sidebyside_${STATE}_${SIZE}.png}"
  GOLDEN="$GOLD/${STATE}_${SIZE}.png"
  [ -f "$GOLDEN" ] || { echo "FAIL no golden for ${STATE}_${SIZE}"; exit 2; }
  [ -f "$CAND" ]   || { echo "FAIL missing candidate $CAND"; exit 2; }
  tmp="${TMPDIR:-/tmp}/fscmp.$$"; mkdir -p "$tmp"
  # heatmap = 3x-amplified absolute difference, inferno colormap (channel 0).
  "$OIIO" "$GOLDEN" --ch R,G,B "$CAND" --ch R,G,B --absdiff --mulc 3 --colormap inferno -o "$tmp/heat.png" >/dev/null 2>&1
  # 3x1 mosaic with labels; padded so the panels read as separate frames.
  "$OIIO" \
    "$GOLDEN" --ch R,G,B --text:x=24:y=44:size=30:color=1,1,0 "NATIVE 5.2.0 (oracle)" \
    "$CAND"   --ch R,G,B --text:x=24:y=44:size=30:color=1,1,0 "WEB (wasm)" \
    "$tmp/heat.png"       --text:x=24:y=44:size=30:color=1,1,1 "DIFF x3 (inferno)" \
    --mosaic 3x1:pad=10 -o "$OUT" >/dev/null 2>&1
  rm -rf "$tmp"
  [ -s "$OUT" ] && echo "COMPOSITE -> ${OUT#$ROOT/}" || { echo "COMPOSITE_FAILED"; exit 2; }
  # also print the verdict so a composite run is self-documenting
  idiff "$GOLDEN" "$CAND" "${STATE}_${SIZE}"
  exit 0
fi

# ---- default: <candidate.png> <state> <WxH> => verdict -------------------------
CAND="${1:?usage: compare_fullscreen.sh <candidate.png> <state> <WxH>  |  --selftest  |  --regions ...  |  --composite ...}"
STATE="${2:?usage: compare_fullscreen.sh <candidate.png> <state> <WxH>}"
SIZE="${3:?usage: compare_fullscreen.sh <candidate.png> <state> <WxH>}"
GOLDEN="$GOLD/${STATE}_${SIZE}.png"
if [ ! -f "$GOLDEN" ]; then
  echo "FAIL no golden for ${STATE}_${SIZE} - available:"
  ls "$GOLD" 2>/dev/null | sed 's/^/    /'
  exit 2
fi
idiff "$GOLDEN" "$CAND" "${STATE}_${SIZE}"
exit $?
