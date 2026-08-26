#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
"""Verify that the public snapshot metadata is scrubbed without breaking recovery replay."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import NoReturn


ROOT = Path(__file__).resolve().parents[2]
ANCHOR = "0577f7f46a4be0ec2e61f02230e9fc7bff15a7cd"
PATCH = ROOT / "patches/OUTER_WORKTREE_REMAINDER.patch"
CHECKSUM = ROOT / "patches/OUTER_WORKTREE_REMAINDER.sha256"
CARRIERS = (
    ROOT / ".gitignore",
    ROOT / "patches/series",
    PATCH,
)
HOST_LABEL = b"ornith" + b"-lab"
PRIVATE_PATHS = (
    ("macOS user path", re.compile(rb"/Users/[A-Za-z0-9._-]+(?:/|\\b)")),
    ("Linux user path", re.compile(rb"/home/[A-Za-z0-9._-]+(?:/|\\b)")),
)


def fail(message: str) -> NoReturn:
    raise SystemExit(f"publication metadata scrub: FAIL: {message}")


def run(args: list[str], *, cwd: Path, input_stream=None) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            stdin=input_stream,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        fail(f"cannot run {' '.join(args)}: {error}")
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").splitlines()
        fail(f"{' '.join(args)} returned {result.returncode}: {detail[:3]}")
    return result


def require_scrubbed(path: Path, label: str | None = None) -> None:
    data = path.read_bytes()
    lowered = data.lower()
    display = label
    if display is None:
        try:
            display = str(path.relative_to(ROOT))
        except ValueError:
            display = path.name
    if HOST_LABEL.lower() in lowered:
        fail(f"migration host label remains in {display}")
    for label, pattern in PRIVATE_PATHS:
        match = pattern.search(data)
        if match:
            line = data.count(b"\n", 0, match.start()) + 1
            fail(f"{label} remains in {display}:{line}")


def touched_paths(patch_data: bytes) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for line in patch_data.splitlines():
        if not line.startswith(b"diff --git a/"):
            continue
        try:
            _, _, _old, new = line.decode("utf-8").split(" ", 3)
        except (UnicodeDecodeError, ValueError):
            fail(f"malformed diff header: {line[:120]!r}")
        if not new.startswith("b/"):
            fail(f"unsafe diff destination: {new}")
        relative = Path(new[2:])
        if relative.is_absolute() or ".." in relative.parts:
            fail(f"unsafe diff path: {relative}")
        paths.add(relative)
    if not paths:
        fail("outer-worktree patch has no diff entries")
    return tuple(sorted(paths))


def path_state(path: Path) -> tuple[str, int, str] | tuple[str]:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return ("absent",)
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISLNK(info.st_mode):
        return ("symlink", mode, os.readlink(path))
    if stat.S_ISREG(info.st_mode):
        return ("file", mode, hashlib.sha256(path.read_bytes()).hexdigest())
    fail(f"unsupported replay path type: {path}")


def main() -> None:
    for carrier in CARRIERS:
        if not carrier.is_file():
            fail(f"missing carrier: {carrier.relative_to(ROOT)}")
        require_scrubbed(carrier)

    patch_data = PATCH.read_bytes()
    digest = hashlib.sha256(patch_data).hexdigest()
    expected = CHECKSUM.read_text(encoding="utf-8").splitlines()
    exact_line = f"{digest}  {PATCH.name}"
    if expected != [exact_line]:
        fail(f"checksum file must contain exactly {exact_line!r}")

    touched = touched_paths(patch_data)
    with tempfile.TemporaryDirectory(prefix="bw-publication-replay-") as scratch:
        replay = Path(scratch)
        archive = subprocess.Popen(
            ["git", "archive", "--format=tar", ANCHOR],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert archive.stdout is not None
        extract = run(["tar", "-x", "-C", str(replay)], cwd=ROOT, input_stream=archive.stdout)
        archive.stdout.close()
        archive_stderr = archive.stderr.read() if archive.stderr is not None else b""
        archive_rc = archive.wait(timeout=120)
        if archive_rc != 0:
            fail(f"git archive returned {archive_rc}: {archive_stderr.decode('utf-8', 'replace')}")
        if extract.stdout or extract.stderr:
            fail("tar extraction produced unexpected output")

        before = {path: path_state(replay / path) for path in touched}
        run(["git", "apply", "--check", str(PATCH)], cwd=replay)
        run(["git", "apply", str(PATCH)], cwd=replay)
        for relative in touched:
            applied = replay / relative
            if applied.is_file():
                require_scrubbed(applied, f"replay:{relative}")
        run(["git", "apply", "--reverse", "--check", str(PATCH)], cwd=replay)
        run(["git", "apply", "--reverse", str(PATCH)], cwd=replay)
        after = {path: path_state(replay / path) for path in touched}
        if after != before:
            drift = [str(path) for path in touched if before[path] != after[path]]
            fail(f"reverse replay did not restore anchor state: {drift[:8]}")

    print(
        "PUBLICATION_METADATA_SCRUB_PASS "
        f"carriers={len(CARRIERS)} touched={len(touched)} "
        f"anchor={ANCHOR[:7]} patch_sha256={digest}"
    )


if __name__ == "__main__":
    main()
