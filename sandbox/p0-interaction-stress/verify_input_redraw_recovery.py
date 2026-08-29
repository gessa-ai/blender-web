#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind ordinary web input to a bounded burst plus a terminal full retry tail."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SYSTEM_HEADER = ROOT / "platform_web/ghost/GHOST_SystemWeb.hh"
SYSTEM_SOURCE = ROOT / "platform_web/ghost/GHOST_SystemWeb.cc"
BRIDGE_SOURCE = ROOT / "platform_web/ghost/GHOST_EventBridgeWeb.cc"
CONTEXT_SOURCE = ROOT / "platform_web/ghost/GHOST_ContextWGPUWeb.cc"

HELPER_DECL = "void requestInputRedrawRetry(const char *terminal_kind = nullptr,"
HELPER = "void GHOST_SystemWeb::requestInputRedrawRetry(const char *terminal_kind,"
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
REQUESTS = {
    "mouse-move": "sys.requestInputRedrawRetry();",
    "mouse-button": (
        'sys.requestInputRedrawRetry(down ? nullptr : "button-up", uint32_t(button));'
    ),
    "wheel": 'sys.requestInputRedrawRetry("wheel");',
    "key": 'sys.requestInputRedrawRetry(down ? nullptr : "key-up", uint32_t(key));',
}
EXPORT = 'extern "C" EMSCRIPTEN_KEEPALIVE double bw_redraw_retry_count(void)'


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


def validate(header: str, system: str, bridge: str, context: str) -> None:
    if header.count(HELPER_DECL) != 1:
        raise ValueError("system API lost the input redraw-retry declaration")

    helper = method(system, HELPER)
    if helper.count("ghost_web::request_input_redraw_retry()") != 1:
        raise ValueError("system helper no longer publishes exactly one input activity edge")
    if "ghost_web::request_redraw_retry();" in helper:
        raise ValueError("ordinary input collapsed back into shader-readiness ownership")
    if "request_redraw_episode" in helper:
        raise ValueError("ordinary input must not enter the resize-only episode/barrier path")

    callbacks = {
        "mouse-move": method(bridge, MOVE),
        "mouse-button": method(bridge, BUTTON),
        "wheel": method(bridge, WHEEL),
        "key": method(bridge, KEY),
    }
    for label, body in callbacks.items():
        if body.count(REQUESTS[label]) != 1:
            raise ValueError(f"{label} does not publish exactly one coalescible retry")
        if "request_redraw_episode" in body:
            raise ValueError(f"{label} incorrectly starts a resize-only redraw episode")

    button = callbacks["mouse-button"]
    button_request = REQUESTS["mouse-button"]
    invalid_guard = "if (button == GHOST_kButtonMaskNone)"
    if button.index(button_request) < button.index(invalid_guard):
        raise ValueError("unsupported mouse buttons publish a redraw retry")

    wheel = callbacks["wheel"]
    wheel_request = REQUESTS["wheel"]
    zero_guard = "if (e.deltaY == 0.0 && e.deltaX == 0.0)"
    if zero_guard not in wheel or wheel.index(wheel_request) < wheel.index(zero_guard):
        raise ValueError("zero-delta wheel events publish a redraw retry")
    if wheel.index(wheel_request) > min(wheel.index("if (e.deltaY != 0.0)"),
                                        wheel.index("if (e.deltaX != 0.0)")):
        raise ValueError("wheel retry is conditional on only one axis")

    if bridge.count("sys.requestInputRedrawRetry") != len(callbacks):
        raise ValueError("unexpected input redraw-retry call outside the four input bridges")

    export = method(context, EXPORT)
    if export.count("ghost_web::redraw_retry_generation()") != 1:
        raise ValueError("browser diagnostic does not expose the live retry generation")


def self_check(header: str, system: str, bridge: str, context: str) -> None:
    validate(header, system, bridge, context)
    helper = method(system, HELPER)
    callbacks = tuple(method(bridge, signature) for signature in (MOVE, BUTTON, WHEEL, KEY))
    mutations: list[tuple[str, str, str, str]] = [
        (header.replace(HELPER_DECL, "", 1), system, bridge, context),
        (
            header,
            replace_once(
                system,
                helper,
                helper.replace("ghost_web::request_input_redraw_retry()", "", 1),
            ),
            bridge,
            context,
        ),
        (
            header,
            replace_once(
                system,
                helper,
                helper.replace(
                    "ghost_web::request_input_redraw_retry()",
                    "ghost_web::request_redraw_episode();",
                    1,
                ),
            ),
            bridge,
            context,
        ),
    ]
    for (label, callback) in zip(("mouse-move", "mouse-button", "wheel", "key"), callbacks):
        mutations.append(
            (
                header,
                system,
                replace_once(bridge, callback, callback.replace(REQUESTS[label], "", 1)),
                context,
            )
        )

    button = callbacks[1]
    button_request = REQUESTS["mouse-button"]
    moved_button_request = button.replace(f"  {button_request}\n", "", 1)
    moved_button_request = moved_button_request.replace(
        "  if (button == GHOST_kButtonMaskNone)",
        f"  {button_request}\n  if (button == GHOST_kButtonMaskNone)",
        1,
    )
    mutations.append(
        (
            header,
            system,
            replace_once(bridge, button, moved_button_request),
            context,
        )
    )
    mutations.append((header, system, bridge + "\nsys.requestInputRedrawRetry();\n", context))
    export = method(context, EXPORT)
    mutations.append((
        header,
        system,
        bridge,
        replace_once(
            context,
            export,
            export.replace("ghost_web::redraw_retry_generation()", "0", 1),
        ),
    ))

    rejected = 0
    for mutated_header, mutated_system, mutated_bridge, mutated_context in mutations:
        try:
            validate(mutated_header, mutated_system, mutated_bridge, mutated_context)
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
    context = CONTEXT_SOURCE.read_text(encoding="utf-8")
    if args.self_check:
        self_check(header, system, bridge, context)
    else:
        validate(header, system, bridge, context)
        print(
            "P0J_INPUT_REDRAW_RECOVERY_SOURCE_PASS "
            "events=move,button,wheel,key mode=bounded-burst+terminal-full-tail"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"P0J_INPUT_REDRAW_RECOVERY_SOURCE_FAIL {error}")
        raise SystemExit(1)
