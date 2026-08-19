#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fail-closed verifier for the current M4 first-pixels evidence binding."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "sandbox/m4-d9-gate/evidence"
DEFAULT_BINDING = EVIDENCE / "m4-current-r1.binding.json"
COMPARATOR_RE = re.compile(
    r"^PASS (?P<mode>splash|workspace)_1280x720\s+"
    r"Max error\s+=\s+(?P<max>[0-9.eE+-]+) over: "
    r"(?P<pixels>[0-9]+) pixels \((?P<percent>[0-9.]+)%\) over 0\.016$"
)
DEFERRED_WASM_FILENAME = os.environ.get(
    "BW_DEFERRED_WASM_FILENAME", "blender_browser.deferred.wasm"
)
if (not re.fullmatch(r"blender_browser(?:\.[A-Za-z0-9_-]+)*\.wasm", DEFERRED_WASM_FILENAME)
        or DEFERRED_WASM_FILENAME in {"blender_browser.wasm", "blender_browser.wasm.orig"}):
    raise SystemExit(
        f"M4_BINDING_FAIL unsafe deferred Wasm filename: {DEFERRED_WASM_FILENAME!r}"
    )


def selected_binding() -> pathlib.Path:
    text = os.environ.get("M4_BINDING")
    path = pathlib.Path(text) if text else DEFAULT_BINDING
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if path.parent != EVIDENCE.resolve() or not path.name.endswith(".binding.json"):
        fail(f"binding must be an immutable file directly under {EVIDENCE.relative_to(ROOT)}")
    return path


def fail(message: str) -> None:
    raise SystemExit(f"M4_BINDING_FAIL {message}")


def digest(path: pathlib.Path) -> str:
    if not path.is_file():
        fail(f"missing file: {path.relative_to(ROOT)}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_hashed_file(path_text: str, expected_sha: str, expected_bytes: int | None = None) -> None:
    path = ROOT / path_text
    actual_sha = digest(path)
    if actual_sha != expected_sha:
        fail(f"sha256 mismatch for {path_text}: {actual_sha} != {expected_sha}")
    if expected_bytes is not None and path.stat().st_size != expected_bytes:
        fail(f"size mismatch for {path_text}: {path.stat().st_size} != {expected_bytes}")


def verify_receipt_artifacts(receipt: dict, expected: dict, mode: str) -> None:
    shipping = receipt.get("shippingBinary")
    key_map = {
        "javascript": "javascript",
        "wasm": "webAssembly",
        "deferred": "deferredWebAssembly",
        "preload": "preloadedData",
    }
    if not isinstance(shipping, dict) or set(shipping) != set(key_map):
        fail(f"receipt artifact set mismatch for {mode}")
    for receipt_key, binding_key in key_map.items():
        actual = shipping.get(receipt_key)
        wanted = expected[binding_key]
        if not isinstance(actual, dict):
            fail(f"receipt missing {receipt_key} artifact for {mode}")
        actual_path = pathlib.Path(str(actual.get("path", ""))).resolve()
        wanted_path = (ROOT / wanted["path"]).resolve()
        if actual_path != wanted_path:
            fail(f"receipt {receipt_key} path mismatch for {mode}")
        if actual.get("sha256") != wanted["sha256"] or actual.get("bytes") != wanted["bytes"]:
            fail(f"receipt {receipt_key} binding mismatch for {mode}")


def parse_comparator(output: str, mode: str) -> dict[str, float | int | str]:
    match = COMPARATOR_RE.fullmatch(output)
    if match is None or match.group("mode") != mode:
        fail(f"unparseable comparator output for {mode}: {output}")
    return {
        "maxError": float(match.group("max")),
        "pixelsOverThreshold": int(match.group("pixels")),
        "percentOverThreshold": float(match.group("percent")),
        "verdict": "PASS",
    }


def main() -> None:
    if "--selfcheck" in sys.argv[1:]:
        parsed = parse_comparator(
            "PASS splash_1280x720  Max error  = 0.5 over: 12 pixels (0.125%) over 0.016",
            "splash",
        )
        if parsed["pixelsOverThreshold"] != 12 or parsed["percentOverThreshold"] != 0.125:
            fail("comparator parser self-check")
        print("M4_BINDING_SELFCHECK_PASS selector=M4_BINDING schema=3 artifacts+served-shell=receipt-bound")
        return

    binding_path = selected_binding()
    if not binding_path.is_file():
        fail(f"missing binding: {binding_path.relative_to(ROOT)}")
    binding = json.loads(binding_path.read_text())
    if binding.get("schema") != 3 or binding.get("milestone") != "M4_FIRST_PIXELS":
        fail("unsupported binding schema or milestone")
    run = binding.get("run")
    if (not isinstance(run, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run)
            or binding_path.name != f"{run}.binding.json"):
        fail("binding filename/run identity mismatch")

    gate = binding.get("gate", {})
    expected_gate = {
        "width": 1280,
        "height": 720,
        "deviceScaleFactor": 1,
        "settleMs": 60000,
        "failThreshold": 0.016,
        "failPercent": 1.0,
    }
    if gate != expected_gate:
        fail(f"gate contract changed: {gate!r}")

    artifacts = binding.get("verificationArtifacts", {})
    if set(artifacts) != {
        "javascript", "webAssembly", "deferredWebAssembly", "preloadedData"
    }:
        fail("verification artifact set must be exact")
    expected_artifact_paths = {
        "javascript": "build-wasm-windowed-opt/bin/blender_browser.js",
        "webAssembly": "build-wasm-windowed-opt/bin/blender_browser.wasm",
        "deferredWebAssembly": f"build-wasm-windowed-opt/bin/{DEFERRED_WASM_FILENAME}",
        "preloadedData": "build-wasm-windowed-opt/bin/blender_browser.data",
    }
    for key, artifact in artifacts.items():
        if artifact.get("path") != expected_artifact_paths[key]:
            fail(f"verification artifact path changed for {key}: {artifact.get('path')}")
        verify_hashed_file(artifact["path"], artifact["sha256"], artifact["bytes"])

    shell = binding.get("servedShell", {})
    expected_shell_paths = {
        "index": "platform_web/shell/index.html",
        "windowed": "platform_web/shell/windowed.html",
        "diagnostics": "platform_web/shell/diagnostics-bootstrap.js",
        "boot": "platform_web/shell/boot-windowed.js",
        "fileBridge": "platform_web/shell/file-bridge.js",
        "preinit": "platform_web/shell/wgpu-preinit-worker.js",
    }
    if set(shell) != set(expected_shell_paths):
        fail("served-shell binding set must be exact")
    for key, item in shell.items():
        if item.get("path") != expected_shell_paths[key]:
            fail(f"served-shell path changed for {key}")
        verify_hashed_file(item["path"], item["sha256"], item["bytes"])

    sources = binding.get("verificationSources", {})
    expected_source_paths = {
        "capture": "sandbox/m4-d9-gate/capture_m4.mjs",
        "binder": "sandbox/m4-d9-gate/bind_current.py",
        "verifier": "sandbox/m4-d9-gate/verify_current_binding.py",
        "comparator": "sandbox/m4-golden-prep/compare_m4.sh",
    }
    if set(sources) != set(expected_source_paths):
        fail("verification source set must be exact")
    for key, source in sources.items():
        if source.get("path") != expected_source_paths[key]:
            fail(f"verification source path changed for {key}: {source.get('path')}")
        verify_hashed_file(source["path"], source["sha256"], source["bytes"])

    captures = binding.get("captures", {})
    if set(captures) != {"splash", "workspace"}:
        fail("capture set must be exactly splash and workspace")

    summaries: list[str] = []
    comparator = ROOT / "sandbox/m4-golden-prep/compare_m4.sh"
    for mode in ("splash", "workspace"):
        capture = captures[mode]
        if capture.get("verdict") != "PASS" or capture.get("percentOverThreshold", 101) > 1.0:
            fail(f"stored comparator disposition is not a strict pass for {mode}")
        verify_hashed_file(capture["image"], capture["imageSha256"])
        verify_hashed_file(capture["receipt"], capture["receiptSha256"])
        verify_hashed_file(capture["golden"], capture["goldenSha256"])

        expected_image = f"sandbox/m4-d9-gate/evidence/{run}-{mode}_1280x720.png"
        expected_receipt = f"sandbox/m4-d9-gate/evidence/{run}-{mode}_1280x720.receipt.json"
        expected_golden = f"sandbox/m4-golden-prep/goldens/{mode}_1280x720.png"
        if (capture.get("image") != expected_image or capture.get("receipt") != expected_receipt
                or capture.get("golden") != expected_golden):
            fail(f"capture path/run identity mismatch for {mode}")

        receipt = json.loads((ROOT / capture["receipt"]).read_text())
        if receipt.get("mode") != mode or receipt.get("label") != run:
            fail(f"receipt identity mismatch for {mode}")
        if receipt.get("sha256") != capture["imageSha256"]:
            fail(f"receipt image hash mismatch for {mode}")
        if receipt.get("pageCrashed") or receipt.get("runError") is not None:
            fail(f"browser failure recorded for {mode}")
        if receipt.get("blockingErrors") != [] or receipt.get("presentCount", 0) < 1:
            fail(f"GPU/page/present gate failed for {mode}")
        verify_receipt_artifacts(receipt, artifacts, mode)
        capture_source = receipt.get("sources", {}).get("capture")
        if capture_source != {
            "path": str((ROOT / sources["capture"]["path"]).resolve()),
            "bytes": sources["capture"]["bytes"],
            "sha256": sources["capture"]["sha256"],
        }:
            fail(f"capture source receipt mismatch for {mode}")
        served = receipt.get("servedShell")
        expected_local = receipt.get("expectedServedShell")
        if not isinstance(served, dict) or set(served) != set(shell):
            fail(f"served-shell receipt set mismatch for {mode}")
        if not isinstance(expected_local, dict) or set(expected_local) != set(shell):
            fail(f"local shell receipt set mismatch for {mode}")
        suffixes = {"index": "/index.html", "windowed": "/windowed.html",
                    "diagnostics": "/diagnostics-bootstrap.js",
                    "boot": "/boot-windowed.js", "fileBridge": "/file-bridge.js",
                    "preinit": "/wgpu-preinit-worker.js"}
        for key, item in shell.items():
            local = {"path": str((ROOT / item["path"]).resolve()),
                     "bytes": item["bytes"], "sha256": item["sha256"]}
            if expected_local.get(key) != local:
                fail(f"local shell receipt mismatch for {mode}/{key}")
            actual = served.get(key)
            if (not isinstance(actual, dict)
                    or not str(actual.get("url", "")).endswith(suffixes[key])
                    or actual.get("bytes") != item["bytes"]
                    or actual.get("sha256") != item["sha256"]):
                fail(f"served shell mismatch for {mode}/{key}")
        exact_gate = receipt.get("gateReceipt", {})
        if exact_gate != {
            "backingWidth": 1280,
            "backingHeight": 720,
            "cssWidth": 1280,
            "cssHeight": 720,
            "dpr": 1,
            "gateClass": True,
        }:
            fail(f"capture gate mismatch for {mode}: {exact_gate!r}")

        result = subprocess.run(
            ["bash", str(comparator), capture["image"], mode, "1280x720"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            fail(f"live comparator failed for {mode}: rc={result.returncode} {output}")
        live_metrics = parse_comparator(output, mode)
        stored_metrics = {key: capture.get(key) for key in live_metrics}
        if stored_metrics != live_metrics:
            fail(f"stored/live comparator metrics differ for {mode}: {stored_metrics} != {live_metrics}")
        summaries.append(output)

    print("M4_BINDING_PASS " + " | ".join(summaries))


if __name__ == "__main__":
    main()
