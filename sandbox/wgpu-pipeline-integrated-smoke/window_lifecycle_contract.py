#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind GHOST-web active-window disposal to callback and pointer retirement."""

from __future__ import annotations

import argparse
from pathlib import Path


DISPOSE_MARKER = "GHOST_TSuccess GHOST_SystemWeb::disposeWindow(GHOST_IWindow *window)"
REGISTER_MARKER = "void GHOST_SystemWeb::registerCanvasCallbacks()"
UNREGISTER_MARKER = "void GHOST_SystemWeb::unregisterCanvasCallbacks()"
DESTRUCTOR_MARKER = "GHOST_SystemWeb::~GHOST_SystemWeb()"
CREATE_MARKER = "GHOST_IWindow *GHOST_SystemWeb::createWindow(const char *title,"


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


def require_once(body: str, token: str, label: str) -> None:
    if body.count(token) != 1:
        raise ValueError(f"{label} requires exactly one {token!r}")


def validate(header: str, source: str) -> None:
    for token in (
        "~GHOST_SystemWeb() override;",
        "GHOST_TSuccess disposeWindow(GHOST_IWindow *window) override;",
        "void unregisterCanvasCallbacks();",
        "bool callbacks_registered_ = false;",
    ):
        require_once(header, token, "header")

    require_once(
        source,
        "std::atomic<GHOST_SystemWeb *> g_callback_system{nullptr};",
        "callback owner",
    )
    require_once(
        source,
        "g_callback_system.load(std::memory_order_acquire) == candidate",
        "callback owner",
    )
    if source.count("callback_system(ud)") != 8 or source.count("if (system == nullptr)") != 7:
        raise ValueError("every HTML5 callback must validate its live system owner")

    destructor = method(source, DESTRUCTOR_MARKER)
    require_once(destructor, "unregisterCanvasCallbacks();", "destructor")
    require_once(destructor, "window_ = nullptr;", "destructor")
    if destructor.index("unregisterCanvasCallbacks();") > destructor.index("window_ = nullptr;"):
        raise ValueError("destructor detaches the system before unregistering callbacks")

    registration = method(source, REGISTER_MARKER)
    require_once(registration, "if (callbacks_registered_)", "registration")
    require_once(
        registration,
        "g_callback_system.store(this, std::memory_order_release);",
        "registration",
    )
    require_once(registration, "callbacks_registered_ = true;", "registration")
    if registration.index("g_callback_system.store") > registration.index(
        "emscripten_set_mousemove_callback"
    ):
        raise ValueError("callback owner publishes after listener registration")

    unregistration = method(source, UNREGISTER_MARKER)
    require_once(unregistration, "if (!callbacks_registered_)", "unregistration")
    require_once(
        unregistration,
        "g_callback_system.compare_exchange_strong(",
        "unregistration",
    )
    require_once(unregistration, "callbacks_registered_ = false;", "unregistration")
    removals = (
        ("canvas", "EMSCRIPTEN_EVENT_MOUSEMOVE", "cb_mousemove"),
        ("canvas", "EMSCRIPTEN_EVENT_MOUSEDOWN", "cb_mousebtn"),
        ("canvas", "EMSCRIPTEN_EVENT_MOUSEUP", "cb_mousebtn"),
        ("canvas", "EMSCRIPTEN_EVENT_WHEEL", "cb_wheel"),
        ("canvas", "EMSCRIPTEN_EVENT_CONTEXTMENU", "cb_contextmenu"),
        ("canvas", "EMSCRIPTEN_EVENT_FOCUS", "cb_focus"),
        ("canvas", "EMSCRIPTEN_EVENT_BLUR", "cb_blur"),
        ("win", "EMSCRIPTEN_EVENT_KEYDOWN", "cb_key"),
        ("win", "EMSCRIPTEN_EVENT_KEYUP", "cb_key"),
        ("win", "EMSCRIPTEN_EVENT_RESIZE", "cb_resize"),
    )
    for target, event, callback in removals:
        token = f"remove_html5_callback({target}, this, {event}, {callback})"
        require_once(unregistration, token, "unregistration")
    if unregistration.index("g_callback_system.compare_exchange_strong(") > unregistration.index(
        "remove_html5_callback("
    ):
        raise ValueError("callback owner retires after listener removal")

    disposal = method(source, DISPOSE_MARKER)
    for token in (
        "if (window != window_ || !validWindow(window))",
        "active_window->endIME();",
        "ghost_web_bridge::poll_ime(*this);",
        "window_ = nullptr;",
        "unregisterCanvasCallbacks();",
        "buttons_ = GHOST_Buttons();",
        "noteModifierFlags(false, false, false, false);",
        "window_ = active_window;",
    ):
        require_once(disposal, token, "disposal")
    require_once(disposal, "\n    registerCanvasCallbacks();", "disposal")
    if disposal.count("GHOST_System::disposeWindow(window)") != 2:
        raise ValueError("disposal requires guarded and active base-disposal calls")
    detach = disposal.index("window_ = nullptr;")
    unregister = disposal.index("unregisterCanvasCallbacks();")
    base_dispose = disposal.rindex("GHOST_System::disposeWindow(window)")
    if not detach < unregister < base_dispose:
        raise ValueError("active pointer/callback retirement does not precede base deletion")

    creation = method(source, CREATE_MARKER)
    require_once(creation, "redraw_heartbeat_ = 0;", "creation")
    if creation.index("window_ = valid_window;") > creation.index("registerCanvasCallbacks();"):
        raise ValueError("replacement callbacks register before active-window publication")


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return text.replace(old, new, 1)


def mutate_method(source: str, marker: str, old: str, new: str) -> str:
    original = method(source, marker)
    changed = replace_once(original, old, new)
    return source.replace(original, changed, 1)


def selfcheck(header: str, source: str) -> None:
    validate(header, source)
    mutations = (
        (replace_once(header, "~GHOST_SystemWeb() override;", "~GHOST_SystemWeb() override = default;"), source),
        (replace_once(header, "GHOST_TSuccess disposeWindow(GHOST_IWindow *window) override;", ""), source),
        (replace_once(header, "bool callbacks_registered_ = false;", "bool callbacks_registered_ = true;"), source),
        (header, replace_once(source, "std::atomic<GHOST_SystemWeb *> g_callback_system{nullptr};", "")),
        (header, replace_once(source, "if (callback_system(ud) == nullptr)", "if (false)")),
        (header, mutate_method(source, REGISTER_MARKER, "if (callbacks_registered_)", "if (false)")),
        (header, mutate_method(source, REGISTER_MARKER, "g_callback_system.store(this, std::memory_order_release);", "")),
        (header, mutate_method(source, UNREGISTER_MARKER, "EMSCRIPTEN_EVENT_MOUSEUP", "EMSCRIPTEN_EVENT_MOUSEDOWN")),
        (header, mutate_method(source, UNREGISTER_MARKER, "EMSCRIPTEN_EVENT_KEYUP", "EMSCRIPTEN_EVENT_KEYDOWN")),
        (header, mutate_method(source, UNREGISTER_MARKER, "g_callback_system.compare_exchange_strong(", "g_callback_system.store(")),
        (header, mutate_method(source, DISPOSE_MARKER, "if (window != window_ || !validWindow(window))", "if (window != window_)")),
        (header, mutate_method(source, DISPOSE_MARKER, "active_window->endIME();", "")),
        (header, mutate_method(source, DISPOSE_MARKER, "ghost_web_bridge::poll_ime(*this);", "")),
        (header, mutate_method(source, DISPOSE_MARKER, "window_ = nullptr;", "window_ = active_window;")),
        (header, mutate_method(source, DISPOSE_MARKER, "buttons_ = GHOST_Buttons();", "")),
        (header, mutate_method(source, DISPOSE_MARKER, "noteModifierFlags(false, false, false, false);", "")),
        (header, mutate_method(source, CREATE_MARKER, "redraw_heartbeat_ = 0;", "redraw_heartbeat_ = 180;")),
    )
    for index, (mutated_header, mutated_source) in enumerate(mutations, start=1):
        try:
            validate(mutated_header, mutated_source)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("header", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    header = args.header.read_text(encoding="utf-8")
    source = args.source.read_text(encoding="utf-8")
    if args.selfcheck:
        selfcheck(header, source)
    else:
        validate(header, source)
    print(
        "WINDOW_LIFECYCLE_CONTRACT PASS active=detach-before-delete callbacks=10 "
        "replacement=rebound ime=retired queued=owner-gated mutations=17"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
