#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed source contract for the owned NDOF depth continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PIN = "fbe6228777e7d9afefcd61a413844e790ae75db7"
NDOF_PATH = "source/blender/editors/space_view3d/view3d_navigate_view_ndof.cc"
NAV_PATH = "source/blender/editors/space_view3d/view3d_navigate.cc"
NAV_HEADER_PATH = "source/blender/editors/space_view3d/view3d_navigate.hh"
SOURCE_PATHS = (
    NDOF_PATH,
    NAV_PATH,
    NAV_HEADER_PATH,
    "source/blender/gpu/GPU_framebuffer.hh",
    "source/blender/gpu/GPU_readback.hh",
    "source/blender/gpu/intern/gpu_framebuffer.cc",
)


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def require_once(text: str, needle: str, label: str) -> None:
    count = text.count(needle)
    require(count == 1, f"{label}: expected once, found {count}: {needle!r}")


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
    for relative in sorted(sources):
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(sources[relative].encode())
        digest.update(b"\0")
    return digest.hexdigest()


def validate(sources: dict[str, str]) -> dict[str, object]:
    ndof = sources[NDOF_PATH]
    nav = sources[NAV_PATH]
    header = sources[NAV_HEADER_PATH]
    framebuffer_api = sources["source/blender/gpu/GPU_framebuffer.hh"]
    framebuffer_impl = sources["source/blender/gpu/intern/gpu_framebuffer.cc"]
    readback_api = sources["source/blender/gpu/GPU_readback.hh"]

    require(
        "SPDX-FileCopyrightText: 2023 Blender Authors" in ndof
        and "SPDX-FileCopyrightText: 2026 blender-web contributors" in ndof
        and "Ported for the web from source/blender/editors/space_view3d/"
        "view3d_navigate_view_ndof.cc @ fbe6228777e7." in ndof,
        "NDOF license or provenance header differs",
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

    require("static float ndof_read_zbuf_rect(" not in ndof, "synchronous NDOF rectangle read remains")
    require("view3d_depths_rect_create(region" not in ndof, "NDOF still enters synchronous depth helper")

    require_ordered(
        ndof,
        (
            "struct NdofQueuedMotion",
            "wmEvent event = {};",
            "wmNDOFMotionData motion = {};",
            "struct NdofDepthRead",
            "GPUReadback *readback = nullptr;",
            "wmTimer *timer = nullptr;",
            "wmWindow *window = nullptr;",
            "bScreen *screen = nullptr;",
            "ScrArea *area = nullptr;",
            "ARegion *region = nullptr;",
            "View3D *view3d = nullptr;",
            "RegionView3D *region_view = nullptr;",
            "wmEvent invoke_event = {};",
            "wmNDOFMotionData invoke_motion = {};",
            "Vector<NdofQueuedMotion> queued_motions;",
            "rcti sample_rect = {};",
            "size_t expected_size = 0;",
            "float viewinv[4][4] = {};",
            "float winmat[4][4] = {};",
            "float persmat[4][4] = {};",
            "float persinv[4][4] = {};",
            "int tick_count = 0;",
            "bool empty_ready = false;",
            "bool resolved = false;",
        ),
        "owned NDOF depth state",
    )

    creation = braced_definition(ndof, "static NdofDepthRead *ndof_depth_read_create(", "read creation")
    for needle in (
        "read->invoke_event = *event;",
        "read->invoke_motion = *static_cast<const wmNDOFMotionData *>(event->customdata);",
        "read->invoke_event.customdata = nullptr;",
        "read->invoke_event.customdata_free = false;",
        "BLI_rcti_isect(&bounds, &read->sample_rect, &read->sample_rect);",
        "GPU_viewport_depth_texture(viewport)",
        "GPU_framebuffer_read_depth_async(",
    ):
        require(needle in creation, f"read creation missing {needle!r}")

    consume = braced_definition(ndof, "static bool ndof_depth_read_consume(", "nearest-depth consume")
    require_ordered(
        consume,
        (
            "GPU_readback_consume(read->readback, depths.data(), read->expected_size)",
            "float nearest = 1.0f;",
            "if (depth < nearest && depth > 0.0f)",
            "nearest_index = int(index);",
            "read->sample_rect.xmin + (nearest_index % width)",
            "read->sample_rect.ymin + (nearest_index / width)",
        ),
        "strict row-major nearest-depth reduction",
    )

    context = braced_definition(ndof, "static bool ndof_depth_context_matches(", "context guard")
    for needle in (
        "CTX_wm_window(C) != read->window",
        "CTX_wm_screen(C) != read->screen",
        "CTX_wm_area(C) != read->area",
        "CTX_wm_region(C) != read->region",
        "CTX_wm_view3d(C) != read->view3d",
        "CTX_wm_region_view3d(C) != read->region_view",
        "equals_m4m4(rv3d->viewinv, read->viewinv)",
        "equals_m4m4(rv3d->winmat, read->winmat)",
        "equals_m4m4(rv3d->persmat, read->persmat)",
        "equals_m4m4(rv3d->persinv, read->persinv)",
        "effective_navigation_mode != read->navigation_mode",
        "U.ndof_flag != read->ndof_flag",
    ):
        require(needle in context, f"context guard missing {needle!r}")

    modal = braced_definition(ndof, "wmOperatorStatus view3d_ndof_depth_modal(", "bounded modal continuation")
    require_ordered(
        modal,
        (
            "view3d_ndof_depth_is_pending(vod)",
            "ndof_depth_context_matches(C, vod, read)",
            "event->type == EVT_ESCKEY && event->val == KM_PRESS",
            "event->type == NDOF_MOTION",
            "constexpr int max_queued_motions = 256;",
            "read->queued_motions.append(ndof_motion_copy(*event));",
            "event->type != TIMER || event->customdata != read->timer",
            "constexpr int max_tick_count = 240;",
            "if (++read->tick_count > max_tick_count)",
            "ndof_depth_read_status(read)",
            "ndof_depth_read_consume(read, min_depth_point)",
            "read->resolved = true;",
            "ndof_replay_owned_event(C, op, vod, invoke_event, invoke_motion)",
            "for (int index = 0; index < queued_motions.size(); index++)",
        ),
        "NDOF payload FIFO and bounded settlement",
    )
    for needle in (
        "BKE_report(op->reports, RPT_ERROR, \"Timed out waiting for NDOF depth\")",
        "BKE_report(op->reports, RPT_ERROR, \"NDOF depth readback failed\")",
        "return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;",
    ):
        require(needle in modal, f"NDOF modal terminal contract missing {needle!r}")

    cleanup = braced_definition(ndof, "void view3d_ndof_depth_cancel(", "NDOF cleanup")
    require_ordered(
        cleanup,
        (
            "WM_event_timer_remove(CTX_wm_manager(C), read->window, read->timer);",
            "GPU_readback_cancel(read->readback);",
            "vod->ndof_depth_read = nullptr;",
            "MEM_delete(read);",
        ),
        "NDOF cleanup order",
    )

    center = braced_definition(ndof, "static NdofOrbitCenterResult ndof_orbit_center_calc(", "center state machine")
    require_ordered(
        center,
        (
            "vod->ndof_depth_read != nullptr && vod->ndof_depth_read->resolved",
            "ndof_orbit_center_calc_from_depth_point(",
            "ndof_orbit_center_calc_from_bounds(",
            "if (r_center.has_value())",
            "ndof_orbit_center_sample_rect(vod->region)",
            "ndof_depth_read_create(C, vod, event, sample_rect)",
            "const eGPUReadbackStatus status = ndof_depth_read_status(read);",
            "return NdofOrbitCenterResult::Pending;",
            "ndof_depth_read_consume(read, read->min_depth_point)",
        ),
        "bounds-first owned center calculation",
    )

    invoke = braced_definition(ndof, "static wmOperatorStatus ndof_orbit_zoom_invoke_impl(", "NDOF invoke")
    require_ordered(
        invoke,
        (
            "NdofOrbitCenterResult center_result = ndof_orbit_center_calc(",
            "if (center_result == NdofOrbitCenterResult::Pending)",
            "return OPERATOR_RUNNING_MODAL;",
            "if (center_result == NdofOrbitCenterResult::Failed)",
            "return OPERATOR_CANCELLED;",
            "if (center_test.has_value())",
            "rv3d->ndof_flag |= RV3D_NDOF_OFS_IS_VALID;",
        ),
        "pending NDOF invoke tail",
    )

    for needle in (
        "NdofDepthRead *ndof_depth_read = nullptr;",
        "bool view3d_ndof_depth_is_pending(const ViewOpsData *vod);",
        "wmOperatorStatus view3d_ndof_depth_modal(bContext *C, wmOperator *op, const wmEvent *event);",
        "void view3d_ndof_depth_cancel(bContext *C, ViewOpsData *vod);",
    ):
        require(needle in header, f"NDOF continuation declaration missing {needle!r}")
    for needle in (
        "if (view3d_ndof_depth_is_pending(vod))",
        "return view3d_ndof_depth_modal(C, op, event);",
        "view3d_ndof_depth_cancel(C, this);",
    ):
        require(needle in nav, f"navigation lifecycle integration missing {needle!r}")
    require(nav.count("view3d_ndof_depth_is_pending(vod)") >= 2, "cancel path does not recognize NDOF pending state")
    require(ndof.count("ot->modal = view3d_navigate_modal_fn;") == 2, "NDOF modal callback count differs")
    require(ndof.count("ot->cancel = view3d_navigate_cancel_fn;") == 2, "NDOF cancel callback count differs")

    return {
        "schema": 1,
        "verdict": "PASS",
        "contracts": {
            "owned_rectangle_depth": True,
            "bounds_first_fallback": True,
            "strict_nearest_xy": True,
            "native_immediate_completion": True,
            "owned_ndof_payload": True,
            "ordered_motion_replay": True,
            "producing_view_guard": True,
            "bounded_failure_cancellation": True,
            "external_cancel_cleanup": True,
            "live_hardware_receipt": False,
        },
        "converted_consumer": "ndof",
        "remaining_depth_pick_consumers": [],
        "remaining_sync_families": ["depth_cache", "window_capture"],
        "source_count": len(SOURCE_PATHS),
        "source_sha256": source_digest(sources),
    }


def run_selfcheck(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        (NDOF_PATH, "read->invoke_event.customdata = nullptr;", "read->invoke_event.customdata = event->customdata;", "payload ownership"),
        (NDOF_PATH, "if (depth < nearest && depth > 0.0f)", "if (depth <= nearest && depth >= 0.0f)", "nearest semantics"),
        (NDOF_PATH, "read->queued_motions.append(ndof_motion_copy(*event));", "/* dropped queued motion */", "FIFO replay"),
        (NDOF_PATH, "constexpr int max_tick_count = 240;", "constexpr int max_tick_count = 0;", "timeout"),
        (NDOF_PATH, "ndof_depth_context_matches(C, vod, read)", "true", "context guard"),
        (NDOF_PATH, "GPU_readback_cancel(read->readback);", "read->readback = nullptr;", "GPU cleanup"),
        (NAV_PATH, "return view3d_ndof_depth_modal(C, op, event);", "return OPERATOR_CANCELLED;", "modal routing"),
        (NDOF_PATH, "ot->cancel = view3d_navigate_cancel_fn;", "ot->cancel = nullptr;", "external cancellation"),
    )
    for relative, old, new, label in mutations:
        require_once(sources[relative], old, f"selfcheck {label}") if label != "external cancellation" else None
        mutated = dict(sources)
        mutated[relative] = sources[relative].replace(old, new, 1)
        try:
            validate(mutated)
        except ContractError:
            continue
        raise ContractError(f"selfcheck mutation escaped: {label}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    sources = read_sources(args.source_root.resolve())
    if args.selfcheck:
        run_selfcheck(sources)
        print("M5_NDOF_DEPTH_SOURCE_SELFCHECK_PASS mutations=8")
        return 0
    result = validate(sources)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "M5_NDOF_DEPTH_SOURCE_PASS "
        f"sources={result['source_count']} remaining={len(result['remaining_sync_families'])} "
        f"sha256={result['source_sha256']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"M5_NDOF_DEPTH_SOURCE_FAIL {error}", file=__import__("sys").stderr)
        raise SystemExit(1)
