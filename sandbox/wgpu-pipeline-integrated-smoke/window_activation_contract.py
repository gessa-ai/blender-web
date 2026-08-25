#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind the web window activation result to its owned GHOST drawing context."""

from __future__ import annotations

import argparse
from pathlib import Path


WINDOW_MARKER = "GHOST_TSuccess GHOST_WindowWeb::activateDrawingContext()"
BASE_MARKER = "GHOST_TSuccess GHOST_Window::activateDrawingContext()"
WINDOW_DELEGATE = "return GHOST_Window::activateDrawingContext();"
BASE_DELEGATE = "return context_->activateDrawingContext();"


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


def validate(window_source: str, base_source: str) -> None:
    window_activate = method(window_source, WINDOW_MARKER)
    base_activate = method(base_source, BASE_MARKER)
    if window_activate.count(WINDOW_DELEGATE) != 1:
        raise ValueError("web window activation does not delegate through GHOST_Window")
    if "return GHOST_kSuccess;" in window_activate or "return GHOST_kFailure;" in window_activate:
        raise ValueError("web window activation contains a hard-coded status")
    if base_activate.count(BASE_DELEGATE) != 1:
        raise ValueError("stock GHOST_Window activation no longer delegates to its context")


def selfcheck(window_source: str, base_source: str) -> None:
    validate(window_source, base_source)
    mutations = (
        window_source.replace(WINDOW_DELEGATE, "return GHOST_kFailure;", 1),
        window_source.replace(WINDOW_DELEGATE, "return GHOST_kSuccess;", 1),
        window_source.replace(WINDOW_DELEGATE, "return swapBufferRelease();", 1),
    )
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate(mutation, base_source)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("window_source", type=Path)
    parser.add_argument("base_source", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    window_source = args.window_source.read_text(encoding="utf-8")
    base_source = args.base_source.read_text(encoding="utf-8")
    if args.selfcheck:
        selfcheck(window_source, base_source)
    else:
        validate(window_source, base_source)
    print("WINDOW_ACTIVATION_CONTRACT PASS cases=1 mutations=3 status=delegated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
