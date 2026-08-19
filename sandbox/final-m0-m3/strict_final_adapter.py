#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn one strict final M0--M3 manifest into an honest harness scope result.

The harness must not rerun historical mutable test drivers after the release
source freeze.  This adapter reruns the authoritative strict verifier, checks
its complete result against the exact manifest and receipt bytes, and exposes
only the M1, M2b, or M3 summary requested by the harness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LABEL_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,79}")
SHA_RE = re.compile(r"[0-9a-f]{64}")
SCOPES = {"m1": "m1", "m2b": "m2", "m3": "m3"}
RECEIPTS = {"m0", "m1", "m2", "m2_deps", "m3"}
M3_GPU_TEST_COUNT = 197
M3_SHADER_COUNT = 1003


class AdapterError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise AdapterError(message)


def strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            fail(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def load_json(path: Path, where: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"{where}: invalid JSON: {error}")
    if not isinstance(value, dict):
        fail(f"{where}: JSON root is not an object")
    return value


def exact(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        fail(f"{where}: expected exact keys {sorted(keys)}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reject_symlinks(path: Path, where: str) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            fail(f"{where}: symlink path component is not accepted: {current}")


def repository_file(root: Path, value: str | Path, where: str) -> Path:
    raw = os.fspath(value)
    candidate = Path(raw) if Path(raw).is_absolute() else root / PurePosixPath(raw)
    reject_symlinks(candidate, where)
    try:
        path = candidate.resolve(strict=True)
    except OSError as error:
        fail(f"{where}: missing file: {error}")
    if path == root or root not in path.parents or not path.is_file():
        fail(f"{where}: expected a regular file strictly inside the repository")
    return path


def file_ref(root: Path, value: Any, where: str) -> Path:
    row = exact(value, {"path", "bytes", "sha256"}, where)
    if not isinstance(row["path"], str):
        fail(f"{where}: path is not text")
    pure = PurePosixPath(row["path"])
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        fail(f"{where}: unsafe repository-relative path")
    path = repository_file(root, row["path"], where)
    if (not isinstance(row["bytes"], int) or isinstance(row["bytes"], bool)
            or row["bytes"] < 0 or path.stat().st_size != row["bytes"]):
        fail(f"{where}: byte count mismatch")
    if not isinstance(row["sha256"], str) or SHA_RE.fullmatch(row["sha256"]) is None:
        fail(f"{where}: invalid sha256")
    if sha256(path) != row["sha256"]:
        fail(f"{where}: sha256 mismatch")
    return path


def integer(value: Any, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        fail(f"{where}: expected non-negative integer")
    return value


def summarize(scope: str, receipt: dict[str, Any]) -> str:
    if scope == "m1":
        gtests = receipt.get("gtests")
        if not isinstance(gtests, dict):
            fail("m1 receipt lacks gtests")
        counts: dict[str, int] = {}
        for name, expected in (("blenlib", 1667), ("bmesh_core", 1)):
            row = gtests.get(name)
            if not isinstance(row, dict):
                fail(f"m1 receipt lacks {name} gtest result")
            total = integer(row.get("total"), f"m1.{name}.total")
            passed = integer(row.get("passed"), f"m1.{name}.passed")
            failed = integer(row.get("failed"), f"m1.{name}.failed")
            crashed = integer(row.get("crashed"), f"m1.{name}.crashed")
            if (total, passed, failed, crashed) != (expected, expected, 0, 0):
                fail(f"m1 {name} is not exact all-pass")
            counts[name] = passed
        corpus = receipt.get("main_corpus")
        versioning = receipt.get("versioning")
        if (not isinstance(corpus, dict)
                or (corpus.get("total"), corpus.get("equal")) != (9, 9)):
            fail("m1 main corpus is not exact 9/9 parity")
        if (not isinstance(versioning, dict)
                or (versioning.get("total"), versioning.get("pass"),
                    versioning.get("oracle_refuse"), versioning.get("equal"))
                != (12, 10, 2, 12)):
            fail("m1 versioning corpus is not exact 12/12 native parity")
        return (
            f"blenlib={counts['blenlib']}/1667 bmesh={counts['bmesh_core']}/1 "
            "main_corpus=9/9 versioning=12/12"
        )
    if scope == "m2b":
        if receipt.get("total") != 75 or not isinstance(receipt.get("rows"), dict):
            fail("m2 receipt is not the exact 75-row suite")
        rows = receipt["rows"]
        if len(rows) != 75:
            fail("m2 receipt does not contain exactly 75 rows")
        passed = sum(isinstance(row, dict) and row.get("result") == "PASS" for row in rows.values())
        deferred = sum(isinstance(row, dict) and row.get("result") == "DEFERRED" for row in rows.values())
        if passed + deferred != 75:
            fail("m2 receipt contains a non-strict result status")
        return f"suite=75/75 pass={passed} active_deferrals={deferred} dependency_receipt=PASS"
    gtests = receipt.get("gpu_tests")
    draw = receipt.get("draw_webgpu_tests")
    static = receipt.get("static_shaders")
    if (not isinstance(gtests, dict)
            or (gtests.get("total"), gtests.get("passed"), gtests.get("failed"),
                gtests.get("crashed")) != (
                    M3_GPU_TEST_COUNT, M3_GPU_TEST_COUNT, 0, 0)):
        fail(
            f"m3 GPU census is not exact {M3_GPU_TEST_COUNT}/{M3_GPU_TEST_COUNT}"
        )
    if (not isinstance(draw, dict)
            or (draw.get("total"), draw.get("passed"), draw.get("failed"),
                draw.get("crashed")) != (2, 2, 0, 0)):
        fail("m3 supplemental DrawWebGPUTest census is not exact 2/2")
    if not isinstance(static, dict):
        fail("m3 receipt lacks static shader census")
    total = integer(static.get("total"), "m3.static.total")
    passed = integer(static.get("passed"), "m3.static.passed")
    excluded = integer(static.get("excluded"), "m3.static.excluded")
    failed = integer(static.get("failed"), "m3.static.failed")
    if total != M3_SHADER_COUNT or failed != 0 or passed + excluded != M3_SHADER_COUNT:
        fail(f"m3 shader census does not account exactly for {M3_SHADER_COUNT}")
    return (
        f"gpu={M3_GPU_TEST_COUNT}/{M3_GPU_TEST_COUNT} "
        "draw_webgpu=2/2 "
        f"shaders={passed}/{M3_SHADER_COUNT} "
        f"scoped_nonshipping_exclusions={excluded} cache=PASS"
    )


def verify_scope(
    root: Path, manifest_value: str | Path, label: str, scope: str,
    max_age_seconds: int, now: str | None = None,
) -> str:
    root = root.resolve(strict=True)
    if scope not in SCOPES:
        fail(f"unsupported harness scope: {scope}")
    if LABEL_RE.fullmatch(label) is None:
        fail("unsafe or missing final run label")
    manifest_path = repository_file(root, manifest_value, "final M0-M3 manifest")
    expected = root / "sandbox/final-m0-m3/evidence" / label / "final-m0-m3.json"
    if manifest_path != expected:
        fail(f"manifest must be the canonical immutable path: {expected.relative_to(root)}")
    manifest = exact(
        load_json(manifest_path, "final M0-M3 manifest"),
        {"schema", "verdict", "run_label", "created_utc", "source_tree", "source_freeze", "receipts"},
        "final M0-M3 manifest",
    )
    if (manifest["schema"] != 1 or manifest["verdict"] != "PASS"
            or manifest["source_tree"] != "upstream" or manifest["run_label"] != label):
        fail("final M0-M3 manifest identity mismatch")
    refs = exact(manifest["receipts"], RECEIPTS, "final M0-M3 manifest.receipts")
    receipt_paths = {
        name: file_ref(root, value, f"final M0-M3 manifest.receipts.{name}")
        for name, value in refs.items()
    }
    verifier = repository_file(root, "sandbox/final-m0-m3/verify.py", "strict verifier")
    command = [
        sys.executable, os.fspath(verifier), "--root", os.fspath(root),
        "--manifest", os.fspath(manifest_path), "--max-age-seconds", str(max_age_seconds),
    ]
    if now is not None:
        command.extend(["--now", now])
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        output = (completed.stdout + completed.stderr).strip()
        fail(f"strict final verifier is red: {output[-1600:]}")
    try:
        result = json.loads(completed.stdout, object_pairs_hook=strict_pairs)
    except json.JSONDecodeError as error:
        fail(f"strict final verifier returned invalid JSON: {error}")
    result = exact(
        result,
        {"schema", "verdict", "run_label", "source_freeze_sha256", "receipt_sha256", "contracts"},
        "strict final verifier result",
    )
    hashes = exact(result["receipt_sha256"], RECEIPTS, "strict final verifier receipt hashes")
    if (result["schema"] != 1 or result["verdict"] != "PASS"
            or result["run_label"] != label
            or not isinstance(result["source_freeze_sha256"], str)
            or SHA_RE.fullmatch(result["source_freeze_sha256"]) is None):
        fail("strict final verifier result identity mismatch")
    for name, path in receipt_paths.items():
        if hashes[name] != sha256(path) or hashes[name] != refs[name]["sha256"]:
            fail(f"strict final verifier receipt hash mismatch: {name}")
    receipt_name = SCOPES[scope]
    receipt = load_json(receipt_paths[receipt_name], f"strict {receipt_name} receipt")
    detail = summarize(scope, receipt)
    return (
        f"STRICT_{scope.upper()}_PASS run_label={label} "
        f"manifest_sha256={sha256(manifest_path)} "
        f"source_freeze_sha256={result['source_freeze_sha256']} "
        f"receipt_sha256={hashes[receipt_name]} {detail}"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--scope", choices=sorted(SCOPES), required=True)
    parser.add_argument("--max-age-seconds", type=int, default=24 * 60 * 60)
    parser.add_argument("--now", help="test-only UTC RFC3339 timestamp")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        print(verify_scope(
            args.root, args.manifest, args.run_label, args.scope,
            args.max_age_seconds, args.now,
        ))
    except (AdapterError, OSError, subprocess.SubprocessError) as error:
        print(f"STRICT_FINAL_ADAPTER_FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
