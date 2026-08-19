#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hermetic positive/adversarial checks for the production composer."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from typing import Callable


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("final_m0_m3_compose", HERE / "compose.py")
assert SPEC and SPEC.loader
composer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(composer)


def write(path: Path, payload: str | bytes, executable: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload.encode() if isinstance(payload, str) else payload)
    path.chmod(0o755 if executable else 0o644)
    return path


def write_json(path: Path, value: object) -> Path:
    return write(path, json.dumps(value, sort_keys=True, indent=2) + "\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def embedded(path: Path, *, entries: int | None = None) -> dict[str, object]:
    value: dict[str, object] = {
        "path": path.name, "bytes": path.stat().st_size, "sha256": digest(path)
    }
    if entries is not None:
        value["entries"] = entries
    return value


def build_fixture(root: Path, label: str, now: dt.datetime) -> tuple[argparse.Namespace, Path, str]:
    (root / "upstream").mkdir(parents=True)
    freeze_root = root / "external-freeze"
    component = freeze_root / "upstream"
    patch = write(component / "canonical-source.patch", "diff --git a/a b/a\n")
    live = write(component / "live.manifest.jsonl", '{"mode":"100644","path":"a","sha256":"' + "a" * 64 + '","size":1}\n')
    replay = write(component / "replay.manifest.jsonl", live.read_bytes())
    stamp = (now - dt.timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    child = write_json(component / "receipt.json", {
        "schema": 1, "verdict": "PASS", "created_utc": stamp,
        "source": str((root / "upstream").resolve()),
        "expected_pin": "f" * 40,
        "recorded_pin_file": {"path": "pin", "sha256": "b" * 64},
        "git_version": "git version fixture",
        "patch": embedded(patch), "live_manifest": embedded(live, entries=1),
        "replay_manifest": embedded(replay, entries=1),
        "ignored_worktree_paths": {"policy": "fixture", "count": 0, "nul_list_sha256": "c" * 64},
        "checks": {},
    })
    child_hash = digest(child)
    release = write_json(freeze_root / "receipt.json", {
        "schema": 1, "verdict": "PASS", "created_utc": stamp,
        "project": {},
        "upstream": {
            "directory": "upstream", "receipt_sha256": child_hash,
            "patch": embedded(patch), "live_manifest": embedded(live, entries=1),
        },
        "coverage": {
            "policy": "all project+upstream source byte-exact; exact generator-owned outputs independently post-bound",
            "required_paths": ["fixture"], "required_paths_present": 1,
            "required_upstream_paths": ["source/blender/blenlib/CMakeLists.txt"],
            "required_upstream_paths_present": 1,
            "volatile_generated_outputs": list(composer.VOLATILE_GENERATED_OUTPUTS),
        },
        "final_paired_resnapshot": {
            "policy": "nested overlapping live resnapshots immediately before publication",
            "order": ["project", "upstream", "upstream", "project"],
            "checks_per_root": 2,
        },
        "checks": {name: True for name in composer.RELEASE_CHECKS},
    })
    receipt_dir = root / "inputs"
    receipt_stamp = (now - dt.timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    receipts: dict[str, Path] = {}
    for name in composer.RECEIPT_NAMES:
        receipts[name] = write_json(receipt_dir / f"{name}.json", {
            "schema": 1, "verdict": "PASS", "run_label": label,
            "created_utc": receipt_stamp, "source_freeze_sha256": child_hash,
            "fixture_kind": name,
        })
    verifier = write(root / "stub_verify.py", """#!/usr/bin/env python3
import argparse,hashlib,json,pathlib
p=argparse.ArgumentParser();p.add_argument('--root');p.add_argument('--manifest');p.add_argument('--now');a=p.parse_args()
m=json.loads(pathlib.Path(a.manifest).read_text());f=pathlib.Path(a.root)/m['source_freeze']['receipt']['path']
print(json.dumps({'verdict':'PASS','run_label':m['run_label'],'source_freeze_sha256':hashlib.sha256(f.read_bytes()).hexdigest()}))
""", True)
    args = argparse.Namespace(
        root=root, run_label=label, release_freeze=release, output_dir=None,
        **{name: receipts[name].relative_to(root).as_posix() for name in composer.RECEIPT_NAMES},
    )
    return args, verifier, child_hash


def main() -> int:
    now = dt.datetime(2026, 8, 15, 16, 0, tzinfo=dt.timezone.utc)
    rejected: list[str] = []
    with tempfile.TemporaryDirectory(prefix="final-m0-m3-compose-") as temp:
        root = Path(temp)
        args, verifier, _ = build_fixture(root, "compose-fixture-r1", now)
        output_root = root / "sandbox/final-m0-m3/evidence"

        manifest = composer.compose(
            args, now=now, _canonical_root=root, _output_root=output_root, _verifier=verifier
        )
        assert manifest.is_file() and not (manifest.parent / "INCOMPLETE").exists()
        assert json.loads(manifest.read_text())["run_label"] == "compose-fixture-r1"

        def reject(name: str, operation: Callable[[], None]) -> None:
            try:
                operation()
            except (composer.ComposeError, OSError):
                rejected.append(name)
            else:
                raise AssertionError(f"negative fixture unexpectedly passed: {name}")

        reject("immutable_output_overwrite", lambda: composer.compose(
            args, now=now, _canonical_root=root, _output_root=output_root, _verifier=verifier
        ))

        args2, verifier2, _ = build_fixture(root / "mismatch", "compose-fixture-r2", now)
        bad_receipt = Path(args2.root) / args2.m1
        value = json.loads(bad_receipt.read_text())
        value["run_label"] = "historical-r0"
        write_json(bad_receipt, value)
        reject("mixed_run_label", lambda: composer.compose(
            args2, now=now, _canonical_root=Path(args2.root),
            _output_root=Path(args2.root) / "sandbox/final-m0-m3/evidence", _verifier=verifier2
        ))

        args3, verifier3, _ = build_fixture(root / "freeze-tamper", "compose-fixture-r3", now)
        release = json.loads(Path(args3.release_freeze).read_text())
        release["upstream"]["receipt_sha256"] = "0" * 64
        write_json(Path(args3.release_freeze), release)
        reject("composite_child_digest_tamper", lambda: composer.compose(
            args3, now=now, _canonical_root=Path(args3.root),
            _output_root=Path(args3.root) / "sandbox/final-m0-m3/evidence", _verifier=verifier3
        ))

        args4, verifier4, _ = build_fixture(root / "symlink", "compose-fixture-r4", now)
        real = Path(args4.root) / args4.m2
        link = real.with_name("m2-link.json")
        link.symlink_to(real.name)
        args4.m2 = link.relative_to(args4.root).as_posix()
        reject("symlink_receipt", lambda: composer.compose(
            args4, now=now, _canonical_root=Path(args4.root),
            _output_root=Path(args4.root) / "sandbox/final-m0-m3/evidence", _verifier=verifier4
        ))

        args5, verifier5, _ = build_fixture(root / "duplicate", "compose-fixture-r5", now)
        receipt = Path(args5.root) / args5.m3
        receipt.write_text(receipt.read_text().replace('  "schema": 1,', '  "schema": 1,\n  "schema": 1,', 1))
        reject("duplicate_receipt_key", lambda: composer.compose(
            args5, now=now, _canonical_root=Path(args5.root),
            _output_root=Path(args5.root) / "sandbox/final-m0-m3/evidence", _verifier=verifier5
        ))

        args6, _, _ = build_fixture(root / "verifier-red", "compose-fixture-r6", now)
        red = write(Path(args6.root) / "red.py", "import sys;print('RED');sys.exit(1)\n")
        reject("strict_verifier_rejection", lambda: composer.compose(
            args6, now=now, _canonical_root=Path(args6.root),
            _output_root=Path(args6.root) / "sandbox/final-m0-m3/evidence", _verifier=red
        ))
        assert (Path(args6.root) / "sandbox/final-m0-m3/evidence/compose-fixture-r6/INCOMPLETE").is_file()

    print(json.dumps({
        "schema": 1, "verdict": "PASS", "positive": 1,
        "negative": len(rejected), "negative_checks": rejected,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
