#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind GHOST-web window disposal to registration-epoch callback retirement."""

from __future__ import annotations

import argparse
from pathlib import Path


DISPOSE_MARKER = "GHOST_TSuccess GHOST_SystemWeb::disposeWindow(GHOST_IWindow *window)"
REGISTER_MARKER = "bool GHOST_SystemWeb::registerCanvasCallbacks()"
UNREGISTER_MARKER = "void GHOST_SystemWeb::unregisterCanvasCallbacks()"
REMOVE_PREFIX_MARKER = "bool remove_html5_callback_prefix(const char *canvas,"
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


def validate(
        header: str,
        source: str,
        harness_test: str,
        live_test: str,
        integrated_test: str) -> None:
    for token in (
        "~GHOST_SystemWeb() override;",
        "GHOST_TSuccess disposeWindow(GHOST_IWindow *window) override;",
        "bool registerCanvasCallbacks();",
        "void unregisterCanvasCallbacks();",
        "bool callbacks_registered_ = false;",
        "void *callback_user_data_ = nullptr;",
    ):
        require_once(header, token, "header")

    for token in (
        "constexpr uint32_t kCallbackRegistrationBudget = 4096;",
        "std::array<uint8_t, kCallbackRegistrationBudget> g_callback_registration_tokens{};",
        "std::atomic<uint32_t> g_callback_registration_token_count{0};",
        "std::atomic<void *> g_callback_registration{nullptr};",
        "std::atomic<GHOST_SystemWeb *> g_callback_system{nullptr};",
        "g_callback_registration.load(std::memory_order_acquire) != user_data",
        "g_callback_system.load(std::memory_order_acquire)",
    ):
        require_once(source, token, "registration epoch")
    if "struct CallbackRegistration" in source or \
            "g_callback_registrations" in source or \
            "static_cast<GHOST_SystemWeb *>(user_data)" in source:
        raise ValueError("callback admission still reuses the system pointer")
    if source.count("callback_system(ud)") != 12 or source.count("if (system == nullptr)") != 8:
        raise ValueError("every HTML5 callback must validate its live system owner")

    for token in (
        "Object.defineProperty(globalThis, \"__bwStaleCallbackProbe\"",
        "this instanceof HTMLCanvasElement",
        "this.id === \"blender-canvas\"",
        "probe.held.push(() => listener.call(this, event));",
        "await queueOldKey(\"q\", \"KeyQ\", 1);",
        "await queueOldKey(\"w\", \"KeyW\", 2);",
        "document.querySelector(\"#blender-canvas\").dispatchEvent(",
        "const staleSnapshot = await page.evaluate(() => {",
        "staleLog.includes(\"KeyDown\")",
        "queued=registration-epoch repeated-replacements=2",
        "const managerState = () => page.evaluate(() => Number(",
        "created canvas window was not published active",
        "disposed canvas window remained active in GHOST_WindowManager",
        "replacement canvas window was not published active",
        "const secondWindowResult = await request(3);",
        "secondWindowResult !== 0b1111111",
        "simultaneous second window did not fail closed",
        "second-window rejection changed the active canvas window",
        "second-window=fail-closed",
        "manager=create-focus-blur-dispose-replace",
    ):
        require_once(live_test, token, "live stale-callback test")

    for token in (
        "if (action < 0 || action > 3)",
        "else if (requested_lifecycle == 3)",
        "const size_t windows_before = window_manager ? window_manager->getWindows().size() : 0;",
        "GHOST_IWindow *second_window = create_harness_window();",
        "result |= second_window == nullptr ? (1 << 2) : 0;",
        "window_manager->getWindows().size() == windows_before",
        "if (second_window != nullptr)",
    ):
        require_once(harness_test, token, "two-live-window harness")

    destructor = method(source, DESTRUCTOR_MARKER)
    require_once(destructor, "unregisterCanvasCallbacks();", "destructor")
    require_once(destructor, "window_ = nullptr;", "destructor")
    if destructor.index("unregisterCanvasCallbacks();") > destructor.index("window_ = nullptr;"):
        raise ValueError("destructor detaches the system before unregistering callbacks")

    registration = method(source, REGISTER_MARKER)
    require_once(registration, "if (callbacks_registered_)", "registration")
    for token in (
        "void *user_data = callback_registration_token_acquire();",
        "if (user_data == nullptr)",
        "callback registration token budget exhausted",
        "ghost_web::sequential_registration_transaction<kWebCallbackCount>(",
        "remove_html5_callback_prefix(canvas, win, user_data, registered_count)",
        "callback_user_data_ = user_data;",
        "g_callback_system.store(this, std::memory_order_release);",
        "g_callback_registration.store(user_data, std::memory_order_release);",
        "return registration_succeeded;",
    ):
        require_once(registration, token, "registration")
    require_once(registration, "callbacks_registered_ = true;", "registration")
    acquire = registration.index("callback_registration_token_acquire()")
    transaction = registration.index(
        "ghost_web::sequential_registration_transaction<kWebCallbackCount>(")
    publish_user_data = registration.index("callback_user_data_ = user_data;")
    publish_owner = registration.index("g_callback_system.store(")
    publish_record = registration.index("g_callback_registration.store(")
    publish_registered = registration.index("callbacks_registered_ = true;")
    if not acquire < transaction < publish_user_data < publish_owner < publish_record < publish_registered:
        raise ValueError("callback owner publishes before the complete listener transaction")
    if ", this, false," in registration:
        raise ValueError("listener registration still uses the reusable system pointer")
    for setter in (
        "emscripten_set_mousemove_callback",
        "emscripten_set_mousedown_callback",
        "emscripten_set_mouseup_callback",
        "emscripten_set_wheel_callback",
        "emscripten_set_contextmenu_callback",
        "emscripten_set_pointerlockchange_callback",
        "emscripten_set_pointerlockerror_callback",
        "emscripten_set_resize_callback",
    ):
        require_once(registration, setter, "registration result")
    for setter in ("emscripten_set_keydown_callback", "emscripten_set_keyup_callback"):
        if registration.count(setter) != 2:
            raise ValueError(f"registration requires two owned-domain {setter} results")
    for setter in ("emscripten_set_focus_callback", "emscripten_set_blur_callback"):
        if registration.count(setter) != 2:
            raise ValueError(f"registration requires two logical-domain {setter} results")

    for token in (
        "bool ghost_callback_registration_transaction_contract()",
        "failed_position < listener_count",
        "rollback_prefix == failed_position",
        "active_owner == 0",
        "replacement_failure == 8",
        "failed_positions=16 replacement=rollback-retry",
    ):
        require_once(integrated_test, token, "registration transaction behavior")
    if integrated_test.count("sequential_registration_transaction<listener_count>(") != 2:
        raise ValueError("registration transaction behavior requires failure matrix and replacement")

    unregistration = method(source, UNREGISTER_MARKER)
    require_once(unregistration, "if (!callbacks_registered_)", "unregistration")
    for token in (
        "void *expected_registration = callback_user_data_;",
        "g_callback_registration.compare_exchange_strong(",
        "GHOST_SystemWeb *expected_system = this;",
        "g_callback_system.compare_exchange_strong(",
        "callback_user_data_ = nullptr;",
    ):
        require_once(unregistration, token, "unregistration")
    require_once(unregistration, "callbacks_registered_ = false;", "unregistration")
    require_once(
        unregistration,
        "remove_html5_callback_prefix(canvas, win, callback_user_data_, kWebCallbackCount)",
        "unregistration",
    )
    removal_helper = method(source, REMOVE_PREFIX_MARKER)
    removals = (
        ("window", "EMSCRIPTEN_EVENT_MOUSEMOVE", "cb_mousemove"),
        ("canvas", "EMSCRIPTEN_EVENT_MOUSEDOWN", "cb_mousebtn"),
        ("window", "EMSCRIPTEN_EVENT_MOUSEUP", "cb_mousebtn"),
        ("canvas", "EMSCRIPTEN_EVENT_WHEEL", "cb_wheel"),
        ("canvas", "EMSCRIPTEN_EVENT_CONTEXTMENU", "cb_contextmenu"),
        ("canvas", "EMSCRIPTEN_EVENT_FOCUS", "cb_canvas_focus"),
        ("canvas", "EMSCRIPTEN_EVENT_BLUR", "cb_canvas_blur"),
        ("window", "EMSCRIPTEN_EVENT_FOCUS", "cb_window_focus"),
        ("window", "EMSCRIPTEN_EVENT_BLUR", "cb_window_blur"),
        ("canvas", "EMSCRIPTEN_EVENT_KEYDOWN", "cb_key"),
        ("canvas", "EMSCRIPTEN_EVENT_KEYUP", "cb_key"),
        ("kImeInputSelector", "EMSCRIPTEN_EVENT_KEYDOWN", "cb_key"),
        ("kImeInputSelector", "EMSCRIPTEN_EVENT_KEYUP", "cb_key"),
        ("window", "EMSCRIPTEN_EVENT_RESIZE", "cb_resize"),
    )
    for target, event, callback in removals:
        compact = " ".join(removal_helper.split()).replace("( ", "(")
        token = f"remove_html5_callback({target}, user_data, {event}, {callback})"
        if token not in compact:
            raise ValueError(f"prefix removal requires exact token {token!r}")
    for event, callback in (
        ("EMSCRIPTEN_EVENT_POINTERLOCKCHANGE", "cb_pointerlockchange"),
        ("EMSCRIPTEN_EVENT_POINTERLOCKERROR", "cb_pointerlockerror"),
    ):
        require_once(removal_helper, event, "prefix removal")
        require_once(removal_helper, callback, "prefix removal")
    retire_record = unregistration.index("g_callback_registration.compare_exchange_strong(")
    retire_owner = unregistration.index("g_callback_system.compare_exchange_strong(")
    first_remove = unregistration.index("remove_html5_callback_prefix(")
    clear_userdata = unregistration.index("callback_user_data_ = nullptr;")
    if not retire_record < retire_owner < first_remove < clear_userdata:
        raise ValueError("callback epoch/token lifetime is not ordered around listener removal")

    disposal = method(source, DISPOSE_MARKER)
    for token in (
        "if (window != window_ || !validWindow(window))",
        "active_window->endIME();",
        "ghost_web_bridge::poll_ime(*this);",
        "active_window->releasePointerLock();",
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
    release_pointer_lock = disposal.index("active_window->releasePointerLock();")
    detach = disposal.index("window_ = nullptr;")
    unregister = disposal.index("unregisterCanvasCallbacks();")
    base_dispose = disposal.rindex("GHOST_System::disposeWindow(window)")
    if not release_pointer_lock < detach < unregister < base_dispose:
        raise ValueError("active pointer/callback retirement does not precede base deletion")

    creation = method(source, CREATE_MARKER)
    single_window_guard = "if (window_ != nullptr) {\n    return nullptr;\n  }"
    require_once(creation, single_window_guard, "single-canvas ownership")
    for token in (
        "bool publication_succeeded = true;",
        "if (!registerCanvasCallbacks())",
        "window_ = nullptr;",
        "publication_succeeded = false;",
        "if (!publication_succeeded)",
        "delete result;",
        "redraw_heartbeat_ = 0;",
        "wm->setActiveWindow(valid_window);",
    ):
        require_once(creation, token, "creation registration rollback")
    if creation.count("return nullptr;") != 2:
        raise ValueError("creation requires one early ownership rejection and one rollback return")
    if creation.index("window_ = valid_window;") > creation.index("if (!registerCanvasCallbacks())"):
        raise ValueError("replacement callbacks register before active-window publication")
    if creation.index(single_window_guard) > creation.index("GHOST_ContextParams context_params"):
        raise ValueError("second live window is rejected only after context construction begins")
    if creation.index("if (!registerCanvasCallbacks())") > creation.index("redraw_heartbeat_ = 0;"):
        raise ValueError("window state publishes before callback registration succeeds")
    if creation.index("wm->addWindow(valid_window);") > creation.index(
            "wm->setActiveWindow(valid_window);"):
        raise ValueError("window becomes active before window-manager publication")


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return text.replace(old, new, 1)


def mutate_method(source: str, marker: str, old: str, new: str) -> str:
    original = method(source, marker)
    changed = replace_once(original, old, new)
    return source.replace(original, changed, 1)


def selfcheck(
        header: str,
        source: str,
        harness_test: str,
        live_test: str,
        integrated_test: str) -> None:
    validate(header, source, harness_test, live_test, integrated_test)
    mutations = (
        (replace_once(header, "~GHOST_SystemWeb() override;", "~GHOST_SystemWeb() override = default;"), source, live_test),
        (replace_once(header, "GHOST_TSuccess disposeWindow(GHOST_IWindow *window) override;", ""), source, live_test),
        (replace_once(header, "bool callbacks_registered_ = false;", "bool callbacks_registered_ = true;"), source, live_test),
        (replace_once(header, "void *callback_user_data_ = nullptr;", ""), source, live_test),
        (header, replace_once(source, "std::atomic<uint32_t> g_callback_registration_token_count{0};", ""), live_test),
        (header, replace_once(source, "g_callback_registration.load(std::memory_order_acquire) != user_data", "g_callback_registration.load(std::memory_order_acquire) == user_data"), live_test),
        (header, replace_once(source, "g_callback_system.load(std::memory_order_acquire)", "nullptr"), live_test),
        (header, replace_once(source, "if (callback_system(ud) == nullptr)", "if (false)"), live_test),
        (header, mutate_method(source, REGISTER_MARKER, "if (callbacks_registered_)", "if (false)"), live_test),
        (header, mutate_method(source, REGISTER_MARKER, "void *user_data = callback_registration_token_acquire();", "void *user_data = this;"), live_test),
        (header, mutate_method(source, REGISTER_MARKER, "g_callback_system.store(this, std::memory_order_release);", ""), live_test),
        (header, mutate_method(source, REMOVE_PREFIX_MARKER, "EMSCRIPTEN_EVENT_MOUSEUP", "EMSCRIPTEN_EVENT_MOUSEDOWN"), live_test),
        (header, mutate_method(
            source,
            REMOVE_PREFIX_MARKER,
            "kImeInputSelector, user_data, EMSCRIPTEN_EVENT_KEYUP, cb_key",
            "kImeInputSelector, user_data, EMSCRIPTEN_EVENT_KEYDOWN, cb_key"), live_test),
        (header, mutate_method(source, REMOVE_PREFIX_MARKER,
                               "EMSCRIPTEN_EVENT_POINTERLOCKERROR",
                               "EMSCRIPTEN_EVENT_POINTERLOCKCHANGE"), live_test),
        (header, mutate_method(source, UNREGISTER_MARKER, "g_callback_registration.compare_exchange_strong(", "g_callback_registration.store("), live_test),
        (header, mutate_method(source, UNREGISTER_MARKER, "callback_user_data_ = nullptr;", ""), live_test),
        (header, mutate_method(source, DISPOSE_MARKER, "if (window != window_ || !validWindow(window))", "if (window != window_)"), live_test),
        (header, mutate_method(source, DISPOSE_MARKER, "active_window->endIME();", ""), live_test),
        (header, mutate_method(source, DISPOSE_MARKER, "ghost_web_bridge::poll_ime(*this);", ""), live_test),
        (header, mutate_method(source, DISPOSE_MARKER, "active_window->releasePointerLock();", ""), live_test),
        (header, mutate_method(source, DISPOSE_MARKER, "window_ = nullptr;", "window_ = active_window;"), live_test),
        (header, mutate_method(source, DISPOSE_MARKER, "buttons_ = GHOST_Buttons();", ""), live_test),
        (header, mutate_method(source, DISPOSE_MARKER, "noteModifierFlags(false, false, false, false);", ""), live_test),
        (header, mutate_method(source, CREATE_MARKER, "redraw_heartbeat_ = 0;", "redraw_heartbeat_ = 180;"), live_test),
        (header, mutate_method(source, CREATE_MARKER,
                               "if (window_ != nullptr) {\n    return nullptr;\n  }",
                               "if (false) {\n    return nullptr;\n  }"), live_test),
        (header, mutate_method(source, CREATE_MARKER,
                               "wm->setActiveWindow(valid_window);", ""), live_test),
        (header, source, replace_once(live_test, "const staleSnapshot = await page.evaluate(() => {", "const staleSnapshot = (() => {"), integrated_test),
    )
    normalized_mutations = []
    for mutation in mutations[:-1]:
        normalized_mutations.append((*mutation, integrated_test))
    normalized_mutations.append(mutations[-1])
    normalized_mutations.extend((
        (header, source,
         replace_once(live_test,
                      "secondWindowResult !== 0b1111111",
                      "secondWindowResult !== 0b1111110"),
         integrated_test),
        (header, mutate_method(source, REGISTER_MARKER,
                               "ghost_web::sequential_registration_transaction<kWebCallbackCount>(",
                               "ghost_web::sequential_registration_transaction<15>("),
         live_test, integrated_test),
        (header, mutate_method(source, REGISTER_MARKER,
                               "callback_user_data_ = user_data;", ""),
         live_test, integrated_test),
        (header, mutate_method(source, REGISTER_MARKER,
                               "remove_html5_callback_prefix(canvas, win, user_data, registered_count)",
                               "true"), live_test, integrated_test),
        (header, mutate_method(source, CREATE_MARKER,
                               "if (!registerCanvasCallbacks())", "if (false)"),
         live_test, integrated_test),
        (header, source, live_test,
         replace_once(integrated_test, "rollback_prefix == failed_position",
                      "rollback_prefix <= failed_position")),
        (header, source, live_test,
         replace_once(integrated_test, "active_owner == 0", "active_owner != 0")),
        (header, source, live_test,
         replace_once(integrated_test, "replacement_failure == 8",
                      "replacement_failure == 7")),
    ))
    harness_mutations = [
        (mutated_header, mutated_source, harness_test, mutated_live_test, mutated_integrated_test)
        for mutated_header, mutated_source, mutated_live_test, mutated_integrated_test in
        normalized_mutations
    ]
    harness_mutations.extend((
        (header, source,
         replace_once(harness_test,
                      "if (action < 0 || action > 3)",
                      "if (action < 0 || action > 2)"),
         live_test, integrated_test),
        (header, source,
         replace_once(harness_test,
                      "result |= second_window == nullptr ? (1 << 2) : 0;",
                      "result |= second_window != nullptr ? (1 << 2) : 0;"),
         live_test, integrated_test),
        (header, source,
         replace_once(harness_test,
                      "window_manager->getWindows().size() == windows_before",
                      "window_manager->getWindows().size() >= windows_before"),
         live_test, integrated_test),
    ))
    for index, (mutated_header, mutated_source, mutated_harness_test,
                mutated_live_test, mutated_integrated_test) in enumerate(
            harness_mutations, start=1):
        try:
            validate(mutated_header,
                     mutated_source,
                     mutated_harness_test,
                     mutated_live_test,
                     mutated_integrated_test)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("header", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("harness_test", type=Path)
    parser.add_argument("live_test", type=Path)
    parser.add_argument("integrated_test", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    header = args.header.read_text(encoding="utf-8")
    source = args.source.read_text(encoding="utf-8")
    harness_test = args.harness_test.read_text(encoding="utf-8")
    live_test = args.live_test.read_text(encoding="utf-8")
    integrated_test = args.integrated_test.read_text(encoding="utf-8")
    if args.selfcheck:
        selfcheck(header, source, harness_test, live_test, integrated_test)
    else:
        validate(header, source, harness_test, live_test, integrated_test)
    print(
        "WINDOW_LIFECYCLE_CONTRACT PASS active=detach-before-delete callbacks=16 "
        "replacement=rebound ime=retired pointerlock=retired queued=registration-epoch "
        "replacements=2 second-window=fail-closed manager=active-lifecycle "
        "registration=transactional mutations=38"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
