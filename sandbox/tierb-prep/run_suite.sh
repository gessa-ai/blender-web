#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
#
# Run ONE tier-(b) candidate suite on the native oracle with the EXACT
# `add_blender_test` invocation profile from upstream/tests/CMakeLists.txt:56
# (--background --factory-startup are already added by oracle/bpy.sh).
#
# Usage:  run_suite.sh <ctest_name>          # name from suites.tsv
#         run_suite.sh <ctest_name> <script.py> [args...]   # ad-hoc
#
# Emits:  baseline-<ctest_name>.txt  (normalized stdout+stderr, committed)
#         _out/raw-<ctest_name>.log  (raw, NOT committed — scratch)
# Prints one TSV result line:  <name>\t<PASS|FAIL>\t<exit>\t<wall_s>\t<summary>
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
ORACLE="$REPO/oracle/bpy.sh"
PYDIR="$REPO/upstream/tests/python"
SRC="$REPO/upstream/tests/files"          # stub tree; path-exists use only
OUT="$HERE/_out"
mkdir -p "$OUT"

name="${1:?usage: run_suite.sh <ctest_name> [script args...]}"; shift || true

# Resolve script + args: explicit override, else look up suites.tsv.
if [ "$#" -ge 1 ]; then
  script="$1"; shift; args=("$@")
else
  line="$(grep -vE '^\s*#' "$HERE/suites.tsv" | awk -F'\t' -v n="$name" '$1==n{print;exit}')"
  [ -n "$line" ] || { echo "$name	FAIL	-	-	no-such-suite-in-manifest"; exit 3; }
  script="$(printf '%s' "$line" | awk -F'\t' '{print $2}')"
  rawargs="$(printf '%s' "$line" | awk -F'\t' '{print $3}')"
  # Expand @OUT@/@SRC@ placeholders, then word-split.
  rawargs="${rawargs//@OUT@/$OUT}"; rawargs="${rawargs//@SRC@/$SRC}"
  # shellcheck disable=SC2206
  args=($rawargs)
fi

raw="$OUT/raw-$name.log"
base="$HERE/baseline-$name.txt"

# Some suites (e.g. bl_pyapi_bmesh) write a `.blend` to CWD. Run from the
# gitignored scratch dir so such stray outputs never land in the repo root.
# All script/arg paths are absolute, so changing CWD is safe.
cd "$OUT" || exit 4

# The `--python-expr` thumbnail-disable mirrors TEST_BLENDER_EXE_PARAMS_NO_THUMB.
t0="$(perl -MTime::HiRes=time -e 'printf "%.3f", time')"
"$ORACLE" \
  --console-crash-handler \
  --debug-memory \
  --debug-exit-on-error \
  --python-exit-code 1 \
  --python-expr "import bpy;bpy.context.preferences.filepaths.file_preview_type='NONE'" \
  --python "$PYDIR/$script" \
  ${args[0]+-- "${args[@]}"} \
  >"$raw" 2>&1
rc=$?
t1="$(perl -MTime::HiRes=time -e 'printf "%.3f", time')"
wall="$(perl -e "printf '%.2f', $t1 - $t0")"

# Normalize for parity comparison.
sed -f "$HERE/normalize.sed" "$raw" > "$base"

# Verdict + human summary. unittest => trust its OK/FAILED line; else exit code.
if grep -qE '^(OK|FAILED)' "$raw"; then
  summary="$(grep -E '^(OK|FAILED)' "$raw" | tail -1)"
  ran="$(grep -E '^Ran [0-9]+ test' "$raw" | tail -1 | sed -E 's/ in .*//')"
  summary="${ran:+$ran; }$summary"
  case "$summary" in *OK*) verdict=PASS;; *) verdict=FAIL;; esac
  # A nonzero exit with an OK line still counts as a harness/env problem.
  [ "$rc" -eq 0 ] || verdict=FAIL
else
  [ "$rc" -eq 0 ] && verdict=PASS || verdict=FAIL
  summary="exit=$rc $(tail -1 "$raw" | cut -c1-70)"
fi

printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$verdict" "$rc" "$wall" "$summary"
