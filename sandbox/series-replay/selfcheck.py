#!/usr/bin/env python3
"""Hermetic mutation checks for the canonical fixed-path freeze receipt."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile


HERE = Path(__file__).resolve().parent
VERIFY_PATH = HERE / "verify.py"
SPEC = importlib.util.spec_from_file_location("series_replay_verify", VERIFY_PATH)
assert SPEC and SPEC.loader
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_receipt(path: Path, receipt: dict[str, object]) -> bytes:
    payload = json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.write_bytes(payload)
    return payload


def expect_rejection(
    receipt_path: Path,
    canonical_patch: Path,
    source: Path,
    pin_file: Path,
    expected_pin: str,
) -> None:
    try:
        verify.validate_canonical_freeze_receipt(
            receipt_path,
            canonical_patch,
            source,
            pin_file,
            expected_pin,
        )
    except verify.ReplayError:
        return
    raise AssertionError("invalid canonical freeze receipt was accepted")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="series-receipt-selfcheck-") as temporary:
        root = Path(temporary)
        source = root / "upstream"
        source.mkdir()

        expected_pin = "1" * 40
        pin_file = root / "PIN"
        pin_file.write_text(f"{expected_pin[:12]} fixture\n", encoding="utf-8")
        canonical_patch = root / "PREVIEW_SNAPSHOT.patch"
        canonical_bytes = b"diff --git a/file b/file\nfixture canonical patch\n"
        canonical_patch.write_bytes(canonical_bytes)
        receipt_path = root / "canonical-freeze-receipt.json"

        ignored_paths = b"ignored/cache.bin\0"
        manifest = {
            "bytes": 101,
            "entries": 2,
            "path": "live.manifest.jsonl",
            "sha256": "2" * 64,
        }
        base: dict[str, object] = {
            "checks": {name: True for name in verify.CANONICAL_RECEIPT_CHECKS},
            "created_utc": "2026-08-25T00:00:00Z",
            "expected_pin": expected_pin,
            "git_version": "git version fixture",
            "ignored_worktree_paths": {
                "count": ignored_paths.count(b"\0"),
                "nul_list_sha256": sha256(ignored_paths),
                "policy": "excluded by the repository's standard Git ignore rules",
            },
            "live_manifest": manifest,
            "patch": {
                "bytes": len(canonical_bytes),
                "path": "canonical-source.patch",
                "sha256": sha256(canonical_bytes),
            },
            "recorded_pin_file": {
                "path": os.fspath(pin_file.resolve()),
                "sha256": sha256(pin_file.read_bytes()),
            },
            "replay_manifest": {**manifest, "path": "replay.manifest.jsonl"},
            "schema": 1,
            "source": os.fspath(source.resolve()),
            "verdict": "PASS",
        }

        baseline_bytes = write_receipt(receipt_path, base)
        baseline_digest = verify.validate_canonical_freeze_receipt(
            receipt_path,
            canonical_patch,
            source,
            pin_file,
            expected_pin,
        )
        if baseline_digest != sha256(baseline_bytes):
            raise AssertionError("baseline receipt digest differs")

        mutations = 0

        def reject(mutator) -> None:
            nonlocal mutations
            candidate = copy.deepcopy(base)
            mutator(candidate)
            write_receipt(receipt_path, candidate)
            expect_rejection(receipt_path, canonical_patch, source, pin_file, expected_pin)
            mutations += 1

        reject(lambda value: value.__setitem__("verdict", "FAIL"))
        reject(lambda value: value.__setitem__("schema", True))
        reject(lambda value: value.__setitem__("expected_pin", "3" * 40))
        reject(lambda value: value.__setitem__("source", "relative/upstream"))
        reject(lambda value: value.__setitem__("created_utc", "not-a-time"))
        reject(lambda value: value.__setitem__("unexpected", True))
        reject(lambda value: value["checks"].__setitem__("source_head_exact_pin", False))
        reject(lambda value: value["checks"].pop("source_real_index_pristine"))
        reject(lambda value: value["patch"].__setitem__("bytes", len(canonical_bytes) + 1))
        reject(lambda value: value["patch"].__setitem__("sha256", "4" * 64))
        reject(lambda value: value["patch"].__setitem__("path", "PREVIEW_SNAPSHOT.patch"))
        reject(lambda value: value["live_manifest"].__setitem__("sha256", "5" * 64))
        reject(lambda value: value["recorded_pin_file"].__setitem__("sha256", "6" * 64))
        reject(lambda value: value["recorded_pin_file"].__setitem__("path", "/tmp/PIN"))
        reject(lambda value: value["ignored_worktree_paths"].__setitem__("count", -1))
        reject(
            lambda value: value["ignored_worktree_paths"].__setitem__(
                "nul_list_sha256", "not-a-digest"
            )
        )

        receipt_path.write_bytes(b"{malformed json\n")
        expect_rejection(receipt_path, canonical_patch, source, pin_file, expected_pin)
        mutations += 1

        write_receipt(receipt_path, base)
        canonical_patch.write_bytes(canonical_bytes + b"mutated\n")
        expect_rejection(receipt_path, canonical_patch, source, pin_file, expected_pin)
        canonical_patch.write_bytes(canonical_bytes)
        mutations += 1

        print(
            "CANONICAL_RECEIPT_SELFCHECK_PASS "
            f"mutations={mutations} receipt_sha256={baseline_digest[:12]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
