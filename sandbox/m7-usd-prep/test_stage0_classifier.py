#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed unit checks for the measured Stage-0 reclassification."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STAGE_PACK = ROOT / "sandbox/m8-staged-deploy/stage_pack.py"
spec = importlib.util.spec_from_file_location("bw_stage_pack", STAGE_PACK)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {STAGE_PACK}")
stage_pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage_pack)


DEFER = (
    "/usd/plugInfo.json",
    "/usd/usdGeom/resources/generatedSchema.usda",
    "/bw/datafiles/icons_blend/toolbar.blend",
    "/bw/datafiles/preview.blend",
    "/bw/datafiles/preview_grease_pencil.blend",
    "/bw/datafiles/splash.png",
    "/bw/datafiles/splash_template.xcf",
    "/bw/datafiles/studiolights/studio/basic.sl",
    "/bw/datafiles/studiolights/matcap/checker.exr",
    "/bw/python/lib/python3.13/site-packages/numpy/_core/tests/test_umath.py",
    "/bw/python/lib/python3.13/site-packages/numpy/linalg/test_linalg.py",
)

KEEP = (
    "/bw/datafiles/icons/brush.svgi",
    "/bw/datafiles/fonts/Inter.woff2",
    "/bw/datafiles/colormanagement/config.ocio",
    "/bw/python/lib/python3.13/site-packages/numpy/__init__.py",
    "/bw/python/lib/python3.13/site-packages/numpy/testing/__init__.py",
)


def main() -> int:
    failures = []
    for path in DEFER:
        if stage_pack.classify(path, True) != "defer":
            failures.append(f"expected defer: {path}")
    for path in KEEP:
        if stage_pack.classify(path, True) != "keep":
            failures.append(f"expected keep: {path}")
    # --no-defer-datafiles must retain datafile assets, but NumPy tests are an
    # independent dead-Python rule and remain deferred.
    if stage_pack.classify("/bw/datafiles/icons_blend/toolbar.blend", False) != "keep":
        failures.append("--no-defer-datafiles did not retain icons_blend")
    if stage_pack.classify(DEFER[-1], False) != "defer":
        failures.append("NumPy tests unexpectedly entered Stage 0")
    if failures:
        for failure in failures:
            print(f"STAGE0_CLASSIFIER_RED {failure}")
        return 1
    print(f"STAGE0_CLASSIFIER_OK defer={len(DEFER)} keep={len(KEEP)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
