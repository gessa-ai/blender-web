#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate the P0-I/J cumulative-interaction diagnostic or Apple evidence run."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from typing import Any


class DiagnosticError(RuntimeError):
    pass


REQUIRED_STEPS = (
    "00-baseline",
    "01-preflight-modeling-click",
    "03a-reference-pose-3s",
    "03b-reference-pose-6s",
    "10-after-orbit",
    "20-after-pan",
    "30-after-zoom",
    "61b-frame-selected-3s",
    "61c-frame-selected-6s",
    "62a-post-stress-move",
    "62b-post-stress-undo",
    "63-final-orbit",
    "64a-post-orbit-3s",
    "64b-post-orbit-6s",
    "65a-post-orbit-known-pose-3s",
    "65b-post-orbit-known-pose-6s",
)
HARDWARE_EVIDENCE_CLASS = "apple-hardware-interaction-v1"
FALLBACK_EVIDENCE_CLASS = "diagnostic-software-fallback"
ADAPTER_CONTRACT = "hardware-webgpu-adapter-v1"
NODE_VERSION = "v22.16.0"
PLAYWRIGHT_VERSION = "1.61.1"
PNGJS_VERSION = "7.0.0"
CHROMIUM_VERSION = "149.0.7827.55"
SAME_POSE_CHANGED_FRACTION_LIMIT = 0.01
TEXT_REGION_CHANGED_FRACTION_LIMIT = 0.002
SHA256_LENGTH = 64
REQUIRED_PRODUCT_FILES = {
    "blender_browser.js",
    "blender_browser.wasm",
    "blender_browser.wasm.orig",
    "blender_browser.data",
    "blender_browser.split-build.json",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DiagnosticError(message)


def is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def validate_evidence_binding(document: dict[str, Any]) -> str:
    require(
        document.get("schema") == "blender-web.p0ij-interaction-stress.v1",
        "interaction evidence schema differs",
    )
    evidence_class = document.get("evidenceClass")
    require(
        evidence_class in {HARDWARE_EVIDENCE_CLASS, FALLBACK_EVIDENCE_CLASS},
        "evidence class is absent or unknown",
    )
    source = document.get("source")
    require(isinstance(source, dict) and is_sha256(source.get("sha256")),
            "producer source identity is absent")
    stack = document.get("stack")
    require(isinstance(stack, dict), "browser stack identity is absent")
    if evidence_class == FALLBACK_EVIDENCE_CLASS:
        require(document.get("adapter") is None, "fallback diagnostic claims an adapter")
        require(document.get("productIdentity") is None,
                "fallback diagnostic claims an exact product identity")
        return evidence_class

    require(document.get("run") not in (None, ""), "hardware run label is absent")
    require(stack.get("platform") == "darwin", "hardware evidence is not from darwin")
    require(stack.get("nodeVersion") == NODE_VERSION, "hardware Node version differs")
    require(stack.get("playwrightVersion") == PLAYWRIGHT_VERSION,
            "hardware Playwright version differs")
    require(stack.get("pngjsVersion") == PNGJS_VERSION, "hardware PNGJS version differs")
    require(stack.get("chromiumVersion") == CHROMIUM_VERSION,
            "hardware Chromium version differs")
    adapter = document.get("adapter")
    require(isinstance(adapter, dict), "hardware adapter proof is absent")
    require(adapter.get("contract") == ADAPTER_CONTRACT, "adapter contract differs")
    require(adapter.get("status") == "ACCEPTED" and adapter.get("reason") == "accepted-hardware",
            "adapter was not accepted as hardware")
    require(adapter.get("isFallbackAdapter") is False, "adapter is fallback or unclassified")
    require(adapter.get("softwareMatches") == [], "adapter matches a software identity")
    info = adapter.get("info")
    require(isinstance(info, dict) and any(info.get(key) for key in
            ("architecture", "device", "description")), "adapter detail identity is absent")

    identity = document.get("productIdentity")
    require(isinstance(identity, dict), "exact product identity is absent")
    files = identity.get("files")
    require(isinstance(files, dict) and set(files) == REQUIRED_PRODUCT_FILES,
            "exact product inventory differs")
    for name, fact in files.items():
        require(isinstance(fact, dict), f"product identity is invalid for {name}")
        require(type(fact.get("bytes")) is int and fact["bytes"] > 0,
                f"product byte size is invalid for {name}")
        require(is_sha256(fact.get("sha256")), f"product SHA-256 is invalid for {name}")
    generation = identity.get("generation")
    served = identity.get("servedGeneration")
    require(isinstance(generation, dict) and isinstance(served, dict),
            "local/served generation binding is absent")
    expected = files["blender_browser.wasm.orig"]["sha256"]
    require(generation.get("mode") == "capture" and served.get("mode") == "capture",
            "local/served product is not CAPTURE mode")
    require(generation.get("originalWasmSha256") == expected,
            "local split generation differs from wasm.orig")
    require(served.get("originalWasmSha256") == expected,
            "served split generation differs from wasm.orig")
    return evidence_class


def validate(document: dict[str, Any]) -> dict[str, int]:
    evidence_class = validate_evidence_binding(document)
    product = document.get("product")
    require(isinstance(product, dict), "product result is absent")
    require(product.get("state") == "running", "product did not remain running")
    require(type(product.get("ticks")) is int and product["ticks"] > 0, "tick counter is invalid")
    require(
        type(product.get("presents")) is int and product["presents"] > 0,
        "present counter is invalid",
    )

    hard_warnings = document.get("hardCompletenessWarnings")
    require(isinstance(hard_warnings, list), "hard completeness warning census is absent")
    require(not hard_warnings, f"hard completeness warnings remain: {hard_warnings[:3]}")
    page_errors = document.get("pageErrors")
    lifecycle = document.get("lifecycleEvents")
    require(isinstance(page_errors, list) and not page_errors, f"page errors remain: {page_errors}")
    require(
        isinstance(lifecycle, list) and not lifecycle,
        f"browser lifecycle failures remain: {lifecycle}",
    )

    steps_value = document.get("steps")
    require(isinstance(steps_value, list), "step results are absent")
    steps: dict[str, dict[str, Any]] = {}
    for step in steps_value:
        require(isinstance(step, dict), "step result is not an object")
        name = step.get("name")
        require(isinstance(name, str) and name, "step name is invalid")
        require(name not in steps, f"duplicate step: {name}")
        steps[name] = step
    missing = sorted(set(REQUIRED_STEPS) - set(steps))
    require(not missing, f"required steps are absent: {missing}")

    for name in REQUIRED_STEPS:
        step = steps[name]
        pixels = step.get("semanticPixels")
        require(isinstance(pixels, dict), f"{name}: semantic pixel result is absent")
        require(
            type(pixels.get("quantizedColors")) is int and pixels["quantizedColors"] >= 128,
            f"{name}: insufficient semantic color diversity",
        )
        ratio = pixels.get("nonWhiteRatio")
        require(
            isinstance(ratio, (int, float)) and not isinstance(ratio, bool) and ratio >= 0.5,
            f"{name}: canvas is predominantly a white compositor tile",
        )
        state = step.get("state")
        require(isinstance(state, dict), f"{name}: Blender-native state is absent")
        require(state.get("cube_in_view") is True, f"{name}: Cube projection is outside VIEW_3D")
        require(state.get("selected") is True, f"{name}: selected Cube state was lost")
        require(isinstance(state.get("view"), dict), f"{name}: VIEW_3D region is absent")

    preflight = steps["01-preflight-modeling-click"]
    require(preflight.get("workspaceRequested") == "Modeling", "preflight target changed")
    require(preflight.get("workspaceAccepted") is True, "clean Modeling workspace click failed")
    require(preflight["state"].get("workspace") == "Modeling", "preflight workspace state differs")

    settled_6s = steps["61c-frame-selected-6s"]
    require(
        steps["63-final-orbit"].get("sha256") != settled_6s.get("sha256"),
        "final orbit did not change pixels",
    )
    require(
        steps["65a-post-orbit-known-pose-3s"].get("sha256")
        == steps["65b-post-orbit-known-pose-6s"].get("sha256"),
        "post-orbit known-pose pixels did not settle between three and six seconds",
    )

    same_pose = document.get("samePoseCanaries")
    require(isinstance(same_pose, list) and len(same_pose) == 2,
            "same-pose pixel canary census differs")
    require([item.get("name") for item in same_pose] ==
            ["post-stress-known-pose", "post-orbit-known-pose"],
            "same-pose pixel canary order differs")
    expected_same_pose_steps = {
        "post-stress-known-pose": "61c-frame-selected-6s",
        "post-orbit-known-pose": "65b-post-orbit-known-pose-6s",
    }
    for canary in same_pose:
        name = canary.get("name")
        candidate_name = expected_same_pose_steps[name]
        require(canary.get("reference") == "03b-reference-pose-6s" and
                canary.get("candidate") == candidate_name,
                f"{name}: same-pose step binding differs")
        require(canary.get("referenceSha256") ==
                steps["03b-reference-pose-6s"].get("sha256"),
                f"{name}: reference screenshot identity differs")
        require(canary.get("candidateSha256") == steps[candidate_name].get("sha256"),
                f"{name}: candidate screenshot identity differs")
        require(canary.get("referenceState") == canary.get("candidateState"),
                f"{name}: Blender-native same-pose state differs")
        diff = canary.get("pixelDiff")
        require(isinstance(diff, dict), f"{name}: pixel diff is absent")
        require(diff.get("limit") == SAME_POSE_CHANGED_FRACTION_LIMIT,
                f"{name}: pixel-diff limit changed")
        for field in ("fullChangedFraction", "viewChangedFraction"):
            fraction = diff.get(field)
            require(isinstance(fraction, (int, float)) and not isinstance(fraction, bool),
                    f"{name}: {field} is invalid")
            require(0 <= fraction <= SAME_POSE_CHANGED_FRACTION_LIMIT,
                    f"{name}: {field} exceeds the same-pose limit")
        require(diff.get("detailRegionLimit") == TEXT_REGION_CHANGED_FRACTION_LIMIT,
                f"{name}: detail-region limit changed")
        details = diff.get("detailRegions")
        require(isinstance(details, dict) and set(details) ==
                {"viewHeader", "leftToolbar", "outlinerText", "workspaceTabs"},
                f"{name}: detail-region census differs")
        for region_name, region in details.items():
            require(isinstance(region, dict),
                    f"{name}: {region_name} result is invalid")
            fraction = region.get("changedFraction")
            require(isinstance(fraction, (int, float)) and not isinstance(fraction, bool),
                    f"{name}: {region_name} fraction is invalid")
            require(0 <= fraction <= TEXT_REGION_CHANGED_FRACTION_LIMIT,
                    f"{name}: {region_name} differs from the reference")

    operator = document.get("postStressOperatorCanary")
    require(isinstance(operator, dict), "post-stress operator canary is absent")
    require(operator.get("operation") == "G X 2 Enter; Control+Z",
            "post-stress operator recipe changed")
    before = operator.get("before")
    moved = operator.get("moved")
    undone = operator.get("undone")
    require(all(isinstance(value, list) and len(value) == 3 for value in
                (before, moved, undone)), "post-stress operator vectors are invalid")
    require(abs(moved[0] - (before[0] + 2)) < 0.0001,
            "post-stress move did not reach native Cube state")
    require(undone == before, "post-stress undo did not restore native Cube state")

    workspace_steps = sorted([
        step for name, step in steps.items() if len(name) >= 3 and name[:2].isdigit() and name[0] == "4"
    ], key=lambda step: step["name"])
    require(len(workspace_steps) == 9, "post-stress workspace attempt census is incomplete")
    expected_workspaces = [
        "Modeling", "Sculpting", "UV Editing", "Texture Paint", "Shading",
        "Animation", "Rendering", "Compositing", "Layout",
    ]
    require(
        [step.get("workspaceRequested") for step in workspace_steps] == expected_workspaces,
        "post-stress workspace target order changed",
    )
    workspace_transitions = [step for step in workspace_steps
                             if step.get("workspaceBefore") != step.get("workspaceRequested")]
    require(len(workspace_transitions) == 9, "post-stress transition census is incomplete")
    workspace_accepted = sum(step.get("workspaceAccepted") is True for step in workspace_transitions)
    require(workspace_accepted == 9, "post-stress workspace transitions did not all succeed")
    for expected, step in zip(expected_workspaces, workspace_steps, strict=True):
        require(
            isinstance(step.get("state"), dict) and step["state"].get("workspace") == expected,
            f"post-stress native workspace differs for {expected}",
        )

    canary = document.get("workspaceInputCanary")
    require(isinstance(canary, dict), "workspace button-coordinate canary is absent")
    expected_x = [352, 421, 494, 577, 657, 727, 805, 891, 288]
    require(canary.get("expectedX") == expected_x, "workspace coordinate canary changed")
    require(canary.get("domClickX") == expected_x, "DOM workspace click coordinates differ")
    require(canary.get("ghostPressX") == expected_x, "GHOST workspace press coordinates differ")

    relevant = document.get("relevantWarnings")
    require(isinstance(relevant, list), "relevant warning census is absent")
    pointer_fallbacks = [line for line in relevant if "Pointer Lock request rejected" in line]
    if evidence_class == FALLBACK_EVIDENCE_CLASS:
        require(len(pointer_fallbacks) == 1,
                "fallback pointer-lock rejection was not exactly bounded once")
    else:
        require(len(pointer_fallbacks) <= 1,
                "hardware pointer-lock rejection diagnostic was not bounded")

    return {
        "steps": len(steps_value),
        "states": len(document.get("states", [])),
        "presents": product["presents"],
        "workspace_accepted": workspace_accepted,
        "workspace_attempted": len(workspace_transitions),
        "hardware": int(evidence_class == HARDWARE_EVIDENCE_CLASS),
    }


def synthetic_document() -> dict[str, Any]:
    steps = []
    stable_hashes = {
        "03a-reference-pose-3s": "reference-pose",
        "03b-reference-pose-6s": "reference-pose",
        "61b-frame-selected-3s": "post-stress-pose",
        "61c-frame-selected-6s": "post-stress-pose",
        "65a-post-orbit-known-pose-3s": "post-orbit-pose",
        "65b-post-orbit-known-pose-6s": "post-orbit-pose",
    }
    canonical_state = {
        "workspace": "Layout",
        "mode": "OBJECT",
        "cube_in_view": True,
        "selected": True,
        "location": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
        "view": {"x": 0, "y": 0, "width": 100, "height": 100},
        "view_distance": 2.0,
        "view_location": [0.0, 0.0, 0.0],
        "view_rotation": [1.0, 0.0, 0.0, 0.0],
    }
    for index, name in enumerate(REQUIRED_STEPS):
        state = copy.deepcopy(canonical_state)
        if name == "01-preflight-modeling-click":
            state["workspace"] = "Modeling"
        if name == "62a-post-stress-move":
            state["location"] = [2.0, 0.0, 0.0]
        steps.append(
            {
                "name": name,
                "sha256": stable_hashes.get(name, f"hash-{index}"),
                "semanticPixels": {"quantizedColors": 256, "nonWhiteRatio": 0.9},
                "state": state,
                **(
                    {"workspaceRequested": "Modeling", "workspaceAccepted": True}
                    if name == "01-preflight-modeling-click"
                    else {}
                ),
            }
        )
    workspaces = [
        "Modeling", "Sculpting", "UV Editing", "Texture Paint", "Shading",
        "Animation", "Rendering", "Compositing", "Layout",
    ]
    for index, workspace in enumerate(workspaces):
        steps.append(
            {
                "name": f"4{index}-Workspace",
                "workspaceBefore": "Layout" if index == 0 else workspaces[index - 1],
                "workspaceRequested": workspace,
                "workspaceAccepted": True,
                "semanticPixels": {"quantizedColors": 256, "nonWhiteRatio": 0.9},
                "state": {
                    **copy.deepcopy(canonical_state),
                    "workspace": workspace,
                },
            }
        )
    same_pose_state = {
        "workspace": "Layout",
        "mode": "OBJECT",
        "selected": True,
        "location": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
        "view": {"x": 0, "y": 0, "width": 100, "height": 100},
        "viewDistance": 2.0,
        "viewLocation": [0.0, 0.0, 0.0],
        "viewRotation": [1.0, 0.0, 0.0, 0.0],
    }
    same_pose = []
    for name, candidate in (
        ("post-stress-known-pose", "61c-frame-selected-6s"),
        ("post-orbit-known-pose", "65b-post-orbit-known-pose-6s"),
    ):
        same_pose.append({
            "name": name,
            "reference": "03b-reference-pose-6s",
            "candidate": candidate,
            "referenceSha256": "reference-pose",
            "candidateSha256": stable_hashes[candidate],
            "referenceState": copy.deepcopy(same_pose_state),
            "candidateState": copy.deepcopy(same_pose_state),
            "pixelDiff": {
                "limit": SAME_POSE_CHANGED_FRACTION_LIMIT,
                "fullChangedFraction": 0.0,
                "viewChangedFraction": 0.0,
                "detailRegionLimit": TEXT_REGION_CHANGED_FRACTION_LIMIT,
                "detailRegions": {
                    region: {"changedFraction": 0.0}
                    for region in ("viewHeader", "leftToolbar", "outlinerText", "workspaceTabs")
                },
            },
        })
    return {
        "schema": "blender-web.p0ij-interaction-stress.v1",
        "evidenceClass": FALLBACK_EVIDENCE_CLASS,
        "run": None,
        "source": {"path": "capture_diagnostic.mjs", "sha256": "a" * 64},
        "stack": {
            "platform": "linux",
            "nodeVersion": NODE_VERSION,
            "playwrightVersion": PLAYWRIGHT_VERSION,
            "pngjsVersion": PNGJS_VERSION,
            "chromiumVersion": CHROMIUM_VERSION,
        },
        "adapter": None,
        "productIdentity": None,
        "product": {"state": "running", "ticks": 10, "presents": 10},
        "steps": steps,
        "states": [{}],
        "hardCompletenessWarnings": [],
        "relevantWarnings": ["[bw] Pointer Lock request rejected; continuing without lock"],
        "lifecycleEvents": [],
        "pageErrors": [],
        "workspaceInputCanary": {
            "expectedX": [352, 421, 494, 577, 657, 727, 805, 891, 288],
            "domClickX": [352, 421, 494, 577, 657, 727, 805, 891, 288],
            "ghostPressX": [352, 421, 494, 577, 657, 727, 805, 891, 288],
        },
        "samePoseCanaries": same_pose,
        "postStressOperatorCanary": {
            "operation": "G X 2 Enter; Control+Z",
            "before": [0.0, 0.0, 0.0],
            "moved": [2.0, 0.0, 0.0],
            "undone": [0.0, 0.0, 0.0],
        },
    }


def hardware_document() -> dict[str, Any]:
    document = synthetic_document()
    document["evidenceClass"] = HARDWARE_EVIDENCE_CLASS
    document["run"] = "apple-r1"
    document["stack"]["platform"] = "darwin"
    document["relevantWarnings"] = []
    document["adapter"] = {
        "contract": ADAPTER_CONTRACT,
        "status": "ACCEPTED",
        "reason": "accepted-hardware",
        "isFallbackAdapter": False,
        "softwareMatches": [],
        "info": {
            "vendor": "apple",
            "architecture": "metal-3",
            "device": "Apple M4 Pro",
            "description": "Apple M4 Pro",
        },
    }
    files = {
        name: {"bytes": index + 1, "sha256": chr(ord("a") + index) * 64}
        for index, name in enumerate(sorted(REQUIRED_PRODUCT_FILES))
    }
    expected = files["blender_browser.wasm.orig"]["sha256"]
    generation = {
        "mode": "capture",
        "originalWasmSha256": expected,
        "instrumentedWasmSha256": "e" * 64,
        "javascriptSha256": "f" * 64,
    }
    document["productIdentity"] = {
        "binDir": "build-wasm-windowed-opt/bin",
        "files": files,
        "generation": copy.deepcopy(generation),
        "servedGeneration": copy.deepcopy(generation),
    }
    return document


def step_named(document: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in document["steps"] if step["name"] == name)


def self_check() -> int:
    baseline = synthetic_document()
    validate(baseline)
    hardware = hardware_document()
    validate(hardware)
    mutations = (
        lambda value: value["product"].__setitem__("state", "error"),
        lambda value: value["hardCompletenessWarnings"].append("incomplete"),
        lambda value: value["pageErrors"].append("pageerror"),
        lambda value: step_named(value, "01-preflight-modeling-click").__setitem__(
            "workspaceAccepted", False),
        lambda value: value["steps"][0]["semanticPixels"].__setitem__("quantizedColors", 2),
        lambda value: value["steps"][0]["state"].__setitem__("cube_in_view", False),
        lambda value: step_named(value, "03b-reference-pose-6s").__setitem__(
            "sha256", "not-settled"),
        lambda value: step_named(value, "61c-frame-selected-6s").__setitem__(
            "sha256", "not-settled"),
        lambda value: step_named(value, "65a-post-orbit-known-pose-3s").__setitem__(
            "sha256", "not-settled"),
        lambda value: value["relevantWarnings"].clear(),
        lambda value: next(step for step in value["steps"]
                           if step.get("workspaceRequested") == "Modeling" and
                           step["name"].startswith("4")).__setitem__("workspaceAccepted", False),
        lambda value: next(step for step in value["steps"]
                           if step.get("workspaceRequested") == "Modeling" and
                           step["name"].startswith("4"))["state"].__setitem__(
                               "workspace", "Layout"),
        lambda value: value["workspaceInputCanary"]["ghostPressX"].__setitem__(0, 288),
        lambda value: value["samePoseCanaries"][0]["pixelDiff"].__setitem__(
            "viewChangedFraction", 0.2),
        lambda value: value["samePoseCanaries"][0]["pixelDiff"]["detailRegions"][
            "viewHeader"].__setitem__("changedFraction", 0.1),
        lambda value: value["samePoseCanaries"][1]["candidateState"].__setitem__(
            "viewDistance", 3.0),
        lambda value: value["postStressOperatorCanary"].__setitem__(
            "moved", [0.0, 0.0, 0.0]),
        lambda value: value["postStressOperatorCanary"].__setitem__(
            "undone", [2.0, 0.0, 0.0]),
    )
    rejected = 0
    for mutate in mutations:
        candidate = copy.deepcopy(baseline)
        mutate(candidate)
        try:
            validate(candidate)
        except DiagnosticError:
            rejected += 1
        else:
            raise DiagnosticError("self-check mutation was accepted")
    hardware_mutations = (
        lambda value: value["adapter"].__setitem__("isFallbackAdapter", True),
        lambda value: value["adapter"].__setitem__("softwareMatches", ["swiftshader"]),
        lambda value: value["adapter"]["info"].update(
            {"architecture": "", "device": "", "description": ""}),
        lambda value: value["stack"].__setitem__("chromiumVersion", "149.0.0.0"),
        lambda value: value["productIdentity"]["servedGeneration"].__setitem__(
            "originalWasmSha256", "0" * 64),
        lambda value: value["productIdentity"]["files"].pop("blender_browser.data"),
        lambda value: value.__setitem__("evidenceClass", FALLBACK_EVIDENCE_CLASS),
    )
    hardware_rejected = 0
    for mutate in hardware_mutations:
        candidate = copy.deepcopy(hardware)
        mutate(candidate)
        try:
            validate(candidate)
        except DiagnosticError:
            hardware_rejected += 1
        else:
            raise DiagnosticError("hardware self-check mutation was accepted")
    print(
        "P0IJ_INTERACTION_STRESS_SELFCHECK_PASS "
        f"positive=2 negative={rejected + hardware_rejected} "
        f"hardware_negative={hardware_rejected}"
    )
    return 0


def main() -> int:
    if sys.argv[1:] == ["--self-check"]:
        return self_check()
    if len(sys.argv) > 2:
        raise DiagnosticError("usage: analyze_diagnostic.py [diagnostic.json|--self-check]")
    path = (
        Path(sys.argv[1])
        if len(sys.argv) == 2
        else Path(__file__).with_name("artifacts") / "diagnostic.json"
    )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DiagnosticError(f"could not read {path}: {error}") from error
    require(isinstance(document, dict), "diagnostic root is not an object")
    result = validate(document)
    evidence_label = "HARDWARE" if result["hardware"] else "DIAGNOSTIC"
    print(
        f"P0IJ_INTERACTION_STRESS_{evidence_label}_PASS "
        f"steps={result['steps']} states={result['states']} presents={result['presents']} "
        "hard_warnings=0 page_errors=0 "
        f"workspace_transitions={result['workspace_accepted']}/{result['workspace_attempted']} "
        "button_coords=dom-ghost-matched same_pose=2 operator=move-undo"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DiagnosticError as error:
        print(f"P0I_INTERACTION_STRESS_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
