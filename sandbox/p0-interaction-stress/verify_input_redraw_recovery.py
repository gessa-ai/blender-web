#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind ordinary web input to the existing bounded redraw-retry generation."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SYSTEM_HEADER = ROOT / "platform_web/ghost/GHOST_SystemWeb.hh"
SYSTEM_SOURCE = ROOT / "platform_web/ghost/GHOST_SystemWeb.cc"
BRIDGE_SOURCE = ROOT / "platform_web/ghost/GHOST_EventBridgeWeb.cc"

HELPER_DECL = "void requestInputRedrawRetry();"
HELPER = "void GHOST_SystemWeb::requestInputRedrawRetry()"
MOVE = "void on_mouse_move(GHOST_SystemWeb &sys, const EmscriptenMouseEvent &e)"
BUTTON = (
    "void on_mouse_button(GHOST_SystemWeb &sys, int em_event_type, "
    "const EmscriptenMouseEvent &e)"
)
WHEEL = "void on_wheel(GHOST_SystemWeb &sys, const EmscriptenWheelEvent &e)"
KEY = (
    "void on_key(GHOST_SystemWeb &sys, int em_event_type, "
    "const EmscriptenKeyboardEvent &e)"
)
REQUEST = "sys.requestInputRedrawRetry();"


def method(source: str, signature: str) -> str:
    if source.count(signature) != 1:
        raise ValueError(f"method boundary is not unique: {signature}")
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated method: {signature}")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation boundary is not unique: {old}")
    return source.replace(old, new, 1)


def validate(header: str, system: str, bridge: str) -> None:
    if header.count(HELPER_DECL) != 1:
        raise ValueError("system API lost the input redraw-retry declaration")

    helper = method(system, HELPER)
    if helper.count("ghost_web::request_redraw_retry();") != 1:
        raise ValueError("system helper no longer publishes exactly one bounded retry")
    if "request_redraw_episode" in helper:
        raise ValueError("ordinary input must not enter the resize-only episode/barrier path")

    callbacks = {
        "mouse-move": method(bridge, MOVE),
        "mouse-button": method(bridge, BUTTON),
        "wheel": method(bridge, WHEEL),
        "key": method(bridge, KEY),
    }
    for label, body in callbacks.items():
        if body.count(REQUEST) != 1:
            raise ValueError(f"{label} does not publish exactly one coalescible retry")
        if "request_redraw_episode" in body:
            raise ValueError(f"{label} incorrectly starts a resize-only redraw episode")

    button = callbacks["mouse-button"]
    invalid_guard = "if (button == GHOST_kButtonMaskNone)"
    if button.index(REQUEST) < button.index(invalid_guard):
        raise ValueError("unsupported mouse buttons publish a redraw retry")

    wheel = callbacks["wheel"]
    zero_guard = "if (e.deltaY == 0.0 && e.deltaX == 0.0)"
    if zero_guard not in wheel or wheel.index(REQUEST) < wheel.index(zero_guard):
        raise ValueError("zero-delta wheel events publish a redraw retry")
    if wheel.index(REQUEST) > min(wheel.index("if (e.deltaY != 0.0)"),
                                  wheel.index("if (e.deltaX != 0.0)")):
        raise ValueError("wheel retry is conditional on only one axis")

    if bridge.count(REQUEST) != len(callbacks):
        raise ValueError("unexpected input redraw-retry call outside the four input bridges")


def self_check(header: str, system: str, bridge: str) -> None:
    validate(header, system, bridge)
    helper = method(system, HELPER)
    callbacks = tuple(method(bridge, signature) for signature in (MOVE, BUTTON, WHEEL, KEY))
    mutations: list[tuple[str, str, str]] = [
        (header.replace(HELPER_DECL, "", 1), system, bridge),
        (
            header,
            replace_once(
                system,
                helper,
                helper.replace("ghost_web::request_redraw_retry();", "", 1),
            ),
            bridge,
        ),
        (
            header,
            replace_once(
                system,
                helper,
                helper.replace(
                    "ghost_web::request_redraw_retry();",
                    "ghost_web::request_redraw_episode();",
                    1,
                ),
            ),
            bridge,
        ),
    ]
    for callback in callbacks:
        mutations.append((header, system, replace_once(bridge, callback, callback.replace(REQUEST, "", 1))))

    button = callbacks[1]
    moved_button_request = button.replace(f"  {REQUEST}\n", "", 1)
    moved_button_request = moved_button_request.replace(
        "  if (button == GHOST_kButtonMaskNone)",
        f"  {REQUEST}\n  if (button == GHOST_kButtonMaskNone)",
        1,
    )
    mutations.append(
        (
            header,
            system,
            replace_once(bridge, button, moved_button_request),
        )
    )
    mutations.append((header, system, bridge + f"\n{REQUEST}\n"))

    rejected = 0
    for mutated_header, mutated_system, mutated_bridge in mutations:
        try:
            validate(mutated_header, mutated_system, mutated_bridge)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0J_INPUT_REDRAW_RECOVERY_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    header = SYSTEM_HEADER.read_text(encoding="utf-8")
    system = SYSTEM_SOURCE.read_text(encoding="utf-8")
    bridge = BRIDGE_SOURCE.read_text(encoding="utf-8")
    if args.self_check:
        self_check(header, system, bridge)
    else:
        validate(header, system, bridge)
        print(
            "P0J_INPUT_REDRAW_RECOVERY_SOURCE_PASS "
            "events=move,button,wheel,key mode=bounded-retry"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"P0J_INPUT_REDRAW_RECOVERY_SOURCE_FAIL {error}")
        raise SystemExit(1)
