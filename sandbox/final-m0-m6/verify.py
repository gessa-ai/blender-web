#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail-closed integration verifier for a frozen technical release.

This gate does not create evidence.  It re-runs the strict M0--M3, M4, M5 and
M6 verifiers plus the authoritative M8 post-receipt verifier with immutable
inputs, and binds all of them to one source freeze and one exact split-build
inventory.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any
from urllib.parse import quote_from_bytes, unquote_to_bytes


SCHEMA = 1
MAX_AGE_SECONDS = 24 * 60 * 60
LABEL_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,79}")
SHA_RE = re.compile(r"[0-9a-f]{64}")
MILESTONE_PREFIXES = {
    "m4": "M4_BINDING_PASS ",
    "m5": "M5_FINAL_PASS ",
    "m6": "M6_RENDER_PASS ",
}
COMPONENT_CHECKS = {
    "source_head_exact_pin", "source_real_index_pristine",
    "source_repository_operation_idle", "initialized_submodules_clean",
    "replay_started_pristine", "patch_regenerated_byte_exact",
    "manifest_replay_byte_exact", "live_resnapshot_byte_exact",
    "pin_and_ignore_inputs_stable", "outputs_created_without_overwrite",
}
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
M8_TECHNICAL_INPUTS = {
    "staged_receipt": "sandbox/m8-launch-gate/artifacts/current-staged-receipt.json",
    "runtime_proof": "sandbox/m8-staged-deploy/artifacts/verify_staged.json",
    "performance_proof": "sandbox/m8-staged-deploy/artifacts/measure_staged-4g.json",
    "runtime_screenshot": "sandbox/m8-staged-deploy/artifacts/staged_boot_1280x720.png",
    "runtime_screenshot_license": "sandbox/m8-staged-deploy/artifacts/staged_boot_1280x720.png.license",
    "runtime_console": "sandbox/m8-staged-deploy/artifacts/verify_console.log",
    "browser_matrix": "sandbox/m8-launch-gate/artifacts/current-browser-matrix.json",
    "product": "sandbox/m8-launch-gate/artifacts/current-product-receipt.json",
    "soak": "sandbox/m8-launch-gate/artifacts/current-soak-result.json",
    "compliance": "sandbox/m8-launch-gate/artifacts/current-compliance-receipt.json",
}
M8_TECHNICAL_TREES = {
    "launch_artifacts": (
        "sandbox/m8-launch-gate/artifacts", ("current-m8-preflight.json",),
    ),
    "staged_artifacts": ("sandbox/m8-staged-deploy/artifacts", ()),
    "bundle": ("sandbox/m8-staged-deploy/bundle-staged", ()),
}
M7_TECHNICAL_INPUTS = {
    "files_receipt": "sandbox/m7-product-gate/verify_files.json",
    "bundle_identity": "sandbox/m7-product-gate/bundle-identity.json",
}


class VerificationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise VerificationError(message)


def strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail(f"duplicate JSON field: {key!r}")
        result[key] = value
    return result


def load_json(path: Path, where: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"{where}: invalid JSON: {error}")


def exact(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{where}: expected object")
    actual = set(value)
    if actual != keys:
        fail(f"{where}: fields mismatch missing={sorted(keys-actual)} unknown={sorted(actual-keys)}")
    return value


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Context:
    def __init__(self, root: Path, now: dt.datetime, max_age: int):
        self.root = root.resolve(strict=True)
        self.now = now
        self.max_age = max_age
        self.snapshots: dict[Path, tuple[int, str]] = {}
        self.tree_snapshots: dict[tuple[Path, tuple[str, ...]], tuple[int, str]] = {}

    @staticmethod
    def reject_symlink_components(path: Path, where: str) -> None:
        absolute = path.absolute()
        current = Path(absolute.anchor)
        for part in absolute.parts[1:]:
            current /= part
            if current.is_symlink():
                fail(f"{where}: symlink path component is not accepted: {current}")

    def snapshot(self, path: Path) -> None:
        identity = (path.stat().st_size, sha256(path))
        previous = self.snapshots.setdefault(path, identity)
        if previous != identity:
            fail(f"referenced file changed during verification: {path}")

    def tree_identity(
        self, path: Path, where: str, excluded: tuple[str, ...] = (), *,
        snapshot_files: bool = True,
    ) -> tuple[int, str]:
        excluded_set = set(excluded)
        if len(excluded_set) != len(excluded) or any(
            not name or PurePosixPath(name).is_absolute()
            or any(part in {"", ".", ".."} for part in PurePosixPath(name).parts)
            for name in excluded
        ):
            fail(f"{where}: invalid projected-tree exclusions")
        digest = hashlib.sha256()
        count = 0
        for item in sorted(path.rglob("*")):
            self.reject_symlink_components(item, where)
            relative = item.relative_to(path).as_posix()
            if relative in excluded_set:
                if not item.is_file():
                    fail(f"{where}: excluded entry is not a regular file: {relative}")
                continue
            if item.is_dir():
                continue
            if not item.is_file():
                fail(f"{where}: non-regular tree entry: {item}")
            digest.update(relative.encode("utf-8") + b"\0")
            digest.update(item.read_bytes())
            digest.update(b"\0")
            count += 1
            if snapshot_files:
                self.snapshot(item)
        return count, digest.hexdigest()

    def projected_tree_ref(
        self, value: Any, where: str, expected: str, excluded: tuple[str, ...] = (),
    ) -> Path:
        ref = exact(value, {"path", "excluded", "files", "sha256"}, where)
        if ref["path"] != expected or ref["excluded"] != list(excluded):
            fail(f"{where}: projected-tree path/exclusions differ from exact contract")
        pure = PurePosixPath(expected)
        lexical = self.root / pure
        self.reject_symlink_components(lexical, where)
        path = lexical.resolve(strict=True)
        if not path.is_dir() or path != lexical:
            fail(f"{where}: expected canonical directory")
        current = self.tree_identity(path, where, excluded)
        if (not isinstance(ref["files"], int) or isinstance(ref["files"], bool)
                or (ref["files"], ref["sha256"]) != current):
            fail(f"{where}: stale projected-tree identity")
        self.tree_snapshots[(path, excluded)] = current
        return path

    def path(self, value: Any, where: str) -> Path:
        if not isinstance(value, str):
            fail(f"{where}: expected repository-relative path")
        pure = PurePosixPath(value)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            fail(f"{where}: unsafe path: {value!r}")
        lexical = self.root / pure
        self.reject_symlink_components(lexical, where)
        try:
            path = lexical.resolve(strict=True)
        except OSError as error:
            fail(f"{where}: missing path: {error}")
        if path != self.root and self.root not in path.parents:
            fail(f"{where}: path escapes repository")
        if not path.is_file():
            fail(f"{where}: expected regular non-symlink file")
        return path

    def external_path(self, value: Any, where: str) -> Path:
        if not isinstance(value, str):
            fail(f"{where}: expected canonical absolute path")
        lexical = Path(value)
        if not lexical.is_absolute() or lexical != lexical.resolve(strict=True):
            fail(f"{where}: expected canonical absolute path")
        self.reject_symlink_components(lexical, where)
        if not lexical.is_file():
            fail(f"{where}: expected regular file")
        return lexical

    def file_ref(self, value: Any, where: str, expected: str | None = None) -> Path:
        ref = exact(value, {"path", "bytes", "sha256"}, where)
        if expected is not None and ref["path"] != expected:
            fail(f"{where}: expected {expected!r}, got {ref['path']!r}")
        path = self.path(ref["path"], where + ".path")
        if not isinstance(ref["bytes"], int) or isinstance(ref["bytes"], bool):
            fail(f"{where}.bytes: expected integer")
        if path.stat().st_size != ref["bytes"]:
            fail(f"{where}: stale byte count")
        if not isinstance(ref["sha256"], str) or SHA_RE.fullmatch(ref["sha256"]) is None:
            fail(f"{where}.sha256: expected lowercase SHA-256")
        if sha256(path) != ref["sha256"]:
            fail(f"{where}: stale SHA-256")
        self.snapshot(path)
        return path

    def external_file_ref(self, value: Any, where: str) -> Path:
        ref = exact(value, {"path", "bytes", "sha256"}, where)
        path = self.external_path(ref["path"], where + ".path")
        if (not isinstance(ref["bytes"], int) or isinstance(ref["bytes"], bool)
                or ref["bytes"] != path.stat().st_size):
            fail(f"{where}: stale/invalid byte count")
        if not isinstance(ref["sha256"], str) or SHA_RE.fullmatch(ref["sha256"]) is None:
            fail(f"{where}.sha256: expected lowercase SHA-256")
        if ref["sha256"] != sha256(path):
            fail(f"{where}: stale SHA-256")
        self.snapshot(path)
        return path

    def tree_ref(self, value: Any, where: str, expected: str) -> Path:
        ref = exact(value, {"path", "files", "sha256"}, where)
        if ref["path"] != expected:
            fail(f"{where}: expected {expected!r}, got {ref['path']!r}")
        pure = PurePosixPath(expected)
        lexical = self.root / pure
        self.reject_symlink_components(lexical, where)
        path = lexical.resolve(strict=True)
        if not path.is_dir() or path != self.root / pure:
            fail(f"{where}: expected canonical directory")
        current = self.tree_identity(path, where)
        if (not isinstance(ref["files"], int) or isinstance(ref["files"], bool)
                or (ref["files"], ref["sha256"]) != current):
            fail(f"{where}: stale tree identity")
        self.tree_snapshots[(path, ())] = current
        return path

    def recheck_snapshots(self) -> None:
        for path, expected in self.snapshots.items():
            self.reject_symlink_components(path, "post-comparator snapshot")
            if not path.is_file() or (path.stat().st_size, sha256(path)) != expected:
                fail(f"referenced file changed during verification: {path}")
        for (path, excluded), expected in self.tree_snapshots.items():
            current = self.tree_identity(
                path, "post-comparator evidence tree", excluded, snapshot_files=False
            )
            if current != expected:
                fail(f"evidence tree changed during verification: {path}")

    def closure(self, candidate_manifest: Path) -> dict[str, Any]:
        files = []
        for path, (size, digest) in sorted(self.snapshots.items(), key=lambda row: str(row[0])):
            if path == candidate_manifest:
                continue
            if path == self.root or self.root in path.parents:
                kind = "repository"
                name = path.relative_to(self.root).as_posix()
            else:
                kind = "external"
                name = os.fspath(path)
            files.append({"kind": kind, "path": name, "bytes": size, "sha256": digest})
        trees = []
        for (path, excluded), (count, digest) in sorted(
            self.tree_snapshots.items(), key=lambda row: (str(row[0][0]), row[0][1])
        ):
            if path != self.root and self.root not in path.parents:
                fail(f"verification closure contains an external tree: {path}")
            trees.append({
                "path": path.relative_to(self.root).as_posix(),
                "excluded": list(excluded), "files": count, "sha256": digest,
            })
        return {"schema": 1, "files": files, "trees": trees}


def validate_split_inventory(ctx: Context, section: Any) -> dict[str, str]:
    refs = exact(section, {"manifest", "javascript", "preload", "primary", "deferred"}, "artifacts")
    manifest_path = ctx.file_ref(
        refs["manifest"], "artifacts.manifest",
        "build-wasm-windowed-opt/bin/blender_browser.split-build.json",
    )
    manifest = exact(
        load_json(manifest_path, "split manifest"),
        {
            "schema", "mode", "verdict", "contract", "reserve_bytes", "original",
            "profile", "profile_receipt", "primary", "secondary", "js", "single_flight",
            "shared_memory_view_refresh", "pthread_memory_range_sync", "controller_closure",
            "link_command", "finalizer", "binaryen_features", "placeholder_modules", "maps",
            "facts", "wasm_inventory", "inventory_policy",
        },
        "split manifest",
    )
    if manifest["schema"] != 1 or manifest["mode"] != "apply" or manifest["verdict"] != "PASS":
        fail("split manifest is not schema-1 APPLY/PASS")
    policy = exact(
        manifest["inventory_policy"],
        {"glob", "unlisted", "bundle_roles", "build_only_roles", "profile_export_absent", "prior_receipt_invalidated_before_mutation"},
        "split manifest.inventory_policy",
    )
    if policy["glob"] != "blender_browser*.wasm*" or policy["unlisted"] != "reject":
        fail("split manifest does not reject unlisted Wasm")
    if policy["bundle_roles"] != ["primary", "deferred"] or policy["build_only_roles"] != ["original_build_only"]:
        fail("split manifest role policy drift")

    rows = manifest["wasm_inventory"]
    if not isinstance(rows, list) or len(rows) != 3:
        fail("split manifest must list exactly three Wasm artifacts")
    by_role: dict[str, dict[str, Any]] = {}
    expected_row_keys = {"role", "filename", "path", "bytes", "sha256", "shipped", "critical", "request_phase"}
    for index, raw in enumerate(rows):
        row = exact(raw, expected_row_keys, f"split manifest.wasm_inventory[{index}]")
        role = row["role"]
        if role in by_role or role not in {"primary", "deferred", "original_build_only"}:
            fail("split manifest has duplicate/unknown Wasm role")
        filename = row["filename"]
        if (not isinstance(filename, str) or Path(filename).name != filename
                or not re.fullmatch(r"blender_browser(?:\.[A-Za-z0-9_-]+)*\.wasm(?:\.orig)?", filename)):
            fail(f"split manifest has unsafe Wasm filename: {filename!r}")
        path = Path(str(row["path"])).resolve()
        expected_path = manifest_path.parent / filename
        if path != expected_path or not path.is_file() or path.is_symlink():
            fail(f"split manifest path mismatch for {role}")
        if row["bytes"] != path.stat().st_size or row["sha256"] != sha256(path):
            fail(f"split manifest stale for {role}")
        by_role[role] = row
    if set(by_role) != {"primary", "deferred", "original_build_only"}:
        fail("split manifest role set is not exact")
    if by_role["primary"]["filename"] != "blender_browser.wasm":
        fail("primary Wasm filename drift")
    if by_role["original_build_only"]["filename"] != "blender_browser.wasm.orig":
        fail("build-only original filename drift")
    expected_semantics = {
        "primary": (True, True, "stage0"),
        "deferred": (True, False, "after_semantic_first_interaction"),
        "original_build_only": (False, False, "never"),
    }
    for role, values in expected_semantics.items():
        row = by_role[role]
        if (row["shipped"], row["critical"], row["request_phase"]) != values:
            fail(f"split manifest shipping semantics drift for {role}")

    expected_names = {row["filename"] for row in rows}
    actual_names: set[str] = set()
    for path in manifest_path.parent.glob("blender_browser*.wasm*"):
        if path.is_symlink() or not path.is_file():
            fail(f"unaccepted Wasm filesystem entry: {path.name}")
        actual_names.add(path.name)
    if actual_names != expected_names:
        fail(f"unlisted/missing Wasm files: expected={sorted(expected_names)} actual={sorted(actual_names)}")

    js = ctx.file_ref(refs["javascript"], "artifacts.javascript", "build-wasm-windowed-opt/bin/blender_browser.js")
    preload = ctx.file_ref(refs["preload"], "artifacts.preload", "build-wasm-windowed-opt/bin/blender_browser.data")
    primary = ctx.file_ref(refs["primary"], "artifacts.primary", "build-wasm-windowed-opt/bin/blender_browser.wasm")
    deferred_expected = f"build-wasm-windowed-opt/bin/{by_role['deferred']['filename']}"
    deferred = ctx.file_ref(refs["deferred"], "artifacts.deferred", deferred_expected)
    if manifest["js"]["sha256"] != sha256(js):
        fail("split manifest JS digest differs from release artifact")
    for label, path in (("primary", primary), ("secondary", deferred)):
        embedded = manifest[label]
        if Path(str(embedded["path"])).resolve() != path or embedded["bytes"] != path.stat().st_size or embedded["sha256"] != sha256(path):
            fail(f"split manifest {label} binding differs from release artifact")
    return {
        "javascript": sha256(js), "preload": sha256(preload),
        "primary": sha256(primary), "deferred": sha256(deferred),
        "manifest": sha256(manifest_path),
        "deferred_filename": by_role["deferred"]["filename"],
    }


def external_embedded_file(
    ctx: Context, directory: Path, record: Any, where: str, *, entries: bool = False
) -> Path:
    keys = {"path", "bytes", "sha256"} | ({"entries"} if entries else set())
    row = exact(record, keys, where)
    name = row["path"]
    if not isinstance(name, str) or Path(name).name != name:
        fail(f"{where}: embedded path is not one safe filename")
    path = directory / name
    return ctx.external_file_ref(
        {"path": os.fspath(path), "bytes": row["bytes"], "sha256": row["sha256"]},
        where,
    )


def validate_component_receipt(
    ctx: Context, receipt_path: Path, expected_source: Path, where: str
) -> tuple[dict[str, Any], dict[str, Path]]:
    receipt = exact(
        load_json(receipt_path, where),
        {
            "schema", "verdict", "created_utc", "source", "expected_pin",
            "recorded_pin_file", "git_version", "patch", "live_manifest",
            "replay_manifest", "ignored_worktree_paths", "checks",
        },
        where,
    )
    if receipt["schema"] != 1 or receipt["verdict"] != "PASS":
        fail(f"{where}: component is not schema-1 PASS")
    if Path(str(receipt["source"])).resolve() != expected_source.resolve():
        fail(f"{where}: source root mismatch")
    pin = receipt["expected_pin"]
    if not isinstance(pin, str) or re.fullmatch(r"[0-9a-f]{40,64}", pin) is None:
        fail(f"{where}: invalid exact pin")
    head = subprocess.run(
        ["git", "-C", os.fspath(expected_source), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if head != pin:
        fail(f"{where}: current HEAD differs from frozen pin")
    checks = exact(receipt["checks"], COMPONENT_CHECKS, where + ".checks")
    if any(value is not True for value in checks.values()):
        fail(f"{where}: component replay checks are not all true")
    parse_time(receipt["created_utc"], where + ".created_utc")
    directory = receipt_path.parent
    paths = {
        "patch": external_embedded_file(ctx, directory, receipt["patch"], where + ".patch"),
        "live_manifest": external_embedded_file(
            ctx, directory, receipt["live_manifest"], where + ".live_manifest", entries=True
        ),
        "replay_manifest": external_embedded_file(
            ctx, directory, receipt["replay_manifest"], where + ".replay_manifest", entries=True
        ),
    }
    if paths["live_manifest"].read_bytes() != paths["replay_manifest"].read_bytes():
        fail(f"{where}: replay manifest is not byte-exact")
    lines = paths["live_manifest"].read_bytes().splitlines()
    if receipt["live_manifest"]["entries"] != len(lines) or receipt["replay_manifest"]["entries"] != len(lines):
        fail(f"{where}: manifest entry counts are stale")
    if paths["patch"].stat().st_size == 0:
        fail(f"{where}: canonical patch is empty")
    return receipt, paths


def validate_current_manifest(
    source: Path, manifest_path: Path, ignored_record: Any, where: str,
    volatile: set[bytes] | None = None,
) -> None:
    volatile = volatile or set()
    listed = subprocess.run(
        ["git", "-C", os.fspath(source), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        capture_output=True, check=True,
    ).stdout.split(b"\0")
    current = {name for name in listed if name}
    rows: dict[bytes, dict[str, Any]] = {}
    for number, line in enumerate(manifest_path.read_bytes().splitlines(), 1):
        try:
            row = json.loads(line, object_pairs_hook=strict_pairs)
        except (UnicodeError, json.JSONDecodeError) as error:
            fail(f"{where}:{number}: invalid JSON: {error}")
        row = exact(row, {"mode", "path", "sha256", "size"}, f"{where}:{number}")
        if not isinstance(row["path"], str):
            fail(f"{where}:{number}: path is not text")
        raw = unquote_to_bytes(row["path"])
        if quote_from_bytes(raw, safe="/-._~") != row["path"] or raw in rows:
            fail(f"{where}:{number}: noncanonical/duplicate path")
        rows[raw] = row
    if set(rows) - volatile != current - volatile:
        fail(f"{where}: current source path set differs from freeze")
    staged_raw = subprocess.run(
        ["git", "-C", os.fspath(source), "ls-files", "--stage", "-z"],
        capture_output=True, check=True,
    ).stdout.split(b"\0")
    tracked_modes: dict[bytes, str] = {}
    for item in staged_raw:
        if item:
            header, name = item.split(b"\t", 1)
            tracked_modes[name] = header.split(b" ", 1)[0].decode("ascii")
    for raw, row in rows.items():
        if raw in volatile:
            continue
        lexical = source / Path(os.fsdecode(raw))
        if lexical.is_symlink():
            payload = os.fsencode(os.readlink(lexical))
            mode = "120000"
        elif lexical.is_file():
            payload = lexical.read_bytes()
            mode = tracked_modes.get(raw, "100755" if os.access(lexical, os.X_OK) else "100644")
        else:
            fail(f"{where}: missing/non-file current path: {os.fsdecode(raw)}")
        if (row["mode"], row["size"], row["sha256"]) != (
            mode, len(payload), hashlib.sha256(payload).hexdigest()
        ):
            fail(f"{where}: current source identity differs: {os.fsdecode(raw)}")
    # Generated evidence is intentionally ignored and is produced after source
    # freeze, so its path set may grow. Validate the frozen ignored-set record's
    # shape, while the exact non-ignored source manifest above remains immutable.
    ignored = exact(
        ignored_record, {"policy", "count", "nul_list_sha256"}, where + ".ignored"
    )
    if (ignored["policy"] != "excluded by the repository's standard Git ignore rules"
            or not isinstance(ignored["count"], int) or isinstance(ignored["count"], bool)
            or ignored["count"] < 0 or not isinstance(ignored["nul_list_sha256"], str)
            or SHA_RE.fullmatch(ignored["nul_list_sha256"]) is None):
        fail(f"{where}: invalid frozen ignored-path record")


def validate_release_freeze(
    ctx: Context, section: Any, created: dt.datetime
) -> tuple[str, str]:
    ref = exact(section, {"receipt"}, "source_freeze")
    release_path = ctx.external_file_ref(ref["receipt"], "source_freeze.receipt")
    release = exact(
        load_json(release_path, "release source-freeze receipt"),
        {"schema", "verdict", "created_utc", "project", "upstream", "coverage", "final_paired_resnapshot", "checks"},
        "release source-freeze receipt",
    )
    if release["schema"] != 1 or release["verdict"] != "PASS":
        fail("release source-freeze receipt is not schema-1 PASS")
    release_time = parse_time(release["created_utc"], "release source-freeze receipt.created_utc")
    if release_time > created or release_time > ctx.now or (ctx.now - release_time).total_seconds() > ctx.max_age:
        fail("release source-freeze receipt is future-dated, stale, or postdates candidate")
    checks = exact(release["checks"], RELEASE_CHECKS, "release source-freeze receipt.checks")
    if any(value is not True for value in checks.values()):
        fail("release source-freeze checks are not all true")
    coverage = exact(
        release["coverage"], {
            "policy", "required_paths", "required_paths_present",
            "required_upstream_paths", "required_upstream_paths_present",
            "volatile_generated_outputs",
        },
        "release source-freeze receipt.coverage",
    )
    required = coverage["required_paths"]
    required_upstream = coverage["required_upstream_paths"]
    if (not isinstance(required, list) or len(required) != len(set(required))
            or coverage["required_paths_present"] != len(required)
            or not isinstance(required_upstream, list)
            or len(required_upstream) != len(set(required_upstream))
            or coverage["required_upstream_paths_present"] != len(required_upstream)):
        fail("release source-freeze coverage is invalid")
    if coverage["policy"] != "all project+upstream source byte-exact; exact generator-owned outputs independently post-bound":
        fail("release source-freeze coverage policy drift")
    volatile = coverage["volatile_generated_outputs"]
    if volatile != list(VOLATILE_GENERATED_OUTPUTS):
        fail("release source-freeze volatile generated-output policy drift")
    paired = exact(
        release["final_paired_resnapshot"], {"policy", "order", "checks_per_root"},
        "release source-freeze receipt.final_paired_resnapshot",
    )
    if paired != {
        "policy": "nested overlapping live resnapshots immediately before publication",
        "order": ["project", "upstream", "upstream", "project"],
        "checks_per_root": 2,
    }:
        fail("release source-freeze paired-resnapshot contract drift")
    mandatory = {
        "harness/run.sh", "scripts/dashboard.sh", "scripts/deps/opensubdiv.sh",
        "scripts/finalize-wasm-split.py",
        "platform_web/ghost/GHOST_ContextWGPUWeb.cc",
        "platform_web/shell/boot-windowed.js", "platform_web/shell/file-bridge.js",
        "platform_web/shell/wgpu-preinit-worker.js",
        "sandbox/m8-staged-deploy/make_staged_bundle.sh",
        "sandbox/m8-staged-deploy/stage_pack.py",
        "sandbox/m8-staged-deploy/stage_provenance.py",
        "sandbox/m8-staged-deploy/prepare_split_inventory.py",
        "sandbox/m8-staged-deploy/public_shell_hardening.py",
        "sandbox/m8-staged-deploy/stage1-loader.js",
        "sandbox/m8-staged-deploy/service-worker.js",
        "sandbox/m8-staged-deploy/service-worker-register.js",
        "sandbox/m8-staged-deploy/transport_contract.py",
        "sandbox/m8-staged-deploy/verify_staged.mjs",
        "sandbox/m8-staged-deploy/verify_public_query_hardening.mjs",
        "sandbox/m8-staged-deploy/verify_update_transition.mjs",
        "sandbox/m8-deploy/_headers",
        "sandbox/m8-staged-deploy/serve_measure.py",
        "sandbox/m8-launch-gate/verify_m8.py",
        "sandbox/m8-launch-gate/bundle_identity.mjs",
        "sandbox/m8-launch-gate/make_staged_receipt.py",
        "sandbox/m8-launch-gate/measure_current.mjs",
        "sandbox/m8-launch-gate/browser_matrix.mjs",
        "sandbox/m8-launch-gate/runtime_evidence.mjs",
        "sandbox/m8-launch-gate/runtime_evidence_selfcheck.mjs",
        "sandbox/m8-launch-gate/verify_product_bar.mjs",
        "sandbox/m8-launch-gate/soak_current.mjs",
        "sandbox/m8-launch-gate/audit_compliance.py",
        "sandbox/m8-launch-gate/test_technical_receipt_contracts.py",
        "sandbox/m7-product-gate/run.sh", "sandbox/m7-product-gate/verify_m7.py",
        "sandbox/m7-product-gate/fallback_receipt.schema.json",
        "sandbox/m7-product-gate/capture_fallback.py",
        "sandbox/m7-product-gate/verify_files.mjs",
        "sandbox/m7-product-gate/verify_bundle_sources.py",
        "sandbox/m7-usd-prep/verify_browser_usd.mjs",
        "sandbox/m7-usd-prep/make_native_receipt.py",
        "sandbox/m7-io-smoke/export_scene.py",
        "sandbox/m7-io-smoke/roundtrip_scene.py",
        "sandbox/m7-io-smoke/parse_obj.py",
        "sandbox/m7-io-smoke/parse_glb.py",
        "sandbox/final-m0-m6/verify.py", "sandbox/final-m0-m6/compose.py",
        "sandbox/final-m0-m3/verify.py", "sandbox/final-m0-m3/compose.py",
        "sandbox/final-m0-m3/compose_selfcheck.py", "sandbox/final-m0-m3/selfcheck.py",
        "sandbox/final-m0-m3/run_m0.py", "sandbox/final-m0-m3/run_m1.py",
        "sandbox/final-m0-m3/run_m2.py", "sandbox/final-m0-m3/run_m2_deps.py",
        "sandbox/final-m0-m3/run_m3.py", "sandbox/final-m0-m3/runner_selfcheck.py",
        "sandbox/final-m0-m3/gpu_webgpu_tests.txt",
        "sandbox/final-m0-m3/static_shader_identities.txt",
        "sandbox/final-m0-m3/strict_final_adapter.py",
        "sandbox/final-m0-m3/strict_final_adapter_selfcheck.py",
        "sandbox/m4-d9-gate/capture_m4.mjs", "sandbox/m4-d9-gate/bind_current.py",
        "sandbox/m4-d9-gate/verify_current_binding.py",
        "sandbox/m5-final/verify_m5.py", "sandbox/m5-final/runtime-artifacts.mjs",
        "sandbox/gpu-r61/workbench-preview/run_matrix.sh",
        "sandbox/gpu-r61/workbench-preview/drive_workbench_case.mjs",
        "sandbox/gpu-r61/eevee-matrix-preview/run_eevee_matrix.mjs",
        "sandbox/gpu-r61/f12-eevee-acceptance/drive_eevee_f12.mjs",
        "sandbox/gpu-r61/cycles-windowed/drive_cycles_f12.mjs",
        "sandbox/m6-prep/run_wasm_cycles.sh",
        "sandbox/m6-prep/verify_render_closeout.py",
        "sandbox/dawn-probe/build.sh",
    }
    if not mandatory.issubset(set(required)):
        fail("release source-freeze coverage omits aggregate technical inputs")
    mandatory_upstream = {
        "CMakeLists.txt", "build_files/cmake/testing.cmake",
        "source/blender/blenlib/CMakeLists.txt",
        "source/blender/blenlib/intern/path_utils.cc",
        "source/blender/blenlib/intern/expr_pylike_eval.cc",
        "source/blender/blenlib/tests/BLI_fileops_test.cc",
        "source/blender/blenlib/tests/BLI_expr_pylike_eval_test.cc",
        "source/blender/bmesh/CMakeLists.txt",
        "intern/ghost/intern/GHOST_ContextWGPU.cc",
        "intern/ghost/intern/GHOST_ContextWGPU.hh",
        "intern/opensubdiv/CMakeLists.txt",
        "intern/opensubdiv/internal/evaluator/eval_output_gpu.h",
        "intern/opensubdiv/internal/evaluator/evaluator_capi.cc",
        "intern/opensubdiv/internal/evaluator/gpu_compute_evaluator.cc",
        "source/blender/gpu/CMakeLists.txt",
        "source/blender/gpu/webgpu/wgpu_context.cc",
        "source/blender/gpu/webgpu/wgpu_context.hh",
        "source/blender/gpu/webgpu/wgpu_framebuffer.cc",
        "source/blender/gpu/webgpu/wgpu_texture.cc",
        "source/blender/gpu/webgpu/wgpu_texture.hh",
        "source/blender/gpu/webgpu/wgpu_shader.cc",
        "source/blender/gpu/webgpu/wgpu_shader.hh",
        "source/blender/gpu/webgpu/wgpu_shader_cache.cc",
        "source/blender/gpu/webgpu/wgpu_shader_compiler.cc",
        "source/blender/gpu/webgpu/wgpu_shader_interface_map.cc",
        "source/blender/gpu/webgpu/wgpu_vertex_buffer.cc",
        "source/blender/gpu/webgpu/wgpu_vertex_buffer.hh",
        "source/blender/gpu/intern/gpu_shader_create_info.cc",
        "source/blender/gpu/intern/gpu_shader_dependency.cc",
        "source/blender/gpu/metal/kernels/gpu_shader_fullscreen_blit_infos.hh",
        "source/blender/gpu/shaders/infos/gpu_shader_test_infos.hh",
        "source/blender/gpu/tests/gpu_testing.hh",
        "source/blender/gpu/tests/framebuffer_test.cc",
        "source/blender/gpu/tests/shaders/gpu_texture_atomic_test.glsl",
        "source/blender/gpu/tests/shaders/CMakeLists.txt",
        "source/blender/gpu/tests/shaders/gpu_framebuffer_subpass_input_test.glsl",
        "source/blender/gpu/tests/shader_test.cc",
        "source/blender/gpu/tests/shader_create_info_test.cc",
        "source/blender/gpu/tests/texture_test.cc",
        "source/blender/draw/CMakeLists.txt",
        "source/blender/draw/intern/DRW_gpu_wrapper.hh",
        "source/blender/draw/intern/draw_debug.cc",
        "source/blender/draw/intern/draw_shader.cc",
        "source/blender/draw/intern/draw_shader.hh",
        "source/blender/draw/intern/shaders/draw_debug_infos.hh",
        "source/blender/draw/intern/shaders/draw_debug_draw_display_vert.glsl",
        "source/blender/draw/intern/shaders/draw_debug_draw_compact_comp.glsl",
        "source/blender/draw/tests/draw_testing.cc",
        "source/blender/draw/tests/draw_testing.hh",
        "source/blender/draw/tests/draw_debug_test.cc",
        "source/blender/draw/intern/draw_cache_impl_curves.cc",
        "source/blender/draw/intern/draw_cache_impl_particles.cc",
        "source/blender/draw/intern/draw_curves.cc",
        "source/blender/draw/intern/draw_curves_defines.hh",
        "source/blender/draw/intern/draw_hair_private.hh",
        "source/blender/draw/intern/shaders/draw_curves_infos.hh",
        "source/blender/draw/intern/shaders/draw_curves_interpolation_comp.glsl",
        "source/blender/draw/intern/shaders/draw_curves_test.glsl",
        "source/blender/draw/tests/draw_curves_test.cc",
        "source/blender/draw/intern/draw_cache_impl_subdivision.cc",
        "source/blender/draw/intern/shaders/subdiv_patch_eval_infos.hh",
        "source/blender/draw/intern/shaders/subdiv_patch_evaluation_comp.glsl",
    }
    if not mandatory_upstream.issubset(set(required_upstream)):
        fail("release source-freeze coverage omits upstream parity inputs")

    child_hashes: dict[str, str] = {}
    for name, expected_source in (("project", ctx.root), ("upstream", ctx.root / "upstream")):
        component = exact(
            release[name], {"directory", "receipt_sha256", "patch", "live_manifest"},
            f"release source-freeze receipt.{name}",
        )
        if component["directory"] != name:
            fail(f"release source-freeze {name} directory drift")
        child_path = release_path.parent / name / "receipt.json"
        child_path = ctx.external_file_ref(
            {
                "path": os.fspath(child_path), "bytes": child_path.stat().st_size,
                "sha256": component["receipt_sha256"],
            },
            f"release source-freeze {name} receipt",
        )
        child, paths = validate_component_receipt(
            ctx, child_path, expected_source, f"release source-freeze {name} receipt"
        )
        if name == "project":
            validate_current_manifest(
                expected_source, paths["live_manifest"], child["ignored_worktree_paths"],
                "release source-freeze project manifest",
                {os.fsencode(item) for item in VOLATILE_GENERATED_OUTPUTS},
            )
            frozen_names = {
                unquote_to_bytes(json.loads(line, object_pairs_hook=strict_pairs)["path"]).decode(
                    "utf-8", "surrogateescape"
                )
                for line in paths["live_manifest"].read_bytes().splitlines()
            }
            if not set(required).issubset(frozen_names):
                fail("release source-freeze asserted coverage is absent from project manifest")
        for key in ("patch", "live_manifest"):
            if component[key] != child[key] or sha256(paths[key]) != component[key]["sha256"]:
                fail(f"release source-freeze {name} {key} binding drift")
        child_hashes[name] = sha256(child_path)
    return sha256(release_path), child_hashes["upstream"]


def run_gate(command: list[str], cwd: Path, env: dict[str, str], prefix: str, where: str) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    output = (result.stdout + result.stderr).strip()
    lines = [line for line in output.splitlines() if line.strip()]
    if result.returncode != 0:
        fail(f"{where}: verifier failed rc={result.returncode}: {output[-2000:]}")
    if not lines or not lines[-1].startswith(prefix):
        fail(f"{where}: verifier output lacks exact PASS prefix")
    return lines[-1]


def snapshot_reference_graph(ctx: Context, document_path: Path, where: str) -> None:
    """Snapshot every repository file identity reachable from JSON file refs."""
    seen_json: set[Path] = set()

    def inspect(value: Any, location: str, base: Path) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                inspect(item, f"{location}[{index}]", base)
            return
        if not isinstance(value, dict):
            return
        if {"path", "bytes", "sha256"}.issubset(value):
            raw = value.get("path")
            if not isinstance(raw, str):
                fail(f"{location}: file-ref path is not text")
            lexical = Path(raw)
            if lexical.is_absolute():
                try:
                    relative = lexical.absolute().relative_to(ctx.root)
                except ValueError:
                    fail(f"{location}: referenced evidence escapes repository")
                normalized = relative.as_posix()
            else:
                root_candidate = ctx.root / lexical
                local_candidate = base / lexical
                selected = root_candidate if root_candidate.exists() else local_candidate
                try:
                    normalized = selected.absolute().relative_to(ctx.root).as_posix()
                except ValueError:
                    fail(f"{location}: referenced evidence escapes repository")
            path = ctx.file_ref(
                {"path": normalized, "bytes": value["bytes"], "sha256": value["sha256"]},
                location,
            )
            if path.suffix == ".json" and path not in seen_json:
                seen_json.add(path)
                inspect(load_json(path, location), location, path.parent)
        for key, item in value.items():
            inspect(item, f"{location}.{key}", base)

    if document_path not in seen_json:
        seen_json.add(document_path)
        inspect(load_json(document_path, where), where, document_path.parent)


def validate_m8_technical(
    ctx: Context, section: Any, generated: dict[str, Any]
) -> tuple[str, str]:
    """Bind every current M8 input, then run its authoritative post-receipt gate."""
    row = exact(
        section, {"verifier", "evidence", "evidence_trees", "result", "dashboard"},
        "m8_technical",
    )
    if row["result"] != generated["ledger/results/m8.json"]:
        fail("m8_technical.result differs from the aggregate generated-output binding")
    if row["dashboard"] != generated["reports/dashboard.md"]:
        fail("m8_technical.dashboard differs from the aggregate generated-output binding")
    ctx.file_ref(
        row["result"], "m8_technical.result", "ledger/results/m8.json"
    )
    ctx.file_ref(
        row["dashboard"], "m8_technical.dashboard", "reports/dashboard.md"
    )
    verifier = ctx.file_ref(
        row["verifier"], "m8_technical.verifier",
        "sandbox/m8-launch-gate/verify_m8.py",
    )
    evidence = exact(row["evidence"], set(M8_TECHNICAL_INPUTS), "m8_technical.evidence")
    evidence_paths: dict[str, Path] = {}
    for name, expected in M8_TECHNICAL_INPUTS.items():
        path = ctx.file_ref(evidence[name], f"m8_technical.evidence.{name}", expected)
        evidence_paths[name] = path
        if path.suffix == ".json":
            snapshot_reference_graph(ctx, path, f"M8 {name} evidence graph")

    tree_rows = exact(
        row["evidence_trees"], set(M8_TECHNICAL_TREES), "m8_technical.evidence_trees"
    )
    for name, (expected, excluded) in M8_TECHNICAL_TREES.items():
        ctx.projected_tree_ref(
            tree_rows[name], f"m8_technical.evidence_trees.{name}", expected, excluded
        )

    # Receipt artifact rows intentionally omit paths. Resolve their exact names
    # under the authoritative build/deploy roots and snapshot those bytes before
    # the subprocess; the authoritative M8 verifier independently requires the
    # row sets to equal build_files()/bundle_files().
    staged_doc = load_json(evidence_paths["staged_receipt"], "M8 staged receipt")
    if not isinstance(staged_doc, dict):
        fail("M8 staged receipt is not an object")
    for key, base in (
        ("source_artifacts", "build-wasm-windowed-opt/bin"),
        ("bundle_artifacts", "sandbox/m8-staged-deploy/bundle-staged"),
    ):
        artifacts = staged_doc.get(key)
        if not isinstance(artifacts, dict) or not artifacts:
            fail(f"M8 staged receipt {key} is absent/empty")
        for name, identity_row in artifacts.items():
            if (not isinstance(name, str) or PurePosixPath(name).is_absolute()
                    or any(part in {"", ".", ".."} for part in PurePosixPath(name).parts)):
                fail(f"M8 staged receipt has unsafe {key} name: {name!r}")
            identity_row = exact(identity_row, {"bytes", "sha256"}, f"M8 {key}.{name}")
            artifact_path = ctx.path(f"{base}/{name}", f"M8 {key}.{name}.path")
            if (identity_row["bytes"], identity_row["sha256"]) != (
                artifact_path.stat().st_size, sha256(artifact_path)
            ):
                fail(f"M8 {key} current artifact identity differs: {name}")
            ctx.snapshot(artifact_path)

    output = run_gate(
        [sys.executable, os.fspath(verifier), "--post-receipt"],
        ctx.root, os.environ.copy(), "M8_TECHNICAL_POST_RECEIPT_PASS ", "M8",
    )
    # The authoritative verifier deliberately regenerates this diagnostic output.
    # Snapshot it after the successful run, bind its hash into our verification
    # receipt, and recheck it with every pre-existing M8 input below.
    preflight = ctx.path(
        "sandbox/m8-launch-gate/artifacts/current-m8-preflight.json",
        "M8 post-receipt preflight",
    )
    ctx.snapshot(preflight)
    preflight_doc = exact(
        load_json(preflight, "M8 post-receipt preflight"),
        {
            "schema", "checked_at", "mode", "technical_pass", "post_receipt_pass",
            "external_launch_pass", "external_verification_deferred",
            "external_verification_reason", "launch_ready", "technical_failures",
            "post_receipt_failures", "external_blockers",
        },
        "M8 post-receipt preflight",
    )
    if (preflight_doc["schema"] != 1
            or preflight_doc["mode"] != "technical_post_receipt"
            or preflight_doc["technical_pass"] is not True
            or preflight_doc["post_receipt_pass"] is not True
            or preflight_doc["external_launch_pass"] is not None
            or preflight_doc["external_verification_deferred"] is not None
            or preflight_doc["external_verification_reason"] is not None
            or preflight_doc["launch_ready"] is not False
            or preflight_doc["technical_failures"] != []
            or preflight_doc["post_receipt_failures"] != []
            or preflight_doc["external_blockers"] != []
            or not isinstance(preflight_doc["checked_at"], str)):
        fail("M8 post-receipt preflight is not an exact technical PASS")
    return output, sha256(preflight)


def validate_m7_technical(ctx: Context, section: Any, label: str) -> str:
    """Bind every ignored M7 proof and rerun the strict gate at one release label."""
    row = exact(section, {"verifier", "evidence", "evidence_trees"}, "m7_technical")
    verifier = ctx.file_ref(
        row["verifier"], "m7_technical.verifier", "sandbox/m7-product-gate/verify_m7.py"
    )
    evidence = exact(row["evidence"], set(M7_TECHNICAL_INPUTS), "m7_technical.evidence")
    for name, expected in M7_TECHNICAL_INPUTS.items():
        path = ctx.file_ref(evidence[name], f"m7_technical.evidence.{name}", expected)
        if path.suffix == ".json":
            snapshot_reference_graph(ctx, path, f"M7 {name} evidence graph")
    trees = exact(
        row["evidence_trees"], {"fallback", "usd_browser", "usd_native"},
        "m7_technical.evidence_trees",
    )
    expected_trees = {
        "fallback": f"sandbox/m7-product-gate/fallback-evidence/{label}",
        "usd_browser": f"sandbox/m7-usd-prep/browser-roundtrip/{label}",
        "usd_native": f"sandbox/m7-usd-prep/native-capability/{label}",
    }
    for name, expected in expected_trees.items():
        ctx.tree_ref(trees[name], f"m7_technical.evidence_trees.{name}", expected)
    env = os.environ.copy()
    env["FINAL_RUN_LABEL"] = label
    return run_gate(
        [sys.executable, os.fspath(verifier), "--release-label", label],
        ctx.root, env, "M7_STRICT_PASS ", "M7",
    )


def verify(root: Path, manifest_path: Path, now: dt.datetime, max_age: int) -> dict[str, Any]:
    ctx = Context(root, now, max_age)
    lexical_manifest = manifest_path if manifest_path.is_absolute() else ctx.root / manifest_path
    try:
        relative_manifest = lexical_manifest.absolute().relative_to(ctx.root)
    except ValueError:
        fail("candidate manifest escapes repository")
    manifest_path = ctx.path(relative_manifest.as_posix(), "candidate manifest path")
    ctx.snapshot(manifest_path)
    candidate = exact(
        load_json(manifest_path, "candidate manifest"),
        {"schema", "verdict", "run_label", "created_utc", "source_freeze", "m0_m3", "artifacts", "milestones", "m7_technical", "m8_technical", "generated_outputs"},
        "candidate manifest",
    )
    if candidate["schema"] != SCHEMA or candidate["verdict"] != "PASS":
        fail("candidate manifest must be schema-1 PASS")
    label = candidate["run_label"]
    if not isinstance(label, str) or LABEL_RE.fullmatch(label) is None:
        fail("candidate manifest has unsafe run label")
    created = parse_time(candidate["created_utc"], "candidate manifest.created_utc")
    if created > now or (now - created).total_seconds() > max_age:
        fail("candidate manifest is future-dated or stale")
    release_freeze_hash, upstream_freeze_hash = validate_release_freeze(
        ctx, candidate["source_freeze"], created
    )
    generated = exact(
        candidate["generated_outputs"], set(VOLATILE_GENERATED_OUTPUTS),
        "generated_outputs",
    )
    for relative in VOLATILE_GENERATED_OUTPUTS:
        path = ctx.file_ref(generated[relative], f"generated_outputs.{relative}", relative)
        if relative.startswith("ledger/results/"):
            result = load_json(path, f"generated output {relative}")
            stem = Path(relative).stem
            if (not isinstance(result, dict) or result.get("scope") != stem
                    or result.get("pass") is not True):
                fail(f"generated result is not an exact-scope PASS: {relative}")

    m03 = exact(candidate["m0_m3"], {"manifest", "verifier"}, "m0_m3")
    m03_manifest = ctx.file_ref(m03["manifest"], "m0_m3.manifest")
    m03_verifier = ctx.file_ref(m03["verifier"], "m0_m3.verifier", "sandbox/final-m0-m3/verify.py")
    m03_candidate = load_json(m03_manifest, "M0-M3 manifest")
    snapshot_reference_graph(ctx, m03_manifest, "M0-M3 manifest graph")
    if m03_candidate.get("run_label") != label:
        fail("M0-M3 manifest uses another run label")
    freeze_ref = m03_candidate.get("source_freeze", {}).get("receipt")
    freeze_path = ctx.file_ref(freeze_ref, "M0-M3 source-freeze receipt")
    if sha256(freeze_path) != upstream_freeze_hash:
        fail("M0-M3 source-freeze receipt differs from composite upstream component")
    freeze = load_json(freeze_path, "source-freeze receipt")
    freeze_time = parse_time(freeze.get("created_utc"), "source-freeze receipt.created_utc")
    if created < freeze_time:
        fail("candidate manifest predates source freeze")
    # The strict M0-M3 verifier prints a multi-line JSON object instead of a
    # one-line PASS marker, so validate its complete stdout directly.
    full_m03 = subprocess.run(
        [sys.executable, os.fspath(m03_verifier), "--root", os.fspath(ctx.root), "--manifest", os.fspath(m03_manifest), "--max-age-seconds", str(max_age), "--now", now.isoformat().replace("+00:00", "Z")],
        cwd=ctx.root, text=True, capture_output=True, check=False,
    )
    if full_m03.returncode != 0:
        fail("M0-M3 verifier changed result during closeout")
    try:
        m03_result = json.loads(full_m03.stdout, object_pairs_hook=strict_pairs)
    except json.JSONDecodeError as error:
        fail(f"M0-M3 verifier returned invalid JSON: {error}")
    if (m03_result.get("verdict") != "PASS" or m03_result.get("run_label") != label
            or m03_result.get("source_freeze_sha256") != upstream_freeze_hash):
        fail("M0-M3 verifier result is not bound to this candidate")

    artifact_hashes = validate_split_inventory(ctx, candidate["artifacts"])
    milestones = exact(candidate["milestones"], {"m4", "m5", "m6"}, "milestones")
    outputs: dict[str, str] = {}

    m4 = exact(milestones["m4"], {"verifier", "binding"}, "milestones.m4")
    m4_verifier = ctx.file_ref(m4["verifier"], "milestones.m4.verifier", "sandbox/m4-d9-gate/verify_current_binding.py")
    m4_binding = ctx.file_ref(m4["binding"], "milestones.m4.binding")
    if load_json(m4_binding, "M4 binding").get("run") != f"{label}.m4":
        fail("M4 binding does not use the final run label")
    snapshot_reference_graph(ctx, m4_binding, "M4 binding graph")
    env = os.environ.copy()
    env["M4_BINDING"] = os.fspath(m4_binding)
    env["BW_DEFERRED_WASM_FILENAME"] = artifact_hashes["deferred_filename"]
    outputs["m4"] = run_gate([sys.executable, os.fspath(m4_verifier)], ctx.root, env, MILESTONE_PREFIXES["m4"], "M4")

    m5 = exact(milestones["m5"], {"verifier", "click", "canvas", "latency"}, "milestones.m5")
    m5_verifier = ctx.file_ref(m5["verifier"], "milestones.m5.verifier", "sandbox/m5-final/verify_m5.py")
    env = os.environ.copy()
    m5_roots = {
        "click": "sandbox/m5-click-pick/evidence",
        "canvas": "sandbox/m5-canvas-smoke/evidence",
        "latency": "sandbox/m5-latency/evidence",
    }
    for kind, suffix in (("click", "click"), ("canvas", "canvas"), ("latency", "latency")):
        row = exact(m5[kind], {"run_label", "receipt_sha256"}, f"milestones.m5.{kind}")
        expected_label = f"{label}.m5-{suffix}"
        if row["run_label"] != expected_label or not isinstance(row["receipt_sha256"], str) or SHA_RE.fullmatch(row["receipt_sha256"]) is None:
            fail(f"M5 {kind} selector is not the final immutable run")
        env[f"M5_{kind.upper()}_RUN_LABEL"] = row["run_label"]
        env[f"M5_{kind.upper()}_RECEIPT_SHA256"] = row["receipt_sha256"]
        receipt_relative = f"{m5_roots[kind]}/{row['run_label']}/receipt.json"
        receipt_path = ctx.path(receipt_relative, f"milestones.m5.{kind}.receipt")
        if sha256(receipt_path) != row["receipt_sha256"]:
            fail(f"M5 {kind} receipt SHA-256 selector is stale")
        ctx.snapshot(receipt_path)
        snapshot_reference_graph(ctx, receipt_path, f"M5 {kind} receipt graph")
        digest_path = ctx.path(
            f"{m5_roots[kind]}/{row['run_label']}/receipt.sha256",
            f"milestones.m5.{kind}.receipt_sha256",
        )
        ctx.snapshot(digest_path)
    env["BW_DEFERRED_WASM_FILENAME"] = artifact_hashes["deferred_filename"]
    outputs["m5"] = run_gate([sys.executable, os.fspath(m5_verifier)], ctx.root, env, MILESTONE_PREFIXES["m5"], "M5")

    m6 = exact(milestones["m6"], {"verifier", "workbench", "eevee", "cycles_smoke", "cycles_suite"}, "milestones.m6")
    m6_verifier = ctx.file_ref(m6["verifier"], "milestones.m6.verifier", "sandbox/m6-prep/verify_render_closeout.py")
    expected_m6 = {
        "workbench": f"{label}.m6-workbench", "eevee": f"{label}.m6-eevee",
        "cycles_smoke": f"{label}.m6-cycles-smoke", "cycles_suite": f"{label}.m6-cycles-suite",
    }
    m6_rows: dict[str, dict[str, Any]] = {}
    for key, expected in expected_m6.items():
        keys = {"run_label", "evidence", "evidence_tree"} if key == "cycles_smoke" else {
            "run_label", "evidence"
        }
        row = exact(m6[key], keys, f"milestones.m6.{key}")
        if row["run_label"] != expected:
            fail(f"M6 {key} selector is not the final immutable run")
        m6_rows[key] = row
    ctx.tree_ref(
        m6_rows["workbench"]["evidence"], "milestones.m6.workbench.evidence",
        f"sandbox/gpu-r61/workbench-preview/runs/{expected_m6['workbench']}",
    )
    ctx.tree_ref(
        m6_rows["eevee"]["evidence"], "milestones.m6.eevee.evidence",
        f"sandbox/gpu-r61/eevee-matrix-preview/runs/{expected_m6['eevee']}",
    )
    cycles_smoke_manifest = ctx.file_ref(
        m6_rows["cycles_smoke"]["evidence"], "milestones.m6.cycles_smoke.evidence",
        f"sandbox/gpu-r61/cycles-windowed/evidence/{expected_m6['cycles_smoke']}-manifest.json",
    )
    snapshot_reference_graph(ctx, cycles_smoke_manifest, "M6 Cycles smoke evidence graph")
    ctx.tree_ref(
        m6_rows["cycles_smoke"]["evidence_tree"],
        "milestones.m6.cycles_smoke.evidence_tree",
        "sandbox/gpu-r61/cycles-windowed/evidence",
    )
    ctx.tree_ref(
        m6_rows["cycles_suite"]["evidence"], "milestones.m6.cycles_suite.evidence",
        f"sandbox/m6-prep/cycles-runs/{expected_m6['cycles_suite']}",
    )
    env = os.environ.copy()
    env.update({
        "M6_WORKBENCH_RUN": m6_rows["workbench"]["run_label"],
        "M6_EEVEE_RUN": m6_rows["eevee"]["run_label"],
        "M6_CYCLES_SMOKE": m6_rows["cycles_smoke"]["run_label"],
        "M6_CYCLES_RESULTS": m6_rows["cycles_suite"]["run_label"],
        "BW_DEFERRED_WASM_FILENAME": artifact_hashes["deferred_filename"],
    })
    outputs["m6"] = run_gate([sys.executable, os.fspath(m6_verifier)], ctx.root, env, MILESTONE_PREFIXES["m6"], "M6")

    outputs["m7"] = validate_m7_technical(ctx, candidate["m7_technical"], label)

    outputs["m8"], m8_preflight_hash = validate_m8_technical(
        ctx, candidate["m8_technical"], generated
    )

    # Recheck artifacts after all live comparators to detect a concurrent replacement.
    if validate_split_inventory(ctx, candidate["artifacts"]) != artifact_hashes:
        fail("release artifacts changed during verification")
    ctx.recheck_snapshots()
    candidate_identity = {
        "bytes": manifest_path.stat().st_size, "sha256": sha256(manifest_path),
    }
    return {
        "schema": 1, "verdict": "PASS", "run_label": label,
        "source_freeze_sha256": release_freeze_hash,
        "m0_m3_source_freeze_sha256": upstream_freeze_hash,
        "artifact_sha256": artifact_hashes,
        "milestone_output": outputs,
        "m8_post_receipt_preflight_sha256": m8_preflight_hash,
        "candidate_manifest": candidate_identity,
        "verification_closure": ctx.closure(manifest_path),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--max-age-seconds", type=int, default=MAX_AGE_SECONDS)
    parser.add_argument("--now", help="test-only UTC RFC3339 timestamp")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        now = parse_time(args.now, "--now") if args.now else dt.datetime.now(dt.timezone.utc)
        result = verify(args.root, args.manifest, now, args.max_age_seconds)
    except (VerificationError, OSError, subprocess.SubprocessError) as error:
        print(f"final-m0-m6: FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
