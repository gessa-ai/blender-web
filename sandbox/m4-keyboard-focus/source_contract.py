#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind raw GHOST keyboard delivery to the DOM-focused canvas."""

from __future__ import annotations

import argparse
from pathlib import Path


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


def validate(system: str, live_test: str, lifecycle_test: str) -> None:
    registration = compact(method(system, REGISTER_MARKER))
    removal = compact(method(system, REMOVE_MARKER))
    for event in ("keydown", "keyup"):
        require_once(
            registration,
            f"emscripten_set_{event}_callback(canvas, user_data, false, cb_key)",
            "canvas keyboard registration",
        )
        if f"emscripten_set_{event}_callback(win, user_data, false, cb_key)" in registration:
            raise ValueError(f"{event} remains registered on the browser window")

    for event in ("KEYDOWN", "KEYUP"):
        require_once(
            removal,
            f"remove_html5_callback(canvas, user_data, EMSCRIPTEN_EVENT_{event}, cb_key)",
            "canvas keyboard removal",
        )
        if (
            f"remove_html5_callback(window, user_data, EMSCRIPTEN_EVENT_{event}, cb_key)"
            in removal
        ):
            raise ValueError(f"{event} removal targets the browser window")

    for token in (
        'const canvas = page.locator("#blender-canvas");',
        "await canvas.focus();",
        'await page.keyboard.press("a");',
        'document.querySelector("#clear").focus();',
        'await page.keyboard.press("b");',
        'snapshot.activeId !== "clear"',
        'snapshot.log.includes("KeyDown") || snapshot.log.includes("KeyUp")',
        "focused=delivered blurred=suppressed worker=proxy-pthread",
    ):
        require_once(live_test, token, "live focus test")

    for token in (
        "this instanceof HTMLCanvasElement",
        'this.id === "blender-canvas"',
        'document.querySelector("#blender-canvas").dispatchEvent(',
    ):
        require_once(lifecycle_test, token, "registration-epoch test")


def selfcheck(system: str, live_test: str, lifecycle_test: str) -> None:
    validate(system, live_test, lifecycle_test)
    mutations = (
        (
            replace_once(
                system,
                "emscripten_set_keydown_callback(canvas,",
                "emscripten_set_keydown_callback(win,",
            ),
            live_test,
            lifecycle_test,
        ),
        (
            replace_once(
                system,
                "emscripten_set_keyup_callback(canvas,",
                "emscripten_set_keyup_callback(win,",
            ),
            live_test,
            lifecycle_test,
        ),
        (
            replace_once(
                system,
                "canvas, user_data, EMSCRIPTEN_EVENT_KEYDOWN, cb_key",
                "window, user_data, EMSCRIPTEN_EVENT_KEYDOWN, cb_key",
            ),
            live_test,
            lifecycle_test,
        ),
        (
            replace_once(
                system,
                "canvas, user_data, EMSCRIPTEN_EVENT_KEYUP, cb_key",
                "window, user_data, EMSCRIPTEN_EVENT_KEYUP, cb_key",
            ),
            live_test,
            lifecycle_test,
        ),
        (
            system,
            replace_once(
                live_test,
                'document.querySelector("#clear").focus();',
                'document.querySelector("#blender-canvas").focus();',
            ),
            lifecycle_test,
        ),
        (
            system,
            replace_once(
                live_test,
                'snapshot.activeId !== "clear"',
                'snapshot.activeId === "clear"',
            ),
            lifecycle_test,
        ),
        (
            system,
            live_test,
            replace_once(
                lifecycle_test,
                "this instanceof HTMLCanvasElement",
                "this === window",
            ),
        ),
        (
            system,
            live_test,
            replace_once(
                lifecycle_test,
                'document.querySelector("#blender-canvas").dispatchEvent(',
                "window.dispatchEvent(",
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
    parser.add_argument("lifecycle_test", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    inputs = (
        args.system_source.read_text(encoding="utf-8"),
        args.live_test.read_text(encoding="utf-8"),
        args.lifecycle_test.read_text(encoding="utf-8"),
    )
    if args.selfcheck:
        selfcheck(*inputs)
    else:
        validate(*inputs)
    print(
        "KEYBOARD_FOCUS_CONTRACT PASS target=canvas focused=deliver blurred=suppress "
        "queued=registration-epoch mutations=8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
