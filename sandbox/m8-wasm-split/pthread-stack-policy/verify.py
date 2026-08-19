#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile and run exact Emscripten stack-policy and JS-only twin-link proofs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
EMCC = REPO / "tools/emsdk/upstream/emscripten/emcc"
NODE = REPO / "tools/emsdk/node/22.16.0_64bit/bin/node"
STACK_SOURCE = HERE / "stack_policy.c"
TWIN_SOURCE = HERE / "twin.c"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True)


def artifact(path: Path) -> dict[str, object]:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def main() -> int:
    if len(sys.argv) != 2 or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", sys.argv[1]):
        raise SystemExit("usage: verify.py IMMUTABLE_LABEL")
    label = sys.argv[1]
    out = HERE / "evidence" / label
    if out.exists():
        raise SystemExit(f"refusing existing immutable evidence label {out}")
    out.mkdir(parents=True)

    common = [
        str(EMCC),
        "-O1",
        "-pthread",
        "-sPROXY_TO_PTHREAD=1",
        "-sEXIT_RUNTIME=1",
        "-sINITIAL_MEMORY=134217728",
        "-sALLOW_MEMORY_GROWTH=1",
        "-Wno-pthreads-mem-growth",
        "-sSTACK_SIZE=33554432",
    ]
    semantic_js = out / "stack_policy.js"
    semantic_command = [
        *common,
        "-sDEFAULT_PTHREAD_STACK_SIZE=8388608",
        "-sPTHREAD_POOL_SIZE=2",
        str(STACK_SOURCE),
        "-o",
        str(semantic_js),
    ]
    semantic_build = run(semantic_command, REPO)
    semantic_run = None
    facts = None
    failures: list[str] = []
    if semantic_build.returncode != 0:
        failures.append("semantic build failed")
    else:
        semantic_run = run([str(NODE), str(semantic_js)], REPO)
        rows = re.findall(r"BW_PTHREAD_STACK_POLICY (\{[^\n]+\})", semantic_run.stdout)
        if len(rows) == 1:
            facts = json.loads(rows[0])
        if semantic_run.returncode != 0 or "BW_PTHREAD_STACK_POLICY_RESULT PASS" not in semantic_run.stdout:
            failures.append("semantic executable failed")
        if facts != {
            "proxy_main": 33554432,
            "ordinary_default": 8388608,
            "explicit_child": 2097152,
        }:
            failures.append(f"semantic stack facts mismatch: {facts!r}")

    twin_rows: dict[str, dict[str, object]] = {}
    for name, default_size in (("default32", 33554432), ("default8", 8388608)):
        directory = out / name
        directory.mkdir()
        js_path = directory / "twin.js"
        command = [
            *common,
            f"-sDEFAULT_PTHREAD_STACK_SIZE={default_size}",
            "-sPTHREAD_POOL_SIZE=1",
            str(TWIN_SOURCE),
            "-o",
            str(js_path),
        ]
        completed = run(command, REPO)
        if completed.returncode != 0:
            failures.append(f"{name} twin build failed")
            continue
        wasm_path = directory / "twin.wasm"
        js_source = js_path.read_text(encoding="utf-8")
        twin_rows[name] = {
            "default_pthread_stack_size": default_size,
            "command": command,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "js": artifact(js_path),
            "wasm": artifact(wasm_path),
            "expected_default_literal_count": js_source.count(str(default_size)),
        }

    twin_pass = False
    if set(twin_rows) == {"default32", "default8"}:
        row32 = twin_rows["default32"]
        row8 = twin_rows["default8"]
        twin_pass = (
            row32["wasm"]["bytes"] == row8["wasm"]["bytes"]
            and row32["wasm"]["sha256"] == row8["wasm"]["sha256"]
            and row32["js"]["sha256"] != row8["js"]["sha256"]
            and row32["expected_default_literal_count"] >= 1
            and row8["expected_default_literal_count"] >= 1
        )
    if not twin_pass:
        failures.append("twin-link JS-only stack-policy proof failed")

    version = run([str(EMCC), "--version"], REPO)
    receipt = {
        "schema": "blender-web.pthread-stack-policy.v1",
        "status": "PASS" if not failures else "FAIL",
        "label": label,
        "contract": "proxy-main-32m-ordinary-pthread-8m-explicit-child-2m-v1",
        "failures": failures,
        "semantic": {
            "command": semantic_command,
            "build_exit": semantic_build.returncode,
            "build_stdout": semantic_build.stdout,
            "build_stderr": semantic_build.stderr,
            "run_exit": semantic_run.returncode if semantic_run else None,
            "run_stdout": semantic_run.stdout if semantic_run else "",
            "run_stderr": semantic_run.stderr if semantic_run else "",
            "facts": facts,
            "js": artifact(semantic_js) if semantic_js.is_file() else None,
            "wasm": artifact(out / "stack_policy.wasm")
            if (out / "stack_policy.wasm").is_file()
            else None,
        },
        "twin_link": {
            "pass": twin_pass,
            "wasm_byte_identical": twin_pass,
            "rows": twin_rows,
        },
        "sources": {
            "stack_policy": artifact(STACK_SOURCE),
            "twin": artifact(TWIN_SOURCE),
            "driver": artifact(Path(__file__).resolve()),
        },
        "toolchain": {
            "emcc": artifact(EMCC),
            "emcc_version": version.stdout + version.stderr,
            "node": artifact(NODE),
        },
    }
    receipt_path = out / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
