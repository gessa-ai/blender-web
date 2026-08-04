#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# M5 tier-(c) ORACLE-SIDE session goldens (event-simulate).
#
# For each M5 session (sessions/m5_core.py): launch the GUI oracle Blender TWICE
# in separate processes with --enable-event-simulate, capturing:
#   (a) operator trace  — stdout "operator | Started bpy.ops.X(...)" lines, TIMESTAMP
#       STRIPPED (the only non-deterministic field) -> traces/<session>.trace.txt
#   (b) post-session state dump (state_dump.build_dump) -> goldens/<session>.json
# Assert BOTH artifacts are byte-identical across the two runs (determinism), the
# same discipline as the corpus goldens. This is the oracle half of tier-(c); the
# wasm half compares wasm dumps+traces against these once M4/M5 land a GHOST-web
# window + WebGPU. No raw logs surfaced — only verdict + hashes.
#
# REQUIRES a real window server (macOS Cocoa/Metal here, or Linux headless weston
# via tests/utils/blender_headless.py). Fails loudly if a window cannot be created.
# Usage: bash sandbox/m5-prep/run_oracle_sessions.sh
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"

MP=sandbox/m5-prep
BIN="$ROOT/oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender"
RUNNER="$ROOT/$MP/m5_run_session.py"
GOLD="$ROOT/$MP/goldens"
TRACE="$ROOT/$MP/traces"
SCR="${TMPDIR:-/tmp}/m5oracle.$$"
mkdir -p "$GOLD" "$TRACE" "$SCR"

SESSIONS=(
  m5_core.object_select_all
  m5_core.object_click_select
  m5_core.object_transform_grxsz
  m5_core.edit_mode_toggle
  m5_core.mesh_extrude_region
  m5_core.mesh_bevel
  m5_core.undo_depth
)

[ -x "$BIN" ] || { echo "ORACLE_MISSING $BIN"; exit 2; }

# Deterministic operator trace: keep only "Started bpy.ops.X(...)" lines, drop the
# leading "HH:MM.mmm  operator | " prefix (timestamp is the sole non-det field).
sanitize_trace() {  # $1 = raw stdout file
  grep -aE 'operator[[:space:]]*\| Started bpy\.ops\.' "$1" \
    | sed -E 's/^.*\| Started //'
}

# $1=session $2=state-out $3=stdout-capture ; returns blender exit code
run_session() {
  timeout 180 "$BIN" -p 0 0 800 600 --factory-startup --no-window-frame --no-native-pixels \
    --enable-event-simulate --log "operator" --log-level "debug" \
    --python "$RUNNER" -- --session "$1" --state-out "$2" >"$3" 2>/dev/null
}

overall_ok=1
echo "== M5 oracle session goldens (2-run determinism) =="
for s in "${SESSIONS[@]}"; do
  o1="$SCR/$s.1.json"; o2="$SCR/$s.2.json"
  l1="$SCR/$s.1.out";  l2="$SCR/$s.2.out"
  t1="$SCR/$s.1.trace"; t2="$SCR/$s.2.trace"
  rm -f "$o1" "$o2"
  run_session "$s" "$o1" "$l1"
  run_session "$s" "$o2" "$l2"
  sanitize_trace "$l1" > "$t1"; sanitize_trace "$l2" > "$t2"

  # Session error / no dump?
  if [ ! -s "$o1" ] || [ ! -s "$o2" ]; then
    echo "FAIL $s  (no state dump produced)"; overall_ok=0; continue
  fi
  if grep -aq '"_m5_result": "error"' "$o1"; then
    echo "FAIL $s  (session reported error — see t.assert)"; overall_ok=0; continue
  fi

  sh1=$(shasum -a 256 "$o1" | cut -d' ' -f1); sh2=$(shasum -a 256 "$o2" | cut -d' ' -f1)
  th1=$(shasum -a 256 "$t1" | cut -d' ' -f1); th2=$(shasum -a 256 "$t2" | cut -d' ' -f1)
  nops=$(wc -l < "$t1" | tr -d ' ')

  if [ "$sh1" = "$sh2" ] && [ "$th1" = "$th2" ]; then
    cp "$o1" "$GOLD/$s.json"; cp "$t1" "$TRACE/$s.trace.txt"
    echo "PASS $s  state=$sh1  trace=$th1  ops=$nops"
  else
    overall_ok=0
    [ "$sh1" != "$sh2" ] && echo "NONDET-STATE $s  run1=$sh1 run2=$sh2"
    [ "$th1" != "$th2" ] && { echo "NONDET-TRACE $s"; diff "$t1" "$t2" | head -8; }
  fi
done

rm -rf "$SCR"
if [ "$overall_ok" -eq 1 ]; then echo "ALL_PASS"; else echo "SOME_FAIL"; exit 1; fi
