#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind the single-canvas window lookup to GHOST's client-bounds contract."""

from __future__ import annotations

import argparse
from pathlib import Path


WEB_MARKER = "GHOST_IWindow *GHOST_SystemWeb::getWindowUnderCursor("
BASE_MARKER = "GHOST_IWindow *GHOST_System::getWindowUnderCursor("


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
    interface: str,
    base_source: str,
    web_source: str,
    harness_source: str,
    browser_test: str,
) -> None:
    require_once(
        interface,
        r"\return The window under the cursor or nullptr if none.",
        "GHOST interface",
    )

    base = method(base_source, BASE_MARKER)
    for token in (
        "win->getClientBounds(bounds);",
        "if (bounds.isInside(x, y))",
        "return nullptr;",
    ):
        require_once(base, token, "base lookup")

    web = method(web_source, WEB_MARKER)
    for token in (
        "if (window_ == nullptr) {",
        "GHOST_Rect bounds;",
        "window_->getClientBounds(bounds);",
        "return bounds.isInside(x, y) ? window_ : nullptr;",
    ):
        require_once(web, token, "web lookup")
    positions = [
        web.index("if (window_ == nullptr) {"),
        web.index("window_->getClientBounds(bounds);"),
        web.index("return bounds.isInside(x, y) ? window_ : nullptr;"),
    ]
    if positions != sorted(positions):
        raise ValueError("web lookup tests bounds before resolving a live window")

    for token in (
        "if (action < 0 || action > 3)",
        "else if (requested_lifecycle == 2)",
        "g_window->getClientBounds(bounds);",
        "hits_window(bounds.l_, bounds.t_)",
        "hits_window(bounds.r_, bounds.b_)",
        "hits_nothing(bounds.l_ - 1, bounds.t_)",
        "hits_nothing(bounds.l_, bounds.t_ - 1)",
        "hits_nothing(bounds.r_ + 1, bounds.b_)",
        "hits_nothing(bounds.r_, bounds.b_ + 1)",
    ):
        require_once(harness_source, token, "worker harness")
    for token in (
        "const hitTestResult = await request(2);",
        "hitTestResult !== 0b11111111",
        "hit-test=bounded",
    ):
        require_once(browser_test, token, "browser harness")


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return text.replace(old, new, 1)


def mutate_method(source: str, marker: str, old: str, new: str) -> str:
    original = method(source, marker)
    changed = replace_once(original, old, new)
    return source.replace(original, changed, 1)


def selfcheck(
    interface: str,
    base_source: str,
    web_source: str,
    harness_source: str,
    browser_test: str,
) -> None:
    validate(interface, base_source, web_source, harness_source, browser_test)
    mutations = (
        (replace_once(interface, r"\return The window under the cursor or nullptr if none.", ""), base_source, web_source, harness_source, browser_test),
        (interface, replace_once(base_source, "if (bounds.isInside(x, y))", "if (true)"), web_source, harness_source, browser_test),
        (interface, base_source, mutate_method(web_source, WEB_MARKER, "if (window_ == nullptr) {", "if (false) {"), harness_source, browser_test),
        (interface, base_source, mutate_method(web_source, WEB_MARKER, "window_->getClientBounds(bounds);", ""), harness_source, browser_test),
        (interface, base_source, mutate_method(web_source, WEB_MARKER, "bounds.isInside(x, y)", "true"), harness_source, browser_test),
        (interface, base_source, mutate_method(web_source, WEB_MARKER, "? window_ : nullptr", "? window_ : window_"), harness_source, browser_test),
        (interface, base_source, web_source, replace_once(harness_source, "if (action < 0 || action > 3)", "if (action < 0 || action > 1)"), browser_test),
        (interface, base_source, web_source, replace_once(harness_source, "hits_nothing(bounds.r_ + 1, bounds.b_)", "hits_window(bounds.r_ + 1, bounds.b_)"), browser_test),
        (interface, base_source, web_source, harness_source, replace_once(browser_test, "hitTestResult !== 0b11111111", "hitTestResult !== 0b00001111")),
        (interface, base_source, web_source, harness_source, replace_once(browser_test, "hit-test=bounded", "hit-test=unbounded")),
    )
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate(*mutation)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("interface", type=Path)
    parser.add_argument("base_source", type=Path)
    parser.add_argument("web_source", type=Path)
    parser.add_argument("harness_source", type=Path)
    parser.add_argument("browser_test", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    inputs = tuple(
        path.read_text(encoding="utf-8")
        for path in (
            args.interface,
            args.base_source,
            args.web_source,
            args.harness_source,
            args.browser_test,
        )
    )
    if args.selfcheck:
        selfcheck(*inputs)
    else:
        validate(*inputs)
    print(
        "WINDOW_HIT_TEST_CONTRACT PASS inside=3 outside=4 null=detached "
        "coordinates=client-screen-identity mutations=10"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
