#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Execute the production pthread range-sync finalizer transform semantically."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile


REPO = Path(__file__).resolve().parents[2]
FINALIZER_PATH = REPO / "scripts/finalize-wasm-split.py"
SPEC = importlib.util.spec_from_file_location("finalize_wasm_split", FINALIZER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import finalizer: {FINALIZER_PATH}")
FINALIZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FINALIZER)

RAW_GROW = "function growMemViews(){if(wasmMemory.buffer!=HEAP8.buffer){updateMemoryViews()}}"
RAW_GUARD = "if(HEAP8?.buffer?.growable)return;"
RAW_ESTABLISH = (
    "function establishStackSpace(pthread_ptr){var stackHigh=(growMemViews(),HEAPU32)"
    "[pthread_ptr+48>>2];var stackSize=(growMemViews(),HEAPU32)[pthread_ptr+52>>2];"
    "var stackLow=stackHigh-stackSize;_emscripten_stack_set_limits(stackHigh,stackLow);"
    "stackRestore(stackHigh)}"
)
RAW_MAILBOX = (
    "var __emscripten_thread_mailbox_await=pthread_ptr=>{if(!waitAsyncPolyfilled){"
    "var wait=Atomics.waitAsync((growMemViews(),HEAP32),pthread_ptr>>2,pthread_ptr);"
    "wait.value.then(checkMailbox);var waitingAsync=pthread_ptr+112;"
    "Atomics.store((growMemViews(),HEAP32),waitingAsync>>2,1)}};var checkMailbox="
)
PATCHED_GROW = (
    "function growMemViews(){/*BW_SPLIT_SHARED_MEMORY_VIEW_REFRESH_V1*/"
    "var b=wasmMemory.buffer;if(b!=HEAP8.buffer||b.byteLength!=HEAP8.byteLength){"
    "updateMemoryViews()}}"
)
HELPER_TAIL = "if(ENVIRONMENT_IS_NODE&&ENVIRONMENT_IS_PTHREAD)"


def raw_fixture() -> str:
    return (
        "/*fixture-prefix*/"
        "function getMemoryBuffer(){return wasmMemory.buffer}"
        "function updateMemoryViews(){"
        + RAW_GUARD
        + "var b=getMemoryBuffer();HEAP8=new Int8Array(b);HEAPU8=new Uint8Array(b);"
        "HEAP32=new Int32Array(b);HEAPU32=new Uint32Array(b);refreshCount++}"
        + RAW_GROW
        + "if(ENVIRONMENT_IS_NODE&&ENVIRONMENT_IS_PTHREAD){}"
        + RAW_ESTABLISH
        + RAW_MAILBOX
        + "()=>{mailboxCheckCount++};/*fixture-suffix*/"
    )


def transform(source: str) -> tuple[str, dict[str, object], dict[str, object]]:
    with tempfile.TemporaryDirectory(prefix="bw-range-sync-") as directory:
        path = Path(directory) / "fixture.js"
        path.write_text(source, encoding="utf-8")
        refresh = FINALIZER.patch_shared_memory_view_refresh(path)
        range_sync = FINALIZER.patch_pthread_memory_range_sync(path)
        return path.read_text(encoding="utf-8"), refresh, range_sync


def range_transform_only(source: str) -> tuple[str, dict[str, object]]:
    with tempfile.TemporaryDirectory(prefix="bw-range-sync-negative-") as directory:
        path = Path(directory) / "fixture.js"
        path.write_text(source, encoding="utf-8")
        facts = FINALIZER.patch_pthread_memory_range_sync(path)
        return path.read_text(encoding="utf-8"), facts


def expect_failure(callback, label: str) -> None:
    try:
        callback()
    except FINALIZER.WasmError:
        return
    raise RuntimeError(f"{label} unexpectedly passed")


def run_node(transformed: str) -> dict[str, object]:
    script = f"""
const oldBuffer = new SharedArrayBuffer(64);
const grownBuffer = new SharedArrayBuffer(512);
const ENVIRONMENT_IS_NODE = false;
const ENVIRONMENT_IS_PTHREAD = false;
let exposeGrown = false;
let growZeroCount = 0;
let refreshCount = 0;
const wasmMemory = {{
  get buffer() {{ return exposeGrown ? grownBuffer : oldBuffer; }},
  grow(pages) {{
    if (pages !== 0) throw new Error('only grow(0) is permitted');
    growZeroCount++; exposeGrown = true; return 8;
  }},
}};
let HEAP8, HEAPU8, HEAP32, HEAPU32;
let stackLimits = null; let stackCurrent = 0; let stackRestoreCount = 0;
let waitAsyncCount = 0; let atomicStoreCount = 0;
let mailboxCheckCount = 0; let invokeCount = 0;
function _emscripten_stack_set_limits(high, low) {{ stackLimits = {{ high, low }}; }}
function stackRestore(high) {{ stackRestoreCount++; stackCurrent = high; }}
let waitAsyncPolyfilled = false;
const Atomics = {{
  waitAsync(heap, index, expected) {{
    waitAsyncCount++;
    if (heap !== HEAP32 || index !== 20 || expected !== 80) {{
      throw new Error('waitAsync payload mismatch');
    }}
    return {{ value: Promise.resolve('not-equal') }};
  }},
  store(heap, index, value) {{
    atomicStoreCount++;
    if (heap !== HEAP32 || index !== 48 || value !== 1) {{
      throw new Error('mailbox store payload mismatch');
    }}
    heap[index] = value; return value;
  }},
}};
{transformed}
function invokeEntryPoint() {{ invokeCount++; }}

updateMemoryViews();
const initialGrowMemViewsBytes = (growMemViews(), HEAPU8.byteLength);
const pthreadPtr = 80;
new Uint32Array(grownBuffer)[(pthreadPtr + 48) >> 2] = 240;
new Uint32Array(grownBuffer)[(pthreadPtr + 52) >> 2] = 64;
establishStackSpace(pthreadPtr);
__emscripten_thread_mailbox_await(pthreadPtr);
invokeEntryPoint();
await Promise.resolve();
const positive = {{
  initialGrowMemViewsBytes, grownBytes: HEAPU8.byteLength, growZeroCount, refreshCount,
  metadataEnd: pthreadPtr + 116, metadataCovered: pthreadPtr + 116 <= HEAPU8.byteLength,
  stackHigh: 240, stackSize: 64, stackLow: 176, stackLimits, stackCurrent,
  stackRestoreCount, waitAsyncCount, atomicStoreCount,
  mailboxIndex: 48, mailboxStore: HEAP32[48], mailboxCheckCount, invokeCount,
}};

function resetSideEffects() {{
  stackLimits = null; stackCurrent = 0; stackRestoreCount = 0;
  waitAsyncCount = 0; atomicStoreCount = 0; mailboxCheckCount = 0; invokeCount = 0;
}}
function resetGrownMemory() {{ exposeGrown = true; updateMemoryViews(); }}
function rejected(label, callback) {{
  resetSideEffects(); let error = null;
  try {{ callback(); invokeEntryPoint(); }} catch (caught) {{ error = String(caught); }}
  if (!error || stackRestoreCount !== 0 || waitAsyncCount !== 0 ||
      atomicStoreCount !== 0 || invokeCount !== 0) {{
    throw new Error(label + ' did not fail before side effects: ' + JSON.stringify({{
      error, stackRestoreCount, waitAsyncCount, atomicStoreCount, invokeCount,
    }}));
  }}
  return {{ label, error }};
}}

const negatives = [];
resetGrownMemory();
negatives.push(rejected('unsafe pointer', () => establishStackSpace(Number.MAX_SAFE_INTEGER + 1)));
negatives.push(rejected('unaligned pointer', () => establishStackSpace(81)));
negatives.push(rejected('overflow pointer', () => establishStackSpace(Number.MAX_SAFE_INTEGER - 64)));
negatives.push(rejected('mailbox unaligned pointer', () => __emscripten_thread_mailbox_await(81)));

const originalGrow = wasmMemory.grow;
exposeGrown = false; updateMemoryViews();
wasmMemory.grow = (pages) => {{
  if (pages !== 0) throw new Error('unexpected allocation');
  growZeroCount++; exposeGrown = false; return 1;
}};
negatives.push(rejected('grow0 remains short', () => establishStackSpace(pthreadPtr)));
wasmMemory.grow = originalGrow;

function metadataFailure(label, high, size) {{
  resetGrownMemory();
  HEAPU32[(pthreadPtr + 48) >> 2] = high;
  HEAPU32[(pthreadPtr + 52) >> 2] = size;
  negatives.push(rejected(label, () => establishStackSpace(pthreadPtr)));
}}
metadataFailure('zero high', 0, 64);
metadataFailure('zero size', 240, 0);
metadataFailure('size exceeds high', 64, 80);
metadataFailure('high outside memory', 528, 64);

console.log(JSON.stringify({{ positive, negatives }}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stdout + completed.stderr)
    return json.loads(completed.stdout)


def main() -> None:
    raw = raw_fixture()
    transformed, refresh, range_sync = transform(raw)
    result = run_node(transformed)
    expected_positive = {
        "initialGrowMemViewsBytes": 64,
        "grownBytes": 512,
        "growZeroCount": 1,
        "refreshCount": 2,
        "metadataEnd": 196,
        "metadataCovered": True,
        "stackHigh": 240,
        "stackSize": 64,
        "stackLow": 176,
        "stackLimits": {"high": 240, "low": 176},
        "stackCurrent": 240,
        "stackRestoreCount": 1,
        "waitAsyncCount": 1,
        "atomicStoreCount": 1,
        "mailboxIndex": 48,
        "mailboxStore": 1,
        "mailboxCheckCount": 1,
        "invokeCount": 1,
    }
    if result["positive"] != expected_positive:
        raise RuntimeError(f"positive production-transform mismatch: {result['positive']}")
    if len(result["negatives"]) != 9:
        raise RuntimeError(f"negative count mismatch: {result['negatives']}")

    refreshed_source, _refresh, _range = transform(raw)
    expect_failure(lambda: range_transform_only(refreshed_source), "prepatched")

    with tempfile.TemporaryDirectory(prefix="bw-range-structural-") as directory:
        base_path = Path(directory) / "base.js"
        base_path.write_text(raw, encoding="utf-8")
        FINALIZER.patch_shared_memory_view_refresh(base_path)
        refreshed = base_path.read_text(encoding="utf-8")
    expect_failure(
        lambda: range_transform_only(refreshed.replace(RAW_ESTABLISH, "")),
        "missing establish",
    )
    expect_failure(
        lambda: range_transform_only(refreshed.replace(PATCHED_GROW + HELPER_TAIL, HELPER_TAIL)),
        "missing helper anchor",
    )
    expect_failure(
        lambda: range_transform_only(refreshed.replace(RAW_MAILBOX, "")),
        "missing mailbox",
    )
    expect_failure(
        lambda: range_transform_only(refreshed + RAW_ESTABLISH),
        "duplicate establish",
    )
    expect_failure(
        lambda: range_transform_only(refreshed + PATCHED_GROW + HELPER_TAIL),
        "duplicate helper anchor",
    )
    expect_failure(
        lambda: range_transform_only(refreshed + RAW_MAILBOX),
        "duplicate mailbox",
    )

    if refresh["contract"] != "shared-memory-fixed-view-refresh-v2":
        raise RuntimeError(f"unexpected refresh receipt: {refresh}")
    if range_sync != {
        "contract": "pthread-cross-realm-memory-range-sync-v1",
        "helper_marker": "BW_SPLIT_PTHREAD_MEMORY_RANGE_SYNC_V1",
        "stack_marker": "BW_SPLIT_PTHREAD_STACK_RANGE_SYNC_V1",
        "mailbox_marker": "BW_SPLIT_PTHREAD_MAILBOX_RANGE_SYNC_V1",
        "helper_anchor_count_before": 1,
        "helper_anchor_count_after": 0,
        "helper_marker_count_after": 1,
        "stack_anchor_count_before": 1,
        "stack_anchor_count_after": 0,
        "stack_marker_count_after": 1,
        "mailbox_anchor_count_before": 1,
        "mailbox_anchor_count_after": 0,
        "mailbox_marker_count_after": 1,
        "grow_zero_count_after": 1,
        "bounded_attempt_count": 3,
        "metadata_end_offset": 116,
        "stack_high_offset": 48,
        "stack_size_offset": 52,
    }:
        raise RuntimeError(f"unexpected production range-sync receipt: {range_sync}")

    print(
        "BW_PTHREAD_MEMORY_RANGE_SYNC_TEST PASS "
        f"positive=1 negatives={len(result['negatives'])} structural=7 "
        f"contract={range_sync['contract']}"
    )


if __name__ == "__main__":
    main()
