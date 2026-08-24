#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed source contract for the owned zoom-border depth continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PIN = "fbe6228777e7d9afefcd61a413844e790ae75db7"
ZOOM_PATH = "source/blender/editors/space_view3d/view3d_navigate_zoom_border.cc"
SOURCE_PATHS = (
    ZOOM_PATH,
    "source/blender/gpu/GPU_framebuffer.hh",
    "source/blender/gpu/GPU_readback.hh",
    "source/blender/gpu/intern/gpu_framebuffer.cc",
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
    zoom = sources[ZOOM_PATH]
    framebuffer_api = sources["source/blender/gpu/GPU_framebuffer.hh"]
    readback_api = sources["source/blender/gpu/GPU_readback.hh"]
    framebuffer_impl = sources["source/blender/gpu/intern/gpu_framebuffer.cc"]

    require(
        "SPDX-FileCopyrightText: 2023 Blender Authors" in zoom
        and "SPDX-FileCopyrightText: 2026 blender-web contributors" in zoom
        and "Ported for the web from source/blender/editors/space_view3d/"
        "view3d_navigate_zoom_border.cc @ fbe6228777e7." in zoom,
        "license or provenance header differs",
    )
    require(
        "GPU_framebuffer_read_depth_async(" in framebuffer_api
        and "GPUReadback *GPU_framebuffer_read_depth_async(" in framebuffer_impl,
        "owned framebuffer-depth API missing",
    )
    require(
        "bool GPU_readback_consume(GPUReadback *&readback" in readback_api
        and "void GPU_readback_cancel(GPUReadback *&readback);" in readback_api,
        "owned readback consume/cancel API missing",
    )

    require_ordered(
        zoom,
        (
            "struct ZoomBorderDepthRead",
            "ZoomBorderDepthRead *next = nullptr;",
            "wmOperator *owner = nullptr;",
            "GPUReadback *readback = nullptr;",
            "View3D *view3d = nullptr;",
            "RegionView3D *region_view = nullptr;",
            "ARegion *region = nullptr;",
            "ScrArea *area = nullptr;",
            "wmWindow *timer_window = nullptr;",
            "wmTimer *timer = nullptr;",
            "rcti rect = {};",
            "size_t expected_size = 0;",
            "float viewinv[4][4] = {};",
            "float winmat[4][4] = {};",
            "void *smooth_state = nullptr;",
            "wmTimer *smooth_timer = nullptr;",
            "int smooth_viewtx = 0;",
            "bool zoom_in = true;",
            "bool listed = false;",
            "bool superseded = false;",
        ),
        "owned zoom-border state",
    )

    context_guard = braced_definition(
        zoom,
        "static bool view3d_zoom_border_depth_read_context_matches(",
        "producing context guard",
    )
    for needle in (
        "CTX_wm_view3d(C) != read->view3d",
        "CTX_wm_region_view3d(C) != read->region_view",
        "CTX_wm_region(C) != read->region",
        "CTX_wm_area(C) != read->area",
        "CTX_wm_window(C) != read->timer_window",
        "equals_m4m4(rv3d->viewinv, read->viewinv)",
        "equals_m4m4(rv3d->winmat, read->winmat)",
        "equals_v3v3(rv3d->ofs, read->ofs)",
        "equals_v4v4(rv3d->viewquat, read->viewquat)",
        "rv3d->dist == read->dist",
        "rv3d->camzoom == read->camzoom",
        "v3d->lens == read->lens",
        "v3d->clip_start == read->clip_start",
        "v3d->camera == read->camera",
        "rv3d->sms == read->smooth_state",
        "rv3d->smooth_timer == read->smooth_timer",
        "int(RV3D_LOCK_FLAGS(rv3d)) == read->view_lock",
    ):
        require(needle in context_guard, f"producing context guard missing {needle!r}")

    cleanup = braced_definition(
        zoom,
        "static void view3d_zoom_border_depth_read_free(",
        "owned request cleanup",
    )
    require_ordered(
        cleanup,
        (
            "BLI_remlink(&zoom_border_depth_reads, read);",
            "WM_event_timer_remove(CTX_wm_manager(C), read->timer_window, read->timer);",
            "GPU_readback_cancel(read->readback);",
            "if (op->customdata == read)",
            "op->customdata = nullptr;",
            "MEM_delete(read);",
        ),
        "owned cleanup order",
    )

    registration = braced_definition(
        zoom,
        "static void view3d_zoom_border_depth_read_register(",
        "newest-request registration",
    )
    require_ordered(
        registration,
        (
            "active->timer_window == read->timer_window",
            "active->region == read->region",
            "active->superseded = true;",
            "BLI_addtail(&zoom_border_depth_reads, read);",
            "read->listed = true;",
        ),
        "newest-request registration",
    )

    consume = braced_definition(
        zoom,
        "static bool view3d_zoom_border_depth_read_consume(",
        "nearest-depth consume",
    )
    require_ordered(
        consume,
        (
            "view3d_zoom_border_depth_read_status(read) != GPU_READBACK_READY",
            "r_depth_near = FLT_MAX;",
            "std::vector<float> depths(read->expected_size / sizeof(float));",
            "GPU_readback_consume(read->readback, depths.data(), read->expected_size)",
            "float nearest = 1.0f;",
            "if (depth < nearest && depth > 0.0f)",
            "nearest = depth;",
            "if (nearest != 1.0f)",
            "r_depth_near = nearest;",
        ),
        "strict nearest-depth consume",
    )

    create = braced_definition(
        zoom,
        "static ZoomBorderDepthRead *view3d_zoom_border_depth_read_create(",
        "rectangle-depth kick",
    )
    require_ordered(
        create,
        (
            "read->smooth_viewtx = WM_operator_smooth_viewtx_get(op);",
            'read->zoom_in = !RNA_boolean_get(op->ptr, "zoom_out");',
            "WM_operator_properties_border_to_rcti(op, &read->rect);",
            "copy_m4_m4(read->viewinv, read->region_view->viewinv);",
            "copy_m4_m4(read->winmat, read->region_view->winmat);",
            "read->smooth_state = read->region_view->sms;",
            "read->view_lock = int(RV3D_LOCK_FLAGS(read->region_view));",
            "rcti request_rect = read->rect;",
            "BLI_rcti_isect(&bounds, &request_rect, &request_rect);",
            "read->rect = request_rect;",
            "width > std::numeric_limits<size_t>::max() / height",
            "read->expected_size = width * height * sizeof(float);",
            "GPU_viewport_depth_texture(viewport)",
            "GPU_framebuffer_ensure_config(&depth_read_fb",
            "GPU_framebuffer_read_depth_async(depth_read_fb",
            "GPU_framebuffer_restore();",
            "GPU_framebuffer_free(depth_read_fb);",
        ),
        "exact rectangle-depth kick",
    )
    require(
        "GPU_framebuffer_read_depth(" not in create
        and "view3d_depths_rect_create(" not in create
        and "view3d_depth_near(" not in create,
        "rectangle kick retains a synchronous read",
    )

    apply = braced_definition(
        zoom,
        "static wmOperatorStatus view3d_zoom_border_apply(",
        "settled stock replay",
    )
    require_ordered(
        apply,
        (
            "view3d_zoom_border_depth_read_context_matches(C, read)",
            "rcti rect = read->rect;",
            "ED_view3d_dist_soft_range_get(v3d, rv3d->is_persp)",
            "const float region_aspect = float(region->winx) / float(region->winy);",
            "BLI_rcti_resize_x(&rect",
            "cent[0] = (float(rect.xmin) + float(rect.xmax)) / 2;",
            "if (rv3d->is_persp)",
            "if (depth_close == FLT_MAX)",
            "ED_view3d_unproject_v3(region, cent[0], cent[1], depth_close, p)",
            "dist_new *= (v3d->lens / DEFAULT_SENSOR_WIDTH);",
            "dist_new = rv3d->dist;",
            "if (depth_close != FLT_MAX && ED_view3d_unproject_v3(",
            "copy_v3_v3(ofs_new, rv3d->ofs);",
            "ED_view3d_win_to_delta(region, xy_delta, zfac, dvec);",
            "dist_new *= max_ff(xscale, yscale);",
            "if (!read->zoom_in)",
            "dist_new = rv3d->dist * (rv3d->dist / dist_new);",
            "CLAMP(dist_new, dist_range.min, dist_range.max);",
            "ED_view3d_camera_lock_check(v3d, rv3d)",
            "ED_view3d_smooth_view(C, v3d, region, read->smooth_viewtx, &sview_params);",
            "view3d_boxview_sync(read->area, region);",
            "view3d_zoom_border_depth_read_free(C, op, read);",
            "return OPERATOR_FINISHED;",
        ),
        "stock zoom-border replay",
    )

    execute = braced_definition(
        zoom,
        "static wmOperatorStatus view3d_zoom_border_exec(",
        "zoom-border execute",
    )
    require_ordered(
        execute,
        (
            "view3d_operator_needs_gpu(C);",
            "ED_view3d_depth_override(",
            "view3d_zoom_border_depth_read_create(C, op);",
            "view3d_zoom_border_depth_read_status(read);",
            "if (status == GPU_READBACK_READY)",
            "view3d_zoom_border_depth_read_finish(C, op, read)",
            "if (status != GPU_READBACK_PENDING)",
            "view3d_zoom_border_depth_read_register(read);",
            "if (op->customdata == nullptr)",
            "view3d_zoom_border_depth_read_attach(C, op, read, true);",
            "return OPERATOR_RUNNING_MODAL;",
        ),
        "native-immediate or pending execute",
    )
    require(
        "view3d_depths_rect_create(" not in execute
        and "GPU_framebuffer_read_depth(" not in execute,
        "operator execute retains synchronous readback",
    )

    modal = braced_definition(
        zoom,
        "static wmOperatorStatus view3d_zoom_border_modal(",
        "gesture and readback modal",
    )
    require_ordered(
        modal,
        (
            "view3d_zoom_border_depth_read_find(op);",
            "if (read == nullptr || op->customdata != read)",
            "WM_gesture_box_modal(C, op, event);",
            "read = view3d_zoom_border_depth_read_find(op);",
            "if (status == GPU_READBACK_READY)",
            "view3d_zoom_border_depth_read_finish(C, op, read)",
            "view3d_zoom_border_depth_read_attach(C, op, read, false);",
            "if (read->superseded || !view3d_zoom_border_depth_read_context_matches(C, read)",
            "event->type == EVT_ESCKEY && event->val == KM_PRESS",
            "event->type == EVT_MODAL_MAP && event->val == GESTURE_MODAL_CANCEL",
            "event->type != TIMER || event->customdata != read->timer",
            "OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH",
            "constexpr int max_tick_count = 240;",
            "if (++read->tick_count > max_tick_count)",
            "if (status == GPU_READBACK_PENDING)",
            "view3d_zoom_border_depth_read_finish(C, op, read)",
        ),
        "gesture handoff and bounded continuation",
    )

    for needle in (
        "ot->invoke = WM_gesture_box_invoke;",
        "ot->exec = view3d_zoom_border_exec;",
        "ot->modal = view3d_zoom_border_modal;",
        "ot->cancel = view3d_zoom_border_cancel;",
    ):
        require(needle in zoom, f"operator callback wiring missing {needle!r}")

    return {
        "schema": 1,
        "verdict": "PASS",
        "pin": PIN,
        "contracts": {
            "owned_rectangle_depth": True,
            "stock_post_clamp_rectangle": True,
            "strict_nearest_depth": True,
            "native_immediate_completion": True,
            "gesture_to_readback_handoff": True,
            "exact_zoom_mode_smooth_replay": True,
            "perspective_and_ortho_semantics": True,
            "producing_view_drift_rejected": True,
            "newest_request_supersedes": True,
            "bounded_failure_cancellation": True,
            "unrelated_event_passthrough": True,
            "live_hardware_receipt": False,
        },
        "converted_consumer": "zoom_border",
        "remaining_depth_pick_consumers": ["ndof"],
        "remaining_sync_family_count": 3,
        "source_count": len(SOURCE_PATHS),
        "source_sha256": source_digest(sources),
    }


def run_selfcheck(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        ("read->rect = request_rect;", "read->rect = {};", "post-clamp rectangle"),
        (
            "GPU_framebuffer_read_depth_async(depth_read_fb",
            "GPU_framebuffer_read_depth(depth_read_fb",
            "async depth request",
        ),
        ("depth < nearest && depth > 0.0f", "depth < nearest", "strict near range"),
        (
            "active->superseded = true;",
            "active->superseded = false;",
            "newest request wins",
        ),
        (
            "equals_m4m4(rv3d->viewinv, read->viewinv)",
            "true",
            "view matrix guard",
        ),
        ("rv3d->sms == read->smooth_state", "true", "smooth-state guard"),
        (
            'read->zoom_in = !RNA_boolean_get(op->ptr, "zoom_out");',
            "read->zoom_in = true;",
            "zoom mode capture",
        ),
        (
            "ED_view3d_smooth_view(C, v3d, region, read->smooth_viewtx, &sview_params);",
            "ED_view3d_smooth_view(C, v3d, region, 0, &sview_params);",
            "smooth duration replay",
        ),
        (
            "view3d_zoom_border_depth_read_attach(C, op, read, false);",
            "return OPERATOR_CANCELLED;",
            "gesture handoff",
        ),
        (
            "event->type != TIMER || event->customdata != read->timer",
            "event->type != TIMER",
            "exact timer identity",
        ),
        (
            "if (++read->tick_count > max_tick_count)",
            "if (false)",
            "bounded timeout",
        ),
        (
            "return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;",
            "return OPERATOR_RUNNING_MODAL;",
            "unrelated event passthrough",
        ),
        (
            "view3d_zoom_border_depth_read_context_matches(C, read)",
            "true",
            "settled context guard",
        ),
        (
            "GPU_readback_cancel(read->readback);",
            "read->readback = nullptr;",
            "owned cancellation",
        ),
        (
            "ot->cancel = view3d_zoom_border_cancel;",
            "ot->cancel = WM_gesture_box_cancel;",
            "cancel callback",
        ),
    )
    for before, after, label in mutations:
        mutated = dict(sources)
        text = mutated[ZOOM_PATH]
        require(before in text, f"selfcheck setup missing {label!r}")
        mutated[ZOOM_PATH] = text.replace(before, after, 1)
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
        print("M5_ZOOM_BORDER_DEPTH_SOURCE_SELFCHECK_PASS mutations=15")
        return 0

    receipt = validate(sources)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(
        "M5_ZOOM_BORDER_DEPTH_SOURCE_PASS "
        f"files={receipt['source_count']} sha256={receipt['source_sha256']} "
        "remaining_sync=3 live_receipt=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"M5_ZOOM_BORDER_DEPTH_SOURCE_FAIL {error}")
        raise SystemExit(1)
