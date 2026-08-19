#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Measure the adopted narrower first-pixel data partition without writing bytes.

The legacy set reconstructs the immediately preceding classifier by adding back
the now-deferred build-time/compiled-in resources, external StudioLights, and
NumPy tests. The shipping set is stage_pack.py's current KEEP classification.
Browser first-pixel and full post-Stage-1 Workbench proof remain mandatory.
"""

import argparse
import importlib.util
import json
from pathlib import Path

import brotli


def load_stage_pack(path: Path):
    spec = importlib.util.spec_from_file_location("bw_stage_pack", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidate_defer(filename: str) -> bool:
    # toolbar.blend is input to blender_icons_geom_update.py, not a runtime icon
    # source. preview*.blend and splash.png are compiled into the executable by
    # editors/datafiles/CMakeLists.txt; splash_template.xcf is an authoring file.
    if "/datafiles/icons_blend/" in filename:
        return True
    if any(
        suffix in filename
        for suffix in (
            "/datafiles/preview.blend",
            "/datafiles/preview_grease_pencil.blend",
            "/datafiles/splash.png",
            "/datafiles/splash_template.xcf",
        )
    ):
        return True

    # Solid Workbench has the internal default StudioLight. External studio,
    # world and matcap assets must be installed before those user modes are used,
    # but do not belong to the first-solid-frame transfer.
    if "/datafiles/studiolights/" in filename:
        return True

    # NumPy itself remains in Stage 0 because enabled add-ons import it. Its test
    # corpus is not part of registration or a product import/export operation.
    if "/site-packages/numpy/" in filename and (
        "/tests/" in filename or "/test_" in filename
    ):
        return True
    return False


def compressed_size(parts: list[memoryview], quality: int) -> int:
    compressor = brotli.Compressor(quality=quality)
    total = 0
    for part in parts:
        total += len(compressor.process(part))
    total += len(compressor.finish())
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--bin", type=Path, default=None)
    parser.add_argument("--quality", type=int, default=5, choices=range(0, 12))
    args = parser.parse_args()

    repo = args.repo.resolve()
    bin_dir = (args.bin or repo / "build-wasm-windowed-opt/bin").resolve()
    stage_pack = load_stage_pack(repo / "sandbox/m8-staged-deploy/stage_pack.py")
    glue = (bin_dir / "blender_browser.js").read_text()
    data = (bin_dir / "blender_browser.data").read_bytes()
    _, _, entries, remote_size = stage_pack.parse_manifest(glue)
    if remote_size != len(data):
        raise RuntimeError(f"manifest bytes {remote_size} != data bytes {len(data)}")

    view = memoryview(data)
    candidate = [(name, start, end) for name, start, end in entries
                 if stage_pack.classify(name, True) == "keep"]
    moved = [(name, start, end) for name, start, end in entries
             if candidate_defer(name)]
    candidate_names = {name for name, _, _ in candidate}
    base = candidate + [(name, start, end) for name, start, end in moved
                        if name not in candidate_names]

    base_parts = [view[start:end] for _, start, end in base]
    candidate_parts = [view[start:end] for _, start, end in candidate]
    result = {
        "quality": args.quality,
        "base_files": len(base),
        "base_raw_bytes": sum(end - start for _, start, end in base),
        "base_brotli_bytes": compressed_size(base_parts, args.quality),
        "candidate_files": len(candidate),
        "candidate_raw_bytes": sum(end - start for _, start, end in candidate),
        "candidate_brotli_bytes": compressed_size(candidate_parts, args.quality),
        "moved_files": len(moved),
        "moved_raw_bytes": sum(end - start for _, start, end in moved),
        "shipping_classifier_changed": True,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
