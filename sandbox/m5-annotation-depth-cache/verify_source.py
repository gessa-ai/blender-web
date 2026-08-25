#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed source contract for annotation depth-cache ownership."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


RELATIVE = Path("source/blender/editors/gpencil_legacy/annotate_paint.cc")


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def definition(source: str, name: str) -> str:
    match = None
    brace = -1
    for candidate in re.finditer(rf"\b{re.escape(name)}\s*\(", source):
        candidate_brace = source.find("{", candidate.end())
        candidate_semicolon = source.find(";", candidate.end())
        if candidate_brace != -1 and (candidate_semicolon == -1 or candidate_brace < candidate_semicolon):
            match = candidate
            brace = candidate_brace
            break
    require(match is not None, f"definition missing: {name}")
    depth = 0
    quote = ""
    escaped = False
    line_comment = False
    block_comment = False
    index = brace
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
        elif block_comment:
            if char == "*" and nxt == "/":
                block_comment = False
                index += 1
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char == "/" and nxt == "/":
            line_comment = True
            index += 1
        elif char == "/" and nxt == "*":
            block_comment = True
            index += 1
        elif char in {'"', "'"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : index + 1]
        index += 1
    raise ContractError(f"unbalanced definition: {name}")


def braced_block(source: str, marker: str) -> str:
    start = source.find(marker)
    require(start != -1, f"block missing: {marker}")
    brace = source.find("{", start + len(marker))
    require(brace != -1, f"block body missing: {marker}")
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise ContractError(f"unbalanced block: {marker}")


def ordered(body: str, needles: tuple[str, ...], label: str) -> None:
    position = -1
    for needle in needles:
        found = body.find(needle, position + 1)
        require(found != -1, f"{label} missing {needle!r}")
        position = found


def verify_text(source: str) -> dict[str, object]:
    for needle in (
        "SPDX-FileCopyrightText: 2008-2018 Blender Authors",
        "SPDX-FileCopyrightText: 2026 blender-web contributors",
        "SPDX-License-" "Identifier: GPL-2.0-or-later",
        "Ported for the web from source/blender/editors/gpencil_legacy/annotate_paint.cc @",
        "fbe6228777e7.",
        '#include "BLI_vector.hh"',
    ):
        require(needle in source, f"license/provenance contract missing {needle!r}")

    data = braced_block(source, "struct tGPsdata")
    for needle in (
        "ViewportDepthCacheSession *depth_cache_session = nullptr;",
        "Vector<wmEvent> *depth_cache_events = nullptr;",
        "wmTimer *depth_cache_timer = nullptr;",
        "RegionView3D *depth_cache_region_view = nullptr;",
        "float depth_cache_viewinv[4][4] = {};",
        "float depth_cache_winmat[4][4] = {};",
        "bool depth_cache_pending = false;",
        "bool depth_cache_valid = false;",
        "bool depth_cache_owned = false;",
        "bool depth_cache_resume_apply_event = false;",
        "Vector<AnnotationRecordedStrokePoint> *recorded_stroke_points = nullptr;",
        "int64_t recorded_stroke_index = 0;",
        "bool recorded_stroke_exec = false;",
    ):
        require(needle in data, f"annotation owner state missing {needle!r}")

    matches = definition(source, "annotation_depth_cache_matches")
    for needle in (
        "p->depth_cache_mode != mode",
        "p->region->regiondata != p->depth_cache_region_view",
        "p->region->winx != p->depth_cache_region_size[0]",
        "equals_m4m4(region_view->viewinv, p->depth_cache_viewinv)",
        "equals_m4m4(region_view->winmat, p->depth_cache_winmat)",
    ):
        require(needle in matches, f"cache identity guard missing {needle!r}")

    event_push = definition(source, "annotation_depth_event_push")
    for needle in (
        "constexpr int max_queued_events = 256;",
        "event->type == TIMER",
        "event->custom != 0",
        "event->customdata != nullptr",
        "queued.next = nullptr;",
        "queued.prev = nullptr;",
        "queued.customdata_free = false;",
    ):
        require(needle in event_push, f"safe event ownership missing {needle!r}")

    begin = definition(source, "annotation_depth_cache_begin")
    ordered(
        begin,
        (
            "annotation_depth_cache_matches(p, mode)",
            "CTX_wm_window(C) != p->win",
            "ED_view3d_depth_override_prepare(",
            "MEM_new<ViewportDepthCacheSession>",
            "p->depth_cache_session->init(p->region)",
            "ViewportDepthCacheSession::ReadbackState::Ready",
            "WM_event_timer_add(manager, p->win, TIMER, 0.01f)",
            "p->depth_cache_pending = true;",
        ),
        "depth-cache request",
    )
    require(
        "p->depth_cache_mode == mode ? AnnotationDepthCacheState::Pending" in begin,
        "pending request mode ownership missing",
    )

    take = definition(source, "annotation_depth_cache_take")
    ordered(
        take,
        (
            "p->depth_cache_session->take(p->region)",
            "annotation_depth_cache_discard(p)",
            "p->depths = depths;",
            "copy_m4_m4(p->depth_cache_viewinv",
            "copy_m4_m4(p->depth_cache_winmat",
            "p->depth_cache_valid = true;",
            "MEM_SAFE_DELETE(p->depth_cache_session)",
        ),
        "depth-cache transfer",
    )

    convert = definition(source, "annotation_stroke_convertcoords")
    require(
        "annotation_depth_cache_matches(p, annotation_depth_cache_mode_get(p))" in convert,
        "interactive coordinate conversion does not bind the owned cache",
    )
    require(
        "annotation_project_check(p) && depth != nullptr" in convert,
        "owned coordinate conversion can enter an implicit synchronous point read",
    )

    addpoint = definition(source, "annotation_stroke_addpoint")
    eraser = definition(source, "annotation_stroke_doeraser")
    stroke_end = definition(source, "annotation_paint_strokeend")
    for label, body, mode in (
        ("polyline", addpoint, "annotation_depth_cache_matches(p, mode)"),
        ("eraser", eraser, "annotation_depth_cache_matches(p, V3D_DEPTH_NO_GPENCIL)"),
        ("stroke end", stroke_end, "annotation_depth_cache_matches(p, mode)"),
    ):
        require(mode in body, f"{label} owned cache guard missing")
        require("ED_view3d_depth_override(" not in body,
                f"{label} retains a synchronous depth override")

    require(
        source.count("ED_view3d_depth_override(") == 0,
        "synchronous annotation depth-override residual remains",
    )
    require(
        source.count("ED_view3d_depth_override_prepare(") == 1,
        "unexpected asynchronous annotation prepare census",
    )

    invoke = definition(source, "annotation_draw_invoke")
    execute = definition(source, "annotation_draw_exec")
    require("p->depth_cache_owned = true;" in invoke,
            "interactive ownership is not enabled from invoke")
    ordered(
        execute,
        (
            "p->depth_cache_owned = true;",
            "p->recorded_stroke_exec = true;",
            "MEM_new<Vector<AnnotationRecordedStrokePoint>>",
            'RNA_float_get_array(&itemptr, "mouse", point.mouse)',
            'point.pressure = RNA_float_get(&itemptr, "pressure")',
            'point.time = RNA_float_get(&itemptr, "time")',
            'point.is_start = RNA_boolean_get(&itemptr, "is_start")',
            "p->recorded_stroke_points->append(point)",
            "annotation_recorded_stroke_resume(C, op)",
            "WM_event_add_modal_handler(C, op)",
        ),
        "recorded-stroke owned snapshot",
    )
    require("annotation_draw_apply(op, p" not in execute,
            "recorded-stroke exec still applies RNA points synchronously")
    require("p->depth_cache_resume_apply_event = true;" in invoke,
            "immediate invoke cannot resume its exact initial event")

    recorded_cache = definition(source, "annotation_recorded_stroke_cache_ensure")
    for needle in (
        "p->flags & GP_PAINTFLAG_V3D_ERASER_DEPTH",
        "V3D_DEPTH_NO_GPENCIL",
        "annotation_project_check(p)",
        "annotation_depth_cache_mode_get(p)",
    ):
        require(needle in recorded_cache, f"recorded cache policy missing {needle!r}")

    recorded_resume = definition(source, "annotation_recorded_stroke_resume")
    ordered(
        recorded_resume,
        (
            "p->recorded_stroke_index < p->recorded_stroke_points->size()",
            "point.is_start && (p->flags & GP_PAINTFLAG_FIRSTRUN) == 0",
            "annotation_recorded_stroke_cache_ensure(C, p, false)",
            "annotation_paint_strokeend(p)",
            "annotation_paint_initstroke(p, p->paintmode, depsgraph)",
            "annotation_recorded_stroke_cache_ensure(C, p, true)",
            "p->mval[0] = int(point.mouse[0])",
            "annotation_draw_apply(op, p, depsgraph)",
            "p->recorded_stroke_index++",
            "annotation_recorded_stroke_cache_ensure(C, p, false)",
            "annotation_draw_exit(C, op)",
            "WM_event_add_notifier(C, NC_GPENCIL | NA_EDITED, nullptr)",
        ),
        "recorded-stroke bounded replay",
    )

    dispatch = definition(source, "annotation_draw_modal_dispatch")
    require("p = annotation_stroke_begin(C, op);" in dispatch,
            "stock annotation stroke-begin seam missing")
    require("p->depth_cache_resume_apply_event = true;" in dispatch,
            "post-stroke-begin event lacks exact resume disposition")

    context = definition(source, "annotation_depth_context_matches")
    for needle in (
        "CTX_wm_manager(C) == p->depth_cache_manager",
        "CTX_wm_window(C) == p->win",
        "CTX_wm_screen(C) == p->depth_cache_screen",
        "CTX_wm_area(C) == p->area",
        "CTX_wm_region(C) == p->region",
        "CTX_wm_region_view3d(C)",
        "CTX_wm_view3d(C)",
        "CTX_data_scene(C) == p->scene",
    ):
        require(needle in context, f"producing context guard missing {needle!r}")

    poll = definition(source, "annotation_depth_poll")
    ordered(
        poll,
        (
            "annotation_depth_context_matches(C, p)",
            "event->customdata != p->depth_cache_timer",
            "constexpr int max_tick_count = 240;",
            "p->depth_cache_session->state()",
            "annotation_depth_cache_take(p)",
            "annotation_depth_timer_remove(p)",
            "const bool resume_apply_event = p->depth_cache_resume_apply_event;",
            "if (p->recorded_stroke_exec)",
            "annotation_recorded_stroke_resume(C, op)",
            "annotation_depth_resume_apply_event(",
            "annotation_draw_modal(C, op",
            "if (p->depth_cache_pending)",
            "annotation_depth_event_push(p",
        ),
        "bounded annotation settlement",
    )

    wrapper = definition(source, "annotation_draw_modal")
    ordered(
        wrapper,
        (
            "if (p->depth_cache_pending)",
            "annotation_depth_poll(C, op, event)",
            "annotation_depth_event_requires_cache(p, event)",
            "annotation_depth_cache_defer_event(",
            "annotation_draw_modal_dispatch(C, op, event)",
        ),
        "modal continuation wrapper",
    )

    cancel = definition(source, "annotation_draw_cancel")
    session_free = definition(source, "annotation_session_free")
    require("annotation_draw_abort(C, op);" in cancel,
            "external interactive cancellation can finish a pending stroke")
    require("annotation_depth_wait_cancel(p);" in session_free,
            "session destruction does not retire the pending ticket/timer")
    require("annotation_depth_cache_discard(p);" in session_free,
            "session destruction does not release the owned cache")
    require("MEM_SAFE_DELETE(p->recorded_stroke_points);" in session_free,
            "session destruction does not release the recorded-stroke snapshot")

    operator_register = definition(source, "GPENCIL_OT_annotate")
    for needle in (
        "ot->exec = annotation_draw_exec;",
        "ot->invoke = annotation_draw_invoke;",
        "ot->modal = annotation_draw_modal;",
        "ot->cancel = annotation_draw_cancel;",
    ):
        require(needle in operator_register, f"operator callback drift: {needle}")

    return {
        "verdict": "PASS",
        "contracts": {
            "interactive_draw_completion": True,
            "interactive_polyline_updates": True,
            "interactive_depth_eraser": True,
            "native_immediate_completion": True,
            "pending_event_fifo": True,
            "bounded_timer_and_context": True,
            "failure_and_external_cancel_cleanup": True,
            "recorded_stroke_exec_async": True,
            "live_hardware_receipt": False,
        },
        "converted_callers": [
            "GPENCIL_OT_annotate interactive",
            "GPENCIL_OT_annotate recorded-stroke exec",
        ],
        "remaining_annotation_residuals": [],
        "remaining_sync_families": ["depth_cache", "window_capture"],
    }


def mutation_selfcheck(source: str) -> int:
    mutations = (
        ("prepare", "ED_view3d_depth_override_prepare(", "ED_view3d_depth_override_legacy("),
        ("queue-bound", "constexpr int max_queued_events = 256;", "constexpr int max_queued_events = 257;"),
        ("customdata", "event->customdata != nullptr", "event->customdata == nullptr"),
        ("cache-mode", "p->depth_cache_mode != mode", "false"),
        ("view-matrix", "equals_m4m4(region_view->viewinv, p->depth_cache_viewinv)", "true"),
        ("timeout", "constexpr int max_tick_count = 240;", "constexpr int max_tick_count = 0;"),
        (
            "take",
            "state == ViewportDepthCacheSession::ReadbackState::Failed ||\n      !annotation_depth_cache_take(p)",
            "state == ViewportDepthCacheSession::ReadbackState::Failed ||\n      false",
        ),
        ("initial-resume", "p->depth_cache_resume_apply_event = true;", "p->depth_cache_resume_apply_event = false;"),
        ("context", "CTX_wm_manager(C) == p->depth_cache_manager", "true"),
        ("point-read", "annotation_project_check(p) && depth != nullptr", "annotation_project_check(p)"),
        ("invoke-owner", "p->depth_cache_owned = true;", "p->depth_cache_owned = false;"),
        ("recorded-owner", "p->recorded_stroke_exec = true;", "p->recorded_stroke_exec = false;"),
        ("recorded-index", "p->recorded_stroke_index++;", "p->recorded_stroke_index += 0;"),
        (
            "recorded-boundary",
            "annotation_recorded_stroke_cache_ensure(C, p, false)",
            "AnnotationDepthCacheState::Ready",
        ),
        (
            "recorded-snapshot",
            'point.is_start = RNA_boolean_get(&itemptr, "is_start");',
            "point.is_start = false;",
        ),
        (
            "recorded-settlement",
            "return annotation_recorded_stroke_resume(C, op);",
            "return OPERATOR_RUNNING_MODAL;",
        ),
        ("cancel", "annotation_draw_abort(C, op);", "annotation_draw_exit(C, op);"),
    )
    rejected = 0
    for label, old, new in mutations:
        require(old in source, f"selfcheck mutation target missing: {label}")
        mutated = source.replace(old, new, 1)
        try:
            verify_text(mutated)
        except ContractError:
            rejected += 1
        else:
            raise ContractError(f"selfcheck mutation unexpectedly accepted: {label}")
    return rejected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    path = args.source_root / RELATIVE
    source_bytes = path.read_bytes()
    source = source_bytes.decode("utf-8")
    receipt = verify_text(source)
    receipt["source_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    receipt["source"] = RELATIVE.as_posix()
    if args.selfcheck:
        receipt["rejected_mutations"] = mutation_selfcheck(source)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "M5_ANNOTATION_DEPTH_CACHE_SOURCE_PASS "
        f"sha256={receipt['source_sha256']} mutations={receipt.get('rejected_mutations', 0)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"ERROR: {error}")
        raise SystemExit(1)
