#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# M4-fullscreen-parity - capture the native FULL-WINDOW golden (ORACLE-SIDE).
#
# Extends sandbox/m4-golden-prep/capture_m4_golden.sh: same pinned native Blender
# 5.2.0, same windowed screenshot-operator method, same determinism receipt
# (capture TWICE in independent processes; byte-identical preferred, else the
# 0.016/1 tier-c threshold). Difference: one WORKSPACE state at 1600x900 (the
# whole Blender window - topbar, toolbar, viewport with shaded cube + grid +
# gizmos, sidebar panels, status bar). No splash (show_splash=False in the driver).
#
# The golden is named by its ACTUAL captured dimensions. This capture host
# (3024x1964 Retina) clamps window CONTENT HEIGHT to ~1001px; 1600x900 is within
# bounds and captures at the exact requested size. If a future host clamps below
# the requested height, the script WARNs and names the file by the real size so
# nothing is mislabeled (verified pattern from m4-golden-prep).
#
# BLENDER_USER_CONFIG is pointed at a throwaway empty dir (fresh factory profile),
# matching a fresh-OPFS wasm boot; irrelevant to the workspace state (no splash)
# but kept for parity with the m4-golden-prep method.
#
# Usage:
#   bash sandbox/m4-fullscreen-parity/capture_fullscreen_golden.sh            # workspace 1600x900
#   bash sandbox/m4-fullscreen-parity/capture_fullscreen_golden.sh <W> <H>    # workspace at WxH
#   bash sandbox/m4-fullscreen-parity/capture_fullscreen_golden.sh <state> <W> <H>
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"
MP=sandbox/m4-fullscreen-parity
BIN="${BLENDER_BIN:-$ROOT/oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender}"
OIIO="${OIIOTOOL:-oiiotool}"
PY="$ROOT/$MP/fullscreen_capture.py"
GOLD="$ROOT/$MP/goldens"
MANIFEST="$ROOT/$MP/manifest.tsv"
DELAY="${DELAY:-1.5}"
THR=0.016; FP=1
mkdir -p "$GOLD"

[ -x "$BIN" ] || { echo "ORACLE_MISSING $BIN"; exit 2; }
command -v "$OIIO" >/dev/null || { echo "OIIOTOOL_MISSING $OIIO"; exit 2; }

# actual "WxH" of a PNG
dims() { "$OIIO" --info "$1" 2>/dev/null | sed 's|.*png : ||' | awk '{gsub(/,/,""); print $1"x"$3}'; }

# emit the CC0 .license sidecar the repo requires for committed PNGs
# REUSE-IgnoreStart
license_sidecar() {
  local png="$1"
  cat > "${png}.license" <<'LIC'
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
LIC
}
# REUSE-IgnoreEnd

# one capture -> $1=state $2=W $3=H $4=outfile
capture() {
  local state="$1" W="$2" H="$3" out="$4" cfg
  cfg="$(mktemp -d)"; rm -f "$out"
  BLENDER_USER_CONFIG="$cfg" timeout 120 "$BIN" -p 0 0 "$W" "$H" \
    --factory-startup --no-native-pixels --no-window-frame \
    --python "$PY" -- --out "$out" --mode "$state" --delay "$DELAY" >/dev/null 2>&1
  rm -rf "$cfg"
}

# capture <state> at <W>x<H>, twice, verify determinism, stage golden + sidecar + manifest row
stage_one() {
  local state="$1" W="$2" H="$3"
  local tmp; tmp="${TMPDIR:-/tmp}/fscap.$$"; mkdir -p "$tmp"
  local a="$tmp/${state}_a.png" b="$tmp/${state}_b.png"
  capture "$state" "$W" "$H" "$a"
  capture "$state" "$W" "$H" "$b"
  if [ ! -s "$a" ] || [ ! -s "$b" ]; then echo "FAIL $state ${W}x${H} (no output)"; rm -rf "$tmp"; return 1; fi
  local da db; da="$(dims "$a")"; db="$(dims "$b")"
  if [ "$da" != "$db" ]; then echo "FAIL $state ${W}x${H} (dim jitter $da vs $db)"; rm -rf "$tmp"; return 1; fi
  [ "$da" = "${W}x${H}" ] || echo "WARN $state requested ${W}x${H} but host produced $da (display clamp) - staging as $da"
  local ha hb; ha="$(shasum -a256 < "$a" | cut -d' ' -f1)"; hb="$(shasum -a256 < "$b" | cut -d' ' -f1)"
  local det
  if [ "$ha" = "$hb" ]; then det="byte-identical sha=$ha"
  else
    "$OIIO" "$a" --ch R,G,B "$b" --ch R,G,B --fail "$THR" --failpercent "$FP" --diff >/dev/null 2>&1 \
      && det="threshold-identical(0.016/1) sha:$ha!=$hb" \
      || { echo "FAIL $state ${W}x${H} NON-DETERMINISTIC beyond 0.016/1 ($ha vs $hb)"; rm -rf "$tmp"; return 1; }
  fi
  local dst="$GOLD/${state}_${da}.png"
  cp "$a" "$dst"
  license_sidecar "$dst"
  local shaline; shaline="$(shasum -a256 < "$dst" | cut -d' ' -f1)"
  # write/refresh the manifest row (header lazily created)
  if [ ! -f "$MANIFEST" ]; then
    # REUSE-IgnoreStart
    {
      echo "# SPDX-FileCopyrightText: 2026 blender-web contributors"
      echo "# SPDX-License-Identifier: CC0-1.0"
      echo "# M4-fullscreen-parity - staged native full-window goldens."
      echo "# Comparator: compare_fullscreen.sh <candidate.png> <state> <actual_size>  (oiiotool --fail 0.016 --failpercent 1 --diff, exit-code-primary)"
      echo "# Native oracle: oracle/blender-5.2.0 (Blender 5.2.0 LTS, Cocoa+Metal) - same pin as the corpus/m4/m5/m6 goldens."
      echo "# determinism: two independent windowed runs; \"byte\" = byte-identical PNG (sha256 below), else threshold-identical(0.016/1)."
      printf 'state\trequested\tactual\tgolden\tfail_threshold\tfail_percent\tdeterminism\tsha256\n'
    } > "$MANIFEST"
    # REUSE-IgnoreEnd
  fi
  # drop any prior row for this state+actual, then append fresh
  grep -v -e "^${state}	${W}x${H}	" -e "	${dst#$ROOT/}	" "$MANIFEST" > "$MANIFEST.tmp" 2>/dev/null || cp "$MANIFEST" "$MANIFEST.tmp"
  mv "$MANIFEST.tmp" "$MANIFEST"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$state" "${W}x${H}" "$da" "${dst#$ROOT/}" "$THR" "$FP" "${det%% *}" "$shaline" >> "$MANIFEST"
  echo "STAGED $state ${da}  $det  -> $MP/goldens/${state}_${da}.png"
  rm -rf "$tmp"
}

case "$#" in
  0) stage_one workspace 1600 900 ;;
  2) stage_one workspace "$1" "$2" ;;
  3) stage_one "$1" "$2" "$3" ;;
  *) echo "usage: $0 [<state>] <W> <H>   (default: workspace 1600 900)"; exit 2 ;;
esac
