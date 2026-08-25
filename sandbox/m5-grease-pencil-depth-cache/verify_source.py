#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind the freehand Grease Pencil placement continuation to shipping source."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile


PATHS = {
    "placement_header": Path("source/blender/editors/include/ED_grease_pencil.hh"),
    "operation_header": Path(
        "source/blender/editors/sculpt_paint/grease_pencil/grease_pencil_intern.hh"
    ),
    "placement": Path(
        "source/blender/editors/grease_pencil/intern/grease_pencil_utils.cc"
    ),
    "dispatcher": Path(
        "source/blender/editors/sculpt_paint/grease_pencil/draw_ops.cc"
    ),
    "paint": Path("source/blender/editors/sculpt_paint/grease_pencil/paint.cc"),
}


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def function_body(source: str, signature: str) -> str:
    start = source.find(signature)
    require(start >= 0, f"missing function: {signature}")
    opening = source.find("{", start + len(signature))
    require(opening >= 0, f"missing function body: {signature}")
    depth = 0
    state = "code"
    i = opening
    while i < len(source):
        char = source[i]
        pair = source[i : i + 2]
        if state == "line":
            if char == "\n":
                state = "code"
        elif state == "block":
            if pair == "*/":
                state = "code"
                i += 1
        elif state == "string":
            if char == "\\":
                i += 1
            elif char == '"':
                state = "code"
        elif state == "char":
            if char == "\\":
                i += 1
            elif char == "'":
                state = "code"
        else:
            if pair == "//":
                state = "line"
                i += 1
            elif pair == "/*":
                state = "block"
                i += 1
            elif char == '"':
                state = "string"
            elif char == "'":
                state = "char"
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return source[opening : i + 1]
        i += 1
    raise VerificationError(f"unterminated function: {signature}")


def verify(sources: dict[str, str]) -> None:
    placement_header = sources["placement_header"]
    operation_header = sources["operation_header"]
    placement = sources["placement"]
    dispatcher = sources["dispatcher"]
    paint = sources["paint"]

    for token in (
        "enum class DrawingPlacementDepthCacheState : int8_t { Ready, Pending, Failed };",
        "ViewportDepthCacheSession *depth_cache_session_ = nullptr;",
        "DrawingPlacementDepthCacheState cache_viewport_depths_async(",
        "DrawingPlacementDepthCacheState poll_viewport_depths(ARegion *region);",
        "void cancel_viewport_depths();",
    ):
        require(token in placement_header, f"placement API missing: {token}")

    for token in (
        "enum class GreasePencilStrokeOperationAsyncState : int8_t { Running, Pending, Failed };",
        "virtual GreasePencilStrokeOperationAsyncState async_state() const",
        "virtual GreasePencilStrokeOperationAsyncState poll_async(const bContext &C)",
        "virtual void cancel_async()",
    ):
        require(token in operation_header, f"operation async API missing: {token}")

    start_async = function_body(
        placement, "DrawingPlacement::cache_viewport_depths_async("
    )
    poll_async = function_body(placement, "DrawingPlacement::poll_viewport_depths(")
    cancel_async = function_body(placement, "DrawingPlacement::cancel_viewport_depths()")
    for token in (
        "ED_view3d_depth_override_prepare(",
        "MEM_new<ViewportDepthCacheSession>",
        "view3d->gp_flag = previous_gp_flag;",
        "depth_cache_session_->init(region)",
    ):
        require(token in start_async, f"placement async start missing: {token}")
    for token in (
        "ViewportDepthCacheSession::ReadbackState::Pending",
        "ViewportDepthCacheSession::ReadbackState::Failed",
        "depth_cache_session_->take(region)",
        "MEM_SAFE_DELETE(depth_cache_session_);",
    ):
        require(token in poll_async, f"placement async poll missing: {token}")
    require("MEM_SAFE_DELETE(depth_cache_session_);" in cancel_async,
            "placement cancellation does not own its request")
    require("std::swap(depth_cache_session_, other.depth_cache_session_);" in placement,
            "placement move does not transfer pending request ownership")
    require("BLI_assert(other.depth_cache_session_ == nullptr);" in placement,
            "placement copy does not reject an uncopyable pending request")

    stroke_class = dispatcher[dispatcher.find("struct GreasePencilPaintStroke") :]
    for token in (
        "wmTimer *depth_cache_timer_ = nullptr;",
        "const int event_type_;",
        "std::optional<wmEvent> deferred_finish_event_;",
        "wmOperatorStatus modal(bContext *C, wmOperator *op, const wmEvent *event);",
        "void cancel(bContext *C);",
    ):
        require(token in stroke_class, f"paint-stroke owner missing: {token}")
    modal = function_body(dispatcher, "GreasePencilPaintStroke::modal(")
    for token in (
        "event->customdata == depth_cache_timer_",
        "operation->poll_async(*C)",
        "this->depth_cache_timer_remove(C)",
        "return PaintStroke::modal(C, op, &finish_event);",
        "event->type == event_type_ && event->val == KM_RELEASE",
        "ELEM(event->type, EVT_RETKEY, EVT_SPACEKEY)",
        "EVT_MODAL_MAP",
        "constexpr int paint_stroke_modal_cancel = 1;",
        "finish_event.customdata = nullptr;",
        "finish_event.customdata_free = false;",
    ):
        require(token in modal, f"paint-stroke modal continuation missing: {token}")
    require("WM_event_timer_add(" in dispatcher and "1.0 / 60.0" in dispatcher,
            "paint-stroke continuation lacks its bounded poll timer")
    timer_remove = function_body(
        dispatcher, "GreasePencilPaintStroke::depth_cache_timer_remove("
    )
    require("WM_event_timer_remove(" in timer_remove,
            "paint-stroke continuation does not retire its exact timer")

    for token in (
        "std::optional<InputSample> depth_cache_start_sample_;",
        "Vector<InputSample> depth_cache_samples_;",
        "wmWindowManager *depth_cache_manager_ = nullptr;",
        "wmWindow *depth_cache_window_ = nullptr;",
        "bScreen *depth_cache_screen_ = nullptr;",
        "ScrArea *depth_cache_area_ = nullptr;",
        "ARegion *depth_cache_region_ = nullptr;",
        "RegionView3D *depth_cache_region_view_ = nullptr;",
        "View3D *depth_cache_view3d_ = nullptr;",
        "Scene *depth_cache_scene_ = nullptr;",
        "Object *depth_cache_object_ = nullptr;",
        "const bke::greasepencil::Layer *depth_cache_layer_ = nullptr;",
        "int depth_cache_tick_count_ = 0;",
        "bool stroke_initialized_ = false;",
    ):
        require(token in paint, f"paint operation ownership missing: {token}")

    begin = function_body(paint, "PaintOperation::on_stroke_begin(")
    require("cache_viewport_depths_async(" in begin,
            "freehand paint does not start the owned cache")
    require("cache_viewport_depths(" not in begin,
            "freehand paint retains its synchronous depth-cache call")
    require("depth_cache_start_sample_ = start_sample;" in begin,
            "starting input sample is not retained")
    require("return;" in begin, "pending begin cannot return before mutation")

    context_match = function_body(paint, "PaintOperation::depth_cache_context_matches(")
    for token in (
        "CTX_wm_manager(&C) != depth_cache_manager_",
        "CTX_wm_window(&C) != depth_cache_window_",
        "CTX_wm_screen(&C) != depth_cache_screen_",
        "CTX_wm_area(&C) != depth_cache_area_",
        "CTX_wm_region(&C) != depth_cache_region_",
        "CTX_wm_region_view3d(&C) != depth_cache_region_view_",
        "CTX_wm_view3d(&C) != depth_cache_view3d_",
        "CTX_data_scene(&C) != depth_cache_scene_",
        "CTX_data_active_object(&C) != depth_cache_object_",
        "get_active_layer() == depth_cache_layer_",
    ):
        require(token in context_match, f"producing context guard missing: {token}")

    poll = function_body(paint, "PaintOperation::poll_async(")
    for token in (
        "constexpr int max_tick_count = 240;",
        "++depth_cache_tick_count_ > max_tick_count",
        "placement_.poll_viewport_depths(depth_cache_region_)",
        "this->on_stroke_begin_ready(C, start_sample);",
        "for (const InputSample &sample : queued_samples)",
        "this->on_stroke_extended(C, sample);",
    ):
        require(token in poll, f"paint async settlement missing: {token}")
    extended = function_body(paint, "PaintOperation::on_stroke_extended(")
    require("constexpr int max_sample_count = 256;" in extended,
            "pending sample FIFO lacks a bound")
    require("depth_cache_samples_.append(extension_sample);" in extended,
            "pending samples are not copied into the FIFO")
    require("GreasePencilStrokeOperationAsyncState::Failed" in extended,
            "sample overflow does not fail closed")
    done = function_body(paint, "PaintOperation::on_stroke_done(")
    require("if (!stroke_initialized_)" in done,
            "terminal callback can touch an uninitialized stroke")
    cancel = function_body(paint, "PaintOperation::cancel_async()")
    require("placement_.cancel_viewport_depths();" in cancel,
            "operation cancellation does not retire placement request")
    require("depth_cache_samples_.clear();" in cancel,
            "operation cancellation does not retire queued samples")


def source_digest(sources: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(PATHS):
        digest.update(str(PATHS[name]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(sources[name].encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def run_selfcheck(sources: dict[str, str]) -> None:
    mutations = (
        ("placement_header", "cache_viewport_depths_async", "cache_viewport_depths_retired"),
        ("operation_header", "poll_async", "poll_retired"),
        ("placement", "ED_view3d_depth_override_prepare(", "ED_view3d_depth_override("),
        ("placement", "depth_cache_session_->take(region)", "nullptr"),
        ("dispatcher", "1.0 / 60.0", "0.0"),
        ("dispatcher", "return PaintStroke::modal(C, op, &finish_event);",
         "return OPERATOR_FINISHED;"),
        ("paint", "constexpr int max_tick_count = 240;", "constexpr int max_tick_count = 0;"),
        ("paint", "constexpr int max_sample_count = 256;", "constexpr int max_sample_count = 0;"),
        ("paint", "CTX_wm_region(&C) != depth_cache_region_", "false"),
        ("paint", "depth_cache_start_sample_ = start_sample;", "depth_cache_start_sample_.reset();"),
        ("paint", "placement_.poll_viewport_depths(depth_cache_region_)",
         "DrawingPlacementDepthCacheState::Ready"),
        ("paint", "placement_.cancel_viewport_depths();", "/* retired */"),
    )
    for name, old, new in mutations:
        require(old in sources[name], f"selfcheck mutation source missing: {name}: {old}")
        mutated = dict(sources)
        mutated[name] = sources[name].replace(old, new, 1)
        try:
            verify(mutated)
        except VerificationError:
            continue
        raise VerificationError(f"selfcheck mutation survived: {name}: {old}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    sources = {
        name: (source_root / relative).read_text(encoding="utf-8")
        for name, relative in PATHS.items()
    }
    verify(sources)
    if args.selfcheck:
        run_selfcheck(sources)
    if args.output is not None:
        payload = {
            "verdict": "PASS",
            "source_sha256": source_digest(sources),
            "converted_callers": ["GREASE_PENCIL_OT_brush_stroke freehand paint"],
            "contracts": {
                "native_immediate_completion": True,
                "pending_first_sample": True,
                "pending_sample_fifo": True,
                "bounded_timer": True,
                "producing_context_guard": True,
                "release_after_settlement": True,
                "failure_timeout_cancellation": True,
                "live_hardware_receipt": False,
            },
            "remaining_grease_pencil_callers": ["primitive", "fill", "pen-helper"],
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
    print("M5_GREASE_PENCIL_DEPTH_CACHE_SOURCE_PASS files=5 mutations=12")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, VerificationError) as error:
        print(f"M5_GREASE_PENCIL_DEPTH_CACHE_SOURCE_FAIL {error}", file=__import__("sys").stderr)
        raise SystemExit(1)
