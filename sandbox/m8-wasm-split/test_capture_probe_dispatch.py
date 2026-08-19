#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

import importlib.util
import subprocess
import tempfile
from pathlib import Path

FINALIZER = Path(__file__).resolve().parents[2] / "scripts/finalize-wasm-split.py"
SPEC = importlib.util.spec_from_file_location("finalize_wasm_split", FINALIZER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def expect_fail(source: str, count: int) -> None:
    with tempfile.TemporaryDirectory(prefix="bw-capture-probe-") as temp:
        path = Path(temp) / "generated.js"
        path.write_text(source, encoding="utf-8")
        try:
            MODULE.patch_capture_probe_dispatch(path)
        except MODULE.WasmError as error:
            if f"expected one anchor, found {count}" not in str(error):
                raise AssertionError(error) from error
        else:
            raise AssertionError("invalid anchor population passed")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="bw-capture-probe-") as temp:
        path = Path(temp) / "generated.js"
        path.write_text(
            "prefixwasmModule=msgData.wasmModule;createWasm();run();startWorker()}else if(cmd==2){establishStackSpace()}else if(cmd){err()",
            encoding="utf-8",
        )
        receipt = MODULE.patch_capture_probe_dispatch(path)
        output = path.read_text(encoding="utf-8")
        assert receipt["contract"] == "capture-worker-core-probe-ack-v1"
        assert receipt["anchor_count_before"] == 1
        assert receipt["anchor_count_after"] == 0
        assert receipt["marker_count_after"] == 1
        assert receipt["probe_branch_count_after"] == 1
        assert receipt["core_branch_count_after"] == 1
        assert receipt["postjs_probe_handler_count_after"] == 0
        assert receipt["postjs_outgoing_ack_count_after"] == 0
        assert receipt["main_ack_listener_count_after"] == 0
        assert output.count(MODULE.CAPTURE_PROBE_CORE_DISPATCH_MARKER) == 1
        assert 'cmd=="bwCaptureProbe"' in output and 'cmd:"bwCaptureProbeAck"' in output
        assert output.index('cmd=="bwCaptureProbe"') < output.index("cmd==2")
        dispatch = output[output.index("wasmModule="):]
        script = f'''let sent=[];let called=[];let wasmModule,initializedJS=false;
function postMessage(v){{sent.push(v)}} function createWasm(){{called.push("create")}}
function run(){{called.push("run")}} function startWorker(){{called.push("start")}}
function establishStackSpace(){{called.push("cmd2")}} function __emscripten_thread_init(){{}}
const PThread={{receiveOffscreenCanvases(){{}},threadInitTLS(){{}}}};
function __emscripten_thread_mailbox_await(){{}} function invokeEntryPoint(){{}}
function err(){{called.push("other")}}
function handle(msgData){{let cmd=msgData.cmd;if(cmd==1){{{dispatch}}}}}
handle({{cmd:"bwCaptureProbe",token:7,workerId:9}});
if(sent.length!==1||sent[0].cmd!=="bwCaptureProbeAck"||sent[0].token!==7||sent[0].workerId!==9||called.length!==0)process.exit(2);
handle({{cmd:2,pthread_ptr:1,start_routine:2,arg:3}});if(!called.includes("cmd2"))process.exit(3);
handle({{cmd:99}});if(!called.includes("other"))process.exit(4);
'''
        subprocess.run(["node", "-e", script], check=True)
        contract = Path(__file__).with_name("capture_probe_contract.mjs")
        minified_handler = ('\nif(message?.cmd==="bwCaptureProbe"){' \
            'postMessage({cmd:"bwCaptureProbeAck",token:message.token})}')
        minified_listener = '\nif(message?.cmd==="bwCaptureProbeAck"){resolve(message)}'
        integrated = output + minified_handler + minified_listener
        fixture = Path(temp) / "integrated.js"
        fixture.write_text(integrated, encoding="utf-8")
        subprocess.run(
            ["node", "--input-type=module", "-e",
             f'import {{validateCaptureProbeGeneratedSource as v}} from {str(contract)!r};'
             f'import {{readFileSync}} from "fs";v(readFileSync({str(fixture)!r},"utf8"));'],
            check=True,
        )
        readable = output + '\nif (message?.cmd === "bwCaptureProbe") {' \
            'postMessage({ cmd: "bwCaptureProbeAck", token: message.token }); }' \
            '\nif (message?.cmd === "bwCaptureProbeAck") { resolve(message); }'
        readable_fixture = Path(temp) / "readable.js"
        readable_fixture.write_text(readable, encoding="utf-8")
        command = (
            f'import {{validateCaptureProbeGeneratedSource as v}} from {str(contract)!r};'
            'import {readFileSync} from "fs";'
        )
        subprocess.run(["node", "--input-type=module", "-e",
                        command + f'v(readFileSync({str(readable_fixture)!r},"utf8"));'], check=True)
        for label, invalid in {
            "zero": output,
            # Keep the core and listener populations valid so this specifically
            # proves that a duplicated same-form post-js handler/ACK is rejected.
            "duplicate": output + minified_handler + minified_handler + minified_listener,
            # A readable seam may not coexist with its minified equivalent.
            "mixed": integrated + '\nif (message?.cmd === "bwCaptureProbe") {'
                     'postMessage({ cmd: "bwCaptureProbeAck" }); }',
        }.items():
            invalid_fixture = Path(temp) / f"invalid-{label}.js"
            invalid_fixture.write_text(invalid, encoding="utf-8")
            result = subprocess.run(
                ["node", "--input-type=module", "-e",
                 command + f'try{{v(readFileSync({str(invalid_fixture)!r},"utf8"));process.exit(2)}}catch{{}}'],
                check=False,
            )
            if result.returncode:
                raise AssertionError(f"shared validator negative {label} failed")
    expect_fail("no worker dispatcher", 0)
    anchor = "wasmModule=msgData.wasmModule;createWasm();run();startWorker()}else if(cmd==2){"
    expect_fail(anchor + anchor, 2)
    with tempfile.TemporaryDirectory(prefix="bw-capture-probe-") as temp:
        path = Path(temp) / "generated.js"
        path.write_text(anchor, encoding="utf-8")
        MODULE.patch_capture_probe_dispatch(path)
        try:
            MODULE.patch_capture_probe_dispatch(path)
        except MODULE.WasmError as error:
            assert "already patched" in str(error)
        else:
            raise AssertionError("prepatched input passed")
    print("capture probe core transformation: semantic core + readable/minified integration, 6 negative PASS")


if __name__ == "__main__":
    main()
