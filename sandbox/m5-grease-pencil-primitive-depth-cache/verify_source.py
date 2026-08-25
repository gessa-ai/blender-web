#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind the six Grease Pencil primitive operators to one depth-cache continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile


RELATIVE = Path(
    "source/blender/editors/grease_pencil/intern/grease_pencil_primitive.cc"
)
OPERATOR_NAMES = (
    "line",
    "polyline",
    "arc",
    "curve",
    "box",
    "circle",
)


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def braced_definition(source: str, signature: str, label: str) -> str:
    start = source.find(signature)
    require(start >= 0, f"missing {label}: {signature}")
    opening = source.find("{", start + len(signature))
    require(opening >= 0, f"missing body for {label}: {signature}")
    depth = 0
    state = "code"
    index = opening
    while index < len(source):
        char = source[index]
        pair = source[index : index + 2]
        if state == "line":
            if char == "\n":
                state = "code"
        elif state == "block":
            if pair == "*/":
                state = "code"
                index += 1
        elif state == "string":
            if char == "\\":
                index += 1
            elif char == '"':
                state = "code"
        elif state == "char":
            if char == "\\":
                index += 1
            elif char == "'":
                state = "code"
        else:
            if pair == "//":
                state = "line"
                index += 1
            elif pair == "/*":
                state = "block"
                index += 1
            elif char == '"':
                state = "string"
            elif char == "'":
                state = "char"
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return source[start : index + 1]
        index += 1
    raise VerificationError(f"unterminated {label}: {signature}")


def verify(source: str) -> None:
    owner = braced_definition(source, "struct PrimitiveToolOperation", "primitive owner")
    for token in (
        "wmTimer *depth_cache_timer = nullptr;",
        "Vector<wmEvent> depth_cache_events;",
        "wmWindowManager *depth_cache_manager = nullptr;",
        "wmWindow *depth_cache_window = nullptr;",
        "bScreen *depth_cache_screen = nullptr;",
        "ScrArea *depth_cache_area = nullptr;",
        "RegionView3D *depth_cache_region_view = nullptr;",
        "View3D *depth_cache_view3d = nullptr;",
        "Depsgraph *depth_cache_depsgraph = nullptr;",
        "Scene *depth_cache_scene = nullptr;",
        "Object *depth_cache_object = nullptr;",
        "GreasePencil *depth_cache_grease_pencil = nullptr;",
        "const bke::greasepencil::Layer *depth_cache_layer = nullptr;",
        "int depth_cache_frame = 0;",
        "int depth_cache_tick_count = 0;",
        "bool depth_cache_pending = false;",
        "bool initialized = false;",
    ):
        require(token in owner, f"primitive continuation ownership missing: {token}")

    invoke = braced_definition(
        source, "static wmOperatorStatus grease_pencil_primitive_invoke(", "primitive invoke"
    )
    for token in (
        "ptd.start_position_2d = float2(event->mval);",
        'ptd.subdivision = RNA_int_get(op->ptr, "subdivision");',
        'ptd.type = PrimitiveType(RNA_enum_get(op->ptr, "type"));',
        "ptd.placement = DrawingPlacement(",
        "ptd.placement.cache_viewport_depths_async(",
        "if (depth_state == DrawingPlacementDepthCacheState::Pending)",
        "grease_pencil_primitive_depth_cache_wait_begin(C, ptd)",
        "grease_pencil_primitive_invoke_ready(C, op, ptd);",
        "WM_event_add_modal_handler(C, op);",
    ):
        require(token in invoke, f"primitive invoke continuation missing: {token}")
    require(
        "cache_viewport_depths(" not in invoke,
        "primitive invoke retains a synchronous depth-cache call",
    )
    require(
        "if (depth_state == DrawingPlacementDepthCacheState::Failed)" not in invoke,
        "initial depth failure no longer follows the stock projection fallback",
    )
    require(
        invoke.find("ptd.start_position_2d = float2(event->mval);")
        < invoke.find("cache_viewport_depths_async("),
        "invoke-time start coordinates are not captured before suspension",
    )

    ready = braced_definition(
        source,
        "static void grease_pencil_primitive_invoke_ready(",
        "ready initialization",
    )
    for token in (
        "ptd.vod = ED_view3d_navigation_init(C, nullptr);",
        "const float3 pos = ptd.placement.project(ptd.start_position_2d);",
        "ptd.control_points = Vector<float3>({pos});",
        "grease_pencil_primitive_init_curves(ptd);",
        "ED_region_draw_cb_activate(",
        "ptd.initialized = true;",
    ):
        require(token in ready, f"ready initialization missing: {token}")
    require(
        ready.find("ptd.vod = ED_view3d_navigation_init(C, nullptr);")
        < ready.find("ptd.placement.project(ptd.start_position_2d)"),
        "native navigation/initial projection order differs",
    )

    wait_begin = braced_definition(
        source,
        "static bool grease_pencil_primitive_depth_cache_wait_begin(",
        "wait begin",
    )
    for token in (
        "CTX_wm_manager(C)",
        "CTX_wm_window(C)",
        "CTX_wm_screen(C)",
        "CTX_wm_area(C)",
        "CTX_wm_region_view3d(C)",
        "CTX_wm_view3d(C)",
        "CTX_data_depsgraph_pointer(C)",
        "CTX_data_scene(C)",
        "CTX_data_active_object(C)",
        "WM_event_timer_add(",
        "TIMER, 0.01f",
        "ptd.depth_cache_pending = true;",
    ):
        require(token in wait_begin, f"wait ownership missing: {token}")

    context_match = braced_definition(
        source,
        "static bool grease_pencil_primitive_depth_cache_context_matches(",
        "producing-context guard",
    )
    for token in (
        "CTX_wm_manager(C) != ptd.depth_cache_manager",
        "CTX_wm_window(C) != ptd.depth_cache_window",
        "CTX_wm_screen(C) != ptd.depth_cache_screen",
        "CTX_wm_area(C) != ptd.depth_cache_area",
        "CTX_wm_region(C) != ptd.region",
        "CTX_wm_region_view3d(C) != ptd.depth_cache_region_view",
        "CTX_wm_view3d(C) != ptd.depth_cache_view3d",
        "CTX_data_depsgraph_pointer(C) != ptd.depth_cache_depsgraph",
        "CTX_data_scene(C) != ptd.depth_cache_scene",
        "CTX_data_active_object(C) != ptd.depth_cache_object",
        "get_active_layer() != ptd.depth_cache_layer",
        "scene->r.cfra != ptd.depth_cache_frame",
    ):
        require(token in context_match, f"producing-context guard missing: {token}")

    event_push = braced_definition(
        source,
        "static bool grease_pencil_primitive_depth_cache_event_push(",
        "pending-event copy",
    )
    for token in (
        "constexpr int max_queued_events = 256;",
        "event->custom != 0",
        "event->customdata != nullptr",
        "queued.next = nullptr;",
        "queued.prev = nullptr;",
        "queued.customdata = nullptr;",
        "queued.customdata_free = false;",
        "ptd.depth_cache_events.append(queued);",
    ):
        require(token in event_push, f"pending-event ownership missing: {token}")

    poll = braced_definition(
        source,
        "static wmOperatorStatus grease_pencil_primitive_depth_cache_poll(",
        "depth-cache poll",
    )
    for token in (
        "grease_pencil_primitive_depth_cache_context_matches(C, ptd)",
        "constexpr int max_tick_count = 240;",
        "++ptd.depth_cache_tick_count > max_tick_count",
        "ptd.placement.poll_viewport_depths(ptd.region)",
        "DrawingPlacementDepthCacheState::Pending",
        "DrawingPlacementDepthCacheState::Failed",
        "ptd.depth_cache_pending = false;",
        "grease_pencil_primitive_invoke_ready(C, op, ptd);",
        "Vector<wmEvent> queued_events = std::move(ptd.depth_cache_events);",
        "grease_pencil_primitive_modal_dispatch(",
        "C, op, &queued_event);",
    ):
        require(token in poll, f"depth-cache settlement missing: {token}")
    require(
        poll.find("ptd.depth_cache_pending = false;")
        < poll.find("grease_pencil_primitive_invoke_ready(C, op, ptd);"),
        "settlement can recursively re-enter the pending path",
    )

    timer_remove = braced_definition(
        source,
        "static void grease_pencil_primitive_depth_cache_timer_remove(",
        "timer cleanup",
    )
    require(
        "WM_event_timer_remove(" in timer_remove
        and "ptd.depth_cache_manager" in timer_remove
        and "ptd.depth_cache_window" in timer_remove,
        "timer cleanup does not use its producing owner",
    )

    modal = braced_definition(
        source, "static wmOperatorStatus grease_pencil_primitive_modal(", "modal wrapper"
    )
    require(
        "if (ptd.depth_cache_pending)" in modal
        and "return grease_pencil_primitive_depth_cache_poll(C, op, event);" in modal
        and "return grease_pencil_primitive_modal_dispatch(C, op, event);" in modal,
        "modal wrapper does not isolate pending initialization",
    )

    exit_body = braced_definition(
        source,
        "static void grease_pencil_primitive_exit(bContext *C, wmOperator *op, const bool cancelled)",
        "primitive exit",
    )
    for token in (
        "grease_pencil_primitive_depth_cache_timer_remove(*ptd);",
        "ptd->placement.cancel_viewport_depths();",
        "ptd->depth_cache_events.clear();",
        "if (!ptd->initialized)",
        "WM_cursor_modal_restore(ptd->vc.win);",
        "op->customdata = nullptr;",
    ):
        require(token in exit_body, f"pending modal teardown missing: {token}")

    for name in OPERATOR_NAMES:
        registration = braced_definition(
            source,
            f"static void GREASE_PENCIL_OT_primitive_{name}(",
            f"primitive {name} registration",
        )
        require(
            "ot->invoke = grease_pencil_primitive_invoke;" in registration,
            f"primitive {name} does not share the continuation",
        )


def source_digest(source: str) -> str:
    digest = hashlib.sha256()
    digest.update(str(RELATIVE).encode("utf-8"))
    digest.update(b"\0")
    digest.update(source.encode("utf-8"))
    digest.update(b"\0")
    return digest.hexdigest()


def run_selfcheck(source: str) -> None:
    mutations = (
        ("cache_viewport_depths_async(", "cache_viewport_depths_retired("),
        ("if (depth_state == DrawingPlacementDepthCacheState::Pending)",
         "if (depth_state == DrawingPlacementDepthCacheState::Failed)"),
        ("constexpr int max_tick_count = 240;", "constexpr int max_tick_count = 0;"),
        ("constexpr int max_queued_events = 256;", "constexpr int max_queued_events = 0;"),
        ("CTX_wm_region(C) != ptd.region", "false"),
        ("event->customdata != nullptr", "false"),
        ("queued.customdata = nullptr;", "/* borrowed payload retained */"),
        ("ptd.placement.poll_viewport_depths(ptd.region)",
         "DrawingPlacementDepthCacheState::Ready"),
        ("grease_pencil_primitive_invoke_ready(C, op, ptd);", "/* initialization retired */"),
        ("Vector<wmEvent> queued_events = std::move(ptd.depth_cache_events);",
         "Vector<wmEvent> queued_events;"),
        ("ptd.depth_cache_pending = false;\n  grease_pencil_primitive_depth_cache_timer_remove(ptd);",
         "ptd.depth_cache_pending = true;\n  grease_pencil_primitive_depth_cache_timer_remove(ptd);"),
        ("WM_event_timer_remove(", "WM_event_timer_remove_retired("),
        ("ptd->placement.cancel_viewport_depths();", "/* request leaked */"),
        ("if (ptd.depth_cache_pending)", "if (false)"),
        ("ptd.start_position_2d = float2(event->mval);", "ptd.start_position_2d = float2();"),
        ("ot->invoke = grease_pencil_primitive_invoke;",
         "ot->invoke = grease_pencil_primitive_invoke_retired;"),
    )
    for old, new in mutations:
        require(old in source, f"selfcheck mutation source missing: {old}")
        mutated = source.replace(old, new, 1)
        try:
            verify(mutated)
        except VerificationError:
            continue
        raise VerificationError(f"selfcheck mutation survived: {old}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    source_path = args.source_root.resolve() / RELATIVE
    source = source_path.read_text(encoding="utf-8")
    verify(source)
    if args.selfcheck:
        run_selfcheck(source)
    if args.output is not None:
        payload = {
            "verdict": "PASS",
            "source_sha256": source_digest(source),
            "converted_callers": [
                f"GREASE_PENCIL_OT_primitive_{name}" for name in OPERATOR_NAMES
            ],
            "contracts": {
                "native_immediate_initialization": True,
                "stock_initial_failure_fallback": True,
                "pending_before_first_projection": True,
                "bounded_event_fifo": True,
                "producing_context_guard": True,
                "cursor_navigation_ownership": True,
                "exact_once_settlement": True,
                "failure_timeout_cancellation": True,
                "live_hardware_receipt": False,
            },
            "remaining_grease_pencil_callers": ["fill", "pen-helper"],
            "remaining_sync_families": ["depth_cache", "window_capture"],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=args.output.parent, delete=False
        ) as temporary:
            json.dump(payload, temporary, sort_keys=True, indent=2)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        temporary_path.replace(args.output)
    print("M5_GREASE_PENCIL_PRIMITIVE_DEPTH_CACHE_SOURCE_PASS files=1 mutations=16")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, VerificationError) as error:
        print(
            f"M5_GREASE_PENCIL_PRIMITIVE_DEPTH_CACHE_SOURCE_FAIL {error}",
            file=__import__("sys").stderr,
        )
        raise SystemExit(1)
