#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind the Web GHOST context's documented initialization lifecycles to its class."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


CLASS_DECLARATION = "class GHOST_ContextWGPUWeb : public GHOST_Context {"
ADJACENT_CLASS_DOC = re.compile(
    r"(?P<doc>/\*\*(?:(?!\*/).)*\*/)\s*"
    + re.escape(CLASS_DECLARATION),
    re.DOTALL,
)

REQUIRED_TEXT = (
    "The class derives from `GHOST_Context` and has two deliberately separate "
    "initialization paths.",
    "Shipping path: `wgpu-preinit-worker.js` asynchronously acquires a device on the "
    "WM worker and, for a presentable window, validates the canvas, surface, and initial "
    "backbuffer before `main()`.",
    "`initializeDrawingContext()` then synchronously imports the mode-appropriate "
    "pre-main bundle.",
    "The shipping path does not call `initAsync()`.",
    "Standalone proof path: `initAsync()` asynchronously requests an adapter and device "
    "through `CallbackMode::AllowSpontaneous`, creates the requested presentation "
    "resources, and invokes its ready callback when acquisition settles.",
    "Both paths serialize asynchronous callback delivery and public owner access through "
    "the shared `CallbackLifetime` execution gate.",
    "Destruction closes admission and waits for admitted work before releasing context "
    "storage.",
)

RETIRED_TEXT = (
    re.compile(r"one-time\s+(?:top-level\s+)?(?:startup\s+)?await", re.IGNORECASE),
    re.compile(r"GHOST-web\s+system\s+runs\s+`?initAsync", re.IGNORECASE),
    re.compile(r"gates?\s+the\s+WM\s+main-loop\s+start", re.IGNORECASE),
    re.compile(r"does\s+not\s+subclass", re.IGNORECASE),
)


class ContractError(RuntimeError):
    pass


def normalize_comment(comment: str) -> str:
    lines = comment.splitlines()
    if not lines or not lines[0].lstrip().startswith("/**"):
        raise ContractError("the adjacent class lifecycle text is not a Doxygen comment")
    normalized: list[str] = []
    for line in lines:
        line = re.sub(r"^\s*/?\*+/?\s?", "", line)
        normalized.append(line)
    return " ".join(" ".join(normalized).split())


def analyze(source: str) -> dict[str, int]:
    if source.count(CLASS_DECLARATION) != 1:
        raise ContractError("the exact GHOST_Context inheritance declaration must occur once")

    pragma_offset = source.find("#pragma once")
    if pragma_offset < 0:
        raise ContractError("header has no #pragma once boundary")
    preamble = source[:pragma_offset]
    duplicated_terms = (
        "`initAsync()`",
        "`initializeDrawingContext()`",
        "`CallbackLifetime`",
        "Shipping path:",
        "Standalone proof path:",
    )
    if any(term in preamble for term in duplicated_terms):
        raise ContractError("initialization lifecycle text is duplicated in the file preamble")

    matches = tuple(ADJACENT_CLASS_DOC.finditer(source))
    if len(matches) != 1:
        raise ContractError("the class must have one immediately adjacent lifecycle comment")
    documentation = normalize_comment(matches[0].group("doc"))

    for required in REQUIRED_TEXT:
        if required not in documentation:
            raise ContractError(f"class lifecycle documentation is missing {required!r}")
    for retired in RETIRED_TEXT:
        if retired.search(documentation):
            raise ContractError(
                f"class lifecycle documentation retains retired text {retired.pattern!r}"
            )
    if documentation.count("`initAsync()`") != 2:
        raise ContractError("class lifecycle documentation must name exactly two initAsync roles")

    return {
        "paths": 2,
        "pre_main_import": 1,
        "standalone_async": 1,
        "owner_gate": 1,
    }


def expect_rejected(name: str, source: str) -> None:
    try:
        analyze(source)
    except ContractError:
        return
    raise ContractError(f"mutation control {name!r} was incorrectly accepted")


def replace_once(source: str, old: str, new: str, name: str) -> str:
    if source.count(old) != 1:
        raise ContractError(
            f"self-test {name}: expected one occurrence of {old!r}, got {source.count(old)}"
        )
    return source.replace(old, new, 1)


def replace_normalized_once(source: str, old: str, new: str, name: str) -> str:
    pattern = re.compile(r"[\s*]+".join(re.escape(word) for word in old.split()))
    matches = tuple(pattern.finditer(source))
    if len(matches) != 1:
        raise ContractError(
            f"self-test {name}: expected one whitespace-normalized occurrence of {old!r}, "
            f"got {len(matches)}"
        )
    match = matches[0]
    return source[: match.start()] + new + source[match.end() :]


def run_self_test(source: str) -> None:
    expect_rejected(
        "wrong inheritance",
        replace_once(
            source,
            CLASS_DECLARATION,
            "class GHOST_ContextWGPUWeb {",
            "wrong inheritance",
        ),
    )
    expect_rejected(
        "shipping calls initAsync",
        replace_normalized_once(
            source,
            REQUIRED_TEXT[3],
            "The shipping path calls `initAsync()` before importing the device.",
            "shipping calls initAsync",
        ),
    )
    expect_rejected(
        "standalone path omitted",
        replace_normalized_once(source, REQUIRED_TEXT[4], "", "standalone path omitted"),
    )
    expect_rejected(
        "owner gate omitted",
        replace_normalized_once(source, REQUIRED_TEXT[5], "", "owner gate omitted"),
    )

    match = ADJACENT_CLASS_DOC.search(source)
    if match is None:
        raise ContractError("self-test could not locate the accepted adjacent class comment")
    prefix_only = (
        source[: source.find("#pragma once")]
        + match.group("doc")
        + "\n"
        + source[source.find("#pragma once") : match.start("doc")]
        + "/** Browser WebGPU context. */\n"
        + source[match.end("doc") :]
    )
    expect_rejected("prefix-only lifecycle", prefix_only)

    stale_duplicate = replace_normalized_once(
        source,
        REQUIRED_TEXT[3],
        REQUIRED_TEXT[3]
        + " The GHOST-web system runs initAsync and gates the WM main-loop start on its "
        "ready callback through a one-time startup await.",
        "stale duplicate",
    )
    expect_rejected("stale duplicate", stale_duplicate)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("header", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    try:
        source = args.header.read_text(encoding="utf-8")
        report = analyze(source)
        if args.self_test:
            run_self_test(source)
    except (ContractError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        "CONTEXT_LIFECYCLE_DOC_PASS "
        f"paths={report['paths']} pre_main_import={report['pre_main_import']} "
        f"standalone_async={report['standalone_async']} owner_gate={report['owner_gate']}"
    )
    if args.self_test:
        print(
            "CONTEXT_LIFECYCLE_DOC_SELFTEST_PASS controls=6 "
            "wrong_inheritance=reject shipping_calls_initAsync=reject "
            "standalone_omission=reject owner_gate_omission=reject "
            "prefix_only=reject stale_duplicate=reject"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
