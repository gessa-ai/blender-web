#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail closed on the windowed-only Grease Pencil registration cut."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "patches/blender_web.cmake"
SPACE_CMAKE = ROOT / "upstream/source/blender/editors/space_api/CMakeLists.txt"
SPACE_SOURCE = ROOT / "upstream/source/blender/editors/space_api/spacetypes.cc"
SERIES = ROOT / "patches/series"
PATCH_NAME = "0249-web-windowed-grease-pencil-registration-cut.patch"
PATCH = ROOT / "patches" / PATCH_NAME

GUARD = "#if !defined(__EMSCRIPTEN__) || defined(WITH_BLENDER_WEB_GREASE_PENCIL)"
CALLS = (
    "ED_operatortypes_gpencil_legacy();",
    "ED_operatortypes_grease_pencil();",
    "ED_operatormacros_grease_pencil();",
    "ED_keymap_gpencil_legacy(keyconf);",
    "ED_keymap_grease_pencil(keyconf);",
)
OPTION_RE = re.compile(
    r'option\(WITH_BLENDER_WEB_GREASE_PENCIL\s+'
    r'"blender-web: register non-launch Grease Pencil editing operators/keymaps"\s+ON\)'
)
WINDOWED_OFF_RE = re.compile(
    r'set\(WITH_BLENDER_WEB_GREASE_PENCIL\s+OFF\s+CACHE BOOL "" FORCE\)'
)
CMAKE_FALLBACK = """if(NOT DEFINED WITH_BLENDER_WEB_GREASE_PENCIL)
  if(WITH_BLENDER_WEB_WINDOWED)
    set(WITH_BLENDER_WEB_GREASE_PENCIL OFF)
  else()
    set(WITH_BLENDER_WEB_GREASE_PENCIL ON)
  endif()
endif()
if(WITH_BLENDER_WEB_GREASE_PENCIL)
  target_compile_definitions(bf_editor_space_api PRIVATE WITH_BLENDER_WEB_GREASE_PENCIL)
endif()"""


def verify(config: str, cmake: str, source: str, series: str, patch: str) -> list[str]:
    errors: list[str] = []
    if len(OPTION_RE.findall(config)) != 1:
        errors.append("config must declare the Grease Pencil option exactly once with default ON")
    if len(WINDOWED_OFF_RE.findall(config)) != 1:
        errors.append("windowed profile must force the Grease Pencil option OFF exactly once")
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
        (config.replace("editing operators/keymaps\" ON)", "editing operators/keymaps\" OFF)", 1), cmake, source, series, patch),
        (config.replace("GREASE_PENCIL OFF CACHE", "GREASE_PENCIL ON CACHE", 1), cmake, source, series, patch),
        (config, cmake, source.replace(GUARD, "#if 1", 1), series, patch),
        (config, cmake, source.replace(CALLS[0], CALLS[0] + "\n  " + CALLS[0], 1), series, patch),
    )
    rejected = sum(bool(verify(*control)) for control in controls)
    if rejected != len(controls):
        raise RuntimeError(f"self-check admitted {len(controls) - rejected} invalid mutation(s)")
    return rejected


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_roundtrip() -> str:
    relative_paths = (
        Path("source/blender/editors/space_api/CMakeLists.txt"),
        Path("source/blender/editors/space_api/spacetypes.cc"),
    )
    with tempfile.TemporaryDirectory(prefix="m8-grease-pencil-cut-") as temp_name:
        temp_root = Path(temp_name)
        for relative in relative_paths:
            destination = temp_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "upstream" / relative, destination)
        before = {relative: digest(temp_root / relative) for relative in relative_paths}
        reverse = subprocess.run(
            ["git", "apply", "--reverse", str(PATCH)],
            cwd=temp_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if reverse.returncode != 0:
            raise RuntimeError(f"isolated reverse failed: {reverse.stderr.strip()}")
        reversed_hashes = {relative: digest(temp_root / relative) for relative in relative_paths}
        if reversed_hashes == before:
            raise RuntimeError("isolated reverse did not change either shipping input")
        forward = subprocess.run(
            ["git", "apply", str(PATCH)],
            cwd=temp_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if forward.returncode != 0:
            raise RuntimeError(f"isolated forward failed: {forward.stderr.strip()}")
        after = {relative: digest(temp_root / relative) for relative in relative_paths}
        if after != before:
            raise RuntimeError("isolated reverse/forward did not restore exact source bytes")
    return digest(PATCH)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selfcheck", action="store_true")
    parser.add_argument("--roundtrip", action="store_true")
    args = parser.parse_args()
    try:
        inputs = load()
    except RuntimeError as error:
        print(f"M8_GREASE_PENCIL_CUT_FAIL {error}")
        return 1
    errors = verify(*inputs)
    if errors:
        print("M8_GREASE_PENCIL_CUT_FAIL " + " | ".join(errors))
        return 1
    controls = run_selfcheck(inputs) if args.selfcheck else 0
    patch_sha256 = run_roundtrip() if args.roundtrip else "not-run"
    print(
        "M8_GREASE_PENCIL_CUT_PASS "
        f"calls={len(CALLS)} controls={controls} patch={PATCH_NAME} "
        f"patch_sha256={patch_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
