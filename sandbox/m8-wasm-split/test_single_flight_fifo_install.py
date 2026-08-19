# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Execute the production FIFO late-worker transform and fail-closed cases."""

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
FINALIZER = REPO / "scripts/finalize-wasm-split.py"
RUNTIME = REPO / "platform_web/split/single-flight.js"


def load_finalizer():
    spec = importlib.util.spec_from_file_location("bw_finalize_split", FINALIZER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RAW_CORE = r'''
var instantiateSync=function(){};
var loadSplitModule=instantiateSync;
var messageQueue=[];
var invokeCount=0;
var wasmMemory=null;
var wasmModule=null;
var wasmRawExports={};
var self={};
function createWasm(){wasmRawExports={}}
function run(){}
var handleMessage=function handleMessage(event){
  var msgData=event.data;
  var cmd=msgData.cmd;
  if(cmd==1){
    var startWorker=()=>{postMessage({cmd:3});for(let msg of messageQueue){handleMessage(msg)}self.onmessage=handleMessage};
    wasmMemory=msgData.wasmMemory;wasmModule=msgData.wasmModule;createWasm();run();startWorker()
  }else if(cmd==2){invokeCount++}
};
'''


def transform(module, root: Path, source: str) -> str:
    root.mkdir(parents=True, exist_ok=True)
    js = root / "fixture.js"
    secondary = root / "fixture.deferred.wasm"
    js.write_text(source + "\n" + RUNTIME.read_text(encoding="utf-8"), encoding="utf-8")
    secondary.write_bytes(b"deferred-fixture")
    receipt = module.patch_single_flight_runtime(js, secondary)
    assert receipt["late_worker_delivery"] == "fifo-initial-install-before-thread-entry"
    assert receipt["initial_install_post_count"] == 1
    assert receipt["initial_install_dispatch_count"] == 1
    assert receipt["cmd1_secondary_piggyback_absent"] is True
    output = js.read_text(encoding="utf-8")
    assert output.count("BW_SPLIT_WORKER_INITIAL_INSTALL_FIFO_V1") == 1
    assert (output.count('cmd:"bwSplitInitialInstall"')
            + output.count('cmd: "bwSplitInitialInstall"')) == 1
    assert "msgData.bwSplitSecondaryModule" not in output
    assert "bwSplitWorkerId:worker.__bwSplitId" not in output
    page = output.split("PThread.loadWasmModuleToWorker = function (worker) {", 1)[1]
    positions = [
        page.index("var loading = bwSplitOriginalLoadWorker(worker);"),
        page.index("bwSplitAttachWorker(worker);"),
        page.index('cmd: "bwSplitInitialInstall"'),
        page.index("return loading.then"),
    ]
    assert positions == sorted(positions) and len(set(positions)) == 4
    return output


def run_case(output: str, root: Path, label: str, payload: str, expect_ok: bool) -> None:
    script = root / f"{label}.js"
    script.write_text(
        "var Module={};var PThread={};var ENVIRONMENT_IS_PTHREAD=true;"
        "var locateFile=(x)=>x;var sent=[];var postMessage=(x)=>sent.push(x);\n"
        + output
        + "\nvar emptyModule=new WebAssembly.Module(new Uint8Array([0,97,115,109,1,0,0,0]));\n"
        + f"var initial={payload};\n"
        + "messageQueue=[{data:initial},{data:{cmd:2}}];var thrown=null;"
          "try{handleMessage({data:{cmd:1,wasmMemory:{},wasmModule:emptyModule}})}"
          "catch(error){thrown=String(error)}\n"
        + (
            "if(thrown!==null||invokeCount!==1||sent.length!==2||sent[0].cmd!==3||"
            "sent[1].cmd!==\"bwSplitReady\"||sent[1].ok!==true||"
            "sent[1].delivery!==\"initial-before-start\"||sent[1].instanceCount!==1)"
            "throw new Error(JSON.stringify({thrown,invokeCount,sent}));\n"
            if expect_ok
            else
            "if(thrown===null||invokeCount!==0||sent.length!==2||sent[0].cmd!==3||"
            "sent[1].cmd!==\"bwSplitReady\"||sent[1].ok!==false||"
            "sent[1].delivery!==\"initial-before-start\")"
            "throw new Error(JSON.stringify({thrown,invokeCount,sent}));\n"
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(["node", str(script)], text=True, capture_output=True)
    if completed.returncode:
        raise AssertionError(label + " failed\n" + completed.stdout + completed.stderr)


def main() -> None:
    module = load_finalizer()
    with tempfile.TemporaryDirectory(prefix="bw-fifo-install-") as temporary:
        root = Path(temporary)
        output = transform(module, root, RAW_CORE)
        valid = '{cmd:"bwSplitInitialInstall",module:emptyModule,generation:1,workerId:15}'
        run_case(output, root, "positive", valid, True)
        run_case(output, root, "missing_module",
                 '{cmd:"bwSplitInitialInstall",generation:1,workerId:15}', False)
        run_case(output, root, "wrong_generation",
                 '{cmd:"bwSplitInitialInstall",module:emptyModule,generation:0,workerId:15}', False)
        run_case(output, root, "wrong_worker",
                 '{cmd:"bwSplitInitialInstall",module:emptyModule,generation:1,workerId:0}', False)

        structural = {
            "missing": RAW_CORE.replace("}else if(cmd==2){", "}else if(cmd==7){"),
            "duplicate": RAW_CORE + RAW_CORE,
            "prepatched": RAW_CORE.replace(
                "}else if(cmd==2){",
                '}else if(cmd=="bwSplitInitialInstall"){/*'
                + module.SINGLE_FLIGHT_INITIAL_DISPATCH_MARKER
                + '*/}else if(cmd==2){',
            ),
        }
        for label, source in structural.items():
            try:
                transform(module, root / label, source)
            except module.WasmError:
                continue
            raise AssertionError(f"structural negative {label} unexpectedly passed")

    print("BW_SINGLE_FLIGHT_FIFO_INSTALL_TEST PASS positive=1 semantic-negative=3 structural=3")


if __name__ == "__main__":
    main()
