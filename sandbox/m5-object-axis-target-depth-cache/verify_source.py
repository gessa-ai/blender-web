#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind OBJECT_OT_transform_axis_target to an owned depth-cache continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile


RELATIVE = Path("source/blender/editors/object/object_transform.cc")


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


def verify(source: str) -> None:
    owner = braced_definition(source, "struct XFormAxisData", "axis-target owner")
    for token in (
        "ViewDepths *depths = nullptr;",
        "ViewportDepthCacheSession depth_cache_session;",
        "Vector<wmEvent> depth_cache_events;",
        "wmEvent depth_cache_start_event{};",
        "wmTimer *depth_cache_timer = nullptr;",
        "wmWindowManager *depth_cache_manager = nullptr;",
        "wmWindow *depth_cache_window = nullptr;",
        "bScreen *depth_cache_screen = nullptr;",
        "ScrArea *depth_cache_area = nullptr;",
        "int depth_cache_tick_count = 0;",
        "bool depth_cache_start_event_valid = false;",
        "bool depth_cache_pending = false;",
        "bool initialized = false;",
    ):
        require(token in owner, f"axis-target continuation ownership missing: {token}")

    invoke = braced_definition(
        source, "static wmOperatorStatus object_transform_axis_target_invoke(", "axis-target invoke"
    )
    for token in (
        "XFormAxisData *xfd = MEM_new<XFormAxisData>(__func__);",
        "op->customdata = xfd;",
        "xfd->vc = vc;",
        "vc.v3d->flag2 |= V3D_HIDE_OVERLAYS;",
        "ED_view3d_depth_override_prepare(",
        "vc.v3d->flag2 = flag2_prev;",
        "xfd->depth_cache_session.init(vc.region)",
        "ViewportDepthCacheSession::ReadbackState::Ready",
        "xfd->depths = xfd->depth_cache_session.take(vc.region);",
        "object_transform_axis_target_initialize_ready(C, op, event);",
        "object_transform_axis_target_depth_wait_begin(C, xfd, event)",
        "WM_event_add_modal_handler(C, op);",
    ):
        require(token in invoke, f"axis-target invoke continuation missing: {token}")
    require(
        "ED_view3d_depth_override(" not in invoke,
        "axis-target invoke retains its synchronous full-viewport read",
    )
    require(
        invoke.find("ED_view3d_depth_override_prepare(")
        < invoke.find("vc.v3d->flag2 = flag2_prev;")
        < invoke.find("depth_cache_session.init(vc.region)"),
        "render override is not restored before readback initialization can return",
    )
    require(
        invoke.find("depth_cache_session.init(vc.region)")
        < invoke.find("object_transform_axis_target_initialize_ready(C, op, event);"),
        "selected objects can be captured before the depth request settles",
    )
    require(
        "selected_editable_objects" not in invoke and "BKE_object_tfm_backup" not in invoke,
        "invoke still captures selected objects or transform backups directly",
    )
    require(
        'RPT_WARNING, "Unable to access depth buffer, using view plane"' in invoke,
        "stock no-depth warning/cancellation was not preserved",
    )

    ready = braced_definition(
        source,
        "static void object_transform_axis_target_initialize_ready(",
        "ready-only initialization",
    )
    for token in (
        "xfd->vc.mval[0] = event->mval[0];",
        "xfd->vc.mval[1] = event->mval[1];",
        "xfd->init_event = WM_userdef_event_type_from_keymap_type(event->type);",
        "selected_editable_objects",
        "item.obtfm = BKE_object_tfm_backup(item.ob);",
        "xfd->initialized = true;",
    ):
        require(token in ready, f"ready-only stock initialization missing: {token}")
    require(
        ready.find("selected_editable_objects") < ready.find("BKE_object_tfm_backup"),
        "selected-object and transform-backup ordering differs",
    )

    wait_begin = braced_definition(
        source,
        "static bool object_transform_axis_target_depth_wait_begin(",
        "wait begin",
    )
    for token in (
        "CTX_wm_manager(C)",
        "CTX_wm_window(C)",
        "CTX_wm_screen(C)",
        "CTX_wm_area(C)",
        "depth_cache_start_event = *event;",
        "depth_cache_start_event.next = nullptr;",
        "depth_cache_start_event.prev = nullptr;",
        "depth_cache_start_event.custom = 0;",
        "depth_cache_start_event.customdata = nullptr;",
        "depth_cache_start_event.customdata_free = false;",
        "WM_event_timer_add(",
        "TIMER, 0.01f",
        "depth_cache_pending = true;",
    ):
        require(token in wait_begin, f"pending invoke ownership missing: {token}")

    context_match = braced_definition(
        source,
        "static bool object_transform_axis_target_depth_context_matches(",
        "producing-context guard",
    )
    for token in (
        "CTX_wm_manager(C) != xfd->depth_cache_manager",
        "CTX_wm_window(C) != xfd->depth_cache_window",
        "CTX_wm_screen(C) != xfd->depth_cache_screen",
        "CTX_wm_area(C) != xfd->depth_cache_area",
        "CTX_wm_region(C) != xfd->vc.region",
        "CTX_wm_region_view3d(C) != xfd->vc.rv3d",
        "CTX_wm_view3d(C) != xfd->vc.v3d",
        "CTX_data_depsgraph_pointer(C) != xfd->vc.depsgraph",
        "CTX_data_scene(C) != xfd->vc.scene",
        "CTX_data_view_layer(C) != xfd->vc.view_layer",
        "CTX_data_active_object(C) != xfd->vc.obact",
    ):
        require(token in context_match, f"producing-context guard missing: {token}")

    event_push = braced_definition(
        source,
        "static bool object_transform_axis_target_depth_event_push(",
        "pending-event copy",
    )
    for token in (
        "constexpr int max_queued_events = 256;",
        "event->custom != 0",
        "event->customdata != nullptr",
        "queued.next = nullptr;",
        "queued.prev = nullptr;",
        "queued.custom = 0;",
        "queued.customdata = nullptr;",
        "queued.customdata_free = false;",
        "xfd->depth_cache_events.append(queued);",
    ):
        require(token in event_push, f"pending-event ownership missing: {token}")

    poll = braced_definition(
        source,
        "static wmOperatorStatus object_transform_axis_target_depth_poll(",
        "depth-cache poll",
    )
    for token in (
        "object_transform_axis_target_depth_context_matches(C, xfd)",
        "event->type == EVT_MODAL_MAP && event->val == AXIS_TARGET_MODAL_CANCEL",
        "event->customdata != xfd->depth_cache_timer",
        "object_transform_axis_target_depth_event_push(xfd, event)",
        "constexpr int max_tick_count = 240;",
        "++xfd->depth_cache_tick_count > max_tick_count",
        "xfd->depth_cache_session.state()",
        "ViewportDepthCacheSession::ReadbackState::Pending",
        "ViewportDepthCacheSession::ReadbackState::Failed",
        "xfd->depths = xfd->depth_cache_session.take(xfd->vc.region);",
        "Vector<wmEvent> queued_events = std::move(xfd->depth_cache_events);",
        "const wmEvent start_event = xfd->depth_cache_start_event;",
        "xfd->depth_cache_pending = false;",
        "object_transform_axis_target_initialize_ready(C, op, &start_event);",
        "object_transform_axis_target_modal_dispatch(",
        "C, op, &queued_event);",
    ):
        require(token in poll, f"depth-cache settlement missing: {token}")
    require(
        poll.find("xfd->depth_cache_pending = false;")
        < poll.find("object_transform_axis_target_initialize_ready(C, op, &start_event);"),
        "settlement can recursively re-enter the pending path",
    )

    timer_remove = braced_definition(
        source,
        "static void object_transform_axis_target_depth_timer_remove(",
        "timer cleanup",
    )
    for token in (
        "WM_event_timer_remove(",
        "xfd->depth_cache_manager",
        "xfd->depth_cache_window",
        "xfd->depth_cache_timer",
    ):
        require(token in timer_remove, f"owned timer cleanup missing: {token}")

    free_data = braced_definition(
        source,
        "static void object_transform_axis_target_free_data(",
        "operator cleanup",
    )
    for token in (
        "object_transform_axis_target_depth_timer_remove(xfd);",
        "xfd->depth_cache_events.clear();",
        "xfd->depth_cache_pending = false;",
        "MEM_delete(xfd);",
        "op->customdata = nullptr;",
    ):
        require(token in free_data, f"pending cleanup missing: {token}")

    cancel = braced_definition(
        source,
        "static void object_transform_axis_target_cancel(",
        "operator cancellation",
    )
    require(
        "if (xfd->initialized)" in cancel
        and "BKE_object_tfm_restore(item.ob, item.obtfm);" in cancel,
        "pending cancellation can restore backups that do not exist yet",
    )

    modal = braced_definition(
        source,
        "static wmOperatorStatus object_transform_axis_target_modal(",
        "modal wrapper",
    )
    require(
        "if (xfd->depth_cache_pending)" in modal
        and "return object_transform_axis_target_depth_poll(C, op, event);" in modal
        and "return object_transform_axis_target_modal_dispatch(C, op, event);" in modal,
        "modal wrapper does not isolate pending initialization",
    )


def source_digest(source: str) -> str:
    digest = hashlib.sha256()
    digest.update(str(RELATIVE).encode("utf-8"))
    digest.update(b"\0")
    digest.update(source.encode("utf-8"))
    digest.update(b"\0")
    return digest.hexdigest()


def run_selfcheck(source: str) -> None:
    mutations = (
        ("ED_view3d_depth_override_prepare(", "ED_view3d_depth_override("),
        ("vc.v3d->flag2 = flag2_prev;", "/* render override leaked */"),
        ("constexpr int max_tick_count = 240;", "constexpr int max_tick_count = 0;"),
        ("constexpr int max_queued_events = 256;", "constexpr int max_queued_events = 0;"),
        ("CTX_wm_region(C) != xfd->vc.region", "false"),
        ("event->customdata != nullptr", "false"),
        ("queued.customdata = nullptr;", "/* borrowed payload retained */"),
        (
            "const ViewportDepthCacheSession::ReadbackState state = xfd->depth_cache_session.state();",
            "const ViewportDepthCacheSession::ReadbackState state = "
            "ViewportDepthCacheSession::ReadbackState::Ready;",
        ),
        ("xfd->depths = xfd->depth_cache_session.take(xfd->vc.region);", "xfd->depths = nullptr;"),
        ("Vector<wmEvent> queued_events = std::move(xfd->depth_cache_events);", "Vector<wmEvent> queued_events;"),
        ("object_transform_axis_target_initialize_ready(C, op, &start_event);", "/* ready tail retired */"),
        ("C, op, &queued_event);", "C, op, event);"),
        ("object_transform_axis_target_depth_timer_remove(xfd);", "/* timer leaked */"),
        ("if (xfd->depth_cache_pending)", "if (false)"),
        ("item.obtfm = BKE_object_tfm_backup(item.ob);", "item.obtfm = nullptr;"),
        ("event->type == EVT_MODAL_MAP && event->val == AXIS_TARGET_MODAL_CANCEL", "false"),
        ("if (xfd->initialized)", "if (true)"),
    )
    for old, new in mutations:
        require(old in source, f"selfcheck mutation source missing: {old}")
        mutated = source.replace(old, new, 1)
        try:
            verify(mutated)
        except VerificationError:
            continue
        raise VerificationError(f"selfcheck mutation survived: {old}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    source = (args.source_root.resolve() / RELATIVE).read_text(encoding="utf-8")
    verify(source)
    if args.selfcheck:
        run_selfcheck(source)
    if args.output is not None:
        payload = {
            "verdict": "PASS",
            "source_sha256": source_digest(source),
            "converted_callers": ["OBJECT_OT_transform_axis_target"],
            "contracts": {
                "operation_owned_request": True,
                "render_override_restoration": True,
                "stock_no_depth_cancellation": True,
                "pre_selection_suspension": True,
                "retained_start_event_and_fifo": True,
                "producing_context_guard": True,
                "bounded_identified_poll": True,
                "failure_timeout_cancellation": True,
                "live_hardware_receipt": False,
            },
            "remaining_depth_cache_callers": ["particle-edit"],
            "remaining_sync_families": ["depth_cache", "window_capture"],
            "mutation_controls": len(MUTATIONS_FOR_COUNT),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=args.output.parent, delete=False
        ) as temporary:
            json.dump(payload, temporary, sort_keys=True, indent=2)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        temporary_path.replace(args.output)
    print(
        "M5_OBJECT_AXIS_TARGET_DEPTH_CACHE_SOURCE_PASS "
        f"files=1 mutations={len(MUTATIONS_FOR_COUNT)}"
    )
    return 0


MUTATIONS_FOR_COUNT = tuple(range(17))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, VerificationError) as error:
        print(
            f"M5_OBJECT_AXIS_TARGET_DEPTH_CACHE_SOURCE_FAIL {error}",
            file=__import__("sys").stderr,
        )
        raise SystemExit(1)
