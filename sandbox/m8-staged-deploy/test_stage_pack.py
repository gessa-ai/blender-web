#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail-closed contract for the staged preload packer."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Callable


HERE = Path(__file__).resolve().parent
PACKER = HERE / "stage_pack.py"
SPEC = importlib.util.spec_from_file_location("bw_stage_pack", PACKER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def manifest(entries: list[tuple[str, str, str]], remote_size: int) -> str:
    rows = ",".join(
        f'{{filename:"{filename}",start:{start},end:{end}}}'
        for filename, start, end in entries
    )
    return f"prefix();loadPackage({{files:[{rows}],remote_package_size:{remote_size}}});suffix();"


def expect_exit(label: str, action: Callable[[], object], needle: str) -> None:
    try:
        action()
    except SystemExit as error:
        if needle not in str(error):
            raise AssertionError(f"{label}: {error!s} lacks {needle!r}") from error
    else:
        raise AssertionError(f"{label}: unexpectedly passed")


def write_source(root: Path, glue: str, data: bytes) -> Path:
    source = root / "bin"
    source.mkdir()
    (source / "blender_browser.js").write_text(glue, encoding="utf-8")
    (source / "blender_browser.data").write_bytes(data)
    return source


def run_packer(source: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PACKER), "--bin", str(source), "--out", str(output)],
        cwd=HERE.parents[1],
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> None:
    classifications = {
        "/bw/python/lib/python3.13/os.py": "keep",
        "/bw/python/lib/python3.13/asyncio/tasks.py": "defer",
        "/bw/python/lib/python3.13/site-packages/numpy/_core/tests/test_multiarray.py": "defer",
        "/bw/python/lib/python3.13/site-packages/numpy/_core/multiarray.py": "keep",
        "/usd/usdGeom/resources/generatedSchema.usda": "defer",
        "/bw/scripts/addons_core/rigify/__init__.py": "defer",
        "/bw/scripts/addons_core/cycles/__init__.py": "keep",
        "/bw/scripts/addons_core/io_scene_gltf2/__init__.py": "keep",
        "/bw/scripts/startup/bl_app_templates_system/2D_Animation/__init__.py": "defer",
        "/bw/scripts/startup/bl_app_templates_system/2D_Animation/startup.blend": "defer",
        "/bw/datafiles/icons_blend/toolbar.blend": "defer",
        "/bw/datafiles/preview.blend": "defer",
        "/bw/datafiles/preview_grease_pencil.blend": "defer",
        "/bw/datafiles/splash.png": "defer",
        "/bw/datafiles/splash_template.xcf": "defer",
        "/bw/datafiles/studiolights/studio/paint.sl": "keep",
        "/bw/datafiles/studiolights/world/studio.exr": "defer",
        "/bw/datafiles/studiolights/matcap/basic.exr": "defer",
        "/bw/datafiles/fonts/Inter.woff2": "keep",
        "/bw/datafiles/fonts/Noto Sans CJK Regular.woff2": "defer",
        "/bw/datafiles/colormanagement/config.ocio": "keep",
        "/bw/datafiles/colormanagement/luts/AgX_Base_sRGB.cube": "keep",
        "/bw/datafiles/colormanagement/luts/pbrNeutral.cube": "defer",
        "/bw/datafiles/locale/ja/LC_MESSAGES/blender.mo": "defer",
        "/bw/python/lib/python3.13/__pycache__/os.cpython-313.pyc": "drop",
        "/bw/python/lib/python3.13/pip.whl": "drop",
    }
    for filename, expected in classifications.items():
        actual = MODULE.classify(filename, True)
        if actual != expected:
            raise AssertionError(f"classification {filename}: {actual} != {expected}")

    entries = [
        ("/bw/python/lib/python3.13/os.py", "0", "1e+0"),
        ("/bw/python/lib/python3.13/asyncio/tasks.py", "1e+0", "3"),
        ("/bw/python/lib/python3.13/__pycache__/x.pyc", "3", "6"),
        ("/usd/plugin.json", "6", "1e+1"),
        ("/bw/datafiles/fonts/Inter.woff2", "10", "15"),
        ("/bw/scripts/startup/bl_app_templates_system/VFX/startup.blend", "15", "19"),
    ]
    source_data = b"ABBCCCDDDDEEEEEFFFF"
    with tempfile.TemporaryDirectory(prefix="bw-stage-pack-contract-") as temp_text:
        temp = Path(temp_text)
        source = write_source(temp, manifest(entries, len(source_data)), source_data)
        output = temp / "out"
        result = run_packer(source, output)
        if result.returncode != 0:
            raise AssertionError(f"valid pack failed: {result.stderr or result.stdout}")
        if (output / "blender_browser.data").read_bytes() != b"AEEEEE":
            raise AssertionError("stage-0 concatenation changed")
        if (output / "stage1.data").read_bytes() != b"BBDDDDFFFF":
            raise AssertionError("stage-1 concatenation changed")
        _, _, packed_entries, packed_size = MODULE.parse_manifest(
            (output / "blender_browser.js").read_text(encoding="utf-8")
        )
        expected_entries = [
            (entries[0][0], 0, 1),
            (entries[1][0], 0, 0),
            (entries[3][0], 0, 0),
            (entries[4][0], 1, 6),
            (entries[5][0], 0, 0),
        ]
        if packed_entries != expected_entries or packed_size != 6:
            raise AssertionError(
                f"rewritten preload manifest changed: {packed_entries!r}/{packed_size}"
            )
        stage1 = json.loads((output / "stage1-manifest.json").read_text(encoding="utf-8"))
        if stage1 != {
            "total_bytes": 10,
            "files": [
                {"filename": entries[1][0], "start": 0, "end": 2},
                {"filename": entries[3][0], "start": 2, "end": 6},
                {"filename": entries[5][0], "start": 6, "end": 10},
            ],
        }:
            raise AssertionError(f"stage-1 manifest changed: {stage1!r}")

        malformed = manifest(entries, len(source_data)).replace("start:0", "start:bogus", 1)
        expect_exit(
            "unparsed manifest entry",
            lambda: MODULE.parse_manifest(malformed),
            "parsed 5 of 6 manifest entries",
        )
        invalid_source = temp / "invalid"
        invalid_source.mkdir()
        (invalid_source / "blender_browser.js").write_text(
            manifest(entries, len(source_data) - 1), encoding="utf-8"
        )
        (invalid_source / "blender_browser.data").write_bytes(source_data)
        invalid = run_packer(invalid_source, temp / "invalid-out")
        if invalid.returncode == 0 or "remote_package_size 18 != data bytes 19" not in (
            invalid.stderr + invalid.stdout
        ):
            raise AssertionError("end-to-end remote-size mutation did not fail closed")

    expect_exit(
        "remote size", lambda: MODULE.validate_source_manifest([("/a", 0, 1)], 2, 1),
        "remote_package_size 2 != data bytes 1",
    )
    expect_exit(
        "empty", lambda: MODULE.validate_source_manifest([], 0, 0), "contains no entries"
    )
    expect_exit(
        "unsafe path",
        lambda: MODULE.validate_source_manifest([("relative", 0, 1)], 1, 1),
        "unsafe manifest path",
    )
    expect_exit(
        "duplicate",
        lambda: MODULE.validate_source_manifest([("/a", 0, 1), ("/a", 1, 2)], 2, 2),
        "duplicate manifest path",
    )
    expect_exit(
        "out of range",
        lambda: MODULE.validate_source_manifest([("/a", 0, 2)], 1, 1),
        "invalid range",
    )
    expect_exit(
        "gap",
        lambda: MODULE.validate_source_manifest([("/a", 1, 2)], 2, 2),
        "source interval gap",
    )
    expect_exit(
        "overlap",
        lambda: MODULE.validate_source_manifest([("/a", 0, 2), ("/b", 1, 3)], 3, 3),
        "source interval overlap",
    )
    expect_exit(
        "incomplete coverage",
        lambda: MODULE.validate_source_manifest([("/a", 0, 1)], 2, 2),
        "source coverage ends at 1, expected 2",
    )

    print(
        "BW_STAGE_PACK_CONTRACT_PASS "
        f"classifications={len(classifications)} positive=5 negative=10"
    )


if __name__ == "__main__":
    main()
