#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind DOM key sides to exact GHOST modifier state and aggregate reconciliation."""

from __future__ import annotations

import argparse
from pathlib import Path


GET_MARKER = "GHOST_TSuccess GHOST_SystemWeb::getModifierKeys("
PAIR_MARKER = "void reconcile_modifier_pair("
FLAGS_MARKER = "void GHOST_SystemWeb::noteModifierFlags("
KEY_MARKER = "void GHOST_SystemWeb::noteModifierKey("
ON_KEY_MARKER = "void on_key("
EXPORT_MARKER = 'extern "C" EMSCRIPTEN_KEEPALIVE int ghost_harness_modifier_state_exact()'


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


MAPPINGS = (
    ("GHOST_kKeyLeftShift", "GHOST_kModifierKeyLeftShift"),
    ("GHOST_kKeyRightShift", "GHOST_kModifierKeyRightShift"),
    ("GHOST_kKeyLeftControl", "GHOST_kModifierKeyLeftControl"),
    ("GHOST_kKeyRightControl", "GHOST_kModifierKeyRightControl"),
    ("GHOST_kKeyLeftAlt", "GHOST_kModifierKeyLeftAlt"),
    ("GHOST_kKeyRightAlt", "GHOST_kModifierKeyRightAlt"),
    ("GHOST_kKeyLeftOS", "GHOST_kModifierKeyLeftOS"),
    ("GHOST_kKeyRightOS", "GHOST_kModifierKeyRightOS"),
)

PAIRS = (
    ("Control", "ctrl"),
    ("Shift", "shift"),
    ("Alt", "alt"),
    ("OS", "meta"),
)


def validate(header: str, system: str, bridge: str, harness: str, live_test: str) -> None:
    for token in (
        "void noteModifierFlags(bool ctrl, bool shift, bool alt, bool meta);",
        "void noteModifierKey(GHOST_TKey key, bool down);",
        "GHOST_ModifierKeys modifiers_;",
    ):
        require_once(header, token, "side-aware header")
    for obsolete in ("mod_ctrl_", "mod_shift_", "mod_alt_", "mod_meta_"):
        if obsolete in header or obsolete in system:
            raise ValueError(f"legacy aggregate modifier storage remains: {obsolete}")

    get_state = compact(method(system, GET_MARKER))
    require_once(get_state, "keys = modifiers_;", "exact modifier query")

    pair = compact(method(system, PAIR_MARKER))
    for token in (
        "if (!held)",
        "keys.set(left, false);",
        "keys.set(right, false);",
        "if (!keys.get(left) && !keys.get(right))",
        "keys.set(left, true);",
    ):
        require_once(pair, token, "aggregate pair reconciliation")
    if not (
        pair.index("keys.set(left, false);")
        < pair.index("keys.set(right, false);")
        < pair.index("return;")
        < pair.index("if (!keys.get(left) && !keys.get(right))")
    ):
        raise ValueError("released aggregate pair is not cleared before fallback")

    flags = compact(method(system, FLAGS_MARKER))
    for family, value in PAIRS:
        require_once(
            flags,
            f"reconcile_modifier_pair(modifiers_, GHOST_kModifierKeyLeft{family}, "
            f"GHOST_kModifierKeyRight{family}, {value});",
            f"{family} aggregate reconciliation",
        )

    exact = compact(method(system, KEY_MARKER))
    for key, modifier in MAPPINGS:
        require_once(exact, f"case {key}:", "exact modifier key switch")
        require_once(exact, f"modifiers_.set({modifier}, down);", "exact modifier state")

    on_key = compact(method(bridge, ON_KEY_MARKER))
    for token in (
        "const bool down = (em_event_type == EMSCRIPTEN_EVENT_KEYDOWN);",
        "const GHOST_TKey key = ghost_web_key_from_code(e.code);",
        "sys.noteModifierKey(key, down);",
        "sys.noteModifierFlags(e.ctrlKey, e.shiftKey, e.altKey, e.metaKey);",
        "std::make_unique<GHOST_EventKey>(",
    ):
        require_once(on_key, token, "key event ordering")
    if not (
        on_key.index("sys.noteModifierKey(key, down);")
        < on_key.index("sys.noteModifierFlags(")
        < on_key.index("std::make_unique<GHOST_EventKey>(")
    ):
        raise ValueError("exact key state is not published before aggregate reconciliation/event")

    export = compact(method(harness, EXPORT_MARKER))
    for token in (
        "g_system->getModifierKeys(keys)",
        "modifier = int(GHOST_kModifierKeyLeftShift)",
        "modifier <= int(GHOST_kModifierKeyRightOS)",
        "keys.get(GHOST_TModifierKey(modifier))",
        "state |= 1 << modifier;",
    ):
        require_once(export, token, "exact-state harness export")

    for token in (
        'newCDPSession(page)',
        'client.send("Input.dispatchKeyEvent"',
        'client.send("Input.dispatchMouseEvent"',
        'right: "ShiftRight"',
        'right: "ControlRight"',
        'right: "AltRight"',
        'right: "MetaRight"',
        "family.leftBit | family.rightBit",
        "`${family.label} right up while left held`",
        'document.querySelector("#clear").focus()',
        '"focus loss clears exact right shift"',
        '"aggregate-only shift fallback"',
        "M4_MODIFIER_SIDE_LIVE PASS trusted=cdp",
    ):
        require_once(live_test, token, "trusted live side test")


def selfcheck(header: str, system: str, bridge: str, harness: str, live_test: str) -> None:
    validate(header, system, bridge, harness, live_test)
    mutations: list[tuple[str, str, str, str, str]] = []

    mutations.append((replace_once(header, "GHOST_ModifierKeys modifiers_;", "bool mod_shift_;"),
                      system, bridge, harness, live_test))
    mutations.append((header, mutate_method(system, GET_MARKER, "keys = modifiers_;", "keys.clear();"),
                      bridge, harness, live_test))
    mutations.append((header, mutate_method(system, PAIR_MARKER,
                                            "keys.set(right, false);", "keys.set(right, true);"),
                      bridge, harness, live_test))
    mutations.append((header, mutate_method(system, PAIR_MARKER,
                                            "!keys.get(left) && !keys.get(right)",
                                            "!keys.get(left) || !keys.get(right)"),
                      bridge, harness, live_test))
    mutations.append((header, mutate_method(system, PAIR_MARKER,
                                            "keys.set(left, true);", "keys.set(right, true);"),
                      bridge, harness, live_test))

    for key, modifier in MAPPINGS:
        opposite = modifier.replace("Left", "Right") if "Left" in modifier else modifier.replace(
            "Right", "Left")
        mutations.append((header, mutate_method(system, KEY_MARKER,
                                                f"modifiers_.set({modifier}, down);",
                                                f"modifiers_.set({opposite}, down);"),
                          bridge, harness, live_test))

    exact_then_flags = (
        "sys.noteModifierKey(key, down);\n"
        "  sys.noteModifierFlags(e.ctrlKey, e.shiftKey, e.altKey, e.metaKey);"
    )
    flags_then_exact = (
        "sys.noteModifierFlags(e.ctrlKey, e.shiftKey, e.altKey, e.metaKey);\n"
        "  sys.noteModifierKey(key, down);"
    )
    mutations.append((header, system, replace_once(bridge, exact_then_flags, flags_then_exact),
                      harness, live_test))
    mutations.append((header, system,
                      mutate_method(bridge, ON_KEY_MARKER, "sys.noteModifierKey(key, down);", ""),
                      harness, live_test))
    mutations.append((header, system, bridge,
                      mutate_method(harness, EXPORT_MARKER,
                                    "GHOST_kModifierKeyRightOS", "GHOST_kModifierKeyLeftOS"),
                      live_test))
    mutations.append((header, system, bridge, harness,
                      replace_once(live_test, 'newCDPSession(page)', 'newKeyboardSession(page)')))
    mutations.append((header, system, bridge, harness,
                      replace_once(live_test, "family.leftBit | family.rightBit",
                                   "family.leftBit")))
    mutations.append((header, system, bridge, harness,
                      replace_once(live_test, '"focus loss clears exact right shift"',
                                   '"focus loss retains exact right shift"')))

    for index, mutation in enumerate(mutations, start=1):
        try:
            validate(*mutation)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("system_header", type=Path)
    parser.add_argument("system_source", type=Path)
    parser.add_argument("event_bridge", type=Path)
    parser.add_argument("harness_source", type=Path)
    parser.add_argument("live_test", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    inputs = tuple(
        path.read_text(encoding="utf-8")
        for path in (
            args.system_header,
            args.system_source,
            args.event_bridge,
            args.harness_source,
            args.live_test,
        )
    )
    if args.selfcheck:
        selfcheck(*inputs)
    else:
        validate(*inputs)
    print(
        "M4_MODIFIER_SIDE_CONTRACT PASS families=4 sides=left,right,both "
        "aggregate=preserve,fallback focus=cleared mutations=19"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
