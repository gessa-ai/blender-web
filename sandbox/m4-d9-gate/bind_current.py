#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Create one immutable M4 binding from two artifact-bound browser receipts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "sandbox/m4-d9-gate/evidence"
COMPARATOR = ROOT / "sandbox/m4-golden-prep/compare_m4.sh"
GOLDENS = ROOT / "sandbox/m4-golden-prep/goldens"
BIN_DIR = Path(os.environ.get("BLENDER_WEB_BIN", ROOT / "build-wasm-windowed-opt/bin")).resolve()
DEFERRED_WASM_FILENAME = os.environ.get(
    "BW_DEFERRED_WASM_FILENAME", "blender_browser.deferred.wasm"
)
if (not re.fullmatch(r"blender_browser(?:\.[A-Za-z0-9_-]+)*\.wasm", DEFERRED_WASM_FILENAME)
        or DEFERRED_WASM_FILENAME in {"blender_browser.wasm", "blender_browser.wasm.orig"}):
    raise SystemExit(f"M4_BIND_FAIL unsafe deferred Wasm filename: {DEFERRED_WASM_FILENAME!r}")
ARTIFACTS = {
    "javascript": BIN_DIR / "blender_browser.js",
    "wasm": BIN_DIR / "blender_browser.wasm",
    "deferred": BIN_DIR / DEFERRED_WASM_FILENAME,
    "preload": BIN_DIR / "blender_browser.data",
}
SHELL = {
    "index": ROOT / "platform_web/shell/index.html",
    "windowed": ROOT / "platform_web/shell/windowed.html",
    "diagnostics": ROOT / "platform_web/shell/diagnostics-bootstrap.js",
    "boot": ROOT / "platform_web/shell/boot-windowed.js",
    "fileBridge": ROOT / "platform_web/shell/file-bridge.js",
    "preinit": ROOT / "platform_web/shell/wgpu-preinit-worker.js",
}
ARTIFACT_BINDING_KEYS = {
    "javascript": "javascript",
    "wasm": "webAssembly",
    "deferred": "deferredWebAssembly",
    "preload": "preloadedData",
}
SOURCES = {
    "capture": ROOT / "sandbox/m4-d9-gate/capture_m4.mjs",
    "binder": ROOT / "sandbox/m4-d9-gate/bind_current.py",
    "verifier": ROOT / "sandbox/m4-d9-gate/verify_current_binding.py",
    "comparator": ROOT / "sandbox/m4-golden-prep/compare_m4.sh",
}
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
COMPARATOR_RE = re.compile(
    r"^PASS (?P<mode>splash|workspace)_1280x720\s+"
    r"Max error\s+=\s+(?P<max>[0-9.eE+-]+) over: "
    r"(?P<pixels>[0-9]+) pixels \((?P<percent>[0-9.]+)%\) over 0\.016$"
)
CC0 = "SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n"


def fail(message: str) -> None:
    raise SystemExit(f"M4_BIND_FAIL {message}")


def digest(path: Path) -> str:
    if not path.is_file():
        fail(f"missing file: {path}")
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_receipts() -> dict[str, dict[str, object]]:
    return {
        key: {"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}
        for key, path in ARTIFACTS.items()
    }


def verify_receipt_artifacts(receipt: dict, expected: dict, mode: str) -> None:
    actual = receipt.get("shippingBinary")
    if not isinstance(actual, dict) or set(actual) != set(ARTIFACTS):
        fail(f"{mode} receipt artifact set is not exact")
    for key, expected_item in expected.items():
        item = actual.get(key)
        if not isinstance(item, dict):
            fail(f"{mode} receipt missing {key} artifact")
        if Path(str(item.get("path", ""))).resolve() != ARTIFACTS[key]:
            fail(f"{mode} receipt {key} path mismatch")
        if item.get("bytes") != expected_item["bytes"] or item.get("sha256") != expected_item["sha256"]:
            fail(f"{mode} receipt {key} is stale")


def verify_browser_receipt(receipt: dict, run: str, mode: str, image: Path) -> None:
    if receipt.get("mode") != mode or receipt.get("label") != run:
        fail(f"{mode} receipt identity mismatch")
    if Path(str(receipt.get("output", ""))).resolve() != image.resolve():
        fail(f"{mode} receipt image path mismatch")
    if receipt.get("sha256") != digest(image):
        fail(f"{mode} receipt image hash mismatch")
    if receipt.get("pageCrashed") or receipt.get("runError") is not None:
        fail(f"{mode} browser failure recorded")
    if receipt.get("blockingErrors") != [] or receipt.get("presentCount", 0) < 1:
        fail(f"{mode} GPU/present receipt failed")
    if receipt.get("settleMs") != 60000 or receipt.get("deviceScaleFactor") != 1:
        fail(f"{mode} settle/DPR receipt changed")
    if receipt.get("gateReceipt") != {
        "backingWidth": 1280,
        "backingHeight": 720,
        "cssWidth": 1280,
        "cssHeight": 720,
        "dpr": 1,
        "gateClass": True,
    }:
        fail(f"{mode} exact gate receipt failed")
    capture_source = receipt.get("sources", {}).get("capture")
    if not isinstance(capture_source, dict):
        fail(f"{mode} capture source receipt missing")
    capture_path = SOURCES["capture"]
    if (Path(str(capture_source.get("path", ""))).resolve() != capture_path
            or capture_source.get("bytes") != capture_path.stat().st_size
            or capture_source.get("sha256") != digest(capture_path)):
        fail(f"{mode} capture source receipt is stale")
    served = receipt.get("servedShell")
    expected = receipt.get("expectedServedShell")
    if not isinstance(served, dict) or set(served) != set(SHELL):
        fail(f"{mode} served-shell receipt set is not exact")
    if not isinstance(expected, dict) or set(expected) != set(SHELL):
        fail(f"{mode} local shell receipt set is not exact")
    for key, path in SHELL.items():
        local = {"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}
        if expected.get(key) != local:
            fail(f"{mode} local shell receipt is stale: {key}")
        item = served.get(key)
        expected_url = {"index": "/index.html", "windowed": "/windowed.html",
                        "diagnostics": "/diagnostics-bootstrap.js",
                        "boot": "/boot-windowed.js", "fileBridge": "/file-bridge.js",
                        "preinit": "/wgpu-preinit-worker.js"}[key]
        if (not isinstance(item, dict) or not str(item.get("url", "")).endswith(expected_url)
                or item.get("bytes") != local["bytes"] or item.get("sha256") != local["sha256"]):
            fail(f"{mode} served shell is not the exact local file: {key}")


def comparator_metrics(image: Path, mode: str) -> dict[str, object]:
    result = subprocess.run(
        ["bash", str(COMPARATOR), str(image), mode, "1280x720"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    output = (result.stdout + result.stderr).strip()
    match = COMPARATOR_RE.fullmatch(output)
    if result.returncode != 0 or match is None:
        fail(f"live comparator failed for {mode}: rc={result.returncode} {output}")
    return {
        "maxError": float(match.group("max")),
        "pixelsOverThreshold": int(match.group("pixels")),
        "percentOverThreshold": float(match.group("percent")),
        "verdict": "PASS",
    }


def selfcheck() -> None:
    sample = "PASS splash_1280x720  Max error  = 0.5 over: 12 pixels (0.125%) over 0.016"
    match = COMPARATOR_RE.fullmatch(sample)
    if not match or match.group("mode") != "splash" or float(match.group("percent")) != 0.125:
        fail("comparator parser self-check")
    if set(ARTIFACTS) != {"javascript", "wasm", "deferred", "preload"}:
        fail("artifact set self-check")
    if set(SHELL) != {"index", "windowed", "diagnostics", "boot", "fileBridge", "preinit"}:
        fail("shell set self-check")
    print("M4_BIND_SELFCHECK_PASS immutable=1 artifacts=javascript,wasm,deferred,preload shell=index,windowed,diagnostics,boot,fileBridge,preinit modes=splash,workspace")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=False)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    if args.selfcheck:
        selfcheck()
        return
    run = (args.run or "").strip()
    if not LABEL_RE.fullmatch(run):
        fail("--run must be a safe non-empty immutable label")

    output = EVIDENCE / f"{run}.binding.json"
    license_path = Path(f"{output}.license")
    for path in (output, license_path):
        if path.exists():
            fail(f"refusing to overwrite existing binding: {path.relative_to(ROOT)}")

    current_artifacts = artifact_receipts()
    captures: dict[str, dict[str, object]] = {}
    for mode in ("splash", "workspace"):
        stem = f"{run}-{mode}_1280x720"
        image = EVIDENCE / f"{stem}.png"
        receipt_path = EVIDENCE / f"{stem}.receipt.json"
        receipt = json.loads(receipt_path.read_text())
        verify_browser_receipt(receipt, run, mode, image)
        verify_receipt_artifacts(receipt, current_artifacts, mode)
        golden = GOLDENS / f"{mode}_1280x720.png"
        captures[mode] = {
            "image": str(image.relative_to(ROOT)),
            "imageSha256": digest(image),
            "receipt": str(receipt_path.relative_to(ROOT)),
            "receiptSha256": digest(receipt_path),
            "golden": str(golden.relative_to(ROOT)),
            "goldenSha256": digest(golden),
            **comparator_metrics(image, mode),
        }

    verification_artifacts = {
        ARTIFACT_BINDING_KEYS[key]: {
            "path": str(ARTIFACTS[key].relative_to(ROOT)),
            "bytes": item["bytes"],
            "sha256": item["sha256"],
        }
        for key, item in current_artifacts.items()
    }
    binding = {
        "schema": 3,
        "milestone": "M4_FIRST_PIXELS",
        "run": run,
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "browserMode": "headed bundled Chromium",
        "gate": {
            "width": 1280,
            "height": 720,
            "deviceScaleFactor": 1,
            "settleMs": 60000,
            "failThreshold": 0.016,
            "failPercent": 1.0,
        },
        "verificationArtifacts": verification_artifacts,
        "servedShell": {
            key: {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": digest(path),
            }
            for key, path in SHELL.items()
        },
        "verificationSources": {
            key: {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": digest(path),
            }
            for key, path in SOURCES.items()
        },
        "captures": captures,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as handle:
        json.dump(binding, handle, indent=2)
        handle.write("\n")
    with license_path.open("x") as handle:
        handle.write(CC0)
    print(f"M4_BIND_PASS run={run} binding={output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
