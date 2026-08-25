#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind Grease Pencil pixel/Delaunay fill to one owned depth-cache wait."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


DRAW_OPS = Path("source/blender/editors/sculpt_paint/grease_pencil/draw_ops.cc")
FILL = Path("source/blender/editors/sculpt_paint/grease_pencil/fill.cc")
HEADER = Path("source/blender/editors/include/ED_grease_pencil.hh")
RELATIVES = (DRAW_OPS, FILL, HEADER)


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


def verify(sources: dict[Path, str]) -> None:
    draw_ops = sources[DRAW_OPS]
    fill = sources[FILL]
    header = sources[HEADER]

    owner = braced_definition(draw_ops, "struct GreasePencilFillOpData", "fill owner")
    for token in (
        "std::optional<ed::greasepencil::DrawingPlacement> depth_cache_placement;",
        "std::optional<wmEvent> depth_cache_event;",
        "wmTimer *depth_cache_timer = nullptr;",
        "wmWindowManager *depth_cache_manager = nullptr;",
        "wmWindow *depth_cache_window = nullptr;",
        "bScreen *depth_cache_screen = nullptr;",
        "ScrArea *depth_cache_area = nullptr;",
        "ARegion *depth_cache_region = nullptr;",
        "RegionView3D *depth_cache_region_view = nullptr;",
        "View3D *depth_cache_view3d = nullptr;",
        "Depsgraph *depth_cache_depsgraph = nullptr;",
        "Scene *depth_cache_scene = nullptr;",
        "ViewLayer *depth_cache_view_layer = nullptr;",
        "Object *depth_cache_object = nullptr;",
        "GreasePencil *depth_cache_grease_pencil = nullptr;",
        "bke::greasepencil::Layer *depth_cache_layer = nullptr;",
        "Paint *depth_cache_paint = nullptr;",
        "Brush *depth_cache_brush = nullptr;",
        "int depth_cache_frame = 0;",
        "int depth_cache_tick_count = 0;",
        "bool depth_cache_pending = false;",
    ):
        require(token in owner, f"fill continuation ownership missing: {token}")

    wait_begin = braced_definition(
        draw_ops, "static bool grease_pencil_fill_depth_cache_wait_begin(", "wait begin"
    )
    for token in (
        "CTX_wm_manager(&C)",
        "CTX_wm_window(&C)",
        "CTX_wm_screen(&C)",
        "CTX_wm_area(&C)",
        "CTX_wm_region(&C)",
        "CTX_wm_region_view3d(&C)",
        "CTX_wm_view3d(&C)",
        "CTX_data_depsgraph_pointer(&C)",
        "CTX_data_scene(&C)",
        "CTX_data_view_layer(&C)",
        "CTX_data_active_object(&C)",
        "retained_event.next = nullptr;",
        "retained_event.prev = nullptr;",
        "retained_event.customdata = nullptr;",
        "retained_event.customdata_free = false;",
        "TIMER, 0.01f",
        "op_data.depth_cache_pending = true;",
    ):
        require(token in wait_begin, f"wait ownership missing: {token}")

    context = braced_definition(
        draw_ops,
        "static bool grease_pencil_fill_depth_cache_context_matches(",
        "producing-context guard",
    )
    for token in (
        "CTX_wm_manager(&C) != op_data.depth_cache_manager",
        "CTX_wm_window(&C) != op_data.depth_cache_window",
        "CTX_wm_screen(&C) != op_data.depth_cache_screen",
        "CTX_wm_area(&C) != op_data.depth_cache_area",
        "CTX_wm_region(&C) != op_data.depth_cache_region",
        "CTX_wm_region_view3d(&C) != op_data.depth_cache_region_view",
        "CTX_wm_view3d(&C) != op_data.depth_cache_view3d",
        "CTX_data_depsgraph_pointer(&C) != op_data.depth_cache_depsgraph",
        "CTX_data_scene(&C) != op_data.depth_cache_scene",
        "CTX_data_view_layer(&C) != op_data.depth_cache_view_layer",
        "CTX_data_active_object(&C) != op_data.depth_cache_object",
        "op_data.depth_cache_scene->r.cfra != op_data.depth_cache_frame",
        "grease_pencil->get_active_layer() != op_data.depth_cache_layer",
        "paint == op_data.depth_cache_paint",
        "BKE_paint_brush(paint) == op_data.depth_cache_brush",
    ):
        require(token in context, f"producing-context guard missing: {token}")

    clear = braced_definition(
        draw_ops, "static void grease_pencil_fill_depth_cache_clear(", "owned cleanup"
    )
    for token in (
        "grease_pencil_fill_depth_cache_timer_remove(op_data);",
        "op_data.depth_cache_placement->cancel_viewport_depths();",
        "op_data.depth_cache_placement.reset();",
        "op_data.depth_cache_event.reset();",
        "op_data.depth_cache_pending = false;",
    ):
        require(token in clear, f"owned cleanup missing: {token}")

    begin = braced_definition(
        draw_ops, "static wmOperatorStatus grease_pencil_fill_apply_or_defer(", "fill begin"
    )
    for token in (
        "BLI_rcti_isect_pt_v(&region.winrct, event.xy)",
        "op_data.depth_cache_placement.emplace(",
        "DEG_get_evaluated(&depsgraph, &object)",
        "grease_pencil->get_active_layer()",
        "cache_viewport_depths_async(",
        "DrawingPlacementDepthCacheState::Pending",
        "grease_pencil_fill_depth_cache_wait_begin(C, op_data, event)",
        "grease_pencil_apply_fill(C, op, event, *op_data.depth_cache_placement)",
    ):
        require(token in begin, f"fill begin missing: {token}")
    require("cache_viewport_depths(" not in begin, "fill begin retains synchronous readback")
    require(
        "DrawingPlacementDepthCacheState::Failed" not in begin,
        "initial read failure no longer follows stock projection fallback",
    )
    require(
        begin.find("cache_viewport_depths_async(")
        < begin.find("grease_pencil_apply_fill(C, op, event"),
        "fill work can run before depth-cache readiness",
    )

    poll = braced_definition(
        draw_ops, "static wmOperatorStatus grease_pencil_fill_depth_cache_poll(", "fill poll"
    )
    for token in (
        "grease_pencil_fill_depth_cache_context_matches(C, op_data)",
        "event.customdata != op_data.depth_cache_timer",
        "constexpr int max_tick_count = 240;",
        "++op_data.depth_cache_tick_count > max_tick_count",
        "poll_viewport_depths(op_data.depth_cache_region)",
        "DrawingPlacementDepthCacheState::Pending",
        "DrawingPlacementDepthCacheState::Failed",
        "op_data.depth_cache_pending = false;",
        "const wmEvent retained_event = *op_data.depth_cache_event;",
        "grease_pencil_apply_fill(",
        "C, op, retained_event, *op_data.depth_cache_placement",
    ):
        require(token in poll, f"fill settlement missing: {token}")
    require(
        poll.find("op_data.depth_cache_pending = false;")
        < poll.find("grease_pencil_apply_fill("),
        "ready settlement can recursively re-enter pending state",
    )

    modal = braced_definition(draw_ops, "static wmOperatorStatus grease_pencil_fill_modal(", "modal")
    for token in (
        "if (op_data.depth_cache_pending)",
        "grease_pencil_fill_depth_cache_poll(*C, *op, *event)",
        "grease_pencil_fill_apply_or_defer(*C, *op, *event)",
    ):
        require(token in modal, f"modal routing missing: {token}")
    require(
        modal.find("if (op_data.depth_cache_pending)")
        < modal.find("else if (!op_data.show_extension)"),
        "pending fill is not isolated before stock modal dispatch",
    )

    apply_fill = braced_definition(
        draw_ops, "static bool grease_pencil_apply_fill(", "ready-only fill"
    )
    require(
        "const ed::greasepencil::DrawingPlacement &fill_placement" in apply_fill,
        "ready-only fill does not require an owned placement",
    )
    for call in ("pixel_fill_strokes(view_context,", "delaunay_fill_strokes(view_context,"):
        call_at = apply_fill.find(call)
        require(call_at >= 0, f"missing ready-only helper call: {call}")
        require(
            "fill_placement" in apply_fill[call_at : call_at + 500],
            f"helper call does not consume the ready placement: {call}",
        )

    require(
        fill.count("const DrawingPlacement &placement") == 2,
        "pixel and Delaunay implementations do not both require caller-owned placement",
    )
    require(
        header.count("const DrawingPlacement &placement") == 3,
        "public helper declarations do not both require caller-owned placement",
    )
    require(
        "cache_viewport_depths(" not in fill,
        "fill helpers retain a synchronous viewport-depth cache read",
    )
    pixel = braced_definition(fill, "bke::CurvesGeometry pixel_fill_strokes(", "pixel fill")
    delaunay = braced_definition(
        fill,
        "std::optional<bke::CurvesGeometry> delaunay_fill_strokes(",
        "Delaunay fill",
    )
    for token in ("render_strokes(", "process_image(", "placement"):
        require(token in pixel, f"pixel ready semantics missing: {token}")
    for token in ("get_input_from_drawings(", "delaunay_2d_calc(input, CDT_FULL)", "placement"):
        require(token in delaunay, f"Delaunay ready semantics missing: {token}")


def load_sources(source_root: Path) -> dict[Path, str]:
    return {
        relative: (source_root / relative).read_text(encoding="utf-8")
        for relative in RELATIVES
    }


def combined_digest(sources: dict[Path, str]) -> str:
    digest = hashlib.sha256()
    for relative in RELATIVES:
        digest.update(relative.as_posix().encode("utf-8") + b"\0")
        digest.update(sources[relative].encode("utf-8"))
    return digest.hexdigest()


def selfcheck(sources: dict[Path, str]) -> int:
    mutations = (
        (DRAW_OPS, "cache_viewport_depths_async(", "cache_viewport_depths("),
        (DRAW_OPS, "constexpr int max_tick_count = 240;", "constexpr int max_tick_count = 0;"),
        (DRAW_OPS, "retained_event.customdata = nullptr;", "retained_event.customdata = event.customdata;"),
        (DRAW_OPS, "CTX_wm_region(&C) != op_data.depth_cache_region", "false /* region drift */"),
        (DRAW_OPS, "op_data.depth_cache_placement->cancel_viewport_depths();", "/* no cancel */"),
        (DRAW_OPS, "if (op_data.depth_cache_pending)", "if (false)"),
        (DRAW_OPS, "event.customdata != op_data.depth_cache_timer", "false /* foreign timer */"),
        (DRAW_OPS, "C, op, retained_event, *op_data.depth_cache_placement", "C, op, retained_event, {}"),
        (FILL, "const DrawingPlacement &placement", "const int placement", 1),
        (FILL, "delaunay_2d_calc(input, CDT_FULL)", "delaunay_2d_calc(input, CDT_INSIDE)"),
        (HEADER, "const DrawingPlacement &placement", "const int placement", 1),
        (FILL, "BLI_assert(view_context.obact->type == OB_GREASE_PENCIL);", "placement.cache_viewport_depths(nullptr, nullptr, nullptr);"),
    )
    rejected = 0
    for mutation in mutations:
        relative, old, new, *count = mutation
        require(old in sources[relative], f"self-check mutation anchor missing: {old}")
        changed = dict(sources)
        changed[relative] = sources[relative].replace(old, new, count[0] if count else -1)
        try:
            verify(changed)
        except VerificationError:
            rejected += 1
    require(rejected == len(mutations), f"self-check rejected {rejected}/{len(mutations)} mutations")
    return rejected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    sources = load_sources(args.source_root.resolve())
    verify(sources)
    mutations = selfcheck(sources) if args.selfcheck else 0
    receipt = {
        "schema": "blender-web-m5-grease-pencil-fill-depth-cache-v1",
        "verdict": "PASS",
        "source_sha256": combined_digest(sources),
        "source_paths": [relative.as_posix() for relative in RELATIVES],
        "converted_callers": ["pixel_fill", "delaunay_fill"],
        "remaining_grease_pencil_callers": ["pen-helper"],
        "remaining_sync_families": ["depth_cache", "window_capture"],
        "mutation_controls": mutations,
        "contracts": {
            "operation_owned_request": True,
            "native_immediate_and_initial_fallback": True,
            "pre_result_suspension": True,
            "pixel_and_delaunay_ready_only": True,
            "retained_fill_point": True,
            "producing_context_guard": True,
            "bounded_identified_poll": True,
            "failure_timeout_cancellation": True,
            "live_hardware_receipt": False,
        },
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, VerificationError) as error:
        print(f"M5_GREASE_PENCIL_FILL_DEPTH_CACHE_SOURCE_FAIL {error}", file=__import__("sys").stderr)
        raise SystemExit(1)
