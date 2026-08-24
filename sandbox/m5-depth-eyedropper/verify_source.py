#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed source contract for asynchronous viewport-depth eyedropper sampling."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PIN = "fbe6228777e7d9afefcd61a413844e790ae75db7"
SOURCE_PATHS = (
    "source/blender/editors/include/ED_view3d.hh",
    "source/blender/editors/space_view3d/view3d_draw.cc",
    "source/blender/editors/interface/eyedroppers/eyedropper_depth.cc",
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
    result: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = root / relative
        require(path.is_file(), f"source file missing: {relative}")
        result[relative] = path.read_text(encoding="utf-8")
    return result


def source_digest(sources: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(sources):
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(sources[relative].encode())
        digest.update(b"\0")
    return digest.hexdigest()


def validate(sources: dict[str, str]) -> dict[str, object]:
    api = sources["source/blender/editors/include/ED_view3d.hh"]
    draw = sources["source/blender/editors/space_view3d/view3d_draw.cc"]
    eye = sources[
        "source/blender/editors/interface/eyedroppers/eyedropper_depth.cc"
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
        "owned progressive-depth API",
    )
    require(
        "GPU_framebuffer_read_depth_async(" in framebuffer_api,
        "owned framebuffer-depth API missing",
    )
    require(
        "GPU_readback_consume(GPUReadback *&readback" in readback_api,
        "owned consume API missing",
    )
    depth_init = braced_definition(
        draw,
        "bool ViewportDepthPickSession::init(ARegion *region, const int mval[2])",
        "progressive-depth init",
    )
    require(
        "GPU_framebuffer_read_depth_async(depth_read_fb" in depth_init
        and "GPU_framebuffer_read_depth(depth_read_fb" not in depth_init,
        "progressive-depth primitive is not asynchronous",
    )

    require(
        "SPDX-FileCopyrightText: 2009 Blender Authors" in eye
        and "SPDX-FileCopyrightText: 2026 blender-web contributors" in eye
        and "Ported for the web from source/blender/editors/interface/eyedroppers/eyedropper_depth.cc @ fbe6228777e7"
        in eye,
        "derived-file provenance missing",
    )
    require_ordered(
        eye,
        (
            "enum class DepthDropperReadbackAction",
            "None,",
            "Accumulate,",
            "AccumulateAndSet,",
            "struct DepthDropper",
            "ViewportDepthPickSession readback_session;",
            "wmTimer *readback_timer = nullptr;",
            "wmWindow *readback_window = nullptr;",
            "bScreen *readback_screen = nullptr;",
            "Scene *readback_scene = nullptr;",
            "ScrArea *readback_area = nullptr;",
            "ARegion *readback_region = nullptr;",
            "View3D *readback_view3d = nullptr;",
            "RegionView3D *readback_region_view = nullptr;",
            "int readback_event_xy[2] = {};",
            "int readback_mval[2] = {};",
            "float readback_view_origin[3] = {};",
            "int readback_tick_count = 0;",
            "DepthDropperReadbackAction readback_action = DepthDropperReadbackAction::None;",
            "bool readback_confirm_after = false;",
        ),
        "owned eyedropper state",
    )

    context_guard = braced_definition(
        eye,
        "static bool depthdropper_readback_context_matches(",
        "producing-context guard",
    )
    for needle in (
        "CTX_wm_window(C) == ddr->readback_window",
        "CTX_wm_screen(C) == ddr->readback_screen",
        "CTX_data_scene(C) == ddr->readback_scene",
        "BKE_screen_find_area_xy(",
        "ddr->readback_event_xy) == ddr->readback_area",
        "ddr->readback_area->spacetype == SPACE_VIEW3D",
        "BKE_area_find_region_xy(",
        "ddr->readback_region",
        "ddr->readback_area->spacedata.first == ddr->readback_view3d",
        "ddr->readback_region->regiondata == ddr->readback_region_view",
    ):
        require(needle in context_guard, f"context guard missing {needle!r}")

    cleanup = braced_definition(
        eye, "static void depthdropper_exit(bContext *C, wmOperator *op)", "cleanup"
    )
    require_ordered(
        cleanup,
        (
            "if (ddr->readback_timer != nullptr)",
            "WM_event_timer_remove(",
            "ddr->readback_window",
            "ddr->readback_timer = nullptr;",
            "MEM_delete(ddr);",
        ),
        "readback cleanup order",
    )

    settle = braced_definition(
        eye,
        "static wmOperatorStatus depthdropper_readback_apply(bContext *C, wmOperator *op)",
        "settled replay",
    )
    require_ordered(
        settle,
        (
            "depthdropper_readback_context_matches(C, ddr)",
            "ddr->readback_session.sample(ddr->readback_region, co)",
            "ddr->readback_session.state() == ViewportDepthPickSession::ReadbackState::Failed",
            "ddr->readback_mval",
            "ED_view3d_win_to_3d(",
            "ddr->readback_view3d",
            "ddr->readback_region",
            "len_v3v3(ddr->readback_view_origin, co_align)",
            "DepthDropperReadbackAction::Accumulate",
            "DepthDropperReadbackAction::AccumulateAndSet",
            "depthdropper_depth_set_accum(C, ddr);",
            "if (ddr->readback_confirm_after)",
            "depthdropper_exit(C, op);",
        ),
        "settled action replay",
    )

    request = braced_definition(
        eye,
        "static wmOperatorStatus depthdropper_readback_request(bContext *C,",
        "readback request",
    )
    require_ordered(
        request,
        (
            "BKE_screen_find_area_xy(screen, SPACE_TYPE_ANY, m_xy)",
            "BKE_area_find_region_xy(area, RGN_TYPE_WINDOW, m_xy)",
            "CTX_wm_area_set(C, area);",
            "CTX_wm_region_set(C, region);",
            "ED_view3d_depth_override(",
            "ddr->readback_session.init(region, mval)",
            "CTX_wm_area_set(C, area_prev);",
            "CTX_wm_region_set(C, region_prev);",
            "ddr->readback_window = CTX_wm_window(C);",
            "copy_v2_v2_int(ddr->readback_event_xy, m_xy);",
            "copy_v2_v2_int(ddr->readback_mval, mval);",
            "copy_v3_v3(ddr->readback_view_origin, view_origin);",
            "ddr->readback_action = action;",
            "ReadbackState::Ready",
            "depthdropper_readback_apply(C, op)",
            "WM_event_timer_add(",
        ),
        "kick then poll",
    )
    require(
        "ED_view3d_autodist(" not in eye
        and "GPU_framebuffer_read_depth(" not in eye
        and "GPU_texture_read(" not in eye,
        "depth eyedropper still reaches synchronous GPU readback",
    )

    modal = braced_definition(
        eye, "static wmOperatorStatus depthdropper_modal(bContext *C", "modal continuation"
    )
    require_ordered(
        modal,
        (
            "event->type == TIMER",
            "event->customdata == ddr->readback_timer",
            "constexpr int max_tick_count = 240;",
            "if (++ddr->readback_tick_count > max_tick_count)",
            "ddr->readback_session.state();",
            "ReadbackState::Pending",
            "ReadbackState::Failed",
            "depthdropper_readback_apply(C, op)",
            "if (ddr->readback_confirm_after)",
            "EYE_MODAL_CANCEL",
            "EYE_MODAL_SAMPLE_CONFIRM",
            "ddr->readback_confirm_after = true;",
            "EYE_MODAL_SAMPLE_BEGIN",
            "DepthDropperReadbackAction::Accumulate",
            "EYE_MODAL_SAMPLE_RESET",
            "DepthDropperReadbackAction::AccumulateAndSet",
            "else if (event->type == MOUSEMOVE)",
            "DepthDropperReadbackAction::AccumulateAndSet",
        ),
        "bounded modal continuation",
    )
    require(
        "if (ddr->accum_tot == 0)" in modal,
        "pinned direct-confirm behavior disappeared",
    )
    require(
        modal.count("ddr->readback_confirm_after = true;") == 2,
        "confirm barrier must cover empty and accumulated pending samples",
    )

    return {
        "verdict": "PASS",
        "pin": PIN,
        "contracts": {
            "shared_owned_progressive_depth": True,
            "native_immediate_completion": True,
            "depth_eyedropper_modal_continuation": True,
            "producing_context_guard": True,
            "exact_view_aligned_depth": True,
            "accumulate_and_reset_replay": True,
            "confirm_waits_for_inflight_sample": True,
            "latest_drag_sample_supersedes_pending": True,
            "bounded_failure_cancellation": True,
            "pinned_direct_confirm_behavior": True,
            "live_hardware_receipt": False,
        },
        "converted_consumer": "depth_eyedropper",
        "remaining_depth_pick_consumers": [
            "navigation",
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
    eye_path = "source/blender/editors/interface/eyedroppers/eyedropper_depth.cc"
    mutations = (
        ("ViewportDepthPickSession readback_session;", "int readback_session;", "session"),
        (
            "CTX_data_scene(C) == ddr->readback_scene",
            "true",
            "scene guard",
        ),
        (
            "ddr->readback_region->regiondata == ddr->readback_region_view",
            "true",
            "region-view guard",
        ),
        (
            "ddr->readback_session.sample(ddr->readback_region, co)",
            "false",
            "settled sample",
        ),
        (
            "len_v3v3(ddr->readback_view_origin, co_align)",
            "0.0f",
            "view-aligned depth",
        ),
        (
            "ED_view3d_depth_override(",
            "ED_view3d_depth_override_removed(",
            "depth refresh",
        ),
        (
            "ddr->readback_session.init(region, mval)",
            "false",
            "owned kick",
        ),
        (
            "event->customdata == ddr->readback_timer",
            "true",
            "timer identity",
        ),
        (
            "if (++ddr->readback_tick_count > max_tick_count)",
            "if (false)",
            "bounded timeout",
        ),
        (
            "ddr->readback_confirm_after = true;",
            "ddr->readback_confirm_after = false;",
            "confirm barrier",
        ),
        (
            "DepthDropperReadbackAction::AccumulateAndSet",
            "DepthDropperReadbackAction::Accumulate",
            "set replay",
        ),
        (
            "WM_event_timer_remove(",
            "WM_event_timer_remove_missing(",
            "timer cleanup",
        ),
    )
    for before, after, label in mutations:
        mutated = dict(sources)
        text = mutated[eye_path]
        require(before in text, f"selfcheck setup missing {label!r}")
        mutated[eye_path] = text.replace(before, after, 1)
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
        print("M5_DEPTH_EYEDROPPER_SOURCE_SELFCHECK_PASS mutations=12")
        return 0
    receipt = validate(sources)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(
        "M5_DEPTH_EYEDROPPER_SOURCE_PASS "
        f"files={receipt['source_count']} sha256={receipt['source_sha256']} "
        "remaining_sync=3 live_receipt=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"M5_DEPTH_EYEDROPPER_SOURCE_FAIL {error}")
        raise SystemExit(1)
