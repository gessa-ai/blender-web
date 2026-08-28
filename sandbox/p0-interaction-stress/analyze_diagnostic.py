#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate the device-free P0-I cumulative-interaction diagnostic."""

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
    "10-after-orbit",
    "20-after-pan",
    "30-after-zoom",
    "61b-frame-selected-3s",
    "61c-frame-selected-6s",
    "63-final-orbit",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DiagnosticError(message)


def validate(document: dict[str, Any]) -> dict[str, int]:
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

    settled_3s = steps["61b-frame-selected-3s"]
    settled_6s = steps["61c-frame-selected-6s"]
    require(
        settled_3s.get("sha256") == settled_6s.get("sha256"),
        "Frame Selected pixels did not settle between three and six seconds",
    )
    require(
        steps["63-final-orbit"].get("sha256") != settled_6s.get("sha256"),
        "final orbit did not change pixels",
    )

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
    require(len(pointer_fallbacks) == 1, "pointer-lock rejection fallback was not exactly bounded once")

    return {
        "steps": len(steps_value),
        "states": len(document.get("states", [])),
        "presents": product["presents"],
        "workspace_accepted": workspace_accepted,
        "workspace_attempted": len(workspace_transitions),
    }


def synthetic_document() -> dict[str, Any]:
    steps = []
    for index, name in enumerate(REQUIRED_STEPS):
        steps.append(
            {
                "name": name,
                "sha256": "settled" if "frame-selected" in name else f"hash-{index}",
                "semanticPixels": {"quantizedColors": 256, "nonWhiteRatio": 0.9},
                "state": {
                    "workspace": "Modeling" if name == "01-preflight-modeling-click" else "Layout",
                    "cube_in_view": True,
                    "selected": True,
                    "view": {"width": 100, "height": 100},
                },
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
                    "workspace": workspace,
                    "cube_in_view": True,
                    "selected": True,
                    "view": {},
                },
            }
        )
    return {
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
    }


def self_check() -> int:
    baseline = synthetic_document()
    validate(baseline)
    mutations = (
        lambda value: value["product"].__setitem__("state", "error"),
        lambda value: value["hardCompletenessWarnings"].append("incomplete"),
        lambda value: value["pageErrors"].append("pageerror"),
        lambda value: value["steps"][1].__setitem__("workspaceAccepted", False),
        lambda value: value["steps"][0]["semanticPixels"].__setitem__("quantizedColors", 2),
        lambda value: value["steps"][0]["state"].__setitem__("cube_in_view", False),
        lambda value: value["steps"][6].__setitem__("sha256", "not-settled"),
        lambda value: value["steps"][7].__setitem__("sha256", "settled"),
        lambda value: value["relevantWarnings"].clear(),
        lambda value: value["steps"][8].__setitem__("workspaceAccepted", False),
        lambda value: value["steps"][8]["state"].__setitem__("workspace", "Layout"),
        lambda value: value["workspaceInputCanary"]["ghostPressX"].__setitem__(0, 288),
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
    print(f"P0I_INTERACTION_STRESS_SELFCHECK_PASS positive=1 negative={rejected}")
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
    print(
        "P0I_PENDING_GEOMETRY_BIND_RUNTIME_PASS "
        f"steps={result['steps']} states={result['states']} presents={result['presents']} "
        "hard_warnings=0 page_errors=0 "
        f"workspace_transitions={result['workspace_accepted']}/{result['workspace_attempted']} "
        "button_coords=dom-ghost-matched"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DiagnosticError as error:
        print(f"P0I_INTERACTION_STRESS_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
