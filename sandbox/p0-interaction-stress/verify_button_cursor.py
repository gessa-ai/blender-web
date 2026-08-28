#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Keep worker-proxied button events from rolling the GHOST cursor backward."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "platform_web/ghost/GHOST_EventBridgeWeb.cc"
MOVE = "void on_mouse_move(GHOST_SystemWeb &sys, const EmscriptenMouseEvent &e)"
BUTTON = (
    "void on_mouse_button(GHOST_SystemWeb &sys, int em_event_type, "
    "const EmscriptenMouseEvent &e)"
)


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


def validate(source: str) -> None:
    move = method(source, MOVE)
    button = method(source, BUTTON)
    if move.count("sys.noteCursor(x, y);") != 1:
        raise ValueError("mouse-move no longer owns exactly one cursor update")
    if move.index("sys.noteCursor(x, y);") > move.index("GHOST_EventCursor"):
        raise ValueError("mouse-move publishes the cursor before caching it")
    if "noteCursor(" in button:
        raise ValueError("button event still overwrites the ordered mouse-move cursor")
    for marker in (
        "sys.noteModifierFlags(",
        "button_from_dom(e.button)",
        "sys.noteButton(button, down);",
        "std::make_unique<GHOST_EventButton>(",
    ):
        if button.count(marker) != 1:
            raise ValueError(f"button bridge lost {marker}")


def self_check(source: str) -> None:
    validate(source)
    move = method(source, MOVE)
    button = method(source, BUTTON)
    mutations = (
        source.replace(
            button,
            button.replace(
                "sys.noteModifierFlags(e.ctrlKey, e.shiftKey, e.altKey, e.metaKey);",
                "sys.noteModifierFlags(e.ctrlKey, e.shiftKey, e.altKey, e.metaKey);\n"
                "  sys.noteCursor(e.targetX, e.targetY);",
                1,
            ),
            1,
        ),
        source.replace(move, move.replace("sys.noteCursor(x, y);", "", 1), 1),
        source.replace(button, button.replace("sys.noteButton(button, down);", "", 1), 1),
    )
    rejected = 0
    for mutation in mutations:
        try:
            validate(mutation)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0J_BUTTON_CURSOR_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    source = BRIDGE.read_text(encoding="utf-8")
    if args.self_check:
        self_check(source)
    else:
        validate(source)
        print("P0J_BUTTON_CURSOR_SOURCE_PASS owner=mouse-move button=non-overwriting")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"P0J_BUTTON_CURSOR_SOURCE_FAIL {error}")
        raise SystemExit(1)
