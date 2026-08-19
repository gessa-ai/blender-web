#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fail-closed verifier for the current-artifact M5 click-pick receipt."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = REPO / "sandbox/m5-click-pick/evidence"
DEFAULT_RUN_LABEL = "m5-click-pick-r3"
DEFAULT_RECEIPT_SHA256 = "77a8532ed3aefa355dcaeefde0f56d381fa0e5a3a208a2a2ac3fc2d2b1961b72"
RUN_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RUNTIME_BINARY_PATHS = (
    "build-wasm-windowed-opt/bin/blender_browser.js",
    "build-wasm-windowed-opt/bin/blender_browser.wasm",
    "build-wasm-windowed-opt/bin/blender_browser.deferred.wasm",
    "build-wasm-windowed-opt/bin/blender_browser.data",
)
RUNTIME_CONTRACT_PATH = "sandbox/m5-final/runtime-artifacts.mjs"
SPLIT_MANIFEST_PATH = "build-wasm-windowed-opt/bin/blender_browser.split-build.json"
DENIED_CONSOLE = (
    "GPUValidationError",
    "WebGPU Error",
    "device lost",
    "table index is out of bounds",
    "WebGPU selection readback failed",
    "Timed out waiting for WebGPU selection readback",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"M5_CLICK_PICK_FAIL {message}")


def resolve_repo_path(value: str) -> Path:
    path = (REPO / value).resolve()
    require(path == REPO or REPO in path.parents, f"path escapes repository: {value}")
    return path


def verify_file(record: dict) -> None:
    path = resolve_repo_path(record["path"])
    require(path.is_file(), f"missing bound file: {record['path']}")
    require(path.stat().st_size == record["bytes"], f"size drift: {record['path']}")
    require(sha256(path) == record["sha256"], f"hash drift: {record['path']}")


def main() -> None:
    run_label = os.environ.get("M5_CLICK_RUN_LABEL", DEFAULT_RUN_LABEL)
    digest_override = os.environ.get("M5_CLICK_RECEIPT_SHA256")
    require(RUN_LABEL_RE.fullmatch(run_label) is not None, "invalid M5_CLICK_RUN_LABEL")
    if run_label != DEFAULT_RUN_LABEL:
        require(digest_override is not None,
                "M5_CLICK_RECEIPT_SHA256 is required for an alternate run")
    expected_digest = digest_override or DEFAULT_RECEIPT_SHA256
    require(SHA256_RE.fullmatch(expected_digest) is not None,
            "invalid M5_CLICK_RECEIPT_SHA256")
    run = EVIDENCE_ROOT / run_label
    receipt_path = run / "receipt.json"

    require(receipt_path.is_file(), f"missing immutable receipt: {run_label}")
    digest_line = (run / "receipt.sha256").read_text().strip().split()
    require(len(digest_line) == 2 and digest_line[1] == "receipt.json", "bad receipt.sha256")
    require(digest_line[0] == expected_digest == sha256(receipt_path), "receipt digest mismatch")
    receipt = json.loads(receipt_path.read_text())

    require(receipt["schema"] == "blender-web.m5-click-pick-continuation.v1", "schema drift")
    require(receipt["run"] == run_label, "run-label drift")
    require(receipt["status"] == "PASS", "receipt is not PASS")
    require(receipt["contract"]["runtimeArtifacts"] == list(RUNTIME_BINARY_PATHS),
            "runtime-artifact contract drift")
    result = receipt["result"]
    require(result["fatal"] is None and result["pageErrors"] == [], "browser failure recorded")
    require(result["statePass"] and result["inputPass"] and result["tracePass"],
            "state/input/trace gate failed")
    require(result["selectOperatorCount"] == 2, "expected exactly two view3d.select ops")
    require(result["deselectOperatorCount"] == 2, "expected exactly two deselect ops")
    require(result["externalRequestCount"] == 0, "external request recorded")
    require(result["finalState"]["active"] == "Cube", "Cube is not active")
    require(result["finalState"]["selected"] == ["Cube"], "Cube is not sole selection")
    require(result["canvas"]["backing"] == [1280, 720], "canvas backing drift")
    require(result["canvas"]["css"] == [1280, 720], "canvas CSS drift")
    require(result["canvas"]["dpr"] == 1, "device pixel ratio drift")
    require(result["canvas"]["crossOriginIsolated"] is True, "COOP/COEP isolation absent")

    binary_records = receipt["provenance"]["binaryFiles"]
    by_path = {record["path"]: record for record in binary_records}
    require(len(binary_records) == len(by_path), "duplicate binary receipt path")
    require(set(by_path) == set(RUNTIME_BINARY_PATHS), "binary receipt set drift")
    for record in binary_records:
        verify_file(record)
    require(receipt["provenance"]["runtimeContract"]["path"] == RUNTIME_CONTRACT_PATH,
            "runtime-contract provenance path drift")
    require(receipt["provenance"]["splitManifest"]["path"] == SPLIT_MANIFEST_PATH,
            "split-manifest provenance path drift")
    verify_file(receipt["provenance"]["runtimeContract"])
    verify_file(receipt["provenance"]["splitManifest"])
    verify_file(receipt["provenance"]["driver"])
    verify_file(receipt["provenance"]["nativeGolden"])
    for record in receipt["provenance"]["shell"]:
        verify_file(record)
    for record in receipt["artifacts"].values():
        verify_file(record)

    expected_cycle = [
        "bpy.ops.object.select_all(action='DESELECT')",
        "bpy.ops.view3d.select(deselect_all=True)",
    ]
    trace = (run / "operator-trace.txt").read_text().splitlines()
    require(trace[-4:] == expected_cycle * 2, "operator trace does not end in two native cycles")
    require(sum(line.startswith("bpy.ops.view3d.select(") for line in trace) == 2,
            "extra/missing view3d.select trace")

    inputs = json.loads((run / "trusted-inputs.json").read_text())
    clicks = [event for event in inputs if event["type"] == "click"]
    mouse = [event for event in inputs if event["type"] in {"mousedown", "mouseup", "click"}]
    alt_a = [event for event in inputs if event["type"] == "keydown" and event["key"] == "a"]
    require(len(clicks) == 2 and len(mouse) == 6 and len(alt_a) == 2, "trusted input count drift")
    require(all(event["isTrusted"] and event["targetId"] == "canvas" and
                event["activeId"] == "canvas" for event in mouse + alt_a),
            "untrusted or misrouted input")
    require(all(event["altKey"] for event in alt_a), "deselect keys lacked Alt")

    console = (run / "console.log").read_text()
    for denied in DENIED_CONSOLE:
        require(denied not in console, f"denied console diagnostic: {denied}")

    print(
        "M5_CLICK_PICK_PASS "
        f"run={run_label} receipt={sha256(receipt_path)} "
        f"primary_wasm={by_path['build-wasm-windowed-opt/bin/blender_browser.wasm']['sha256']} "
        f"deferred_wasm={by_path['build-wasm-windowed-opt/bin/blender_browser.deferred.wasm']['sha256']} "
        "cycles=2 select_ops=2 final=Cube"
    )


if __name__ == "__main__":
    main()
