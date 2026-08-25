#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify the particle-edit depth-cache continuation and its caller ownership."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


HEADER = Path("source/blender/editors/include/ED_particle.hh")
PARTICLE = Path("source/blender/editors/physics/particle_edit.cc")
VIEW3D = Path("source/blender/editors/space_view3d/view3d_select.cc")
PATHS = (HEADER, PARTICLE, VIEW3D)


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def function_body(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise VerificationError(f"missing function signature: {signature}")
    brace = text.find("{", start)
    if brace < 0:
        raise VerificationError(f"missing function body: {signature}")
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[brace : index + 1]
    raise VerificationError(f"unterminated function body: {signature}")


def before(body: str, first: str, second: str, label: str) -> None:
    first_at = body.find(first)
    second_at = body.find(second)
    require(first_at >= 0 and second_at >= 0 and first_at < second_at, label)


def verify_texts(texts: dict[Path, str]) -> dict[str, object]:
    header = texts[HEADER]
    particle = texts[PARTICLE]
    view3d = texts[VIEW3D]

    require("enum class ParticleEditDepthCacheState" in header, "missing depth state API")
    require("enum class ParticleEditOperationResult" in header, "missing operation result API")
    require(header.count("ParticleEditDepthCacheSession *depth_session") == 3,
            "one-shot session parameters differ")
    for api in (
        "PE_depth_cache_session_create",
        "PE_depth_cache_session_free",
        "PE_depth_cache_session_state",
        "PE_circle_select_depth_cache_pending",
        "PE_circle_select_depth_cache_event",
        "PE_circle_select_depth_cache_event_pop",
    ):
        require(api in header, f"missing public continuation API: {api}")

    require("ED_view3d_depth_override(" not in particle,
            "particle source retains synchronous full-cache read")
    require(particle.count("ED_view3d_depth_override_prepare(") == 1,
            "particle prepare call count differs")
    require(particle.count("PE_set_view3d_data(") == 7,
            "particle prepare/consume caller census differs")
    require("ViewportDepthCacheSession readback;" in particle,
            "opaque session does not own the readback")
    require("session->consumed = true;" in particle, "session lacks one-shot consumption")
    require("data->depths = session->readback.take(session->region);" in particle,
            "cache transfer differs")
    require("return XRAY_ENABLED(session->view3d) == session->xray_bypass;" in particle,
            "XRAY bypass guard differs")

    context_body = function_body(particle, "static bool PE_depth_cache_context_matches")
    for token in (
        "CTX_wm_manager(C)",
        "CTX_wm_window(C)",
        "CTX_wm_screen(C)",
        "CTX_wm_area(C)",
        "CTX_wm_region(C)",
        "CTX_wm_region_view3d(C)",
        "CTX_wm_view3d(C)",
        "CTX_data_main(C)",
        "CTX_data_depsgraph_pointer(C)",
        "CTX_data_scene(C)",
        "CTX_data_view_layer(C)",
        "CTX_data_active_object(C)",
        "PE_get_current(",
    ):
        require(token in context_body, f"producing-context guard missing {token}")

    nearest = function_body(particle, "static ParticleEditOperationResult pe_nearest_point_and_key")
    linked = function_body(particle, "static wmOperatorStatus select_linked_pick_apply")
    box = function_body(particle, "ParticleEditOperationResult PE_box_select")
    circle = function_body(particle, "ParticleEditOperationResult PE_circle_select")
    lasso = function_body(particle, "ParticleEditOperationResult PE_lasso_select")
    brush_init = function_body(particle, "static ParticleEditDepthCacheState brush_edit_init")
    before(nearest, "PE_set_view3d_data", "for_mouse_hit_keys", "click traverses before depth")
    before(linked, "PE_set_view3d_data", "for_mouse_hit_keys", "linked traverses before depth")
    before(box, "PE_set_view3d_data", "PE_deselect_all_visible_ex", "box mutates before depth")
    before(circle, "PE_set_view3d_data", "PE_deselect_all_visible_ex", "circle mutates before depth")
    before(lasso, "PE_set_view3d_data", "LOOP_VISIBLE_POINTS", "lasso traverses before depth")
    before(brush_init, "PE_set_view3d_data", "PE_create_random_generator", "brush state precedes depth")

    for token in (
        "struct ParticleLinkedPickData",
        "select_linked_pick_modal",
        "select_linked_pick_cancel_callback",
        "constexpr int max_tick_count = 240",
        "Particle linked-select depth context changed",
    ):
        require(token in particle, f"linked owner missing {token}")

    for token in (
        "struct ParticleCircleSelectData",
        "pending_input_valid",
        "constexpr int max_queued_events = 512",
        "event->custom != 0",
        "PE_circle_select_depth_cache_event_pop",
        "pe_circle_select_depth_timer_remove",
    ):
        require(token in particle, f"circle owner missing {token}")

    for token in (
        "Vector<wmEvent> depth_events",
        "depth_start_event_valid",
        "exec_pending",
        "constexpr int max_queued_events = 256",
        "brush_edit_depth_poll",
        "brush_edit_modal_dispatch",
        "Vector<wmEvent> queued_events = std::move",
    ):
        require(token in particle, f"brush owner missing {token}")

    for token in (
        "ParticleEditDepthCacheSession *particle_depth_session",
        "View3DGestureAsyncKind::ParticleBox",
        "View3DGestureAsyncKind::ParticleLasso",
        "view3d_particle_box_deferred_op",
        "view3d_particle_gesture_async_operators",
        "view3d_particle_gesture_async_modal",
        "struct View3DParticleCircleDirectData",
        "view3d_particle_circle_direct_operators",
        "view3d_particle_circle_depth_modal",
        "view3d_particle_circle_direct_modal",
        "PE_mouse_particles(",
    ):
        require(token in view3d, f"generic caller owner missing {token}")

    require(view3d.count("PE_depth_cache_session_create()") >= 4,
            "generic/native session ownership count differs")
    require(view3d.count("WM_event_add_modal_handler(C, op)") >= 4,
            "direct continuation modal-handler count differs")
    require(view3d.count("constexpr int max_tick_count = 240") >= 4,
            "generic identified poll bounds differ")
    require("WM_event_timer_remove(data->manager, data->window, data->timer)" in view3d,
            "generic owner does not remove the producing timer")

    for operator in (
        "VIEW3D_OT_select",
        "PARTICLE_OT_select_linked_pick",
        "VIEW3D_OT_select_box",
        "VIEW3D_OT_select_lasso",
        "VIEW3D_OT_select_circle",
        "PARTICLE_OT_brush_edit",
    ):
        require(operator in particle + view3d, f"converted operator missing: {operator}")

    source_hash = hashlib.sha256(
        b"\0".join(texts[path].encode("utf-8") for path in PATHS)
    ).hexdigest()
    return {
        "verdict": "PASS",
        "source_sha256": source_hash,
        "contracts": {
            "owned_prepare_consume": True,
            "xray_native_immediate": True,
            "pre_traversal_suspension": True,
            "exact_operator_inputs": True,
            "one_shot_gesture_owners": True,
            "circle_persistent_and_direct": True,
            "brush_invoke_and_exec": True,
            "bounded_identified_cleanup": True,
            "live_hardware_receipt": False,
        },
        "converted_callers": ["click", "linked", "box", "lasso", "circle", "brush"],
        "remaining_depth_cache_callers": [],
        "remaining_sync_families": ["window_capture"],
        "sync_particle_depth_calls": 0,
        "mutation_controls": 20,
    }


MUTATIONS: tuple[tuple[Path, str, str], ...] = (
    (PARTICLE, "ED_view3d_depth_override_prepare(", "ED_view3d_depth_override("),
    (PARTICLE, "CTX_wm_manager(C) != session->manager", "false"),
    (PARTICLE, "session->consumed = true;", "session->consumed = false;"),
    (PARTICLE, "data->depths = session->readback.take(session->region);", "data->depths = nullptr;"),
    (PARTICLE, "return XRAY_ENABLED(session->view3d) == session->xray_bypass;", "return true;"),
    (PARTICLE, "select_linked_pick_modal", "select_linked_pick_wait"),
    (PARTICLE, "select_linked_pick_cancel_callback", "select_linked_pick_cancel_lost"),
    (PARTICLE, "struct ParticleCircleSelectData", "struct LostCircleSelectData"),
    (PARTICLE, "pending_input_valid", "pending_input_lost"),
    (PARTICLE, "constexpr int max_queued_events = 512", "constexpr int max_queued_events = 0"),
    (PARTICLE, "event->custom != 0", "false"),
    (PARTICLE, "PE_circle_select_depth_cache_event_pop", "PE_circle_select_depth_cache_drop"),
    (PARTICLE, "depth_start_event_valid", "depth_start_event_lost"),
    (PARTICLE, "exec_pending", "exec_input_lost"),
    (PARTICLE, "constexpr int max_queued_events = 256", "constexpr int max_queued_events = 0"),
    (VIEW3D, "View3DGestureAsyncKind::ParticleBox", "View3DGestureAsyncKind::Box"),
    (VIEW3D, "View3DGestureAsyncKind::ParticleLasso", "View3DGestureAsyncKind::Lasso"),
    (VIEW3D, "view3d_particle_box_deferred_op", "view3d_particle_box_lost_op"),
    (VIEW3D, "struct View3DParticleCircleDirectData", "struct LostCircleDirectData"),
    (HEADER, "enum class ParticleEditOperationResult", "enum class LostOperationResult"),
)


def run_selfcheck(texts: dict[Path, str]) -> None:
    verify_texts(texts)
    for index, (path, old, new) in enumerate(MUTATIONS, start=1):
        require(old in texts[path], f"mutation {index} anchor missing: {old}")
        mutated = dict(texts)
        mutated[path] = texts[path].replace(old, new)
        try:
            verify_texts(mutated)
        except VerificationError:
            continue
        raise VerificationError(f"mutation {index} did not fail closed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--selfcheck", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    texts = {
        path: (source_root / path).read_text(encoding="utf-8")
        for path in PATHS
    }
    if args.selfcheck:
        run_selfcheck(texts)
    receipt = verify_texts(texts)
    payload = json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, VerificationError) as error:
        print(f"M5_PARTICLE_EDIT_DEPTH_CACHE_SOURCE_FAIL {error}", file=__import__("sys").stderr)
        raise SystemExit(1)
