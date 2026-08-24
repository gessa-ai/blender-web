#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
NODE="$ROOT/tools/emsdk/node/22.16.0_64bit/bin/node"
HOST_PYTHON="$ROOT/.host-tools/bin/python3.13"
BLENDER_JS="$ROOT/build-wasm-m1-parity/bin/blender.js"
BLENDER_WASM="$ROOT/build-wasm-m1-parity/bin/blender.wasm"
ORACLE="$ROOT/scripts/oracle-container.sh"

for required in "$NODE" "$HOST_PYTHON" "$BLENDER_JS" "$BLENDER_WASM" "$ORACLE"; do
  if [[ ! -x "$required" && ! -f "$required" ]]; then
    echo "M7_TYPE_ROUNDTRIP_FAIL missing required path: $required" >&2
    exit 2
  fi
done
if [[ "$($NODE --version)" != "v22.16.0" ]]; then
  echo "M7_TYPE_ROUNDTRIP_FAIL wrong Node runtime" >&2
  exit 2
fi

RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/bw-m7-type-roundtrip.XXXXXX")"
case "$RUN_ROOT" in
  "${TMPDIR:-/tmp}"/bw-m7-type-roundtrip.*) ;;
  *) echo "M7_TYPE_ROUNDTRIP_FAIL unsafe temporary path: $RUN_ROOT" >&2; exit 2 ;;
esac
SUCCESS=0
cleanup() {
  if [[ "$SUCCESS" == 1 ]]; then
    rm -rf -- "$RUN_ROOT"
  else
    echo "M7_TYPE_ROUNDTRIP_FAIL retained diagnostics: $RUN_ROOT" >&2
  fi
}
trap cleanup EXIT

cp "$SCRIPT_DIR/fixture.py" "$SCRIPT_DIR/verify.py" "$RUN_ROOT/"

diagnose_log() {
  local log="$1"
  rg -n 'Traceback|AssertionError|Error:|ERROR|Aborted|RuntimeError' "$log" | head -n 30 || true
}

run_native() {
  local label="$1"
  shift
  local log="$RUN_ROOT/$label.log"
  if ! (
    cd "$RUN_ROOT"
    BLENDER_ORACLE_WORK_ROOT="$RUN_ROOT" "$ORACLE" blender \
      --console-crash-handler --python-exit-code 1 --python "$RUN_ROOT/fixture.py" -- "$@"
  ) >"$log" 2>&1; then
    echo "M7_TYPE_ROUNDTRIP_FAIL native phase: $label" >&2
    diagnose_log "$log"
    return 1
  fi
}

run_wasm() {
  local label="$1"
  shift
  local log="$RUN_ROOT/$label.log"
  if ! (
    cd "$RUN_ROOT"
    BLENDER_SYSTEM_RESOURCES="$ROOT/upstream" \
    BLENDER_SYSTEM_PYTHON="$ROOT/lib/wasm" \
    BLENDER_SYSTEM_DATAFILES="$ROOT/upstream/release/datafiles" \
      "$NODE" "$BLENDER_JS" --background --factory-startup --console-crash-handler \
      --python-exit-code 1 --python "$RUN_ROOT/fixture.py" -- "$@"
  ) >"$log" 2>&1; then
    echo "M7_TYPE_ROUNDTRIP_FAIL Wasm phase: $label" >&2
    diagnose_log "$log"
    return 1
  fi
}

run_native native-author \
  --mode author --output "$RUN_ROOT/source.blend" \
  --pre-state "$RUN_ROOT/expected.json" --post-state "$RUN_ROOT/author-post.json"

run_native native-source-roundtrip \
  --mode roundtrip --source "$RUN_ROOT/source.blend" --output "$RUN_ROOT/native.blend" \
  --pre-state "$RUN_ROOT/native-pre.json" --post-state "$RUN_ROOT/native-post.json"

run_wasm wasm-source-roundtrip \
  --mode roundtrip --source "$RUN_ROOT/source.blend" --output "$RUN_ROOT/wasm.blend" \
  --pre-state "$RUN_ROOT/wasm-pre.json" --post-state "$RUN_ROOT/wasm-post.json"

# The omitted-type audit requires native- and Wasm-side load/save/reload state
# parity for one native-authored fixture. Stock-native readability of a Wasm32-
# authored file is a distinct, currently RED ABI boundary: patch 0014 fixes the
# Wasm TARGET layout only, while stock Blender interprets 32-bit file members with
# the legacy unpadded i386 layout. M7-WASM32-WRITE-CROSS-ABI owns that product fix;
# this focused receipt explicitly does not claim it.
run_wasm wasm-cross-roundtrip \
  --mode roundtrip --source "$RUN_ROOT/native.blend" --output "$RUN_ROOT/wasm-from-native.blend" \
  --pre-state "$RUN_ROOT/wasm-cross-pre.json" --post-state "$RUN_ROOT/wasm-cross-post.json"

"$HOST_PYTHON" "$RUN_ROOT/verify.py" \
  --expected "$RUN_ROOT/expected.json" \
  --state "$RUN_ROOT/author-post.json" \
  --state "$RUN_ROOT/native-pre.json" \
  --state "$RUN_ROOT/native-post.json" \
  --state "$RUN_ROOT/wasm-pre.json" \
  --state "$RUN_ROOT/wasm-post.json" \
  --state "$RUN_ROOT/wasm-cross-pre.json" \
  --state "$RUN_ROOT/wasm-cross-post.json" \
  --blend "$RUN_ROOT/source.blend" \
  --blend "$RUN_ROOT/native.blend" \
  --blend "$RUN_ROOT/wasm.blend" \
  --blend "$RUN_ROOT/wasm-from-native.blend" \
  --javascript "$BLENDER_JS" --wasm "$BLENDER_WASM" \
  --receipt "$RUN_ROOT/receipt.json"

SUCCESS=1
