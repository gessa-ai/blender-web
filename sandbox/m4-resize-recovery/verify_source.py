#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail closed unless resize adoption and the synchronous window swap stay coherent."""

from __future__ import annotations

import argparse
from pathlib import Path


REQUIRED_BLOCK = """  /* The persistent texture wrapper changes its handle and dimensions in place on resize.
   * FrameBuffer::attachment_set() deliberately ignores an identical wrapper pointer, so the
   * default framebuffers' separately cached width_/height_ would otherwise keep the old surface
   * extent. That stale cache feeds viewport_scissor_plan() even though the render attachment is
   * already the new size, producing an out-of-range scissor and rejecting every draw. Mirror the
   * OpenGL window-context contract and publish the live backing extent on every activation. */
  if (back_left != nullptr) {
    back_left->size_set(w, h);
  }
  if (front_left != nullptr) {
    front_left->size_set(w, h);
  }
"""

REACTIVATION_BLOCK = """#if defined(WITH_METAL_BACKEND) || \\
    (defined(WITH_WEBGPU_BACKEND) && defined(__EMSCRIPTEN__))
  /* Reset drawable to ensure GPU context activation happens at least once per frame if only a
   * single context exists. This is required to ensure the default framebuffer is updated
   * to be the latest backbuffer. */
  wm_window_clear_drawable(wm);
#endif
"""

FORBIDDEN_DEFERRED_PRESENT_MARKERS = (
    "setPresentQueueEnqueue",
    "PresentQueueEnqueue",
    "QueuedPresent",
    "PresentCompletion",
    "present_queue_enqueue_",
)

FRAME_EPISODE_MEMBER = "uint64_t redraw_present_frame_episode_ = 0;"
BACKBUFFER_SNAPSHOT_TYPE = "struct BackbufferFrameSnapshot"
BACKBUFFER_SNAPSHOT_METHOD = "BackbufferFrameSnapshot getBackbufferFrameSnapshot() const"
BACKBUFFER_EPISODE_MEMBER = "uint64_t backbuffer_redraw_episode_ = 0;"
DISPLAY_STATE_INCLUDE = '#include "GHOST_WebDisplayState.hh"'


def method(source: str, marker: str) -> str:
    start = source.find(marker)
    if start < 0:
        return ""
    opening = source.find("{", start)
    if opening < 0:
        return ""
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    return ""


def validate(
    context_source: str,
    context_header: str,
    wm_source: str,
    wm_window_source: str,
    ghost_source: str,
    ghost_header: str,
) -> list[str]:
    errors: list[str] = []
    adopt = "  back->adopt_external(backbuffer, fmt, w, h);"
    if context_source.count(adopt) != 1:
        errors.append("persistent backbuffer adoption is not unique")
    if context_source.count(REQUIRED_BLOCK) != 1:
        errors.append("default framebuffer extent synchronization block differs")
    adopt_at = context_source.find(adopt)
    refresh_at = context_source.find(REQUIRED_BLOCK)
    endif_at = context_source.find("#endif", refresh_at)
    if not (adopt_at >= 0 and refresh_at > adopt_at and endif_at > refresh_at):
        errors.append("extent synchronization is not ordered after adoption inside the web guard")

    # The frame-episode guard is meaningful only when the window context has already adopted the
    # current persistent backbuffer. Bind WGPUContext activation itself: wm_draw_update() forces
    # one activation per browser frame below, and GPU_context_begin_frame() captures the episode
    # only after that activation has refreshed the wrapper and both default-framebuffer extents.
    activation = method(context_source, "void WGPUContext::activate()")
    activation_tokens = (
        "is_active_ = true;",
        "sync_backbuffer();",
        "immActivate();",
    )
    for token in activation_tokens:
        if activation.count(token) != 1:
            errors.append(f"window context activation differs: {token}")
    if activation and all(token in activation for token in activation_tokens):
        positions = tuple(activation.index(token) for token in activation_tokens)
        if positions != tuple(sorted(positions)):
            errors.append("persistent backbuffer adoption is not ordered inside activation")

    # One activation must adopt the handle, extent, format, and redraw episode from one GHOST
    # lifetime-gated snapshot. Separate getters can be interleaved by an AllowSpontaneous resize
    # completion, producing an old texture tagged with the new episode and admitting an empty
    # replacement backbuffer at the completed-frame barrier.
    sync = method(context_source, "void WGPUContext::sync_backbuffer()")
    sync_tokens = (
        "wgpu_ghost->getBackbufferFrameSnapshot()",
        "backbuffer_snapshot.texture",
        "backbuffer_snapshot.format",
        "backbuffer_snapshot.width",
        "backbuffer_snapshot.height",
        "redraw_present_frame_episode_ = backbuffer_snapshot.redraw_episode;",
    )
    for token in sync_tokens:
        if sync.count(token) != 1:
            errors.append(f"atomic backbuffer frame snapshot differs: {token}")
    if "wgpu_ghost->getBackbufferTexture()" in sync:
        errors.append("frame adoption still reads the backbuffer through a split getter")
    adopt_token = "back->adopt_external(backbuffer, fmt, w, h);"
    if sync and adopt_token in sync and all(token in sync for token in sync_tokens):
        snapshot_at = sync.index(sync_tokens[0])
        adopt_at = sync.index(adopt_token)
        episode_at = sync.index(sync_tokens[-1])
        if not snapshot_at < adopt_at < episode_at:
            errors.append("backbuffer snapshot is not bound to the adopted frame")

    if wm_source.count(REACTIVATION_BLOCK) != 1:
        errors.append("browser WebGPU does not reactivate the window context before each draw")
    update_at = wm_source.find("void wm_draw_update(bContext *C)")
    reactivate_at = wm_source.find(REACTIVATION_BLOCK)
    window_loop_at = wm_source.find("  for (wmWindow &win : wm->windows)", update_at)
    if not (update_at >= 0 and update_at < reactivate_at < window_loop_at):
        errors.append("window-context reactivation is not ordered before the draw loop")

    # The barrier's ready transition requests one synthetic WindowUpdate. Carry a one-shot request
    # across notifier-driven screen relayout, then tag the rebuilt areas immediately before frame
    # encoding. Tagging the pre-layout regions can be consumed while only retained chrome is
    # recomposited, producing a validation-clean frame with no VIEW_3D content.
    ghost_event = method(wm_window_source, "static bool ghost_event_proc(")
    update_case_at = ghost_event.find("case GHOST_kEventWindowUpdate:")
    update_decor_case_at = ghost_event.find(
        "case GHOST_kEventWindowUpdateDecor:", update_case_at
    )
    window_update = (
        ghost_event[update_case_at:update_decor_case_at]
        if update_case_at >= 0 and update_decor_case_at > update_case_at
        else ""
    )
    window_update_tokens = (
        "wm_window_make_drawable(wm, win);",
        "#ifdef __EMSCRIPTEN__",
        "win->runtime->web_full_redraw_after_window_update = true;",
        "WM_event_add_notifier_ex(wm, win, NC_SCREEN | NA_EDITED, nullptr);",
        "#endif",
        "WM_event_add_notifier_ex(wm, win, NC_WINDOW, nullptr);",
    )
    if not window_update:
        errors.append("GHOST window-update event boundary differs")
    for token in window_update_tokens:
        if window_update.count(token) != 1:
            errors.append(f"web full-screen WindowUpdate invalidation differs: {token}")
    if window_update and all(token in window_update for token in window_update_tokens):
        positions = tuple(window_update.index(token) for token in window_update_tokens)
        if positions != tuple(sorted(positions)):
            errors.append("web full-screen invalidation is outside the drawable WindowUpdate")

    update_test = method(wm_source, "static bool wm_draw_update_test_window(")
    update_test_trigger = "do_draw = win->runtime->web_full_redraw_after_window_update;"
    if update_test.count(update_test_trigger) != 1:
        errors.append("post-layout browser redraw does not force a window draw")

    draw_update = method(wm_source, "void wm_draw_update(bContext *C)")
    post_layout_tokens = (
        "ED_screen_ensure_updated(C, wm, &win);",
        "if (win.runtime->web_full_redraw_after_window_update)",
        "win.runtime->web_full_redraw_after_window_update = false;",
        "ED_screen_areas_iter (&win, updated_screen, area)",
        "ED_area_tag_redraw(area);",
        "wm_draw_window(C, &win);",
    )
    for token in post_layout_tokens:
        if draw_update.count(token) != 1:
            errors.append(f"post-layout browser area redraw differs: {token}")
    if draw_update and all(token in draw_update for token in post_layout_tokens):
        positions = tuple(draw_update.index(token) for token in post_layout_tokens)
        if positions != tuple(sorted(positions)):
            errors.append("browser area redraw is not ordered after relayout and before encoding")

    # WGPUContext::end_frame() is the queue-tail hook used by the resize barrier. Blender's
    # similarly named GPU_render_end() is backend-wide and runs later; it does not call the
    # context hook. Bind the real window call graph so the barrier cannot drift before region
    # encoding or after GHOST has already copied the persistent backbuffer to the surface.
    draw_window = method(wm_source, "static void wm_draw_window(bContext *C, wmWindow *win)")
    context_begin = (
        "GPU_context_begin_frame(static_cast<GPUContext *>(win->runtime->gpuctx));"
    )
    context_end = (
        "GPU_context_end_frame(static_cast<GPUContext *>(win->runtime->gpuctx));"
    )
    for token in (context_begin, context_end):
        if draw_window.count(token) != 1:
            errors.append(f"window context frame boundary differs: {token}")
    begin_at = draw_window.find(context_begin)
    first_region_draw_at = draw_window.find("wm_draw_window_offscreen(C, win, stereo);")
    last_composite_at = draw_window.rfind("wm_draw_window_onscreen(C, win")
    draw_clear_at = draw_window.find("screen->do_draw = false;")
    end_at = draw_window.find(context_end)
    if not (
        begin_at >= 0
        and begin_at < first_region_draw_at <= last_composite_at < draw_clear_at < end_at
    ):
        errors.append("context end-frame is not after complete window encoding")

    draw_update = method(wm_source, "void wm_draw_update(bContext *C)")
    window_sequence = (
        "wm_window_make_drawable(wm, &win);",
        "wm_window_swap_buffer_acquire(&win);",
        "wm_draw_window(C, &win);",
        "wm_draw_update_clear_window(C, &win);",
        "wm_window_swap_buffer_release(&win);",
    )
    for index, token in enumerate(window_sequence):
        # A second make-drawable restores the window context after optional offscreen surfaces.
        # The first occurrence must still precede this window's acquire/draw/release sequence.
        expected = draw_update.count(token) >= 1 if index == 0 else draw_update.count(token) == 1
        if not expected:
            errors.append(f"window draw/swap sequence differs: {token}")
    if all(token in draw_update for token in window_sequence):
        positions = tuple(draw_update.index(token) for token in window_sequence)
        if positions != tuple(sorted(positions)):
            errors.append("context end-frame can no longer precede synchronous window swap")

    if context_header.count(FRAME_EPISODE_MEMBER) != 1:
        errors.append("window frame does not retain its resize episode")

    if ghost_header.count(DISPLAY_STATE_INCLUDE) != 1:
        errors.append("GHOST backbuffer snapshot lacks its display-state declaration")
    if ghost_header.count(BACKBUFFER_SNAPSHOT_TYPE) != 1:
        errors.append("GHOST does not expose one coherent backbuffer frame snapshot type")
    snapshot = method(ghost_header, BACKBUFFER_SNAPSHOT_METHOD)
    for token in (
        "const std::shared_ptr<CallbackLifetime> lifetime = callback_lifetime_;",
        "auto owner_execution = lifetime->enter();",
        "device_state_allows_callback_work(device_state_)",
        "return {backbuffer_,",
        "surface_format_",
        "backbuffer_w_",
        "backbuffer_h_",
    ):
        if snapshot.count(token) != 1:
            errors.append(f"coherent GHOST backbuffer snapshot differs: {token}")
    if snapshot.count("backbuffer_redraw_episode_") != 1:
        errors.append("coherent GHOST snapshot does not return its adopted episode")
    if "redraw_trace_frame_begin" in snapshot:
        errors.append("GPU context reactivation still erases an in-progress window-frame trace")
    if ghost_header.count(BACKBUFFER_EPISODE_MEMBER) != 1:
        errors.append("GHOST backbuffer does not retain its committed redraw episode")

    ensure = method(ghost_source, "void GHOST_ContextWGPUWeb::ensureBackbuffer()")
    commit_tokens = (
        "const uint64_t committed_redraw_episode =\n"
        "                        ghost_web::request_redraw_episode();",
        "owner.backbuffer_redraw_episode_ = committed_redraw_episode;",
    )
    for token in commit_tokens:
        if ensure.count(token) != 1:
            errors.append(f"backbuffer commit episode publication differs: {token}")
    if ensure and all(token in ensure for token in commit_tokens):
        if ensure.index(commit_tokens[0]) > ensure.index(commit_tokens[1]):
            errors.append("backbuffer episode is captured before the redraw episode publishes")

    begin_frame = method(context_source, "void WGPUContext::begin_frame()")
    begin_frame_tokens = (
        "ghost_web::redraw_trace_frame_begin(redraw_present_frame_episode_);",
        "queue_scheduler_.begin_epoch();",
    )
    for token in begin_frame_tokens:
        if begin_frame.count(token) != 1:
            errors.append(f"resize frame-start binding differs: {token}")
    if "redraw_present_frame_episode_ = ghost_web::redraw_episode_generation();" in begin_frame:
        errors.append("frame start resamples the episode separately from backbuffer adoption")
    if begin_frame and all(token in begin_frame for token in begin_frame_tokens):
        if begin_frame.index(begin_frame_tokens[0]) > begin_frame.index(begin_frame_tokens[1]):
            errors.append("frame trace starts after the backend queue epoch")

    end_frame = method(context_source, "void WGPUContext::end_frame()")
    end_frame_tokens = (
        "ghost_web::redraw_episode_generation()",
        "const ghost_web::RedrawTraceSnapshot completed_frame =\n"
        "      ghost_web::redraw_trace_snapshot();",
        "const bool viewport_content_pending =",
        "const bool frame_complete =",
        "ghost_web::viewport_content_trace_complete(completed_frame, episode)",
        "ghost_web::redraw_present_trace_complete(completed_frame, episode)",
        "ghost_window_ != nullptr",
        "ghost_web::redraw_present_frame_matches_episode(",
        "redraw_present_frame_episode_, episode",
        "ghost_web::redraw_trace_active(episode)",
        "      frame_complete &&",
        "ghost_web::schedule_redraw_present_barrier(\n"
        "          episode, completed_frame)",
        "queue_scheduler_.enqueue(",
        "ghost_web::arrive_redraw_present_barrier(episode, std::move(done));",
        "ghost_web::cancel_redraw_present_barrier(episode);",
    )
    for token in end_frame_tokens:
        if end_frame.count(token) != 1:
            errors.append(f"resize present queue barrier differs: {token}")
    if end_frame and all(token in end_frame for token in end_frame_tokens):
        positions = tuple(end_frame.index(token) for token in end_frame_tokens[1:13])
        if positions != tuple(sorted(positions)):
            errors.append("resize present barrier can capture an incomplete window frame tail")

    destructor = method(context_source, "WGPUContext::~WGPUContext()")
    for token in (
        "ghost_web::redraw_present_barrier_is_scheduled()",
        "ghost_web::cancel_redraw_present_barrier(",
        "ghost_web::redraw_present_barrier_scheduled_episode()",
    ):
        if destructor.count(token) != 1:
            errors.append(f"resize present barrier teardown differs: {token}")

    for marker in FORBIDDEN_DEFERRED_PRESENT_MARKERS:
        if marker in context_source or marker in ghost_source or marker in ghost_header:
            errors.append(f"deferred window-present seam remains reachable: {marker}")
    if ghost_header.count("bool presentBackbuffer();") != 1:
        errors.append("GHOST presentBackbuffer is not the synchronous no-callback interface")

    swap_start = ghost_source.find("GHOST_TSuccess GHOST_ContextWGPUWeb::swapBufferRelease()")
    swap_end = ghost_source.find(
        "GHOST_TSuccess GHOST_ContextWGPUWeb::activateDrawingContext()", swap_start
    )
    swap_release = ghost_source[swap_start:swap_end]
    immediate = "return presentBackbuffer() ? GHOST_kSuccess : GHOST_kFailure;"
    if swap_release.count(immediate) != 1:
        errors.append("GHOST swap does not synchronously execute exactly one present")
    for token in (
        "if (ghost_web::redraw_present_barrier_is_scheduled())",
        "if (!ghost_web::redraw_present_barrier_is_ready())",
        "const uint64_t episode = ghost_web::redraw_present_barrier_ready_episode();",
        "ghost_web::redraw_present_barrier_ready_trace_snapshot()",
        "ghost_web::redraw_present_trace_complete(completed_frame, episode)",
        "ghost_web::complete_redraw_present_barrier(episode, false);",
        "const bool presented = presentBackbuffer();",
        "ghost_web::complete_redraw_present_barrier(episode, presented);",
        "return presented ? GHOST_kSuccess : GHOST_kFailure;",
        "const uint64_t active_redraw_episode = ghost_web::redraw_episode_generation();",
        "if (ghost_web::redraw_trace_active(active_redraw_episode))",
    ):
        if swap_release.count(token) != 1:
            errors.append(f"resize present barrier differs: {token}")
    device_check = swap_release.find("if (!deviceIsUsable())")
    device_only = swap_release.find(
        "if (mode_ == ghost_web::DrawingContextMode::DeviceOnly)"
    )
    barrier_scheduled = swap_release.find(
        "if (ghost_web::redraw_present_barrier_is_scheduled())"
    )
    barrier_ready = swap_release.find(
        "if (!ghost_web::redraw_present_barrier_is_ready())"
    )
    barrier_trace = swap_release.find(
        "ghost_web::redraw_present_barrier_ready_trace_snapshot()"
    )
    barrier_trace_complete = swap_release.find(
        "ghost_web::redraw_present_trace_complete(completed_frame, episode)"
    )
    barrier_reject = swap_release.find(
        "ghost_web::complete_redraw_present_barrier(episode, false);"
    )
    barrier_retry_return = swap_release.find("return GHOST_kSuccess;", barrier_reject)
    barrier_present = swap_release.find("const bool presented = presentBackbuffer();")
    barrier_complete = swap_release.find(
        "ghost_web::complete_redraw_present_barrier(episode, presented);"
    )
    active_episode = swap_release.find(
        "const uint64_t active_redraw_episode = ghost_web::redraw_episode_generation();"
    )
    incomplete_withhold = swap_release.find(
        "if (ghost_web::redraw_trace_active(active_redraw_episode))"
    )
    withhold_return = swap_release.find("return GHOST_kSuccess;", incomplete_withhold)
    immediate_at = swap_release.find(immediate)
    if not (
        device_check >= 0
        and device_check < device_only < barrier_scheduled < barrier_ready
        < barrier_trace < barrier_trace_complete < barrier_reject < barrier_retry_return
        < barrier_present < barrier_complete < active_episode < incomplete_withhold
        < withhold_return < immediate_at
    ):
        errors.append("GHOST synchronous present is outside the validated swap boundary")
    if ghost_source.count("bool GHOST_ContextWGPUWeb::presentBackbuffer()") != 1:
        errors.append("GHOST synchronous present implementation differs")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("upstream/source/blender/gpu/webgpu/wgpu_context.cc"),
    )
    parser.add_argument(
        "--wm-source",
        type=Path,
        default=Path("upstream/source/blender/windowmanager/intern/wm_draw.cc"),
    )
    parser.add_argument(
        "--wm-window-source",
        type=Path,
        default=Path("upstream/source/blender/windowmanager/intern/wm_window.cc"),
    )
    parser.add_argument(
        "--header",
        type=Path,
        default=Path("upstream/source/blender/gpu/webgpu/wgpu_context.hh"),
    )
    parser.add_argument(
        "--ghost-source",
        type=Path,
        default=Path("platform_web/ghost/GHOST_ContextWGPUWeb.cc"),
    )
    parser.add_argument(
        "--ghost-header",
        type=Path,
        default=Path("platform_web/ghost/GHOST_ContextWGPUWeb.hh"),
    )
    args = parser.parse_args()
    context_source = args.source.read_text(encoding="utf-8")
    context_header = args.header.read_text(encoding="utf-8")
    wm_source = args.wm_source.read_text(encoding="utf-8")
    wm_window_source = args.wm_window_source.read_text(encoding="utf-8")
    ghost_source = args.ghost_source.read_text(encoding="utf-8")
    ghost_header = args.ghost_header.read_text(encoding="utf-8")
    errors = validate(
        context_source,
        context_header,
        wm_source,
        wm_window_source,
        ghost_source,
        ghost_header,
    )
    if errors:
        for error in errors:
            print(f"BW_M4_RESIZE_SOURCE_FAIL {error}")
        return 1

    context_mutations = {
        "back_extent": context_source.replace(
            "back_left->size_set(w, h);", "back_left->size_set(w, w);", 1
        ),
        "front_extent": context_source.replace(
            "front_left->size_set(w, h);", "front_left->size_set(h, h);", 1
        ),
        "adoption": context_source.replace(
            "back->adopt_external(backbuffer, fmt, w, h);",
            "back->adopt_external(backbuffer, fmt, w, w);",
            1,
        ),
        "activation_sync_call": context_source.replace("  sync_backbuffer();", "", 1),
        "activation_sync_order": context_source.replace(
            "  sync_backbuffer();\n  immActivate();",
            "  immActivate();\n  sync_backbuffer();",
            1,
        ),
        "snapshot_call": context_source.replace(
            "wgpu_ghost->getBackbufferFrameSnapshot()",
            "WGPUGhostContext::BackbufferFrameSnapshot()",
            1,
        ),
        "snapshot_episode": context_source.replace(
            "redraw_present_frame_episode_ = backbuffer_snapshot.redraw_episode;",
            "redraw_present_frame_episode_ = ghost_web::redraw_episode_generation();",
            1,
        ),
        "frame_trace_reset": context_source.replace(
            "  ghost_web::redraw_trace_frame_begin(redraw_present_frame_episode_);",
            "",
            1,
        ),
        "deferred_present_registration": context_source.replace(
            "  instance_ = wgpu_ghost->getInstance();",
            "  wgpu_ghost->setPresentQueueEnqueue([](WGPUGhostContext::QueuedPresent) {});\n"
            "  instance_ = wgpu_ghost->getInstance();",
            1,
        ),
        "barrier_schedule": context_source.replace(
            "ghost_web::schedule_redraw_present_barrier(\n"
            "          episode, completed_frame)",
            "false",
            1,
        ),
        "barrier_arrival": context_source.replace(
            "ghost_web::arrive_redraw_present_barrier(episode, std::move(done));",
            "done(true);",
            1,
        ),
        "barrier_cancel": context_source.replace(
            "ghost_web::cancel_redraw_present_barrier(episode);",
            "",
            1,
        ),
        "barrier_incomplete_schedule": context_source.replace(
            "ghost_web::redraw_present_trace_complete(completed_frame, episode)",
            "true",
            1,
        ),
        "frame_episode_match": context_source.replace(
            "redraw_present_frame_episode_, episode",
            "episode, episode",
            1,
        ),
        "window_context_guard": context_source.replace(
            "ghost_window_ != nullptr",
            "true",
            1,
        ),
    }
    context_header_mutations = {
        "frame_episode_member": context_header.replace(FRAME_EPISODE_MEMBER, "", 1),
    }
    wm_mutations = {
        "webgpu_reactivation": wm_source.replace(
            "#if defined(WITH_METAL_BACKEND) || \\\n    (defined(WITH_WEBGPU_BACKEND) && defined(__EMSCRIPTEN__))",
            "#ifdef WITH_METAL_BACKEND",
            1,
        ),
        "browser_scope": wm_source.replace(" && defined(__EMSCRIPTEN__)", "", 1),
        "reactivation_call": wm_source.replace("  wm_window_clear_drawable(wm);", "", 1),
        "window_activation_call": wm_source.replace(
            "      wm_window_make_drawable(wm, &win);", "", 1
        ),
        "window_context_end_missing": wm_source.replace(
            "  GPU_context_end_frame(static_cast<GPUContext *>(win->runtime->gpuctx));",
            "",
            1,
        ),
        "window_context_end_before_clear": wm_source.replace(
            "  screen->do_draw = false;\n\n"
            "  GPU_context_end_frame(static_cast<GPUContext *>(win->runtime->gpuctx));",
            "  GPU_context_end_frame(static_cast<GPUContext *>(win->runtime->gpuctx));\n\n"
            "  screen->do_draw = false;",
            1,
        ),
        "window_swap_before_draw": wm_source.replace(
            "      wm_draw_window(C, &win);\n"
            "      wm_draw_update_clear_window(C, &win);\n\n"
            "      wm_window_swap_buffer_release(&win);",
            "      wm_window_swap_buffer_release(&win);\n\n"
            "      wm_draw_window(C, &win);\n"
            "      wm_draw_update_clear_window(C, &win);",
            1,
        ),
        "web_window_redraw_trigger": wm_source.replace(
            "  do_draw = win->runtime->web_full_redraw_after_window_update;",
            "",
            1,
        ),
        "web_window_post_layout_area_redraw": wm_source.replace(
            "          ED_area_tag_redraw(area);",
            "",
            1,
        ),
        "web_window_post_layout_order": wm_source.replace(
            "      ED_screen_ensure_updated(C, wm, &win);",
            "      ED_screen_ensure_updated_disabled(C, wm, &win);",
            1,
        ),
    }
    wm_window_mutations = {
        "web_window_redraw_request": wm_window_source.replace(
            "      win->runtime->web_full_redraw_after_window_update = true;",
            "",
            1,
        ),
        "web_window_screen_invalidation": wm_window_source.replace(
            "      WM_event_add_notifier_ex(wm, win, NC_SCREEN | NA_EDITED, nullptr);",
            "",
            1,
        ),
        "web_window_screen_scope": wm_window_source.replace(
            "#ifdef __EMSCRIPTEN__\n"
            "      /* Screen relayout may rebuild region state. Carry this request",
            "#ifdef __linux__\n"
            "      /* Screen relayout may rebuild region state. Carry this request",
            1,
        ),
        "web_window_screen_order": wm_window_source.replace(
            "      WM_event_add_notifier_ex(wm, win, NC_SCREEN | NA_EDITED, nullptr);\n"
            "#endif\n"
            "      WM_event_add_notifier_ex(wm, win, NC_WINDOW, nullptr);",
            "      WM_event_add_notifier_ex(wm, win, NC_WINDOW, nullptr);\n"
            "#endif\n"
            "      WM_event_add_notifier_ex(wm, win, NC_SCREEN | NA_EDITED, nullptr);",
            1,
        ),
    }
    ghost_source_mutations = {
        "present_bypass": ghost_source.replace(
            "return presentBackbuffer() ? GHOST_kSuccess : GHOST_kFailure;",
            "return GHOST_kSuccess;",
            1,
        ),
        "deferred_present_signature": ghost_source.replace(
            "bool GHOST_ContextWGPUWeb::presentBackbuffer()",
            "bool GHOST_ContextWGPUWeb::presentBackbuffer(PresentCompletion on_complete)",
            1,
        ),
        "barrier_bypass": ghost_source.replace(
            "if (ghost_web::redraw_present_barrier_is_scheduled())",
            "if (false)",
            1,
        ),
        "barrier_readiness": ghost_source.replace(
            "if (!ghost_web::redraw_present_barrier_is_ready())",
            "if (ghost_web::redraw_present_barrier_is_ready())",
            1,
        ),
        "barrier_frame_trace": ghost_source.replace(
            "ghost_web::redraw_present_barrier_ready_trace_snapshot()",
            "ghost_web::redraw_trace_snapshot()",
            1,
        ),
        "barrier_frame_admission": ghost_source.replace(
            "if (!ghost_web::redraw_present_trace_complete(completed_frame, episode))",
            "if (false)",
            1,
        ),
        "barrier_frame_rejection": ghost_source.replace(
            "ghost_web::complete_redraw_present_barrier(episode, false);",
            "",
            1,
        ),
        "unbarriered_incomplete_present": ghost_source.replace(
            "if (ghost_web::redraw_trace_active(active_redraw_episode))",
            "if (false)",
            1,
        ),
        "barrier_completion": ghost_source.replace(
            "ghost_web::complete_redraw_present_barrier(episode, presented);",
            "",
            1,
        ),
    }
    ghost_header_mutations = {
        "display_state_include": ghost_header.replace(DISPLAY_STATE_INCLUDE, "", 1),
        "backbuffer_snapshot_type": ghost_header.replace(
            BACKBUFFER_SNAPSHOT_TYPE, "struct DisabledBackbufferFrameSnapshot", 1
        ),
        "backbuffer_snapshot_method": ghost_header.replace(
            BACKBUFFER_SNAPSHOT_METHOD,
            "BackbufferFrameSnapshot disabledBackbufferFrameSnapshot() const",
            1,
        ),
        "backbuffer_snapshot_episode": ghost_header.replace(
            "backbuffer_h_,\n            backbuffer_redraw_episode_};",
            "backbuffer_h_,\n            uint64_t(0)};",
            1,
        ),
        "backbuffer_episode_member": ghost_header.replace(BACKBUFFER_EPISODE_MEMBER, "", 1),
        "deferred_present_alias": ghost_header.replace(
            "  bool presentBackbuffer();",
            "  using PresentCompletion = std::function<void(bool success)>;\n"
            "  bool presentBackbuffer();",
            1,
        ),
        "present_signature": ghost_header.replace("bool presentBackbuffer();", "", 1),
    }
    ghost_source_mutations["backbuffer_commit_episode"] = ghost_source.replace(
        "owner.backbuffer_redraw_episode_ = committed_redraw_episode;",
        "",
        1,
    )
    escaped = [
        name
        for name, mutant in context_mutations.items()
        if not validate(
            mutant, context_header, wm_source, wm_window_source, ghost_source, ghost_header
        )
    ]
    escaped.extend(
        name
        for name, mutant in context_header_mutations.items()
        if not validate(
            context_source, mutant, wm_source, wm_window_source, ghost_source, ghost_header
        )
    )
    escaped.extend(
        name
        for name, mutant in wm_mutations.items()
        if not validate(
            context_source, context_header, mutant, wm_window_source, ghost_source, ghost_header
        )
    )
    escaped.extend(
        name
        for name, mutant in wm_window_mutations.items()
        if not validate(
            context_source, context_header, wm_source, mutant, ghost_source, ghost_header
        )
    )
    escaped.extend(
        name
        for name, mutant in ghost_source_mutations.items()
        if not validate(
            context_source, context_header, wm_source, wm_window_source, mutant, ghost_header
        )
    )
    escaped.extend(
        name
        for name, mutant in ghost_header_mutations.items()
        if not validate(
            context_source, context_header, wm_source, wm_window_source, ghost_source, mutant
        )
    )
    if escaped:
        print("BW_M4_RESIZE_SOURCE_FAIL mutation escaped: " + ",".join(escaped))
        return 1

    print("BW_M4_RESIZE_SOURCE_PASS sources=6 checks=80 mutations=47")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
