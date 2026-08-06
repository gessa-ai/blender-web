#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# M4-golden-prep — capture the native M4 first-pixels goldens (ORACLE-SIDE).
#
# Runs the pinned native Blender WINDOWED (a real window opens briefly per run —
# macOS has no headless GUI backend) and captures, via Blender's own screenshot
# operator, the two M4 gate states at a requested size:
#   splash     : startup Quick Setup splash over the default cube
#   workspace  : post-splash default Layout (cube/camera/light, Blender Dark)
#
# Determinism receipt: each state is captured TWICE in independent processes and
# the two PNGs must be byte-identical (preferred) or oiiotool threshold-identical
# (0.016/1, the M4/tier-c bar) before the golden is staged into goldens/.
#
# The golden is named by its ACTUAL captured dimensions. On a Retina/HiDPI host
# the OS clamps window height to the usable screen area, so a requested height may
# come back smaller (e.g. 1800x1169 -> 1800x1001 on the capture host); the script
# WARNS and names the file by the real size so nothing is mislabeled.
#
# BLENDER_USER_CONFIG is pointed at a throwaway empty dir so the splash shows its
# FRESH "Quick Setup / Continue" variant (no "Import previous version prefs"
# button), matching a fresh-OPFS wasm boot — see m4_capture.py and notes.
#
# Usage:
#   bash sandbox/m4-golden-prep/capture_m4_golden.sh <splash|workspace> <W> <H>
#   bash sandbox/m4-golden-prep/capture_m4_golden.sh all          # 1280x720 + 1800x1169, both states
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"
MP=sandbox/m4-golden-prep
BIN="${BLENDER_BIN:-$ROOT/oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender}"
OIIO="${OIIOTOOL:-oiiotool}"
PY="$ROOT/$MP/m4_capture.py"
GOLD="$ROOT/$MP/goldens"
DELAY="${DELAY:-1.0}"
THR=0.016; FP=1
mkdir -p "$GOLD"

[ -x "$BIN" ] || { echo "ORACLE_MISSING $BIN"; exit 2; }
command -v "$OIIO" >/dev/null || { echo "OIIOTOOL_MISSING $OIIO"; exit 2; }

# actual "WxH" of a PNG
dims() { "$OIIO" --info "$1" 2>/dev/null | sed 's|.*png : ||' | awk '{gsub(/,/,""); print $1"x"$3}'; }

# one capture -> $1=state $2=W $3=H $4=outfile
capture() {
  local state="$1" W="$2" H="$3" out="$4" cfg
  cfg="$(mktemp -d)"; rm -f "$out"
  BLENDER_USER_CONFIG="$cfg" timeout 120 "$BIN" -p 0 0 "$W" "$H" \
    --factory-startup --no-native-pixels --no-window-frame \
    --python "$PY" -- --out "$out" --mode "$state" --delay "$DELAY" >/dev/null 2>&1
  rm -rf "$cfg"
}

# capture <state> at <W>x<H>, twice, verify determinism, stage golden
stage_one() {
  local state="$1" W="$2" H="$3"
  local tmp; tmp="${TMPDIR:-/tmp}/m4cap.$$"; mkdir -p "$tmp"
  local a="$tmp/${state}_a.png" b="$tmp/${state}_b.png"
  capture "$state" "$W" "$H" "$a"
  capture "$state" "$W" "$H" "$b"
  if [ ! -s "$a" ] || [ ! -s "$b" ]; then echo "FAIL $state ${W}x${H} (no output)"; rm -rf "$tmp"; return 1; fi
  local da db; da="$(dims "$a")"; db="$(dims "$b")"
  if [ "$da" != "$db" ]; then echo "FAIL $state ${W}x${H} (dim jitter $da vs $db)"; rm -rf "$tmp"; return 1; fi
  [ "$da" = "${W}x${H}" ] || echo "WARN $state requested ${W}x${H} but host produced $da (display clamp) — staging as $da"
  local ha hb; ha="$(shasum -a256 < "$a" | cut -d' ' -f1)"; hb="$(shasum -a256 < "$b" | cut -d' ' -f1)"
  local det
  if [ "$ha" = "$hb" ]; then det="byte-identical sha=$ha"
  else
    "$OIIO" "$a" --ch R,G,B "$b" --ch R,G,B --fail "$THR" --failpercent "$FP" --diff >/dev/null 2>&1 \
      && det="threshold-identical(0.016/1) sha:$ha!=$hb" \
      || { echo "FAIL $state ${W}x${H} NON-DETERMINISTIC beyond 0.016/1"; rm -rf "$tmp"; return 1; }
  fi
  local dst="$GOLD/${state}_${da}.png"
  cp "$a" "$dst"
  echo "STAGED $state ${da}  $det  -> $MP/goldens/${state}_${da}.png"
  rm -rf "$tmp"
}

do_size() { stage_one splash "$1" "$2"; stage_one workspace "$1" "$2"; }

case "${1:-all}" in
  all) do_size 1280 720; do_size 1800 1169 ;;
  splash|workspace) stage_one "$1" "${2:?need W}" "${3:?need H}" ;;
  *) echo "usage: $0 <splash|workspace> <W> <H>   |   $0 all"; exit 2 ;;
esac
