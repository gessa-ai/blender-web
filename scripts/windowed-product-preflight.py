#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fail-closed artifact-shape check for the reconstructed windowed product."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
MODE_CACHE_KEY = "BLENDER_WEB_WASM_SPLIT_MODE"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PreflightError(RuntimeError):
    pass


class ModeBlocked(PreflightError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PreflightError(message)


def regular_file(path: Path, label: str) -> Path:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as error:
        raise PreflightError(f"missing {label}: {path}") from error
    require(stat.S_ISREG(mode) and not path.is_symlink(), f"{label} is not an exact regular file: {path}")
    require(path.stat().st_size > 0, f"{label} is empty: {path}")
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, int | str]:
    regular_file(path, "artifact")
    return {"bytes": path.stat().st_size, "sha256": sha256(path)}


def cache_value(cache: Path, key: str) -> str:
    regular_file(cache, "CMake cache")
    prefix = f"{key}:"
    matches = []
    for line in cache.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix) and "=" in line:
            matches.append(line.split("=", 1)[1])
    require(len(matches) == 1, f"CMake cache must contain exactly one {key} entry")
    return matches[0]


def load_manifest(path: Path) -> dict[str, Any]:
    regular_file(path, "split-build manifest")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PreflightError(f"invalid split-build manifest: {error}") from error
    require(isinstance(value, dict), "split-build manifest root is not an object")
    require(value.get("schema") == 1 and value.get("verdict") == "PASS", "split-build manifest is not schema-1 PASS")
    return value


def record_path(row: dict[str, Any]) -> Path:
    raw = row.get("path")
    require(isinstance(raw, str) and raw, "artifact receipt path is absent")
    path = Path(raw)
    if not path.is_absolute():
        path = REPO / path
    return path.resolve()


def verify_record(label: str, row: Any, expected: Path, *, require_bytes: bool = True) -> None:
    require(isinstance(row, dict), f"{label} receipt row is absent")
    expected = expected.resolve()
    require(record_path(row) == expected, f"{label} receipt path does not name the exact artifact")
    actual = identity(expected)
    digest = row.get("sha256")
    require(isinstance(digest, str) and SHA256_RE.fullmatch(digest) is not None, f"{label} receipt SHA-256 is invalid")
    require(digest == actual["sha256"], f"{label} receipt SHA-256 drift")
    if require_bytes:
        require(row.get("bytes") == actual["bytes"], f"{label} receipt byte-count drift")


def exact_wasm_files(bin_dir: Path) -> set[str]:
    return {
        path.name
        for path in bin_dir.glob("blender_browser*.wasm*")
        if path.is_file() or path.is_symlink()
    }


def verify_wasm_shape(bin_dir: Path, expected: set[str]) -> None:
    actual = exact_wasm_files(bin_dir)
    require(actual == expected, f"Wasm artifact set mismatch: actual={sorted(actual)} expected={sorted(expected)}")
    for name in expected:
        regular_file(bin_dir / name, name)


def validate_off(_build_dir: Path, bin_dir: Path) -> dict[str, int]:
    verify_wasm_shape(bin_dir, {"blender_browser.wasm"})
    require(
        not (bin_dir / "blender_browser.split-build.json").exists(),
        "OFF mode retains a stale split-build manifest",
    )
    return {"primary": (bin_dir / "blender_browser.wasm").stat().st_size}


def validate_capture(_build_dir: Path, bin_dir: Path) -> dict[str, int]:
    wasm = bin_dir / "blender_browser.wasm"
    original = bin_dir / "blender_browser.wasm.orig"
    verify_wasm_shape(bin_dir, {wasm.name, original.name})
    manifest = load_manifest(bin_dir / "blender_browser.split-build.json")
    require(manifest.get("mode") == "capture", "capture cache is not paired with a capture manifest")
    verify_record("capture instrumented", manifest.get("instrumented"), wasm)
    verify_record("capture original", manifest.get("original"), original)
    verify_record("capture JavaScript", manifest.get("js"), bin_dir / "blender_browser.js")
    require(manifest.get("inventory_policy", {}).get("capture_artifact_is_not_shippable") is True,
            "capture manifest does not mark the instrumented artifact non-shippable")
    return {"instrumented": wasm.stat().st_size, "original": original.stat().st_size}


def validate_apply(_build_dir: Path, bin_dir: Path) -> dict[str, int]:
    primary = bin_dir / "blender_browser.wasm"
    original = bin_dir / "blender_browser.wasm.orig"
    deferred = bin_dir / "blender_browser.deferred.wasm"
    verify_wasm_shape(bin_dir, {primary.name, original.name, deferred.name})
    manifest = load_manifest(bin_dir / "blender_browser.split-build.json")
    require(manifest.get("mode") == "apply", "APPLY cache is not paired with an apply manifest")
    verify_record("apply primary", manifest.get("primary"), primary)
    verify_record("apply original", manifest.get("original"), original)
    verify_record("apply deferred", manifest.get("secondary"), deferred)
    verify_record("apply JavaScript", manifest.get("js"), bin_dir / "blender_browser.js",
                  require_bytes=False)

    profile_receipt = manifest.get("profile_receipt")
    require(isinstance(profile_receipt, dict), "apply manifest lacks its profile-union receipt")
    require(profile_receipt.get("schema") == "blender-web.wasm-split-profile-union.v2" and
            profile_receipt.get("status") == "PASS", "apply profile-union receipt is not strict PASS")
    require(manifest.get("controller_closure", {}).get("verdict") == "PASS",
            "apply controller-closure proof is not PASS")
    policy = manifest.get("inventory_policy", {})
    require(policy.get("bundle_roles") == ["primary", "deferred"] and
            policy.get("build_only_roles") == ["original_build_only"],
            "apply inventory policy changed")

    rows = manifest.get("wasm_inventory")
    require(isinstance(rows, list), "apply Wasm inventory is absent")
    by_role = {row.get("role"): row for row in rows if isinstance(row, dict)}
    require(set(by_role) == {"primary", "deferred", "original_build_only"},
            "apply Wasm inventory roles are not exact")
    for role, path in (("primary", primary), ("deferred", deferred), ("original_build_only", original)):
        row = by_role[role]
        require(row.get("filename") == path.name, f"{role} inventory filename changed")
        verify_record(f"{role} inventory", row, path)
    return {"primary": primary.stat().st_size, "deferred": deferred.stat().st_size,
            "original": original.stat().st_size}


def validate(build_dir: Path, expected_mode: str) -> str:
    build_dir = build_dir.resolve()
    bin_dir = build_dir / "bin"
    require(bin_dir.is_dir(), f"missing product bin directory: {bin_dir}")
    actual_mode = cache_value(build_dir / "CMakeCache.txt", MODE_CACHE_KEY).upper()
    require(actual_mode in {"OFF", "CAPTURE", "APPLY"}, f"unsupported split mode in CMake cache: {actual_mode}")

    js = regular_file(bin_dir / "blender_browser.js", "browser JavaScript")
    data = regular_file(bin_dir / "blender_browser.data", "preloaded data")
    sizes = {
        "OFF": validate_off,
        "CAPTURE": validate_capture,
        "APPLY": validate_apply,
    }[actual_mode](build_dir, bin_dir)

    expected_mode = expected_mode.upper()
    if actual_mode != expected_mode:
        recovery = (
            "configure CAPTURE, collect strict success+terminal-error profiles on the accepted hardware "
            "adapter, merge them, then relink APPLY"
        )
        raise ModeBlocked(f"actual_mode={actual_mode} expected_mode={expected_mode}; {recovery}")

    size_text = " ".join(f"{key}_bytes={value}" for key, value in sorted(sizes.items()))
    return (
        f"WINDOWED_PRODUCT_PREFLIGHT_PASS mode={actual_mode} js_bytes={js.stat().st_size} "
        f"data_bytes={data.stat().st_size} {size_text}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, default=REPO / "build-wasm-windowed-opt")
    parser.add_argument("--expect", choices=("off", "capture", "apply"), default="apply")
    args = parser.parse_args()
    try:
        print(validate(args.build_dir, args.expect))
    except ModeBlocked as error:
        print(f"WINDOWED_PRODUCT_PREFLIGHT_BLOCKED {error}")
        return 5
    except PreflightError as error:
        print(f"WINDOWED_PRODUCT_PREFLIGHT_FAIL {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
