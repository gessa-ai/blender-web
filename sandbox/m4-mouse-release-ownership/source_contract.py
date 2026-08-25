#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind window-level mouse-up delivery to an existing canvas-owned press."""

from __future__ import annotations

import argparse
from pathlib import Path


CALLBACK_MARKER = "bool cb_mousebtn(int t, const EmscriptenMouseEvent *e, void *ud)"
REGISTER_MARKER = "bool GHOST_SystemWeb::registerCanvasCallbacks()"
REMOVE_MARKER = "bool remove_html5_callback_prefix(const char *canvas,"


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


def compact(source: str) -> str:
    return " ".join(source.split()).replace("( ", "(")


def require_once(source: str, token: str, label: str) -> None:
    if source.count(token) != 1:
        raise ValueError(f"{label} requires exactly one {token!r}")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return source.replace(old, new, 1)


def mutate_method(source: str, marker: str, old: str, new: str) -> str:
    original = method(source, marker)
    changed = replace_once(original, old, new)
    return source.replace(original, changed, 1)


def validate(system: str, live_test: str, lifecycle_contract: str) -> None:
    callback = compact(method(system, CALLBACK_MARKER))
    registration = compact(method(system, REGISTER_MARKER))
    removal = compact(method(system, REMOVE_MARKER))

    require_once(
        registration,
        "emscripten_set_mouseup_callback(win, user_data, true, cb_mousebtn)",
        "window capture registration",
    )
    if "emscripten_set_mouseup_callback(canvas," in registration:
        raise ValueError("mouse-up remains scoped to the canvas")
    require_once(
        registration,
        "emscripten_set_mousedown_callback(canvas, user_data, false, cb_mousebtn)",
        "canvas press ownership",
    )
    require_once(
        removal,
        "remove_html5_callback(window, user_data, EMSCRIPTEN_EVENT_MOUSEUP, cb_mousebtn)",
        "matching window removal",
    )
    require_once(
        removal,
        "remove_html5_callback(canvas, user_data, EMSCRIPTEN_EVENT_MOUSEDOWN, cb_mousebtn)",
        "matching canvas removal",
    )

    for token in (
        "EmscriptenMouseEvent event = *e;",
        "if (t == EMSCRIPTEN_EVENT_MOUSEUP)",
        "ghost_web_bridge::button_from_dom(e->button)",
        "system->getButtonState(button, held) != GHOST_kSuccess || !held",
        "const char *selector = system->canvasSelector().c_str();",
        "event.targetX = e->clientX - canvas_left;",
        "event.targetY = e->clientY - canvas_top;",
        "ghost_web_bridge::on_mouse_button(*system, t, event);",
    ):
        require_once(callback, token, "owned-release callback")
    if callback.count("document.querySelector(UTF8ToString($0))") != 2:
        raise ValueError("owned-release callback requires two canvas-origin reads")
    if callback.index("!held") > callback.index(
            "ghost_web_bridge::on_mouse_button(*system, t, event);"):
        raise ValueError("unowned release filtering occurs after GHOST delivery")

    for token in (
        "box.x + box.width - 12",
        "await page.mouse.down({button: \"left\"});",
        "box.x + box.width + 80",
        "await page.mouse.up({button: \"left\"});",
        "_ghost_harness_input_state()) === 0",
        'owned.activeId !== "blender-canvas"',
        '!owned.log.includes("ButtonUp")',
        'window.dispatchEvent(event);',
        "unrelatedPrevented || releasesAfter !== releasesBefore",
        "outside=delivered unowned=suppressed ",
        "focus=canvas worker=proxy-pthread",
    ):
        require_once(live_test, token, "live ownership test")

    require_once(
        lifecycle_contract,
        '("window", "EMSCRIPTEN_EVENT_MOUSEUP", "cb_mousebtn")',
        "integrated lifecycle target",
    )
    if '("canvas", "EMSCRIPTEN_EVENT_MOUSEUP", "cb_mousebtn")' in lifecycle_contract:
        raise ValueError("integrated lifecycle contract still expects canvas mouse-up")


def selfcheck(system: str, live_test: str, lifecycle_contract: str) -> None:
    validate(system, live_test, lifecycle_contract)
    mutations = (
        (
            mutate_method(
                system,
                REGISTER_MARKER,
                "emscripten_set_mouseup_callback(win, user_data, true, cb_mousebtn)",
                "emscripten_set_mouseup_callback(canvas, user_data, true, cb_mousebtn)",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                REGISTER_MARKER,
                "emscripten_set_mouseup_callback(win, user_data, true, cb_mousebtn)",
                "emscripten_set_mouseup_callback(win, user_data, false, cb_mousebtn)",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                REMOVE_MARKER,
                "window, user_data, EMSCRIPTEN_EVENT_MOUSEUP, cb_mousebtn",
                "canvas, user_data, EMSCRIPTEN_EVENT_MOUSEUP, cb_mousebtn",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                CALLBACK_MARKER,
                "system->getButtonState(button, held) != GHOST_kSuccess || !held",
                "system->getButtonState(button, held) != GHOST_kSuccess",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                CALLBACK_MARKER,
                "if (t == EMSCRIPTEN_EVENT_MOUSEUP)",
                "if (t == EMSCRIPTEN_EVENT_MOUSEDOWN)",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                CALLBACK_MARKER,
                "event.targetX = e->clientX - canvas_left;",
                "event.targetX = e->targetX;",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                CALLBACK_MARKER,
                "event.targetY = e->clientY - canvas_top;",
                "event.targetY = e->targetY;",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                CALLBACK_MARKER,
                "ghost_web_bridge::on_mouse_button(*system, t, event);",
                "ghost_web_bridge::on_mouse_button(*system, t, *e);",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            system,
            replace_once(live_test, "box.x + box.width + 80", "box.x + box.width - 80"),
            lifecycle_contract,
        ),
        (
            system,
            replace_once(
                live_test,
                "_ghost_harness_input_state()) === 0",
                "_ghost_harness_input_state()) === (1 << 4)",
            ),
            lifecycle_contract,
        ),
        (
            system,
            replace_once(
                live_test,
                "unrelatedPrevented || releasesAfter !== releasesBefore",
                "unrelatedPrevented && releasesAfter !== releasesBefore",
            ),
            lifecycle_contract,
        ),
        (
            system,
            live_test,
            replace_once(
                lifecycle_contract,
                '("window", "EMSCRIPTEN_EVENT_MOUSEUP", "cb_mousebtn")',
                '("canvas", "EMSCRIPTEN_EVENT_MOUSEUP", "cb_mousebtn")',
            ),
        ),
    )
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate(*mutation)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("system_source", type=Path)
    parser.add_argument("live_test", type=Path)
    parser.add_argument("lifecycle_contract", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    inputs = (
        args.system_source.read_text(encoding="utf-8"),
        args.live_test.read_text(encoding="utf-8"),
        args.lifecycle_contract.read_text(encoding="utf-8"),
    )
    if args.selfcheck:
        selfcheck(*inputs)
    else:
        validate(*inputs)
    print(
        "MOUSE_RELEASE_OWNERSHIP_CONTRACT PASS press=canvas release=window-capture "
        "unowned=suppressed coords=canvas mutations=12"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
