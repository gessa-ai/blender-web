#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Require web window state changes to use the browser Fullscreen API honestly."""

from __future__ import annotations

import argparse
from pathlib import Path


SET_MARKER = "GHOST_TSuccess GHOST_WindowWeb::setState(GHOST_TWindowState state)"
GET_MARKER = "GHOST_TWindowState GHOST_WindowWeb::getState() const"


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

    required_setter = (
        "switch (state)",
        "case GHOST_kWindowStateNormal:",
        "case GHOST_kWindowStateMaximized:",
        "case GHOST_kWindowStateMinimized:",
        "case GHOST_kWindowStateFullScreen:",
        "emscripten_exit_fullscreen()",
        "EmscriptenFullscreenStrategy strategy = {};",
        "strategy.scaleMode = EMSCRIPTEN_FULLSCREEN_SCALE_STRETCH;",
        "strategy.canvasResolutionScaleMode = EMSCRIPTEN_FULLSCREEN_CANVAS_SCALE_NONE;",
        "strategy.filteringMode = EMSCRIPTEN_FULLSCREEN_FILTERING_DEFAULT;",
        "emscripten_request_fullscreen_strategy(",
        "canvas_selector_.c_str(), true, &strategy)",
        "EMSCRIPTEN_RESULT_DEFERRED",
    )
    for token in required_setter:
        if setter.count(token) != 1:
            raise ValueError(f"window-state setter requires exactly one {token!r}")

    if setter.count("return GHOST_kFailure;") < 2:
        raise ValueError("minimized and unknown window states must fail honestly")
    if "(void)state;" in setter:
        raise ValueError("window-state request is still ignored")

    required_getter = (
        "emscripten_get_fullscreen_status(&fs)",
        "fs.isFullscreen",
        "return GHOST_kWindowStateFullScreen;",
        "return GHOST_kWindowStateNormal;",
    )
    for token in required_getter:
        if getter.count(token) != 1:
            raise ValueError(f"window-state getter requires exactly one {token!r}")


def selfcheck(source: str) -> None:
    validate(source)
    mutations = (
        source.replace("emscripten_exit_fullscreen()", "EMSCRIPTEN_RESULT_SUCCESS", 1),
        source.replace("EMSCRIPTEN_FULLSCREEN_SCALE_STRETCH", "EMSCRIPTEN_FULLSCREEN_SCALE_DEFAULT", 1),
        source.replace("EMSCRIPTEN_FULLSCREEN_CANVAS_SCALE_NONE", "EMSCRIPTEN_FULLSCREEN_CANVAS_SCALE_HIDEF", 1),
        source.replace("canvas_selector_.c_str(), true, &strategy", "canvas_selector_.c_str(), false, &strategy", 1),
        source.replace("EMSCRIPTEN_RESULT_DEFERRED", "EMSCRIPTEN_RESULT_SUCCESS", 1),
        source.replace("case GHOST_kWindowStateMinimized:", "case GHOST_kWindowStateNormal:", 1),
        source.replace("return GHOST_kWindowStateFullScreen;", "return GHOST_kWindowStateNormal;", 1),
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
    print(
        "FULLSCREEN_STATE_CONTRACT PASS states=normal,maximized,minimized,fullscreen "
        "entry=deferred-user-activation exit=browser-api mutations=7"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
