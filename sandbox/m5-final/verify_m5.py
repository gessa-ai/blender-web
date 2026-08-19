#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fail-closed, browser-free verifier for the complete strict M5 contract."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]

DEFERRED_WASM_FILENAME = os.environ.get(
    "BW_DEFERRED_WASM_FILENAME", "blender_browser.deferred.wasm"
)
require_deferred_name = re.compile(
    r"^blender_browser(?:\.[A-Za-z0-9_-]+)*\.wasm$"
)

CURRENT_BINARY_PATHS = (
    "build-wasm-windowed-opt/bin/blender_browser.js",
    "build-wasm-windowed-opt/bin/blender_browser.wasm",
    f"build-wasm-windowed-opt/bin/{DEFERRED_WASM_FILENAME}",
    "build-wasm-windowed-opt/bin/blender_browser.data",
)
SPLIT_MANIFEST_PATH = "build-wasm-windowed-opt/bin/blender_browser.split-build.json"
RUNTIME_CONTRACT_PATH = "sandbox/m5-final/runtime-artifacts.mjs"

# Alternate immutable runs are selected with M5_<KIND>_RUN_LABEL and must also
# supply their independently pinned M5_<KIND>_RECEIPT_SHA256.  A label without
# its digest never falls back to the digest of the historical default run.
RECEIPT_SELECTORS = {
    "CLICK": (
        "sandbox/m5-click-pick/evidence",
        "m5-click-pick-r3",
        "77a8532ed3aefa355dcaeefde0f56d381fa0e5a3a208a2a2ac3fc2d2b1961b72",
    ),
    "CANVAS": (
        "sandbox/m5-canvas-smoke/evidence",
        "m5-canvas-smoke-r5",
        "75d0db1d8a1f43220ebdf6978ef523f1a30f0ad8228c03e9023b2073e52752d7",
    ),
    "LATENCY": (
        "sandbox/m5-latency/evidence",
        "m5-trusted-latency-r8",
        "9af43c79945c267c2cbe96472b074592e3b4deb8c629b52c3183282e361a0096",
    ),
}
RUN_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

PARITY_SESSIONS = (
    "object_select_all",
    "object_transform_grxsz",
    "edit_mode_toggle",
    "edit_mode_select_modes",
    "mesh_extrude_region",
    "mesh_bevel",
    "undo_depth",
)
NUL_NORMALIZED_SESSIONS = {
    "mesh_extrude_region": (1, 0),
    "undo_depth": (2, 0),
}

BUDGETS = {
    "endToEndMedianMs": 100,
    "endToEndP95Ms": 150,
    "keypressToOperatorMedianMs": 33,
    "changeThresholdFloor": 5,
}

DENIED_CONSOLE = (
    "GPUValidationError",
    "WebGPU Error",
    "device lost",
    "table index is out of bounds",
    "WebGPU selection readback failed",
    "Timed out waiting for WebGPU selection readback",
)


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def repo_path(value: str) -> Path:
    path = (REPO / value).resolve()
    require(path == REPO or REPO in path.parents, f"path escapes repository: {value}")
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    require(path.is_file(), f"missing JSON: {path.relative_to(REPO)}")
    try:
        return json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"invalid JSON {path.relative_to(REPO)}: {error}") from error


def verify_file_record(record: dict[str, Any]) -> None:
    require(set(record) >= {"path", "bytes", "sha256"}, "incomplete file receipt")
    path = repo_path(record["path"])
    require(path.is_file(), f"missing bound file: {record['path']}")
    require(path.stat().st_size == record["bytes"], f"size drift: {record['path']}")
    require(sha256(path) == record["sha256"], f"hash drift: {record['path']}")


def selected_receipt(kind: str) -> tuple[Path, str, str]:
    root, default_label, default_digest = RECEIPT_SELECTORS[kind]
    label_name = f"M5_{kind}_RUN_LABEL"
    digest_name = f"M5_{kind}_RECEIPT_SHA256"
    label = os.environ.get(label_name, default_label)
    digest_override = os.environ.get(digest_name)
    require(RUN_LABEL_RE.fullmatch(label) is not None, f"invalid {label_name}")
    if label != default_label:
        require(digest_override is not None,
                f"{digest_name} is required when selecting {label_name}={label}")
    digest = digest_override or default_digest
    require(SHA256_RE.fullmatch(digest) is not None, f"invalid {digest_name}")
    return repo_path(f"{root}/{label}"), label, digest


def verify_receipt_digest(selector: tuple[Path, str, str]) -> tuple[Path, dict[str, Any]]:
    run_path, label, expected = selector
    receipt_path = run_path / "receipt.json"
    run = run_path.relative_to(REPO)
    require(receipt_path.is_file(), f"missing immutable receipt: {run}/receipt.json")
    require(sha256(receipt_path) == expected, f"receipt digest drift: {run}")
    digest_path = run_path / "receipt.sha256"
    require(digest_path.is_file(), f"missing receipt.sha256: {run}")
    fields = digest_path.read_text().strip().split()
    require(fields == [expected, "receipt.json"], f"receipt.sha256 mismatch: {run}")
    receipt = load_json(receipt_path)
    require(isinstance(receipt, dict), f"receipt is not an object: {run}")
    require(receipt.get("run") == label, f"selected run-label drift: {run}")
    return run_path, receipt


def snapshot_current_binaries() -> dict[str, tuple[int, str]]:
    snapshot = {}
    for path_string in CURRENT_BINARY_PATHS:
        path = repo_path(path_string)
        require(path.is_file(), f"missing current binary: {path_string}")
        snapshot[path_string] = (path.stat().st_size, sha256(path))
    return snapshot


def verify_binary_records(
        records: list[dict[str, Any]], current_binaries: dict[str, tuple[int, str]]) -> None:
    by_path = {record["path"]: record for record in records}
    require(len(records) == len(by_path), "duplicate binary receipt path")
    require(set(by_path) == set(CURRENT_BINARY_PATHS), "binary receipt set drift")
    for path_string, (size, digest) in current_binaries.items():
        record = by_path[path_string]
        require(record["bytes"] == size, f"bound binary size drift: {path_string}")
        require(record["sha256"] == digest, f"bound binary hash drift: {path_string}")
        verify_file_record(record)


def verify_current_binaries(current_binaries: dict[str, tuple[int, str]]) -> None:
    require(tuple(current_binaries) == CURRENT_BINARY_PATHS, "current binary selector drift")
    for path_string, (size, digest) in current_binaries.items():
        path = repo_path(path_string)
        require(path.is_file(), f"missing current binary: {path_string}")
        require(path.stat().st_size == size, f"current binary size drift: {path_string}")
        require(sha256(path) == digest, f"current binary hash drift: {path_string}")


def exact_members(observed: list[Any], expected: list[Any], label: str) -> None:
    require(len(observed) == len(set(observed)), f"{label} contains duplicates")
    require(sorted(observed) == sorted(expected), f"{label} drift: {observed}")


def verify_manifest_artifact(
        record: dict[str, Any], expected_name: str, binary_record: tuple[int, str], label: str) -> None:
    require(Path(record["path"]).name == expected_name, f"{label} path drift")
    require((record["bytes"], record["sha256"]) == binary_record,
            f"{label} size/hash drift")


def verify_split_manifest(current_binaries: dict[str, tuple[int, str]]) -> None:
    require(require_deferred_name.fullmatch(DEFERRED_WASM_FILENAME) is not None
            and DEFERRED_WASM_FILENAME not in {"blender_browser.wasm", "blender_browser.wasm.orig"},
            "invalid BW_DEFERRED_WASM_FILENAME")
    manifest = load_json(repo_path(SPLIT_MANIFEST_PATH))
    require(isinstance(manifest, dict), "split manifest is not an object")
    require(manifest["schema"] == 1, "split manifest schema drift")
    require(manifest["mode"] == "apply" and manifest["verdict"] == "PASS",
            "split manifest is not an applied PASS")
    policy = manifest["inventory_policy"]
    require(policy["unlisted"] == "reject", "split manifest no longer rejects unlisted Wasm")
    exact_members(policy["bundle_roles"], ["primary", "deferred"], "bundle roles")

    js_path = "build-wasm-windowed-opt/bin/blender_browser.js"
    primary_path = "build-wasm-windowed-opt/bin/blender_browser.wasm"
    deferred_path = f"build-wasm-windowed-opt/bin/{DEFERRED_WASM_FILENAME}"
    require(Path(manifest["js"]["path"]).name == "blender_browser.js" and
            manifest["js"]["sha256"] == current_binaries[js_path][1],
            "split manifest JS drift")
    verify_manifest_artifact(
        manifest["primary"], "blender_browser.wasm", current_binaries[primary_path], "primary Wasm")
    verify_manifest_artifact(
        manifest["secondary"], DEFERRED_WASM_FILENAME,
        current_binaries[deferred_path], "deferred Wasm")

    inventory = manifest["wasm_inventory"]
    require(isinstance(inventory, list), "wasm_inventory is not an array")
    exact_members([item["role"] for item in inventory],
                  ["primary", "deferred", "original_build_only"], "Wasm inventory roles")
    shipped = [item for item in inventory if item["shipped"] is True]
    exact_members([item["role"] for item in shipped], ["primary", "deferred"], "shipping roles")
    exact_members([item["filename"] for item in shipped],
                  ["blender_browser.wasm", DEFERRED_WASM_FILENAME],
                  "shipping Wasm files")
    by_name = {
        "blender_browser.wasm": current_binaries[primary_path],
        DEFERRED_WASM_FILENAME: current_binaries[deferred_path],
    }
    for item in shipped:
        verify_manifest_artifact(item, item["filename"], by_name[item["filename"]],
                                 f"shipping inventory {item['role']}")
    original = next(item for item in inventory if item["role"] == "original_build_only")
    require(original["filename"] == "blender_browser.wasm.orig" and original["shipped"] is False,
            "original build-only Wasm became a shipping artifact")


def verify_runtime_provenance(receipt: dict[str, Any]) -> None:
    runtime_contract = receipt["provenance"]["runtimeContract"]
    split_manifest = receipt["provenance"]["splitManifest"]
    require(runtime_contract["path"] == RUNTIME_CONTRACT_PATH,
            "runtime-contract provenance path drift")
    require(split_manifest["path"] == SPLIT_MANIFEST_PATH,
            "split-manifest provenance path drift")
    verify_file_record(runtime_contract)
    verify_file_record(split_manifest)


def verify_artifact_records(receipt: dict[str, Any]) -> None:
    for record in receipt["artifacts"].values():
        require(record is not None, "null artifact receipt")
        verify_file_record(record)


def verify_click(
        selector: tuple[Path, str, str], current_binaries: dict[str, tuple[int, str]]) -> None:
    run_path, receipt = verify_receipt_digest(selector)
    require(receipt["schema"] == "blender-web.m5-click-pick-continuation.v1", "click schema drift")
    require(receipt["status"] == "PASS", "click receipt is not PASS")
    require(receipt["contract"]["runtimeArtifacts"] == list(CURRENT_BINARY_PATHS),
            "click runtime-artifact contract drift")
    result = receipt["result"]
    require(result["fatal"] is None and result["pageErrors"] == [], "click browser failure")
    require(result["statePass"] and result["inputPass"] and result["tracePass"],
            "click state/input/trace gate failed")
    require(result["selectOperatorCount"] == 2, "click select operator count drift")
    require(result["deselectOperatorCount"] == 2, "click deselect operator count drift")
    require(result["externalRequestCount"] == 0, "click external request recorded")
    require(result["finalState"]["active"] == "Cube", "click final active object drift")
    require(result["finalState"]["selected"] == ["Cube"], "click final selection drift")
    require(result["finalState"]["cube_selected"] is True, "click Cube is not selected")
    canvas = result["canvas"]
    require(canvas["backing"] == [1280, 720] and canvas["css"] == [1280, 720],
            "click canvas extent drift")
    require(canvas["dpr"] == 1 and canvas["crossOriginIsolated"] is True,
            "click canvas isolation drift")
    verify_binary_records(receipt["provenance"]["binaryFiles"], current_binaries)
    verify_file_record(receipt["provenance"]["driver"])
    verify_runtime_provenance(receipt)
    verify_file_record(receipt["provenance"]["nativeGolden"])
    for record in receipt["provenance"]["shell"]:
        verify_file_record(record)
    verify_artifact_records(receipt)

    expected_cycle = [
        "bpy.ops.object.select_all(action='DESELECT')",
        "bpy.ops.view3d.select(deselect_all=True)",
    ]
    trace = (run_path / "operator-trace.txt").read_text().splitlines()
    require(trace[-4:] == expected_cycle * 2, "click trace lacks two exact native cycles")
    require(sum(line.startswith("bpy.ops.view3d.select(") for line in trace) == 2,
            "click trace has extra/missing select operators")
    inputs = load_json(run_path / "trusted-inputs.json")
    clicks = [event for event in inputs if event["type"] == "click"]
    mouse = [event for event in inputs if event["type"] in {"mousedown", "mouseup", "click"}]
    alt_a = [event for event in inputs if event["type"] == "keydown" and event["key"] == "a"]
    require(len(clicks) == 2 and len(mouse) == 6 and len(alt_a) == 2,
            "click trusted-input count drift")
    require(all(event["isTrusted"] and event["targetId"] == "canvas" and
                event["activeId"] == "canvas" for event in mouse + alt_a),
            "click input is untrusted or misrouted")
    require(all(event["altKey"] for event in alt_a), "click deselect input lacked Alt")
    console = (run_path / "console.log").read_text()
    for diagnostic in DENIED_CONSOLE:
        require(diagnostic not in console, f"click denied console diagnostic: {diagnostic}")


def ordered_subsequence(haystack: list[str], needle: list[str]) -> bool:
    position = 0
    for expected in needle:
        try:
            position = haystack.index(expected, position) + 1
        except ValueError:
            return False
    return True


def verify_canvas(
        selector: tuple[Path, str, str], current_binaries: dict[str, tuple[int, str]]) -> None:
    run_path, receipt = verify_receipt_digest(selector)
    require(receipt["schema"] == "blender-web.m5-playwright-canvas-smoke.v1", "canvas schema drift")
    require(receipt["status"] == "PASS", "canvas receipt is not PASS")
    require(receipt["contract"]["runtimeArtifacts"] == list(CURRENT_BINARY_PATHS),
            "canvas runtime-artifact contract drift")
    result = receipt["result"]
    require(result["fatal"] is None and result["pageErrors"] == [], "canvas browser failure")
    require(result["statePass"] and result["tracePass"] and result["keyPass"],
            "canvas state/trace/key gate failed")
    require(result["externalRequestCount"] == 0, "canvas external request recorded")
    canvas = result["canvas"]
    require(canvas["backing"] == [1280, 720] and canvas["css"] == [1280, 720],
            "canvas extent drift")
    require(canvas["dpr"] == 1 and canvas["activeId"] == "canvas" and
            canvas["crossOriginIsolated"] is True and canvas["hasRuntimeModule"] is True,
            "canvas runtime/focus/isolation drift")
    expected_actions = [
        ("tab_into_edit", "Tab", "EDIT_MODE", "EDIT", ["Cube"]),
        ("tab_back_object", "Tab", "OBJECT_AFTER_EDIT", "OBJECT", ["Cube"]),
        ("deselect_all", "Alt+a", "DESELECTED", "OBJECT", []),
        ("select_all", "a", "SELECT_ALL", "OBJECT", ["Camera", "Cube", "Light"]),
    ]
    require(len(result["actionReceipts"]) == len(expected_actions), "canvas action count drift")
    for action, expected in zip(result["actionReceipts"], expected_actions, strict=True):
        action_id, press, state_name, cube_mode, selected = expected
        require((action["id"], action["playwrightPress"], action["expectedState"]) ==
                (action_id, press, state_name), f"canvas action contract drift: {action_id}")
        observed = action["observedState"]
        require(observed["name"] == state_name and observed["cube_mode"] == cube_mode and
                observed["selected"] == selected, f"canvas action state drift: {action_id}")
    verify_binary_records(receipt["provenance"]["binaryFiles"], current_binaries)
    verify_file_record(receipt["provenance"]["driver"])
    verify_runtime_provenance(receipt)
    for group in ("shell", "nativeGoldens", "existingWasmReceipts"):
        for record in receipt["provenance"][group]:
            verify_file_record(record)
    verify_artifact_records(receipt)

    trace = (run_path / "operator-trace.txt").read_text().splitlines()
    required_trace = [
        "bpy.ops.object.mode_set(mode='EDIT', toggle=True)",
        "bpy.ops.object.editmode_toggle()",
        "bpy.ops.object.mode_set(mode='EDIT', toggle=True)",
        "bpy.ops.object.editmode_toggle()",
        "bpy.ops.object.select_all(action='DESELECT')",
        "bpy.ops.object.select_all(action='SELECT')",
    ]
    require(ordered_subsequence(trace, required_trace), "canvas native trace subsequence missing")
    keys = load_json(run_path / "trusted-keys.json")
    non_modifiers = [event for event in keys if event["key"] not in {"Alt", "Control", "Meta", "Shift"}]
    require([event["key"] for event in non_modifiers] == ["Escape", "Tab", "Tab", "a", "a"],
            "canvas trusted-key sequence drift")
    require(all(event["isTrusted"] and event["targetId"] == "canvas" and
                event["activeId"] == "canvas" for event in non_modifiers),
            "canvas input is untrusted or misrouted")
    require(non_modifiers[3]["altKey"] is True and non_modifiers[4]["altKey"] is False,
            "canvas Alt+A/A modifiers drift")


def normalized_trace(path: Path) -> bytes:
    return path.read_bytes().replace(b"\0", b"")


def verify_non_click_parity() -> None:
    summary_list = load_json(REPO / "sandbox/m5-prep/wasm-out/_run-summary.json")
    require(isinstance(summary_list, list), "M5 replay summary is not a list")
    summary = {entry["session"]: entry for entry in summary_list}
    require(len(summary) == len(summary_list), "duplicate M5 replay summary session")
    for name in PARITY_SESSIONS:
        session = f"m5_core.{name}"
        golden_state = REPO / f"sandbox/m5-prep/goldens/{session}.json"
        wasm_state = REPO / f"sandbox/m5-prep/wasm-out/{session}.json"
        require(golden_state.read_bytes() == wasm_state.read_bytes(), f"state parity drift: {session}")
        state_diff = (REPO / f"sandbox/m5-prep/wasm-out/{session}.statediff.txt").read_text()
        require(state_diff.startswith("PASS ") and "(0 divergences)" in state_diff,
                f"state-diff receipt drift: {session}")

        native_trace = REPO / f"sandbox/m5-prep/traces/{session}.trace.txt"
        wasm_trace = REPO / f"sandbox/m5-prep/wasm-out/{session}.trace.txt"
        require(normalized_trace(native_trace) == normalized_trace(wasm_trace),
                f"operator trace parity drift: {session}")
        expected_nuls = NUL_NORMALIZED_SESSIONS.get(name, (0, 0))
        observed_nuls = (native_trace.read_bytes().count(b"\0"), wasm_trace.read_bytes().count(b"\0"))
        require(observed_nuls == expected_nuls, f"trace NUL contract drift: {session}")
        if name in NUL_NORMALIZED_SESSIONS:
            note = (REPO / f"sandbox/m5-prep/wasm-out/{session}.trace.nul.txt").read_text()
            require(f"native NUL bytes={expected_nuls[0]}" in note and
                    f"wasm NUL bytes={expected_nuls[1]}" in note and
                    "normalized out" in note, f"trace NUL note drift: {session}")

        require(session in summary, f"missing M5 replay summary: {session}")
        entry = summary[session]
        line_count = len(wasm_trace.read_bytes().splitlines())
        require(entry["result"] == "ok" and entry["errors"] == [],
                f"M5 replay result drift: {session}")
        require(entry["ntrace_file"] == line_count and entry["ntrace_console"] == line_count,
                f"M5 replay trace count drift: {session}")


def finite_nonnegative(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def verify_latency(
        selector: tuple[Path, str, str], current_binaries: dict[str, tuple[int, str]]) -> None:
    run_path, receipt = verify_receipt_digest(selector)
    require(receipt["schema"] == "blender-web.m5-trusted-roi-latency.v1", "latency schema drift")
    require(receipt["status"] == "PASS", "latency receipt is not PASS")
    require(receipt["contract"]["runtimeArtifacts"] == list(CURRENT_BINARY_PATHS),
            "latency runtime-artifact contract drift")
    require(receipt["contract"]["budgets"] == BUDGETS, "latency budget drift")
    result = receipt["result"]
    require(result["fatal"] is None and result["pageErrors"] == [], "latency browser failure")
    require(result["externalRequestCount"] == 0 and result["deniedDiagnostics"] == [],
            "latency network/GPU diagnostic failure")
    require(result["inputPass"] and result["canvasPass"] and result["measurementPass"] and
            result["budgetPass"], "latency strict gate failed")
    expected_n = result["nRequested"]
    require(expected_n >= 10, "latency sample count weakened below 10")
    require(result["nDispatch"] == expected_n and result["nWithOperator"] == expected_n and
            result["nWithVisible"] == expected_n, "latency sample coverage incomplete")
    require(result["calibration"]["pairs"] == 5, "latency calibration pair count drift")
    require(result["frameDiff"]["changeThreshold"] >= BUDGETS["changeThresholdFloor"],
            "latency change detector weakened")
    expected_roi = {"left": 850, "top": 26, "width": 200, "height": 621}
    require(receipt["contract"]["operatorProbe"] == "bpy.ops.wm.context_toggle",
            "latency operator probe drift")
    require(receipt["contract"]["roi"]["derivation"] ==
            "rightmost 200px of READY View3D WINDOW region", "latency ROI derivation drift")
    require(receipt["contract"]["roi"]["rectangle"] == expected_roi and
            result["frameDiff"]["roi"] == expected_roi, "latency ROI rectangle drift")
    require(receipt["contract"]["roi"]["sourceView3d"] == result["ready"]["view3d"],
            "latency ROI source geometry drift")
    metrics = result["metrics"]
    require(metrics["keypressToOperatorMs"]["n"] == expected_n and
            metrics["endToEndMs"]["n"] == expected_n, "latency metric n drift")
    require(metrics["keypressToOperatorMs"]["median"] <= BUDGETS["keypressToOperatorMedianMs"],
            "keypress-to-operator median exceeds 33 ms")
    require(metrics["endToEndMs"]["median"] <= BUDGETS["endToEndMedianMs"],
            "end-to-end median exceeds 100 ms")
    require(metrics["endToEndMs"]["p95"] <= BUDGETS["endToEndP95Ms"],
            "end-to-end p95 exceeds 150 ms")
    require(len(result["samples"]) == expected_n, "latency sample array length drift")
    for index, sample in enumerate(result["samples"]):
        require(sample["index"] == index and sample["hasOperator"] and sample["hasVisible"],
                f"latency incomplete sample {index}")
        require(finite_nonnegative(sample["keypressToOperatorMs"]) and
                finite_nonnegative(sample["operatorToPresentMs"]) and
                finite_nonnegative(sample["endToEndMs"]), f"latency invalid sample {index}")
        require(sample["maxDifference"] > result["frameDiff"]["changeThreshold"],
                f"latency sample lacks threshold-crossing pixels: {index}")
    canvas = result["canvas"]
    require(canvas["backing"] == [1280, 720] and canvas["css"] == [1280, 720] and
            canvas["dpr"] == 1 and canvas["activeId"] == "canvas" and
            canvas["crossOriginIsolated"] is True, "latency canvas contract drift")
    inputs = receipt["browser"]["trustedInputs"]
    require(len(inputs) == expected_n, "latency trusted input count drift")
    require(all(event["index"] == index and event["key"] == "n" and event["code"] == "KeyN" and
                event["isTrusted"] is True and event["targetId"] == "canvas" and
                event["activeId"] == "canvas" for index, event in enumerate(inputs)),
            "latency input is untrusted or misrouted")
    verify_binary_records(receipt["provenance"]["binaryFiles"], current_binaries)
    verify_file_record(receipt["provenance"]["driver"])
    verify_runtime_provenance(receipt)
    for record in receipt["provenance"]["shell"]:
        verify_file_record(record)
    verify_artifact_records(receipt)
    console = (run_path / "console.log").read_text()
    for diagnostic in DENIED_CONSOLE:
        require(diagnostic not in console, f"latency denied console diagnostic: {diagnostic}")


def main() -> None:
    try:
        selectors = {kind: selected_receipt(kind) for kind in RECEIPT_SELECTORS}
        current_binaries = snapshot_current_binaries()
        verify_current_binaries(current_binaries)
        verify_split_manifest(current_binaries)
        verify_non_click_parity()
        verify_click(selectors["CLICK"], current_binaries)
        verify_canvas(selectors["CANVAS"], current_binaries)
        verify_latency(selectors["LATENCY"], current_binaries)
        # Catch an artifact replacement during verification rather than letting
        # different receipts bind different binary generations.
        verify_current_binaries(current_binaries)
        verify_split_manifest(current_binaries)
    except (KeyError, TypeError, ValueError, OSError, VerificationError) as error:
        print(f"M5_FINAL_FAIL {error}")
        raise SystemExit(1) from error
    print(
        "M5_FINAL_PASS "
        f"parity=7 click={selectors['CLICK'][1]} canvas={selectors['CANVAS'][1]} "
        f"trusted_latency={selectors['LATENCY'][1]} "
        f"primary_wasm={current_binaries['build-wasm-windowed-opt/bin/blender_browser.wasm'][1]} "
        f"deferred_wasm={current_binaries[f'build-wasm-windowed-opt/bin/{DEFERRED_WASM_FILENAME}'][1]}"
    )


if __name__ == "__main__":
    main()
