#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail closed on the windowed-only sculpt/paint registration cut."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "patches/blender_web.cmake"
SPACE_CMAKE = ROOT / "upstream/source/blender/editors/space_api/CMakeLists.txt"
SPACE_SOURCE = ROOT / "upstream/source/blender/editors/space_api/spacetypes.cc"
SERIES = ROOT / "patches/series"
PATCH_NAME = "0248-web-windowed-sculpt-paint-registration-cut.patch"
PATCH = ROOT / "patches" / PATCH_NAME

GUARD = "#if !defined(__EMSCRIPTEN__) || defined(WITH_BLENDER_WEB_SCULPT_PAINT)"
CALLS = (
    "sculpt_paint::operatortypes_sculpt();",
    "ED_operatortypes_sculpt_curves();",
    "ED_operatortypes_paint();",
    "ED_operatormacros_paint();",
    "ED_keymap_paint(keyconf);",
    "sculpt_paint::keymap_sculpt(keyconf);",
)
OPTION_RE = re.compile(
    r'option\(WITH_BLENDER_WEB_SCULPT_PAINT\s+'
    r'"blender-web: register non-launch sculpt and paint operators/keymaps"\s+ON\)'
)
WINDOWED_OFF_RE = re.compile(
    r'set\(WITH_BLENDER_WEB_SCULPT_PAINT\s+OFF\s+CACHE BOOL "" FORCE\)'
)
CMAKE_FALLBACK = """if(NOT DEFINED WITH_BLENDER_WEB_SCULPT_PAINT)
  if(WITH_BLENDER_WEB_WINDOWED)
    set(WITH_BLENDER_WEB_SCULPT_PAINT OFF)
  else()
    set(WITH_BLENDER_WEB_SCULPT_PAINT ON)
  endif()
endif()
if(WITH_BLENDER_WEB_SCULPT_PAINT)
  target_compile_definitions(bf_editor_space_api PRIVATE WITH_BLENDER_WEB_SCULPT_PAINT)
endif()"""


def verify(config: str, cmake: str, source: str, series: str, patch: str) -> list[str]:
    errors: list[str] = []
    if len(OPTION_RE.findall(config)) != 1:
        errors.append("config must declare the sculpt/paint option exactly once with default ON")
    if len(WINDOWED_OFF_RE.findall(config)) != 1:
        errors.append("windowed profile must force the sculpt/paint option OFF exactly once")
    if CMAKE_FALLBACK not in cmake:
        errors.append("space_api CMake fallback/compile-definition contract changed")

    stack: list[str] = []
    call_counts = {call: 0 for call in CALLS}
    guarded_counts = {call: 0 for call in CALLS}
    for line_number, raw in enumerate(source.splitlines(), start=1):
        line = raw.strip()
        if line.startswith(("#if ", "#ifdef ", "#ifndef ")):
            stack.append(line)
        elif line == "#endif":
            if not stack:
                errors.append(f"unbalanced #endif at source line {line_number}")
            else:
                stack.pop()
        for call in CALLS:
            if line == call:
                call_counts[call] += 1
                if GUARD in stack:
                    guarded_counts[call] += 1
    if stack:
        errors.append("unterminated preprocessor conditional in spacetypes.cc")
    for call in CALLS:
        if call_counts[call] != 1:
            errors.append(f"registration call count changed for {call}: {call_counts[call]}")
        if guarded_counts[call] != 1:
            errors.append(f"registration call escaped the web feature guard: {call}")

    active_series = [
        line.strip()
        for line in series.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if active_series.count(PATCH_NAME) != 1:
        errors.append("numbered patch must occur exactly once in patches/series")
    for path in (
        "source/blender/editors/space_api/CMakeLists.txt",
        "source/blender/editors/space_api/spacetypes.cc",
    ):
        if patch.count(f"diff --git a/{path} b/{path}") != 1:
            errors.append(f"numbered patch does not bind exactly one diff for {path}")
    return errors


def load() -> tuple[str, str, str, str, str]:
    paths = (CONFIG, SPACE_CMAKE, SPACE_SOURCE, SERIES, PATCH)
    missing = [str(path.relative_to(ROOT)) for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing inputs: {', '.join(missing)}")
    return tuple(path.read_text(encoding="utf-8") for path in paths)  # type: ignore[return-value]


def run_selfcheck(inputs: tuple[str, str, str, str, str]) -> int:
    config, cmake, source, series, patch = inputs
    controls = (
        (config.replace("operators/keymaps\" ON)", "operators/keymaps\" OFF)", 1), cmake, source, series, patch),
        (config.replace("SCULPT_PAINT OFF CACHE", "SCULPT_PAINT ON CACHE", 1), cmake, source, series, patch),
        (config, cmake, source.replace(GUARD, "#if 1", 1), series, patch),
        (config, cmake, source.replace(CALLS[0], CALLS[0] + "\n  " + CALLS[0], 1), series, patch),
    )
    rejected = sum(bool(verify(*control)) for control in controls)
    if rejected != len(controls):
        raise RuntimeError(f"self-check admitted {len(controls) - rejected} invalid mutation(s)")
    return rejected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    inputs = load()
    errors = verify(*inputs)
    if errors:
        print("M8_SCULPT_PAINT_CUT_FAIL " + " | ".join(errors))
        return 1
    controls = run_selfcheck(inputs) if args.selfcheck else 0
    print(
        "M8_SCULPT_PAINT_CUT_PASS "
        f"calls={len(CALLS)} controls={controls} patch={PATCH_NAME}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
