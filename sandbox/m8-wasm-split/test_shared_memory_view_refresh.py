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

ANCHOR = "function growMemViews(){if(wasmMemory.buffer!=HEAP8.buffer){updateMemoryViews()}}"
GUARD_ANCHOR = "if(HEAP8?.buffer?.growable)return;"
FIXTURE = (
    "function getMemoryBuffer(){return wasmMemory.buffer}"
    "function updateMemoryViews(){" + GUARD_ANCHOR +
    "updates++;const b=getMemoryBuffer();HEAP8=new Int8Array(b);HEAP32=new Int32Array(b)}" +
    ANCHOR
)


def transform(source: str) -> tuple[str, dict[str, object]]:
    with tempfile.TemporaryDirectory(prefix="bw-view-refresh-") as temp:
        path = Path(temp) / "generated.js"
        path.write_text(source, encoding="utf-8")
        receipt = MODULE.patch_shared_memory_view_refresh(path)
        return path.read_text(encoding="utf-8"), receipt


def expect_fail(source: str, message: str) -> None:
    with tempfile.TemporaryDirectory(prefix="bw-view-refresh-") as temp:
        path = Path(temp) / "generated.js"
        path.write_text(source, encoding="utf-8")
        try:
            MODULE.patch_shared_memory_view_refresh(path)
        except MODULE.WasmError as error:
            if message not in str(error):
                raise AssertionError(error) from error
        else:
            raise AssertionError("invalid view-refresh input passed")


def main() -> None:
    output, receipt = transform("prefix;" + FIXTURE + ";suffix")
    assert receipt == {
        "contract": "shared-memory-fixed-view-refresh-v2",
        "refresh_marker": "BW_SPLIT_SHARED_MEMORY_VIEW_REFRESH_V1",
        "guard_marker": "BW_SPLIT_SHARED_MEMORY_GROWABLE_VIEW_GUARD_V1",
        "refresh_anchor_count_before": 1,
        "refresh_anchor_count_after": 0,
        "refresh_marker_count_after": 1,
        "refresh_replacement_count_after": 1,
        "guard_anchor_count_before": 1,
        "guard_anchor_count_after": 0,
        "guard_marker_count_after": 1,
        "guard_replacement_count_after": 1,
        "identity_predicate_count_after": 1,
        "byte_length_predicate_count_after": 1,
        "growable_length_guard_count_after": 1,
    }

    functions = output[output.index("function getMemoryBuffer"):output.index(";suffix")]
    script = f"""
let updates=0;
let wasmMemory={{buffer:new ArrayBuffer(32)}};
let HEAP8=new Int8Array(wasmMemory.buffer,0,8);
let HEAP32=new Int32Array(wasmMemory.buffer,0,2);
{functions}
growMemViews();
if(updates!==1||HEAP8.byteLength!==32||HEAP32.length!==8)process.exit(2);
const first=wasmMemory.buffer;HEAP8=new Int8Array(first);
wasmMemory.buffer=new ArrayBuffer(32);growMemViews();
if(updates!==2||HEAP8.buffer!==wasmMemory.buffer)process.exit(3);
growMemViews();if(updates!==2)process.exit(4);

const gsab=new SharedArrayBuffer(16,{{maxByteLength:128}});
wasmMemory={{buffer:gsab}};
HEAP8=new Int8Array(gsab,0,16);HEAP32=new Int32Array(gsab,0,4);
gsab.grow(64);
if(!HEAP8.buffer.growable||HEAP8.byteLength!==16||HEAP8.buffer.byteLength!==64)process.exit(5);
const beforeOld=updates;
function oldUpdateMemoryViews(){{if(HEAP8?.buffer?.growable)return;updates++;HEAP8=new Int8Array(gsab);HEAP32=new Int32Array(gsab)}}
oldUpdateMemoryViews();
if(updates!==beforeOld||HEAP32.length!==4)process.exit(6);
let oldFailed=false;try{{Atomics.store(HEAP32,4,17)}}catch(error){{oldFailed=error instanceof RangeError}}
if(!oldFailed)process.exit(7);
growMemViews();
if(updates!==beforeOld+1||HEAP8.byteLength!==64||HEAP32.length!==16)process.exit(8);
Atomics.store(HEAP32,4,23);if(Atomics.load(HEAP32,4)!==23)process.exit(9);

HEAP8=new Int8Array(gsab);HEAP32=new Int32Array(gsab);
gsab.grow(96);
if(HEAP8.byteLength!==96||HEAP32.byteLength!==96)process.exit(10);
const beforeCurrent=updates;growMemViews();updateMemoryViews();
if(updates!==beforeCurrent||HEAP8.byteLength!==96)process.exit(11);
"""
    subprocess.run(["node", "-e", script], check=True)

    expect_fail(GUARD_ANCHOR, "shared-memory view refresh expected one anchor, found 0")
    expect_fail(ANCHOR + ANCHOR + GUARD_ANCHOR, "shared-memory view refresh expected one anchor, found 2")
    expect_fail(ANCHOR, "shared-memory growable-view guard expected one anchor, found 0")
    expect_fail(ANCHOR + GUARD_ANCHOR + GUARD_ANCHOR,
                "shared-memory growable-view guard expected one anchor, found 2")
    expect_fail(output, "already patched")
    print(
        "shared-memory view refresh: growable fixed view, replaced buffer, "
        "length-tracking no-op + 5 negative PASS"
    )


if __name__ == "__main__":
    main()
