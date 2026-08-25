#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Require GHOST window titles to reach the browser main thread synchronously."""

from __future__ import annotations

import argparse
from pathlib import Path


SET_MARKER = "void GHOST_WindowWeb::setTitle(const char *title)"
GET_MARKER = "std::string GHOST_WindowWeb::getTitle() const"


def method(source: str, marker: str) -> str:
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"missing method: {marker}")
    opening = source.find("{", start)
    if opening < 0:
        raise ValueError(f"missing method body: {marker}")
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated method: {marker}")


def validate(source: str) -> None:
    setter = method(source, SET_MARKER)
    getter = method(source, GET_MARKER)
    required = (
        'title_ = title ? title : "";',
        "MAIN_THREAD_EM_ASM(",
        'typeof document !== "undefined"',
        "document.title = UTF8ToString($0);",
        "title_.c_str());",
    )
    for token in required:
        if setter.count(token) != 1:
            raise ValueError(f"title setter requires exactly one {token!r}")
    if "MAIN_THREAD_ASYNC_EM_ASM" in setter:
        raise ValueError("asynchronous title proxy outlives its c_str input")
    if "ghost_web_set_document_title" in source:
        raise ValueError("worker-local EM_JS title helper remains")
    if getter.count("return title_;") != 1:
        raise ValueError("title getter does not preserve the published title")


def selfcheck(source: str) -> None:
    validate(source)
    mutations = (
        source.replace("MAIN_THREAD_EM_ASM(", "EM_ASM(", 1),
        source.replace("document.title = UTF8ToString($0);", "void($0);", 1),
        source.replace("title_.c_str());", "title);", 1),
        source.replace('title_ = title ? title : "";', "(void)title;", 1),
        source.replace("return title_;", 'return "";', 1),
    )
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate(mutation)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("window_source", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    source = args.window_source.read_text(encoding="utf-8")
    if args.selfcheck:
        selfcheck(source)
    else:
        validate(source)
    print("WINDOW_TITLE_CONTRACT PASS cases=unicode,empty mutations=5 thread=browser-main-sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
