#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify the canonical source patch and optionally diagnose numbered history."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile


EXPECTED_PIN = "fbe6228777e7d9afefcd61a413844e790ae75db7"
RETIRED_PATCHES = {
    "0117-gpu-webgpu-diag-readback.patch",
    "0125-gpu-webgpu-render-result-bridge.patch",
}


class ReplayError(RuntimeError):
    pass


def run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise ReplayError(f"command failed ({result.returncode}): {' '.join(argv)}\n{stderr}")
    return result


def active_manifest(manifest_path: Path) -> list[str]:
    entries = [
        line.strip()
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(entries) != len(set(entries)):
        raise ReplayError(f"{manifest_path} contains duplicate active entries")
    return entries


def patch_paths(patch_path: Path) -> set[Path]:
    paths: set[Path] = set()
    for line in patch_path.read_text(encoding="utf-8", errors="surrogateescape").splitlines():
        if not line.startswith("diff --git "):
            continue
        fields = shlex.split(line)
        if len(fields) != 4:
            raise ReplayError(f"unsupported diff header in {patch_path.name}: {line}")
        for field, prefix in ((fields[2], "a/"), (fields[3], "b/")):
            if not field.startswith(prefix):
                raise ReplayError(f"unsafe diff path in {patch_path.name}: {field}")
            relative = Path(field[len(prefix) :])
            if relative.is_absolute() or ".." in relative.parts:
                raise ReplayError(f"unsafe diff path in {patch_path.name}: {relative}")
            paths.add(relative)
    if not paths:
        raise ReplayError(f"patch has no diff paths: {patch_path.name}")
    return paths


def dirty_paths(source: Path) -> set[Path]:
    payload = run(
        ["git", "-C", str(source), "status", "--porcelain=v1", "-z", "--untracked-files=all"]
    ).stdout
    records = payload.split(b"\0")
    paths: set[Path] = set()
    index = 0
    while index < len(records) and records[index]:
        record = records[index]
        if len(record) < 4:
            raise ReplayError("malformed porcelain status record")
        status_code = record[:2].decode("ascii", "strict")
        paths.add(Path(os.fsdecode(record[3:])))
        index += 1
        if "R" in status_code or "C" in status_code:
            if index >= len(records) or not records[index]:
                raise ReplayError("malformed rename/copy porcelain status record")
            paths.add(Path(os.fsdecode(records[index])))
            index += 1
    return paths


def fingerprint(path: Path) -> tuple[object, ...]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return ("missing",)
    mode = stat.S_IMODE(metadata.st_mode)
    if stat.S_ISLNK(metadata.st_mode):
        return ("symlink", mode, os.readlink(path))
    if stat.S_ISREG(metadata.st_mode):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return ("file", mode, metadata.st_size, digest)
    return ("other", stat.S_IFMT(metadata.st_mode), mode)


def extract_pin(source: Path, destination: Path) -> None:
    archive = subprocess.Popen(
        ["git", "-C", str(source), "archive", "--format=tar", EXPECTED_PIN],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert archive.stdout is not None
    extract = subprocess.run(
        ["tar", "-xf", "-", "-C", str(destination)],
        stdin=archive.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    archive.stdout.close()
    archive_stderr = archive.communicate()[1].decode("utf-8", "replace").strip()
    if archive.returncode != 0:
        raise ReplayError(f"git archive failed ({archive.returncode}): {archive_stderr}")
    if extract.returncode != 0:
        stderr = extract.stderr.decode("utf-8", "replace").strip()
        raise ReplayError(f"tar extraction failed ({extract.returncode}): {stderr}")


def main() -> int:
    if sys.argv[1:] not in (
        [],
        ["--canonical-only"],
        ["--preview-only"],
        ["--numbered-history"],
    ):
        raise ReplayError(
            "usage: verify.py [--canonical-only|--numbered-history]"
        )
    verify_numbered_history = sys.argv[1:] == ["--numbered-history"]

    root = Path(__file__).resolve().parents[2]
    source = root / "upstream"
    patches = root / "patches"
    series_path = patches / "series"
    canonical_path = patches / "canonical"

    source_head = run(["git", "-C", str(source), "rev-parse", "HEAD"]).stdout.decode().strip()
    if source_head != EXPECTED_PIN:
        raise ReplayError(f"upstream HEAD mismatch: expected {EXPECTED_PIN}, got {source_head}")

    entries = active_manifest(series_path)
    active = set(entries)
    numbered = {path.name for path in patches.glob("0*.patch")}
    missing = sorted(active - numbered)
    unlisted = numbered - active
    if missing:
        raise ReplayError(f"active series entries are missing: {', '.join(missing)}")
    if unlisted != RETIRED_PATCHES:
        raise ReplayError(
            "unexpected unlisted numbered patches: "
            f"expected={sorted(RETIRED_PATCHES)} actual={sorted(unlisted)}"
        )

    touched: set[Path] = set()
    for entry in entries:
        touched.update(patch_paths(patches / entry))

    canonical_entries = active_manifest(canonical_path)
    if len(canonical_entries) != 1:
        raise ReplayError(
            f"patches/canonical must name exactly one squashed patch, got {len(canonical_entries)}"
        )
    canonical_name = canonical_entries[0]
    if Path(canonical_name).name != canonical_name or not canonical_name.endswith(".patch"):
        raise ReplayError(f"unsafe canonical patch name: {canonical_name}")

    source_dirty = dirty_paths(source)
    canonical_patch = patches / canonical_name
    canonical_receipt = canonical_patch.with_suffix(".sha256")
    receipt_fields = canonical_receipt.read_text(encoding="utf-8").split()
    if len(receipt_fields) != 2 or receipt_fields[1] != canonical_patch.name:
        raise ReplayError(f"malformed {canonical_receipt.name} receipt")
    canonical_sha256 = hashlib.sha256(canonical_patch.read_bytes()).hexdigest()
    if canonical_sha256 != receipt_fields[0]:
        raise ReplayError(
            "canonical source digest mismatch: "
            f"expected {receipt_fields[0]}, got {canonical_sha256}"
        )
    canonical_paths = patch_paths(canonical_patch)
    if canonical_paths != source_dirty:
        missing_from_canonical = sorted(source_dirty - canonical_paths)
        clean_in_source = sorted(canonical_paths - source_dirty)
        raise ReplayError(
            "canonical/source path-set mismatch: "
            f"dirty_not_canonical={missing_from_canonical[:12]} "
            f"canonical_not_dirty={clean_in_source[:12]}"
        )

    with tempfile.TemporaryDirectory(prefix="blender-web-source-replay-") as temporary:
        canonical_replay = Path(temporary) / "canonical"
        canonical_replay.mkdir()
        extract_pin(source, canonical_replay)
        run(["git", "apply", "--check", str(canonical_patch)], cwd=canonical_replay)
        run(["git", "apply", str(canonical_patch)], cwd=canonical_replay)

        mismatches: list[str] = []
        for relative in sorted(canonical_paths):
            expected = fingerprint(source / relative)
            actual = fingerprint(canonical_replay / relative)
            if actual != expected:
                mismatches.append(f"{relative}: replay={actual} frozen={expected}")
        if mismatches:
            raise ReplayError(
                f"canonical replay differs from frozen source on {len(mismatches)} paths\n"
                + "\n".join(mismatches[:12])
            )

        if verify_numbered_history:
            numbered_replay = Path(temporary) / "numbered"
            numbered_replay.mkdir()
            extract_pin(source, numbered_replay)

            for index, entry in enumerate(entries, start=1):
                patch = patches / entry
                try:
                    run(["git", "apply", "--check", str(patch)], cwd=numbered_replay)
                    run(["git", "apply", str(patch)], cwd=numbered_replay)
                except ReplayError as error:
                    raise ReplayError(
                        f"series entry {index}/{len(entries)} {entry}: {error}"
                    ) from error

    canonical_only_paths = source_dirty - touched
    print(
        "CANONICAL_REPLAY_PASS "
        f"pin={EXPECTED_PIN[:12]} patches={len(entries)} retired={len(RETIRED_PATCHES)} "
        f"numbered_touched={len(touched)} canonical_sha256={canonical_sha256[:12]} "
        f"canonical_paths={len(canonical_paths)} canonical_only={len(canonical_only_paths)} "
        f"numbered_history={'verified' if verify_numbered_history else 'diagnostic-only'}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReplayError as error:
        print(f"SERIES_REPLAY_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
