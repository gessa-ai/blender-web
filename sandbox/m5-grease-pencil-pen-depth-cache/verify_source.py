#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind the Grease Pencil pen helper to an owned depth-cache initialization wait."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


HEADER = Path("source/blender/editors/include/ED_curves.hh")
BASE = Path("source/blender/editors/curves/intern/curves_pen.cc")
PEN = Path("source/blender/editors/grease_pencil/intern/grease_pencil_pen.cc")
RELATIVES = (HEADER, BASE, PEN)


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
    header = sources[HEADER]
    base = sources[BASE]
    pen = sources[PEN]

    pen_class = braced_definition(
        pen, "class GreasePencilPenToolOperation", "Grease Pencil pen owner"
    )
    for token in (
        "std::optional<wmEvent> depth_cache_start_event_",
        "Vector<wmEvent> depth_cache_events_",
        "wmTimer *depth_cache_timer_ = nullptr;",
        "wmWindowManager *depth_cache_manager_ = nullptr;",
        "wmWindow *depth_cache_window_ = nullptr;",
        "bScreen *depth_cache_screen_ = nullptr;",
        "ScrArea *depth_cache_area_ = nullptr;",
        "ARegion *depth_cache_region_ = nullptr;",
        "RegionView3D *depth_cache_region_view_ = nullptr;",
        "View3D *depth_cache_view3d_ = nullptr;",
        "Depsgraph *depth_cache_depsgraph_ = nullptr;",
        "Scene *depth_cache_scene_ = nullptr;",
        "ViewLayer *depth_cache_view_layer_ = nullptr;",
        "Object *depth_cache_object_ = nullptr;",
        "Object *depth_cache_eval_object_ = nullptr;",
        "GreasePencil *depth_cache_grease_pencil_ = nullptr;",
        "bke::greasepencil::Layer *depth_cache_layer_ = nullptr;",
        "int depth_cache_frame_ = 0;",
        "int depth_cache_tick_count_ = 0;",
        "bool depth_cache_pending_ = false;",
        "bool initialized_ = false;",
    ):
        require(token in pen_class, f"pen continuation ownership missing: {token}")

    require(
        "void invoke_initialized(bContext *C, wmOperator *op, const wmEvent *event);" in header,
        "base pen operation does not expose the exact post-initialize seam",
    )
    base_resume = braced_definition(
        base, "void PenToolOperation::invoke_initialized(", "base invoke continuation"
    )
    require("invoke_curves(*this, C, op, event);" in base_resume, "resume seam bypasses stock invoke")
    base_invoke = braced_definition(base, "wmOperatorStatus PenToolOperation::invoke(", "base invoke")
    require(
        "this->invoke_initialized(C, op, event);" in base_invoke,
        "native invoke does not use the shared continuation seam",
    )

    wait_begin = braced_definition(
        pen,
        "bool GreasePencilPenToolOperation::depth_cache_wait_begin(",
        "wait begin",
    )
    for token in (
        "CTX_wm_manager(C)",
        "CTX_wm_window(C)",
        "CTX_wm_screen(C)",
        "CTX_wm_area(C)",
        "CTX_wm_region(C)",
        "CTX_wm_region_view3d(C)",
        "CTX_wm_view3d(C)",
        "CTX_data_depsgraph_pointer(C)",
        "CTX_data_scene(C)",
        "CTX_data_view_layer(C)",
        "CTX_data_active_object(C)",
        "DEG_get_evaluated(depth_cache_depsgraph_, depth_cache_object_)",
        "retained_event.next = nullptr;",
        "retained_event.prev = nullptr;",
        "retained_event.customdata = nullptr;",
        "retained_event.customdata_free = false;",
        "TIMER, 0.01f",
        "depth_cache_pending_ = true;",
    ):
        require(token in wait_begin, f"wait ownership missing: {token}")

    context = braced_definition(
        pen,
        "bool GreasePencilPenToolOperation::depth_cache_context_matches(",
        "context guard",
    )
    for token in (
        "CTX_wm_manager(C) != depth_cache_manager_",
        "CTX_wm_window(C) != depth_cache_window_",
        "CTX_wm_screen(C) != depth_cache_screen_",
        "CTX_wm_area(C) != depth_cache_area_",
        "CTX_wm_region(C) != depth_cache_region_",
        "CTX_wm_region_view3d(C) != depth_cache_region_view_",
        "CTX_wm_view3d(C) != depth_cache_view3d_",
        "CTX_data_depsgraph_pointer(C) != depth_cache_depsgraph_",
        "CTX_data_scene(C) != depth_cache_scene_",
        "CTX_data_view_layer(C) != depth_cache_view_layer_",
        "CTX_data_active_object(C) != depth_cache_object_",
        "depth_cache_scene_->r.cfra != depth_cache_frame_",
        "DEG_get_evaluated(depth_cache_depsgraph_, depth_cache_object_) != depth_cache_eval_object_",
        "grease_pencil->get_active_layer() == depth_cache_layer_",
    ):
        require(token in context, f"producing-context guard missing: {token}")

    event_push = braced_definition(
        pen,
        "bool GreasePencilPenToolOperation::depth_cache_event_push(",
        "bounded event queue",
    )
    for token in (
        "constexpr int max_queued_events = 256;",
        "event->type == TIMER",
        "event->custom != 0",
        "event->customdata != nullptr",
        "depth_cache_events_.size() >= max_queued_events",
        "queued.next = nullptr;",
        "queued.prev = nullptr;",
        "queued.customdata = nullptr;",
        "queued.customdata_free = false;",
        "depth_cache_events_.append(queued);",
    ):
        require(token in event_push, f"bounded event ownership missing: {token}")

    clear = braced_definition(
        pen, "void GreasePencilPenToolOperation::depth_cache_clear()", "owned cleanup"
    )
    for token in (
        "depth_cache_timer_remove();",
        "placement.cancel_viewport_depths();",
        "depth_cache_start_event_.reset();",
        "depth_cache_events_.clear();",
        "depth_cache_pending_ = false;",
    ):
        require(token in clear, f"owned cleanup missing: {token}")

    ready = braced_definition(
        pen, "void GreasePencilPenToolOperation::initialize_ready(", "ready-only tail"
    )
    for token in (
        "ensure_active_keyframe(",
        "this->drawings = retrieve_editable_drawings(",
        "layer.local_transform()",
        "layer.to_world_space(*this->vc.obact)",
        "this->initialized_ = true;",
    ):
        require(token in ready, f"ready-only initialization missing: {token}")
    require(
        ready.find("ensure_active_keyframe(") < ready.find("retrieve_editable_drawings("),
        "editable drawings are captured before stock keyframe duplication",
    )

    initialize = braced_definition(
        pen,
        "std::optional<wmOperatorStatus> GreasePencilPenToolOperation::initialize(",
        "pen initialize",
    )
    for token in (
        "this->placement = DrawingPlacement(",
        "this->placement.use_project_to_surface() || this->placement.use_project_to_stroke()",
        "this->placement.cache_viewport_depths_async(",
        "DrawingPlacementDepthCacheState::Pending",
        "this->depth_cache_wait_begin(C, event)",
        "WM_event_add_modal_handler(C, op);",
        "this->initialize_ready(C);",
    ):
        require(token in initialize, f"owned initialization missing: {token}")
    require("cache_viewport_depths(" not in initialize, "pen initialize retains synchronous readback")
    require(
        "DrawingPlacementDepthCacheState::Failed" not in initialize,
        "initial read failure no longer follows stock projection fallback",
    )
    for mutation in ("ensure_active_keyframe(", "retrieve_editable_drawings(", "local_transform()"):
        require(mutation not in initialize, f"pen mutates before cache settlement: {mutation}")
    require(
        initialize.find("cache_viewport_depths_async(") < initialize.find("this->initialize_ready(C);"),
        "ready tail can run before the owned cache request",
    )

    poll = braced_definition(
        pen, "wmOperatorStatus GreasePencilPenToolOperation::depth_cache_poll(", "poll"
    )
    for token in (
        "this->depth_cache_context_matches(C)",
        "event->customdata != depth_cache_timer_",
        "constexpr int max_tick_count = 240;",
        "++depth_cache_tick_count_ > max_tick_count",
        "placement.poll_viewport_depths(",
        "depth_cache_region_)",
        "DrawingPlacementDepthCacheState::Pending",
        "DrawingPlacementDepthCacheState::Failed",
        "const wmEvent start_event = *depth_cache_start_event_;",
        "Vector<wmEvent> queued_events = std::move(depth_cache_events_);",
        "this->initialize_ready(C);",
        "this->invoke_initialized(C, op, &start_event);",
        "PenToolOperation::modal(C, op, &queued_event)",
    ):
        require(token in poll, f"pen settlement missing: {token}")
    require(
        poll.find("this->initialize_ready(C);") < poll.find("this->invoke_initialized(C, op, &start_event);"),
        "first event can run before initialization settles",
    )
    require(
        poll.find("this->invoke_initialized(C, op, &start_event);")
        < poll.find("PenToolOperation::modal(C, op, &queued_event)"),
        "queued modal events can run before the exact initiating event",
    )

    modal = braced_definition(
        pen, "wmOperatorStatus GreasePencilPenToolOperation::modal(", "modal"
    )
    require("if (depth_cache_pending_)" in modal, "pending state is not isolated")
    require("this->depth_cache_poll(C, op, event)" in modal, "pending events bypass owned poll")
    require("PenToolOperation::modal(C, op, event)" in modal, "initialized events bypass stock modal")

    exit_body = braced_definition(pen, "static void grease_pencil_pen_exit(", "exit")
    require("ptd->depth_cache_clear();" in exit_body, "exit does not retire the owned wait")
    require("if (ptd->initialized_)" in exit_body, "pending exit touches initialized drawing state")
    operator = braced_definition(pen, "static void GREASE_PENCIL_OT_pen(", "operator registration")
    require("ot->cancel = grease_pencil_pen_cancel;" in operator, "external cancellation is unowned")
    require(pen.count("cache_viewport_depths_async(") == 1, "pen owner must start one exact request")
    require("cache_viewport_depths(" not in pen, "pen helper retains synchronous depth reads")


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
        (PEN, "cache_viewport_depths_async(", "cache_viewport_depths("),
        (PEN, "constexpr int max_tick_count = 240;", "constexpr int max_tick_count = 0;"),
        (PEN, "constexpr int max_queued_events = 256;", "constexpr int max_queued_events = 0;"),
        (PEN, "retained_event.customdata = nullptr;", "retained_event.customdata = event->customdata;"),
        (PEN, "CTX_wm_region(C) != depth_cache_region_", "false /* region drift */"),
        (PEN, "placement.cancel_viewport_depths();", "/* no request cancel */"),
        (PEN, "if (depth_cache_pending_)", "if (false)"),
        (PEN, "event->customdata != depth_cache_timer_", "false /* foreign timer */"),
        (PEN, "this->invoke_initialized(C, op, &start_event);", "/* initiating event lost */"),
        (PEN, "PenToolOperation::modal(C, op, &queued_event)", "OPERATOR_RUNNING_MODAL"),
        (PEN, "this->initialize_ready(C);", "this->initialized_ = true;", 1),
        (PEN, "ot->cancel = grease_pencil_pen_cancel;", "/* no external cancel */"),
        (BASE, "this->invoke_initialized(C, op, event);", "invoke_curves(*this, C, op, event);"),
        (HEADER, "void invoke_initialized(bContext *C, wmOperator *op, const wmEvent *event);", "void invoke_initialized();"),
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
        "schema": "blender-web-m5-grease-pencil-pen-depth-cache-v1",
        "verdict": "PASS",
        "source_sha256": combined_digest(sources),
        "source_paths": [relative.as_posix() for relative in RELATIVES],
        "converted_callers": ["pen-helper"],
        "remaining_grease_pencil_callers": [],
        "remaining_sync_families": ["depth_cache", "window_capture"],
        "mutation_controls": mutations,
        "contracts": {
            "operation_owned_request": True,
            "native_immediate_and_initial_fallback": True,
            "pre_mutation_suspension": True,
            "shared_post_initialize_seam": True,
            "retained_first_event_and_fifo": True,
            "stock_layer_transform_tail": True,
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
        print(f"M5_GREASE_PENCIL_PEN_DEPTH_CACHE_SOURCE_FAIL {error}", file=__import__("sys").stderr)
        raise SystemExit(1)
