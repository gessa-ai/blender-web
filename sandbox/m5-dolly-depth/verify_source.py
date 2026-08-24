#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed source contract for direct-dolly depth continuation."""

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

    require_ordered(api, ("class ViewportDepthPickSession", "bool init(ARegion *region, const int mval[2]);", "ReadbackState state();", "bool sample(ARegion *region, float r_world_location[3]);"), "owned depth-pick API")
    require("GPU_framebuffer_read_depth_async(" in framebuffer_api, "owned framebuffer-depth request missing")
    require("GPU_readback_consume(GPUReadback *&readback" in readback_api, "owned readback consume API missing")
    depth_init = braced_definition(draw, "bool ViewportDepthPickSession::init(ARegion *region, const int mval[2])", "depth-pick init")
    require("GPU_framebuffer_read_depth_async(depth_read_fb" in depth_init and "GPU_framebuffer_read_depth(depth_read_fb" not in depth_init, "depth-pick primitive is not non-blocking")

    require_ordered(header, ("struct ViewOpsDepthRead;", "enum class ViewOpsDataInitResult", "PendingDepth,", "ViewOpsDepthRead *depth_read = nullptr;", "const bool allow_async_depth = false);"), "shared navigation continuation API")
    require_ordered(navigate, ("struct ViewOpsDepthRead", "ViewportDepthPickSession session;", "wmEvent invoke_event = {};", "wmEvent queued_event = {};", "wmTimer *timer = nullptr;", "bool queued_event_valid = false;", "bool resolved = false;"), "owned navigation-depth state")

    generic_invoke = braced_definition(navigate, "static wmOperatorStatus view3d_navigation_invoke_generic(bContext *C,", "generic navigation invoke")
    require_ordered(generic_invoke, ("vod->init_navigation(", "allow_async_depth && dyn_ofs_override == nullptr", "ViewOpsDataInitResult::PendingDepth", "return OPERATOR_RUNNING_MODAL;", "ED_view3d_smooth_view_force_finish(", "nav_type->init_fn(C, vod, event, ptr)"), "generic pending barrier")
    operator_invoke = braced_definition(navigate, "wmOperatorStatus view3d_navigate_invoke_impl(bContext *C,", "operator navigation invoke")
    require("C, vod, event, op->ptr, nav_type, nullptr, true" in operator_invoke, "operator invoke does not own async depth")
    depth_modal = braced_definition(navigate, "static wmOperatorStatus view3d_navigation_depth_modal(", "navigation-depth continuation")
    require_ordered(depth_modal, ("view3d_navigation_depth_context_matches(C, vod, read)", "event->type == EVT_ESCKEY", "event->customdata != read->timer", "read->queued_event = *event;", "constexpr int max_tick_count = 240;", "ReadbackState::Failed", "read->session.sample(vod->region, pivot)", "read->resolved = true;", "const wmEvent invoke_event = read->invoke_event;", "vod->init_navigation(", "viewops_depth_read_free(C, vod);", "nav_type->init_fn(C, vod, &invoke_event, op->ptr);", "if (queued_event_valid)", "view3d_navigate_modal_fn(C, op, &queued_event)"), "bounded generic depth continuation")
    cancel_callback = braced_definition(navigate, "void view3d_navigate_cancel_fn(bContext *C, wmOperator *op)", "navigation cancel")
    require_ordered(cancel_callback, ("vod != nullptr && vod->depth_read != nullptr", "vod->state_restore();", "viewops_data_free(C, vod);", "op->customdata = nullptr;"), "pending external cancel")

    require("SPDX-FileCopyrightText: 2026 blender-web contributors" in dolly, "direct dolly copyright missing")
    require("Ported for the web from source/blender/editors/space_view3d/view3d_navigate_view_dolly.cc @\n * fbe6228777e7." in dolly, "direct dolly pinned provenance missing")

    apply_drag = braced_definition(dolly, "static void viewdolly_apply(ViewOpsData *vod,", "dolly drag")
    require_ordered(apply_drag, ("USER_ZOOM_HORIZ", "if (zoom_invert)", "view_dolly_to_vector_3d", "RV3D_BOXVIEW", "ED_view3d_camera_lock_sync", "ED_region_tag_redraw"), "stock drag semantics")
    modal_apply = braced_definition(dolly, "static wmOperatorStatus viewdolly_modal_apply(", "dolly modal apply")
    require_ordered(modal_apply, ("case VIEW_APPLY:", "viewdolly_apply(vod, xy", "ED_screen_animation_playing", "case VIEW_CONFIRM:", "OPERATOR_FINISHED", "case VIEW_CANCEL:", "vod->state_restore();", "OPERATOR_CANCELLED", "case VIEW_PASS:", "ED_view3d_camera_lock_autokey"), "dolly modal state and autokey")
    modal = braced_definition(dolly, "static wmOperatorStatus viewdolly_modal(bContext *C,", "dolly modal")
    require_ordered(modal, ("vod != nullptr && vod->depth_read != nullptr", "view3d_navigate_modal_fn(C, op, event)", "VIEWROT_MODAL_SWITCH_MOVE", '"VIEW3D_OT_move"', "VIEWROT_MODAL_SWITCH_ROTATE", '"VIEW3D_OT_rotate"', "viewdolly_modal_apply(C, vod, event_code, event->xy)", "ED_view3d_camera_lock_undo_push", "viewops_data_free(C, vod);", "op->customdata = nullptr;"), "pending dispatch and stock modal switching")

    apply_step = braced_definition(dolly, "static void viewdolly_apply_step(", "dolly step")
    require_ordered(apply_step, ("view_dolly_to_vector_3d", "delta < 0 ? 1.8f : 0.2f", "RV3D_BOXVIEW", "view3d_boxview_sync", "ED_view3d_camera_lock_sync", "ED_region_tag_redraw"), "stock delta step")
    execute = braced_definition(dolly, "static wmOperatorStatus viewdolly_exec(bContext *C,", "dolly execute")
    require_ordered(execute, ("BLI_assert(op->customdata == nullptr);", "CTX_wm_area(C)", "CTX_wm_region(C)", "negate_v3_v3(mousevec, rv3d->viewinv[2]);", "USER_ZOOM_TO_MOUSEPOS", "viewdolly_apply_step(CTX_data_ensure_evaluated_depsgraph(C)", "return OPERATOR_FINISHED;"), "context-only execute path")

    invoke_impl = braced_definition(dolly, "static wmOperatorStatus viewdolly_invoke_impl(", "dolly invoke implementation")
    require_ordered(invoke_impl, ("const bool use_cursor_init = RNA_boolean_get(ptr", "if (vod->rv3d->persp != RV3D_PERSP)", "ED_view3d_persp_switch_from_camera", "vod->rv3d->persp = RV3D_PERSP;", "RNA_struct_property_is_set(ptr, \"mx\")", "RNA_int_set(ptr, \"mx\", event->xy[0]);", "USER_ZOOM_TO_MOUSEPOS", "negate_v3_v3(vod->init.mousevec", "RNA_struct_property_is_set(ptr, \"delta\")", "viewdolly_apply_step(vod->depsgraph", "RNA_int_get(ptr, \"delta\")", "return OPERATOR_FINISHED;", "event->type == MOUSEZOOM", "USER_ZOOM_HORIZ", "event->prev_xy[0]", "viewdolly_apply(vod, event->prev_xy", "return OPERATOR_FINISHED;", "return OPERATOR_RUNNING_MODAL;"), "perspective, delta, trackpad, and modal tails")
    invoke = braced_definition(dolly, "static wmOperatorStatus viewdolly_invoke(bContext *C,", "dolly invoke")
    require_ordered(invoke, ("viewdolly_offset_lock_check(C, op)", "return OPERATOR_CANCELLED;", "view3d_navigate_invoke_impl(C, op, event, &ViewOpsType_dolly)"), "lock check before generic owned invoke")
    require("viewops_data_create(" not in dolly, "direct dolly still enters synchronous constructor")
    require_ordered(dolly, ("ViewOpsType ViewOpsType_dolly = {", "/*init_fn*/ viewdolly_invoke_impl,", "/*apply_fn*/ viewdolly_modal_apply,"), "dolly generic callbacks")

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
            "generic_owned_depth_continuation": True,
            "direct_dolly_generic_invoke": True,
            "pending_dolly_modal_dispatch": True,
            "delta_step_preserved": True,
            "trackpad_step_preserved": True,
            "perspective_and_cancel_preserved": True,
            "modal_switch_autokey_undo_preserved": True,
            "context_only_exec_preserved": True,
            "live_hardware_receipt": False,
        },
        "converted_consumer": "dolly",
        "remaining_depth_pick_consumers": [
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
    dolly_path = "source/blender/editors/space_view3d/view3d_navigate_view_dolly.cc"
    mutations = (
        (header_path, "ViewOpsDepthRead *depth_read = nullptr;", "void *depth_read = nullptr;", "owned state"),
        (nav_path, "C, vod, event, op->ptr, nav_type, nullptr, true", "C, vod, event, op->ptr, nav_type, nullptr, false", "operator async enable"),
        (nav_path, "event->customdata != read->timer", "false", "timer identity"),
        (nav_path, "read->queued_event = *event;", "read->queued_event = {};", "latest event"),
        (nav_path, "view3d_navigate_modal_fn(C, op, &queued_event)", "OPERATOR_RUNNING_MODAL", "event replay"),
        (nav_path, "void view3d_navigate_cancel_fn", "void view3d_navigate_cancel_fn_removed", "external rollback"),
        (dolly_path, "SPDX-FileCopyrightText: 2026 blender-web contributors", "SPDX-FileCopyrightText: 2025 somebody", "provenance"),
        (dolly_path, "vod != nullptr && vod->depth_read != nullptr", "false", "pending modal dispatch"),
        (dolly_path, "view3d_navigate_invoke_impl(C, op, event, &ViewOpsType_dolly)", "viewops_data_create(C, event, &ViewOpsType_dolly, false)", "owned generic invoke"),
        (dolly_path, "/*init_fn*/ viewdolly_invoke_impl,", "/*init_fn*/ nullptr,", "init callback"),
        (dolly_path, "/*apply_fn*/ viewdolly_modal_apply,", "/*apply_fn*/ nullptr,", "apply callback"),
        (dolly_path, "viewdolly_offset_lock_check(C, op)", "false", "offset lock"),
        (dolly_path, "if (vod->rv3d->persp != RV3D_PERSP)", "if (false)", "perspective switch"),
        (dolly_path, "RNA_int_set(ptr, \"mx\", event->xy[0]);", "", "mouse property"),
        (dolly_path, "negate_v3_v3(vod->init.mousevec, vod->rv3d->viewinv[2]);", "", "center vector"),
        (dolly_path, "viewdolly_apply_step(vod->depsgraph", "viewdolly_apply_step(nullptr", "delta state"),
        (dolly_path, "if (event->type == MOUSEZOOM)", "if (false)", "trackpad branch"),
        (dolly_path, "if (U.uiflag & USER_ZOOM_HORIZ)", "if (false)", "trackpad axis"),
        (dolly_path, "vod->state_restore();", "", "modal cancel restore"),
        (dolly_path, "ED_view3d_camera_lock_autokey", "ED_view3d_camera_lock_sync", "modal autokey"),
        (dolly_path, '"VIEW3D_OT_move"', '"VIEW3D_OT_zoom"', "modal switch"),
        (dolly_path, "view3d_boxview_sync(area, region);", "", "delta box sync"),
        (dolly_path, "BLI_assert(op->customdata == nullptr);", "", "execute ownership"),
        ("source/blender/editors/space_view3d/view3d_edit.cc", "ED_view3d_autodist(region, v3d, mval, r_cursor_co, nullptr)", "false", "remaining painting census"),
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
        print("M5_DOLLY_DEPTH_SOURCE_SELFCHECK_PASS mutations=24")
        return 0
    receipt = validate(sources)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(
        "M5_DOLLY_DEPTH_SOURCE_PASS "
        f"files={receipt['source_count']} sha256={receipt['source_sha256']} "
        "remaining_sync=3 live_receipt=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"M5_DOLLY_DEPTH_SOURCE_FAIL {error}")
        raise SystemExit(1)
