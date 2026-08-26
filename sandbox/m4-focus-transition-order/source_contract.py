#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail-closed contract for DOM-event-time browser focus publication."""

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


def require_count(source: str, token: str, count: int, label: str) -> None:
    actual = source.count(token)
    if actual != count:
        raise ValueError(f"{label}: expected {count} instances of {token!r}, got {actual}")


def require_order(source: str, tokens: tuple[str, ...], label: str) -> None:
    position = -1
    for token in tokens:
        found = source.find(token, position + 1)
        if found < 0:
            raise ValueError(f"{label}: missing ordered token {token!r}")
        position = found


def validate(header: str, source: str, live_test: str) -> None:
    require_count(
        header,
        "void reconcilePublishedBrowserFocus();",
        1,
        "focus reconciliation declaration",
    )
    require_count(
        header,
        "void acknowledgePublishedBrowserFocusLoss();",
        1,
        "focus loss acknowledgement declaration",
    )
    require_count(
        header,
        "uint32_t browser_focus_loss_generation_ = 0;",
        1,
        "per-system loss baseline",
    )

    publish = method(source, 'extern "C" EMSCRIPTEN_KEEPALIVE void bw_shell_focus_lost()')
    require_count(
        publish,
        "g_browser_focus_loss_generation.fetch_add(1u, std::memory_order_release);",
        1,
        "main-thread loss publication",
    )
    if "g_browser_focus_owned" in source:
        raise ValueError("focus bridge duplicates the live DOM ownership state")

    registration = method(source, "bool GHOST_SystemWeb::registerCanvasCallbacks()")
    for token in (
        'document.addEventListener("blur"',
        "lossGeneration += 1;",
        "bridge.bind(UTF8ToString($0))",
        "browser_focus_loss_generation_ =",
        "g_browser_focus_loss_generation.load(std::memory_order_acquire);",
        "browser_focus_active_ = browserFocusIsOwned();",
    ):
        require_count(registration, token, 1, "event-time focus bridge")
    require_count(
        registration,
        'Module["_bw_shell_focus_lost"]',
        2,
        "fail-closed loss publisher binding",
    )
    require_count(registration, "event.relatedTarget", 1, "focus destination classification")
    require_count(registration, "publishLoss();", 1, "focus loss publication")
    require_count(registration, "focusBridge.beginHandoff();", 2, "IME handoff begin")
    require_count(registration, "focusBridge.endHandoff();", 2, "IME handoff end")
    require_count(registration, "bridge.unbind(UTF8ToString($0));", 1, "rollback unbind")
    for forbidden in (
        'document.addEventListener("focusin"',
        'document.addEventListener("focusout"',
        'window.addEventListener("blur"',
        'window.addEventListener("focus"',
    ):
        if forbidden in registration:
            raise ValueError(f"focus bridge unnecessarily mirrors ownership: {forbidden}")

    unregistration = method(source, "void GHOST_SystemWeb::unregisterCanvasCallbacks()")
    require_count(unregistration, "bridge.unbind(UTF8ToString($0));", 1, "lifecycle unbind")

    canvas_focus = method(source, "bool cb_canvas_focus(")
    require_order(
        canvas_focus,
        (
            "system->reconcilePublishedBrowserFocus();",
            "system->browserFocusIsOwned()",
            "publish_browser_focus_transition(system, true);",
        ),
        "queued canvas focus reconciliation",
    )

    canvas_blur = method(source, "bool cb_canvas_blur(")
    require_order(
        canvas_blur,
        (
            "system->reconcilePublishedBrowserFocus();",
            "system->browserFocusIsOwned()",
            "system->acknowledgePublishedBrowserFocusLoss();",
            "publish_browser_focus_transition(system, false);",
        ),
        "ordinary canvas blur acknowledgement",
    )
    acknowledge = method(source, "void GHOST_SystemWeb::acknowledgePublishedBrowserFocusLoss()")
    require_count(
        acknowledge,
        "g_browser_focus_loss_generation.load(std::memory_order_acquire);",
        1,
        "loss acknowledgement acquire",
    )

    process = method(source, "bool GHOST_SystemWeb::processEvents(bool /*waitForEvent*/)")
    require_order(
        process,
        ("reconcilePublishedBrowserFocus();", "ghost_web_bridge::poll_ime(*this);"),
        "focus-before-input reconciliation",
    )

    poll = method(source, "void GHOST_SystemWeb::reconcilePublishedBrowserFocus()")
    require_order(
        poll,
        (
            "g_browser_focus_loss_generation.load(std::memory_order_acquire);",
            "if (loss_generation == browser_focus_loss_generation_)",
            "return;",
            "publish_browser_focus_transition(this, false);",
            "browserFocusIsOwned()",
            "publish_browser_focus_transition(this, true);",
        ),
        "loss-before-live-state replay",
    )
    if "ghost_web_bridge::on_focus(*this" in poll:
        raise ValueError("focus poll bypasses transition-state admission")

    for token in (
        'document.querySelector("#blender-canvas").focus();',
        'result.log.includes("ButtonUp")',
        'result.publisher !== "function"',
        "result.publishedLoss !== result.bridge?.lossGeneration",
        "ordinary.publishedLoss !== ordinaryBefore.publishedLoss + 1",
        "ordinary.bridge?.lossGeneration !== ordinaryBefore.bridge?.lossGeneration + 1",
        'const assertSameTaskInputOrder = async (kind) => {',
        'canvas.dispatchEvent(new KeyboardEvent("keydown"',
        'canvas.dispatchEvent(new KeyboardEvent("keyup"',
        'canvas.dispatchEvent(new MouseEvent("mousedown"',
        'window.dispatchEvent(new MouseEvent("mouseup"',
        '["deactivate", "activate", "key-down", "key-up"]',
        '["deactivate", "activate", "button-down", "button-up"]',
        'await assertSameTaskInputOrder("key");',
        'await assertSameTaskInputOrder("mouse");',
    ):
        require_count(live_test, token, 1, "real-worker focus-order test")
    require_count(
        live_test,
        'log.includes("WindowDeactivate") && log.includes("WindowActivate")',
        2,
        "held-state and same-task terminal waits",
    )
    require_count(
        live_test,
        'document.querySelector("#clear").focus();',
        2,
        "rapid and ordinary external focus",
    )
    require_count(
        live_test,
        'JSON.stringify(["GHOST WindowDeactivate", "GHOST WindowActivate"])',
        2,
        "single focus transition pairs",
    )
    require_order(
        live_test,
        (
            'document.querySelector("#clear").focus();',
            'document.querySelector("#blender-canvas").focus();',
        ),
        "same-task blur/refocus",
    )


def mutate_once(source: str, old: str, new: str) -> str:
    if old not in source:
        raise ValueError(f"mutation input is absent: {old!r}")
    return source.replace(old, new, 1)


def selfcheck(header: str, source: str, live_test: str) -> int:
    mutations = [
        (
            "header",
            "void reconcilePublishedBrowserFocus();",
            "void skipPublishedBrowserFocus();",
        ),
        (
            "header",
            "void acknowledgePublishedBrowserFocusLoss();",
            "void skipPublishedBrowserFocusLoss();",
        ),
        ("header", "uint32_t browser_focus_loss_generation_ = 0;", "uint32_t ignored_ = 0;"),
        (
            "source",
            "g_browser_focus_loss_generation.fetch_add(1u, std::memory_order_release);",
            "g_browser_focus_loss_generation.fetch_add(1u, std::memory_order_relaxed);",
        ),
        ("source", 'document.addEventListener("blur"', 'document.addEventListener("mouseout"'),
        ("source", "event.relatedTarget", "null"),
        ("source", 'Module["_bw_shell_focus_lost"]', 'Module["_bw_shell_focus_seen"]'),
        ("source", "focusBridge.beginHandoff();", "focusBridge.endHandoff();"),
        ("source", "focusBridge.endHandoff();", "focusBridge.beginHandoff();"),
        (
            "source",
            "system->reconcilePublishedBrowserFocus();",
            "/* queued focus reconciliation removed */",
        ),
        (
            "source",
            "reconcilePublishedBrowserFocus();",
            "/* tick focus reconciliation removed */",
        ),
        (
            "source",
            "system->acknowledgePublishedBrowserFocusLoss();",
            "system->transitionBrowserFocus(false);",
        ),
        ("source", "publish_browser_focus_transition(this, false);", "ghost_web_bridge::on_focus(*this, false);"),
        ("source", "if (browserFocusIsOwned()) {", "if (false) {"),
        ("source", "bridge.unbind(UTF8ToString($0));", "bridge.snapshot();"),
        ("live", 'document.querySelector("#clear").focus();', "/* external focus removed */"),
        ("live", 'result.log.includes("ButtonUp")', "true"),
        ("live", 'result.publisher !== "function"', "false"),
        (
            "live",
            '["deactivate", "activate", "key-down", "key-up"]',
            '["key-down", "key-up", "deactivate", "activate"]',
        ),
        ("live", 'await assertSameTaskInputOrder("mouse");', "/* mouse case removed */"),
    ]
    rejected = 0
    for target, old, new in mutations:
        parts = {"header": header, "source": source, "live": live_test}
        parts[target] = mutate_once(parts[target], old, new)
        try:
            validate(parts["header"], parts["source"], parts["live"])
        except ValueError:
            rejected += 1
        else:
            raise ValueError(f"mutation unexpectedly passed: {target} {old!r}")
    return rejected


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
    validate(header, source, live_test)
    mutations = selfcheck(header, source, live_test) if args.selfcheck else 0
    print(f"M4_FOCUS_TRANSITION_ORDER_SOURCE PASS mutations={mutations}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
