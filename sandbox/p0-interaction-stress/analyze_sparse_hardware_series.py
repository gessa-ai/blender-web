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
    "isolated-orbit-drain",
    "isolated-selection-pending",
    "isolated-selection-navigation-passthrough",
    "isolated-selection-drain",
}


class SparseSeriesError(RuntimeError):
    """One focused diagnostic or its same-generation series is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SparseSeriesError(message)


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
    final = next(step for step in steps if step["name"] == "isolated-selection-drain")
    require(final.get("selectionDrawValidation", {}).get("pending") == 0,
            "selection validation remained pending after the drain")
    continuation = final.get("selectionContinuation")
    require(isinstance(continuation, dict) and continuation.get("active") == 0 and
            continuation.get("queuedEvents") == 0 and continuation.get("gpuFailures") == 0,
            "selection continuation did not retire cleanly")
    timelines = document.get("drainTimelines")
    require(isinstance(timelines, dict) and
            all(isinstance(timelines.get(name), list) and timelines[name]
                for name in (
                    "isolated-orbit-drain",
                    "isolated-selection-navigation-passthrough",
                    "isolated-selection-drain",
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
        "selectionDrawValidation": {"pending": 0, "failures": 0},
        "selectionContinuation": {"active": 0, "queuedEvents": 0, "gpuFailures": 0},
    }
    steps = [dict(base_step, name=name) for name in sorted(REQUIRED_STEPS)]
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
        "actionDrainMs": 500,
        "selectionDrainMs": 1500,
        "recoveryOrbitMs": 1500,
        "nativeStateContract": {
            "enforced": True, "selectionEnforced": True, "actionComplete": True,
            "selectionComplete": True, "recoveryComplete": True,
            "navigationPassedThrough": True,
        },
        "drainTimelines": {
            "isolated-orbit-drain": [{"elapsedMs": 250}],
            "isolated-selection-navigation-passthrough": [{"elapsedMs": 250}],
            "isolated-selection-drain": [{"elapsedMs": 250}],
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
        lambda docs: docs[0]["steps"][-1]["selectionDrawValidation"].__setitem__("pending", 1),
        lambda docs: docs[0].__setitem__("selectionReadbackFailureLines", ["failed"]),
        lambda docs: docs[0]["drainTimelines"].__setitem__(
            "isolated-selection-navigation-passthrough", []),
    ]
    rejected = 0
    for mutate in mutations:
        candidates = copy.deepcopy(documents)
        mutate(candidates)
        try:
            validate_series(candidates)
        except SparseSeriesError:
            rejected += 1
    require(rejected == len(mutations),
            f"series mutation self-check rejected {rejected}/{len(mutations)}")
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
