#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed source contract for curve-draw depth-cache continuations."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PIN = "fbe6228777e7d9afefcd61a413844e790ae75db7"
SOURCE_PATHS = (
    "source/blender/editors/include/ED_view3d.hh",
    "source/blender/editors/space_view3d/view3d_draw.cc",
    "source/blender/editors/curve/editcurve_paint.cc",
    "source/blender/editors/curves/intern/curves_draw.cc",
)


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


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
        elif state == "string":
            if char == "\\":
                index += 2
                continue
            if char == '"':
                state = "code"
        elif state == "character":
            if char == "\\":
                index += 2
                continue
            if char == "'":
                state = "code"
        index += 1
    raise ContractError(f"{label}: unbalanced braces")


def load_sources(source_root: Path) -> dict[str, str]:
    sources: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = source_root / relative
        require(path.is_file(), f"source missing: {relative}")
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


def verify_lane(relative: str, text: str) -> None:
    lane = Path(relative).name
    require("SPDX-FileCopyrightText: 2026 blender-web contributors" in text,
            f"{lane}: web copyright missing")
    require("Ported for the web from " in text, f"{lane}: provenance missing")
    require('#include "BLI_vector.hh"' in text, f"{lane}: event FIFO include missing")

    data = braced_definition(text, "struct CurveDrawData", f"{lane} state")
    for needle in (
        "ViewportDepthCacheSession *depth_cache_session;",
        "Vector<wmEvent> *depth_cache_events;",
        "wmWindowManager *depth_cache_manager;",
        "wmTimer *depth_cache_timer;",
        "wmWindow *depth_cache_window;",
        "bScreen *depth_cache_screen;",
        "ScrArea *depth_cache_area;",
        "int depth_cache_tick_count;",
        "bool depth_cache_pending;",
    ):
        require(needle in data, f"{lane}: continuation state missing {needle!r}")

    context = braced_definition(
        text, "static bool curve_draw_depth_context_matches", f"{lane} context guard"
    )
    for needle in (
        "CTX_wm_manager(C) == cdd->depth_cache_manager",
        "CTX_wm_window(C) == cdd->depth_cache_window",
        "CTX_wm_screen(C) == cdd->depth_cache_screen",
        "CTX_wm_area(C) == cdd->depth_cache_area",
        "CTX_wm_region(C) == cdd->vc.region",
        "CTX_wm_view3d(C) == cdd->vc.v3d",
        "CTX_data_edit_object(C) == cdd->vc.obedit",
    ):
        require(needle in context, f"{lane}: producing-context guard missing {needle!r}")

    event_push = braced_definition(
        text, "static bool curve_draw_depth_event_push", f"{lane} event FIFO"
    )
    for needle in (
        "constexpr int max_queued_events = 256;",
        "event->custom != 0",
        "event->customdata != nullptr",
        "cdd->depth_cache_events->size() >= max_queued_events",
        "queued.next = nullptr;",
        "queued.prev = nullptr;",
        "queued.customdata = nullptr;",
        "queued.customdata_free = false;",
        "cdd->depth_cache_events->append(queued);",
    ):
        require(needle in event_push, f"{lane}: safe FIFO missing {needle!r}")

    cleanup = braced_definition(text, "static void curve_draw_exit", f"{lane} cleanup")
    for needle in (
        "curve_draw_depth_timer_remove(cdd);",
        "MEM_SAFE_DELETE(cdd->depth_cache_events);",
        "MEM_SAFE_DELETE(cdd->depth_cache_session);",
    ):
        require(needle in cleanup, f"{lane}: owned cleanup missing {needle!r}")

    invoke_signature = (
        "static wmOperatorStatus curve_draw_invoke"
        if lane == "editcurve_paint.cc"
        else "static wmOperatorStatus curves_draw_invoke"
    )
    invoke = braced_definition(text, invoke_signature, f"{lane} invoke")
    for needle in (
        "ED_view3d_depth_override_prepare(",
        "depth_mode,\n                                     false);",
        "MEM_new<ViewportDepthCacheSession>",
        "cdd->depth_cache_session->init(cdd->vc.region)",
        "ViewportDepthCacheSession::ReadbackState::Ready",
        "ViewportDepthCacheSession::ReadbackState::Pending",
        "curve_draw_depth_wait_begin(C, cdd)",
        "curve_draw_project_finalize(cdd);",
        "curve_draw_depth_event_push(cdd, event)",
        "WM_event_add_modal_handler(C, op);",
    ):
        require(needle in invoke, f"{lane}: invoke continuation missing {needle!r}")
    require("&cdd->depths" not in invoke,
            f"{lane}: synchronous full-cache read remains")

    poll = braced_definition(text, "static wmOperatorStatus curve_draw_depth_poll",
                             f"{lane} bounded poll")
    for needle in (
        "ELEM(event->type, EVT_ESCKEY, RIGHTMOUSE)",
        "event->type != TIMER || event->customdata != cdd->depth_cache_timer",
        "constexpr int max_tick_count = 240;",
        "++cdd->depth_cache_tick_count > max_tick_count",
        "ReadbackState::Pending",
        "ReadbackState::Failed",
        "cdd->depth_cache_session->take(cdd->vc.region)",
        "curve_draw_project_finalize(cdd);",
        "curve_draw_modal_dispatch(C, op, &queued)",
    ):
        require(needle in poll, f"{lane}: bounded settlement missing {needle!r}")

    modal_signature = (
        "static wmOperatorStatus curve_draw_modal("
        if lane == "editcurve_paint.cc"
        else "static wmOperatorStatus curves_draw_modal("
    )
    modal = braced_definition(text, modal_signature, f"{lane} modal wrapper")
    require("if (cdd->depth_cache_pending)" in modal, f"{lane}: pending path not dispatched")
    require("curve_draw_depth_poll(C, op, event)" in modal, f"{lane}: poll not called")
    require("curve_draw_modal_dispatch(C, op, event)" in modal,
            f"{lane}: stock modal tail not preserved")
    require("ot->cancel = curve_draw_cancel;" in text,
            f"{lane}: external cancellation callback missing")


def verify(sources: dict[str, str]) -> dict[str, object]:
    header = sources["source/blender/editors/include/ED_view3d.hh"]
    draw = sources["source/blender/editors/space_view3d/view3d_draw.cc"]
    require("void ED_view3d_depth_override_prepare(" in header,
            "forced draw-only depth API missing")
    prepare = braced_definition(
        draw, "void ED_view3d_depth_override_prepare(", "forced draw-only depth implementation"
    )
    require(
        "view3d_depth_override_impl(depsgraph, region, v3d, mode, use_overlay, nullptr, true);"
        in prepare,
        "draw-only API does not force the shared depth path",
    )
    impl = braced_definition(draw, "static void view3d_depth_override_impl(", "shared depth draw")
    require("!force_depth_update && (!r_depths || *r_depths != nullptr)" in impl,
            "forced redraw bypass missing")
    require("if (r_depths)" in impl and "*r_depths = view3d_depths_create(region);" in impl,
            "stock synchronous cache path drifted")
    for relative in SOURCE_PATHS[2:]:
        verify_lane(relative, sources[relative])
    return {
        "schema": 1,
        "pin": PIN,
        "verdict": "PASS",
        "contracts": {
            "two_curve_draw_lanes": True,
            "native_immediate_completion": True,
            "pending_event_fifo": True,
            "bounded_timer": True,
            "producing_context_guard": True,
            "failure_timeout_cancellation": True,
            "external_cancel_cleanup": True,
            "live_hardware_receipt": False,
        },
        "converted_callers": ["CURVE_OT_draw", "CURVES_OT_draw"],
        "remaining_sync_families": ["depth_cache", "window_capture"],
        "source_count": len(SOURCE_PATHS),
        "source_sha256": source_digest(sources),
    }


def replace_once(
    sources: dict[str, str], relative: str, old: str, new: str
) -> dict[str, str]:
    mutated = dict(sources)
    require(mutated[relative].count(old) == 1, f"mutation anchor drifted: {relative}: {old!r}")
    mutated[relative] = mutated[relative].replace(old, new, 1)
    return mutated


def selfcheck(sources: dict[str, str]) -> int:
    header = "source/blender/editors/include/ED_view3d.hh"
    draw = "source/blender/editors/space_view3d/view3d_draw.cc"
    curve = "source/blender/editors/curve/editcurve_paint.cc"
    curves = "source/blender/editors/curves/intern/curves_draw.cc"
    mutations = [
        (header, "void ED_view3d_depth_override_prepare(",
         "void ED_view3d_depth_override_blocking_prepare("),
        (draw,
         "view3d_depth_override_impl(depsgraph, region, v3d, mode, use_overlay, nullptr, true);",
         "view3d_depth_override_impl(depsgraph, region, v3d, mode, use_overlay, nullptr, false);"),
        (draw,
         "!force_depth_update && (!r_depths || *r_depths != nullptr)",
         "(!r_depths || *r_depths != nullptr)"),
    ]
    for relative in (curve, curves):
        mutations.extend(
            [
                (relative, "constexpr int max_queued_events = 256;",
                 "constexpr int max_queued_events = 257;"),
                (relative, "event->custom != 0 ||", "false /* unsafe custom accepted */ ||"),
                (relative, "CTX_wm_area(C) == cdd->depth_cache_area",
                 "true /* producing area ignored */"),
                (relative, "constexpr int max_tick_count = 240;",
                 "constexpr int max_tick_count = 241;"),
                (relative,
                 "cdd->depths = cdd->depth_cache_session->take(cdd->vc.region);\n"
                 "  if (cdd->depths == nullptr)",
                 "cdd->depths = nullptr; /* settled cache discarded */\n"
                 "  if (cdd->depths == nullptr)"),
                (relative, "ED_view3d_depth_override_prepare(cdd->vc.depsgraph,",
                 "ED_view3d_depth_override(cdd->vc.depsgraph,"),
                (relative,
                 "if (cdd->depth_cache_pending) {\n    return curve_draw_depth_poll(C, op, event);\n  }",
                 "if (false) {\n    return curve_draw_depth_poll(C, op, event);\n  }"),
                (relative, "ot->cancel = curve_draw_cancel;",
                 "/* external cancel callback omitted */"),
            ]
        )

    for index, (relative, old, new) in enumerate(mutations, 1):
        mutated = replace_once(sources, relative, old, new)
        try:
            verify(mutated)
        except ContractError:
            continue
        raise ContractError(f"mutation {index} did not fail closed")
    return len(mutations)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    try:
        sources = load_sources(args.source_root)
        result = verify(sources)
        mutation_count = selfcheck(sources) if args.selfcheck else 0
    except ContractError as exc:
        raise SystemExit(f"M5_CURVE_DEPTH_CACHE_SOURCE_FAIL {exc}") from exc
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "M5_CURVE_DEPTH_CACHE_SOURCE_PASS "
        f"sources={result['source_count']} mutations={mutation_count} "
        f"sha256={result['source_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
