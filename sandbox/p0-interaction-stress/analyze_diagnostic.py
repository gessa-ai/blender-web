#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate the P0-I/J cumulative-interaction diagnostic or Apple evidence run."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any


class DiagnosticError(RuntimeError):
    pass


REQUIRED_STEPS = (
    "00-baseline",
    "01-preflight-modeling-click",
    "02a-isolated-front",
    "02b-isolated-right",
    "02c-isolated-top",
    "02d-isolated-camera",
    "02e-isolated-camera-orbit-cancelled",
    "02f-isolated-select-all",
    "02g-isolated-deselect-all",
    "02h-isolated-orbit-before-click",
    "02i-isolated-click-select",
    "02j-isolated-move",
    "02k-isolated-undo",
    "02l-isolated-orbit-after-click",
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
ISOLATED_VIEW_KEYS = ["Numpad1", "Numpad3", "Numpad7", "Numpad0", "Numpad4"]
ISOLATED_VIEW_STEPS = (
    "02a-isolated-front",
    "02b-isolated-right",
    "02c-isolated-top",
    "02d-isolated-camera",
    "02e-isolated-camera-orbit-cancelled",
)
ISOLATED_VIEW_EFFECTS = ["view-change"] * 4 + ["cancelled-in-camera-view"]
DESELECTED_STEPS = {"02g-isolated-deselect-all", "02h-isolated-orbit-before-click"}
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


def is_utc_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo == timezone.utc


def validate_evidence_binding(document: dict[str, Any]) -> str:
    require(
        document.get("schema") == "blender-web.p0ij-interaction-stress.v2",
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


def validate_move_undo(operator: object, label: str) -> tuple[list[Any], list[Any], list[Any]]:
    require(isinstance(operator, dict), f"{label} operator canary is absent")
    require(operator.get("operation") == "G X 2 Enter; Control+Z",
            f"{label} operator recipe changed")
    before = operator.get("before")
    moved = operator.get("moved")
    undone = operator.get("undone")
    require(all(isinstance(value, list) and len(value) == 3 for value in
                (before, moved, undone)), f"{label} operator vectors are invalid")
    require(abs(moved[0] - (before[0] + 2)) < 0.0001,
            f"{label} move did not reach native Cube state")
    require(undone == before, f"{label} undo did not restore native Cube state")
    return before, moved, undone


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
    require(type(product.get("viewportContent")) is int and product["viewportContent"] >= 1,
            "qualified VIEW_3D present counter is invalid")
    require(type(product.get("redrawRetries")) is int and product["redrawRetries"] > 0,
            "redraw-retry generation is invalid")

    hard_warnings = document.get("hardCompletenessWarnings")
    require(isinstance(hard_warnings, list), "hard completeness warning census is absent")
    require(not hard_warnings, f"hard completeness warnings remain: {hard_warnings[:3]}")
    pending_diagnostics = document.get("pendingCompletenessDiagnostics")
    require(isinstance(pending_diagnostics, list),
            "pending completeness diagnostic census is absent")
    pending_pattern = re.compile(
        r"^\[bw\] WGPUWeb-bind-pending shader=.+ surviving=\[[0-9,]*\] "
        r"assembled=\[[0-9,]*\] pending=\[[0-9,]*\]$")
    require(all(isinstance(line, str) and pending_pattern.fullmatch(line)
                for line in pending_diagnostics),
            "pending completeness diagnostic is malformed")
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
        if name in DESELECTED_STEPS:
            require(state.get("selected") is False and state.get("selected_count") == 0,
                    f"{name}: isolated deselection state differs")
        else:
            require(state.get("selected") is True, f"{name}: selected Cube state was lost")
            require(type(state.get("selected_count")) is int and state["selected_count"] >= 1,
                    f"{name}: native selection count is invalid")
        require(isinstance(state.get("view"), dict), f"{name}: VIEW_3D region is absent")
        require(type(step.get("redrawRetries")) is int and step["redrawRetries"] >= 0,
                f"{name}: redraw-retry generation is absent")

    preflight = steps["01-preflight-modeling-click"]
    require(preflight.get("workspaceRequested") == "Modeling", "preflight target changed")
    require(preflight.get("workspaceAccepted") is True, "clean Modeling workspace click failed")
    require(preflight["state"].get("workspace") == "Modeling", "preflight workspace state differs")

    contract = document.get("contract")
    require(isinstance(contract, dict), "interaction contract is absent")
    require(contract.get("isolatedFreeze") == {
        "viewKeys": ISOLATED_VIEW_KEYS,
        "selectionCounts": [3, 0, 1],
        "hardwareSelectionMode": "viewport",
        "operator": "G X 2 Enter; Control+Z",
        "orbits": 2,
    }, "isolated freeze contract differs")
    isolated = document.get("isolationCanary")
    require(isinstance(isolated, dict), "isolated freeze canary is absent")
    require(isolated.get("viewKeys") == ISOLATED_VIEW_KEYS,
            "isolated view-key sequence differs")
    views = isolated.get("views")
    require(isinstance(views, list) and len(views) == len(ISOLATED_VIEW_KEYS),
            "isolated native view census differs")
    require([view.get("key") for view in views] == ISOLATED_VIEW_KEYS,
            "isolated native view order differs")
    require([view.get("sha256") for view in views] ==
            [steps[name].get("sha256") for name in ISOLATED_VIEW_STEPS],
            "isolated view screenshot identities differ")
    require(len(set(view.get("sha256") for view in views[:4])) == 4,
            "isolated changing views did not all change pixels")
    require(views[4].get("sha256") == views[3].get("sha256"),
            "cancelled camera-view orbit unexpectedly changed pixels")
    camera_settles = [view.get("pixelSettleMs") for view in views[3:]]
    require(all(type(value) is int and 3000 <= value <= 12000 for value in camera_settles),
            "camera-view stable-pixel windows are absent or out of bounds")
    require([steps[name].get("pixelSettleMs") for name in ISOLATED_VIEW_STEPS[3:]] ==
            camera_settles,
            "camera-view stable-pixel evidence differs")
    sequences = [view.get("sequence") for view in views]
    require(all(type(sequence) is int and sequence > 0 for sequence in sequences),
            "isolated native view sequence is invalid")
    require(sequences[:4] == sorted(set(sequences[:4])) and sequences[4] >= sequences[3],
            "isolated native view sequence did not follow change/change/change/change/no-op")
    perspectives = [view.get("perspective") for view in views]
    require(perspectives[:3] == ["ORTHO", "ORTHO", "ORTHO"],
            "isolated orthographic view states differ")
    require(perspectives[3:] == ["CAMERA", "CAMERA"],
            "isolated camera/cancelled-orbit states differ")
    rotations = [view.get("rotation") for view in views]
    require(all(isinstance(rotation, list) and len(rotation) == 4 for rotation in rotations),
            "isolated native view rotations are invalid")
    require(len({json.dumps(rotation) for rotation in rotations[:4]}) == 4 and
            rotations[4] == rotations[3],
            "isolated native view rotations do not bind the camera-view cancellation")
    require([view.get("expectedEffect") for view in views] == ISOLATED_VIEW_EFFECTS,
            "isolated view-effect census differs")
    for key, name, view in zip(ISOLATED_VIEW_KEYS, ISOLATED_VIEW_STEPS, views, strict=True):
        require(steps[name].get("isolatedInput") == key,
                f"{name}: isolated input binding differs")
        require(steps[name].get("expectedEffect") == view.get("expectedEffect"),
                f"{name}: isolated view-effect binding differs")
        require(steps[name]["state"].get("view_perspective") == view.get("perspective") and
                steps[name]["state"].get("view_rotation") == view.get("rotation"),
                f"{name}: isolated native view record differs")

    expected_selection_counts = (
        [3, 0, 1] if evidence_class == HARDWARE_EVIDENCE_CLASS else [3, 0, 3]
    )
    require(isolated.get("selectionCounts") == expected_selection_counts,
            "isolated selection/deselection/post-orbit liveness states differ")
    require(steps["02f-isolated-select-all"]["state"].get("selected_count") == 3,
            "isolated select-all did not select the default scene")
    require(steps["02i-isolated-click-select"]["state"].get("selected_count") ==
            expected_selection_counts[-1] and
            steps["02i-isolated-click-select"]["state"].get("active_object") == "Cube",
            "isolated post-orbit selection liveness differs")
    click = isolated.get("click")
    require(isinstance(click, dict) and type(click.get("expectedX")) is int,
            "isolated click coordinate canary is absent")
    require(click.get("domX") == click["expectedX"] and
            click.get("ghostX") == click["expectedX"],
            "isolated DOM/GHOST click coordinates differ")
    if evidence_class == HARDWARE_EVIDENCE_CLASS:
        require(click.get("selectionMode") == "viewport",
                "hardware evidence used a non-viewport selection recovery")
        require(click.get("fallbackLivenessInput") is None,
                "hardware evidence claims a fallback liveness input")
    else:
        require(click.get("selectionMode") in {"viewport", "fallback-select-all"},
                "fallback selection mode is invalid")
        if click.get("selectionMode") == "fallback-select-all":
            require(click.get("fallbackLivenessInput") == "A",
                    "fallback Select All liveness input is absent")

    selection_restore = isolated.get("fallbackSelectionRestore")
    if click.get("selectionMode") == "fallback-select-all":
        require(isinstance(selection_restore, dict) and
                selection_restore.get("method") == "outliner-click",
                "fallback Cube-only Outliner restore is absent")
        require(selection_restore.get("expectedX") == selection_restore.get("domX") ==
                selection_restore.get("ghostX") and
                selection_restore.get("expectedY") == selection_restore.get("domY") and
                selection_restore.get("expectedGhostY") == selection_restore.get("ghostY"),
                "fallback Cube-only Outliner coordinates differ")
        require(type(selection_restore.get("sequence")) is int and
                selection_restore["sequence"] > 0 and
                selection_restore.get("selectedCount") == 1 and
                selection_restore.get("activeObject") == "Cube",
                "fallback Outliner restore did not leave Cube selected alone")
    else:
        require(selection_restore is None,
                "non-fallback evidence claims a fallback selection restore")

    for label, field, before_name, after_name in (
        ("pre-click", "preClickOrbit", "02g-isolated-deselect-all",
         "02h-isolated-orbit-before-click"),
        ("post-click", "postClickOrbit", "02k-isolated-undo",
         "02l-isolated-orbit-after-click"),
    ):
        orbit = isolated.get(field)
        require(isinstance(orbit, dict), f"isolated {label} orbit canary is absent")
        require(orbit.get("beforeRotation") != orbit.get("afterRotation"),
                f"isolated {label} orbit did not change native view rotation")
        require(orbit.get("beforeSha256") == steps[before_name].get("sha256") and
                orbit.get("afterSha256") == steps[after_name].get("sha256"),
                f"isolated {label} orbit screenshot binding differs")
        require(orbit.get("beforeSha256") != orbit.get("afterSha256"),
                f"isolated {label} orbit did not change pixels")
        retries = orbit.get("redrawRetries")
        require(isinstance(retries, list) and len(retries) == 2 and
                all(type(value) is int and value >= 0 for value in retries) and
                retries[1] > retries[0],
                f"isolated {label} orbit did not publish an input redraw retry")
        require(type(orbit.get("pixelSettleMs")) is int and
                0 <= orbit["pixelSettleMs"] <= 12000,
                f"isolated {label} orbit did not recover pixels within the bounded retry")

    _, isolated_moved, isolated_undone = validate_move_undo(
        isolated.get("operator"), "isolated post-click",
    )
    require(steps["02j-isolated-move"]["state"].get("location") == isolated_moved and
            steps["02k-isolated-undo"]["state"].get("location") == isolated_undone,
            "isolated operator step states differ from the canary")

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

    _, moved, undone = validate_move_undo(
        document.get("postStressOperatorCanary"), "post-stress",
    )
    require(steps["62a-post-stress-move"]["state"].get("location") == moved and
            steps["62b-post-stress-undo"]["state"].get("location") == undone,
            "post-stress operator step states differ from the canary")

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
        "isolated_views": len(views),
        "hardware": int(evidence_class == HARDWARE_EVIDENCE_CLASS),
    }


def validate_hardware_series(documents: list[dict[str, Any]]) -> dict[str, int]:
    """Require repeated Apple evidence from one exact product generation.

    Each document must first pass the complete single-run contract. The cross-run checks keep a
    repeated acceptance claim from mixing product generations, browser stacks, producers, or
    adapters, and require independently labeled/captured runs rather than duplicate evidence.
    """
    require(len(documents) >= 2, "hardware series requires at least two runs")
    results = [validate(document) for document in documents]
    require(all(result["hardware"] == 1 for result in results),
            "hardware series contains non-hardware evidence")

    runs = [document.get("run") for document in documents]
    require(len(set(runs)) == len(runs), "hardware series run labels are not unique")
    captured_at = [document.get("capturedAt") for document in documents]
    require(all(is_utc_timestamp(value) for value in captured_at),
            "hardware series capture timestamps are absent or invalid")
    require(len(set(captured_at)) == len(captured_at),
            "hardware series capture timestamps are not unique")

    baseline = documents[0]
    baseline_identity = baseline["productIdentity"]
    for index, document in enumerate(documents[1:], 2):
        prefix = f"hardware run {index}"
        require(document.get("source") == baseline.get("source"),
                f"{prefix} producer identity differs")
        require(document.get("stack") == baseline.get("stack"),
                f"{prefix} browser stack differs")
        require(document.get("adapter") == baseline.get("adapter"),
                f"{prefix} adapter identity differs")
        identity = document["productIdentity"]
        for field in ("files", "generation", "servedGeneration"):
            require(identity.get(field) == baseline_identity.get(field),
                    f"{prefix} product {field} differs")

    return {
        "runs": len(documents),
        "steps": sum(result["steps"] for result in results),
        "states": sum(result["states"] for result in results),
        "presents": sum(result["presents"] for result in results),
        "workspace_accepted": sum(result["workspace_accepted"] for result in results),
        "workspace_attempted": sum(result["workspace_attempted"] for result in results),
    }


def synthetic_document() -> dict[str, Any]:
    steps = []
    stable_hashes = {
        "02d-isolated-camera": "isolated-camera",
        "02e-isolated-camera-orbit-cancelled": "isolated-camera",
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
        "selected_count": 1,
        "active_object": "Cube",
        "location": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
        "view": {"x": 0, "y": 0, "width": 100, "height": 100},
        "view_distance": 2.0,
        "view_location": [0.0, 0.0, 0.0],
        "view_rotation": [1.0, 0.0, 0.0, 0.0],
        "view_perspective": "PERSP",
    }
    isolated_view_states = {
        "02a-isolated-front": ("Numpad1", "ORTHO", [0.7071, -0.7071, 0.0, 0.0]),
        "02b-isolated-right": ("Numpad3", "ORTHO", [0.5, -0.5, -0.5, -0.5]),
        "02c-isolated-top": ("Numpad7", "ORTHO", [1.0, 0.0, 0.0, 0.0]),
        "02d-isolated-camera": ("Numpad0", "CAMERA", [0.92, 0.1, 0.2, 0.3]),
        "02e-isolated-camera-orbit-cancelled": (
            "Numpad4", "CAMERA", [0.92, 0.1, 0.2, 0.3]
        ),
    }
    for index, name in enumerate(REQUIRED_STEPS):
        state = copy.deepcopy(canonical_state)
        metadata = {}
        if name == "01-preflight-modeling-click":
            state["workspace"] = "Modeling"
        if name in isolated_view_states:
            key, perspective, rotation = isolated_view_states[name]
            state["view_perspective"] = perspective
            state["view_rotation"] = rotation
            metadata["isolatedInput"] = key
            metadata["expectedEffect"] = (
                "cancelled-in-camera-view" if key == "Numpad4" else "view-change"
            )
            if key in {"Numpad0", "Numpad4"}:
                metadata["pixelSettleMs"] = 3000
        if name == "02f-isolated-select-all":
            state["selected_count"] = 3
        if name in {"02i-isolated-click-select", "02j-isolated-move", "02k-isolated-undo",
                    "02l-isolated-orbit-after-click"}:
            state["selected_count"] = 3
        if name in {"02f-isolated-select-all", "02g-isolated-deselect-all"}:
            state["view_perspective"] = "CAMERA"
            state["view_rotation"] = [0.92, 0.1, 0.2, 0.3]
        if name in DESELECTED_STEPS:
            state["selected"] = False
            state["selected_count"] = 0
            if name == "02h-isolated-orbit-before-click":
                state["view_perspective"] = "PERSP"
                state["view_rotation"] = [0.8, 0.2, 0.3, 0.4]
        if name in {"02i-isolated-click-select", "02j-isolated-move", "02k-isolated-undo"}:
            state["view_rotation"] = [0.8, 0.2, 0.3, 0.4]
        if name == "02l-isolated-orbit-after-click":
            state["view_rotation"] = [0.7, 0.3, 0.4, 0.5]
        if name in {"02j-isolated-move", "62a-post-stress-move"}:
            state["location"] = [2.0, 0.0, 0.0]
        steps.append(
            {
                "name": name,
                "sha256": stable_hashes.get(name, f"hash-{index}"),
                "semanticPixels": {"quantizedColors": 256, "nonWhiteRatio": 0.9},
                "state": state,
                "redrawRetries": index * 10,
                **(
                    {"workspaceRequested": "Modeling", "workspaceAccepted": True}
                    if name == "01-preflight-modeling-click"
                    else {}
                ),
                **metadata,
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
        "selectedCount": 1,
        "activeObject": "Cube",
        "location": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
        "view": {"x": 0, "y": 0, "width": 100, "height": 100},
        "viewDistance": 2.0,
        "viewLocation": [0.0, 0.0, 0.0],
        "viewRotation": [1.0, 0.0, 0.0, 0.0],
        "viewPerspective": "PERSP",
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
    step_by_name = {step["name"]: step for step in steps}
    isolated_views = []
    for sequence, name in enumerate(ISOLATED_VIEW_STEPS, 1):
        key, perspective, rotation = isolated_view_states[name]
        isolated_views.append({
            "key": key,
            "expectedEffect": ISOLATED_VIEW_EFFECTS[sequence - 1],
            "sequence": min(sequence, 4),
            "perspective": perspective,
            "rotation": rotation,
            "sha256": step_by_name[name]["sha256"],
            **(
                {"pixelSettleMs": step_by_name[name]["pixelSettleMs"]}
                if "pixelSettleMs" in step_by_name[name] else {}
            ),
        })
    return {
        "schema": "blender-web.p0ij-interaction-stress.v2",
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
        "product": {
            "state": "running",
            "ticks": 10,
            "presents": 10,
            "viewportContent": 1,
            "redrawRetries": 500,
        },
        "contract": {
            "isolatedFreeze": {
                "viewKeys": ISOLATED_VIEW_KEYS,
                "selectionCounts": [3, 0, 1],
                "hardwareSelectionMode": "viewport",
                "operator": "G X 2 Enter; Control+Z",
                "orbits": 2,
            },
        },
        "steps": steps,
        "states": [{}],
        "hardCompletenessWarnings": [],
        "pendingCompletenessDiagnostics": [],
        "relevantWarnings": ["[bw] Pointer Lock request rejected; continuing without lock"],
        "lifecycleEvents": [],
        "pageErrors": [],
        "workspaceInputCanary": {
            "expectedX": [352, 421, 494, 577, 657, 727, 805, 891, 288],
            "domClickX": [352, 421, 494, 577, 657, 727, 805, 891, 288],
            "ghostPressX": [352, 421, 494, 577, 657, 727, 805, 891, 288],
        },
        "isolationCanary": {
            "viewKeys": ISOLATED_VIEW_KEYS,
            "views": isolated_views,
            "selectionCounts": [3, 0, 3],
            "click": {
                "expectedX": 500,
                "domX": 500,
                "ghostX": 500,
                "selectionMode": "fallback-select-all",
                "fallbackLivenessInput": "A",
            },
            "fallbackSelectionRestore": {
                "method": "outliner-click",
                "expectedX": 1150,
                "expectedY": 106,
                "expectedGhostY": 613,
                "domX": 1150,
                "domY": 106,
                "ghostX": 1150,
                "ghostY": 613,
                "sequence": 24,
                "selectedCount": 1,
                "activeObject": "Cube",
            },
            "preClickOrbit": {
                "beforeRotation": [0.92, 0.1, 0.2, 0.3],
                "afterRotation": [0.8, 0.2, 0.3, 0.4],
                "beforeSha256": step_by_name["02g-isolated-deselect-all"]["sha256"],
                "afterSha256": step_by_name["02h-isolated-orbit-before-click"]["sha256"],
                "redrawRetries": [
                    step_by_name["02g-isolated-deselect-all"]["redrawRetries"],
                    step_by_name["02h-isolated-orbit-before-click"]["redrawRetries"],
                ],
                "pixelSettleMs": 250,
            },
            "operator": {
                "operation": "G X 2 Enter; Control+Z",
                "before": [0.0, 0.0, 0.0],
                "moved": [2.0, 0.0, 0.0],
                "undone": [0.0, 0.0, 0.0],
            },
            "postClickOrbit": {
                "beforeRotation": [0.8, 0.2, 0.3, 0.4],
                "afterRotation": [0.7, 0.3, 0.4, 0.5],
                "beforeSha256": step_by_name["02k-isolated-undo"]["sha256"],
                "afterSha256": step_by_name["02l-isolated-orbit-after-click"]["sha256"],
                "redrawRetries": [
                    step_by_name["02k-isolated-undo"]["redrawRetries"],
                    step_by_name["02l-isolated-orbit-after-click"]["redrawRetries"],
                ],
                "pixelSettleMs": 250,
            },
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
    document["capturedAt"] = "2026-08-28T00:00:01.000Z"
    document["stack"]["platform"] = "darwin"
    document["relevantWarnings"] = []
    document["isolationCanary"]["click"]["selectionMode"] = "viewport"
    document["isolationCanary"]["click"]["fallbackLivenessInput"] = None
    document["isolationCanary"]["fallbackSelectionRestore"] = None
    document["isolationCanary"]["selectionCounts"] = [3, 0, 1]
    for name in ("02i-isolated-click-select", "02j-isolated-move", "02k-isolated-undo",
                 "02l-isolated-orbit-after-click"):
        step_named(document, name)["state"]["selected_count"] = 1
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
    hardware_second = copy.deepcopy(hardware)
    hardware_second["run"] = "apple-r2"
    hardware_second["capturedAt"] = "2026-08-28T00:00:02.000Z"
    validate_hardware_series([hardware, hardware_second])
    mutations = (
        lambda value: value.__setitem__("schema", "blender-web.p0ij-interaction-stress.v1"),
        lambda value: value["product"].__setitem__("state", "error"),
        lambda value: value["hardCompletenessWarnings"].append("incomplete"),
        lambda value: value["pendingCompletenessDiagnostics"].append("malformed"),
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
        lambda value: value["contract"]["isolatedFreeze"].__setitem__("orbits", 1),
        lambda value: value["isolationCanary"]["viewKeys"].__setitem__(4, "Numpad5"),
        lambda value: value["isolationCanary"]["views"][3].__setitem__(
            "perspective", "PERSP"),
        lambda value: value["isolationCanary"]["views"][3].pop("pixelSettleMs"),
        lambda value: step_named(value, "02e-isolated-camera-orbit-cancelled").__setitem__(
            "pixelSettleMs", 2999),
        lambda value: value["isolationCanary"]["views"][1].__setitem__(
            "sha256", value["isolationCanary"]["views"][0]["sha256"]),
        lambda value: value["isolationCanary"].__setitem__("selectionCounts", [1, 0, 1]),
        lambda value: value["isolationCanary"]["click"].__setitem__("ghostX", 501),
        lambda value: value["isolationCanary"]["click"].__setitem__(
            "selectionMode", "synthetic-recovery"),
        lambda value: value["isolationCanary"]["preClickOrbit"].__setitem__(
            "afterRotation", value["isolationCanary"]["preClickOrbit"]["beforeRotation"]),
        lambda value: value["isolationCanary"]["postClickOrbit"].__setitem__(
            "afterSha256", value["isolationCanary"]["postClickOrbit"]["beforeSha256"]),
        lambda value: value["isolationCanary"]["operator"].__setitem__(
            "moved", [0.0, 0.0, 0.0]),
        lambda value: step_named(value, "02g-isolated-deselect-all")["state"].__setitem__(
            "selected_count", 1),
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
        lambda value: value["isolationCanary"]["click"].__setitem__(
            "selectionMode", "fallback-select-all"),
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
    series_mutations = (
        lambda values: values.pop(),
        lambda values: values[1].__setitem__("run", values[0]["run"]),
        lambda values: values[1].__setitem__("capturedAt", values[0]["capturedAt"]),
        lambda values: values[1].__setitem__("capturedAt", "not-a-timestampZ"),
        lambda values: values[1].__setitem__("evidenceClass", FALLBACK_EVIDENCE_CLASS),
        lambda values: values[1]["source"].__setitem__("sha256", "0" * 64),
        lambda values: values[1]["stack"].__setitem__("nodeVersion", "v22.17.0"),
        lambda values: values[1]["adapter"]["info"].__setitem__("device", "Other Apple GPU"),
        lambda values: values[1]["productIdentity"]["files"][
            "blender_browser.data"].__setitem__("sha256", "0" * 64),
        lambda values: values[1]["productIdentity"]["generation"].__setitem__(
            "instrumentedWasmSha256", "0" * 64),
        lambda values: values[1]["productIdentity"]["servedGeneration"].__setitem__(
            "javascriptSha256", "0" * 64),
    )
    series_rejected = 0
    for mutate in series_mutations:
        candidates = [copy.deepcopy(hardware), copy.deepcopy(hardware_second)]
        mutate(candidates)
        try:
            validate_hardware_series(candidates)
        except DiagnosticError:
            series_rejected += 1
        else:
            raise DiagnosticError("hardware-series self-check mutation was accepted")
    print(
        "P0IJ_INTERACTION_STRESS_SELFCHECK_PASS "
        f"positive=3 negative={rejected + hardware_rejected + series_rejected} "
        f"hardware_negative={hardware_rejected} series_negative={series_rejected}"
    )
    return 0


def main() -> int:
    if sys.argv[1:] == ["--self-check"]:
        return self_check()
    if sys.argv[1:2] == ["--hardware-series"]:
        paths = [Path(value) for value in sys.argv[2:]]
        if len(paths) < 2:
            raise DiagnosticError(
                "usage: analyze_diagnostic.py --hardware-series diagnostic-1.json "
                "diagnostic-2.json [...]"
            )
        resolved_paths = [path.resolve() for path in paths]
        require(len(set(resolved_paths)) == len(resolved_paths),
                "hardware series repeats an evidence path")
        documents = []
        for path in paths:
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise DiagnosticError(f"could not read {path}: {error}") from error
            require(isinstance(document, dict), f"diagnostic root is not an object: {path}")
            documents.append(document)
        result = validate_hardware_series(documents)
        print(
            "P0IJ_INTERACTION_STRESS_HARDWARE_SERIES_PASS "
            f"runs={result['runs']} steps={result['steps']} states={result['states']} "
            f"presents={result['presents']} hard_warnings=0 page_errors=0 "
            f"workspace_transitions={result['workspace_accepted']}/"
            f"{result['workspace_attempted']} exact_generation=1"
        )
        return 0
    if len(sys.argv) > 2:
        raise DiagnosticError(
            "usage: analyze_diagnostic.py [diagnostic.json|--self-check|"
            "--hardware-series diagnostic-1.json diagnostic-2.json [...]]"
        )
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
