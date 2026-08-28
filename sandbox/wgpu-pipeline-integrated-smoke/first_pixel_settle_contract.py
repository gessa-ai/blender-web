#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind deferred WebGPU readiness and resize commits to bounded window redraw recovery."""

from __future__ import annotations

import argparse
from pathlib import Path


PROCESS_MARKER = "bool GHOST_SystemWeb::processEvents(bool /*waitForEvent*/)"
CREATE_MARKER = "GHOST_IWindow *GHOST_SystemWeb::createWindow("
HELPER_MARKER = "inline bool redraw_recovery_tick("
SHADER_MODULE_MARKER = "bool WGPUShader::ensure_shader_modules("
COMPUTE_PIPELINE_MARKER = "wgpu::ComputePipeline WGPUShader::compute_pipeline("
BIND_GROUP_MARKER = "bool WGPUShader::bind_group_entries_complete("
EXPLICIT_LAYOUT_MARKER = "bool WGPUShader::ensure_explicit_layout("
RENDER_PIPELINE_MARKER = "wgpu::RenderPipeline WGPUPipelinePool::get("
RESIZE_COMMIT_MARKER = "void GHOST_ContextWGPUWeb::ensureBackbuffer()"
SWAP_RELEASE_MARKER = "GHOST_TSuccess GHOST_ContextWGPUWeb::swapBufferRelease()"
PRESENT_BACKBUFFER_MARKER = "bool GHOST_ContextWGPUWeb::presentBackbuffer()"


def method(source: str, marker: str) -> str:
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"missing method: {marker}")
    opening = source.find("{", start)
    if opening < 0:
        raise ValueError(f"missing method body: {marker}")
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated method: {marker}")


def require_once(source: str, token: str, label: str) -> None:
    if source.count(token) != 1:
        raise ValueError(f"{label} requires exactly one {token!r}")


def require_count(source: str, token: str, count: int, label: str) -> None:
    if source.count(token) != count:
        raise ValueError(f"{label} requires {count} occurrences of {token!r}")


def validate(
    display_header: str,
    system_header: str,
    system_source: str,
    wm_window_source: str,
    shader_source: str,
    pipeline_source: str,
    context_source: str,
) -> None:
    helper = method(display_header, HELPER_MARKER)
    for token in (
        "FIRST_PIXEL_SETTLE_TICKS = 180u",
        "FIRST_PIXEL_SETTLE_INTERVAL = 12u",
        "inline std::atomic<uint64_t> redraw_retry_counter{0};",
        "inline std::atomic<uint64_t> input_redraw_retry_counter{0};",
        "inline std::atomic<uint64_t> redraw_episode_counter{0};",
        "inline std::atomic<uint64_t> redraw_drop_counter{0};",
        "inline std::atomic<uint64_t> present_suppressed_counter{0};",
        "inline std::atomic<uint64_t> present_replay_counter{0};",
        "inline void request_redraw_retry()",
        "inline uint64_t redraw_retry_generation()",
        "inline void request_input_redraw_retry()",
        "inline uint64_t input_redraw_retry_generation()",
        "inline uint64_t request_redraw_episode()",
        "inline uint64_t redraw_episode_generation()",
        "inline void note_redraw_drop()",
        "inline uint64_t redraw_drop_generation()",
        "inline void note_present_suppressed()",
        "inline uint64_t present_suppressed_count()",
        "inline uint64_t request_present_replay()",
        "inline uint64_t present_replay_generation()",
        "inline uint64_t present_replay_count()",
        "inline void redraw_trace_frame_begin(",
        "inline bool redraw_present_frame_matches_episode(",
        "inline bool redraw_present_trace_complete(",
        "class RedrawPresentBarrier {",
        "inline RedrawPresentBarrier redraw_present_barrier;",
        "inline bool schedule_redraw_present_barrier(",
        "inline bool arrive_redraw_present_barrier(",
        "inline bool filter_redraw_present_barrier_update(",
        "inline bool complete_redraw_present_barrier(",
        "inline bool cancel_redraw_present_barrier(",
        "inline bool cancel_superseded_redraw_present_barrier(",
        "inline RedrawTraceSnapshot redraw_present_barrier_ready_trace_snapshot()",
        "inline uint64_t redraw_present_barrier_completion_generation()",
    ):
        require_once(display_header, token, "redraw recovery state")
    present_replay_request = method(display_header, "inline uint64_t request_present_replay()")
    require_once(
        present_replay_request,
        "present_replay_counter.fetch_add(1u, std::memory_order_release) + 1u",
        "WM-owned present replay publication",
    )
    present_replay_generation = method(
        display_header, "inline uint64_t present_replay_generation()"
    )
    require_once(
        present_replay_generation,
        "present_replay_counter.load(std::memory_order_acquire)",
        "WM-owned present replay generation",
    )
    frame_match = method(display_header, "inline bool redraw_present_frame_matches_episode(")
    require_once(
        frame_match,
        "return frame_episode == current_episode;",
        "resize frame episode binding",
    )
    frame_begin = method(display_header, "inline void redraw_trace_frame_begin(")
    for token in (
        "redraw_trace_state.frame_draw_count = 0;",
        "redraw_trace_state.frame_offscreen_draw_count = 0;",
        "redraw_trace_state.frame_window_draw_count = 0;",
        "redraw_trace_state.frame_first_offscreen_sequence = 0;",
        "redraw_trace_state.frame_last_window_sequence = 0;",
        "redraw_trace_state.last = {};",
        "redraw_trace_state.background = {};",
        "redraw_trace_state.display = {};",
    ):
        require_once(frame_begin, token, "frame-local resize trace reset")
    frame_complete = method(display_header, "inline bool redraw_present_trace_complete(")
    for token in (
        "trace.episode_generation == episode",
        "trace.frame_draw_count >= 2u",
        "trace.frame_offscreen_draw_count > 0u",
        "trace.frame_window_draw_count > 0u",
        "trace.frame_first_offscreen_sequence > 0u",
        "trace.frame_last_window_sequence > trace.frame_first_offscreen_sequence",
        "trace.frame_last_window_sequence == trace.last.sequence",
        "trace.background.sequence > 0u",
        "!trace.background.window_target",
        "trace.display.sequence > trace.background.sequence",
        "trace.display.window_target",
    ):
        require_once(frame_complete, token, "completed resize frame admission")
    trace_note = method(display_header, "inline void redraw_trace_note(")
    for token in (
        "redraw_trace_state.frame_draw_count++;",
        "redraw_trace_state.frame_window_draw_count++;",
        "redraw_trace_state.frame_last_window_sequence = plan.sequence;",
        "redraw_trace_state.frame_offscreen_draw_count++;",
        "redraw_trace_state.frame_first_offscreen_sequence = plan.sequence;",
    ):
        require_once(trace_note, token, "frame-local resize trace capture")
    barrier = method(display_header, "class RedrawPresentBarrier")
    for token in (
        "bool schedule(const uint64_t episode, RedrawTraceSnapshot trace_snapshot = {})",
        "bool arrive(const uint64_t episode, Completion completion)",
        "bool filter_update(const uint64_t episode, const bool requested)",
        "bool complete(const uint64_t episode, const bool valid)",
        "bool cancel(const uint64_t episode)",
        "bool cancel_superseded(const uint64_t current_episode)",
        "RedrawTraceSnapshot ready_trace_snapshot() const",
        "trace_snapshot.episode_generation == episode ? std::move(trace_snapshot) :",
        "superseded(false);",
        "phase_ = Phase::Ready;",
        "completion(valid);",
        "completion_generation_++;",
    ):
        require_once(barrier, token, "resize present barrier")
    episode_request = method(display_header, "inline uint64_t request_redraw_episode()")
    require_once(episode_request, "return generation;", "resize episode publication")
    input_request = method(display_header, "inline void request_input_redraw_retry()")
    require_once(
        input_request,
        "input_redraw_retry_counter.fetch_add(1u, std::memory_order_release);",
        "ordinary-input trailing recovery publication",
    )
    require_once(
        input_request,
        "\n  redraw_retry_counter.fetch_add(1u, std::memory_order_release);",
        "ordinary-input aggregate retry publication",
    )
    input_generation_getter = method(
        display_header, "inline uint64_t input_redraw_retry_generation()"
    )
    require_once(
        input_generation_getter,
        "return input_redraw_retry_counter.load(std::memory_order_acquire);",
        "ordinary-input trailing recovery generation",
    )
    supersession = method(
        display_header, "bool cancel_superseded(const uint64_t current_episode)"
    )
    for token in (
        "phase_ == Phase::Idle || scheduled_episode_ == current_episode",
        "completion = std::move(completion_);",
        "phase_ = Phase::Idle;",
        "scheduled_episode_ = 0;",
        "scheduled_trace_snapshot_ = {};",
        "update_requested_ = false;",
        "completion(false);",
    ):
        require_once(token=token, source=supersession, label="commit-time barrier supersession")
    supersession_adapter = method(
        display_header, "inline bool cancel_superseded_redraw_present_barrier("
    )
    for token in (
        "redraw_present_barrier.cancel_superseded(current_episode)",
        "request_redraw_retry();",
        "return canceled;",
    ):
        require_once(
            supersession_adapter, token, "commit-time barrier supersession adapter"
        )
    require_count(
        barrier,
        "scheduled_trace_snapshot_",
        6,
        "resize present barrier trace lifetime",
    )
    for token in (
        "retry_generation != retry_generation_seen",
        "retry_generation_seen = retry_generation;",
        "episode_generation != episode_generation_seen",
        "episode_generation_seen = episode_generation;",
        "drop_generation != drop_generation_seen",
        "drop_generation_seen = drop_generation;",
        "input_retry_generation != input_retry_generation_seen",
        "input_retry_generation_seen = input_retry_generation;",
        "const bool reopen_trace = heartbeat >= FIRST_PIXEL_SETTLE_TICKS;",
        "if (reopen_trace && viewport_content_present_count() == 0u)",
        "episode_published || input_published || readiness_published ||",
        "draw_dropped ||",
        "(heartbeat % FIRST_PIXEL_SETTLE_INTERVAL) == 0u",
        "heartbeat++;",
        "return request_update;",
    ):
        require_once(helper, token, "redraw recovery helper")
    require_count(helper, "if (heartbeat >= FIRST_PIXEL_SETTLE_TICKS)", 2,
                  "redraw recovery helper")
    require_count(helper, "heartbeat = 0;", 3, "redraw recovery helper")
    generic_present_helper = helper.replace("viewport_content_present_count()", "")
    if "present_count" in generic_present_helper or "present_baseline" in helper:
        raise ValueError("redraw recovery still terminates on presentation count")

    require_once(
        system_header,
        "uint64_t redraw_retry_generation_seen_ = 0;",
        "per-window recovery state",
    )
    require_once(
        system_header,
        "uint64_t input_redraw_retry_generation_seen_ = 0;",
        "per-window input-tail state",
    )
    require_once(
        system_header,
        "uint64_t redraw_episode_generation_seen_ = 0;",
        "per-window episode state",
    )
    require_once(
        system_header,
        "uint64_t redraw_drop_generation_seen_ = 0;",
        "per-window drop state",
    )
    require_once(
        system_header,
        "uint64_t redraw_present_barrier_completion_seen_ = 0;",
        "per-window present-barrier state",
    )
    require_once(
        system_header,
        "uint64_t present_replay_generation_seen_ = 0;",
        "per-window settlement-replay state",
    )
    if "redraw_present_baseline_" in system_header:
        raise ValueError("obsolete two-present terminal state remains")

    process = method(system_source, PROCESS_MARKER)
    for token in (
        "ghost_web::redraw_recovery_tick(",
        "ghost_web::redraw_retry_generation()",
        "\n                                      redraw_retry_generation_seen_,",
        "ghost_web::input_redraw_retry_generation()",
        "\n                                      input_redraw_retry_generation_seen_,",
        "ghost_web::redraw_episode_generation()",
        "redraw_episode_generation_seen_",
        "ghost_web::redraw_drop_generation()",
        "redraw_drop_generation_seen_",
        "ghost_web::redraw_present_barrier_completion_generation()",
        "ghost_web::redraw_present_barrier_completed_episode()",
        "ghost_web::filter_redraw_present_barrier_update(",
        "ghost_web::present_replay_generation()",
        "const bool present_replay_pending =",
        "redraw_recovery_requested || present_replay_pending",
        "GHOST_kEventWindowUpdate",
    ):
        require_once(process, token, "processEvents recovery wiring")
    require_count(
        process,
        "redraw_present_barrier_completion_seen_",
        2,
        "processEvents recovery wiring",
    )
    require_count(process, "present_replay_generation_seen_", 2,
                  "processEvents settlement-replay wiring")
    replay_generation_at = process.index("ghost_web::present_replay_generation()")
    replay_pending_at = process.index("const bool present_replay_pending =")
    replay_request_at = process.index("redraw_recovery_requested || present_replay_pending")
    replay_filter_at = process.index("ghost_web::filter_redraw_present_barrier_update(")
    replay_event_at = process.index("GHOST_kEventWindowUpdate", replay_filter_at)
    replay_consume_at = process.index(
        "present_replay_generation_seen_ = present_replay_generation;", replay_event_at
    )
    if not (replay_generation_at < replay_pending_at < replay_filter_at < replay_request_at <
            replay_event_at < replay_consume_at):
        raise ValueError("settlement replay is consumed before its WM update is admitted")
    if "GHOST_kEventWindowActivate" in process:
        raise ValueError("redraw recovery injects synthetic activation")

    resize = method(process, "if (ghost_web::poll_pending_backing(nw, nh))")
    resize_retry = "ghost_web::request_redraw_retry();"
    require_once(resize, resize_retry, "browser resize recovery wiring")
    resize_positions = (
        resize.index("window_->reconfigureSurface();"),
        resize.index("GHOST_kEventWindowSize"),
        resize.index(resize_retry),
    )
    if resize_positions != tuple(sorted(resize_positions)):
        raise ValueError("browser resize retry is not published after extent and WM size update")

    creation = method(system_source, CREATE_MARKER)
    generation = "redraw_retry_generation_seen_ = ghost_web::redraw_retry_generation();"
    input_generation = (
        "input_redraw_retry_generation_seen_ = ghost_web::input_redraw_retry_generation();"
    )
    episode_generation = (
        "redraw_episode_generation_seen_ = ghost_web::redraw_episode_generation();"
    )
    drop_generation = "redraw_drop_generation_seen_ = ghost_web::redraw_drop_generation();"
    heartbeat = "redraw_heartbeat_ = 0;"
    require_once(creation, generation, "window publication")
    require_once(creation, input_generation, "window publication")
    require_once(creation, episode_generation, "window publication")
    require_once(creation, drop_generation, "window publication")
    barrier_completion = (
        "redraw_present_barrier_completion_seen_ =\n"
        "              ghost_web::redraw_present_barrier_completion_generation();"
    )
    require_once(creation, barrier_completion, "window publication")
    replay_generation = (
        "present_replay_generation_seen_ = ghost_web::present_replay_generation();"
    )
    require_once(creation, replay_generation, "window publication")
    require_once(creation, heartbeat, "window publication")
    if max(
        creation.index(generation),
        creation.index(input_generation),
        creation.index(episode_generation),
        creation.index(drop_generation),
    ) > creation.index(heartbeat):
        raise ValueError("window publication resets ticks before capturing its retry generation")

    resize_commit = method(context_source, RESIZE_COMMIT_MARKER)
    committed = method(
        resize_commit,
        "if (result == ghost_web::SurfaceResizeResult::Committed)",
    )
    require_once(
        committed,
        "const uint64_t committed_redraw_episode =\n"
        "                        ghost_web::request_redraw_episode();",
        "coherent resize commit recovery",
    )
    require_once(
        committed,
        "owner.backbuffer_redraw_episode_ = committed_redraw_episode;",
        "coherent resize episode binding",
    )
    require_once(
        committed,
        "ghost_web::cancel_superseded_redraw_present_barrier(\n"
        "                        committed_redraw_episode);",
        "coherent resize barrier supersession",
    )
    resize_commit_order = (
        committed.index("ghost_web::request_redraw_episode();"),
        committed.index("owner.backbuffer_redraw_episode_ = committed_redraw_episode;"),
        committed.index("ghost_web::cancel_superseded_redraw_present_barrier("),
    )
    if resize_commit_order != tuple(sorted(resize_commit_order)):
        raise ValueError("resize commit releases an old barrier before binding the new episode")
    if resize_commit.index("surface_resize_commit_if_current(") > resize_commit.index(
        "if (result == ghost_web::SurfaceResizeResult::Committed)"
    ):
        raise ValueError("resize recovery is published before the coherent commit result")

    swap_release = method(context_source, SWAP_RELEASE_MARKER)
    for token in (
        "ghost_web::redraw_present_barrier_ready_trace_snapshot()",
        "ghost_web::redraw_present_trace_complete(completed_frame, episode)",
        "ghost_web::complete_redraw_present_barrier(episode, false);",
        "const bool presented = presentBackbuffer();",
        "const uint64_t active_redraw_episode = ghost_web::redraw_episode_generation();",
        "if (ghost_web::redraw_trace_active(active_redraw_episode))",
    ):
        require_once(swap_release, token, "completed resize frame admission")
    snapshot_at = swap_release.index(
        "ghost_web::redraw_present_barrier_ready_trace_snapshot()"
    )
    complete_check_at = swap_release.index(
        "ghost_web::redraw_present_trace_complete(completed_frame, episode)"
    )
    reject_at = swap_release.index(
        "ghost_web::complete_redraw_present_barrier(episode, false);"
    )
    retry_return_at = swap_release.find("return GHOST_kSuccess;", reject_at)
    present_at = swap_release.index("const bool presented = presentBackbuffer();")
    active_episode_at = swap_release.index(
        "const uint64_t active_redraw_episode = ghost_web::redraw_episode_generation();"
    )
    withhold_at = swap_release.index(
        "if (ghost_web::redraw_trace_active(active_redraw_episode))"
    )
    withhold_return_at = swap_release.find("return GHOST_kSuccess;", withhold_at)
    fallback_present_at = swap_release.rfind(
        "return presentBackbuffer() ? GHOST_kSuccess : GHOST_kFailure;"
    )
    if not (
        snapshot_at < complete_check_at < reject_at < retry_return_at < present_at
        < active_episode_at < withhold_at < withhold_return_at < fallback_present_at
    ):
        raise ValueError("incomplete resize frame can reach synchronous presentation")

    for token in (
        "extern \"C\" EMSCRIPTEN_KEEPALIVE double bw_present_suppressed_count(void)",
        "return double(ghost_web::present_suppressed_count());",
        "extern \"C\" EMSCRIPTEN_KEEPALIVE double bw_present_replay_count(void)",
        "return double(ghost_web::present_replay_count());",
    ):
        require_once(context_source, token, "suppressed-present telemetry export")
    present_backbuffer = method(context_source, PRESENT_BACKBUFFER_MARKER)
    for token in (
        "ghost_web::note_present_suppressed();",
        "ghost_web::request_present_replay();",
    ):
        require_once(present_backbuffer, token, "suppressed-present telemetry publication")
    overlap_at = present_backbuffer.index(
        "const bool validation_scope_pending = present_settlement_.defer_if_pending();"
    )
    validate_at = present_backbuffer.index(
        "const bool validate_transaction = !validation_scope_pending;"
    )
    suppressed_at = present_backbuffer.index("ghost_web::note_present_suppressed();")
    backbuffer_at = present_backbuffer.index("ensureBackbuffer();")
    begin_at = present_backbuffer.index(
        "if (validate_transaction) {\n    present_settlement_.begin();"
    )
    encode_scope_at = present_backbuffer.index(
        "[device, validate_transaction]() {\n            if (validate_transaction)"
    )
    unscoped_complete_at = present_backbuffer.index(
        "if (validate_transaction) {\n              popErrorScopes(device, \"present command encoding\""
    )
    settlement_at = present_backbuffer.index(
        "const bool retry_after_settlement =\n"
        "                  validate_transaction ? owner.present_settlement_.complete() : false;"
    )
    replay_request_at = present_backbuffer.index("ghost_web::request_present_replay();")
    settlement_tail = present_backbuffer[settlement_at:]
    if "owner.presentBackbuffer()" in settlement_tail:
        raise ValueError("settlement replay still acquires a surface outside the WM draw boundary")
    if "return false;" in present_backbuffer[suppressed_at:backbuffer_at]:
        raise ValueError("validation overlap still suppresses the synchronous WM present")
    if not (
        overlap_at < validate_at < suppressed_at < backbuffer_at < begin_at < encode_scope_at
        < unscoped_complete_at < settlement_at < replay_request_at
    ):
        raise ValueError("validation overlap does not bind unscoped WM present and final replay")

    update_case = wm_window_source.find("case GHOST_kEventWindowUpdate:")
    case_end = wm_window_source.find("break;", update_case)
    if update_case < 0 or case_end < 0:
        raise ValueError("missing WindowUpdate handler")
    update_handler = wm_window_source[update_case:case_end]
    web_notifier = "WM_event_add_notifier_ex(wm, win, NC_SCREEN | NA_EDITED, nullptr);"
    redraw_request = "win->runtime->web_full_redraw_after_window_update = true;"
    require_once(update_handler, redraw_request, "Emscripten WindowUpdate redraw request")
    require_once(update_handler, web_notifier, "Emscripten WindowUpdate handler")
    redraw_request_at = update_handler.find(redraw_request)
    notifier = update_handler.find(web_notifier)
    if notifier < 0:
        raise ValueError("screen notifier is not inside the WindowUpdate handler")
    emscripten_guard = update_handler.rfind("#ifdef __EMSCRIPTEN__", 0, notifier)
    if emscripten_guard < 0 or redraw_request_at < emscripten_guard:
        raise ValueError("screen notifier is not Emscripten-only")
    if redraw_request_at > notifier:
        raise ValueError("post-layout redraw request is published after the screen notifier")

    for source, label in ((shader_source, "shader"), (pipeline_source, "pipeline")):
        require_once(source, '#  include "GHOST_WebDisplayState.hh"',
                     f"{label} web recovery include")
        require_once(source, "static void request_webgpu_redraw_retry()",
                     f"{label} recovery adapter")
        require_once(source, "ghost_web::request_redraw_retry();",
                     f"{label} recovery publication")
    require_once(shader_source, "static void note_webgpu_draw_drop()",
                 "shader drop adapter")
    require_once(shader_source, "ghost_web::note_redraw_drop();",
                 "shader drop publication")

    module = method(shader_source, SHADER_MODULE_MARKER)
    compute = method(shader_source, COMPUTE_PIPELINE_MARKER)
    bindings = method(shader_source, BIND_GROUP_MARKER)
    explicit = method(shader_source, EXPLICIT_LAYOUT_MARKER)
    render = method(pipeline_source, RENDER_PIPELINE_MARKER)
    for body, label in (
        (module, "shader-module settlement"),
        (compute, "compute-pipeline settlement"),
        (explicit, "explicit-layout settlement"),
        (render, "render-pipeline settlement"),
    ):
        require_once(body, "if (published != nullptr)", label)
        require_once(body, "request_webgpu_redraw_retry();", label)
    require_once(bindings, "note_webgpu_draw_drop();", "incomplete bind-group drop")
    if bindings.index("note_webgpu_draw_drop();") > bindings.index("CLOG_WARN"):
        raise ValueError("incomplete bind-group retry is published after its diagnostic")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return source.replace(old, new, 1)


def mutate_method(source: str, marker: str, old: str, new: str) -> str:
    original = method(source, marker)
    changed = replace_once(original, old, new)
    return source.replace(original, changed, 1)


def mutate_window_update(source: str, old: str, new: str) -> str:
    start = source.find("case GHOST_kEventWindowUpdate:")
    end = source.find("break;", start)
    if start < 0 or end < 0:
        raise ValueError("missing WindowUpdate handler mutation input")
    original = source[start:end]
    changed = replace_once(original, old, new)
    return source[:start] + changed + source[end:]


def selfcheck(
    display_header: str,
    system_header: str,
    system_source: str,
    wm_window_source: str,
    shader_source: str,
    pipeline_source: str,
    context_source: str,
) -> None:
    validate(display_header, system_header, system_source, wm_window_source,
             shader_source, pipeline_source, context_source)
    mutations = (
        (replace_once(display_header, "FIRST_PIXEL_SETTLE_TICKS = 180u", "FIRST_PIXEL_SETTLE_TICKS = 0u"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "FIRST_PIXEL_SETTLE_INTERVAL = 12u", "FIRST_PIXEL_SETTLE_INTERVAL = 1u"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "inline std::atomic<uint64_t> redraw_retry_counter{0};", ""), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "inline std::atomic<uint64_t> input_redraw_retry_counter{0};", ""), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "inline std::atomic<uint64_t> redraw_episode_counter{0};", ""), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "inline std::atomic<uint64_t> redraw_drop_counter{0};", ""), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "inline std::atomic<uint64_t> present_suppressed_counter{0};", ""), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "inline std::atomic<uint64_t> present_replay_counter{0};", ""), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (mutate_method(display_header, "inline uint64_t request_present_replay()", "present_replay_counter.fetch_add", "present_suppressed_counter.fetch_add"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "return frame_episode == current_episode;", "return true;"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (mutate_method(display_header, "inline void redraw_trace_frame_begin(", "redraw_trace_state.frame_draw_count = 0;", ""), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (mutate_method(display_header, "inline bool redraw_present_trace_complete(", "trace.frame_offscreen_draw_count > 0u", "true"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (mutate_method(display_header, "inline bool redraw_present_trace_complete(", "trace.background.sequence > 0u", "true"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (mutate_method(display_header, "inline uint64_t request_redraw_episode()", "return generation;", "return 0;"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (mutate_method(display_header, "bool cancel_superseded(const uint64_t current_episode)", "scheduled_episode_ == current_episode", "scheduled_episode_ != current_episode"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (mutate_method(display_header, "inline bool cancel_superseded_redraw_present_barrier(", "redraw_present_barrier.cancel_superseded(current_episode)", "redraw_present_barrier.cancel(current_episode)"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "trace_snapshot.episode_generation == episode ? std::move(trace_snapshot) :", "false ? std::move(trace_snapshot) :"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "return phase_ == Phase::Ready ? scheduled_trace_snapshot_ : RedrawTraceSnapshot{};", "return {};"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "phase_ = Phase::Ready;", "phase_ = Phase::Scheduled;"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "completion(valid);", "completion(false);"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "episode_published ||", "false ||"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "input_published ||", "false ||"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "readiness_published ||", "false ||"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "draw_dropped ||", "false ||"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "episode_generation != episode_generation_seen", "false"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "episode_generation_seen = episode_generation;\n    heartbeat = 0;", "episode_generation_seen = episode_generation;"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "retry_generation != retry_generation_seen", "false"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "input_retry_generation != input_retry_generation_seen", "false"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (mutate_method(display_header, "inline void request_input_redraw_retry()", "input_redraw_retry_counter.fetch_add(1u, std::memory_order_release);", ""), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (mutate_method(display_header, "inline void request_input_redraw_retry()", "\n  redraw_retry_counter.fetch_add(1u, std::memory_order_release);", ""), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (mutate_method(display_header, "inline uint64_t input_redraw_retry_generation()", "return input_redraw_retry_counter.load(std::memory_order_acquire);", "return 0;"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "drop_generation != drop_generation_seen", "false"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (display_header, replace_once(system_header, "uint64_t redraw_retry_generation_seen_ = 0;", ""), system_source, wm_window_source, shader_source, pipeline_source),
        (display_header, replace_once(system_header, "uint64_t input_redraw_retry_generation_seen_ = 0;", ""), system_source, wm_window_source, shader_source, pipeline_source),
        (display_header, replace_once(system_header, "uint64_t redraw_episode_generation_seen_ = 0;", ""), system_source, wm_window_source, shader_source, pipeline_source),
        (display_header, replace_once(system_header, "uint64_t redraw_drop_generation_seen_ = 0;", ""), system_source, wm_window_source, shader_source, pipeline_source),
        (display_header, replace_once(system_header, "uint64_t redraw_present_barrier_completion_seen_ = 0;", ""), system_source, wm_window_source, shader_source, pipeline_source),
        (display_header, replace_once(system_header, "uint64_t present_replay_generation_seen_ = 0;", ""), system_source, wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "ghost_web::redraw_recovery_tick(", "ghost_web::redraw_recovery_disabled("), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "ghost_web::redraw_episode_generation()", "ghost_web::redraw_episode_generation_disabled()"), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "ghost_web::redraw_drop_generation()", "ghost_web::redraw_drop_generation_disabled()"), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "ghost_web::input_redraw_retry_generation()", "ghost_web::input_redraw_retry_generation_disabled()"), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "GHOST_kEventWindowUpdate", "GHOST_kEventWindowActivate"), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "ghost_web::filter_redraw_present_barrier_update(", "ghost_web::filter_redraw_present_barrier_update_disabled("), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "ghost_web::redraw_present_barrier_completion_generation()", "ghost_web::redraw_present_barrier_completion_generation_disabled()"), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "ghost_web::present_replay_generation()", "ghost_web::present_replay_generation_disabled()"), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "ghost_web::request_redraw_retry();", ""), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, CREATE_MARKER, "redraw_retry_generation_seen_ = ghost_web::redraw_retry_generation();", ""), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, CREATE_MARKER, "input_redraw_retry_generation_seen_ = ghost_web::input_redraw_retry_generation();", ""), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, CREATE_MARKER, "redraw_episode_generation_seen_ = ghost_web::redraw_episode_generation();", ""), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, CREATE_MARKER, "redraw_drop_generation_seen_ = ghost_web::redraw_drop_generation();", ""), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, CREATE_MARKER, "present_replay_generation_seen_ = ghost_web::present_replay_generation();", ""), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, system_source, mutate_window_update(wm_window_source, "WM_event_add_notifier_ex(wm, win, NC_SCREEN | NA_EDITED, nullptr);", ""), shader_source, pipeline_source),
        (display_header, system_header, system_source, mutate_window_update(wm_window_source, "win->runtime->web_full_redraw_after_window_update = true;", ""), shader_source, pipeline_source),
        (display_header, system_header, system_source, mutate_window_update(wm_window_source, "#ifdef __EMSCRIPTEN__\n      /* Screen relayout may rebuild", "#if 1\n      /* Screen relayout may rebuild"), shader_source, pipeline_source),
        (display_header, system_header, system_source, wm_window_source, mutate_method(shader_source, SHADER_MODULE_MARKER, "request_webgpu_redraw_retry();", ""), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, mutate_method(shader_source, COMPUTE_PIPELINE_MARKER, "request_webgpu_redraw_retry();", ""), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, mutate_method(shader_source, BIND_GROUP_MARKER, "note_webgpu_draw_drop();", ""), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, mutate_method(shader_source, EXPLICIT_LAYOUT_MARKER, "request_webgpu_redraw_retry();", ""), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, shader_source, mutate_method(pipeline_source, RENDER_PIPELINE_MARKER, "request_webgpu_redraw_retry();", "")),
        (display_header, system_header, system_source, wm_window_source, replace_once(shader_source, '#  include "GHOST_WebDisplayState.hh"', ""), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, replace_once(shader_source, "ghost_web::note_redraw_drop();", ""), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, shader_source, replace_once(pipeline_source, '#  include "GHOST_WebDisplayState.hh"', "")),
        (display_header, system_header, system_source, wm_window_source, mutate_method(shader_source, SHADER_MODULE_MARKER, "if (published != nullptr)", "if (true)"), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, mutate_method(shader_source, COMPUTE_PIPELINE_MARKER, "if (published != nullptr)", "if (true)"), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, mutate_method(shader_source, EXPLICIT_LAYOUT_MARKER, "if (published != nullptr)", "if (true)"), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, shader_source, mutate_method(pipeline_source, RENDER_PIPELINE_MARKER, "if (published != nullptr)", "if (true)")),
    )
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate(*mutation, context_source)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")

    context_mutations = (
        mutate_method(
            context_source,
            RESIZE_COMMIT_MARKER,
            "ghost_web::request_redraw_episode();",
            "",
        ),
        mutate_method(
            context_source,
            RESIZE_COMMIT_MARKER,
            "if (result == ghost_web::SurfaceResizeResult::Committed)",
            "if (result == ghost_web::SurfaceResizeResult::Superseded)",
        ),
        mutate_method(
            context_source,
            RESIZE_COMMIT_MARKER,
            "owner.backbuffer_redraw_episode_ = committed_redraw_episode;",
            "",
        ),
        mutate_method(
            context_source,
            RESIZE_COMMIT_MARKER,
            "ghost_web::cancel_superseded_redraw_present_barrier(\n"
            "                        committed_redraw_episode);",
            "",
        ),
        mutate_method(
            context_source,
            RESIZE_COMMIT_MARKER,
            "owner.backbuffer_redraw_episode_ = committed_redraw_episode;\n"
            "                    /* A prior episode's barrier may already be ready when this replacement\n"
            "                     * commits. Retire it only after the new backbuffer carries its episode;\n"
            "                     * otherwise GHOST can copy this untouched texture under the old barrier. */\n"
            "                    ghost_web::cancel_superseded_redraw_present_barrier(\n"
            "                        committed_redraw_episode);",
            "ghost_web::cancel_superseded_redraw_present_barrier(\n"
            "                        committed_redraw_episode);\n"
            "                    owner.backbuffer_redraw_episode_ = committed_redraw_episode;",
        ),
        mutate_method(
            context_source,
            SWAP_RELEASE_MARKER,
            "ghost_web::redraw_present_barrier_ready_trace_snapshot()",
            "ghost_web::redraw_trace_snapshot()",
        ),
        mutate_method(
            context_source,
            SWAP_RELEASE_MARKER,
            "if (!ghost_web::redraw_present_trace_complete(completed_frame, episode))",
            "if (false)",
        ),
        mutate_method(
            context_source,
            PRESENT_BACKBUFFER_MARKER,
            "ghost_web::note_present_suppressed();",
            "",
        ),
        mutate_method(
            context_source,
            PRESENT_BACKBUFFER_MARKER,
            "ghost_web::request_present_replay();",
            "",
        ),
        mutate_method(
            context_source,
            PRESENT_BACKBUFFER_MARKER,
            "const bool validate_transaction = !validation_scope_pending;",
            "const bool validate_transaction = true;",
        ),
        mutate_method(
            context_source,
            SWAP_RELEASE_MARKER,
            "ghost_web::complete_redraw_present_barrier(episode, false);",
            "",
        ),
        mutate_method(
            context_source,
            SWAP_RELEASE_MARKER,
            "if (ghost_web::redraw_trace_active(active_redraw_episode))",
            "if (false)",
        ),
    )
    for index, context_mutation in enumerate(context_mutations, start=len(mutations) + 1):
        try:
            validate(
                display_header,
                system_header,
                system_source,
                wm_window_source,
                shader_source,
                pipeline_source,
                context_mutation,
            )
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("display_header", type=Path)
    parser.add_argument("system_header", type=Path)
    parser.add_argument("system_source", type=Path)
    parser.add_argument("wm_window_source", type=Path)
    parser.add_argument("shader_source", type=Path)
    parser.add_argument("pipeline_source", type=Path)
    parser.add_argument("context_source", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    inputs = tuple(
        path.read_text(encoding="utf-8")
        for path in (
            args.display_header,
            args.system_header,
            args.system_source,
            args.wm_window_source,
            args.shader_source,
            args.pipeline_source,
            args.context_source,
        )
    )
    if args.selfcheck:
        selfcheck(*inputs)
    else:
        validate(*inputs)
    print("REDRAW_RECOVERY_CONTRACT PASS sources=7 mutations=70 bounded=180 readiness=4 input=full-tail drops=1 resize=requested,commit-fresh,frame-bound,present-barrier-trace-bound,incomplete-withheld,post-layout-redraw,view3d-frame-complete,commit-superseded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
