#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Reverse and reapply patch 0275 against its exact canonical postimage."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile


RELATIVE = Path("source/blender/python/intern/bpy_rna_wm.cc")
ERROR = "Window.screenshot() is unavailable in the browser because WebGPU readback is"


def run(argv: list[str], cwd: Path) -> None:
    result = subprocess.run(argv, cwd=cwd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "command failed: " + " ".join(argv))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    args = parser.parse_args()

    postimage = (args.source_root / RELATIVE).read_bytes()
    patch = args.patch.resolve()
    patch_text = patch.read_text(encoding="utf-8")
    expected_header = f"diff --git a/{RELATIVE} b/{RELATIVE}"
    if patch_text.count(expected_header) != 1 or patch_text.count("diff --git ") != 1:
        raise RuntimeError("numbered patch path boundary differs")

    with tempfile.TemporaryDirectory(prefix="bw-m5-python-screenshot-patch-") as temporary:
        root = Path(temporary)
        target = root / RELATIVE
        target.parent.mkdir(parents=True)
        target.write_bytes(postimage)

        run(["git", "apply", "--reverse", "--check", str(patch)], root)
        run(["git", "apply", "--reverse", str(patch)], root)
        predecessor = target.read_text(encoding="utf-8")
        if ERROR in predecessor or "#ifdef __EMSCRIPTEN__" in predecessor:
            raise RuntimeError("reversed predecessor retains browser policy")
        if predecessor.count("WM_window_pixels_read(C, win, dumprect_size)") != 1:
            raise RuntimeError("reversed predecessor loses synchronous stock capture")

        run(["git", "apply", "--check", str(patch)], root)
        run(["git", "apply", str(patch)], root)
        if target.read_bytes() != postimage:
            raise RuntimeError("forward reapply differs from canonical postimage")

    digest = hashlib.sha256(patch.read_bytes()).hexdigest()
    print(f"M5_PYTHON_WINDOW_SCREENSHOT_PATCH_PASS paths=1 reverse_sync=1 sha256={digest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print(f"M5_PYTHON_WINDOW_SCREENSHOT_PATCH_FAIL {error}")
        raise SystemExit(1)
