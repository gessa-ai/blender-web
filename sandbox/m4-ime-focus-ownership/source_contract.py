#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind the canvas and Blender IME textarea to one logical GHOST focus domain."""

from __future__ import annotations

import argparse
from pathlib import Path


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


def validate(header: str, source: str, live_test: str) -> None:
    for token in (
        "bool browserFocusIsOwned() const;",
        "bool transitionBrowserFocus(bool focused);",
        "bool browser_focus_active_ = false;",
    ):
        require_once(header, token, "focus-domain header")

    ownership = method(source, "bool GHOST_SystemWeb::browserFocusIsOwned() const")
    for token in (
        '!document.hasFocus()',
        "const active = document.activeElement;",
        "const canvas = document.querySelector(UTF8ToString($0));",
        "active === canvas",
        "const bridge = globalThis.__bwImeBridge;",
        'typeof bridge.snapshot !== "function"',
        "state.enabled === true && state.focused === true",
    ):
        require_once(ownership, token, "owned browser focus")

    transition = method(source, "bool GHOST_SystemWeb::transitionBrowserFocus(const bool focused)")
    for token in (
        "if (browser_focus_active_ == focused)",
        "browser_focus_active_ = focused;",
        "return true;",
    ):
        require_once(transition, token, "deduplicated focus transition")

    publish = method(source, "bool publish_browser_focus_transition(")
    require_once(publish, "system->transitionBrowserFocus(focused)", "focus publisher")
    require_once(publish, "ghost_web_bridge::on_focus(*system, focused);", "focus publisher")
    if publish.index("transitionBrowserFocus") > publish.index("ghost_web_bridge::on_focus"):
        raise ValueError("GHOST focus event precedes state-transition admission")

    canvas_focus = method(source, "bool cb_canvas_focus(")
    canvas_blur = method(source, "bool cb_canvas_blur(")
    window_focus = method(source, "bool cb_window_focus(")
    window_blur = method(source, "bool cb_window_blur(")
    for body, condition, state, label in (
        (canvas_focus, "!system->browserFocusIsOwned()", "true", "canvas focus"),
        (canvas_blur, "system->browserFocusIsOwned()", "false", "canvas blur"),
        (window_focus, "!system->browserFocusIsOwned()", "true", "window focus"),
        (window_blur, "system == nullptr", "false", "window blur"),
    ):
        require_once(body, "callback_system(ud)", label)
        require_once(body, condition, label)
        require_once(body, f"publish_browser_focus_transition(system, {state})", label)
    if "browserFocusIsOwned" in window_blur:
        raise ValueError("browser-window blur is incorrectly suppressed inside the IME domain")

    registration = method(source, "bool GHOST_SystemWeb::registerCanvasCallbacks()")
    for token in (
        "ghost_web::sequential_registration_transaction<kWebCallbackCount>(",
        "emscripten_set_focus_callback(canvas, user_data, false, cb_canvas_focus)",
        "emscripten_set_blur_callback(canvas, user_data, false, cb_canvas_blur)",
        "emscripten_set_focus_callback(win, user_data, false, cb_window_focus)",
        "emscripten_set_blur_callback(win, user_data, false, cb_window_blur)",
        "browser_focus_active_ = browserFocusIsOwned();",
    ):
        require_once(registration, token, "focus listener transaction")

    create_window = method(source, "GHOST_IWindow *GHOST_SystemWeb::createWindow(")
    for token in (
        "wm->addWindow(valid_window);",
        "wm->setActiveWindow(valid_window);",
        "if (browser_focus_active_)",
        "ghost_web_bridge::on_focus(*this, true);",
    ):
        require_once(create_window, token, "initial focus publication")
    if create_window.index("wm->setActiveWindow(valid_window);") > create_window.index(
            "ghost_web_bridge::on_focus(*this, true);"):
        raise ValueError("initial focus is published before window-manager admission")

    removal = method(source, "bool remove_html5_callback_prefix(const char *canvas,")
    compact = " ".join(removal.split()).replace("( ", "(")
    for token in (
        "case 16:",
        "remove_html5_callback(canvas, user_data, EMSCRIPTEN_EVENT_FOCUS, cb_canvas_focus)",
        "remove_html5_callback(canvas, user_data, EMSCRIPTEN_EVENT_BLUR, cb_canvas_blur)",
        "remove_html5_callback(window, user_data, EMSCRIPTEN_EVENT_FOCUS, cb_window_focus)",
        "remove_html5_callback(window, user_data, EMSCRIPTEN_EVENT_BLUR, cb_window_blur)",
    ):
        require_once(compact, token, "focus listener removal")

    unregistration = method(source, "void GHOST_SystemWeb::unregisterCanvasCallbacks()")
    require_once(unregistration, "browser_focus_active_ = false;", "focus retirement")
    require_once(
        unregistration,
        "remove_html5_callback_prefix(canvas, win, callback_user_data_, kWebCallbackCount)",
        "focus retirement",
    )

    for token in (
        "begun.log.includes(\"WindowDeactivate\")",
        "ended.log.includes(\"WindowDeactivate\")",
        "external focus-domain contract failed",
        'window.dispatchEvent(new FocusEvent("blur"))',
        'window.dispatchEvent(new FocusEvent("focus"))',
        "window focus-domain contract failed",
        "focus=domain-internal,external,window",
    ):
        require_once(live_test, token, "real worker focus-domain test")


def selfcheck(header: str, source: str, live_test: str) -> None:
    validate(header, source, live_test)
    mutations = (
        (replace_once(header, "bool browserFocusIsOwned() const;", ""), source, live_test),
        (replace_once(header, "bool transitionBrowserFocus(bool focused);", ""), source, live_test),
        (replace_once(header, "bool browser_focus_active_ = false;", ""), source, live_test),
        (header, replace_once(source, "!document.hasFocus()", "false"), live_test),
        (header, replace_once(source, "active === canvas", "false"), live_test),
        (header, replace_once(source,
                              "state.enabled === true && state.focused === true", "false"), live_test),
        (header, replace_once(source,
                              "if (browser_focus_active_ == focused)", "if (false)"), live_test),
        (header, mutate_method(source, "bool cb_canvas_focus(",
                               "!system->browserFocusIsOwned()", "false"), live_test),
        (header, mutate_method(source, "bool cb_canvas_blur(",
                               "system->browserFocusIsOwned()", "false"), live_test),
        (header, replace_once(source,
                              "ghost_web::sequential_registration_transaction<kWebCallbackCount>(",
                              "ghost_web::sequential_registration_transaction<13>("), live_test),
        (header, replace_once(source,
                              "emscripten_set_focus_callback(win, user_data, false, cb_window_focus)",
                              "EMSCRIPTEN_RESULT_SUCCESS"), live_test),
        (header, replace_once(source,
                              "emscripten_set_blur_callback(win, user_data, false, cb_window_blur)",
                              "EMSCRIPTEN_RESULT_SUCCESS"), live_test),
        (header, replace_once(source,
                              "browser_focus_active_ = browserFocusIsOwned();", ""), live_test),
        (header, mutate_method(source, "GHOST_IWindow *GHOST_SystemWeb::createWindow(",
                              "ghost_web_bridge::on_focus(*this, true);", ""), live_test),
        (header, replace_once(source,
                              "remove_html5_callback_prefix(canvas, win, callback_user_data_, kWebCallbackCount)",
                              "remove_html5_callback_prefix(canvas, win, callback_user_data_, 13)"),
         live_test),
        (header, source, replace_once(live_test,
                                      'window.dispatchEvent(new FocusEvent("blur"))', "")),
        (header, source, replace_once(live_test,
                                      "begun.log.includes(\"WindowDeactivate\")", "false")),
        (header, source, replace_once(live_test,
                                      "focus=domain-internal,external,window", "focus=canvas")),
    )
    for index, (mutated_header, mutated_source, mutated_test) in enumerate(mutations, start=1):
        try:
            validate(mutated_header, mutated_source, mutated_test)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("system_header", type=Path)
    parser.add_argument("system_source", type=Path)
    parser.add_argument("live_test", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    header = args.system_header.read_text(encoding="utf-8")
    source = args.system_source.read_text(encoding="utf-8")
    live_test = args.live_test.read_text(encoding="utf-8")
    selfcheck(header, source, live_test) if args.selfcheck else validate(header, source, live_test)
    print(
        "IME_FOCUS_OWNERSHIP_CONTRACT PASS domain=canvas,textarea "
        "external=control,window transitions=deduplicated+initial listeners=16 mutations=18"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
