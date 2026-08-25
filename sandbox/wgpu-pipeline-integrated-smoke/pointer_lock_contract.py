#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind browser cursor grab to Pointer Lock and relative GHOST motion."""

from __future__ import annotations

import argparse
from pathlib import Path


GRAB_MARKER = "GHOST_TSuccess GHOST_WindowWeb::setWindowCursorGrab(GHOST_TGrabCursorMode mode)"
SOFTWARE_CURSOR_MARKER = "bool GHOST_WindowWeb::getCursorGrabUseSoftwareDisplay()"
MOVE_MARKER = "void on_mouse_move(GHOST_SystemWeb &sys, const EmscriptenMouseEvent &e)"
CAPABILITIES_MARKER = "GHOST_TCapabilityFlag GHOST_SystemWeb::getCapabilities() const"
WARP_MARKER = "GHOST_TSuccess GHOST_SystemWeb::setCursorPosition(int32_t"


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


def mutate_method(source: str, marker: str, old: str, new: str) -> str:
    original = method(source, marker)
    changed = original.replace(old, new, 1)
    if changed == original:
        raise ValueError(f"mutation input is absent from {marker}: {old!r}")
    return source.replace(original, changed, 1)


def validate(window: str, header: str, bridge: str, system: str) -> None:
    grab = method(window, GRAB_MARKER)
    software_cursor = method(window, SOFTWARE_CURSOR_MARKER)
    move = method(bridge, MOVE_MARKER)
    capabilities = method(system, CAPABILITIES_MARKER)
    warp = method(system, WARP_MARKER)

    if header.count(
        "GHOST_TSuccess setWindowCursorGrab(GHOST_TGrabCursorMode mode) override;"
    ) != 1:
        raise ValueError("window header does not declare the cursor-grab implementation")
    if header.count("bool getCursorGrabUseSoftwareDisplay() override;") != 1:
        raise ValueError("window header does not declare the software cursor policy")

    required_grab = (
        "switch (mode)",
        "case GHOST_kGrabDisable:",
        "case GHOST_kGrabNormal:",
        "case GHOST_kGrabWrap:",
        "case GHOST_kGrabHide:",
        "emscripten_exit_pointerlock()",
        "emscripten_request_pointerlock(canvas_selector_.c_str(), true)",
        "EMSCRIPTEN_RESULT_DEFERRED",
    )
    for token in required_grab:
        if grab.count(token) != 1:
            raise ValueError(f"cursor grab requires exactly one {token!r}")
    if grab.count("return GHOST_kFailure;") < 1:
        raise ValueError("unknown cursor-grab modes do not fail honestly")
    normal = grab[grab.index("case GHOST_kGrabNormal:") : grab.index("case GHOST_kGrabWrap:")]
    if normal.count("return GHOST_kSuccess;") != 1:
        raise ValueError("normal visible-pointer grab does not preserve SDL semantics")
    if software_cursor.count("return getCursorGrabMode() == GHOST_kGrabWrap;") != 1:
        raise ValueError("wrap grab does not preserve a visible software cursor")

    required_move = (
        "int32_t x = e.targetX;",
        "int32_t y = e.targetY;",
        "win->getCursorGrabModeIsWarp()",
        "sys.getCursorPosition(previous_x, previous_y)",
        "int64_t(previous) + int64_t(movement)",
        "std::numeric_limits<int32_t>::min()",
        "std::numeric_limits<int32_t>::max()",
        "x = add_motion(previous_x, e.movementX);",
        "y = add_motion(previous_y, e.movementY);",
        "sys.noteCursor(x, y);",
        "win, x, y, GHOST_TABLET_DATA_NONE",
    )
    for token in required_move:
        if move.count(token) != 1:
            raise ValueError(f"relative cursor bridge requires exactly one {token!r}")
    if "sys.noteCursor(e.targetX, e.targetY);" in move:
        raise ValueError("locked motion still publishes frozen DOM absolute coordinates")

    if capabilities.count("GHOST_kCapabilityCursorWarp") != 1:
        raise ValueError("absolute cursor warp must remain masked")
    if warp.count("return GHOST_kFailure;") != 1 or "return GHOST_kSuccess;" in warp:
        raise ValueError("absolute cursor positioning is falsely advertised")


def selfcheck(window: str, header: str, bridge: str, system: str) -> None:
    validate(window, header, bridge, system)
    mutations = (
        (mutate_method(window, GRAB_MARKER, "emscripten_exit_pointerlock()",
                       "EMSCRIPTEN_RESULT_SUCCESS"), header, bridge, system),
        (mutate_method(window, GRAB_MARKER,
                       "emscripten_request_pointerlock(canvas_selector_.c_str(), true)",
                       "EMSCRIPTEN_RESULT_SUCCESS"), header, bridge, system),
        (mutate_method(window, GRAB_MARKER,
                       "emscripten_request_pointerlock(canvas_selector_.c_str(), true)",
                       "emscripten_request_pointerlock(canvas_selector_.c_str(), false)"),
         header, bridge, system),
        (mutate_method(window, GRAB_MARKER, "EMSCRIPTEN_RESULT_DEFERRED",
                       "EMSCRIPTEN_RESULT_SUCCESS"), header, bridge, system),
        (mutate_method(window, GRAB_MARKER, "case GHOST_kGrabNormal:",
                       "case GHOST_kGrabDisable:"), header, bridge, system),
        (window, header.replace("setWindowCursorGrab", "setWindowCursorGrabMissing", 1), bridge, system),
        (mutate_method(window, SOFTWARE_CURSOR_MARKER, "GHOST_kGrabWrap",
                       "GHOST_kGrabHide"), header, bridge, system),
        (window, header, bridge.replace("win->getCursorGrabModeIsWarp()", "false", 1), system),
        (window, header, bridge.replace("e.movementX", "e.targetX", 1), system),
        (window, header, bridge.replace("e.movementY", "e.targetY", 1), system),
        (window, header, bridge.replace("sys.getCursorPosition(previous_x, previous_y)",
                                        "GHOST_kFailure", 1), system),
        (window, header, bridge, system.replace("GHOST_kCapabilityCursorWarp |", "", 1)),
        (window, header, bridge,
         mutate_method(system, WARP_MARKER, "return GHOST_kFailure;",
                       "return GHOST_kSuccess;")),
    )
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate(*mutation)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("window_source", type=Path)
    parser.add_argument("window_header", type=Path)
    parser.add_argument("bridge_source", type=Path)
    parser.add_argument("system_source", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    sources = tuple(
        path.read_text(encoding="utf-8")
        for path in (
            args.window_source,
            args.window_header,
            args.bridge_source,
            args.system_source,
        )
    )
    if args.selfcheck:
        selfcheck(*sources)
    else:
        validate(*sources)
    print(
        "POINTER_LOCK_CONTRACT PASS modes=normal,wrap,hide,disable relative=saturated "
        "cursor=wrap-software capability=absolute-warp-off mutations=13"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
