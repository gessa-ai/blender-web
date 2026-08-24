#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed source contract for ordinary-navigation depth continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PIN = "fbe6228777e7d9afefcd61a413844e790ae75db7"
SOURCE_PATHS = (
    "source/blender/editors/include/ED_view3d.hh",
    "source/blender/editors/space_view3d/view3d_draw.cc",
    "source/blender/editors/space_view3d/view3d_navigate.cc",
    "source/blender/editors/space_view3d/view3d_navigate.hh",
    "source/blender/editors/space_view3d/view3d_navigate_view_dolly.cc",
    "source/blender/editors/space_view3d/view3d_navigate_view_ndof.cc",
    "source/blender/editors/space_view3d/view3d_navigate_zoom_border.cc",
    "source/blender/editors/space_view3d/view3d_edit.cc",
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
    navigate = sources["source/blender/editors/space_view3d/view3d_navigate.cc"]
    header = sources["source/blender/editors/space_view3d/view3d_navigate.hh"]
    dolly = sources[
        "source/blender/editors/space_view3d/view3d_navigate_view_dolly.cc"
    ]
    ndof = sources[
        "source/blender/editors/space_view3d/view3d_navigate_view_ndof.cc"
    ]
    zoom_border = sources[
        "source/blender/editors/space_view3d/view3d_navigate_zoom_border.cc"
    ]
    painting = sources["source/blender/editors/space_view3d/view3d_edit.cc"]
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
        "GPU_framebuffer_read_depth_async(depth_read_fb" in depth_init
        and "GPU_framebuffer_read_depth(depth_read_fb" not in depth_init,
        "depth-pick primitive is not non-blocking",
    )

    for text, path in ((navigate, "view3d_navigate.cc"), (header, "view3d_navigate.hh")):
        require(
            "SPDX-FileCopyrightText: 2026 blender-web contributors" in text,
            f"{path}: blender-web copyright missing",
        )
        require(
            f"Ported for the web from source/blender/editors/space_view3d/{path} @ fbe6228777e7."
            in text,
            f"{path}: pinned provenance missing",
        )

    require_ordered(
        header,
        (
            "struct ViewOpsDepthRead;",
            "enum class ViewOpsDataInitResult",
            "Ready,",
            "PendingDepth,",
            "ViewOpsDepthRead *depth_read = nullptr;",
            "ViewOpsDataInitResult init_navigation(bContext *C,",
            "const bool allow_async_depth = false);",
        ),
        "navigation continuation API",
    )
    require_ordered(
        navigate,
        (
            "struct ViewOpsDepthRead",
            "ViewportDepthPickSession session;",
            "wmEvent invoke_event = {};",
            "wmEvent queued_event = {};",
            "wmTimer *timer = nullptr;",
            "wmWindow *window = nullptr;",
            "bScreen *screen = nullptr;",
            "eViewOpsFlag viewops_flag = VIEWOPS_FLAG_NONE;",
            "float fallback_depth_point[3]",
            "float resolved_pivot[3]",
            "int tick_count = 0;",
            "bool use_cursor_init = false;",
            "bool queued_event_valid = false;",
            "bool resolved = false;",
        ),
        "owned navigation-depth state",
    )

    cleanup = braced_definition(
        navigate,
        "static void viewops_depth_read_free(bContext *C, ViewOpsData *vod)",
        "navigation-depth cleanup",
    )
    require_ordered(
        cleanup,
        (
            "ViewOpsDepthRead *read = vod->depth_read;",
            "WM_event_timer_remove(CTX_wm_manager(C), read->window, read->timer);",
            "MEM_delete(read);",
            "vod->depth_read = nullptr;",
        ),
        "navigation-depth cleanup",
    )

    fallback = braced_definition(
        navigate,
        "static void navigate_pivot_fallback(",
        "stock pivot fallback",
    )
    require_ordered(
        fallback,
        (
            "ED_view3d_win_to_3d_int(",
            "read->fallback_depth_point",
            "read->invoke_event.mval",
            "r_pivot",
        ),
        "stock pivot fallback",
    )

    pivot = braced_definition(
        navigate,
        "static eViewOpsFlag navigate_pivot_get(",
        "navigation pivot",
    )
    require_ordered(
        pivot,
        (
            "*r_pending = false;",
            "vod->depth_read != nullptr && vod->depth_read->resolved",
            "copy_v3_v3(r_pivot, vod->depth_read->resolved_pivot);",
            "view3d_orbit_calc_center(C, r_pivot)",
            "ED_view3d_autodist_last_check(win, event)",
            "ED_view3d_depth_override(",
            "allow_async_depth && event != nullptr && event->customdata == nullptr",
            "ViewOpsDepthRead *read = MEM_new<ViewOpsDepthRead>(__func__);",
            "read->invoke_event = *event;",
            "read->invoke_event.next = nullptr;",
            "copy_v3_v3(read->fallback_depth_point, fallback_depth_pt);",
            "read->session.init(region, event->mval)",
            "ReadbackState::Pending",
            "WM_event_timer_add(CTX_wm_manager(C), win, TIMER, 0.01f);",
            "vod->depth_read = read;",
            "*r_pending = true;",
            "ReadbackState::Ready",
            "read->session.sample(region, r_pivot)",
            "ED_view3d_autodist_last_set(win, event, r_pivot, true);",
            "navigate_pivot_fallback(region, v3d, read, r_pivot);",
            "ED_view3d_autodist(",
        ),
        "kick, immediate completion, fallback, and direct path",
    )
    require(
        pivot.count("ED_view3d_autodist(") == 1,
        "direct synchronous pivot path count differs",
    )

    init_navigation = braced_definition(
        navigate,
        "ViewOpsDataInitResult ViewOpsData::init_navigation(bContext *C,",
        "navigation initialization",
    )
    require_ordered(
        init_navigation,
        (
            "this->nav_type = nav_type;",
            "const bool resume_async_depth =",
            "eViewOpsFlag viewops_flag = nav_type->flag & viewops_flag_from_prefs();",
            "if (resume_async_depth)",
            "viewops_flag = this->depth_read->viewops_flag;",
            "if (!resume_async_depth && !use_cursor_init)",
            "if (!resume_async_depth)",
            "ED_view3d_camera_lock_init_ex(",
            "this->state_backup();",
            "ED_view3d_persp_ensure(",
            "navigate_pivot_get(",
            "if (pivot_pending)",
            "this->depth_read->viewops_flag = viewops_flag;",
            "this->depth_read->use_cursor_init = use_cursor_init;",
            "return ViewOpsDataInitResult::PendingDepth;",
            "copy_v2_v2_int(this->init.event_xy, event->xy);",
            "rv3d->rflag |= RV3D_NAVIGATING;",
            "return ViewOpsDataInitResult::Ready;",
        ),
        "stock prelude, barrier, and single resume",
    )

    invoke = braced_definition(
        navigate,
        "static wmOperatorStatus view3d_navigation_invoke_generic(bContext *C,",
        "ordinary navigation invoke",
    )
    require_ordered(
        invoke,
        (
            "const bool allow_async_depth",
            "vod->init_navigation(",
            "allow_async_depth && dyn_ofs_override == nullptr",
            "ViewOpsDataInitResult::PendingDepth",
            "return OPERATOR_RUNNING_MODAL;",
            "ED_view3d_smooth_view_force_finish(",
            "nav_type->init_fn(C, vod, event, ptr)",
        ),
        "ordinary navigation barrier",
    )

    operator_invoke = braced_definition(
        navigate,
        "wmOperatorStatus view3d_navigate_invoke_impl(bContext *C,",
        "operator navigation invoke",
    )
    require(
        "C, vod, event, op->ptr, nav_type, nullptr, true" in operator_invoke,
        "operator navigation did not exclusively enable async depth",
    )

    context = braced_definition(
        navigate,
        "static bool view3d_navigation_depth_context_matches(",
        "producing context guard",
    )
    require_ordered(
        context,
        (
            "CTX_wm_window(C) == read->window",
            "CTX_wm_screen(C) == read->screen",
            "CTX_wm_area(C) == vod->area",
            "CTX_wm_region(C) == vod->region",
            "CTX_wm_view3d(C) == vod->v3d",
            "CTX_wm_region_view3d(C) == vod->rv3d",
            "vod->region->regiondata == vod->rv3d",
        ),
        "producing context guard",
    )
    cancel = braced_definition(
        navigate,
        "static wmOperatorStatus view3d_navigation_depth_cancel(",
        "navigation-depth cancellation",
    )
    require_ordered(
        cancel,
        (
            "vod->state_restore();",
            "viewops_data_free(C, vod);",
            "op->customdata = nullptr;",
            "return OPERATOR_CANCELLED;",
        ),
        "rollback before cancellation",
    )

    modal = braced_definition(
        navigate,
        "static wmOperatorStatus view3d_navigation_depth_modal(",
        "navigation-depth modal continuation",
    )
    require_ordered(
        modal,
        (
            "view3d_navigation_depth_context_matches(C, vod, read)",
            "event->type == EVT_ESCKEY && event->val == KM_PRESS",
            "event->type != TIMER || event->customdata != read->timer",
            "read->queued_event = *event;",
            "read->queued_event.next = nullptr;",
            "read->queued_event_valid = true;",
            "OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH",
            "constexpr int max_tick_count = 240;",
            "if (++read->tick_count > max_tick_count)",
            "read->session.state();",
            "ReadbackState::Pending",
            "ReadbackState::Failed",
            "read->session.sample(vod->region, pivot)",
            "navigate_pivot_fallback(vod->region, vod->v3d, read, pivot);",
            "ED_view3d_autodist_last_set(read->window, &read->invoke_event, pivot, true);",
            "copy_v3_v3(read->resolved_pivot, pivot);",
            "read->resolved = true;",
            "const wmEvent invoke_event = read->invoke_event;",
            "const wmEvent queued_event = read->queued_event;",
            "WM_event_timer_remove(",
            "vod->init_navigation(",
            "BLI_assert(init_result == ViewOpsDataInitResult::Ready);",
            "viewops_depth_read_free(C, vod);",
            "ED_view3d_smooth_view_force_finish(",
            "nav_type->init_fn(C, vod, &invoke_event, op->ptr);",
            "if (queued_event_valid)",
            "view3d_navigate_modal_fn(C, op, &queued_event)",
        ),
        "bounded resolution and exact event replay",
    )

    modal_dispatch = braced_definition(
        navigate,
        "wmOperatorStatus view3d_navigate_modal_fn(bContext *C,",
        "modal dispatch",
    )
    require_ordered(
        modal_dispatch,
        (
            "vod != nullptr && vod->depth_read != nullptr",
            "view3d_navigation_depth_modal(C, op, event)",
            "view3d_navigate_event(vod, event)",
        ),
        "pending depth dispatch precedes stock modal state",
    )
    require(
        "C, vod, event, op->ptr, vod->nav_type, nullptr, true" in modal_dispatch,
        "modal navigation type switch did not retain async ownership",
    )

    cancel_callback = braced_definition(
        navigate,
        "void view3d_navigate_cancel_fn(bContext *C, wmOperator *op)",
        "external navigation cancellation",
    )
    require_ordered(
        cancel_callback,
        (
            "ViewOpsData *vod = static_cast<ViewOpsData *>(op->customdata);",
            "vod != nullptr && vod->depth_read != nullptr",
            "vod->state_restore();",
            "viewops_data_free(C, vod);",
            "op->customdata = nullptr;",
        ),
        "external pending cancellation rollback",
    )

    utility = braced_definition(
        navigate,
        "bool ED_view3d_navigation_do(bContext *C,",
        "embedded navigation utility",
    )
    require(
        "C, vod, event, kmi.ptr, nav_type, depth_loc_override, false" in utility,
        "embedded navigation utility can start an unowned async request",
    )

    data_create = braced_definition(
        navigate,
        "ViewOpsData *viewops_data_create(bContext *C,",
        "direct navigation data create",
    )
    require(
        "vod->init_navigation(C, event, nav_type, nullptr, use_cursor_init);" in data_create,
        "direct navigation callers no longer use the pinned synchronous default",
    )
    require(
        "viewops_data_create(C, event, &ViewOpsType_dolly, use_cursor_init)" in dolly,
        "direct dolly remainder disappeared",
    )
    require(
        ndof.count("view3d_navigate_invoke_impl(C, op, event, &ViewOpsType_ndof_") == 4,
        "NDOF remainder census differs",
    )
    require(
        "view3d_depths_rect_create(region, &rect, &depth_temp);" in zoom_border,
        "zoom-border depth remainder disappeared",
    )
    require(
        "ED_view3d_autodist(region, v3d, mval, r_cursor_co, nullptr)" in painting,
        "painting/cursor depth remainder disappeared",
    )

    return {
        "verdict": "PASS",
        "pin": PIN,
        "contracts": {
            "shared_owned_progressive_depth": True,
            "native_immediate_completion": True,
            "ordinary_navigation_modal_continuation": True,
            "stock_initialization_order_once": True,
            "exact_hit_and_fallback_pivot": True,
            "latest_event_replay": True,
            "producing_context_guard": True,
            "bounded_failure_cancellation": True,
            "direct_callers_remain_pinned": True,
            "live_hardware_receipt": False,
        },
        "converted_consumer": "ordinary_navigation",
        "remaining_depth_pick_consumers": [
            "dolly",
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
    nav_path = "source/blender/editors/space_view3d/view3d_navigate.cc"
    header_path = "source/blender/editors/space_view3d/view3d_navigate.hh"
    mutations = (
        (header_path, "ViewOpsDepthRead *depth_read = nullptr;", "void *depth_read = nullptr;", "owned state"),
        (nav_path, "ViewportDepthPickSession session;", "int session;", "owned session"),
        (nav_path, "read->invoke_event = *event;", "read->invoke_event = {};", "invoke event capture"),
        (nav_path, "event->customdata == nullptr", "true", "safe event ownership"),
        (nav_path, "*r_pending = true;", "*r_pending = false;", "pending barrier"),
        (nav_path, "this->state_backup();", "", "stock backup"),
        (nav_path, "if (!resume_async_depth)", "if (true)", "single prelude"),
        (nav_path, "vod->state_restore();", "", "cancel rollback"),
        (nav_path, "CTX_wm_region(C) == vod->region", "true", "region guard"),
        (nav_path, "read->queued_event = *event;", "read->queued_event = {};", "latest event"),
        (nav_path, "event->customdata != read->timer", "false", "timer identity"),
        (nav_path, "if (++read->tick_count > max_tick_count)", "if (false)", "timeout"),
        (nav_path, "read->session.sample(vod->region, pivot)", "false", "settled sample"),
        (nav_path, "navigate_pivot_fallback(vod->region, vod->v3d, read, pivot);", "", "fallback"),
        (nav_path, "view3d_navigate_modal_fn(C, op, &queued_event)", "OPERATOR_RUNNING_MODAL", "event replay"),
        (nav_path, "allow_async_depth && dyn_ofs_override == nullptr", "false", "ordinary async enable"),
        (nav_path, "depth_loc_override, false", "depth_loc_override, true", "utility pin"),
        (nav_path, "void view3d_navigate_cancel_fn", "void view3d_navigate_cancel_fn_removed", "external rollback"),
    )
    for path, before, after, label in mutations:
        mutated = dict(sources)
        text = mutated[path]
        require(before in text, f"selfcheck setup missing {label!r}")
        mutated[path] = text.replace(before, after, 1)
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
        print("M5_NAVIGATION_DEPTH_SOURCE_SELFCHECK_PASS mutations=18")
        return 0
    receipt = validate(sources)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(
        "M5_NAVIGATION_DEPTH_SOURCE_PASS "
        f"files={receipt['source_count']} sha256={receipt['source_sha256']} "
        "remaining_sync=3 live_receipt=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"M5_NAVIGATION_DEPTH_SOURCE_FAIL {error}")
        raise SystemExit(1)
