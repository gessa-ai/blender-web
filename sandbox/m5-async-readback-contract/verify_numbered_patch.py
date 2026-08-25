#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Reverse/forward an exact aggregate-readback numbered patch in isolation."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shlex
import subprocess
import tempfile


EXPECTED_PATHS_BY_NAME = {
    "0253-m5-legacy-selection-readback-primitive.patch": {
        Path("source/blender/draw/DRW_select_buffer.hh"),
        Path("source/blender/draw/intern/draw_select_buffer.cc"),
    },
    "0254-m5-legacy-selection-click-continuation.patch": {
        Path("source/blender/draw/DRW_select_buffer.hh"),
        Path("source/blender/draw/intern/draw_select_buffer.cc"),
        Path("source/blender/editors/mesh/editmesh_select.cc"),
        Path("source/blender/editors/space_view3d/view3d_select.cc"),
    },
    "0255-m5-legacy-selection-gesture-continuation.patch": {
        Path("source/blender/draw/DRW_select_buffer.hh"),
        Path("source/blender/draw/intern/draw_select_buffer.cc"),
        Path("source/blender/editors/space_view3d/view3d_select.cc"),
    },
    "0273-m5-particle-edit-depth-cache-continuation.patch": {
        Path("source/blender/editors/include/ED_particle.hh"),
        Path("source/blender/editors/physics/particle_edit.cc"),
        Path("source/blender/editors/space_view3d/view3d_select.cc"),
    },
    "0277-m5-particle-producer-state.patch": {
        Path("source/blender/editors/physics/particle_edit.cc"),
    },
}


class VerificationError(RuntimeError):
    pass


def run(argv: list[str], cwd: Path) -> None:
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip()
        raise VerificationError(
            f"command failed ({result.returncode}): {' '.join(argv)}"
            + (f"\n{detail}" if detail else "")
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
            raise VerificationError(f"unsafe or non-identical patch path: {line}")
        paths.add(old_path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    patch = args.patch.resolve()
    if not patch.is_file():
        raise VerificationError(f"missing patch: {patch}")
    expected_paths = EXPECTED_PATHS_BY_NAME.get(patch.name)
    if expected_paths is None:
        raise VerificationError(f"unrecognized patch name: {patch.name}")
    actual_paths = patch_paths(patch)
    if actual_paths != expected_paths:
        raise VerificationError(
            f"patch path set differs: expected={sorted(expected_paths)} actual={sorted(actual_paths)}"
        )

    current = {relative: (source_root / relative).read_bytes() for relative in expected_paths}
    with tempfile.TemporaryDirectory(prefix="m5-readback-patch-") as temporary:
        replay = Path(temporary)
        for relative, payload in current.items():
            destination = replay / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)

        run(["git", "apply", "--reverse", "--check", str(patch)], replay)
        run(["git", "apply", "--reverse", str(patch)], replay)
        if any((replay / relative).read_bytes() == current[relative] for relative in expected_paths):
            raise VerificationError("reverse application left a target unchanged")
        run(["git", "apply", "--check", str(patch)], replay)
        run(["git", "apply", str(patch)], replay)
        for relative, payload in current.items():
            if (replay / relative).read_bytes() != payload:
                raise VerificationError(f"forward replay differs: {relative}")

    digest = hashlib.sha256(patch.read_bytes()).hexdigest()
    print(
        f"M5_ASYNC_READBACK_NUMBERED_PATCH_PASS patch={patch.name} "
        f"files={len(expected_paths)} sha256={digest}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, VerificationError, subprocess.SubprocessError) as error:
        print(f"M5_ASYNC_READBACK_NUMBERED_PATCH_FAIL {error}", file=__import__("sys").stderr)
        raise SystemExit(1)
