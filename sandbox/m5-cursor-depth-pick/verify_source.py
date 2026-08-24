#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed source contract for the owned cursor depth-pick continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PIN = "fbe6228777e7d9afefcd61a413844e790ae75db7"
SOURCE_PATHS = (
    "source/blender/editors/include/ED_view3d.hh",
    "source/blender/editors/space_view3d/view3d_draw.cc",
    "source/blender/editors/space_view3d/view3d_edit.cc",
    "source/blender/gpu/GPU_framebuffer.hh",
    "source/blender/gpu/GPU_readback.hh",
    "source/blender/gpu/intern/gpu_framebuffer.cc",
    "source/blender/windowmanager/intern/wm_draw.cc",
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
            if (state == "string" and char == '"') or (state == "character" and char == "'"):
                state = "code"
        index += 1
    raise ContractError(f"{label}: unterminated definition")


def read_sources(root: Path) -> dict[str, str]:
    require(root.is_dir(), f"source root missing: {root}")
    result: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = root / relative
        require(path.is_file(), f"source file missing: {relative}")
        result[relative] = path.read_text(encoding="utf-8")
    return result


def source_digest(sources: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(sources):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sources[relative].encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def validate(sources: dict[str, str]) -> dict[str, object]:
    api = sources["source/blender/editors/include/ED_view3d.hh"]
    draw = sources["source/blender/editors/space_view3d/view3d_draw.cc"]
    edit = sources["source/blender/editors/space_view3d/view3d_edit.cc"]
    framebuffer_api = sources["source/blender/gpu/GPU_framebuffer.hh"]
    readback_api = sources["source/blender/gpu/GPU_readback.hh"]
    framebuffer_frontend = sources["source/blender/gpu/intern/gpu_framebuffer.cc"]
    wm_draw = sources["source/blender/windowmanager/intern/wm_draw.cc"]

    require_ordered(
        api,
        (
            "class ViewportDepthPickSession",
            "struct Impl;",
            "Impl *impl_ = nullptr;",
            "ViewportDepthPickSession(const ViewportDepthPickSession &) = delete;",
            "bool init(ARegion *region, const int mval[2]);",
            "ReadbackState state();",
            "bool sample(ARegion *region, float r_world_location[3]);",
        ),
        "owned depth-pick API",
    )
    for needle in (
        "GPUReadback *GPU_framebuffer_read_depth_async(",
        "eGPUReadbackStatus GPU_readback_status(GPUReadback *readback);",
        "bool GPU_readback_consume(GPUReadback *&readback, void *dst, size_t dst_len);",
    ):
        require(
            needle in framebuffer_api or needle in readback_api,
            f"owned GPU primitive missing {needle!r}",
        )
    require(
        "return fb->read_async(GPU_DEPTH_BIT, format, rect, 1, 1);" in framebuffer_frontend,
        "framebuffer depth request does not use owned backend result",
    )

    destructor = braced_definition(
        draw,
        "ViewportDepthPickSession::~ViewportDepthPickSession()",
        "depth-pick destructor",
    )
    require_ordered(
        destructor,
        ("GPU_readback_cancel(impl_->readback);", "MEM_delete(impl_);", "impl_ = nullptr;"),
        "depth-pick destruction order",
    )
    init = braced_definition(
        draw,
        "bool ViewportDepthPickSession::init(ARegion *region, const int mval[2])",
        "depth-pick init",
    )
    require_ordered(
        init,
        (
            "copy_m4_m4(impl->viewinv, impl->region_view->viewinv);",
            "copy_m4_m4(impl->winmat, impl->region_view->winmat);",
            "int(2.0f * U.pixelsize)",
            "int(4.0f * U.pixelsize)",
            "impl->sample_rect_valid[i] = view3d_depth_pick_rect_clamp",
            "impl->request_rect = impl->sample_rects[i];",
            "GPU_framebuffer_ensure_config(&depth_read_fb",
            "GPU_framebuffer_read_depth_async(depth_read_fb",
            "GPU_framebuffer_restore();",
            "GPU_framebuffer_free(depth_read_fb);",
            "impl->readback_state = ReadbackState::Pending;",
        ),
        "exact depth request",
    )
    require(
        "GPU_framebuffer_read_depth(depth_read_fb" not in init,
        "depth-pick init regressed to synchronous framebuffer read",
    )
    state = braced_definition(
        draw, "ViewportDepthPickSession::ReadbackState ViewportDepthPickSession::state()", "state"
    )
    require_ordered(
        state,
        (
            "GPU_readback_status(impl_->readback)",
            "status == GPU_READBACK_PENDING",
            "GPU_readback_size(impl_->readback) != impl_->expected_size",
            "GPU_readback_consume(",
            "if (!impl_->sample_rect_valid[sample_index])",
            "if (depth > 0.0f && depth < nearest)",
            "if (nearest < 1.0f)",
            "impl_->readback_state = ReadbackState::Ready;",
        ),
        "progressive settle",
    )
    sample = braced_definition(
        draw,
        "bool ViewportDepthPickSession::sample(ARegion *region, float r_world_location[3])",
        "depth sample",
    )
    require_ordered(
        sample,
        (
            "state() != ReadbackState::Ready",
            "region != impl_->region",
            "region->regiondata != impl_->region_view",
            "region->winx != impl_->region_size[0]",
            "!equals_m4m4(static_cast<RegionView3D *>(region->regiondata)->viewinv",
            "!equals_m4m4(static_cast<RegionView3D *>(region->regiondata)->winmat",
            "impl_->readback_state = ReadbackState::Failed;",
            "if (impl_->depth == FLT_MAX)",
            "ED_view3d_unproject_v3(region",
            "float(impl_->mval[0]) + 0.5f",
        ),
        "exact view replay",
    )

    forced_position = braced_definition(
        edit,
        "static void view3d_cursor3d_position_rotation_ex(bContext *C",
        "forced cursor position",
    )
    require_ordered(
        forced_position,
        (
            "if (depth_location != nullptr)",
            "copy_v3_v3(r_cursor_co, depth_location);",
            "ED_view3d_cursor3d_position(C, mval, use_depth, r_cursor_co);",
        ),
        "forced depth application",
    )
    for needle in (
        "Scene *scene = nullptr;",
        "View3D *view3d = nullptr;",
        "ARegion *region = nullptr;",
        "wmWindow *timer_window = nullptr;",
    ):
        require(needle in edit, f"producing cursor context missing {needle!r}")
    cleanup = braced_definition(
        edit,
        "static void view3d_cursor3d_depth_read_free(bContext *C, wmOperator *op)",
        "cursor cleanup",
    )
    require_ordered(
        cleanup,
        (
            "BLI_remlink(&view3d_cursor_depth_reads, read);",
            "WM_event_timer_remove(CTX_wm_manager(C), read->timer_window, read->timer);",
            "MEM_delete(read);",
            "op->customdata = nullptr;",
        ),
        "cursor cleanup order",
    )
    registration = braced_definition(
        edit,
        "static void view3d_cursor3d_depth_read_register(View3DCursorDepthRead *read)",
        "cursor registration",
    )
    require_ordered(
        registration,
        (
            "active->timer_window == read->timer_window",
            "active->superseded = true;",
            "BLI_addtail(&view3d_cursor_depth_reads, read);",
            "read->listed = true;",
        ),
        "newest cursor request wins",
    )
    cursor_match = braced_definition(
        edit,
        "static bool view3d_cursor3d_depth_read_cursor_matches(const View3DCursor &a",
        "cursor snapshot guard",
    )
    require_ordered(
        cursor_match,
        (
            "equals_v3v3(a.location, b.location)",
            "equals_v4v4(a.rotation_quaternion, b.rotation_quaternion)",
            "equals_v3v3(a.rotation_euler, b.rotation_euler)",
            "equals_v3v3(a.rotation_axis, b.rotation_axis)",
            "a.rotation_angle == b.rotation_angle",
            "a.rotation_mode == b.rotation_mode",
        ),
        "complete cursor snapshot",
    )
    context_match = braced_definition(
        edit,
        "static bool view3d_cursor3d_depth_read_context_matches(",
        "cursor context guard",
    )
    require_ordered(
        context_match,
        (
            "CTX_data_scene(C) == read->scene",
            "CTX_wm_view3d(C) == read->view3d",
            "CTX_wm_region(C) == read->region",
            "CTX_wm_window(C) == read->timer_window",
        ),
        "complete producing context",
    )
    apply = braced_definition(
        edit,
        "static wmOperatorStatus view3d_cursor3d_depth_read_apply(bContext *C, wmOperator *op)",
        "cursor apply",
    )
    require_ordered(
        apply,
        (
            "view3d_cursor3d_depth_read_context_matches(C, read)",
            "view3d_cursor3d_depth_read_cursor_matches(read->cursor_before",
            "read->scene->cursor",
            "view3d_cursor3d_depth_read_free(C, op);",
            "read->session.sample(read->region, depth_location)",
            "read->session.state() == ViewportDepthPickSession::ReadbackState::Failed",
            "view3d_cursor3d_update_ex(C",
            "read->mval",
            "read->orientation",
            "has_depth ? depth_location : nullptr",
            "view3d_cursor3d_depth_read_free(C, op);",
        ),
        "cursor exact replay",
    )
    modal = braced_definition(
        edit,
        "static wmOperatorStatus view3d_cursor3d_modal(bContext *C",
        "cursor modal",
    )
    require_ordered(
        modal,
        (
            "if (read->superseded)",
            "view3d_cursor3d_depth_read_free(C, op);",
            "if (!view3d_cursor3d_depth_read_context_matches(C, read))",
            "event->type != TIMER || event->customdata != read->timer",
            "OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH",
            "constexpr int max_tick_count = 240;",
            "if (++read->tick_count > max_tick_count)",
            "read->session.state();",
            "ReadbackState::Pending",
            "ReadbackState::Failed",
            "view3d_cursor3d_depth_read_apply(C, op)",
        ),
        "bounded cursor continuation",
    )
    invoke = braced_definition(
        edit,
        "static wmOperatorStatus view3d_cursor3d_invoke(bContext *C",
        "cursor invoke",
    )
    require_ordered(
        invoke,
        (
            "if (!use_depth)",
            "ED_view3d_cursor3d_update(C, event->mval, false, orientation);",
            "ED_view3d_depth_override(",
            "read->scene = CTX_data_scene(C);",
            "read->view3d = v3d;",
            "read->region = region;",
            "read->timer_window = CTX_wm_window(C);",
            "copy_v2_v2_int(read->mval, event->mval);",
            "read->orientation = orientation;",
            "read->cursor_before = read->scene->cursor;",
            "read->session.init(region, read->mval)",
            "view3d_cursor3d_depth_read_register(read);",
            "ReadbackState::Ready",
            "view3d_cursor3d_depth_read_apply(C, op)",
            "WM_event_timer_add(",
            "WM_event_add_modal_handler(C, op);",
            "OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH",
        ),
        "cursor kick and continuation",
    )
    require(
        "ED_view3d_cursor3d_update(C, event->mval, use_depth, orientation)" not in invoke,
        "cursor invoke still reaches synchronous depth read",
    )
    for needle in (
        "ot->invoke = view3d_cursor3d_invoke;",
        "ot->modal = view3d_cursor3d_modal;",
        "ot->cancel = view3d_cursor3d_cancel;",
    ):
        require(needle in edit, f"cursor callback wiring missing {needle!r}")

    remaining_sync = {
        "depth_pick": "GPU_framebuffer_read_depth(depth_read_fb",
        "depth_cache": "GPU_texture_read(depth_tx, GPU_DATA_FLOAT, 0)",
        "window_capture": "GPU_offscreen_read_color(offscreen, GPU_DATA_UBYTE, rect);",
    }
    require(remaining_sync["depth_pick"] in draw, "remaining depth-pick callers disappeared")
    require(remaining_sync["depth_cache"] in draw, "remaining depth cache disappeared")
    require(remaining_sync["window_capture"] in wm_draw, "remaining WM capture disappeared")
    require(
        "ED_view3d_autodist(region, v3d, mval, r_cursor_co, nullptr)" in edit,
        "residual depth-pick accounting unexpectedly vanished",
    )

    return {
        "verdict": "PASS",
        "pin": PIN,
        "contracts": {
            "owned_exact_depth_request": True,
            "progressive_margin_precedence": True,
            "view_transform_drift_rejected": True,
            "native_immediate_completion": True,
            "cursor_modal_continuation": True,
            "exact_event_orientation_replay": True,
            "superseded_cursor_rejected": True,
            "late_cursor_mutation_rejected": True,
            "producing_context_drift_rejected": True,
            "bounded_failure_cancellation": True,
            "live_hardware_receipt": False,
        },
        "converted_consumer": "view3d_cursor3d",
        "remaining_sync_families": sorted(remaining_sync),
        "remaining_sync_family_count": len(remaining_sync),
        "source_count": len(SOURCE_PATHS),
        "source_sha256": source_digest(sources),
    }


def run_selfcheck(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        (
            "source/blender/editors/space_view3d/view3d_draw.cc",
            "GPU_framebuffer_read_depth_async(depth_read_fb",
            "GPU_framebuffer_read_depth(depth_read_fb",
            "async request",
        ),
        (
            "source/blender/editors/space_view3d/view3d_draw.cc",
            "int(4.0f * U.pixelsize)",
            "int(0.0f * U.pixelsize)",
            "outer margin",
        ),
        (
            "source/blender/editors/space_view3d/view3d_draw.cc",
            "GPU_readback_size(impl_->readback) != impl_->expected_size",
            "GPU_readback_size(impl_->readback) > impl_->expected_size",
            "exact byte size",
        ),
        (
            "source/blender/editors/space_view3d/view3d_draw.cc",
            "!equals_m4m4(static_cast<RegionView3D *>(region->regiondata)->viewinv, impl_->viewinv)",
            "false",
            "view-transform guard",
        ),
        (
            "source/blender/editors/space_view3d/view3d_edit.cc",
            "read->session.sample(read->region, depth_location)",
            "false",
            "settled sample",
        ),
        (
            "source/blender/editors/space_view3d/view3d_edit.cc",
            "read->mval,\n                            has_depth",
            "event->mval,\n                            has_depth",
            "exact event replay",
        ),
        (
            "source/blender/editors/space_view3d/view3d_edit.cc",
            "read->cursor_before = read->scene->cursor;",
            "/* cursor snapshot removed */",
            "cursor snapshot guard",
        ),
        (
            "source/blender/editors/space_view3d/view3d_edit.cc",
            "view3d_cursor3d_depth_read_context_matches(C, read)",
            "false",
            "producing context guard",
        ),
        (
            "source/blender/editors/space_view3d/view3d_edit.cc",
            "active->superseded = true;",
            "active->superseded = false;",
            "superseded request",
        ),
        (
            "source/blender/editors/space_view3d/view3d_edit.cc",
            "constexpr int max_tick_count = 240;",
            "constexpr int max_tick_count = 0;",
            "bounded timer",
        ),
        (
            "source/blender/editors/space_view3d/view3d_edit.cc",
            "WM_event_add_modal_handler(C, op);",
            "/* modal handler removed */",
            "modal admission",
        ),
        (
            "source/blender/editors/space_view3d/view3d_edit.cc",
            "ot->cancel = view3d_cursor3d_cancel;",
            "ot->cancel = nullptr;",
            "cancel wiring",
        ),
        (
            "source/blender/editors/space_view3d/view3d_edit.cc",
            "has_depth ? depth_location : nullptr",
            "nullptr",
            "forced depth result",
        ),
    )
    for relative, before, after, label in mutations:
        require(before in sources[relative], f"selfcheck fixture drifted: {label}")
        mutated = dict(sources)
        mutated[relative] = sources[relative].replace(before, after, 1)
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
        print("M5_CURSOR_DEPTH_PICK_SOURCE_SELFCHECK_PASS mutations=13")
        return 0

    receipt = validate(sources)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(
        "M5_CURSOR_DEPTH_PICK_SOURCE_PASS "
        f"sources={receipt['source_count']} sha256={receipt['source_sha256'][:12]} "
        f"remaining_sync={receipt['remaining_sync_family_count']} live_receipt=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"M5_CURSOR_DEPTH_PICK_SOURCE_FAIL {error}")
        raise SystemExit(1)
