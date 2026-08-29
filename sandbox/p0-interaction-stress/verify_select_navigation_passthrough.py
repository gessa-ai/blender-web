#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Require pending browser selection continuations to leave later event owners responsive."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VIEW3D_SELECT = ROOT / "upstream/source/blender/editors/space_view3d/view3d_select.cc"
WM_EVENT_SYSTEM = ROOT / "upstream/source/blender/windowmanager/intern/wm_event_system.cc"
SCREENDUMP = ROOT / "upstream/source/blender/editors/screen/screendump.cc"
VIEW3D_EDIT = ROOT / "upstream/source/blender/editors/space_view3d/view3d_edit.cc"
VIEW3D_NAVIGATE = ROOT / "upstream/source/blender/editors/space_view3d/view3d_navigate.cc"
VIEW_CENTER = (
    ROOT / "upstream/source/blender/editors/space_view3d/view3d_navigate_view_center_pick.cc"
)
ZOOM_BORDER = (
    ROOT / "upstream/source/blender/editors/space_view3d/view3d_navigate_zoom_border.cc"
)
VIEW_NDOF = ROOT / "upstream/source/blender/editors/space_view3d/view3d_navigate_view_ndof.cc"
PRODUCER = ROOT / "sandbox/p0-interaction-stress/rapid_freeze_repro.mjs"
NAVIGATION_PATCH = ROOT / "patches/0315-view3d-web-selection-navigation-passthrough.patch"
EVENT_PATCH = ROOT / "patches/0317-view3d-web-selection-unrelated-event-passthrough.patch"
GESTURE_PATCH = ROOT / "patches/0318-view3d-web-gesture-selection-passthrough.patch"
SIBLING_PATCH = ROOT / "patches/0319-web-async-modal-event-passthrough.patch"
MOTION_PATCH = ROOT / "patches/0320-view3d-web-selection-navigation-motion-order.patch"
TAIL_RESET_PATCH = ROOT / "patches/0321-view3d-web-selection-navigation-tail-reset.patch"
SERIES = ROOT / "patches/series"


def require(source: str, token: str, count: int = 1) -> None:
    if source.count(token) != count:
        raise ValueError(f"expected {count} occurrence(s) of {token!r}")


def definition(source: str, marker: str) -> str:
    if source.count(marker) != 1:
        raise ValueError(f"expected one definition marker {marker!r}")
    start = source.index(marker)
    brace = source.find("{", start + len(marker))
    if brace < 0:
        raise ValueError(f"opening brace missing after {marker!r}")
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise ValueError(f"unterminated definition after {marker!r}")


def async_combined_passthrough_census(sources: dict[str, str]) -> int:
    """Allow combined modal/pass-through only where the continuation owns the event."""
    combined_return = re.compile(
        r"return\s+\(?OPERATOR_RUNNING_MODAL\s*\|\s*OPERATOR_PASS_THROUGH\)?;"
    )
    expected_counts = {
        "view3d_select": 0,
        "screendump": 0,
        "view3d_edit": 1,
        "view3d_navigate": 1,
        "view_center": 0,
        "zoom_border": 0,
        "view_ndof": 0,
    }
    actual_counts = {
        key: len(combined_return.findall(sources[key])) for key in expected_counts
    }
    if actual_counts != expected_counts:
        raise ValueError(
            "browser async combined pass-through census differs: "
            f"expected={expected_counts} actual={actual_counts}"
        )

    cursor_invoke = definition(
        sources["view3d_edit"], "static wmOperatorStatus view3d_cursor3d_invoke("
    )
    navigation_modal = definition(
        sources["view3d_navigate"], "static wmOperatorStatus view3d_navigation_depth_modal("
    )
    if len(combined_return.findall(cursor_invoke)) != 1:
        raise ValueError("cursor invoke lost its owned click-drag combined return")
    if len(combined_return.findall(navigation_modal)) != 1:
        raise ValueError("navigation continuation lost its owned queued-event combined return")
    return sum(actual_counts.values())


def validate(sources: dict[str, str]) -> int:
    view3d_select = sources["view3d_select"]
    wm_event_system = sources["wm_event_system"]
    producer = sources["producer"]
    navigation_patch = sources["navigation_patch"]
    event_patch = sources["event_patch"]
    gesture_patch = sources["gesture_patch"]
    sibling_patch = sources["sibling_patch"]
    motion_patch = sources["motion_patch"]
    tail_reset_patch = sources["tail_reset_patch"]
    series = sources["series"]

    require(view3d_select, "  bool navigation_active = false;\n")
    helper = (
        "static bool view3d_select_async_navigation_event(View3DSelectAsyncData *data,\n"
        "                                                 const wmEvent *event)\n"
        "{\n"
        "  if (event->type == MIDDLEMOUSE) {\n"
        "    data->navigation_active = event->val != KM_RELEASE;\n"
        "    return true;\n"
        "  }\n"
        "  if (ISMOUSE_MOTION(event->type)) {\n"
        "    return data->navigation_active;\n"
        "  }\n"
        "  if (ISMOUSE_WHEEL(event->type) || ISMOUSE_GESTURE(event->type) ||\n"
        "      ISKEYMODIFIER(event->type) || ISNDOF(event->type))\n"
        "  {\n"
        "    return true;\n"
        "  }\n"
        "  /* A later modal handler can consume the MMB release after selection passed the gesture\n"
        "   * through. The next ordinary event starts a new ownership tail even when that release was not\n"
        "   * observable here, so its following pointer motion must remain ordered in the replay FIFO. */\n"
        "  data->navigation_active = false;\n"
        "  return false;\n"
        "}"
    )
    require(view3d_select, helper)
    route = (
        "if (view3d_select_async_navigation_event(data, event)) {\n"
        "      return OPERATOR_PASS_THROUGH;\n"
        "    }"
    )
    require(view3d_select, route)
    custom_route = (
        "if (ISTIMER(event->type) || event->customdata != nullptr) {\n"
        "      return OPERATOR_PASS_THROUGH;\n"
        "    }"
    )
    require(view3d_select, custom_route)
    particle_gesture_route = (
        "if (data == nullptr || data->particle_depth_session == nullptr || event->type != TIMER ||\n"
        "      event->customdata != data->timer)\n"
        "  {\n"
        "    return OPERATOR_PASS_THROUGH;\n"
        "  }"
    )
    require(view3d_select, particle_gesture_route)
    bitmap_gesture_route = (
        "if (data == nullptr || event->type != TIMER || event->customdata != data->timer) {\n"
        "    return OPERATOR_PASS_THROUGH;\n"
        "  }"
    )
    require(view3d_select, bitmap_gesture_route)

    sibling_modals = (
        (
            "screendump",
            "static wmOperatorStatus screenshot_modal(",
            "if (scd == nullptr || event->type != TIMER || event->customdata != "
            "scd->readback_timer) {\n"
            "    return OPERATOR_PASS_THROUGH;\n"
            "  }",
            "if (scd->readback_tick_count < max_tick_count) {\n"
            "      return OPERATOR_RUNNING_MODAL;\n"
            "    }",
        ),
        (
            "view3d_edit",
            "static wmOperatorStatus view3d_cursor3d_modal(",
            "if (event->type != TIMER || event->customdata != read->timer) {\n"
            "    return OPERATOR_PASS_THROUGH;\n"
            "  }",
            "if (state == ViewportDepthPickSession::ReadbackState::Pending) {\n"
            "    return OPERATOR_RUNNING_MODAL;\n"
            "  }",
        ),
        (
            "view_center",
            "static wmOperatorStatus viewcenter_pick_modal(",
            "if (event->type != TIMER || event->customdata != read->timer) {\n"
            "    return OPERATOR_PASS_THROUGH;\n"
            "  }",
            "if (state == ViewportDepthPickSession::ReadbackState::Pending) {\n"
            "    return OPERATOR_RUNNING_MODAL;\n"
            "  }",
        ),
        (
            "zoom_border",
            "static wmOperatorStatus view3d_zoom_border_modal(",
            "if (event->type != TIMER || event->customdata != read->timer) {\n"
            "    return OPERATOR_PASS_THROUGH;\n"
            "  }",
            "if (status == GPU_READBACK_PENDING) {\n"
            "    return OPERATOR_RUNNING_MODAL;\n"
            "  }",
        ),
        (
            "view_ndof",
            "wmOperatorStatus view3d_ndof_depth_modal(",
            "if (event->type != TIMER || event->customdata != read->timer) {\n"
            "    return OPERATOR_PASS_THROUGH;\n"
            "  }",
            "if (status == GPU_READBACK_PENDING) {\n"
            "    return OPERATOR_RUNNING_MODAL;\n"
            "  }",
        ),
    )
    for source_key, marker, pass_route, owned_route in sibling_modals:
        modal = definition(sources[source_key], marker)
        require(modal, pass_route)
        require(modal, owned_route)
    cursor_invoke = definition(
        sources["view3d_edit"], "static wmOperatorStatus view3d_cursor3d_invoke("
    )
    require(cursor_invoke, "return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;")
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
        'const selectionPendingWindow = await sampleSparseCadence(',
        'const selectionNavigationWindow = await sampleSparseCadence(',
        '"isolated-selection-navigation-passthrough"',
        'selectionDrain = await waitForActionDrain(',
        '"isolated-selection-drain",\n      selectionNavigationWindow.sha256,',
        "\n    selectionNavigationPassedThrough =\n",
        "navigationPassedThrough: selectionNavigationPassedThrough",
        "selectionNavigationPassthroughRequired,",
        "\n    selectionNavigationPassedThrough,\n    actionDrainMs:",
        "selectionNavigationWindow.selectionContinuation.active === 1",
    ):
        require(producer, token)
    for token in (
        'await page.keyboard.press("g");',
        'await page.mouse.click(center.x + 40, center.y - 20);',
    ):
        require(producer, token, 2)
    require(producer, 'await page.mouse.move(center.x + 40, center.y - 20, {steps: 8});')
    transform_marker = "Match the driver's complete slow/sparse tail."
    require(producer, transform_marker)
    require(
        producer,
        "const nativeSelectionReplayComplete = (current, baseline) =>\n"
        "    current.selectionSync.syncLoops > baseline.selectionSync.syncLoops &&\n"
        "    current.selectionSync.completedLoops > baseline.selectionSync.completedLoops &&\n"
        "    current.nativeStateSequence > baseline.nativeStateSequence &&\n"
        "    baseline.nativeState?.selected_count === 0 && nativeCubeSelected(current) &&\n"
        "    nativeViewChanged(current, baseline) &&\n"
        "    stateArrayChanged(current.nativeState?.location, baseline.nativeState?.location);",
    )
    require(producer, "\n    selectionNavigationPassthroughRequired =\n", 2)
    sparse_start = producer.index("if (sparseDiagnostic) {")
    sparse_drain = producer.index("selectionDrain = await waitForActionDrain(", sparse_start)
    if "waitForActionDrain(" in producer[sparse_start:sparse_drain]:
        raise ValueError("fixed-cadence sparse input still waits for an intermediate drain")
    if "retainedReplayExercised" in producer:
        raise ValueError("hardware producer still requires the navigation gesture to be replayed")
    if not (
        producer.index('"isolated-selection-pending"')
        < producer.index('"isolated-selection-navigation-passthrough"')
        < producer.index(transform_marker)
        < producer.index('"isolated-selection-drain"')
    ):
        raise ValueError("slow/sparse producer lost selection -> live navigation -> settle order")

    require(
        navigation_patch,
        "diff --git a/source/blender/editors/space_view3d/view3d_select.cc "
        "b/source/blender/editors/space_view3d/view3d_select.cc",
    )
    for token in (
        "+static bool view3d_select_async_navigation_event(const short event_type)",
        "+    if (view3d_select_async_navigation_event(event->type)) {",
        "+      return OPERATOR_PASS_THROUGH;",
    ):
        require(navigation_patch, token)
    require(
        event_patch,
        "diff --git a/source/blender/editors/space_view3d/view3d_select.cc "
        "b/source/blender/editors/space_view3d/view3d_select.cc",
    )
    for token in (
        "-      return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;",
        "+      return OPERATOR_PASS_THROUGH;",
    ):
        require(event_patch, token)
    for token in (
        "view3d_particle_gesture_async_modal",
        "view3d_gesture_bitmap_async_modal",
    ):
        require(gesture_patch, token)
    require(gesture_patch, "-    return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;", 2)
    require(gesture_patch, "+    return OPERATOR_PASS_THROUGH;", 2)
    require(sibling_patch, "-    return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;", 8)
    require(sibling_patch, "+    return OPERATOR_PASS_THROUGH;", 5)
    require(sibling_patch, "+    return OPERATOR_RUNNING_MODAL;", 3)
    for relative in (
        "source/blender/editors/screen/screendump.cc",
        "source/blender/editors/space_view3d/view3d_edit.cc",
        "source/blender/editors/space_view3d/view3d_navigate_view_center_pick.cc",
        "source/blender/editors/space_view3d/view3d_navigate_zoom_border.cc",
        "source/blender/editors/space_view3d/view3d_navigate_view_ndof.cc",
    ):
        require(sibling_patch, f"diff --git a/{relative} b/{relative}")
    for token in (
        "+  bool navigation_active = false;",
        "+    data->navigation_active = event->val != KM_RELEASE;",
        "+    return data->navigation_active;",
        "+    if (view3d_select_async_navigation_event(data, event)) {",
    ):
        require(motion_patch, token)
    for token in (
        "diff --git a/source/blender/editors/space_view3d/view3d_select.cc "
        "b/source/blender/editors/space_view3d/view3d_select.cc",
        "+  data->navigation_active = false;",
        "+  return false;",
    ):
        require(tail_reset_patch, token)
    require(series, NAVIGATION_PATCH.name)
    require(series, EVENT_PATCH.name)
    require(series, GESTURE_PATCH.name)
    require(series, SIBLING_PATCH.name)
    require(series, MOTION_PATCH.name)
    require(series, TAIL_RESET_PATCH.name)
    return async_combined_passthrough_census(sources)


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return source.replace(old, new, 1)


def self_check(sources: dict[str, str]) -> None:
    async_combined = validate(sources)
    mutations = (
        (
            "view3d_select",
            "data->navigation_active = event->val != KM_RELEASE;",
            "data->navigation_active = true;",
        ),
        (
            "view3d_select",
            "    return data->navigation_active;",
            "    return true;",
        ),
        (
            "view3d_select",
            "  data->navigation_active = false;\n  return false;",
            "  return false;",
        ),
        (
            "view3d_select",
            "if (view3d_select_async_navigation_event(data, event)) {",
            "if (false && view3d_select_async_navigation_event(data, event)) {",
        ),
        (
            "view3d_select",
            "      return OPERATOR_PASS_THROUGH;\n    }\n    if (!view3d_select_async_event_push",
            "      return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n"
            "    }\n    if (!view3d_select_async_event_push",
        ),
        (
            "view3d_select",
            "if (ISTIMER(event->type) || event->customdata != nullptr) {\n"
            "      return OPERATOR_PASS_THROUGH;\n"
            "    }",
            "if (ISTIMER(event->type) || event->customdata != nullptr) {\n"
            "      return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n"
            "    }",
        ),
        (
            "view3d_select",
            "if (data == nullptr || data->particle_depth_session == nullptr || "
            "event->type != TIMER ||\n"
            "      event->customdata != data->timer)\n"
            "  {\n"
            "    return OPERATOR_PASS_THROUGH;\n"
            "  }",
            "if (data == nullptr || data->particle_depth_session == nullptr || "
            "event->type != TIMER ||\n"
            "      event->customdata != data->timer)\n"
            "  {\n"
            "    return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n"
            "  }",
        ),
        (
            "view3d_navigate",
            "    return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n",
            "    return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n"
            "    return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n",
        ),
        (
            "screendump",
            "if (scd == nullptr || event->type != TIMER || event->customdata != "
            "scd->readback_timer) {\n"
            "    return OPERATOR_PASS_THROUGH;\n"
            "  }",
            "if (scd == nullptr || event->type != TIMER || event->customdata != "
            "scd->readback_timer) {\n"
            "    return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n"
            "  }",
        ),
        (
            "view3d_edit",
            "if (event->type != TIMER || event->customdata != read->timer) {\n"
            "    return OPERATOR_PASS_THROUGH;\n"
            "  }",
            "if (event->type != TIMER || event->customdata != read->timer) {\n"
            "    return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n"
            "  }",
        ),
        (
            "view_center",
            "if (state == ViewportDepthPickSession::ReadbackState::Pending) {\n"
            "    return OPERATOR_RUNNING_MODAL;\n"
            "  }",
            "if (state == ViewportDepthPickSession::ReadbackState::Pending) {\n"
            "    return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n"
            "  }",
        ),
        (
            "zoom_border",
            "if (event->type != TIMER || event->customdata != read->timer) {\n"
            "    return OPERATOR_PASS_THROUGH;\n"
            "  }",
            "if (event->type != TIMER || event->customdata != read->timer) {\n"
            "    return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n"
            "  }",
        ),
        (
            "view_ndof",
            "if (event->type != TIMER || event->customdata != read->timer) {\n"
            "    return OPERATOR_PASS_THROUGH;\n"
            "  }",
            "if (event->type != TIMER || event->customdata != read->timer) {\n"
            "    return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n"
            "  }",
        ),
        (
            "view3d_select",
            "if (data == nullptr || event->type != TIMER || event->customdata != data->timer) {\n"
            "    return OPERATOR_PASS_THROUGH;\n"
            "  }",
            "if (data == nullptr || event->type != TIMER || event->customdata != data->timer) {\n"
            "    return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n"
            "  }",
        ),
        (
            "producer",
            '"isolated-selection-navigation-passthrough"',
            '"isolated-selection-navigation-skipped"',
        ),
        (
            "producer",
            "const selectionNavigationWindow = await sampleSparseCadence(",
            "const selectionNavigationWindow = await waitForActionDrain(",
        ),
        (
            "producer",
            "navigationPassedThrough: selectionNavigationPassedThrough",
            "navigationPassedThrough: true",
        ),
        (
            "navigation_patch",
            "+    if (view3d_select_async_navigation_event(event->type)) {",
            "+    if (false) {",
        ),
        (
            "event_patch",
            "+      return OPERATOR_PASS_THROUGH;",
            "+      return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;",
        ),
        ("series", NAVIGATION_PATCH.name, "0315-missing.patch"),
        ("series", EVENT_PATCH.name, "0317-missing.patch"),
        ("gesture_patch", "view3d_particle_gesture_async_modal", "missing_particle_modal"),
        ("series", GESTURE_PATCH.name, "0318-missing.patch"),
        (
            "sibling_patch",
            "diff --git a/source/blender/editors/screen/screendump.cc "
            "b/source/blender/editors/screen/screendump.cc",
            "diff --git a/source/blender/editors/screen/screendump.cc "
            "b/source/blender/editors/screen/screendump-lost.cc",
        ),
        ("series", SIBLING_PATCH.name, "0319-missing.patch"),
        (
            "motion_patch",
            "+    return data->navigation_active;",
            "+    return true;",
        ),
        ("series", MOTION_PATCH.name, "0320-missing.patch"),
        (
            "tail_reset_patch",
            "+  data->navigation_active = false;",
            "+  data->navigation_active = true;",
        ),
        ("series", TAIL_RESET_PATCH.name, "0321-missing.patch"),
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
    print(
        "P0J_SELECT_NAVIGATION_PASSTHROUGH_SELFCHECK_PASS "
        f"mutations={rejected} async_combined={async_combined}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    sources = {
        "view3d_select": VIEW3D_SELECT.read_text(),
        "wm_event_system": WM_EVENT_SYSTEM.read_text(),
        "screendump": SCREENDUMP.read_text(),
        "view3d_edit": VIEW3D_EDIT.read_text(),
        "view3d_navigate": VIEW3D_NAVIGATE.read_text(),
        "view_center": VIEW_CENTER.read_text(),
        "zoom_border": ZOOM_BORDER.read_text(),
        "view_ndof": VIEW_NDOF.read_text(),
        "producer": PRODUCER.read_text(),
        "navigation_patch": NAVIGATION_PATCH.read_text() if NAVIGATION_PATCH.is_file() else "",
        "event_patch": EVENT_PATCH.read_text() if EVENT_PATCH.is_file() else "",
        "gesture_patch": GESTURE_PATCH.read_text() if GESTURE_PATCH.is_file() else "",
        "sibling_patch": SIBLING_PATCH.read_text() if SIBLING_PATCH.is_file() else "",
        "motion_patch": MOTION_PATCH.read_text() if MOTION_PATCH.is_file() else "",
        "tail_reset_patch": TAIL_RESET_PATCH.read_text() if TAIL_RESET_PATCH.is_file() else "",
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
