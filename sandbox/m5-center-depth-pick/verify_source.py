#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed source contract for the owned view-center depth continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PIN = "fbe6228777e7d9afefcd61a413844e790ae75db7"
SOURCE_PATHS = (
    "source/blender/editors/include/ED_view3d.hh",
    "source/blender/editors/space_view3d/view3d_draw.cc",
    "source/blender/editors/space_view3d/view3d_navigate_view_center_pick.cc",
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
    center = sources[
        "source/blender/editors/space_view3d/view3d_navigate_view_center_pick.cc"
    ]
    framebuffer_api = sources["source/blender/gpu/GPU_framebuffer.hh"]
    readback_api = sources["source/blender/gpu/GPU_readback.hh"]

    require_ordered(
        api,
        (
            "class ViewportDepthPickSession",
            "bool init(ARegion *region, const int mval[2]);",
            "ReadbackState state();",
            "bool sample(ARegion *region, float r_world_location[3]);",
        ),
        "owned depth-pick API",
    )
    require(
        "GPU_framebuffer_read_depth_async(" in framebuffer_api,
        "owned framebuffer-depth request missing",
    )
    require(
        "GPU_readback_consume(GPUReadback *&readback" in readback_api,
        "owned readback consume API missing",
    )
    depth_init = braced_definition(
        draw,
        "bool ViewportDepthPickSession::init(ARegion *region, const int mval[2])",
        "depth-pick init",
    )
    require(
        "GPU_framebuffer_read_depth_async(depth_read_fb" in depth_init and
        "GPU_framebuffer_read_depth(depth_read_fb" not in depth_init,
        "depth-pick primitive is not non-blocking",
    )

    require("#include \"BLI_listbase.h\"" in center, "active-request list include missing")
    require_ordered(
        center,
        (
            "struct ViewCenterPickDepthRead",
            "ViewCenterPickDepthRead *next = nullptr;",
            "ViewportDepthPickSession session;",
            "View3D *view3d = nullptr;",
            "RegionView3D *region_view = nullptr;",
            "ARegion *region = nullptr;",
            "wmTimer *timer = nullptr;",
            "wmWindow *timer_window = nullptr;",
            "int mval[2] = {0, 0};",
            "int smooth_viewtx = 0;",
            "float ofs[3] = {0.0f, 0.0f, 0.0f};",
            "float viewquat[4] = {0.0f, 0.0f, 0.0f, 0.0f};",
            "bool listed = false;",
            "bool superseded = false;",
        ),
        "owned center-pick state",
    )

    view_matches = braced_definition(
        center,
        "static bool viewcenter_pick_depth_read_view_matches(",
        "view snapshot guard",
    )
    for needle in (
        "equals_v3v3(read->region_view->ofs, read->ofs)",
        "equals_v4v4(read->region_view->viewquat, read->viewquat)",
        "read->region_view->dist == read->dist",
        "read->region_view->camdx == read->camdx",
        "read->region_view->camdy == read->camdy",
        "read->region_view->camzoom == read->camzoom",
        "read->region_view->persp == read->persp",
        "read->region_view->view == read->view",
        "read->region_view->view_axis_roll == read->view_axis_roll",
        "read->region_view->sms == nullptr",
        "read->region_view->smooth_timer == nullptr",
    ):
        require(needle in view_matches, f"view snapshot guard missing {needle!r}")

    context_matches = braced_definition(
        center,
        "static bool viewcenter_pick_depth_read_context_matches(",
        "producing context guard",
    )
    require_ordered(
        context_matches,
        (
            "CTX_wm_view3d(C) == read->view3d",
            "CTX_wm_region_view3d(C) == read->region_view",
            "CTX_wm_region(C) == read->region",
            "CTX_wm_window(C) == read->timer_window",
            "viewcenter_pick_depth_read_view_matches(read)",
        ),
        "producing context guard",
    )

    registration = braced_definition(
        center,
        "static void viewcenter_pick_depth_read_register(ViewCenterPickDepthRead *read)",
        "center registration",
    )
    require_ordered(
        registration,
        (
            "active->timer_window == read->timer_window",
            "active->region == read->region",
            "active->superseded = true;",
            "BLI_addtail(&viewcenter_pick_depth_reads, read);",
            "read->listed = true;",
        ),
        "newest center request wins",
    )

    cleanup = braced_definition(
        center,
        "static void viewcenter_pick_depth_read_free(bContext *C, wmOperator *op)",
        "center cleanup",
    )
    require_ordered(
        cleanup,
        (
            "BLI_remlink(&viewcenter_pick_depth_reads, read);",
            "WM_event_timer_remove(CTX_wm_manager(C), read->timer_window, read->timer);",
            "MEM_delete(read);",
            "op->customdata = nullptr;",
        ),
        "center cleanup order",
    )

    smooth_apply = braced_definition(
        center,
        "static void viewcenter_pick_smooth_apply(bContext *C",
        "center smooth application",
    )
    require_ordered(
        smooth_apply,
        (
            "if (depth_location != nullptr)",
            "copy_v3_v3(ofs_new, depth_location);",
            "negate_v3_v3(ofs_new, read->region_view->ofs);",
            "ED_view3d_win_to_3d_int(",
            "read->mval",
            "negate_v3(ofs_new);",
            "sview.ofs = ofs_new;",
            "sview.undo_str = op->type->name;",
            "ED_view3d_smooth_view(",
            "read->smooth_viewtx",
        ),
        "stock hit/fallback semantics",
    )

    apply = braced_definition(
        center,
        "static wmOperatorStatus viewcenter_pick_depth_read_apply(bContext *C, wmOperator *op)",
        "center settled apply",
    )
    require_ordered(
        apply,
        (
            "viewcenter_pick_depth_read_context_matches(C, read)",
            "read->session.sample(read->region, depth_location)",
            "read->session.state() == ViewportDepthPickSession::ReadbackState::Failed",
            "viewcenter_pick_smooth_apply(C, op, read, has_depth ? depth_location : nullptr);",
            "viewcenter_pick_depth_read_free(C, op);",
            "return OPERATOR_FINISHED;",
        ),
        "settled center replay",
    )

    modal = braced_definition(
        center,
        "static wmOperatorStatus viewcenter_pick_modal(bContext *C",
        "center modal continuation",
    )
    require_ordered(
        modal,
        (
            "if (read->superseded)",
            "viewcenter_pick_depth_read_free(C, op);",
            "if (!viewcenter_pick_depth_read_context_matches(C, read))",
            "event->type == EVT_ESCKEY && event->val == KM_PRESS",
            "event->type != TIMER || event->customdata != read->timer",
            "OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH",
            "constexpr int max_tick_count = 240;",
            "if (++read->tick_count > max_tick_count)",
            "read->session.state();",
            "ReadbackState::Pending",
            "ReadbackState::Failed",
            "viewcenter_pick_depth_read_apply(C, op)",
        ),
        "bounded center continuation",
    )

    invoke = braced_definition(
        center,
        "static wmOperatorStatus viewcenter_pick_invoke(bContext *C",
        "center invoke",
    )
    require_ordered(
        invoke,
        (
            "ED_view3d_smooth_view_force_finish(C, v3d, region);",
            "ED_view3d_depth_override(",
            "ViewCenterPickDepthRead *read = MEM_new<ViewCenterPickDepthRead>(__func__);",
            "read->view3d = v3d;",
            "read->region_view = rv3d;",
            "read->region = region;",
            "read->timer_window = CTX_wm_window(C);",
            "copy_v2_v2_int(read->mval, event->mval);",
            "read->smooth_viewtx = WM_operator_smooth_viewtx_get(op);",
            "copy_v3_v3(read->ofs, rv3d->ofs);",
            "copy_v4_v4(read->viewquat, rv3d->viewquat);",
            "read->persp = rv3d->persp;",
            "read->view = rv3d->view;",
            "read->view_axis_roll = rv3d->view_axis_roll;",
            "op->customdata = read;",
            "read->session.init(region, read->mval)",
            "viewcenter_pick_smooth_apply(C, op, read, nullptr);",
            "viewcenter_pick_depth_read_register(read);",
            "ReadbackState::Ready",
            "viewcenter_pick_depth_read_apply(C, op)",
            "WM_event_timer_add(",
            "WM_event_add_modal_handler(C, op);",
            "return OPERATOR_RUNNING_MODAL;",
        ),
        "center kick and continuation",
    )
    require(
        "ED_view3d_autodist(region, v3d, event->mval" not in invoke,
        "center invoke still reaches synchronous depth read",
    )
    for needle in (
        "ot->invoke = viewcenter_pick_invoke;",
        "ot->modal = viewcenter_pick_modal;",
        "ot->cancel = viewcenter_pick_cancel;",
    ):
        require(needle in center, f"center callback wiring missing {needle!r}")

    return {
        "verdict": "PASS",
        "pin": PIN,
        "contracts": {
            "shared_owned_progressive_depth": True,
            "native_immediate_completion": True,
            "center_modal_continuation": True,
            "exact_event_smooth_replay": True,
            "stock_simple_pan_fallback": True,
            "producing_view_drift_rejected": True,
            "superseded_center_rejected": True,
            "bounded_failure_cancellation": True,
            "unrelated_event_passthrough": True,
            "live_hardware_receipt": False,
        },
        "converted_consumer": "view_center_pick",
        "remaining_depth_pick_consumers": [
            "navigation",
            "depth_eyedropper",
            "painting",
            "zoom_border",
            "ndof",
        ],
        "remaining_sync_family_count": 3,
        "source_count": len(SOURCE_PATHS),
        "source_sha256": source_digest(sources),
    }


def run_selfcheck(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        ("ViewportDepthPickSession session;", "int session;", "owned session"),
        ("active->superseded = true;", "active->superseded = false;", "supersession"),
        (
            "equals_v3v3(read->region_view->ofs, read->ofs)",
            "true",
            "view-offset guard",
        ),
        ("read->region_view->camzoom == read->camzoom", "true", "camera zoom guard"),
        (
            "read->session.sample(read->region, depth_location)",
            "false",
            "settled depth sample",
        ),
        (
            "viewcenter_pick_smooth_apply(C, op, read, has_depth ? depth_location : nullptr);",
            "viewcenter_pick_smooth_apply(C, op, read, nullptr);",
            "depth-hit replay",
        ),
        (
            "event->type != TIMER || event->customdata != read->timer",
            "event->type != TIMER",
            "exact timer identity",
        ),
        ("if (++read->tick_count > max_tick_count)", "if (false)", "bounded timeout"),
        (
            "return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;",
            "return OPERATOR_RUNNING_MODAL;",
            "unrelated event passthrough",
        ),
        (
            "copy_v2_v2_int(read->mval, event->mval);",
            "zero_v2_int(read->mval);",
            "exact event coordinate",
        ),
        (
            "viewcenter_pick_smooth_apply(C, op, read, nullptr);",
            "viewcenter_pick_depth_read_free(C, op);",
            "missing-viewport fallback",
        ),
        ("ot->cancel = viewcenter_pick_cancel;", "", "cancel callback"),
    )
    center_path = "source/blender/editors/space_view3d/view3d_navigate_view_center_pick.cc"
    for before, after, label in mutations:
        mutated = dict(sources)
        text = mutated[center_path]
        require(before in text, f"selfcheck setup missing {label!r}")
        mutated[center_path] = text.replace(before, after, 1)
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
        print("M5_CENTER_DEPTH_SOURCE_SELFCHECK_PASS mutations=12")
        return 0

    receipt = validate(sources)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(
        "M5_CENTER_DEPTH_SOURCE_PASS "
        f"files={receipt['source_count']} sha256={receipt['source_sha256']} "
        "remaining_sync=3 live_receipt=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"M5_CENTER_DEPTH_SOURCE_FAIL {error}")
        raise SystemExit(1)
