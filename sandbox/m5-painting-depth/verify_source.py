#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed source contract for image-paint clone-cursor depth continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PIN = "fbe6228777e7d9afefcd61a413844e790ae75db7"
SOURCE_PATHS = (
    "source/blender/editors/include/ED_view3d.hh",
    "source/blender/editors/space_view3d/view3d_draw.cc",
    "source/blender/editors/sculpt_paint/paint_intern.hh",
    "source/blender/editors/sculpt_paint/mesh/paint_image_proj.cc",
    "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc",
    "source/blender/gpu/GPU_framebuffer.hh",
    "source/blender/gpu/GPU_readback.hh",
)


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def require_ordered(text: str, needles: tuple[str, ...], label: str) -> None:
    position = -1
    for needle in needles:
        next_position = text.find(needle, position + 1)
        require(next_position >= 0, f"{label}: missing {needle!r}")
        require(next_position > position, f"{label}: order drifted at {needle!r}")
        position = next_position


def braced_definition(text: str, signature: str, label: str) -> str:
    start = text.find(signature)
    require(start >= 0, f"{label}: signature missing")
    brace = text.find("{", start + len(signature))
    require(brace >= 0, f"{label}: opening brace missing")
    depth = 0
    index = brace
    state = "code"
    while index < len(text):
        char = text[index]
        pair = text[index : index + 2]
        if state == "code":
            if pair == "//":
                state = "line_comment"
                index += 2
                continue
            if pair == "/*":
                state = "block_comment"
                index += 2
                continue
            if char == '"':
                state = "string"
            elif char == "'":
                state = "character"
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        elif state == "line_comment":
            if char == "\n":
                state = "code"
        elif state == "block_comment":
            if pair == "*/":
                state = "code"
                index += 2
                continue
        elif state in ("string", "character"):
            if char == "\\":
                index += 2
                continue
            if (state == "string" and char == '"') or (
                state == "character" and char == "'"
            ):
                state = "code"
        index += 1
    raise ContractError(f"{label}: unterminated definition")


def read_sources(root: Path) -> dict[str, str]:
    require(root.is_dir(), f"source root missing: {root}")
    sources: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = root / relative
        require(path.is_file(), f"source file missing: {relative}")
        sources[relative] = path.read_text(encoding="utf-8")
    return sources


def source_digest(sources: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for relative in SOURCE_PATHS:
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(sources[relative].encode())
        digest.update(b"\0")
    return digest.hexdigest()


def validate(sources: dict[str, str]) -> dict[str, object]:
    depth_api = sources["source/blender/editors/include/ED_view3d.hh"]
    depth_impl = sources["source/blender/editors/space_view3d/view3d_draw.cc"]
    paint_api = sources["source/blender/editors/sculpt_paint/paint_intern.hh"]
    projection = sources[
        "source/blender/editors/sculpt_paint/mesh/paint_image_proj.cc"
    ]
    operator = sources[
        "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc"
    ]
    framebuffer_api = sources["source/blender/gpu/GPU_framebuffer.hh"]
    readback_api = sources["source/blender/gpu/GPU_readback.hh"]

    require_ordered(
        depth_api,
        (
            "class ViewportDepthPickSession",
            "bool init(ARegion *region, const int mval[2]);",
            "ReadbackState state();",
            "bool sample(ARegion *region, float r_world_location[3]);",
        ),
        "owned progressive-depth API",
    )
    require(
        "GPU_framebuffer_read_depth_async(" in framebuffer_api,
        "owned framebuffer-depth API missing",
    )
    require(
        "GPU_readback_cancel(GPUReadback *&readback);" in readback_api,
        "owned cancellation API missing",
    )
    depth_init = braced_definition(
        depth_impl,
        "bool ViewportDepthPickSession::init(ARegion *region, const int mval[2])",
        "progressive-depth init",
    )
    require(
        "GPU_framebuffer_read_depth_async(depth_read_fb" in depth_init
        and "GPU_framebuffer_read_depth(depth_read_fb" not in depth_init,
        "progressive-depth primitive is not asynchronous",
    )

    for text, copyright_line, provenance, label in (
        (
            paint_api,
            "SPDX-FileCopyrightText: 2008 Blender Authors",
            "Ported for the web from source/blender/editors/sculpt_paint/paint_intern.hh @ fbe6228777e7",
            "paint API",
        ),
        (
            projection,
            "SPDX-FileCopyrightText: 2001-2002 NaN Holding BV. All rights reserved.",
            "Ported for the web from source/blender/editors/sculpt_paint/mesh/paint_image_proj.cc @",
            "projection source",
        ),
        (
            operator,
            "SPDX-FileCopyrightText: 2001-2002 NaN Holding BV. All rights reserved.",
            "Ported for the web from source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc @",
            "paint operator",
        ),
    ):
        require(
            copyright_line in text
            and "SPDX-FileCopyrightText: 2026 blender-web contributors" in text
            and provenance in text
            and "fbe6228777e7." in text,
            f"{label}: derived-file provenance missing",
        )

    require_ordered(
        paint_api,
        (
            "enum class PaintProjStrokeResult : int8_t",
            "Complete,",
            "Pending,",
            "Failed,",
            "PaintProjStrokeResult paint_proj_stroke(",
            "PaintProjStrokeResult paint_proj_stroke_readback_poll(",
            "void paint_proj_stroke_done(void *ps_handle_p);",
        ),
        "projection-paint owned API",
    )

    require_ordered(
        projection,
        (
            "struct ProjStrokeHandle",
            "bool is_clone_cursor_pick;",
            "ViewportDepthPickSession clone_cursor_readback;",
            "Scene *clone_cursor_scene = nullptr;",
            "View3D *clone_cursor_view3d = nullptr;",
            "RegionView3D *clone_cursor_region_view = nullptr;",
            "ARegion *clone_cursor_region = nullptr;",
            "wmWindow *clone_cursor_window = nullptr;",
            "int clone_cursor_mval[2] = {0, 0};",
            "float clone_cursor_before[3] = {0.0f, 0.0f, 0.0f};",
            "PaintProjStrokeResult clone_cursor_result = PaintProjStrokeResult::Complete;",
        ),
        "clone-cursor owned state",
    )

    context_guard = braced_definition(
        projection,
        "static bool paint_proj_clone_cursor_readback_context_matches(",
        "clone-cursor context guard",
    )
    for needle in (
        "CTX_wm_window(C) == ps_handle->clone_cursor_window",
        "CTX_data_scene(C) == ps_handle->clone_cursor_scene",
        "CTX_wm_view3d(C) == ps_handle->clone_cursor_view3d",
        "CTX_wm_region(C) == ps_handle->clone_cursor_region",
        "ps_handle->clone_cursor_region->regiondata == ps_handle->clone_cursor_region_view",
    ):
        require(needle in context_guard, f"context guard missing {needle!r}")

    poll = braced_definition(
        projection,
        "PaintProjStrokeResult paint_proj_stroke_readback_poll(",
        "clone-cursor poll",
    )
    require_ordered(
        poll,
        (
            "ps_handle->clone_cursor_result != PaintProjStrokeResult::Pending",
            "ps_handle->clone_cursor_readback.state()",
            "ReadbackState::Pending",
            "ReadbackState::Failed",
            "paint_proj_clone_cursor_readback_context_matches(C, ps_handle)",
            "equals_v3v3(ps_handle->clone_cursor_scene->cursor.location,",
            "ps_handle->clone_cursor_before",
            "ps_handle->clone_cursor_readback.sample(",
            "ps_handle->clone_cursor_region, cursor)",
            "PaintProjStrokeResult::Complete",
            "if (!has_depth)",
            "copy_v3_v3(ps_handle->clone_cursor_scene->cursor.location, cursor);",
            "DEG_id_tag_update(&ps_handle->clone_cursor_scene->id, ID_RECALC_SYNC_TO_EVAL);",
            "ED_region_tag_redraw(ps_handle->clone_cursor_region);",
        ),
        "settled clone-cursor replay",
    )

    stroke = braced_definition(
        projection,
        "PaintProjStrokeResult paint_proj_stroke(const bContext *C,",
        "projection stroke",
    )
    require_ordered(
        stroke,
        (
            "if (ps_handle->is_clone_cursor_pick)",
            "view3d_operator_needs_gpu(C);",
            "ED_view3d_depth_override(",
            "ps_handle->clone_cursor_scene = scene;",
            "ps_handle->clone_cursor_view3d = v3d;",
            "ps_handle->clone_cursor_region_view = static_cast<RegionView3D *>(region->regiondata);",
            "ps_handle->clone_cursor_window = CTX_wm_window(C);",
            "copy_v2_v2_int(ps_handle->clone_cursor_mval, mval_i);",
            "copy_v3_v3(ps_handle->clone_cursor_before, scene->cursor.location);",
            "ps_handle->clone_cursor_readback.init(region, mval_i)",
            "PaintProjStrokeResult::Pending",
            "paint_proj_stroke_readback_poll(C, ps_handle)",
            "paint_proj_stroke_ps(",
            "return PaintProjStrokeResult::Complete;",
        ),
        "kick and native-immediate projection stroke",
    )
    require(
        "ED_view3d_autodist(" not in stroke
        and "GPU_framebuffer_read_depth(" not in stroke
        and "GPU_texture_read(" not in stroke,
        "clone-cursor stroke retains synchronous GPU readback",
    )

    cleanup = braced_definition(
        projection,
        "void paint_proj_stroke_done(void *ps_handle_p)",
        "projection cleanup",
    )
    require_ordered(
        cleanup,
        (
            "if (ps_handle->is_clone_cursor_pick)",
            "MEM_delete(ps_handle);",
            "return;",
        ),
        "owned session destruction",
    )

    abstract_mode = braced_definition(operator, "class AbstractPaintMode", "paint mode API")
    for needle in (
        "virtual PaintProjStrokeResult paint_stroke(",
        "virtual PaintProjStrokeResult paint_stroke_readback_poll(",
        "return PaintProjStrokeResult::Complete;",
    ):
        require(needle in abstract_mode, f"paint mode API missing {needle!r}")
    projection_mode = braced_definition(operator, "class ProjectionPaintMode", "projection mode")
    require_ordered(
        projection_mode,
        (
            "PaintProjStrokeResult paint_stroke(",
            "return paint_proj_stroke(",
            "PaintProjStrokeResult paint_stroke_readback_poll(",
            "return paint_proj_stroke_readback_poll(C, stroke_handle);",
        ),
        "projection mode forwarding",
    )

    require_ordered(
        operator,
        (
            "struct PaintOperation : public PaintModeData",
            "PaintProjStrokeResult readback_result = PaintProjStrokeResult::Complete;",
            "wmTimer *readback_timer = nullptr;",
            "wmWindow *readback_window = nullptr;",
            "int readback_tick_count = 0;",
            "wmEvent deferred_finish_event = {};",
            "bool finish_deferred = false;",
            "const int invoke_event_type_;",
            "bool is_finish_event(const wmEvent *event) const;",
        ),
        "paint-operator retained state",
    )
    finish_event = braced_definition(
        operator, "bool ImagePaintStroke::is_finish_event(", "finish-event classifier"
    )
    require(
        "event->type == invoke_event_type_ && event->val == KM_RELEASE" in finish_event
        and "ELEM(event->type, EVT_RETKEY, EVT_SPACEKEY)" in finish_event,
        "finish-event classifier drifted",
    )

    timer_remove = braced_definition(
        operator,
        "static void image_paint_readback_timer_remove(",
        "readback timer cleanup",
    )
    require_ordered(
        timer_remove,
        (
            "if (pop->readback_timer != nullptr)",
            "WM_event_timer_remove(",
            "pop->readback_window",
            "pop->readback_timer = nullptr;",
            "pop->readback_window = nullptr;",
            "pop->readback_tick_count = 0;",
        ),
        "readback timer cleanup",
    )
    update = braced_definition(
        operator, "void ImagePaintStroke::update_step(", "paint update"
    )
    require_ordered(
        update,
        (
            "pop->readback_result = pop->mode->paint_stroke(",
            "pop->readback_result == PaintProjStrokeResult::Pending",
            "pop->readback_tick_count = 0;",
            "copy_v2_v2(pop->prevmouse, mouse);",
        ),
        "latest motion ownership",
    )
    done = braced_definition(operator, "void ImagePaintStroke::done(", "paint cleanup")
    require_ordered(
        done,
        (
            "image_paint_readback_timer_remove(this->evil_C, pop);",
            "pop->finish_deferred = false;",
            "pop->mode->paint_stroke_done(pop->stroke_handle);",
            "pop->stroke_handle = nullptr;",
        ),
        "paint cleanup",
    )

    invoke = braced_definition(operator, "static wmOperatorStatus paint_invoke(", "paint invoke")
    require(
        "ELEM(retval, OPERATOR_FINISHED, OPERATOR_CANCELLED)" in invoke
        and "stroke->cancel(C);" in invoke,
        "initial terminal cleanup is incomplete",
    )
    modal = braced_definition(operator, "static wmOperatorStatus paint_modal(", "paint modal")
    require_ordered(
        modal,
        (
            "event->type == TIMER",
            "event->customdata == pop->readback_timer",
            "constexpr int max_tick_count = 240;",
            "if (++pop->readback_tick_count > max_tick_count)",
            "pop->mode->paint_stroke_readback_poll(C, pop->stroke_handle)",
            "PaintProjStrokeResult::Pending",
            "image_paint_readback_timer_remove(C, pop);",
            "PaintProjStrokeResult::Failed",
            "if (pop->finish_deferred)",
            "wmEvent finish_event = pop->deferred_finish_event;",
            "finish_event.customdata = nullptr;",
            "paint_modal_dispatch(C, op, stroke, &finish_event)",
            "pop->readback_result == PaintProjStrokeResult::Pending",
            "stroke->is_finish_event(event)",
            "event->customdata != nullptr",
            "pop->deferred_finish_event = *event;",
            "pop->finish_deferred = true;",
            "image_paint_readback_timer_ensure(C, pop)",
            "if (pop->finish_deferred)",
            "event->type == EVT_MODAL_MAP",
            "paint_modal_dispatch(C, op, stroke, event)",
        ),
        "bounded finish continuation",
    )
    require(
        modal.count("paint_modal_readback_cancel(") >= 4,
        "failure paths do not converge on cancellation",
    )

    return {
        "verdict": "PASS",
        "pin": PIN,
        "contracts": {
            "shared_owned_progressive_depth": True,
            "native_immediate_completion": True,
            "clone_cursor_exact_request": True,
            "latest_motion_supersedes_pending": True,
            "cursor_and_context_drift_guard": True,
            "deferred_finish_event_replay": True,
            "bounded_timer_failure_cancellation": True,
            "non_clone_passthrough": True,
            "live_hardware_receipt": False,
        },
        "converted_consumer": "painting",
        "remaining_depth_pick_consumers": ["zoom_border", "ndof"],
        "remaining_sync_family_count": 3,
        "source_count": len(SOURCE_PATHS),
        "source_sha256": source_digest(sources),
    }


def run_selfcheck(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        (
            "source/blender/editors/sculpt_paint/paint_intern.hh",
            "PaintProjStrokeResult paint_proj_stroke_readback_poll(",
            "void paint_proj_stroke_readback_poll_removed(",
            "public poll API",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_proj.cc",
            "ViewportDepthPickSession clone_cursor_readback;",
            "int clone_cursor_readback;",
            "owned session",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_proj.cc",
            "CTX_data_scene(C) == ps_handle->clone_cursor_scene",
            "true",
            "scene guard",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_proj.cc",
            "equals_v3v3(ps_handle->clone_cursor_scene->cursor.location,",
            "equals_v3v3_removed(ps_handle->clone_cursor_scene->cursor.location,",
            "cursor mutation guard",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_proj.cc",
            "ps_handle->clone_cursor_readback.sample(",
            "ps_handle->clone_cursor_readback.sample_removed(",
            "settled sample",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_proj.cc",
            "copy_v3_v3(ps_handle->clone_cursor_scene->cursor.location, cursor);",
            "copy_v3_v3_removed(ps_handle->clone_cursor_scene->cursor.location, cursor);",
            "cursor commit",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_proj.cc",
            "ps_handle->clone_cursor_readback.init(region, mval_i)",
            "false",
            "owned kick",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc",
            "wmEvent deferred_finish_event = {};",
            "int deferred_finish_event = 0;",
            "finish event ownership",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc",
            "pop->readback_result = pop->mode->paint_stroke(",
            "pop->mode->paint_stroke(",
            "update result ownership",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc",
            "image_paint_readback_timer_remove(this->evil_C, pop);",
            "image_paint_readback_timer_remove_missing(this->evil_C, pop);",
            "cleanup",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc",
            "event->customdata == pop->readback_timer",
            "true",
            "timer identity",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc",
            "if (++pop->readback_tick_count > max_tick_count)",
            "if (false)",
            "bounded timeout",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc",
            "finish_event.customdata = nullptr;",
            "finish_event.customdata = pop;",
            "replay sanitization",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc",
            "event->customdata != nullptr",
            "false",
            "unsafe event rejection",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc",
            "pop->deferred_finish_event = *event;",
            "pop->finish_deferred = true;",
            "exact event retention",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc",
            "ELEM(retval, OPERATOR_FINISHED, OPERATOR_CANCELLED)",
            "retval == OPERATOR_FINISHED",
            "initial cancel cleanup",
        ),
    )
    for relative, before, after, label in mutations:
        mutated = dict(sources)
        text = mutated[relative]
        require(before in text, f"selfcheck setup missing {label!r}")
        mutated[relative] = text.replace(before, after, 1)
        try:
            validate(mutated)
        except ContractError:
            continue
        raise ContractError(f"selfcheck mutation passed: {label}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    sources = read_sources(args.source_root.resolve())
    if args.selfcheck:
        run_selfcheck(sources)
        print("M5_PAINTING_DEPTH_SOURCE_SELFCHECK_PASS mutations=16")
        return 0
    receipt = validate(sources)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(
        "M5_PAINTING_DEPTH_SOURCE_PASS "
        f"files={receipt['source_count']} sha256={receipt['source_sha256']} "
        "remaining_sync=3 live_receipt=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"M5_PAINTING_DEPTH_SOURCE_FAIL {error}")
        raise SystemExit(1)
