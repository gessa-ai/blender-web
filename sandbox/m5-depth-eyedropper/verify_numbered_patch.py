#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reverse and replay patch 0258 against its exact isolated postimage."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shlex
import subprocess
import tempfile


EXPECTED_NAME = "0258-m5-depth-eyedropper-continuation.patch"
EXPECTED_PATH = Path(
    "source/blender/editors/interface/eyedroppers/eyedropper_depth.cc"
)


class VerificationError(RuntimeError):
    pass


def run(argv: list[str], cwd: Path) -> None:
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise VerificationError(
            f"command failed ({result.returncode}): {' '.join(argv)}\n{result.stderr.strip()}"
        )


def patch_paths(patch: Path) -> set[Path]:
    paths: set[Path] = set()
    for line in patch.read_text(encoding="utf-8").splitlines():
        if not line.startswith("diff --git "):
            continue
        fields = shlex.split(line)
        if (
            len(fields) != 4
            or not fields[2].startswith("a/")
            or not fields[3].startswith("b/")
        ):
            raise VerificationError(f"malformed diff header: {line}")
        old_path = Path(fields[2][2:])
        new_path = Path(fields[3][2:])
        if old_path != new_path or old_path.is_absolute() or ".." in old_path.parts:
            raise VerificationError(f"unsafe patch path: {line}")
        paths.add(old_path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    patch = args.patch.resolve()
    if patch.name != EXPECTED_NAME or patch_paths(patch) != {EXPECTED_PATH}:
        raise VerificationError("numbered patch identity or path set differs")
    postimage = (source_root / EXPECTED_PATH).read_bytes()

    with tempfile.TemporaryDirectory(prefix="m5-depth-eye-patch-") as temporary:
        replay = Path(temporary)
        target = replay / EXPECTED_PATH
        target.parent.mkdir(parents=True)
        target.write_bytes(postimage)
        run(["git", "apply", "--reverse", "--check", str(patch)], replay)
        run(["git", "apply", "--reverse", str(patch)], replay)
        preimage = target.read_bytes()
        if preimage == postimage:
            raise VerificationError("reverse application left the target unchanged")
        run(["git", "apply", "--check", str(patch)], replay)
        run(["git", "apply", str(patch)], replay)
        if target.read_bytes() != postimage:
            raise VerificationError("forward replay differs from the exact postimage")

    digest = hashlib.sha256(patch.read_bytes()).hexdigest()
    print(f"M5_DEPTH_EYEDROPPER_NUMBERED_PATCH_PASS files=1 sha256={digest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, VerificationError, subprocess.SubprocessError) as error:
        print(f"M5_DEPTH_EYEDROPPER_NUMBERED_PATCH_FAIL {error}", file=__import__("sys").stderr)
        raise SystemExit(1)
