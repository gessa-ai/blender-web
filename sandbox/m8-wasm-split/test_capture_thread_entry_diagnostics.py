#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Semantic and fail-closed tests for CAPTURE pthread entry telemetry."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile


REPO = Path(__file__).resolve().parents[2]
FINALIZER = REPO / "scripts/finalize-wasm-split.py"
SPEC = importlib.util.spec_from_file_location("bw_split_finalizer", FINALIZER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

ANCHOR = (
    "var invokeEntryPoint=(ptr,arg)=>{runtimeKeepaliveCounter=0;noExitRuntime=0;"
    "var result=getWasmTableEntry(ptr)(arg);function finish(result){"
)
STAGE_ANCHOR = (
    "}else if(cmd==2){establishStackSpace(msgData.pthread_ptr);"
    "__emscripten_thread_init(msgData.pthread_ptr,0,0,1,0,0);"
    "PThread.receiveOffscreenCanvases(msgData);PThread.threadInitTLS();"
    "__emscripten_thread_mailbox_await(msgData.pthread_ptr);if(!initializedJS){"
    "initializedJS=true}try{invokeEntryPoint(msgData.start_routine,msgData.arg)}"
)
MAIN_ANCHOR = (
    'case 9:Module[d.handler](...d.args);break;default:if(cmd)err('
    '`worker sent an unknown command ${cmd}`)}};worker.onerror='
)
TAIL = (
    "if(keepRuntimeAlive()){EXITSTATUS=result;return}__emscripten_thread_exit(result)};"
    "finish(result)};"
)
LISTENER = 'if (message?.cmd === "bwCaptureThreadEntryError") {}\n'


def transform(source: str) -> tuple[str, dict[str, object]]:
    with tempfile.TemporaryDirectory(prefix="bw-entry-diag-test-") as temp:
        path = Path(temp) / "fixture.js"
        path.write_text(source, encoding="utf-8")
        receipt = MODULE.patch_capture_thread_entry_diagnostics(path)
        return path.read_text(encoding="utf-8"), receipt


def expect_fail(source: str) -> None:
    try:
        transform(source)
    except MODULE.WasmError:
        return
    raise AssertionError("invalid thread-entry diagnostic fixture unexpectedly passed")


DISPATCH = "function dispatch(cmd,msgData){if(cmd==1){" + STAGE_ANCHOR + "catch(ex){throw ex}}}\n"
MAIN_DISPATCH = (
    "function install(worker){worker.onmessage=e=>{var d=e.data;var cmd=d.cmd;switch(cmd){" +
    MAIN_ANCHOR + "()=>{}}\n"
)
fixture = LISTENER + ANCHOR + TAIL + DISPATCH + MAIN_DISPATCH
output, receipt = transform(fixture)
assert receipt == {
    "contract": "capture-pthread-entry-stack-diagnostics-v1",
    "marker": "BW_SPLIT_CAPTURE_THREAD_ENTRY_DIAG_V1",
    "entry_anchor_count_before": 1,
    "entry_anchor_count_after": 0,
    "marker_count_after": 1,
    "stage_marker": "BW_SPLIT_CAPTURE_THREAD_ENTRY_STAGE_V1",
    "stage_anchor_count_before": 1,
    "stage_anchor_count_after": 0,
    "stage_marker_count_after": 1,
    "stage_count_after": 5,
    "main_dispatch_marker": "BW_SPLIT_CAPTURE_MAIN_DIAGNOSTIC_DISPATCH_V1",
    "main_dispatch_anchor_count_before": 1,
    "main_dispatch_anchor_count_after": 0,
    "main_dispatch_marker_count_after": 1,
    "main_atomic_case_count_after": 1,
    "main_entry_case_count_after": 1,
    "post_count_after": 1,
    "listener_count_after": 1,
    "stack_high_offset": 48,
    "stack_size_offset": 52,
}
assert output.count("BW_SPLIT_CAPTURE_THREAD_ENTRY_DIAG_V1") == 1
assert output.count('cmd:"bwCaptureThreadEntryError"') == 1

expect_fail(LISTENER + "var invokeEntryPoint=()=>{};" + DISPATCH)
expect_fail(LISTENER + ANCHOR + TAIL + ANCHOR + TAIL + DISPATCH)
expect_fail(LISTENER + fixture.replace(ANCHOR, ANCHOR.replace(
    "runtimeKeepaliveCounter=0", "/*BW_SPLIT_CAPTURE_THREAD_ENTRY_DIAG_V1*/runtimeKeepaliveCounter=0"
)))
expect_fail(ANCHOR + TAIL + DISPATCH)
expect_fail(LISTENER + ANCHOR + TAIL + DISPATCH.replace(STAGE_ANCHOR, "}else if(cmd==2){}"))
expect_fail(LISTENER + ANCHOR + TAIL + DISPATCH)
expect_fail(LISTENER + ANCHOR + TAIL + DISPATCH + MAIN_DISPATCH + MAIN_DISPATCH)

runtime = """
var ENVIRONMENT_IS_PTHREAD=true;
var message=null;
globalThis.__bwCaptureWorkerId=12;
var runtimeKeepaliveCounter=1,noExitRuntime=1,EXITSTATUS=0;
var memoryBuffer=new SharedArrayBuffer(1024);
var wasmMemory={buffer:memoryBuffer};
var HEAP8=new Int8Array(memoryBuffer),HEAPU8=new Uint8Array(memoryBuffer),HEAP32=new Int32Array(memoryBuffer);
var HEAPU32=new Uint32Array(memoryBuffer);
HEAPU32[(128+48)>>2]=900;
HEAPU32[(128+52)>>2]=256;
HEAPU32[(192+48)>>2]=800;
HEAPU32[(192+52)>>2]=128;
var posted=[];
var currentStack=700;
var pthreadSelfValue=128;
var establishOverride=null;
var tableLookupCount=0;
var mainLogs=[];
var Module={};
function err(value){mainLogs.push(value)}
function _pthread_self(){return pthreadSelfValue}
function growMemViews(){}
function bwSyncPthreadMemoryRange(){}
function stackSave(){return currentStack}
function establishStackSpace(ptr){
  var inRange=Number.isSafeInteger(ptr)&&ptr>=0&&(ptr&3)==0&&ptr+56<=HEAPU8.byteLength;
  currentStack=establishOverride===null?(inRange?HEAPU32[(ptr+48)>>2]:700):establishOverride;
}
function __emscripten_thread_init(){}
var PThread={receiveOffscreenCanvases(){},threadInitTLS(){}};
function __emscripten_thread_mailbox_await(){}
var initializedJS=false;
function getWasmTableEntry(ptr){
  tableLookupCount++;
  var entry=function(arg){throw new WebAssembly.RuntimeError('memory access out of bounds')};
  Object.defineProperty(entry,'name',{value:'131003'});
  return entry;
}
function postMessage(value){posted.push(value)}
function keepRuntimeAlive(){return false}
function __emscripten_thread_exit(){}
""" + output + """
function runCase(name,messagePtr,selfPtr,stackOverride){
  posted=[];
  currentStack=700;
  pthreadSelfValue=selfPtr;
  establishOverride=stackOverride;
  tableLookupCount=0;
  globalThis.__bwCaptureThreadParams=null;
  globalThis.__bwCaptureThreadEntryStages=[];
  var caught=null;
  try{dispatch(2,{pthread_ptr:messagePtr,start_routine:131571,arg:4242})}
  catch(error){caught=String(error.message)}
  return {name,caught,posted,tableLookupCount};
}
var cases=[
  runCase('normal',128,128,null),
  runCase('bad-message-metadata',2048,128,700),
  runCase('self-message-mismatch',128,192,null),
  runCase('stack-current-out-of-range',128,128,2048)
];
var mainWorker={__bwCaptureId:77};
install(mainWorker);
mainWorker.onmessage({data:cases[0].posted[0]});
mainWorker.onmessage({data:{cmd:'bwCaptureAtomicError',detail:{marker:'atomic-test',op:'waitAsync'}}});
console.log(JSON.stringify({cases,mainLogs,
  mainEntry:globalThis.__bwCaptureThreadEntryDiagnostics,
  mainAtomic:globalThis.__bwCaptureAtomicDiagnostics}));
"""
completed = subprocess.run(
    ["node", "-e", runtime], check=False, capture_output=True, text=True
)
assert completed.returncode == 0, completed.stderr
facts = json.loads(completed.stdout)
assert [case["name"] for case in facts["cases"]] == [
    "normal", "bad-message-metadata", "self-message-mismatch", "stack-current-out-of-range"
]
for case in facts["cases"]:
    assert case["caught"] == "memory access out of bounds"
    assert len(case["posted"]) == 1
    assert case["posted"][0]["cmd"] == "bwCaptureThreadEntryError"
    assert case["tableLookupCount"] == 1

detail = facts["cases"][0]["posted"][0]["detail"]
assert detail["marker"] == "BW_SPLIT_CAPTURE_THREAD_ENTRY_DIAG_V1"
assert detail["startRoutine"] == 131571 and detail["arg"] == 4242
assert detail["pthreadPtr"] == 128 and detail["workerId"] == 12
assert detail["stackCurrent"] == 900 and detail["stackHigh"] == 900
assert detail["stackSize"] == 256 and detail["stackLow"] == 644
assert detail["stackCurrentInMemory"] is True and detail["stackHighInMemory"] is True
assert detail["memoryBytes"] == 1024 and detail["heap32Length"] == 256
assert detail["tableEntryName"] == "131003"
assert detail["messagePthreadMatchesSelf"] is True
assert detail["messageRoutineMatchesInvoke"] is True
assert detail["messageArgMatchesInvoke"] is True
assert detail["stackCurrentMatchesMessageHigh"] is True
assert detail["stackCurrentMatchesSelfHigh"] is True
assert detail["messageStackHighInMemory"] is True
assert detail["messageParams"] == {
    "pthreadPtr": 128,
    "startRoutine": 131571,
    "arg": 4242,
    "pointerSafe": True,
    "pointerAligned": True,
    "metadataInRange": True,
    "stackHigh": 900,
    "stackSize": 256,
    "stackLow": 644,
    "memoryBytes": 1024,
    "heap8Bytes": 1024,
    "heap32Length": 256,
}
assert [row["stage"] for row in detail["stages"]] == [
    "before-establish", "after-establish", "after-thread-init", "after-tls", "before-entry"
]
assert detail["stages"][0]["stackCurrent"] == 700
assert all(row["stackCurrent"] == 900 for row in detail["stages"][1:])

bad = facts["cases"][1]["posted"][0]["detail"]
assert bad["messageParams"]["pthreadPtr"] == 2048
assert bad["messageParams"]["pointerSafe"] is True
assert bad["messageParams"]["pointerAligned"] is True
assert bad["messageParams"]["metadataInRange"] is False
assert bad["messageParams"]["stackHigh"] is None
assert bad["messageParams"]["stackSize"] is None
assert bad["messageParams"]["stackLow"] is None
assert bad["messagePthreadMatchesSelf"] is False
assert bad["messageStackHighInMemory"] is False
assert all(row["metadataInRange"] is False for row in bad["stages"])
assert all(row["stackHigh"] is None and row["stackSize"] is None and row["stackLow"] is None
           for row in bad["stages"])

mismatch = facts["cases"][2]["posted"][0]["detail"]
assert mismatch["messageParams"]["pthreadPtr"] == 128
assert mismatch["pthreadPtr"] == 192
assert mismatch["messagePthreadMatchesSelf"] is False
assert mismatch["stackCurrent"] == 900
assert mismatch["stackHigh"] == 800
assert mismatch["stackCurrentMatchesMessageHigh"] is True
assert mismatch["stackCurrentMatchesSelfHigh"] is False
assert mismatch["selfMetadataInRange"] is True

out_of_range = facts["cases"][3]["posted"][0]["detail"]
assert out_of_range["stackCurrent"] == 2048
assert out_of_range["stackHigh"] == 900
assert out_of_range["stackCurrentInMemory"] is False
assert out_of_range["stackHighInMemory"] is True
assert out_of_range["messageStackHighInMemory"] is True
assert out_of_range["stackCurrentMatchesMessageHigh"] is False
assert out_of_range["stackCurrentMatchesSelfHigh"] is False

assert len(facts["mainEntry"]) == 1
assert facts["mainEntry"][0]["captureWorkerId"] == 77
assert facts["mainEntry"][0]["tableEntryName"] == "131003"
assert facts["mainAtomic"] == [{
    "marker": "atomic-test", "op": "waitAsync", "captureWorkerId": 77
}]
assert len(facts["mainLogs"]) == 2
assert facts["mainLogs"][0].startswith("BW_SPLIT_CAPTURE_THREAD_ENTRY ")
assert facts["mainLogs"][1].startswith("BW_SPLIT_CAPTURE_ATOMIC ")

print("capture pthread entry diagnostics: 4 semantic + five-stage + core dispatch + 7 structural negative PASS")
