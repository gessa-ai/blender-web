#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind window-level drag motion/release to an existing canvas-owned press."""

from __future__ import annotations

import argparse
from pathlib import Path


MOVE_CALLBACK_MARKER = "bool cb_mousemove(int /*t*/, const EmscriptenMouseEvent *e, void *ud)"
BUTTON_CALLBACK_MARKER = "bool cb_mousebtn(int t, const EmscriptenMouseEvent *e, void *ud)"
RESIZE_CALLBACK_MARKER = "bool cb_resize(int /*t*/, const EmscriptenUiEvent *e, void *ud)"
REGISTER_MARKER = "bool GHOST_SystemWeb::registerCanvasCallbacks()"
REMOVE_MARKER = "bool remove_html5_callback_prefix(const char *canvas,"
REFRESH_MARKER = "bool GHOST_SystemWeb::refreshCanvasClientRect()"
COORDINATES_MARKER = "bool GHOST_SystemWeb::windowToCanvasCoordinates("


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
    move_callback = compact(method(system, MOVE_CALLBACK_MARKER))
    button_callback = compact(method(system, BUTTON_CALLBACK_MARKER))
    resize_callback = compact(method(system, RESIZE_CALLBACK_MARKER))
    registration = compact(method(system, REGISTER_MARKER))
    removal = compact(method(system, REMOVE_MARKER))
    refresh = compact(method(system, REFRESH_MARKER))
    coordinates = compact(method(system, COORDINATES_MARKER))

    require_once(
        registration,
        "emscripten_set_mousemove_callback(win, user_data, true, cb_mousemove)",
        "window motion capture registration",
    )
    if "emscripten_set_mousemove_callback(canvas," in registration:
        raise ValueError("mouse-move remains scoped to the canvas")
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
    require_once(
        removal,
        "remove_html5_callback(window, user_data, EMSCRIPTEN_EVENT_MOUSEMOVE, cb_mousemove)",
        "matching window motion removal",
    )

    for token in (
        "EmscriptenMouseEvent event = *e;",
        "if (t == EMSCRIPTEN_EVENT_MOUSEUP)",
        "ghost_web_bridge::button_from_dom(e->button)",
        "system->getButtonState(button, held) != GHOST_kSuccess || !held",
        "system->windowToCanvasCoordinates(e->clientX, e->clientY, event.targetX, event.targetY);",
        "ghost_web_bridge::on_mouse_button(*system, t, event);",
    ):
        require_once(button_callback, token, "owned-release callback")
    if button_callback.index("!held") > button_callback.index(
            "ghost_web_bridge::on_mouse_button(*system, t, event);"):
        raise ValueError("unowned release filtering occurs after GHOST delivery")

    for token in (
        "GHOST_WindowWeb *window = system->activeWindow();",
        "EmscriptenMouseEvent event = *e;",
        "const bool inside_canvas = system->windowToCanvasCoordinates(e->clientX, e->clientY, event.targetX, event.targetY);",
        "const bool have_buttons = system->getButtons(buttons) == GHOST_kSuccess;",
        "buttons.get(GHOST_kButtonMaskLeft)",
        "buttons.get(GHOST_kButtonMaskMiddle)",
        "buttons.get(GHOST_kButtonMaskRight)",
        "buttons.get(GHOST_kButtonMaskButton4)",
        "buttons.get(GHOST_kButtonMaskButton5)",
        "buttons.get(GHOST_kButtonMaskButton6)",
        "buttons.get(GHOST_kButtonMaskButton7)",
        "if (!inside_canvas && !owns_drag && !window->isPointerLockActive())",
        "ghost_web_bridge::on_mouse_move(*system, event);",
    ):
        require_once(move_callback, token, "owned-motion callback")
    if move_callback.index("windowToCanvasCoordinates") > move_callback.index(
            "if (!inside_canvas && !owns_drag"):
        raise ValueError("owned motion is filtered before canvas translation")
    if move_callback.index("if (!inside_canvas && !owns_drag") > move_callback.index(
            "ghost_web_bridge::on_mouse_move(*system, event);"):
        raise ValueError("unowned motion filtering occurs after GHOST delivery")

    for token in (
        "std::array<int32_t, 4> rect = {};",
        "const bounds = canvas.getBoundingClientRect();",
        "HEAP32[($1 >> 2) + 0] = bounds.left | 0;",
        "HEAP32[($1 >> 2) + 1] = bounds.top | 0;",
        "HEAP32[($1 >> 2) + 2] = Math.ceil(bounds.width);",
        "HEAP32[($1 >> 2) + 3] = Math.ceil(bounds.height);",
        "if (rect[2] <= 0 || rect[3] <= 0)",
        "canvas_client_left_ = rect[0];",
        "canvas_client_top_ = rect[1];",
        "canvas_client_width_ = rect[2];",
        "canvas_client_height_ = rect[3];",
    ):
        require_once(refresh, token, "canvas rectangle refresh")
    if refresh.count("document.querySelector(UTF8ToString($0))") != 1:
        raise ValueError("canvas rectangle refresh requires one coherent DOM snapshot")
    if refresh.index("if (rect[2] <= 0 || rect[3] <= 0)") > refresh.index(
            "canvas_client_left_ = rect[0];"):
        raise ValueError("partial canvas rectangle publishes before validation")

    for token in (
        "canvas_x = client_x - canvas_client_left_;",
        "canvas_y = client_y - canvas_client_top_;",
        "canvas_client_width_ > 0 && canvas_client_height_ > 0",
        "canvas_x >= 0 && canvas_y >= 0",
        "canvas_x < canvas_client_width_ && canvas_y < canvas_client_height_",
    ):
        require_once(coordinates, token, "canvas coordinate translation")
    require_once(registration, "if (!refreshCanvasClientRect())", "registration rectangle refresh")
    require_once(
        resize_callback,
        "system->refreshCanvasClientRect();",
        "resize rectangle refresh",
    )

    for token in (
        "box.x + box.width - 12",
        "await page.mouse.down({button: \"left\"});",
        "box.x + box.width + 80",
        "const dragPositions = [...dragLog.matchAll(/CursorMove\\s+x=(-?\\d+) y=(-?\\d+)/g)]",
        "dragPositions.some((position) => position.x > box.width)",
        "await page.mouse.up({button: \"left\"});",
        "_ghost_harness_input_state()) === 0",
        'owned.activeId !== "blender-canvas"',
        '!owned.log.includes("ButtonUp")',
        'window.dispatchEvent(motion);',
        'window.dispatchEvent(release);',
        "unrelatedPrevented || releasesAfter !== releasesBefore || movesAfter !== movesBefore",
        "motion=outside-delivered release=outside-delivered ",
        "unowned=suppressed focus=canvas worker=proxy-pthread",
    ):
        require_once(live_test, token, "live ownership test")

    require_once(
        lifecycle_contract,
        '("window", "EMSCRIPTEN_EVENT_MOUSEMOVE", "cb_mousemove")',
        "integrated motion lifecycle target",
    )
    if '("canvas", "EMSCRIPTEN_EVENT_MOUSEMOVE", "cb_mousemove")' in lifecycle_contract:
        raise ValueError("integrated lifecycle contract still expects canvas mouse-move")
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
                "emscripten_set_mousemove_callback(win, user_data, true, cb_mousemove)",
                "emscripten_set_mousemove_callback(canvas, user_data, true, cb_mousemove)",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                REGISTER_MARKER,
                "emscripten_set_mousemove_callback(win, user_data, true, cb_mousemove)",
                "emscripten_set_mousemove_callback(win, user_data, false, cb_mousemove)",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                REMOVE_MARKER,
                "window, user_data, EMSCRIPTEN_EVENT_MOUSEMOVE, cb_mousemove",
                "canvas, user_data, EMSCRIPTEN_EVENT_MOUSEMOVE, cb_mousemove",
            ),
            live_test,
            lifecycle_contract,
        ),
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
                BUTTON_CALLBACK_MARKER,
                "system->getButtonState(button, held) != GHOST_kSuccess || !held",
                "system->getButtonState(button, held) != GHOST_kSuccess",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                BUTTON_CALLBACK_MARKER,
                "if (t == EMSCRIPTEN_EVENT_MOUSEUP)",
                "if (t == EMSCRIPTEN_EVENT_MOUSEDOWN)",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                BUTTON_CALLBACK_MARKER,
                "e->clientX, e->clientY, event.targetX, event.targetY",
                "e->targetX, e->targetY, event.targetX, event.targetY",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                BUTTON_CALLBACK_MARKER,
                "ghost_web_bridge::on_mouse_button(*system, t, event);",
                "ghost_web_bridge::on_mouse_button(*system, t, *e);",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                MOVE_CALLBACK_MARKER,
                "if (!inside_canvas && !owns_drag && !window->isPointerLockActive())",
                "if (!inside_canvas)",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                MOVE_CALLBACK_MARKER,
                "ghost_web_bridge::on_mouse_move(*system, event);",
                "ghost_web_bridge::on_mouse_move(*system, *e);",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                COORDINATES_MARKER,
                "canvas_x = client_x - canvas_client_left_;",
                "canvas_x = client_x + canvas_client_left_;",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                COORDINATES_MARKER,
                "canvas_x < canvas_client_width_ && canvas_y < canvas_client_height_",
                "canvas_x <= canvas_client_width_ && canvas_y <= canvas_client_height_",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                REGISTER_MARKER,
                "if (!refreshCanvasClientRect())",
                "if (false)",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                RESIZE_CALLBACK_MARKER,
                "system->refreshCanvasClientRect();",
                "",
            ),
            live_test,
            lifecycle_contract,
        ),
        (
            mutate_method(
                system,
                REFRESH_MARKER,
                "if (rect[2] <= 0 || rect[3] <= 0)",
                "if (rect[2] <= 0 && rect[3] <= 0)",
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
                "dragPositions.some((position) => position.x > box.width)",
                "dragPositions.some((position) => position.x < box.width)",
            ),
            lifecycle_contract,
        ),
        (
            system,
            replace_once(
                live_test,
                "unrelatedPrevented || releasesAfter !== releasesBefore || movesAfter !== movesBefore",
                "unrelatedPrevented && releasesAfter !== releasesBefore && movesAfter !== movesBefore",
            ),
            lifecycle_contract,
        ),
        (
            system,
            live_test,
            replace_once(
                lifecycle_contract,
                '("window", "EMSCRIPTEN_EVENT_MOUSEMOVE", "cb_mousemove")',
                '("canvas", "EMSCRIPTEN_EVENT_MOUSEMOVE", "cb_mousemove")',
            ),
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
        "MOUSE_RELEASE_OWNERSHIP_CONTRACT PASS press=canvas motion=window-capture "
        "release=window-capture unowned=suppressed coords=canvas mutations=22"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
