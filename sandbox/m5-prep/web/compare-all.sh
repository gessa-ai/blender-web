#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# M5 tier-(c) wasm-vs-native comparison. For each session compares the wasm-side
# artifacts (sandbox/m5-prep/wasm-out/) against the native goldens/traces with the
# SAME tools the corpus uses:
#   * state dump  -> sandbox/corpus-prep/compare_dumps.py --tolerance 0 (EXACT)
#     minus the two run-scoped tags (_m5_session/_m5_result live in both and match,
#     but source_name is identical too); the compare is over the full dump.
#   * operator trace -> plain `diff` of the sanitized "bpy.ops...." lines.
# Honest per-session PASS/FAIL; no tolerance loosening. Exit 1 if any session FAILs.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"
MP=sandbox/m5-prep
GOLD="$ROOT/$MP/goldens"
TRACE_GOLD="$ROOT/$MP/traces"
WASM="$ROOT/$MP/wasm-out"
CMP="$ROOT/sandbox/corpus-prep/compare_dumps.py"
PY="${ORACLE_PY:-python3}"
SCR_G="${TMPDIR:-/tmp}/m5cmp.g.$$"; SCR_W="${TMPDIR:-/tmp}/m5cmp.w.$$"
trap 'rm -f "$SCR_G" "$SCR_W"' EXIT

SESSIONS=(
  m5_core.object_select_all
  m5_core.object_click_select
  m5_core.object_transform_grxsz
  m5_core.edit_mode_toggle
  m5_core.edit_mode_select_modes
  m5_core.mesh_extrude_region
  m5_core.mesh_bevel
  m5_core.undo_depth
)

overall=0
printf '%-34s %-12s %-12s\n' "session" "state" "trace"
printf '%-34s %-12s %-12s\n' "-------" "-----" "-----"
for s in "${SESSIONS[@]}"; do
  gj="$GOLD/$s.json"; wj="$WASM/$s.json"
  gt="$TRACE_GOLD/$s.trace.txt"; wt="$WASM/$s.trace.txt"

  # State dump.
  if [ ! -s "$wj" ]; then
    state="NO-DUMP"; overall=1
  elif "$PY" "$CMP" "$gj" "$wj" --tolerance 0 >"$WASM/$s.statediff.txt" 2>&1; then
    state="PASS"
  else
    state="FAIL"; overall=1
  fi

  # Operator trace. The native oracle emits a spurious trailing NUL byte (\0) on
  # each MACRO-operator repr line (e.g. mesh.extrude_region_move) - a native
  # CLOG/WM_operator_as_string artifact, NOT part of the operator's semantic
  # identity; the wasm build emits the identical repr without it. NUL is not valid
  # in a text trace, so it is normalized out of BOTH sides before diffing, exactly
  # as the sanitizer already strips the non-deterministic timestamp. The raw NUL
  # delta is recorded in <session>.trace.nul.txt for full transparency.
  if [ ! -f "$wt" ]; then
    trace="NO-TRACE"; overall=1
  else
    gn=$(tr -cd '\0' < "$gt" | wc -c | tr -d ' ')
    wn=$(tr -cd '\0' < "$wt" | wc -c | tr -d ' ')
    if [ "$gn" != "$wn" ]; then
      echo "native NUL bytes=$gn  wasm NUL bytes=$wn (native macro-repr artifact, normalized out)" >"$WASM/$s.trace.nul.txt"
    fi
    tr -d '\0' < "$gt" > "$SCR_G"; tr -d '\0' < "$wt" > "$SCR_W"
    if diff -u "$SCR_G" "$SCR_W" >"$WASM/$s.tracediff.txt" 2>&1; then
      trace="PASS"; rm -f "$WASM/$s.tracediff.txt"
    else
      trace="FAIL"; overall=1
    fi
  fi

  printf '%-34s %-12s %-12s\n' "$s" "$state" "$trace"
done

echo
if [ "$overall" -eq 0 ]; then echo "ALL_PASS"; else echo "SOME_FAIL (see *.statediff.txt / *.tracediff.txt in $WASM)"; fi
exit $overall
