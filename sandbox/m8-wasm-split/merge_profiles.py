#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail-closed union of compatible Binaryen in-memory split profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


ADAPTER_CONTRACT = "hardware-webgpu-adapter-v1"
NODE_VERSION = "v22.16.0"
PLAYWRIGHT_VERSION = "1.61.1"
PNGJS_VERSION = "7.0.0"
CHROMIUM_VERSION = "149.0.7827.55"
SOFTWARE_ADAPTER_TOKENS = (
    "swiftshader",
    "llvmpipe",
    "lavapipe",
    "softpipe",
    "software rasterizer",
    "microsoft basic render",
    "warp",
)
ADAPTER_FIELDS = {
    "contract",
    "status",
    "present",
    "platform",
    "powerPreference",
    "isFallbackAdapter",
    "info",
    "softwareMatches",
    "reason",
}
ADAPTER_INFO_FIELDS = {"vendor", "architecture", "device", "description"}


def identity(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"path": str(path.resolve()), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def resolve_receipt_path(value: str, receipt_path: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    # Capture receipts use repository-relative paths. Locate the repository by
    # walking up from this tool, not from the caller's ambient working directory.
    repo = Path(__file__).resolve().parents[2]
    return (repo / path).resolve()


def verify_capture_browser(capture: object, where: str) -> dict[str, object]:
    if not isinstance(capture, dict) or not isinstance(capture.get("browser"), dict):
        raise ValueError(f"{where}: capture browser proof absent")
    browser = capture["browser"]
    if (
        browser.get("nodeVersion") != NODE_VERSION
        or browser.get("playwrightVersion") != PLAYWRIGHT_VERSION
        or browser.get("pngjsVersion") != PNGJS_VERSION
        or browser.get("version") != CHROMIUM_VERSION
        or browser.get("headed") is not True
        or not isinstance(browser.get("playwrightRoot"), str)
        or not Path(browser["playwrightRoot"]).is_absolute()
    ):
        raise ValueError(f"{where}: capture browser tool identity mismatch")
    adapter = browser.get("adapter")
    if not isinstance(adapter, dict) or set(adapter) != ADAPTER_FIELDS:
        raise ValueError(f"{where}: hardware adapter proof fields mismatch")
    info = adapter.get("info")
    if (
        not isinstance(info, dict)
        or set(info) != ADAPTER_INFO_FIELDS
        or any(not isinstance(info[key], str) for key in ADAPTER_INFO_FIELDS)
    ):
        raise ValueError(f"{where}: hardware adapter info fields mismatch")
    platform = adapter.get("platform")
    expected_args = ["--enable-unsafe-webgpu"] + (["--use-angle=metal"] if platform == "darwin" else [])
    if platform not in {"darwin", "linux"} or browser.get("args") != expected_args:
        raise ValueError(f"{where}: platform browser arguments mismatch")
    identity = " ".join(info[key] for key in ("vendor", "architecture", "device", "description"))
    identity = identity.strip().lower()
    detail_identity = " ".join(info[key] for key in ("architecture", "device", "description")).strip()
    matches = [token for token in SOFTWARE_ADAPTER_TOKENS if token in identity]
    if re.search(r"(^|[^a-z0-9])cpu([^a-z0-9]|$)", identity):
        matches.append("cpu")
    fallback = adapter.get("isFallbackAdapter")
    if type(fallback) is not bool:
        raise ValueError(f"{where}: fallback adapter flag has wrong type")
    if (
        adapter.get("contract") != ADAPTER_CONTRACT
        or adapter.get("status") != "ACCEPTED"
        or adapter.get("present") is not True
        or adapter.get("powerPreference") != "high-performance"
        or fallback is not False
        or not identity
        or not detail_identity
        or matches
        or adapter.get("softwareMatches") != []
        or adapter.get("reason") != "accepted-hardware"
    ):
        raise ValueError(f"{where}: capture did not bind an accepted hardware WebGPU adapter")
    return browser


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--capture-receipt", type=Path, action="append", required=True)
    parser.add_argument("--expected-orig-sha256", required=True)
    parser.add_argument("profiles", type=Path, nargs="+")
    args = parser.parse_args()
    if len(args.profiles) < 2:
        parser.error("at least two profiles are required")
    if len(args.capture_receipt) != len(args.profiles):
        parser.error("one --capture-receipt is required for each direct profile input")
    if len(args.expected_orig_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in args.expected_orig_sha256
    ):
        parser.error("--expected-orig-sha256 must be lowercase 64-hex")

    output = args.output.resolve()
    receipt_path = output.with_suffix(output.suffix + ".receipt.json")
    if output.exists() or receipt_path.exists():
        raise SystemExit(f"refusing overwrite: {output} or {receipt_path}")

    profile_paths = [path.resolve() for path in args.profiles]
    inputs = [path.read_bytes() for path in profile_paths]
    capture_provenance = []
    capture_scenarios: set[str] = set()
    captured_orig_bytes = None
    for profile_path, raw_receipt_path in zip(profile_paths, args.capture_receipt, strict=True):
        capture_receipt_path = raw_receipt_path.resolve()
        capture = json.loads(capture_receipt_path.read_text(encoding="utf-8"))
        if capture.get("schema") != "blender-web.wasm-split-profile.v1" or capture.get("status") != "PASS":
            raise SystemExit(f"capture receipt is not strict PASS: {capture_receipt_path}")
        try:
            verify_capture_browser(capture, str(capture_receipt_path))
        except ValueError as error:
            raise SystemExit(str(error)) from error
        scenario = capture.get("scenario")
        if scenario not in {"success", "terminal-error"} or scenario in capture_scenarios:
            raise SystemExit(f"capture scenario is absent, invalid, or duplicated: {capture_receipt_path}")
        capture_scenarios.add(scenario)
        controller = capture.get("result", {}).get("controller")
        if not isinstance(controller, dict) or controller.get("status") != "PASS":
            raise SystemExit(f"capture controller proof is not strict PASS: {capture_receipt_path}")
        profile_row = capture.get("artifacts", {}).get("profile-hot.data")
        original_row = capture.get("provenance", {}).get("binaries", {}).get("wasm.orig")
        if not isinstance(profile_row, dict) or not isinstance(original_row, dict):
            raise SystemExit(f"capture receipt lacks profile/original provenance: {capture_receipt_path}")
        if resolve_receipt_path(str(profile_row.get("path", "")), capture_receipt_path) != profile_path:
            raise SystemExit(f"capture profile path does not match direct input: {capture_receipt_path}")
        actual_profile = identity(profile_path)
        if profile_row.get("bytes") != actual_profile["bytes"] or profile_row.get("sha256") != actual_profile["sha256"]:
            raise SystemExit(f"capture profile identity mismatch: {capture_receipt_path}")
        if original_row.get("sha256") != args.expected_orig_sha256:
            raise SystemExit(f"capture original SHA mismatch: {capture_receipt_path}")
        if not isinstance(original_row.get("bytes"), int) or original_row["bytes"] <= 0:
            raise SystemExit(f"capture original byte count invalid: {capture_receipt_path}")
        if captured_orig_bytes is None:
            captured_orig_bytes = original_row["bytes"]
        elif captured_orig_bytes != original_row["bytes"]:
            raise SystemExit("capture receipts disagree on original byte count")
        capture_provenance.append(
            {
                "receipt": identity(capture_receipt_path),
                "profile": actual_profile,
                "captured_original": {
                    "bytes": original_row["bytes"],
                    "sha256": original_row["sha256"],
                },
                "scenario": scenario,
            }
        )
    if capture_scenarios != {"success", "terminal-error"}:
        raise SystemExit(
            "profile union requires exactly one success and one terminal-error controller capture"
        )
    lengths = {len(data) for data in inputs}
    if len(lengths) != 1 or next(iter(lengths)) < 12 or (next(iter(lengths)) - 8) % 4:
        raise SystemExit(f"incompatible profile lengths: {sorted(lengths)}")
    headers = {data[:8] for data in inputs}
    if len(headers) != 1:
        raise SystemExit("incompatible Binaryen profile headers")

    merged = bytearray(inputs[0])
    hit_counts = []
    for data in inputs:
        values = [int.from_bytes(data[offset : offset + 4], "little") for offset in range(8, len(data), 4)]
        if any(value not in (0, 1) for value in values):
            raise SystemExit("profile contains a counter outside the expected {0,1} domain")
        hit_counts.append(sum(values))
        for offset, value in zip(range(8, len(data), 4), values, strict=True):
            if value:
                merged[offset : offset + 4] = b"\x01\x00\x00\x00"

    merged_hits = sum(int.from_bytes(merged[offset : offset + 4], "little") for offset in range(8, len(merged), 4))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(merged)
    receipt = {
        "schema": "blender-web.wasm-split-profile-union.v2",
        "status": "PASS",
        "contract": "binaryen-in-memory-boolean-union-v1",
        "header_hex": merged[:8].hex(),
        "input_hit_counts": hit_counts,
        "merged_hit_count": merged_hits,
        "new_hits_over_largest_input": merged_hits - max(hit_counts),
        "inputs": [identity(path) for path in profile_paths],
        "capture_receipts": capture_provenance,
        "capture_scenarios": sorted(capture_scenarios),
        "captured_original": {
            "bytes": captured_orig_bytes,
            "sha256": args.expected_orig_sha256,
        },
        "output": identity(output),
        "driver": identity(Path(__file__)),
    }
    with receipt_path.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
