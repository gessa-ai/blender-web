#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail closed on the windowed-only compositor registration cut."""

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
NODES_CMAKE = ROOT / "upstream/source/blender/nodes/CMakeLists.txt"
NODE_REGISTER = ROOT / "upstream/source/blender/nodes/intern/node_register.cc"
SERIES = ROOT / "patches/series"
PATCH_NAME = "0250-web-windowed-compositor-registration-cut.patch"
PATCH = ROOT / "patches" / PATCH_NAME

GUARD = "#if !defined(__EMSCRIPTEN__) || defined(WITH_BLENDER_WEB_COMPOSITOR)"
TREE_CALL = "register_node_tree_type_cmp();"
IMPLEMENTATION_CALL = "register_compositor_nodes();"
OPTION_RE = re.compile(
    r'option\(WITH_BLENDER_WEB_COMPOSITOR\s+'
    r'"blender-web: register non-launch compositor execution nodes"\s+ON\)'
)
WINDOWED_OFF_RE = re.compile(
    r'set\(WITH_BLENDER_WEB_COMPOSITOR\s+OFF\s+CACHE BOOL "" FORCE\)'
)
CMAKE_FALLBACK = """if(NOT DEFINED WITH_BLENDER_WEB_COMPOSITOR)
  if(WITH_BLENDER_WEB_WINDOWED)
    set(WITH_BLENDER_WEB_COMPOSITOR OFF)
  else()
    set(WITH_BLENDER_WEB_COMPOSITOR ON)
  endif()
endif()
if(WITH_BLENDER_WEB_COMPOSITOR)
  target_compile_definitions(bf_nodes PRIVATE WITH_BLENDER_WEB_COMPOSITOR)
endif()"""
SHIPPING_PATHS = (
    Path("source/blender/nodes/CMakeLists.txt"),
    Path("source/blender/nodes/intern/node_register.cc"),
)


def guarded_call_counts(source: str) -> tuple[dict[str, int], dict[str, int], list[str]]:
    calls = (TREE_CALL, IMPLEMENTATION_CALL)
    totals = {call: 0 for call in calls}
    guarded = {call: 0 for call in calls}
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
        for call in calls:
            if line == call:
                totals[call] += 1
                if GUARD in stack:
                    guarded[call] += 1
    if stack:
        errors.append("unterminated preprocessor conditional in node_register.cc")
    return totals, guarded, errors


def verify(config: str, cmake: str, source: str, series: str, patch: str) -> list[str]:
    errors: list[str] = []
    if len(OPTION_RE.findall(config)) != 1:
        errors.append("config must declare the compositor option exactly once with default ON")
    if len(WINDOWED_OFF_RE.findall(config)) != 1:
        errors.append("windowed profile must force the compositor option OFF exactly once")
    if CMAKE_FALLBACK not in cmake:
        errors.append("bf_nodes CMake fallback/compile-definition contract changed")

    totals, guarded, source_errors = guarded_call_counts(source)
    errors.extend(source_errors)
    if totals[TREE_CALL] != 1:
        errors.append(f"compositor tree registration count changed: {totals[TREE_CALL]}")
    if guarded[TREE_CALL] != 0:
        errors.append("compositor tree registration must remain available for data/RNA loading")
    if totals[IMPLEMENTATION_CALL] != 1:
        errors.append(f"compositor implementation registration count changed: {totals[IMPLEMENTATION_CALL]}")
    if guarded[IMPLEMENTATION_CALL] != 1:
        errors.append("compositor implementation registration escaped the web feature guard")
    if source.find(TREE_CALL) >= source.find(IMPLEMENTATION_CALL):
        errors.append("compositor tree registration must precede concrete node registration")

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
            "numbered patch must touch only the bf_nodes CMake and registration seams: "
            + ",".join(sorted(patch_paths))
        )
    return errors


def load() -> tuple[str, str, str, str, str]:
    paths = (CONFIG, NODES_CMAKE, NODE_REGISTER, SERIES, PATCH)
    missing = [str(path.relative_to(ROOT)) for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing inputs: {', '.join(missing)}")
    return tuple(path.read_text(encoding="utf-8") for path in paths)  # type: ignore[return-value]


def run_selfcheck(inputs: tuple[str, str, str, str, str]) -> int:
    config, cmake, source, series, patch = inputs
    guarded_tree = source.replace(
        TREE_CALL,
        f"{GUARD}\n  {TREE_CALL}\n#endif",
        1,
    )
    controls = (
        (config.replace("execution nodes\" ON)", "execution nodes\" OFF)", 1), cmake, source, series, patch),
        (config.replace("COMPOSITOR OFF CACHE", "COMPOSITOR ON CACHE", 1), cmake, source, series, patch),
        (config, cmake.replace("target_compile_definitions(bf_nodes PRIVATE WITH_BLENDER_WEB_COMPOSITOR)", "", 1), source, series, patch),
        (config, cmake, source.replace(GUARD, "#if 1", 1), series, patch),
        (config, cmake, guarded_tree, series, patch),
        (config, cmake, source.replace(IMPLEMENTATION_CALL, IMPLEMENTATION_CALL + "\n  " + IMPLEMENTATION_CALL, 1), series, patch),
    )
    rejected = sum(bool(verify(*control)) for control in controls)
    if rejected != len(controls):
        raise RuntimeError(f"self-check admitted {len(controls) - rejected} invalid mutation(s)")
    return rejected


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_roundtrip() -> str:
    with tempfile.TemporaryDirectory(prefix="m8-compositor-cut-") as temp_name:
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selfcheck", action="store_true")
    parser.add_argument("--roundtrip", action="store_true")
    args = parser.parse_args()
    try:
        inputs = load()
    except RuntimeError as error:
        print(f"M8_COMPOSITOR_CUT_FAIL {error}")
        return 1
    errors = verify(*inputs)
    if errors:
        print("M8_COMPOSITOR_CUT_FAIL " + " | ".join(errors))
        return 1
    try:
        controls = run_selfcheck(inputs) if args.selfcheck else 0
        patch_sha256 = run_roundtrip() if args.roundtrip else "not-run"
    except RuntimeError as error:
        print(f"M8_COMPOSITOR_CUT_FAIL {error}")
        return 1
    print(
        "M8_COMPOSITOR_CUT_PASS "
        f"calls=2 controls={controls} patch={PATCH_NAME} patch_sha256={patch_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
