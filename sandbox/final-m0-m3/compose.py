#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compose one immutable strict M0--M3 candidate from raw-derived receipts.

This command does not turn milestone summaries into evidence.  The five input
receipts must already have been emitted by the raw-evidence adapters, carry the
same run label, and bind the exact upstream component of the composite release
freeze.  The strict verifier remains the authority and is run before the
candidate is published.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
VERIFIER = HERE / "verify.py"
OUTPUT_ROOT = HERE / "evidence"
LABEL_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,79}")
RECEIPT_NAMES = ("m0", "m1", "m2", "m2_deps", "m3")
COMMON_FIELDS = {"schema", "verdict", "run_label", "created_utc", "source_freeze_sha256"}
RELEASE_CHECKS = {
    "repositories_disjoint", "project_component_pass", "upstream_component_pass",
    "technical_release_inputs_present", "cross_root_resnapshot_byte_exact",
    "both_heads_and_real_indexes_stable", "outputs_created_without_overwrite",
    "final_overlapping_double_resnapshot",
}
VOLATILE_GENERATED_OUTPUTS = (
    "ledger/results/m0.json", "ledger/results/m1.json", "ledger/results/m2b.json",
    "ledger/results/m3.json", "ledger/results/m4.json", "ledger/results/m5.json",
    "ledger/results/m6.json", "ledger/results/m7.json", "ledger/results/m8.json",
    "reports/dashboard.md",
    "sandbox/m8-staged-deploy/artifacts/staged_boot_1280x720.png",
    "sandbox/m8-staged-deploy/artifacts/staged_boot_1280x720.png.license",
)


class ComposeError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ComposeError(message)


def strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_json(path: Path, where: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        fail(f"{where}: expected non-symlink file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"{where}: invalid JSON: {error}")
    if not isinstance(value, dict):
        fail(f"{where}: JSON root is not an object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_ref(root: Path, path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True)
    try:
        relative = path.relative_to(root)
    except ValueError:
        fail(f"referenced file escapes repository: {path}")
    if path.is_symlink() or not path.is_file():
        fail(f"referenced path is not one non-symlink file: {relative}")
    return {"path": relative.as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}


def parse_time(value: Any, where: str) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        fail(f"{where}: expected UTC RFC3339 ending in Z")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        fail(f"{where}: invalid timestamp: {error}")
    if parsed.tzinfo != dt.timezone.utc:
        fail(f"{where}: timestamp is not UTC")
    return parsed


def resolve_root_file(root: Path, raw: str, where: str) -> Path:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        fail(f"{where}: expected nonempty POSIX path")
    candidate = Path(raw)
    path = candidate if candidate.is_absolute() else root / PurePosixPath(raw)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        fail(f"{where}: file escapes/missing from repository: {error}")
    if path.is_symlink() or not resolved.is_file():
        fail(f"{where}: expected non-symlink file")
    return resolved


def validate_release_freeze(
    receipt_path: Path, root: Path = ROOT
) -> tuple[Path, dict[str, Path], str, dt.datetime]:
    release = load_json(receipt_path, "release freeze")
    if set(release) != {
        "schema", "verdict", "created_utc", "project", "upstream", "coverage",
        "final_paired_resnapshot", "checks",
    }:
        fail("release freeze: field set mismatch")
    if release["schema"] != 1 or release["verdict"] != "PASS":
        fail("release freeze is not schema-1 PASS")
    release_time = parse_time(release["created_utc"], "release freeze.created_utc")
    checks = release["checks"]
    if not isinstance(checks, dict) or set(checks) != RELEASE_CHECKS or any(
        value is not True for value in checks.values()
    ):
        fail("release freeze checks are not exact/all true")
    coverage = release["coverage"]
    if not isinstance(coverage, dict) or set(coverage) != {
        "policy", "required_paths", "required_paths_present",
        "required_upstream_paths", "required_upstream_paths_present",
        "volatile_generated_outputs",
    }:
        fail("release freeze coverage is malformed")
    required = coverage["required_paths"]
    required_upstream = coverage["required_upstream_paths"]
    if (coverage["policy"] !=
            "all project+upstream source byte-exact; exact generator-owned outputs independently post-bound"
            or not isinstance(required, list) or len(required) != len(set(required))
            or coverage["required_paths_present"] != len(required)
            or not isinstance(required_upstream, list)
            or len(required_upstream) != len(set(required_upstream))
            or coverage["required_upstream_paths_present"] != len(required_upstream)
            or coverage["volatile_generated_outputs"] != list(VOLATILE_GENERATED_OUTPUTS)):
        fail("release freeze coverage policy drift")
    if release["final_paired_resnapshot"] != {
        "policy": "nested overlapping live resnapshots immediately before publication",
        "order": ["project", "upstream", "upstream", "project"],
        "checks_per_root": 2,
    }:
        fail("release freeze paired-resnapshot contract drift")
    upstream = release.get("upstream")
    if not isinstance(upstream, dict) or set(upstream) != {
        "directory", "receipt_sha256", "patch", "live_manifest"
    } or upstream["directory"] != "upstream":
        fail("release freeze upstream component is malformed")
    child_path = receipt_path.parent / "upstream" / "receipt.json"
    child = load_json(child_path, "upstream freeze receipt")
    if sha256(child_path) != upstream["receipt_sha256"]:
        fail("upstream child receipt differs from composite release freeze")
    if child.get("schema") != 1 or child.get("verdict") != "PASS":
        fail("upstream child is not schema-1 PASS")
    if Path(str(child.get("source", ""))).resolve() != (root / "upstream").resolve():
        fail("upstream child source does not identify this repository")
    component_dir = child_path.parent
    embedded: dict[str, Path] = {"receipt": child_path}
    for key in ("patch", "live_manifest", "replay_manifest"):
        item = child.get(key)
        required = {"path", "bytes", "sha256"} | ({"entries"} if key != "patch" else set())
        if not isinstance(item, dict) or set(item) != required:
            fail(f"upstream child {key} record malformed")
        name = item.get("path")
        if not isinstance(name, str) or Path(name).name != name:
            fail(f"upstream child {key} path is not one safe filename")
        path = component_dir / name
        if path.is_symlink() or not path.is_file():
            fail(f"upstream child {key} is missing or a symlink")
        if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            fail(f"upstream child {key} identity mismatch")
        embedded[key] = path
    if embedded["live_manifest"].read_bytes() != embedded["replay_manifest"].read_bytes():
        fail("upstream live/replay manifests differ")
    return child_path, embedded, sha256(child_path), release_time


def copy_exclusive(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        fail(f"refusing to overwrite output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, destination.open("xb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    if sha256(source) != sha256(destination) or source.stat().st_size != destination.stat().st_size:
        fail(f"copy identity mismatch: {source}")


def validate_input_receipt(
    root: Path, path: Path, name: str, label: str, freeze_hash: str,
    freeze_time: dt.datetime, now: dt.datetime,
) -> None:
    try:
        path.relative_to(root)
    except ValueError:
        fail(f"{name} receipt must be inside the repository")
    receipt = load_json(path, f"{name} receipt")
    if not COMMON_FIELDS <= set(receipt):
        fail(f"{name} receipt lacks common binding fields")
    if receipt["schema"] != 1 or receipt["verdict"] != "PASS":
        fail(f"{name} receipt is not schema-1 PASS")
    if receipt["run_label"] != label or receipt["source_freeze_sha256"] != freeze_hash:
        fail(f"{name} receipt label/source-freeze binding mismatch")
    created = parse_time(receipt["created_utc"], f"{name}.created_utc")
    if created < freeze_time or created > now:
        fail(f"{name} receipt predates freeze or is future-dated")


def compose(
    args: argparse.Namespace,
    *,
    now: dt.datetime | None = None,
    _canonical_root: Path = ROOT,
    _output_root: Path = OUTPUT_ROOT,
    _verifier: Path = VERIFIER,
) -> Path:
    root = args.root.resolve(strict=True)
    if root != _canonical_root.resolve():
        fail(f"--root must be the canonical repository: {_canonical_root}")
    label = args.run_label
    if not isinstance(label, str) or LABEL_RE.fullmatch(label) is None:
        fail("--run-label is unsafe")
    now = now or dt.datetime.now(dt.timezone.utc)
    output = (_output_root / label).resolve(strict=False)
    if args.output_dir is not None and args.output_dir.resolve(strict=False) != output:
        fail(f"--output-dir must be exactly {output}")
    if output.exists() or output.is_symlink():
        fail(f"refusing to overwrite immutable run: {output}")

    release_path = args.release_freeze.resolve(strict=True)
    child_path, embedded, freeze_hash, freeze_time = validate_release_freeze(release_path, root)
    if freeze_time > now:
        fail("release freeze is future-dated")
    receipt_paths = {
        name: resolve_root_file(root, getattr(args, name.replace("_", "_")), f"--{name.replace('_', '-')}")
        for name in RECEIPT_NAMES
    }
    for name, path in receipt_paths.items():
        validate_input_receipt(root, path, name, label, freeze_hash, freeze_time, now)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    incomplete = output / "INCOMPLETE"
    incomplete.write_text("composition in progress\n", encoding="utf-8")
    try:
        freeze_dir = output / "freeze"
        copied: dict[str, Path] = {}
        for key, source in embedded.items():
            destination = freeze_dir / source.name
            copy_exclusive(source, destination)
            copied[key] = destination
        if sha256(copied["receipt"]) != sha256(child_path):
            fail("published upstream receipt differs from composite child")

        stamp = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
        manifest = {
            "schema": 1,
            "verdict": "PASS",
            "run_label": label,
            "created_utc": stamp,
            "source_tree": "upstream",
            "source_freeze": {
                "receipt": file_ref(root, copied["receipt"]),
                "patch": file_ref(root, copied["patch"]),
                "live_manifest": file_ref(root, copied["live_manifest"]),
                "replay_manifest": file_ref(root, copied["replay_manifest"]),
            },
            "receipts": {name: file_ref(root, path) for name, path in receipt_paths.items()},
        }
        manifest_path = output / "final-m0-m3.json"
        with manifest_path.open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.write("\n")
        result = subprocess.run(
            [sys.executable, os.fspath(_verifier), "--root", os.fspath(root),
             "--manifest", os.fspath(manifest_path), "--now", stamp],
            cwd=root, text=True, capture_output=True, check=False,
        )
        if result.returncode != 0:
            fail(f"strict verifier rejected candidate: {(result.stdout + result.stderr)[-4000:]}")
        try:
            verified = json.loads(result.stdout, object_pairs_hook=strict_pairs)
        except json.JSONDecodeError as error:
            fail(f"strict verifier returned invalid JSON: {error}")
        if (verified.get("verdict"), verified.get("run_label"),
                verified.get("source_freeze_sha256")) != ("PASS", label, freeze_hash):
            fail("strict verifier result is not bound to this run/freeze")
        incomplete.unlink()
        return manifest_path
    except BaseException:
        # The directory is newly and exclusively owned by this invocation.  Keep
        # an explicit sentinel and partial bytes for audit instead of silently
        # presenting a failed attempt as an immutable candidate.
        raise


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--release-freeze", type=Path, required=True,
                        help="external composite release receipt.json")
    for name in RECEIPT_NAMES:
        parser.add_argument("--" + name.replace("_", "-"), dest=name, required=True,
                            help=f"repository-relative raw-derived {name} receipt")
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        path = compose(parse_args(sys.argv[1:] if argv is None else argv))
    except (ComposeError, OSError, subprocess.SubprocessError) as error:
        print(f"FINAL_M0_M3_COMPOSE_FAIL {error}", file=sys.stderr)
        return 1
    print(f"FINAL_M0_M3_COMPOSE_PASS manifest={path.relative_to(ROOT)} sha256={sha256(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
