#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Replay the canonical patch and compare it to an isolated immutable postimage."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shlex
import stat
import subprocess
import tempfile


PIN = "fbe6228777e7d9afefcd61a413844e790ae75db7"


class VerificationError(RuntimeError):
    pass


def run(argv: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise VerificationError(
            f"command failed ({result.returncode}): {' '.join(argv)}\n"
            + result.stderr.decode("utf-8", "replace").strip()
        )
    return result


def patch_paths(patch: Path) -> set[Path]:
    paths: set[Path] = set()
    for line in patch.read_text(encoding="utf-8", errors="surrogateescape").splitlines():
        if not line.startswith("diff --git "):
            continue
        fields = shlex.split(line)
        if len(fields) != 4 or not fields[2].startswith("a/") or not fields[3].startswith("b/"):
            raise VerificationError(f"malformed diff header: {line}")
        old_path = Path(fields[2][2:])
        new_path = Path(fields[3][2:])
        if old_path != new_path or old_path.is_absolute() or ".." in old_path.parts:
            raise VerificationError(f"unsafe canonical path: {line}")
        paths.add(old_path)
    if not paths:
        raise VerificationError("canonical patch has no paths")
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
            raise VerificationError("malformed source status")
        code = record[:2].decode("ascii", "strict")
        paths.add(Path(os.fsdecode(record[3:])))
        index += 1
        if "R" in code or "C" in code:
            if index >= len(records) or not records[index]:
                raise VerificationError("malformed rename status")
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
        return ("file", mode, metadata.st_size, hashlib.sha256(path.read_bytes()).hexdigest())
    return ("other", stat.S_IFMT(metadata.st_mode), mode)


def extract_pin(source: Path, destination: Path) -> None:
    archive = subprocess.Popen(
        ["git", "-C", str(source), "archive", "--format=tar", PIN],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert archive.stdout is not None
    extract = subprocess.run(
        ["tar", "-xf", "-", "-C", str(destination)],
        stdin=archive.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    archive.stdout.close()
    archive_error = archive.communicate()[1].decode("utf-8", "replace").strip()
    if archive.returncode != 0:
        raise VerificationError(f"git archive failed: {archive_error}")
    if extract.returncode != 0:
        raise VerificationError(
            "tar extraction failed: " + extract.stderr.decode("utf-8", "replace").strip()
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--sha256", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root.resolve()
    canonical = args.canonical.resolve()
    receipt = args.sha256.resolve()

    head = run(["git", "-C", str(source), "rev-parse", "HEAD"]).stdout.decode().strip()
    if head != PIN:
        raise VerificationError(f"source pin differs: {head}")
    fields = receipt.read_text(encoding="utf-8").split()
    if len(fields) != 2 or fields[1] != canonical.name:
        raise VerificationError("canonical SHA-256 receipt is malformed")
    digest = hashlib.sha256(canonical.read_bytes()).hexdigest()
    if digest != fields[0]:
        raise VerificationError("canonical SHA-256 receipt differs")

    expected_paths = patch_paths(canonical)
    actual_paths = dirty_paths(source)
    if expected_paths != actual_paths:
        raise VerificationError(
            "canonical/source path set differs: "
            f"source_only={sorted(actual_paths - expected_paths)[:8]} "
            f"canonical_only={sorted(expected_paths - actual_paths)[:8]}"
        )

    with tempfile.TemporaryDirectory(prefix="m5-navigation-canonical-") as temporary:
        replay = Path(temporary)
        extract_pin(source, replay)
        run(["git", "apply", "--check", str(canonical)], cwd=replay)
        run(["git", "apply", str(canonical)], cwd=replay)
        mismatches = [
            relative
            for relative in sorted(expected_paths)
            if fingerprint(replay / relative) != fingerprint(source / relative)
        ]
        if mismatches:
            raise VerificationError(f"canonical replay differs: {mismatches[:8]}")

    print(
        "M5_NAVIGATION_CANONICAL_REPLAY_PASS "
        f"pin={PIN[:12]} paths={len(expected_paths)} sha256={digest}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, VerificationError, subprocess.SubprocessError) as error:
        print(f"M5_NAVIGATION_CANONICAL_REPLAY_FAIL {error}", file=__import__("sys").stderr)
        raise SystemExit(1)
