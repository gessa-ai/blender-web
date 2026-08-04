#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
#
# WASM half of the tier-(b) m2b gate: run ONE suite from suites.tsv on the
# wasm build (build-wasm/bin/blender.js under emsdk node), with the SAME
# add_blender_test profile as the oracle runner — only the binary + boot env
# differ (notes/m2-python-boot.md "Boot recipe (exact, VERIFIED)").
#
# Emits:  wasm-<name>.txt         (normalized wasm stdout+stderr, committed)
#         _out/wasm-raw-<name>.log (raw, gitignored)
# Prints: <name>\t<PASS|FAIL>\t<exit>\t<wall_s>\t<DIFF|SAME|DIFF!>\t<summary>
#   col5 = normalized-diff vs baseline-<name>.txt (secondary signal).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
NODE="$REPO/tools/emsdk/node/22.16.0_64bit/bin/node"
BLENDER_JS="$REPO/build-wasm/bin/blender.js"
PYDIR="$REPO/upstream/tests/python"
SRC="$REPO/upstream/tests/files"
OUT="$HERE/_out"
mkdir -p "$OUT"

name="${1:?usage: run_suite_wasm.sh <ctest_name>}"
expand() { local s="$1"; s="${s//@OUT@/$OUT}"; s="${s//@SRC@/$SRC}"; s="${s//@PY@/$PYDIR}"; printf '%s' "$s"; }

line="$(grep -vE '^\s*#' "$HERE/suites.tsv" | awk -F'\t' -v n="$name" '$1==n{print;exit}')"
[ -n "$line" ] || { echo "$name	FAIL	-	-	-	no-such-suite-in-manifest"; exit 3; }
script="$(printf '%s' "$line" | awk -F'\t' '{print $2}')"
rawargs="$(expand "$(printf '%s' "$line" | awk -F'\t' '{print $3}')")"
mode="$(printf '%s' "$line" | awk -F'\t' '{print $4}')"; mode="${mode:-normal}"
# shellcheck disable=SC2206
args=($rawargs)

if [ "$mode" = blend ]; then
  argn=("$(expand "$script")" "${args[@]}")
else
  argn=(--python "$PYDIR/$script")
  [ "${args[0]+set}" = set ] && argn+=(-- "${args[@]}")
fi
dbg=(--debug-exit-on-error); [ "$mode" = allow_error ] && dbg=()

raw="$OUT/wasm-raw-$name.log"
wout="$HERE/wasm-$name.txt"
cd "$OUT" || exit 4

t0="$(perl -MTime::HiRes=time -e 'printf "%.3f", time')"
BLENDER_SYSTEM_RESOURCES="$REPO/upstream" \
BLENDER_SYSTEM_PYTHON="$REPO/lib/wasm" \
BLENDER_SYSTEM_DATAFILES="$REPO/upstream/release/datafiles" \
"$NODE" "$BLENDER_JS" \
  --background --factory-startup \
  --console-crash-handler \
  --debug-memory \
  "${dbg[@]}" \
  --python-exit-code 1 \
  --python-expr "import bpy;bpy.context.preferences.filepaths.file_preview_type='NONE'" \
  "${argn[@]}" \
  >"$raw" 2>&1
rc=$?
t1="$(perl -MTime::HiRes=time -e 'printf "%.3f", time')"
wall="$(perl -e "printf '%.2f', $t1 - $t0")"

# Normalize: shared rules + wasm-specific KNOWN-benign startup noise (see
# wasm-normalize.sed header). These are CLASSIFIED, not hidden — they only affect
# the SECONDARY stdout diff, never the exit code (the PRIMARY gate signal).
sed -f "$HERE/normalize.sed" "$raw" | perl "$HERE/wasm-denoise.pl" | sed -f "$HERE/wasm-normalize.sed" > "$wout"

# Verdict (PRIMARY = exit code, mirroring the oracle runner's logic).
if grep -qE '^(OK|FAILED)' "$raw"; then
  summary="$(grep -E '^(OK|FAILED)' "$raw" | tail -1)"
  ran="$(grep -E '^Ran [0-9]+ test' "$raw" | tail -1 | sed -E 's/ in .*//')"
  summary="${ran:+$ran; }$summary"
  case "$summary" in *OK*) verdict=PASS;; *) verdict=FAIL;; esac
  [ "$rc" -eq 0 ] || verdict=FAIL
else
  [ "$rc" -eq 0 ] && verdict=PASS || verdict=FAIL
  summary="exit=$rc $(tail -1 "$raw" | cut -c1-60)"
fi

# SECONDARY: normalized-diff vs the oracle baseline.
base="$HERE/baseline-$name.txt"
if [ -f "$base" ]; then
  if diff -q <(perl "$HERE/wasm-denoise.pl" < "$base" | sed -f "$HERE/wasm-normalize.sed") "$wout" >/dev/null 2>&1; then
    diffmark=SAME
  else
    diffmark=DIFF
  fi
else
  diffmark=no-baseline
fi

printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$verdict" "$rc" "$wall" "$diffmark" "$summary"
