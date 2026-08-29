#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Require pending browser selection to leave viewport navigation responsive."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VIEW3D_SELECT = ROOT / "upstream/source/blender/editors/space_view3d/view3d_select.cc"
WM_EVENT_SYSTEM = ROOT / "upstream/source/blender/windowmanager/intern/wm_event_system.cc"
PRODUCER = ROOT / "sandbox/p0-interaction-stress/rapid_freeze_repro.mjs"
PATCH = ROOT / "patches/0315-view3d-web-selection-navigation-passthrough.patch"
SERIES = ROOT / "patches/series"


def require(source: str, token: str, count: int = 1) -> None:
    if source.count(token) != count:
        raise ValueError(f"expected {count} occurrence(s) of {token!r}")


def validate(sources: dict[str, str]) -> None:
    view3d_select = sources["view3d_select"]
    wm_event_system = sources["wm_event_system"]
    producer = sources["producer"]
    patch = sources["patch"]
    series = sources["series"]

    helper = (
        "static bool view3d_select_async_navigation_event(const short event_type)\n"
        "{\n"
        "  return ISMOUSE_MOTION(event_type) || event_type == MIDDLEMOUSE ||\n"
        "         ISMOUSE_WHEEL(event_type) || ISMOUSE_GESTURE(event_type) ||\n"
        "         ISKEYMODIFIER(event_type) || ISNDOF(event_type);\n"
        "}"
    )
    require(view3d_select, helper)
    route = (
        "if (view3d_select_async_navigation_event(event->type)) {\n"
        "      return OPERATOR_PASS_THROUGH;\n"
        "    }"
    )
    require(view3d_select, route)
    custom_route = (
        "if (ISTIMER(event->type) || event->customdata != nullptr) {\n"
        "      return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n"
        "    }"
    )
    require(view3d_select, custom_route)
    require(
        wm_event_system,
        "if (retval == (OPERATOR_PASS_THROUGH | OPERATOR_RUNNING_MODAL)) {\n"
        "    return (WM_HANDLER_BREAK | WM_HANDLER_MODAL);\n"
        "  }",
    )
    require(
        wm_event_system,
        "if (retval & OPERATOR_PASS_THROUGH) {\n    return WM_HANDLER_CONTINUE;\n  }",
    )
    require(view3d_select, "if (!view3d_select_async_event_push(data, event)) {")
    if not (
        view3d_select.index(custom_route)
        < view3d_select.index(route)
        < view3d_select.index("if (!view3d_select_async_event_push(data, event)) {")
    ):
        raise ValueError("navigation is not routed before the retained-input FIFO")

    for token in (
        'const selectionNavigationWindow = await waitForActionDrain(',
        '"isolated-selection-navigation-passthrough"',
        "\n    selectionNavigationPassedThrough =\n",
        "navigationPassedThrough: selectionNavigationPassedThrough",
        "selectionNavigationPassthroughRequired,",
        "\n    selectionNavigationPassedThrough,\n    actionDrainMs:",
        "selectionNavigationWindow.selectionContinuation.active === 1",
    ):
        require(producer, token)
    require(producer, "\n    selectionNavigationPassthroughRequired =\n", 2)
    if "retainedReplayExercised" in producer:
        raise ValueError("hardware producer still requires the navigation gesture to be replayed")
    if not (
        producer.index('"isolated-selection-pending"')
        < producer.index('"isolated-selection-navigation-passthrough"')
        < producer.index('"isolated-selection-drain"')
    ):
        raise ValueError("slow/sparse producer lost selection -> live navigation -> settle order")

    require(
        patch,
        "diff --git a/source/blender/editors/space_view3d/view3d_select.cc "
        "b/source/blender/editors/space_view3d/view3d_select.cc",
    )
    for token in (
        "+static bool view3d_select_async_navigation_event(const short event_type)",
        "+    if (view3d_select_async_navigation_event(event->type)) {",
        "+      return OPERATOR_PASS_THROUGH;",
    ):
        require(patch, token)
    require(series, PATCH.name)


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return source.replace(old, new, 1)


def self_check(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        (
            "view3d_select",
            "event_type == MIDDLEMOUSE",
            "event_type == LEFTMOUSE",
        ),
        (
            "view3d_select",
            "ISMOUSE_MOTION(event_type)",
            "false",
        ),
        (
            "view3d_select",
            "if (view3d_select_async_navigation_event(event->type)) {",
            "if (false && view3d_select_async_navigation_event(event->type)) {",
        ),
        (
            "view3d_select",
            "      return OPERATOR_PASS_THROUGH;\n    }\n    if (!view3d_select_async_event_push",
            "      return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n"
            "    }\n    if (!view3d_select_async_event_push",
        ),
        (
            "producer",
            '"isolated-selection-navigation-passthrough"',
            '"isolated-selection-navigation-skipped"',
        ),
        (
            "producer",
            "navigationPassedThrough: selectionNavigationPassedThrough",
            "navigationPassedThrough: true",
        ),
        (
            "patch",
            "+    if (view3d_select_async_navigation_event(event->type)) {",
            "+    if (false) {",
        ),
        ("series", PATCH.name, "0315-missing.patch"),
    )
    rejected = 0
    for key, old, new in mutations:
        mutated = dict(sources)
        mutated[key] = replace_once(mutated[key], old, new)
        try:
            validate(mutated)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0J_SELECT_NAVIGATION_PASSTHROUGH_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    sources = {
        "view3d_select": VIEW3D_SELECT.read_text(),
        "wm_event_system": WM_EVENT_SYSTEM.read_text(),
        "producer": PRODUCER.read_text(),
        "patch": PATCH.read_text() if PATCH.is_file() else "",
        "series": SERIES.read_text(),
    }
    try:
        self_check(sources) if args.self_check else validate(sources)
    except ValueError as error:
        print(f"P0J_SELECT_NAVIGATION_PASSTHROUGH_SOURCE_FAIL {error}")
        return 1
    if not args.self_check:
        print("P0J_SELECT_NAVIGATION_PASSTHROUGH_SOURCE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
