#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind browser cursor grab to confirmed Pointer Lock outcomes and relative motion."""

from __future__ import annotations

import argparse
from pathlib import Path


GRAB_MARKER = "GHOST_TSuccess GHOST_WindowWeb::setWindowCursorGrab(GHOST_TGrabCursorMode mode)"
PUBLIC_GRAB_MARKER = "GHOST_TSuccess GHOST_WindowWeb::setCursorGrab("
CHANGE_MARKER = "void GHOST_WindowWeb::onPointerLockChange(const bool is_active)"
ERROR_MARKER = "void GHOST_WindowWeb::onPointerLockError()"
RELEASE_MARKER = "void GHOST_WindowWeb::releasePointerLock()"
SOFTWARE_CURSOR_MARKER = "bool GHOST_WindowWeb::getCursorGrabUseSoftwareDisplay()"
MOVE_MARKER = "void on_mouse_move(GHOST_SystemWeb &sys, const EmscriptenMouseEvent &e)"
FOCUS_MARKER = "void on_focus(GHOST_SystemWeb &sys, bool focused)"
CHANGE_CALLBACK_MARKER = "bool cb_pointerlockchange("
ERROR_CALLBACK_MARKER = "bool cb_pointerlockerror("
REGISTER_MARKER = "bool GHOST_SystemWeb::registerCanvasCallbacks()"
UNREGISTER_MARKER = "void GHOST_SystemWeb::unregisterCanvasCallbacks()"
REMOVE_PREFIX_MARKER = "bool remove_html5_callback_prefix(const char *canvas,"
DISPOSE_MARKER = "GHOST_TSuccess GHOST_SystemWeb::disposeWindow(GHOST_IWindow *window)"
CAPABILITIES_MARKER = "GHOST_TCapabilityFlag GHOST_SystemWeb::getCapabilities() const"
WARP_MARKER = "GHOST_TSuccess GHOST_SystemWeb::setCursorPosition(int32_t"


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


def mutate_method(source: str, marker: str, old: str, new: str) -> str:
    original = method(source, marker)
    changed = original.replace(old, new, 1)
    if changed == original:
        raise ValueError(f"mutation input is absent from {marker}: {old!r}")
    return source.replace(original, changed, 1)


def validate(window: str, header: str, bridge: str, system: str) -> None:
    grab = method(window, GRAB_MARKER)
    public_grab = method(window, PUBLIC_GRAB_MARKER)
    change = method(window, CHANGE_MARKER)
    error = method(window, ERROR_MARKER)
    release = method(window, RELEASE_MARKER)
    software_cursor = method(window, SOFTWARE_CURSOR_MARKER)
    move = method(bridge, MOVE_MARKER)
    focus = method(bridge, FOCUS_MARKER)
    change_callback = method(system, CHANGE_CALLBACK_MARKER)
    error_callback = method(system, ERROR_CALLBACK_MARKER)
    register = method(system, REGISTER_MARKER)
    unregister = method(system, UNREGISTER_MARKER)
    remove_prefix = method(system, REMOVE_PREFIX_MARKER)
    dispose = method(system, DISPOSE_MARKER)
    capabilities = method(system, CAPABILITIES_MARKER)
    warp = method(system, WARP_MARKER)

    if header.count("enum class PointerLockState : uint8_t") != 1:
        raise ValueError("window header does not expose the pointer-lock outcome state")
    if header.count("GHOST_TSuccess setCursorGrab(GHOST_TGrabCursorMode mode,") != 1:
        raise ValueError("window header does not override accepted-vs-active cursor grab")
    if header.count(
        "GHOST_TSuccess setWindowCursorGrab(GHOST_TGrabCursorMode mode) override;"
    ) != 1:
        raise ValueError("window header does not declare the cursor-grab implementation")
    if header.count("bool getCursorGrabUseSoftwareDisplay() override;") != 1:
        raise ValueError("window header does not declare the software cursor policy")
    for declaration in (
        "void onPointerLockChange(bool is_active);",
        "void onPointerLockError();",
        "void releasePointerLock();",
        "bool isPointerLockActive() const",
        "PointerLockState pointerLockState() const",
        "GHOST_TGrabCursorMode pointerLockRequestedMode() const",
    ):
        if header.count(declaration) != 1:
            raise ValueError(f"window header requires exactly one {declaration!r}")

    required_grab = (
        "switch (mode)",
        "case GHOST_kGrabDisable:",
        "case GHOST_kGrabNormal:",
        "case GHOST_kGrabWrap:",
        "case GHOST_kGrabHide:",
        "emscripten_exit_pointerlock()",
        "emscripten_request_pointerlock(canvas_selector_.c_str(), true)",
        "EMSCRIPTEN_RESULT_DEFERRED",
    )
    for token in required_grab:
        if grab.count(token) != 1:
            raise ValueError(f"cursor grab requires exactly one {token!r}")
    if grab.count("return GHOST_kFailure;") < 1:
        raise ValueError("unknown cursor-grab modes do not fail honestly")
    normal = grab[grab.index("case GHOST_kGrabNormal:") : grab.index("case GHOST_kGrabWrap:")]
    if normal.count("emscripten_exit_pointerlock()") != 1:
        raise ValueError("normal visible-pointer mode does not release an earlier Pointer Lock")
    required_public_grab = (
        "pointer_lock_requested_mode_ = mode;",
        "pointer_lock_state_ = PointerLockState::Pending;",
        "pointer_lock_requested_bounds_ = *bounds;",
        "getClientBounds(pointer_lock_requested_bounds_);",
        "case GHOST_kGrabWrap:",
        "case GHOST_kGrabHide:",
        "case GHOST_kGrabDisable:",
        "case GHOST_kGrabNormal:",
    )
    for token in required_public_grab:
        if public_grab.count(token) != 1:
            raise ValueError(f"accepted-vs-active grab requires exactly one {token!r}")
    if public_grab.count("setWindowCursorGrab(mode)") != 2:
        raise ValueError("acquire and release must each cross the browser platform seam")
    if public_grab.count("applyCursorGrabState(mode, wrap_axis") != 2:
        raise ValueError("confirmed acquire and explicit release must each publish GHOST state")
    public_positions = [
        public_grab.index("pointer_lock_requested_mode_ = mode;"),
        public_grab.index("setWindowCursorGrab(mode)"),
        public_grab.index("pointer_lock_state_ = PointerLockState::Pending;"),
    ]
    if public_positions != sorted(public_positions):
        raise ValueError("pointer lock publishes pending state before the request is accepted")

    for token in (
        "pointer_lock_requested_mode_ == GHOST_kGrabWrap",
        "pointer_lock_requested_mode_ == GHOST_kGrabHide",
        "pointer_lock_state_ = PointerLockState::Active;",
        "applyCursorGrabState(pointer_lock_requested_mode_",
        "retirePointerLock(false);",
        "emscripten_exit_pointerlock();",
    ):
        if change.count(token) != 1:
            raise ValueError(f"pointerlockchange reconciliation requires exactly one {token!r}")
    if error.count("retirePointerLock(true);") != 1:
        raise ValueError("pointerlockerror does not cancel deferred/active ownership")
    if release.count("retirePointerLock(true);") != 1:
        raise ValueError("explicit pointer-lock release does not cancel ownership")
    if software_cursor.count(
        "return isPointerLockActive() && getCursorGrabMode() == GHOST_kGrabWrap;"
    ) != 1:
        raise ValueError("wrap software cursor is shown before Pointer Lock becomes active")

    required_move = (
        "int32_t x = e.targetX;",
        "int32_t y = e.targetY;",
        "win->isPointerLockActive()",
        "sys.getCursorPosition(previous_x, previous_y)",
        "int64_t(previous) + int64_t(movement)",
        "std::numeric_limits<int32_t>::min()",
        "std::numeric_limits<int32_t>::max()",
        "x = add_motion(previous_x, e.movementX);",
        "y = add_motion(previous_y, e.movementY);",
        "sys.noteCursor(x, y);",
        "win, x, y, GHOST_TABLET_DATA_NONE",
    )
    for token in required_move:
        if move.count(token) != 1:
            raise ValueError(f"relative cursor bridge requires exactly one {token!r}")
    if "sys.noteCursor(e.targetX, e.targetY);" in move:
        raise ValueError("locked motion still publishes frozen DOM absolute coordinates")

    for token in (
        "e != nullptr && e->isActive",
        "document.pointerLockElement ===",
        "document.querySelector(selector)",
        "window->onPointerLockChange(owns_lock);",
    ):
        if change_callback.count(token) != 1:
            raise ValueError(f"pointerlockchange callback requires exactly one {token!r}")
    if error_callback.count("window->onPointerLockError();") != 1:
        raise ValueError("pointerlockerror callback does not reach the active window")
    for token in (
        "emscripten_set_pointerlockchange_callback(",
        "emscripten_set_pointerlockerror_callback(",
    ):
        if register.count(token) != 1:
            raise ValueError(f"callback registration requires exactly one {token!r}")
    for token in (
        "EMSCRIPTEN_EVENT_POINTERLOCKCHANGE",
        "cb_pointerlockchange",
        "EMSCRIPTEN_EVENT_POINTERLOCKERROR",
        "cb_pointerlockerror",
    ):
        if remove_prefix.count(token) != 1:
            raise ValueError(f"callback retirement requires exactly one {token!r}")
    if unregister.count("remove_html5_callback_prefix(canvas, win, callback_user_data_, 14)") != 1:
        raise ValueError("callback retirement does not remove the complete listener set")
    if focus.count("win->releasePointerLock();") != 1:
        raise ValueError("blur does not cancel pending/active Pointer Lock")
    if dispose.count("active_window->releasePointerLock();") != 1:
        raise ValueError("window disposal does not cancel pending/active Pointer Lock")

    if capabilities.count("GHOST_kCapabilityCursorWarp") != 1:
        raise ValueError("absolute cursor warp must remain masked")
    if warp.count("return GHOST_kFailure;") != 1 or "return GHOST_kSuccess;" in warp:
        raise ValueError("absolute cursor positioning is falsely advertised")


def selfcheck(window: str, header: str, bridge: str, system: str) -> None:
    validate(window, header, bridge, system)
    mutations = (
        (mutate_method(window, GRAB_MARKER, "emscripten_exit_pointerlock()",
                       "EMSCRIPTEN_RESULT_SUCCESS"), header, bridge, system),
        (mutate_method(window, GRAB_MARKER,
                       "emscripten_request_pointerlock(canvas_selector_.c_str(), true)",
                       "EMSCRIPTEN_RESULT_SUCCESS"), header, bridge, system),
        (mutate_method(window, GRAB_MARKER,
                       "emscripten_request_pointerlock(canvas_selector_.c_str(), true)",
                       "emscripten_request_pointerlock(canvas_selector_.c_str(), false)"),
         header, bridge, system),
        (mutate_method(window, GRAB_MARKER, "EMSCRIPTEN_RESULT_DEFERRED",
                       "EMSCRIPTEN_RESULT_SUCCESS"), header, bridge, system),
        (mutate_method(window, GRAB_MARKER, "case GHOST_kGrabNormal:",
                       "case GHOST_kGrabDisable:"), header, bridge, system),
        (window, header.replace("setWindowCursorGrab", "setWindowCursorGrabMissing", 1), bridge, system),
        (mutate_method(window, SOFTWARE_CURSOR_MARKER, "GHOST_kGrabWrap",
                       "GHOST_kGrabHide"), header, bridge, system),
        (window, header, bridge.replace("win->isPointerLockActive()", "false", 1), system),
        (window, header, bridge.replace("e.movementX", "e.targetX", 1), system),
        (window, header, bridge.replace("e.movementY", "e.targetY", 1), system),
        (window, header, bridge.replace("sys.getCursorPosition(previous_x, previous_y)",
                                        "GHOST_kFailure", 1), system),
        (window, header, bridge, system.replace("GHOST_kCapabilityCursorWarp |", "", 1)),
        (window, header, bridge,
         mutate_method(system, WARP_MARKER, "return GHOST_kFailure;",
                       "return GHOST_kSuccess;")),
        (mutate_method(window, PUBLIC_GRAB_MARKER,
                       "pointer_lock_state_ = PointerLockState::Pending;",
                       "pointer_lock_state_ = PointerLockState::Active;"),
         header, bridge, system),
        (mutate_method(window, CHANGE_MARKER, "retirePointerLock(false);", "return;"),
         header, bridge, system),
        (mutate_method(window, ERROR_MARKER, "retirePointerLock(true);", "return;"),
         header, bridge, system),
        (mutate_method(window, RELEASE_MARKER, "retirePointerLock(true);", "return;"),
         header, bridge, system),
        (window, header, bridge,
         mutate_method(system, CHANGE_CALLBACK_MARKER,
                       "window->onPointerLockChange(owns_lock);", "return false;")),
        (window, header, bridge,
         mutate_method(system, ERROR_CALLBACK_MARKER,
                       "window->onPointerLockError();", "return false;")),
        (window, header, mutate_method(bridge, FOCUS_MARKER,
                                      "win->releasePointerLock();", "return;"), system),
        (window, header, bridge,
         mutate_method(system, DISPOSE_MARKER,
                       "active_window->releasePointerLock();", "return GHOST_kFailure;")),
    )
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate(*mutation)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("window_source", type=Path)
    parser.add_argument("window_header", type=Path)
    parser.add_argument("bridge_source", type=Path)
    parser.add_argument("system_source", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    sources = tuple(
        path.read_text(encoding="utf-8")
        for path in (
            args.window_source,
            args.window_header,
            args.bridge_source,
            args.system_source,
        )
    )
    if args.selfcheck:
        selfcheck(*sources)
    else:
        validate(*sources)
    print(
        "POINTER_LOCK_CONTRACT PASS modes=normal,wrap,hide,disable "
        "outcomes=pending,active,error,lost,blur,disposed relative=active-only,saturated "
        "cursor=wrap-software capability=absolute-warp-off mutations=21"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
