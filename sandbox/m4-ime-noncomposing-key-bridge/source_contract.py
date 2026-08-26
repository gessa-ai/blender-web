#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind ordinary IME-textarea keys to GHOST without duplicating composition."""

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


def validate(system: str, live_test: str, product_test: str) -> None:
    for token in (
        'constexpr const char *kImeInputSelector = "#bw-ime-input";',
        "constexpr size_t kWebCallbackCount = 16;",
        "constexpr size_t kWebCallbackCount = 14;",
    ):
        require_once(system, token, "profile callback count")

    registration = compact(method(system, REGISTER_MARKER))
    removal = compact(method(system, REMOVE_MARKER))
    require_once(
        registration,
        "ghost_web::sequential_registration_transaction<kWebCallbackCount>(",
        "callback transaction",
    )
    for event in ("keydown", "keyup"):
        require_once(
            registration,
            f"emscripten_set_{event}_callback(kImeInputSelector, user_data, false, cb_key)",
            "IME raw-key registration",
        )
    for event in ("KEYDOWN", "KEYUP"):
        require_once(
            removal,
            f"remove_html5_callback(kImeInputSelector, user_data, EMSCRIPTEN_EVENT_{event}, cb_key)",
            "IME raw-key retirement",
        )

    bridge = method(system, "bool GHOST_SystemWeb::registerCanvasCallbacks()")
    for token in (
        "var rawKeyAdmitted = 0;",
        "var rawKeySuppressed = 0;",
        "var admitRawKey = function (event)",
        "var ownsFocus = enabled && document.activeElement === input;",
        "composing || event.isComposing || event.key === \"Process\" ||",
        "event.keyCode === 229;",
        "event.stopImmediatePropagation();",
        'input.addEventListener("keydown", admitRawKey);',
        'input.addEventListener("keyup", admitRawKey);',
        "rawKeyAdmitted: rawKeyAdmitted,",
        "rawKeySuppressed: rawKeySuppressed,",
    ):
        require_once(bridge, token, "composition/raw-key admission")
    if bridge.index('input.addEventListener("keydown", admitRawKey);') > bridge.index(
            'input.addEventListener("compositionstart"'):
        raise ValueError("composition admission listener is installed after composition listeners")
    if bridge.index('input.addEventListener("keyup", admitRawKey);') > bridge.index(
            "sequential_registration_transaction<kWebCallbackCount>"):
        raise ValueError("IME admission listener is installed after Emscripten raw callbacks")

    for token in (
        "ordinary.domKeys.some((event) => !event.trusted || event.composing)",
        '"a", "ArrowLeft", "Backspace", "Enter", "Escape"',
        '"Control", "c", "Control", "x", "Control", "v"',
        "ordinary.ghostKeys.length !== 22",
        "composition.lines.some((line) => line.includes(\"GHOST Key\"))",
        "external.active !== \"clear\" || external.keys.length !== 0",
        "IME_NONCOMPOSING_KEYS_LIVE PASS",
    ):
        require_once(live_test, token, "real-worker keyboard contract")

    for token in (
        'await page.keyboard.press("End");',
        'await page.keyboard.press("Backspace");',
        'await page.keyboard.press("Control+c");',
        'await page.keyboard.press("Control+x");',
        'await page.keyboard.press("Control+v");',
        "bpy.context.active_object.name",
        "PRODUCT_IME_NONCOMPOSING_LIVE PASS",
    ):
        require_once(product_test, token, "Blender text-state contract")
    if product_test.count('await page.keyboard.press("Control+a");') != 3:
        raise ValueError("Blender text-state contract requires edit, clipboard, and cancel Select All")
    if product_test.count('await page.keyboard.press("Escape");') != 2:
        raise ValueError("Blender text-state contract requires splash and rename Escape paths")


def selfcheck(system: str, live_test: str, product_test: str) -> None:
    validate(system, live_test, product_test)
    mutations = (
        (replace_once(system, "constexpr size_t kWebCallbackCount = 16;",
                      "constexpr size_t kWebCallbackCount = 15;"), live_test, product_test),
        (replace_once(system, "emscripten_set_keydown_callback(\n                kImeInputSelector,",
                      "emscripten_set_keydown_callback(\n                canvas,"), live_test, product_test),
        (replace_once(system, "emscripten_set_keyup_callback(\n                kImeInputSelector,",
                      "emscripten_set_keyup_callback(\n                canvas,"), live_test, product_test),
        (replace_once(system, "kImeInputSelector, user_data, EMSCRIPTEN_EVENT_KEYDOWN, cb_key",
                      "canvas, user_data, EMSCRIPTEN_EVENT_KEYDOWN, cb_key"), live_test, product_test),
        (replace_once(system, "kImeInputSelector, user_data, EMSCRIPTEN_EVENT_KEYUP, cb_key",
                      "canvas, user_data, EMSCRIPTEN_EVENT_KEYUP, cb_key"), live_test, product_test),
        (replace_once(system, "enabled && document.activeElement === input", "enabled"),
         live_test, product_test),
        (replace_once(system, "composing || event.isComposing", "false"), live_test, product_test),
        (replace_once(system, 'event.key === "Process"', "false"), live_test, product_test),
        (replace_once(system, "event.keyCode === 229", "false"), live_test, product_test),
        (replace_once(system, "event.stopImmediatePropagation();", ""), live_test, product_test),
        (system, replace_once(live_test,
                              "ordinary.domKeys.some((event) => !event.trusted || event.composing)",
                              "false"), product_test),
        (system, replace_once(live_test, "ordinary.ghostKeys.length !== 22", "false"), product_test),
        (system, replace_once(live_test,
                              "composition.lines.some((line) => line.includes(\"GHOST Key\"))",
                              "false"), product_test),
        (system, live_test, replace_once(product_test,
                                         'await page.keyboard.press("Control+v");', "")),
        (system, live_test, product_test.replace(
            'await page.keyboard.press("Control+a");', "", 1)),
        (system, live_test, product_test.replace(
            'await page.keyboard.press("Escape");', "", 1)),
        (system, live_test, replace_once(product_test,
                                         "bpy.context.active_object.name", "object.name")),
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
    parser.add_argument("product_test", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    inputs = (
        args.system_source.read_text(encoding="utf-8"),
        args.live_test.read_text(encoding="utf-8"),
        args.product_test.read_text(encoding="utf-8"),
    )
    selfcheck(*inputs) if args.selfcheck else validate(*inputs)
    print(
        "IME_NONCOMPOSING_KEY_CONTRACT PASS targets=canvas,textarea callbacks=16 "
        "trusted=ascii,navigation,control,clipboard composition=raw-suppressed mutations=17"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
