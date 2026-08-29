#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Replay patch 0257 plus its later modal-routing overlay against the exact postimage."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shlex
import subprocess
import tempfile


EXPECTED_NAME = "0257-m5-view-center-pick-continuation.patch"
EXPECTED_PATH = Path(
    "source/blender/editors/space_view3d/view3d_navigate_view_center_pick.cc"
)
EXPECTED_OVERLAY_NAME = "0319-web-async-modal-event-passthrough.patch"
EXPECTED_OVERLAY_PATHS = {
    Path("source/blender/editors/screen/screendump.cc"),
    Path("source/blender/editors/space_view3d/view3d_edit.cc"),
    EXPECTED_PATH,
    Path("source/blender/editors/space_view3d/view3d_navigate_zoom_border.cc"),
    Path("source/blender/editors/space_view3d/view3d_navigate_view_ndof.cc"),
}


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
        if len(fields) != 4 or not fields[2].startswith("a/") or not fields[3].startswith("b/"):
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
    parser.add_argument("--overlay-patch", type=Path, required=True)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    patch = args.patch.resolve()
    overlay = args.overlay_patch.resolve()
    if patch.name != EXPECTED_NAME or patch_paths(patch) != {EXPECTED_PATH}:
        raise VerificationError("numbered patch identity or path set differs")
    if overlay.name != EXPECTED_OVERLAY_NAME or patch_paths(overlay) != EXPECTED_OVERLAY_PATHS:
        raise VerificationError("overlay patch identity or path set differs")
    postimage = (source_root / EXPECTED_PATH).read_bytes()

    with tempfile.TemporaryDirectory(prefix="m5-center-patch-") as temporary:
        replay = Path(temporary)
        target = replay / EXPECTED_PATH
        target.parent.mkdir(parents=True)
        target.write_bytes(postimage)
        overlay_args = ["git", "apply", f"--include={EXPECTED_PATH}"]
        run([*overlay_args, "--reverse", "--check", str(overlay)], replay)
        run([*overlay_args, "--reverse", str(overlay)], replay)
        if target.read_bytes() == postimage:
            raise VerificationError("overlay reverse application left the target unchanged")
        run(["git", "apply", "--reverse", "--check", str(patch)], replay)
        run(["git", "apply", "--reverse", str(patch)], replay)
        if target.read_bytes() == postimage:
            raise VerificationError("reverse application left the target unchanged")
        run(["git", "apply", "--check", str(patch)], replay)
        run(["git", "apply", str(patch)], replay)
        run([*overlay_args, "--check", str(overlay)], replay)
        run([*overlay_args, str(overlay)], replay)
        if target.read_bytes() != postimage:
            raise VerificationError("forward replay differs from the exact postimage")

    digest = hashlib.sha256(patch.read_bytes()).hexdigest()
    overlay_digest = hashlib.sha256(overlay.read_bytes()).hexdigest()
    print(
        f"M5_CENTER_NUMBERED_PATCH_PASS files=1 sha256={digest} "
        f"overlay_sha256={overlay_digest}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, VerificationError, subprocess.SubprocessError) as error:
        print(f"M5_CENTER_NUMBERED_PATCH_FAIL {error}", file=__import__("sys").stderr)
        raise SystemExit(1)
