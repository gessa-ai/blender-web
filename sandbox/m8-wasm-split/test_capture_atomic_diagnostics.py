#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exercise the exact CAPTURE-only Emscripten mailbox diagnostic rewrite."""

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FINALIZER = ROOT / "scripts/finalize-wasm-split.py"
SPEC = importlib.util.spec_from_file_location("finalize_wasm_split_atomic", FINALIZER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

ANCHOR = (
    "var __emscripten_thread_mailbox_await=pthread_ptr=>{if(!waitAsyncPolyfilled){/*"
    "BW_SPLIT_PTHREAD_MAILBOX_RANGE_SYNC_V1*/"
    "var heap32=bwSyncPthreadMemoryRange(pthread_ptr,pthread_ptr+116);"
    "var wait=Atomics.waitAsync(heap32,pthread_ptr>>2,pthread_ptr);"
    "wait.value.then(checkMailbox);var waitingAsync=pthread_ptr+112;"
    "Atomics.store(heap32,waitingAsync>>2,1)}};var checkMailbox="
)


def patched(source: str) -> tuple[str, dict[str, object]]:
    with tempfile.TemporaryDirectory(prefix="bw-capture-atomic-") as temp:
        path = Path(temp) / "generated.js"
        path.write_text(source, encoding="utf-8")
        receipt = MODULE.patch_capture_atomic_diagnostics(path)
        return path.read_text(encoding="utf-8"), receipt


def expect_fail(source: str, text: str) -> None:
    try:
        patched(source)
    except MODULE.WasmError as error:
        assert text in str(error), error
    else:
        raise AssertionError("invalid atomic diagnostic input passed")


def run_node(source: str, pointer: int, expected_op: str | None, sync_failure: bool = False) -> None:
    # 128 bytes makes pointer 4 fully valid, pointer 16 valid for wait but its
    # +112 waiting flag exactly out of range, and pointer 256 invalid for wait.
    script = f'''"use strict";
let messages=[];let checkCount=0;let waitAsyncPolyfilled=false;
let wasmMemory={{buffer:new SharedArrayBuffer(128),grow(){{}}}};
let HEAP8=new Int8Array(wasmMemory.buffer,0,64);let HEAPU8=new Uint8Array(wasmMemory.buffer,0,64);
let HEAP16=new Int16Array(wasmMemory.buffer,0,32);let HEAPU16=new Uint16Array(wasmMemory.buffer,0,32);
let HEAP32=new Int32Array(wasmMemory.buffer);
let HEAPU32=new Uint32Array(wasmMemory.buffer,0,16);let HEAPF32=new Float32Array(wasmMemory.buffer,0,16);
let HEAPF64=new Float64Array(wasmMemory.buffer,0,8);let HEAP64=new BigInt64Array(wasmMemory.buffer,0,8);
globalThis.__bwCaptureThreadParams={{pthreadPtr:{pointer},startRoutine:131571,arg:4242}};
globalThis.__bwCaptureThreadEntryStages=[{{stage:"after-tls",pthreadPtr:{pointer}}}];
if (({pointer} >> 2) < HEAP32.length) Atomics.store(HEAP32, {pointer} >> 2, {pointer});
function growMemViews(){{HEAP32=new Int32Array(wasmMemory.buffer)}}
function bwSyncPthreadMemoryRange(){{growMemViews();if(syncFailure)throw new RangeError('sync unavailable');return HEAP32}}
function postMessage(value){{messages.push(value)}}
function checkMailbox(){{checkCount++}}
let ENVIRONMENT_IS_PTHREAD=true;
let syncFailure={str(sync_failure).lower()};
{source}
let thrown=null;
try{{__emscripten_thread_mailbox_await({pointer})}}catch(error){{thrown=error}}
const result={{messages,thrown:thrown&&{{name:thrown.name,message:thrown.message}},
  checkCount,stored:Atomics.load(HEAP32,29)}};
process.stdout.write(JSON.stringify(result));
'''
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    row = json.loads(result.stdout)
    if expected_op is None:
        assert row["messages"] == [] and row["thrown"] is None and row["stored"] == 1, row
        return
    assert row["thrown"]["name"] == "RangeError", row
    assert len(row["messages"]) == 1 and row["messages"][0]["cmd"] == "bwCaptureAtomicError", row
    detail = row["messages"][0]["detail"]
    assert detail["marker"] == "BW_SPLIT_CAPTURE_ATOMIC_DIAG_V1", detail
    assert detail["op"] == expected_op and detail["pthreadPtr"] == pointer, detail
    assert detail["waitIndex"] == pointer >> 2 and detail["storeIndex"] == (pointer + 112) >> 2
    assert detail["heap32Length"] == 32 and detail["memoryBytes"] == 128
    assert detail["heap8Bytes"] == 64 and detail["heapU8Bytes"] == 64
    assert detail["heap16Bytes"] == 64 and detail["heapU16Bytes"] == 64
    assert detail["heap32Bytes"] == 128 and detail["heapU32Bytes"] == 64
    assert detail["heapF32Bytes"] == 64 and detail["heapF64Bytes"] == 64
    assert detail["heap64Bytes"] == 64 and detail["heapU64Bytes"] is None
    assert detail["heap8BufferBytes"] == 128 and detail["heap8BufferGrowable"] is False
    assert detail["heap8BufferMaxBytes"] == 128 and detail["heap8BufferIsMemory"] is True
    assert detail["heap8BufferShared"] is True and detail["memoryBufferShared"] is True
    assert detail["realm"] == "pthread" and detail["safeInteger"] and detail["aligned"]
    assert detail["waitInRange"] is (0 <= (pointer >> 2) < 32)
    assert detail["storeInRange"] is (0 <= ((pointer + 112) >> 2) < 32)
    assert detail["selfPtr"] is None and detail["workerId"] is None
    assert detail["messageParams"] == {
        "pthreadPtr": pointer, "startRoutine": 131571, "arg": 4242
    }
    assert detail["stages"] == [{"stage": "after-tls", "pthreadPtr": pointer}]


def main() -> None:
    output, receipt = patched("prefix;" + ANCHOR + "()=>{}")
    assert receipt == {
        "contract": "capture-mailbox-atomic-diagnostics-v1",
        "marker": "BW_SPLIT_CAPTURE_ATOMIC_DIAG_V1",
        "anchor_count_before": 1,
        "anchor_count_after": 0,
        "marker_count_after": 1,
        "wait_tag_count_after": 1,
        "store_tag_count_after": 1,
        "range_sync_tag_count_after": 1,
        "listener_count_after": 0,
    }
    function = output[output.index("var __emscripten_thread_mailbox_await="):
                      output.index(";var checkMailbox=")]
    run_node(function, 4, None)
    run_node(function, 4, "rangeSync", True)
    run_node(function, 16, "store")
    run_node(function, 256, "waitAsync")
    expect_fail("no mailbox", "expected one anchor, found 0")
    expect_fail(ANCHOR + ANCHOR, "expected one anchor, found 2")
    expect_fail(output, "already patched")
    print("capture atomic diagnostics: optional-view-safe + range/wait/store tagged, 3 structural negative PASS")


if __name__ == "__main__":
    main()
