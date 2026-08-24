#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail closed on the windowed-only NLA editor registration cut."""

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
SPACE_API_CMAKE = ROOT / "upstream/source/blender/editors/space_api/CMakeLists.txt"
SPACETYPES = ROOT / "upstream/source/blender/editors/space_api/spacetypes.cc"
SERIES = ROOT / "patches/series"
PATCH_NAME = "0254-web-windowed-nla-registration-cut.patch"
PATCH = ROOT / "patches" / PATCH_NAME

GUARD = "#if !defined(__EMSCRIPTEN__) || defined(WITH_BLENDER_WEB_NLA)"
SPACE_CALL = "ED_spacetype_nla();"
MACRO_CALL = "ED_operatormacros_nla();"
CALLS = (SPACE_CALL, MACRO_CALL)
OPTION_RE = re.compile(
    r'option\(WITH_BLENDER_WEB_NLA\s+'
    r'"blender-web: register non-launch NLA editor"\s+ON\)'
)
WINDOWED_OFF_RE = re.compile(
    r'set\(WITH_BLENDER_WEB_NLA\s+OFF\s+CACHE BOOL "" FORCE\)'
)
CMAKE_FALLBACK = """if(NOT DEFINED WITH_BLENDER_WEB_NLA)
  if(WITH_BLENDER_WEB_WINDOWED)
    set(WITH_BLENDER_WEB_NLA OFF)
  else()
    set(WITH_BLENDER_WEB_NLA ON)
  endif()
endif()
if(WITH_BLENDER_WEB_NLA)
  target_compile_definitions(bf_editor_space_api PRIVATE WITH_BLENDER_WEB_NLA)
endif()"""
SHIPPING_PATHS = (
    Path("source/blender/editors/space_api/CMakeLists.txt"),
    Path("source/blender/editors/space_api/spacetypes.cc"),
)
BUILD_RULES = (
    (ROOT / "build-wasm-windowed-opt/build.ninja", False),
    (ROOT / "build-wasm-m1-parity/build.ninja", True),
    (ROOT / "build-native-m1-parity/build.ninja", True),
)


def guarded_call_counts(source: str) -> tuple[dict[str, int], dict[str, int], list[str]]:
    totals = dict.fromkeys(CALLS, 0)
    guarded = dict.fromkeys(CALLS, 0)
    errors: list[str] = []
    stack: list[str] = []
    for line_number, raw in enumerate(source.splitlines(), start=1):
        line = raw.strip()
        if line.startswith(("#if ", "#ifdef ", "#ifndef ")):
            stack.append(line)
        elif line == "#endif":
            if not stack:
                errors.append(f"unbalanced #endif at source line {line_number}")
            else:
                stack.pop()
        if line in totals:
            totals[line] += 1
            if GUARD in stack:
                guarded[line] += 1
    if stack:
        errors.append("unterminated preprocessor conditional in spacetypes.cc")
    return totals, guarded, errors


def verify(config: str, cmake: str, source: str, series: str, patch: str) -> list[str]:
    errors: list[str] = []
    if len(OPTION_RE.findall(config)) != 1:
        errors.append("config must declare the NLA option exactly once with default ON")
    if len(WINDOWED_OFF_RE.findall(config)) != 1:
        errors.append("windowed profile must force the NLA option OFF exactly once")
    if CMAKE_FALLBACK not in cmake:
        errors.append("space_api CMake fallback/compile-definition contract changed")
    if cmake.count("bf_editor_space_nla") != 1:
        errors.append("NLA editor library must remain linked exactly once")

    totals, guarded, source_errors = guarded_call_counts(source)
    errors.extend(source_errors)
    for call in CALLS:
        if totals[call] != 1:
            errors.append(f"NLA registration count changed for {call}: {totals[call]}")
        if guarded[call] != 1:
            errors.append(f"NLA registration escaped the web feature guard: {call}")

    active_series = [
        line.strip()
        for line in series.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if active_series.count(PATCH_NAME) != 1:
        errors.append("numbered patch must occur exactly once in patches/series")
    patch_paths = set(re.findall(r"^diff --git a/(\S+) b/\1$", patch, re.MULTILINE))
    expected_paths = {path.as_posix() for path in SHIPPING_PATHS}
    if patch_paths != expected_paths:
        errors.append(
            "numbered patch must touch only the space_api CMake and registration seams: "
            + ",".join(sorted(patch_paths))
        )
    forbidden_fragments = (
        "source/blender/makesdna/",
        "source/blender/makesrna/",
        "source/blender/blenloader/",
        "source/blender/blenkernel/",
        "source/blender/editors/space_nla/",
    )
    for fragment in forbidden_fragments:
        if fragment in patch:
            errors.append(f"numbered patch crosses the retained NLA data/editor boundary: {fragment}")
    return errors


def load() -> tuple[str, str, str, str, str]:
    paths = (CONFIG, SPACE_API_CMAKE, SPACETYPES, SERIES, PATCH)
    missing = [str(path.relative_to(ROOT)) for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing inputs: {', '.join(missing)}")
    return tuple(path.read_text(encoding="utf-8") for path in paths)  # type: ignore[return-value]


def run_selfcheck(inputs: tuple[str, str, str, str, str]) -> int:
    config, cmake, source, series, patch = inputs
    controls = (
        (config.replace('NLA editor" ON)', 'NLA editor" OFF)', 1), cmake, source, series, patch),
        (
            config.replace("WEB_NLA OFF CACHE", "WEB_NLA ON CACHE", 1),
            cmake,
            source,
            series,
            patch,
        ),
        (
            config,
            cmake.replace(
                "target_compile_definitions(bf_editor_space_api PRIVATE WITH_BLENDER_WEB_NLA)",
                "",
                1,
            ),
            source,
            series,
            patch,
        ),
        (config, cmake, source.replace(GUARD, "#if 1"), series, patch),
        (
            config,
            cmake,
            source.replace(SPACE_CALL, SPACE_CALL + "\n  " + SPACE_CALL, 1),
            series,
            patch,
        ),
        (
            config,
            cmake,
            source.replace(MACRO_CALL, MACRO_CALL + "\n  " + MACRO_CALL, 1),
            series,
            patch,
        ),
        (config, cmake.replace("  bf_editor_space_nla\n", "", 1), source, series, patch),
    )
    rejected = sum(bool(verify(*control)) for control in controls)
    if rejected != len(controls):
        raise RuntimeError(f"self-check admitted {len(controls) - rejected} invalid mutation(s)")
    return rejected


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_roundtrip() -> str:
    with tempfile.TemporaryDirectory(prefix="m8-nla-cut-") as temp_name:
        temp_root = Path(temp_name)
        for relative in SHIPPING_PATHS:
            destination = temp_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "upstream" / relative, destination)
        before = {relative: digest(temp_root / relative) for relative in SHIPPING_PATHS}
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
        if {relative: digest(temp_root / relative) for relative in SHIPPING_PATHS} == before:
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
        after = {relative: digest(temp_root / relative) for relative in SHIPPING_PATHS}
        if after != before:
            raise RuntimeError("isolated reverse/forward did not restore exact source bytes")
    return digest(PATCH)


def verify_build_rules() -> int:
    definition = "-DWITH_BLENDER_WEB_NLA"
    pattern = re.compile(
        r"^build source/blender/editors/space_api/CMakeFiles/"
        r"bf_editor_space_api\.dir/spacetypes\.cc\.o:.*$"
        r"(?:\n  .*){0,8}\n  DEFINES = ([^\n]*)",
        re.MULTILINE,
    )
    for path, expect_definition in BUILD_RULES:
        if not path.is_file():
            raise RuntimeError(f"missing generated build rule: {path.relative_to(ROOT)}")
        matches = pattern.findall(path.read_text(encoding="utf-8"))
        if len(matches) != 1:
            raise RuntimeError(
                f"expected one spacetypes compile rule in {path.relative_to(ROOT)}, got {len(matches)}"
            )
        present = definition in matches[0].split()
        if present != expect_definition:
            raise RuntimeError(
                f"NLA definition mismatch in {path.relative_to(ROOT)}: "
                f"expected={expect_definition} actual={present}"
            )
    return len(BUILD_RULES)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selfcheck", action="store_true")
    parser.add_argument("--roundtrip", action="store_true")
    parser.add_argument("--build-rules", action="store_true")
    args = parser.parse_args()
    try:
        inputs = load()
    except RuntimeError as error:
        print(f"M8_NLA_CUT_FAIL {error}")
        return 1
    errors = verify(*inputs)
    if errors:
        print("M8_NLA_CUT_FAIL " + " | ".join(errors))
        return 1
    try:
        controls = run_selfcheck(inputs) if args.selfcheck else 0
        patch_sha256 = run_roundtrip() if args.roundtrip else "not-run"
        build_rules = verify_build_rules() if args.build_rules else 0
    except RuntimeError as error:
        print(f"M8_NLA_CUT_FAIL {error}")
        return 1
    print(
        "M8_NLA_CUT_PASS "
        f"calls=2 controls={controls} build_rules={build_rules} "
        f"patch={PATCH_NAME} patch_sha256={patch_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
