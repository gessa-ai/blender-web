#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Validate and summarize one P0-I modal-extrude WebGPU trace."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACE = ROOT / "sandbox/p0-modal-extrude/artifacts/diagnostic.json"


class TraceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TraceError(message)


def draw_vertex_count(item: dict[str, Any]) -> int | None:
    draws = item.get("draws") or []
    if not draws:
        return None
    args = draws[0].get("args") or []
    return int(args[0]) if args else None


def push_entry(item: dict[str, Any]) -> dict[str, Any] | None:
    for group in item.get("groups") or []:
        for entry in group or []:
            label = str((entry.get("buffer") or {}).get("label") or "")
            if "push-constant" in label:
                return entry
    return None


def immediate_resource_id(item: dict[str, Any]) -> int | None:
    for group in item.get("groups") or []:
        for entry in group or []:
            buffer = entry.get("buffer") or {}
            if buffer.get("label") == "immediate vertex buffer":
                return int(buffer["id"])
    return None


def analyze(data: dict[str, Any]) -> dict[str, int]:
    require(data.get("state") == "running", "windowed product did not remain running")
    require(not data.get("pageErrors"), "browser page errors were captured")

    states = data.get("states") or []
    object_before = next(
        (state for state in states if state.get("mode") == "OBJECT" and state.get("verts") == 8),
        None,
    )
    edit = next((state for state in states if state.get("mode") == "EDIT"), None)
    object_after = next(
        (state for state in states if state.get("mode") == "OBJECT" and state.get("verts", 0) > 8),
        None,
    )
    require(object_before is not None, "missing pre-extrude OBJECT/8 state")
    require(edit is not None, "missing EDIT state")
    require(object_after is not None, "missing confirmed post-extrude topology")
    view = edit.get("view") or {}
    view_width = int(view.get("width", 0))
    view_height = int(view.get("height", 0))
    require(view_width > 0 and view_height > 0, "invalid live VIEW_3D extent")

    warnings = data.get("relevantWarnings") or []
    require(
        not any("assembled group-0 resources do not match" in str(line) for line in warnings),
        "bind-group completeness warning occurred during the diagnostic",
    )

    submissions = [
        item
        for item in data.get("p0iTraces") or []
        if item.get("event") == "submit-pass"
    ]
    modal_phases = ("modal-extrude", "modal-move", "modal-rotate", "modal-scale")
    constraints_by_phase = {
        phase: [
            item
            for item in submissions
            if item.get("phase") == phase
            and item.get("kind") == "polyline"
            and draw_vertex_count(item) == 6
        ]
        for phase in modal_phases
    }
    for phase, items in constraints_by_phase.items():
        require(items, f"no constraint-line submission captured for {phase}")
    constraint = [item for phase in modal_phases for item in constraints_by_phase[phase]]

    resource_ids: set[int] = set()
    sequences: list[int] = []
    for item in constraint:
        attachment = (item.get("attachments") or [None])[0] or {}
        require(
            (attachment.get("width"), attachment.get("height"))
            == (view_width, view_height),
            "constraint-line attachment does not match live VIEW_3D extent",
        )
        viewport = item.get("viewport") or []
        require(
            len(viewport) >= 4
            and tuple(int(value) for value in viewport[:4])
            == (0, 0, view_width, view_height),
            "constraint-line viewport does not match live VIEW_3D extent",
        )
        push = push_entry(item)
        require(push is not None, "constraint-line push constants were not bound")
        floats = push.get("floats") or []
        require(len(floats) > 22, "constraint-line push constants were not captured")
        require(
            (int(floats[20]), int(floats[21])) == (view_width, view_height),
            "constraint-line push viewport is stale",
        )
        require(0.5 <= float(floats[22]) <= 3.0, "constraint-line width is not narrow")
        resource_id = immediate_resource_id(item)
        require(resource_id is not None, "constraint-line immediate resource is absent")
        resource_ids.add(resource_id)
        sequences.append(int(item.get("submitSequence", 0)))

    require(
        len(resource_ids) == len(constraint),
        "constraint-line submissions did not retain distinct immediate resources",
    )
    require(all(sequence > 0 for sequence in sequences), "submission sequence is absent")
    require(sequences == sorted(sequences), "constraint submission sequence is not monotonic")

    modal = [item for item in submissions if item.get("phase") in modal_phases]
    modal_shadows = [item for item in modal if item.get("kind") == "widget-shadow"]
    modal_presents = [item for item in modal if item.get("kind") == "surface-present"]
    presents_by_phase = {
        phase: len(
            [
                item
                for item in submissions
                if item.get("phase") == phase and item.get("kind") == "surface-present"
            ]
        )
        for phase in modal_phases
    }
    shadows_by_phase = {
        phase: len(
            [
                item
                for item in submissions
                if item.get("phase") == phase and item.get("kind") == "widget-shadow"
            ]
        )
        for phase in modal_phases
    }
    clusters_by_phase: dict[str, int] = {}
    for phase, items in constraints_by_phase.items():
        phase_sequences = [int(item["submitSequence"]) for item in items]
        clusters = 1
        for before, after in zip(phase_sequences, phase_sequences[1:]):
            if after - before > 40:
                clusters += 1
        clusters_by_phase[phase] = clusters

    settle = [item for item in submissions if item.get("phase") == "settle"]
    settle_widgets = [item for item in settle if item.get("kind") == "widget-base"]
    settle_composites = [item for item in settle if item.get("kind") == "image-rect"]
    surface_sequences = [
        int(item.get("submitSequence", 0))
        for item in submissions
        if item.get("kind") == "surface-present"
    ]
    require(settle_widgets, "post-confirm widget submissions were not captured")
    require(settle_composites, "post-confirm window composites were not captured")
    require(surface_sequences, "surface presentation was not captured")

    return {
        "constraint_submits": len(constraint),
        "extrude_clusters": clusters_by_phase["modal-extrude"],
        "move_clusters": clusters_by_phase["modal-move"],
        "rotate_clusters": clusters_by_phase["modal-rotate"],
        "scale_clusters": clusters_by_phase["modal-scale"],
        "extrude_presents": presents_by_phase["modal-extrude"],
        "move_presents": presents_by_phase["modal-move"],
        "rotate_presents": presents_by_phase["modal-rotate"],
        "scale_presents": presents_by_phase["modal-scale"],
        "extrude_shadows": shadows_by_phase["modal-extrude"],
        "modal_presents": len(modal_presents),
        "modal_shadows": len(modal_shadows),
        "settle_widgets": len(settle_widgets),
        "settle_composites": len(settle_composites),
        "surface_presents": len(surface_sequences),
    }


def synthetic_fixture() -> dict[str, Any]:
    push = {
        "buffer": {"id": 7, "label": "push-constant buffer creation"},
        "floats": [0.0] * 20 + [640.0, 480.0, 2.0],
    }
    traces: list[dict[str, Any]] = []
    sequence = 10
    resource = 101
    for phase in ("modal-extrude", "modal-move", "modal-rotate", "modal-scale"):
        for _ in range(3):
            traces.append(
                {
                    "event": "submit-pass",
                    "phase": phase,
                    "kind": "polyline",
                    "submitSequence": sequence,
                    "viewport": [0, 0, 640, 480, 0, 1],
                    "attachments": [{"width": 640, "height": 480}],
                    "draws": [{"args": [6, 1, 0, 0]}],
                    "groups": [
                        [push, {"buffer": {"id": resource, "label": "immediate vertex buffer"}}]
                    ],
                }
            )
            sequence += 1
            resource += 1
    traces.extend(
        [
            {"event": "submit-pass", "phase": "settle", "kind": "widget-base"},
            {"event": "submit-pass", "phase": "settle", "kind": "image-rect"},
            {"event": "submit-pass", "phase": "settle", "kind": "surface-present", "submitSequence": 20},
        ]
    )
    return {
        "state": "running",
        "pageErrors": [],
        "states": [
            {"mode": "OBJECT", "verts": 8},
            {"mode": "EDIT", "verts": 8, "view": {"width": 640, "height": 480}},
            {"mode": "OBJECT", "verts": 16},
        ],
        "relevantWarnings": [],
        "p0iTraces": traces,
    }


def self_check() -> None:
    fixture = synthetic_fixture()
    analyze(fixture)
    mutations = []
    broken = copy.deepcopy(fixture)
    broken["pageErrors"] = ["Error: synthetic"]
    mutations.append(broken)
    broken = copy.deepcopy(fixture)
    broken["states"] = broken["states"][:-1]
    mutations.append(broken)
    broken = copy.deepcopy(fixture)
    broken["relevantWarnings"] = ["assembled group-0 resources do not match"]
    mutations.append(broken)
    broken = copy.deepcopy(fixture)
    broken["p0iTraces"][0]["viewport"][2] = 639
    mutations.append(broken)
    broken = copy.deepcopy(fixture)
    broken["p0iTraces"][0]["groups"][0][0]["floats"][22] = 50.0
    mutations.append(broken)
    broken = copy.deepcopy(fixture)
    del broken["p0iTraces"][-1]
    mutations.append(broken)
    rejected = 0
    for mutation in mutations:
        try:
            analyze(mutation)
        except TraceError:
            rejected += 1
    require(rejected == len(mutations), "self-check accepted a negative mutation")
    print(f"P0I_MODAL_TRACE_SELFCHECK_PASS positive=1 negative={rejected}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", nargs="?", type=Path, default=DEFAULT_TRACE)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    summary = analyze(json.loads(args.trace.read_text(encoding="utf-8")))
    fields = " ".join(f"{key}={value}" for key, value in summary.items())
    print(f"P0I_MODAL_TRACE_PASS {fields}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, json.JSONDecodeError, TraceError) as error:
        raise SystemExit(f"P0I_MODAL_TRACE_FAIL {error}") from error
