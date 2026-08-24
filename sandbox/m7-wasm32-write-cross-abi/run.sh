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
DNA_VERIFY="$ROOT/build-wasm-m1-parity/source/blender/makesdna/intern/dna_verify.cc"
ORACLE="$ROOT/scripts/oracle-container.sh"
BPY_ORACLE="$ROOT/oracle/bpy.sh"
SEMANTIC_FIXTURE="$ROOT/sandbox/m7-type-roundtrip/fixture.py"
SEMANTIC_VERIFIER="$ROOT/sandbox/m7-type-roundtrip/verify.py"
LEGACY_BHEAD4="$ROOT/upstream/tests/files/io_tests/blend_parsing/BHead4.blend"
GLOBAL_UNDO="$ROOT/upstream/tests/python/bl_global_undo.py"

for required in \
  "$NODE" "$HOST_PYTHON" "$BLENDER_JS" "$BLENDER_WASM" "$DNA_VERIFY" \
  "$ORACLE" "$BPY_ORACLE" "$SEMANTIC_FIXTURE" "$SEMANTIC_VERIFIER" \
  "$LEGACY_BHEAD4" "$GLOBAL_UNDO" "$SCRIPT_DIR/probe.py" "$SCRIPT_DIR/verify.py"; do
  if [[ ! -e "$required" ]]; then
    echo "M7_WASM32_WRITE_CROSS_ABI_FAIL missing required path: $required" >&2
    exit 2
  fi
done
if [[ "$($NODE --version)" != "v22.16.0" ]]; then
  echo "M7_WASM32_WRITE_CROSS_ABI_FAIL wrong Node runtime" >&2
  exit 2
fi

RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/bw-m7-wasm32-cross-abi.XXXXXX")"
case "$RUN_ROOT" in
  "${TMPDIR:-/tmp}"/bw-m7-wasm32-cross-abi.*) ;;
  *) echo "M7_WASM32_WRITE_CROSS_ABI_FAIL unsafe temporary path: $RUN_ROOT" >&2; exit 2 ;;
esac
SUCCESS=0
cleanup() {
  if [[ "$SUCCESS" == 1 ]]; then
    rm -rf -- "$RUN_ROOT"
  else
    echo "M7_WASM32_WRITE_CROSS_ABI_FAIL retained diagnostics: $RUN_ROOT" >&2
  fi
}
trap cleanup EXIT

cp "$SEMANTIC_FIXTURE" "$RUN_ROOT/semantic_fixture.py"
cp "$SCRIPT_DIR/probe.py" "$RUN_ROOT/probe.py"
cp "$LEGACY_BHEAD4" "$RUN_ROOT/BHead4.blend"

diagnose_log() {
  local log="$1"
  rg -n 'Traceback|AssertionError|Error:|ERROR|Aborted|RuntimeError|corrupt|invalid' "$log" \
    | head -n 30 || true
}

run_native() {
  local label="$1"
  local script="$2"
  shift 2
  local log="$RUN_ROOT/$label.log"
  if ! (
    cd "$RUN_ROOT"
    BLENDER_ORACLE_WORK_ROOT="$RUN_ROOT" "$ORACLE" with-env "$BPY_ORACLE" \
      --console-crash-handler --python-exit-code 1 --python "$script" -- "$@"
  ) >"$log" 2>&1; then
    echo "M7_WASM32_WRITE_CROSS_ABI_FAIL native phase: $label" >&2
    diagnose_log "$log"
    return 1
  fi
}

run_wasm() {
  local label="$1"
  local script="$2"
  shift 2
  local log="$RUN_ROOT/$label.log"
  if ! (
    cd "$RUN_ROOT"
    BLENDER_SYSTEM_RESOURCES="$ROOT/upstream" \
    BLENDER_SYSTEM_PYTHON="$ROOT/lib/wasm" \
    BLENDER_SYSTEM_DATAFILES="$ROOT/upstream/release/datafiles" \
      "$NODE" "$BLENDER_JS" --background --factory-startup --console-crash-handler \
      --python-exit-code 1 --python "$script" -- "$@"
  ) >"$log" 2>&1; then
    echo "M7_WASM32_WRITE_CROSS_ABI_FAIL Wasm phase: $label" >&2
    diagnose_log "$log"
    return 1
  fi
}

# A storage-bearing compositor and active/inactive editor fixture crosses both
# runtimes twice. This is the product-level regression for the original Scene
# root-collection corruption, not merely a binary parser test.
run_native semantic-author "$RUN_ROOT/semantic_fixture.py" \
  --mode author --output "$RUN_ROOT/source.blend" \
  --pre-state "$RUN_ROOT/expected.json" --post-state "$RUN_ROOT/native-author-post.json"

run_wasm semantic-wasm-save "$RUN_ROOT/semantic_fixture.py" \
  --mode roundtrip --source "$RUN_ROOT/source.blend" --output "$RUN_ROOT/wasm.blend" \
  --pre-state "$RUN_ROOT/wasm-pre.json" --post-state "$RUN_ROOT/wasm-post.json"

run_native semantic-native-cross "$RUN_ROOT/semantic_fixture.py" \
  --mode roundtrip --source "$RUN_ROOT/wasm.blend" \
  --output "$RUN_ROOT/native-from-wasm.blend" \
  --pre-state "$RUN_ROOT/native-cross-pre.json" \
  --post-state "$RUN_ROOT/native-cross-post.json"

run_wasm semantic-wasm-reload "$RUN_ROOT/semantic_fixture.py" \
  --mode roundtrip --source "$RUN_ROOT/native-from-wasm.blend" \
  --output "$RUN_ROOT/wasm-after-native.blend" \
  --pre-state "$RUN_ROOT/wasm-reload-pre.json" \
  --post-state "$RUN_ROOT/wasm-reload-post.json"

# Preserve Blender's pinned historical BHead4 corpus file, then save it
# uncompressed so the verifier can independently parse every header and SDNA
# length before stock-native Blender consumes that exact Wasm output.
run_native legacy-native-source "$RUN_ROOT/probe.py" \
  --mode snapshot --source "$RUN_ROOT/BHead4.blend" \
  --pre-state "$RUN_ROOT/legacy-native-source.json"

run_wasm legacy-wasm-roundtrip "$RUN_ROOT/probe.py" \
  --mode roundtrip --source "$RUN_ROOT/BHead4.blend" \
  --output "$RUN_ROOT/wasm-bhead4.blend" \
  --pre-state "$RUN_ROOT/legacy-wasm-pre.json" \
  --post-state "$RUN_ROOT/legacy-wasm-post.json"

run_native legacy-native-output "$RUN_ROOT/probe.py" \
  --mode snapshot --source "$RUN_ROOT/wasm-bhead4.blend" \
  --pre-state "$RUN_ROOT/legacy-native-output.json"

# Undo memfiles deliberately retain the compiled wasm32 layout. Exercise the
# upstream component after both canonical regular-file writes and runtime-layout
# pointer traversal have occurred in the same product.
run_wasm global-undo "$GLOBAL_UNDO" \
  --src-test-dir "$ROOT/upstream/tests/files/" \
  --output-dir "$RUN_ROOT/global-undo"

"$HOST_PYTHON" "$SCRIPT_DIR/verify.py" \
  --expected "$RUN_ROOT/expected.json" \
  --semantic-native-state "$RUN_ROOT/native-author-post.json" \
  --semantic-native-state "$RUN_ROOT/native-cross-pre.json" \
  --semantic-native-state "$RUN_ROOT/native-cross-post.json" \
  --semantic-wasm-state "$RUN_ROOT/wasm-pre.json" \
  --semantic-wasm-state "$RUN_ROOT/wasm-post.json" \
  --semantic-wasm-state "$RUN_ROOT/wasm-reload-pre.json" \
  --semantic-wasm-state "$RUN_ROOT/wasm-reload-post.json" \
  --legacy-native-state "$RUN_ROOT/legacy-native-source.json" \
  --legacy-native-state "$RUN_ROOT/legacy-native-output.json" \
  --legacy-wasm-state "$RUN_ROOT/legacy-wasm-pre.json" \
  --legacy-wasm-state "$RUN_ROOT/legacy-wasm-post.json" \
  --legacy-source "$RUN_ROOT/BHead4.blend" \
  --canonical-blend "$RUN_ROOT/wasm-bhead4.blend" \
  --dna-verify "$DNA_VERIFY" \
  --semantic-fixture "$SEMANTIC_FIXTURE" \
  --semantic-verifier "$SEMANTIC_VERIFIER" \
  --global-undo "$GLOBAL_UNDO" \
  --probe "$SCRIPT_DIR/probe.py" \
  --runner "$SCRIPT_DIR/run.sh" \
  --javascript "$BLENDER_JS" --wasm "$BLENDER_WASM" \
  --receipt "$RUN_ROOT/receipt.json"

SUCCESS=1
