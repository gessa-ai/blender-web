#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate ten exact Apple slow/sparse freeze diagnostics as one product series."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
PRODUCER = ROOT / "sandbox/p0-interaction-stress/rapid_freeze_repro.mjs"
REQUIRED_RUNS = 10
HARDWARE_TIMEOUT_MS = 12_000
MAX_CADENCE_DELAY_MS = 1_500
CADENCE_STEPS = (
    ("first-orbit", "orbit-before-click"),
    ("selection-click", "isolated-selection-pending"),
    ("navigation-orbit", "isolated-selection-navigation-passthrough"),
    ("transform-motion", "isolated-transform-pending"),
    ("transform-confirm", "isolated-transform-confirmed"),
)
SAFE_RUN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PRODUCT_FILES = {
    "blender_browser.js",
    "blender_browser.wasm",
    "blender_browser.wasm.orig",
    "blender_browser.data",
    "blender_browser.split-build.json",
}
REQUIRED_STACK = {
    "platform": "darwin",
    "nodeVersion": "v22.16.0",
    "playwrightVersion": "1.61.1",
    "pngjsVersion": "7.0.0",
    "chromiumVersion": "149.0.7827.55",
}
REQUIRED_STEPS = {
    "splash-dismissed",
    "front",
    "right",
    "top",
    "camera",
    "camera-orbit-cancelled",
    "select-all",
    "deselect-all",
    "orbit-before-click",
    "isolated-selection-pending",
    "isolated-selection-navigation-passthrough",
    "isolated-transform-pending",
    "isolated-transform-confirmed",
    "isolated-selection-drain",
    "isolated-post-drain-recovery-orbit",
}


class SparseSeriesError(RuntimeError):
    """One focused diagnostic or its same-generation series is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SparseSeriesError(message)


def numeric_vector(value: object, size: int) -> list[float] | None:
    if not isinstance(value, list) or len(value) != size:
        return None
    if not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
        return None
    return [float(item) for item in value]


def vector_changed(left: object, right: object, size: int) -> bool:
    lhs = numeric_vector(left, size)
    rhs = numeric_vector(right, size)
    return lhs is not None and rhs is not None and any(
        abs(a - b) > 0.00001 for a, b in zip(lhs, rhs, strict=True)
    )


def vector_equal(left: object, right: object, size: int) -> bool:
    lhs = numeric_vector(left, size)
    rhs = numeric_vector(right, size)
    return lhs is not None and rhs is not None and all(
        abs(a - b) <= 0.00001 for a, b in zip(lhs, rhs, strict=True)
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def expected_source() -> dict[str, str]:
    return {
        "path": "sandbox/p0-interaction-stress/rapid_freeze_repro.mjs",
        "sha256": sha256_file(PRODUCER),
    }


def validate_generation(value: object, label: str) -> dict[str, object]:
    require(isinstance(value, dict), f"{label} is absent")
    expected_fields = {
        "mode", "originalWasmSha256", "instrumentedWasmSha256", "javascriptSha256"
    }
    require(set(value) == expected_fields, f"{label} fields differ")
    require(value.get("mode") == "capture", f"{label} is not CAPTURE mode")
    for field in expected_fields - {"mode"}:
        require(isinstance(value.get(field), str) and SHA256.fullmatch(value[field]) is not None,
                f"{label} {field} is invalid")
    return value


def validate_product(value: object) -> dict[str, Any]:
    require(isinstance(value, dict), "product identity is absent")
    require(isinstance(value.get("binDir"), str) and Path(value["binDir"]).is_absolute(),
            "product binDir is not absolute")
    files = value.get("files")
    require(isinstance(files, dict) and set(files) == PRODUCT_FILES,
            "product file inventory differs")
    for name, identity in files.items():
        require(isinstance(identity, dict), f"product identity is invalid for {name}")
        require(type(identity.get("bytes")) is int and identity["bytes"] > 0,
                f"product byte size is invalid for {name}")
        require(isinstance(identity.get("sha256"), str) and
                SHA256.fullmatch(identity["sha256"]) is not None,
                f"product SHA-256 is invalid for {name}")
    generation = validate_generation(value.get("generation"), "local generation")
    served = validate_generation(value.get("servedGeneration"), "served generation")
    require(served == generation, "served and local CAPTURE generations differ")
    require(generation["originalWasmSha256"] ==
            files["blender_browser.wasm.orig"]["sha256"],
            "wasm.orig differs from the CAPTURE generation")
    require(generation["instrumentedWasmSha256"] == files["blender_browser.wasm"]["sha256"],
            "instrumented Wasm differs from the CAPTURE generation")
    require(generation["javascriptSha256"] == files["blender_browser.js"]["sha256"],
            "JavaScript differs from the CAPTURE generation")
    return value


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    require(document.get("schema") == 2, "focused diagnostic schema differs")
    run = document.get("run")
    require(isinstance(run, str) and SAFE_RUN.fullmatch(run) is not None,
            "focused diagnostic run label is invalid")
    require(is_timestamp(document.get("capturedAt")), "capture timestamp is invalid")
    require(document.get("source") == expected_source(), "producer identity differs")
    require(document.get("stack") == REQUIRED_STACK, "pinned Apple browser stack differs")
    require(document.get("mode") == "slow-sparse", "diagnostic is not slow/sparse")
    require(document.get("sampleCadenceMs") == 650, "slow/sparse cadence differs")
    require(document.get("evidenceClass") == "diagnostic-apple",
            "diagnostic is not Apple hardware evidence")

    adapter = document.get("adapter")
    require(isinstance(adapter, dict), "adapter evidence is absent")
    require(adapter.get("status") == "ACCEPTED" and
            adapter.get("reason") == "accepted-hardware" and
            adapter.get("present") is True and
            adapter.get("isFallbackAdapter") is False and
            adapter.get("softwareMatches") == [], "adapter is not accepted hardware")
    info = adapter.get("info")
    require(isinstance(info, dict) and isinstance(info.get("vendor"), str) and
            bool(info["vendor"].strip()) and isinstance(info.get("architecture"), str) and
            bool(info["architecture"].strip()), "adapter identity is incomplete")
    product = validate_product(document.get("productIdentity"))

    contract = document.get("nativeStateContract")
    require(isinstance(contract, dict), "native-state contract is absent")
    for field in (
        "enforced", "selectionEnforced", "actionComplete", "selectionComplete",
        "recoveryComplete", "navigationPassedThrough",
    ):
        require(contract.get(field) is True, f"native-state contract failed: {field}")
    require(document.get("selectionNavigationPassthroughRequired") is True,
            "run did not exercise navigation through a pending selection")
    require(document.get("selectionNavigationPassedThrough") is True,
            "pending selection blocked the isolated navigation gesture")

    point = document.get("selectionPoint")
    require(isinstance(point, dict) and all(
        isinstance(point.get(axis), (int, float)) and not isinstance(point.get(axis), bool)
        for axis in ("x", "y")
    ), "projected Cube selection point is invalid")
    for field in ("actionDrainMs", "selectionDrainMs", "recoveryOrbitMs"):
        value = document.get(field)
        require(isinstance(value, (int, float)) and not isinstance(value, bool) and
                0 <= value <= HARDWARE_TIMEOUT_MS, f"{field} exceeded the hardware bound")
    cadence = document.get("sparseCadenceTimeline")
    require(isinstance(cadence, list) and len(cadence) == len(CADENCE_STEPS),
            "fixed-cadence action timeline is incomplete")
    previous_sample_ms = -1
    for entry, (expected_action, expected_sample) in zip(cadence, CADENCE_STEPS, strict=True):
        require(isinstance(entry, dict) and set(entry) == {
            "action", "sample", "actionCompletedAtMs", "sampleStartedAtMs", "delayMs"
        }, "fixed-cadence timeline fields differ")
        require(entry.get("action") == expected_action and
                entry.get("sample") == expected_sample,
                "fixed-cadence action/sample order differs")
        action_ms = entry.get("actionCompletedAtMs")
        sample_ms = entry.get("sampleStartedAtMs")
        delay_ms = entry.get("delayMs")
        require(all(type(value) is int and value >= 0
                    for value in (action_ms, sample_ms, delay_ms)),
                "fixed-cadence timeline values are invalid")
        require(sample_ms - action_ms == delay_ms and
                document["sampleCadenceMs"] <= delay_ms <= MAX_CADENCE_DELAY_MS,
                "slow/sparse action did not preserve the fixed cadence")
        require(action_ms >= previous_sample_ms,
                "slow/sparse actions overlap or reorder their samples")
        previous_sample_ms = sample_ms
    require(document.get("actionDrainMs") == cadence[0]["delayMs"],
            "first-orbit timing is not bound to the fixed-cadence sample")
    for field in ("pageErrors", "lifecycle", "selectionReadbackFailureLines"):
        require(document.get(field) == [], f"{field} is not empty")

    steps = document.get("steps")
    require(isinstance(steps, list) and steps, "focused step evidence is absent")
    names = [step.get("name") for step in steps if isinstance(step, dict)]
    require(len(names) == len(steps) and len(set(names)) == len(names),
            "focused step names are invalid or duplicated")
    require(REQUIRED_STEPS.issubset(names), "focused slow/sparse step census is incomplete")
    for step in steps:
        require(isinstance(step.get("sha256"), str) and
                SHA256.fullmatch(step["sha256"]) is not None,
                f"focused step pixel SHA-256 is invalid: {step.get('name')}")
    by_name = {step["name"]: step for step in steps}
    deselected = by_name["deselect-all"]
    baseline = by_name["orbit-before-click"]
    navigation = by_name["isolated-selection-navigation-passthrough"]
    final = by_name["isolated-selection-drain"]
    recovery = by_name["isolated-post-drain-recovery-orbit"]
    require(baseline["sha256"] != deselected["sha256"],
            "first isolated orbit did not change pixels")
    require(navigation["sha256"] != baseline["sha256"],
            "pending-selection navigation did not change pixels")
    require(final["sha256"] != baseline["sha256"],
            "replayed transform tail did not change pixels")
    require(recovery["sha256"] != final["sha256"],
            "independent post-drain orbit did not change pixels")
    require(final.get("selectionDrawValidation", {}).get("pending") == 0,
            "selection validation remained pending after the drain")
    continuation = final.get("selectionContinuation")
    require(isinstance(continuation, dict) and continuation.get("active") == 0 and
            continuation.get("queuedEvents") == 0 and continuation.get("gpuFailures") == 0,
            "selection continuation did not retire cleanly")
    require(vector_changed(final.get("nativeState", {}).get("location"),
                           baseline.get("nativeState", {}).get("location"), 3),
            "queued G/motion/confirm tail did not move Cube")
    require(vector_changed(final.get("nativeState", {}).get("view_rotation"),
                           baseline.get("nativeState", {}).get("view_rotation"), 4),
            "pending-selection navigation did not change the native view")
    require(vector_changed(recovery.get("nativeState", {}).get("view_rotation"),
                           final.get("nativeState", {}).get("view_rotation"), 4),
            "independent post-drain orbit did not change the native view")
    require(vector_equal(recovery.get("nativeState", {}).get("location"),
                         final.get("nativeState", {}).get("location"), 3),
            "independent post-drain orbit unexpectedly changed Cube location")
    recovery_continuation = recovery.get("selectionContinuation")
    require(isinstance(recovery_continuation, dict) and
            recovery_continuation.get("active") == 0 and
            recovery_continuation.get("queuedEvents") == 0 and
            recovery_continuation.get("gpuFailures") == continuation.get("gpuFailures"),
            "selection continuation resumed during post-drain recovery")
    recovery_native = recovery.get("nativeState")
    require(isinstance(recovery_native, dict) and
            recovery_native.get("active_object") == "Cube" and
            recovery_native.get("selected_count") == 1,
            "independent post-drain orbit lost the selected Cube")
    final_rotate = final.get("view3dRotate")
    recovery_rotate = recovery.get("view3dRotate")
    require(isinstance(final_rotate, dict) and isinstance(recovery_rotate, dict) and
            all(type(final_rotate.get(field)) is int and
                type(recovery_rotate.get(field)) is int and
                recovery_rotate[field] >= final_rotate[field] + 1
                for field in ("invokes", "confirms", "terminals")) and
            recovery_rotate.get("cancels") == final_rotate.get("cancels") and
            recovery_rotate.get("active") == final_rotate.get("active") == 0,
            "independent post-drain VIEW3D_OT_rotate did not retire")
    input_contracts = {
        "ghostInput": (
            ("leftPresses", 2), ("leftReleases", 2),
            ("middlePresses", 1), ("middleReleases", 1),
            ("keyPresses", 1), ("keyReleases", 1),
        ),
        "wmInput": (
            ("wmLeftPresses", 2), ("wmLeftReleases", 2),
            ("wmMiddlePresses", 1), ("wmMiddleReleases", 1),
            ("wmKeyPresses", 1), ("wmKeyReleases", 1),
        ),
    }
    for input_field, counters in input_contracts.items():
        before = baseline.get(input_field)
        after = final.get(input_field)
        require(isinstance(before, dict) and isinstance(after, dict),
                f"{input_field} evidence is absent")
        for counter, delta in counters:
            require(type(before.get(counter)) is int and type(after.get(counter)) is int and
                    after[counter] >= before[counter] + delta,
                    f"{input_field} {counter} missed the complete slow/sparse tail")
        recovery_after = recovery.get(input_field)
        press = "middlePresses" if input_field == "ghostInput" else "wmMiddlePresses"
        release = "middleReleases" if input_field == "ghostInput" else "wmMiddleReleases"
        require(isinstance(recovery_after, dict) and
                type(after.get(press)) is int and type(recovery_after.get(press)) is int and
                type(after.get(release)) is int and type(recovery_after.get(release)) is int and
                recovery_after[press] >= after[press] + 1 and
                recovery_after[release] >= after[release] + 1,
                f"{input_field} missed the independent post-drain orbit")
    final_redraw = final.get("inputRedraw")
    recovery_redraw = recovery.get("inputRedraw")
    require(isinstance(final_redraw, dict) and isinstance(recovery_redraw, dict) and
            type(final_redraw.get("terminal")) is int and
            type(recovery_redraw.get("terminal")) is int and
            recovery_redraw["terminal"] > final_redraw["terminal"] and
            all(type(recovery_redraw.get(field)) is int and
                recovery_redraw[field] >= recovery_redraw["terminal"]
                for field in ("admitted", "dispatched", "presented", "contentPresented")) and
            recovery_redraw.get("episode") == final_redraw.get("episode"),
            "post-drain orbit lacks same-episode input presentation evidence")
    require(type(final.get("ticks")) is int and type(recovery.get("ticks")) is int and
            type(final.get("presents")) is int and type(recovery.get("presents")) is int and
            recovery["ticks"] > final["ticks"] and recovery["presents"] > final["presents"],
            "post-drain orbit did not advance WM and presentation")
    navigation_continuation = navigation.get("selectionContinuation")
    require(isinstance(navigation_continuation, dict) and
            navigation_continuation.get("active") == 1 and
            type(navigation_continuation.get("replayedEvents")) is int and
            type(continuation.get("replayedEvents")) is int and
            continuation["replayedEvents"] > navigation_continuation["replayedEvents"],
            "pending selection did not retain and replay the transform tail")
    timelines = document.get("drainTimelines")
    require(isinstance(timelines, dict) and
            all(isinstance(timelines.get(name), list) and timelines[name]
                for name in (
                    "isolated-selection-drain",
                    "isolated-post-drain-recovery-orbit",
                )),
            "bounded drain timelines are incomplete")
    return {
        "run": run,
        "product": product,
        "passthrough": int(document["selectionNavigationPassthroughRequired"]),
    }


def validate_series(documents: list[dict[str, Any]]) -> dict[str, Any]:
    require(len(documents) == REQUIRED_RUNS,
            f"slow/sparse hardware series requires exactly {REQUIRED_RUNS} runs")
    results = [validate_document(document) for document in documents]
    runs = [result["run"] for result in results]
    require(len(set(runs)) == REQUIRED_RUNS, "slow/sparse run labels are not unique")
    timestamps = [document["capturedAt"] for document in documents]
    require(len(set(timestamps)) == REQUIRED_RUNS, "slow/sparse timestamps are not unique")
    baseline = documents[0]
    for index, document in enumerate(documents[1:], 2):
        for field in ("source", "stack", "adapter", "productIdentity"):
            require(document.get(field) == baseline.get(field),
                    f"slow/sparse run {index} {field} differs")
    return {
        "runs": REQUIRED_RUNS,
        "passthroughRuns": sum(result["passthrough"] for result in results),
        "wasmOrigSha256": results[0]["product"]["generation"]["originalWasmSha256"],
    }


def synthetic_document(index: int = 0) -> dict[str, Any]:
    hashes = {name: hashlib.sha256(name.encode()).hexdigest() for name in PRODUCT_FILES}
    generation = {
        "mode": "capture",
        "originalWasmSha256": hashes["blender_browser.wasm.orig"],
        "instrumentedWasmSha256": hashes["blender_browser.wasm"],
        "javascriptSha256": hashes["blender_browser.js"],
    }
    base_step = {
        "sha256": hashlib.sha256(b"pixels").hexdigest(),
        "ticks": 10,
        "presents": 10,
        "selectionDrawValidation": {"pending": 0, "failures": 0},
        "selectionContinuation": {
            "active": 0, "queuedEvents": 0, "gpuFailures": 0, "replayedEvents": 0,
        },
        "view3dRotate": {
            "invokes": 0, "confirms": 0, "cancels": 0, "terminals": 0, "active": 0,
        },
        "nativeState": {
            "active_object": "Cube", "selected_count": 1,
            "location": [0.0, 0.0, 0.0], "view_rotation": [1.0, 0.0, 0.0, 0.0],
        },
        "inputRedraw": {
            "terminal": 0, "admitted": 0, "dispatched": 0,
            "presented": 0, "contentPresented": 0, "episode": 1,
        },
        "ghostInput": {
            "leftPresses": 0, "leftReleases": 0, "middlePresses": 0,
            "middleReleases": 0, "keyPresses": 0, "keyReleases": 0,
        },
        "wmInput": {
            "wmLeftPresses": 0, "wmLeftReleases": 0, "wmMiddlePresses": 0,
            "wmMiddleReleases": 0, "wmKeyPresses": 0, "wmKeyReleases": 0,
        },
    }
    steps = [copy.deepcopy(dict(
        base_step,
        name=name,
        sha256=hashlib.sha256(f"pixels-{name}".encode()).hexdigest(),
    )) for name in sorted(REQUIRED_STEPS)]
    by_name = {step["name"]: step for step in steps}
    by_name["isolated-selection-navigation-passthrough"]["selectionContinuation"].update(
        {"active": 1, "replayedEvents": 0}
    )
    final = by_name["isolated-selection-drain"]
    final["selectionContinuation"]["replayedEvents"] = 5
    final["view3dRotate"].update({"invokes": 2, "confirms": 2, "terminals": 2})
    final["nativeState"] = {
        "active_object": "Cube", "selected_count": 1,
        "location": [1.0, 0.0, 0.0], "view_rotation": [0.9, 0.1, 0.0, 0.0],
    }
    final["inputRedraw"].update({
        "terminal": 10, "admitted": 10, "dispatched": 10,
        "presented": 10, "contentPresented": 10,
    })
    final["ghostInput"].update({
        "leftPresses": 2, "leftReleases": 2, "middlePresses": 1,
        "middleReleases": 1, "keyPresses": 1, "keyReleases": 1,
    })
    final["wmInput"].update({
        "wmLeftPresses": 2, "wmLeftReleases": 2, "wmMiddlePresses": 1,
        "wmMiddleReleases": 1, "wmKeyPresses": 1, "wmKeyReleases": 1,
    })
    recovery = by_name["isolated-post-drain-recovery-orbit"]
    recovery["ticks"] = 11
    recovery["presents"] = 11
    recovery["selectionContinuation"]["replayedEvents"] = 5
    recovery["view3dRotate"].update({"invokes": 3, "confirms": 3, "terminals": 3})
    recovery["nativeState"] = {
        "active_object": "Cube", "selected_count": 1,
        "location": [1.0, 0.0, 0.0], "view_rotation": [0.8, 0.2, 0.0, 0.0],
    }
    recovery["inputRedraw"].update({
        "terminal": 11, "admitted": 11, "dispatched": 11,
        "presented": 11, "contentPresented": 11,
    })
    recovery["ghostInput"].update({
        "leftPresses": 2, "leftReleases": 2, "middlePresses": 2,
        "middleReleases": 2, "keyPresses": 1, "keyReleases": 1,
    })
    recovery["wmInput"].update({
        "wmLeftPresses": 2, "wmLeftReleases": 2, "wmMiddlePresses": 2,
        "wmMiddleReleases": 2, "wmKeyPresses": 1, "wmKeyReleases": 1,
    })
    timestamp = datetime(2026, 8, 29, tzinfo=timezone.utc) + timedelta(seconds=index)
    return {
        "schema": 2,
        "run": f"mac-sparse-{index:02d}",
        "capturedAt": timestamp.isoformat().replace("+00:00", "Z"),
        "source": expected_source(),
        "stack": dict(REQUIRED_STACK),
        "productIdentity": {
            "binDir": "/tmp/blender-web/bin",
            "files": {name: {"bytes": 1, "sha256": digest} for name, digest in hashes.items()},
            "generation": generation,
            "servedGeneration": dict(generation),
        },
        "mode": "slow-sparse",
        "sampleCadenceMs": 650,
        "evidenceClass": "diagnostic-apple",
        "adapter": {
            "status": "ACCEPTED", "reason": "accepted-hardware", "present": True,
            "isFallbackAdapter": False, "softwareMatches": [],
            "info": {"vendor": "apple", "architecture": "metal-3"},
        },
        "steps": steps,
        "selectionPoint": {"x": 512.0, "y": 360.0},
        "selectionNavigationPassthroughRequired": True,
        "selectionNavigationPassedThrough": True,
        "actionDrainMs": 650,
        "selectionDrainMs": 1500,
        "recoveryOrbitMs": 1500,
        "sparseCadenceTimeline": [
            {
                "action": action,
                "sample": sample,
                "actionCompletedAtMs": offset,
                "sampleStartedAtMs": offset + 650,
                "delayMs": 650,
            }
            for offset, (action, sample) in zip(
                (0, 800, 1600, 2400, 3200), CADENCE_STEPS, strict=True)
        ],
        "nativeStateContract": {
            "enforced": True, "selectionEnforced": True, "actionComplete": True,
            "selectionComplete": True, "recoveryComplete": True,
            "navigationPassedThrough": True,
        },
        "drainTimelines": {
            "isolated-selection-drain": [{"elapsedMs": 250}],
            "isolated-post-drain-recovery-orbit": [{"elapsedMs": 250}],
        },
        "pageErrors": [], "lifecycle": [], "selectionReadbackFailureLines": [],
    }


def self_check() -> None:
    documents = [synthetic_document(index) for index in range(REQUIRED_RUNS)]
    validate_document(documents[0])
    result = validate_series(documents)
    require(result["passthroughRuns"] == REQUIRED_RUNS,
            "positive series lost the navigation-passthrough census")
    mutations: list[Callable[[list[dict[str, Any]]], None]] = [
        lambda docs: docs.pop(),
        lambda docs: docs.__setitem__(1, copy.deepcopy(docs[0])),
        lambda docs: docs[1].__setitem__("capturedAt", docs[0]["capturedAt"]),
        lambda docs: docs[0].__setitem__("schema", 1),
        lambda docs: docs[0].__setitem__("mode", "rapid-burst"),
        lambda docs: docs[0].__setitem__("sampleCadenceMs", 350),
        lambda docs: docs[0].__setitem__("evidenceClass", "diagnostic-software-fallback"),
        lambda docs: docs[0]["stack"].__setitem__("chromiumVersion", "149.0.0.0"),
        lambda docs: docs[0]["source"].__setitem__("sha256", "0" * 64),
        lambda docs: docs[0]["adapter"].__setitem__("isFallbackAdapter", True),
        lambda docs: docs[0]["productIdentity"]["servedGeneration"].__setitem__(
            "originalWasmSha256", "0" * 64),
        lambda docs: docs[1]["productIdentity"]["files"]["blender_browser.data"].__setitem__(
            "sha256", "0" * 64),
        lambda docs: docs[0]["nativeStateContract"].__setitem__("recoveryComplete", False),
        lambda docs: docs[0].__setitem__("selectionNavigationPassthroughRequired", False),
        lambda docs: docs[0].__setitem__("selectionNavigationPassedThrough", False),
        lambda docs: docs[0].__setitem__("selectionDrainMs", HARDWARE_TIMEOUT_MS + 1),
        lambda docs: docs[0]["steps"].pop(),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-selection-drain")[
                              "selectionDrawValidation"].__setitem__("pending", 1),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-selection-drain")["nativeState"].__setitem__(
                              "location", [0.0, 0.0, 0.0]),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-selection-drain")["ghostInput"].__setitem__(
                              "keyPresses", 0),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-selection-drain")[
                              "selectionContinuation"].__setitem__("replayedEvents", 0),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "orbit-before-click").__setitem__(
                              "sha256", next(step for step in docs[0]["steps"]
                                             if step["name"] == "deselect-all")["sha256"]),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-selection-navigation-passthrough").__setitem__(
                              "sha256", next(step for step in docs[0]["steps"]
                                             if step["name"] == "orbit-before-click")["sha256"]),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-selection-drain").__setitem__(
                              "sha256", next(step for step in docs[0]["steps"]
                                             if step["name"] == "orbit-before-click")["sha256"]),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-post-drain-recovery-orbit").__setitem__(
                              "sha256", next(step for step in docs[0]["steps"]
                                             if step["name"] == "isolated-selection-drain")["sha256"]),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-post-drain-recovery-orbit")[
                              "nativeState"].__setitem__(
                                  "view_rotation", next(step for step in docs[0]["steps"]
                                                        if step["name"] ==
                                                        "isolated-selection-drain")[
                                                            "nativeState"]["view_rotation"]),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-post-drain-recovery-orbit")[
                              "nativeState"].__setitem__("location", [2.0, 0.0, 0.0]),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-post-drain-recovery-orbit")[
                              "nativeState"].__setitem__("selected_count", 0),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-post-drain-recovery-orbit")[
                              "view3dRotate"].__setitem__("terminals", 2),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-post-drain-recovery-orbit")[
                              "selectionContinuation"].__setitem__("active", 1),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-post-drain-recovery-orbit")[
                              "ghostInput"].__setitem__("middleReleases", 1),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-post-drain-recovery-orbit")[
                              "wmInput"].__setitem__("wmMiddlePresses", 1),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-post-drain-recovery-orbit")[
                              "inputRedraw"].__setitem__("contentPresented", 10),
        lambda docs: next(step for step in docs[0]["steps"]
                          if step["name"] == "isolated-post-drain-recovery-orbit").__setitem__(
                              "ticks", 10),
        lambda docs: docs[0].__setitem__("selectionReadbackFailureLines", ["failed"]),
        lambda docs: docs[0]["sparseCadenceTimeline"].pop(),
        lambda docs: docs[0]["sparseCadenceTimeline"][0].__setitem__(
            "delayMs", MAX_CADENCE_DELAY_MS + 1),
        lambda docs: docs[0]["sparseCadenceTimeline"][1].__setitem__(
            "action", "selection-drain"),
        lambda docs: docs[0]["sparseCadenceTimeline"][2].__setitem__(
            "sample", "isolated-selection-drain"),
        lambda docs: docs[0]["sparseCadenceTimeline"][3].__setitem__(
            "actionCompletedAtMs", 0),
        lambda docs: docs[0]["drainTimelines"].__setitem__(
            "isolated-selection-drain", []),
        lambda docs: docs[0]["drainTimelines"].__setitem__(
            "isolated-post-drain-recovery-orbit", []),
    ]
    rejected = 0
    accepted_mutations = []
    for index, mutate in enumerate(mutations):
        candidates = copy.deepcopy(documents)
        mutate(candidates)
        try:
            validate_series(candidates)
        except SparseSeriesError:
            rejected += 1
        else:
            accepted_mutations.append(index)
    require(rejected == len(mutations),
            f"series mutation self-check rejected {rejected}/{len(mutations)}; "
            f"accepted={accepted_mutations}")
    print(f"P0J_SPARSE_HARDWARE_SERIES_SELFCHECK_PASS positive=2 negative={rejected}")


def load_document(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"evidence is not a direct file: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SparseSeriesError(f"could not read evidence {path}: {error}") from error
    require(isinstance(document, dict), f"evidence root is not an object: {path}")
    return document


def main() -> int:
    if sys.argv[1:] == ["--self-check"]:
        self_check()
        return 0
    paths = [Path(value).expanduser().resolve() for value in sys.argv[1:]]
    require(len(paths) == REQUIRED_RUNS,
            f"usage: {Path(sys.argv[0]).name} <10 slow-sparse diagnostic JSON files>")
    require(len(set(paths)) == REQUIRED_RUNS, "slow/sparse evidence paths are duplicated")
    documents = [load_document(path) for path in paths]
    for path, document in zip(paths, documents, strict=True):
        require(path.stem == document.get("run"),
                f"evidence filename differs from its immutable run label: {path}")
    result = validate_series(documents)
    print(
        "P0J_SPARSE_HARDWARE_SERIES_PASS "
        f"runs={result['runs']} passthrough_runs={result['passthroughRuns']} "
        f"wasm_orig={result['wasmOrigSha256']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SparseSeriesError as error:
        print(f"P0J_SPARSE_HARDWARE_SERIES_FAIL {error}")
        raise SystemExit(1)
