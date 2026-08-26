#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind browser focus loss to fail-closed GHOST input-state retirement."""

from __future__ import annotations

import argparse
from pathlib import Path


FOCUS_MARKER = "void on_focus(GHOST_SystemWeb &sys, bool focused)"


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


def mutate_method(source: str, old: str, new: str) -> str:
    original = method(source, FOCUS_MARKER)
    changed = original.replace(old, new, 1)
    if changed == original:
        raise ValueError(f"mutation input is absent: {old!r}")
    return source.replace(original, changed, 1)


def require_once(body: str, token: str) -> None:
    if body.count(token) != 1:
        raise ValueError(f"focus retirement requires exactly one {token!r}")


def validate(source: str) -> None:
    focus = method(source, FOCUS_MARKER)
    required = (
        "if (GHOST_WindowManager *window_manager = sys.getWindowManager())",
        "if (focused)",
        "window_manager->setActiveWindow(win);",
        "window_manager->setWindowInactive(win);",
        "if (!focused)",
        "sys.getButtons(held_buttons) == GHOST_kSuccess",
        "const bool was_held = have_buttons && held_buttons.get(button);",
        "sys.noteButton(button, false);",
        "if (was_held && win != nullptr)",
        "GHOST_kEventButtonUp",
        "GHOST_TABLET_DATA_NONE",
        "sys.noteModifierFlags(false, false, false, false);",
        "focused ? GHOST_kEventWindowActivate : GHOST_kEventWindowDeactivate",
    )
    for token in required:
        require_once(focus, token)

    for button in (
        "GHOST_kButtonMaskLeft",
        "GHOST_kButtonMaskMiddle",
        "GHOST_kButtonMaskRight",
        "GHOST_kButtonMaskButton4",
        "GHOST_kButtonMaskButton5",
        "GHOST_kButtonMaskButton6",
        "GHOST_kButtonMaskButton7",
    ):
        require_once(focus, button)

    modifier_clear = focus.index("sys.noteModifierFlags(false, false, false, false);")
    button_release = focus.index("GHOST_kEventButtonUp")
    manager_activate = focus.index("window_manager->setActiveWindow(win);")
    manager_deactivate = focus.index("window_manager->setWindowInactive(win);")
    deactivation = focus.index(
        "focused ? GHOST_kEventWindowActivate : GHOST_kEventWindowDeactivate"
    )
    if (modifier_clear > deactivation or button_release > deactivation or
            manager_activate > deactivation or manager_deactivate > deactivation):
        raise ValueError("focus state is reconciled after the GHOST focus event")


def selfcheck(source: str) -> None:
    validate(source)
    mutations = (
        mutate_method(
            source,
            "window_manager->setActiveWindow(win);",
            "window_manager->setWindowInactive(win);",
        ),
        mutate_method(
            source,
            "window_manager->setWindowInactive(win);",
            "window_manager->setActiveWindow(win);",
        ),
        mutate_method(source, "if (focused)", "if (!focused)"),
        mutate_method(source, "if (!focused)", "if (focused)"),
        mutate_method(
            source,
            "sys.getButtons(held_buttons) == GHOST_kSuccess",
            "false",
        ),
        mutate_method(
            source,
            "const bool was_held = have_buttons && held_buttons.get(button);",
            "const bool was_held = false;",
        ),
        mutate_method(
            source,
            "sys.noteButton(button, false);",
            "sys.noteButton(button, true);",
        ),
        mutate_method(source, "GHOST_kEventButtonUp", "GHOST_kEventButtonDown"),
        mutate_method(
            source,
            "if (was_held && win != nullptr)",
            "if (was_held)",
        ),
        mutate_method(
            source,
            "sys.noteModifierFlags(false, false, false, false);",
            "sys.noteModifierFlags(true, false, false, false);",
        ),
        mutate_method(source, "GHOST_kButtonMaskLeft,", "GHOST_kButtonMaskMiddle,"),
        mutate_method(source, "GHOST_kButtonMaskButton7,", "GHOST_kButtonMaskButton6,"),
        mutate_method(
            source,
            "focused ? GHOST_kEventWindowActivate : GHOST_kEventWindowDeactivate",
            "GHOST_kEventWindowActivate",
        ),
    )
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate(mutation)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bridge_source", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    source = args.bridge_source.read_text(encoding="utf-8")
    if args.selfcheck:
        selfcheck(source)
    else:
        validate(source)
    print(
        "FOCUS_STATE_CONTRACT PASS manager=active-inactive modifiers=cleared "
        "buttons=release-before-deactivate coverage=7 mutations=13"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
