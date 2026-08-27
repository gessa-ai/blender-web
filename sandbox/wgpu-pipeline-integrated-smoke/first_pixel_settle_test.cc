/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm behavior contract for per-window first-pixel settling. */

#include <cstdint>
#include <cstdio>
#include <limits>

#ifndef BW_GHOST_DISPLAY_STATE_HEADER
#  error "BW_GHOST_DISPLAY_STATE_HEADER must name the shipping web display-state header"
#endif

#include BW_GHOST_DISPLAY_STATE_HEADER

namespace {

int checks = 0;

bool require(const bool condition, const char *message)
{
  checks++;
  if (!condition) {
    std::fprintf(stderr, "FAIL %s\n", message);
    return false;
  }
  return true;
}

}  // namespace

int main()
{
  uint64_t retry_generation_seen = ghost_web::redraw_retry_generation();
  uint64_t episode_generation_seen = ghost_web::redraw_episode_generation();
  uint64_t drop_generation_seen = ghost_web::redraw_drop_generation();
  uint32_t heartbeat = 0;
  const auto recovery_tick = [&]() {
    return ghost_web::redraw_recovery_tick(ghost_web::redraw_retry_generation(),
                                           retry_generation_seen,
                                           ghost_web::redraw_episode_generation(),
                                           episode_generation_seen,
                                           ghost_web::redraw_drop_generation(),
                                           drop_generation_seen,
                                           heartbeat);
  };
  if (!require(recovery_tick() &&
                   heartbeat == 1,
               "initial epoch requests an update"))
  {
    return 1;
  }

  bool early_request = false;
  for (uint32_t tick = 1; tick < ghost_web::FIRST_PIXEL_SETTLE_INTERVAL; tick++) {
    early_request |= recovery_tick();
  }
  if (!require(!early_request && heartbeat == ghost_web::FIRST_PIXEL_SETTLE_INTERVAL,
               "settle interval is quiet between requests") ||
      !require(recovery_tick() &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_INTERVAL + 1u,
               "settle interval requests its next update"))
  {
    return 1;
  }

  int periodic_requests = 2;
  while (heartbeat < ghost_web::FIRST_PIXEL_SETTLE_TICKS) {
    periodic_requests += recovery_tick() ? 1 : 0;
  }
  if (!require(periodic_requests == 15,
               "boot recovery ignores presentation count and reaches every bounded interval") ||
      !require(!recovery_tick() &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_TICKS,
               "completed recovery remains terminal"))
  {
    return 1;
  }

  const uint64_t before_drop = ghost_web::redraw_drop_generation();
  ghost_web::note_redraw_drop();
  const uint64_t after_drop = ghost_web::redraw_drop_generation();
  if (!require(after_drop == before_drop + 1u,
               "an incomplete draw publishes a monotonic drop generation") ||
      !require(!recovery_tick() && drop_generation_seen == after_drop &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_TICKS,
               "a late drop is acknowledged without rearming a completed burst"))
  {
    return 1;
  }

  const uint64_t before_request = ghost_web::redraw_retry_generation();
  ghost_web::request_redraw_retry();
  const uint64_t after_request = ghost_web::redraw_retry_generation();
  if (!require(after_request == before_request + 1u,
               "WebGPU readiness publishes a monotonic retry generation") ||
      !require(recovery_tick() &&
                   retry_generation_seen == after_request && heartbeat == 1,
               "late readiness re-arms a terminal recovery burst") ||
      !require(ghost_web::redraw_trace_active(ghost_web::redraw_episode_generation()),
               "late readiness reopens semantic tracing before VIEW_3D readiness"))
  {
    return 1;
  }

  heartbeat = 50;
  retry_generation_seen = after_request;
  drop_generation_seen = after_drop;
  ghost_web::note_redraw_drop();
  const uint64_t active_drop = ghost_web::redraw_drop_generation();
  if (!require(recovery_tick() && drop_generation_seen == active_drop && heartbeat == 51,
               "an incomplete draw requests an immediate retry inside the active burst"))
  {
    return 1;
  }

  ghost_web::request_redraw_retry();
  const uint64_t active_request = ghost_web::redraw_retry_generation();
  if (!require(recovery_tick() && retry_generation_seen == active_request && heartbeat == 52,
               "readiness during an active burst requests immediately without resetting budget"))
  {
    return 1;
  }

  /* A resize may arrive on the final tick of an older readiness episode while its replacement
   * surface/backbuffer is still validating. The resize request can spend that final update before
   * the new extent is drawable; the later coherent commit must therefore start its own budget. */
  heartbeat = ghost_web::FIRST_PIXEL_SETTLE_TICKS - 1u;
  retry_generation_seen = active_request;
  ghost_web::request_redraw_retry();
  const uint64_t resize_request = ghost_web::redraw_retry_generation();
  if (!require(recovery_tick() && retry_generation_seen == resize_request &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_TICKS,
               "resize request can consume the final tick of an older recovery episode"))
  {
    return 1;
  }
  const uint64_t before_episode = ghost_web::redraw_episode_generation();
  ghost_web::request_redraw_episode();
  const uint64_t after_episode = ghost_web::redraw_episode_generation();
  if (!require(after_episode == before_episode + 1u,
               "a drawable extent commit publishes a monotonic episode generation") ||
      !require(recovery_tick() && episode_generation_seen == after_episode && heartbeat == 1,
               "a drawable extent commit starts a fresh bounded recovery episode"))
  {
    return 1;
  }

  /* Browser command validation can leave one complete frame behind the queue while GHOST reaches
   * swapBufferRelease(). A resize-only barrier must suppress those intermediate presents, admit
   * exactly one WindowUpdate when the queued frame is ready, and release the queue only after the
   * synchronous GHOST present has been submitted. */
  ghost_web::RedrawPresentBarrier barrier;
  ghost_web::RedrawTraceSnapshot completed_frame_trace;
  completed_frame_trace.episode_generation = after_episode;
  completed_frame_trace.draw_count = 7;
  completed_frame_trace.window_draw_count = 3;
  ghost_web::RedrawTraceSnapshot later_frame_trace = completed_frame_trace;
  later_frame_trace.draw_count = 99;
  bool first_completion_called = false;
  bool first_completion_valid = false;
  if (!require(barrier.schedule(after_episode, completed_frame_trace),
               "a fresh resize episode schedules one present barrier") ||
      !require(!barrier.schedule(after_episode, later_frame_trace),
               "one resize episode cannot schedule duplicate barriers") ||
      !require(barrier.scheduled_episode() == after_episode &&
                   barrier.ready_episode() == 0,
               "a scheduled barrier blocks presentation before queue arrival") ||
      !require(!barrier.filter_update(after_episode, true),
               "synthetic redraws pause while the completed frame is pending") ||
      !require(barrier.arrive(after_episode, [&](const bool valid) {
                 first_completion_called = true;
                 first_completion_valid = valid;
               }),
               "the ordered queue publishes one completed resize frame") ||
      !require(barrier.ready_episode() == after_episode &&
                   barrier.ready_trace_snapshot().episode_generation == after_episode &&
                   barrier.ready_trace_snapshot().draw_count == completed_frame_trace.draw_count,
               "the arrived barrier exposes the frame-tail trace, not a later redraw") ||
      !require(!barrier.filter_update(after_episode, false),
               "a ready barrier does not invent a WindowUpdate") ||
      !require(barrier.filter_update(after_episode, true) &&
                   !barrier.filter_update(after_episode, true),
               "a ready barrier admits exactly one presentation WindowUpdate") ||
      !require(barrier.complete(after_episode, true) && first_completion_called &&
                   first_completion_valid,
               "a synchronous present releases the ordered queue successfully") ||
      !require(barrier.completed_episode() == after_episode &&
                   barrier.scheduled_episode() == 0 && barrier.ready_episode() == 0 &&
                   barrier.ready_trace_snapshot().episode_generation == 0,
               "successful presentation retires the resize barrier") ||
      !require(barrier.filter_update(after_episode, true),
               "ordinary redraw policy resumes after the completed barrier") ||
      !require(!barrier.schedule(after_episode),
               "an already presented episode cannot reopen its barrier"))
  {
    return 1;
  }

  const uint64_t superseded_episode = after_episode + 1u;
  const uint64_t newest_episode = after_episode + 2u;
  bool superseded_completion_called = false;
  bool superseded_completion_valid = true;
  if (!require(barrier.schedule(superseded_episode) &&
                   barrier.arrive(superseded_episode, [&](const bool valid) {
                     superseded_completion_called = true;
                     superseded_completion_valid = valid;
                   }),
               "a later resize can reach its barrier") ||
      !require(barrier.schedule(newest_episode) && superseded_completion_called &&
                   !superseded_completion_valid,
               "a newer resize cancels the older waiting barrier") ||
      !require(barrier.cancel(newest_episode) &&
                   barrier.scheduled_episode() == 0,
               "a canceled queue entry makes the same episode retryable") ||
      !require(barrier.schedule(newest_episode),
               "a canceled resize barrier can be scheduled again"))
  {
    return 1;
  }
  bool rejected_completion_called = false;
  bool rejected_completion_valid = true;
  if (!require(barrier.arrive(newest_episode, [&](const bool valid) {
                 rejected_completion_called = true;
                 rejected_completion_valid = valid;
               }) &&
                   barrier.complete(newest_episode, false) && rejected_completion_called &&
                   !rejected_completion_valid,
               "a failed synchronous present rejects and clears its barrier") ||
      !require(barrier.schedule(newest_episode),
               "a failed present leaves the current resize episode retryable"))
  {
    return 1;
  }
  barrier.cancel(newest_episode);

  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::Other,
                               false,
                               640,
                               480,
                               1,
                               2,
                               300,
                               200,
                               true,
                               3,
                               4,
                               250,
                               150);
  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::OverlayBackground,
                               false,
                               808,
                               306,
                               0,
                               0,
                               808,
                               306,
                               false,
                               0,
                               0,
                               0,
                               0);
  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::OcioDisplay,
                               true,
                               1100,
                               640,
                               50,
                               87,
                               808,
                               306,
                               true,
                               50,
                               87,
                               808,
                               306);
  const ghost_web::RedrawTraceSnapshot trace = ghost_web::redraw_trace_snapshot();
  if (!require(ghost_web::redraw_trace_active(after_episode),
               "a fresh drawable episode enables bounded draw tracing") ||
      !require(trace.episode_generation == after_episode && trace.draw_count == 3 &&
                   trace.window_draw_count == 1,
               "draw tracing counts one episode without crossing generations") ||
      !require(trace.last.sequence == 3 && trace.last.window_target &&
                   trace.last.target_width == 1100 && trace.last.target_height == 640 &&
                   trace.last.viewport_x == 50 && trace.last.viewport_y == 87 &&
                   trace.last.viewport_width == 808 && trace.last.viewport_height == 306 &&
                   trace.last.scissor_enabled && trace.last.scissor_x == 50 &&
                   trace.last.scissor_y == 87 && trace.last.scissor_width == 808 &&
                   trace.last.scissor_height == 306,
               "latest draw tracing preserves the exact target viewport and scissor") ||
      !require(trace.background.sequence == 2 && trace.background.target_width == 808 &&
                   trace.background.target_height == 306 &&
                   !trace.background.window_target,
               "background tracing remains independently addressable") ||
      !require(trace.display.sequence == 3 && trace.display.window_target,
               "display-composite tracing remains independently addressable"))
  {
    return 1;
  }
  ghost_web::redraw_trace_finish(after_episode - 1u);
  if (!require(ghost_web::redraw_trace_active(after_episode),
               "a stale generation cannot retire current tracing"))
  {
    return 1;
  }
  ghost_web::redraw_trace_finish(after_episode);
  const uint64_t stopped_draw_count = ghost_web::redraw_trace_snapshot().draw_count;
  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::Other,
                               true,
                               1,
                               1,
                               0,
                               0,
                               1,
                               1,
                               false,
                               0,
                               0,
                               0,
                               0);
  if (!require(!ghost_web::redraw_trace_active(after_episode) &&
                   ghost_web::redraw_trace_snapshot().draw_count == stopped_draw_count,
               "retired tracing ignores later draws"))
  {
    return 1;
  }

  /* A coherent drawable may commit in the middle of an old frame. Episode-wide tracing can then
   * contain valid-looking draws from that old drawable before the first replacement frame begins.
   * A resize present must admit only a frame-local offscreen -> window composite; otherwise an
   * empty next frame can present the untouched replacement backbuffer as a validation-clean black
   * canvas. */
  const uint64_t frame_episode = ghost_web::request_redraw_episode();
  ghost_web::redraw_trace_frame_begin(frame_episode);
  if (!require(!ghost_web::redraw_present_trace_complete(
                   ghost_web::redraw_trace_snapshot(), frame_episode),
               "an empty replacement frame cannot authorize resize presentation"))
  {
    return 1;
  }
  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::Other,
                               false,
                               900,
                               547,
                               0,
                               0,
                               900,
                               547,
                               false,
                               0,
                               0,
                               0,
                               0);
  if (!require(!ghost_web::redraw_present_trace_complete(
                   ghost_web::redraw_trace_snapshot(), frame_episode),
               "offscreen-only work cannot authorize resize presentation"))
  {
    return 1;
  }
  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::Other,
                               true,
                               1100,
                               640,
                               0,
                               0,
                               1100,
                               640,
                               false,
                               0,
                               0,
                               0,
                               0);
  if (!require(!ghost_web::redraw_present_trace_complete(
                   ghost_web::redraw_trace_snapshot(), frame_episode),
               "generic offscreen-to-window work cannot impersonate 3D region content"))
  {
    return 1;
  }
  ghost_web::redraw_trace_frame_begin(frame_episode);
  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::OverlayBackground,
                               false,
                               900,
                               547,
                               0,
                               0,
                               900,
                               547,
                               false,
                               0,
                               0,
                               0,
                               0);
  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::OcioDisplay,
                               true,
                               1100,
                               640,
                               0,
                               0,
                               1100,
                               640,
                               false,
                               0,
                               0,
                               0,
                               0);
  if (!require(ghost_web::redraw_present_trace_complete(
                   ghost_web::redraw_trace_snapshot(), frame_episode),
               "frame-local 3D background followed by window display authorizes presentation") ||
      !require(!ghost_web::viewport_content_trace_complete(
                   ghost_web::redraw_trace_snapshot(), frame_episode),
               "background-only VIEW_3D content cannot dismiss the loader") ||
      !require(!ghost_web::note_viewport_content_presented(
                   ghost_web::redraw_trace_snapshot(), frame_episode) &&
                   ghost_web::viewport_content_present_count() == 0,
               "an incomplete VIEW_3D trace cannot publish loader readiness"))
  {
    return 1;
  }

  /* The live overlay manager encodes its stock grid before overlay_background; both feed the
   * later direct-window display composite. Loader readiness must accept that real order while
   * still rejecting a grid that arrives after the composite it is meant to qualify. */
  ghost_web::redraw_trace_frame_begin(frame_episode);
  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::OverlayGrid,
                               false,
                               900,
                               547,
                               0,
                               0,
                               900,
                               547,
                               false,
                               0,
                               0,
                               0,
                               0);
  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::OverlayBackground,
                               false,
                               900,
                               547,
                               0,
                               0,
                               900,
                               547,
                               false,
                               0,
                               0,
                               0,
                               0);
  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::OcioDisplay,
                               true,
                               1100,
                               640,
                               0,
                               0,
                               1100,
                               640,
                               false,
                               0,
                               0,
                               0,
                               0);
  if (!require(ghost_web::viewport_content_trace_complete(
                   ghost_web::redraw_trace_snapshot(), frame_episode),
               "grid-background-display frame qualifies as VIEW_3D content"))
  {
    return 1;
  }

  /* The alternate background-grid-display order remains semantically complete, and one
   * validated surface submission publishes exactly one process-wide readiness edge. */
  ghost_web::redraw_trace_frame_begin(frame_episode);
  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::OverlayBackground,
                               false,
                               900,
                               547,
                               0,
                               0,
                               900,
                               547,
                               false,
                               0,
                               0,
                               0,
                               0);
  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::OverlayGrid,
                               false,
                               900,
                               547,
                               0,
                               0,
                               900,
                               547,
                               false,
                               0,
                               0,
                               0,
                               0);
  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::OcioDisplay,
                               true,
                               1100,
                               640,
                               0,
                               0,
                               1100,
                               640,
                               false,
                               0,
                               0,
                               0,
                               0);
  const ghost_web::RedrawTraceSnapshot viewport_content_frame =
      ghost_web::redraw_trace_snapshot();
  if (!require(ghost_web::viewport_content_trace_complete(viewport_content_frame, frame_episode),
               "background-grid-display frame qualifies as VIEW_3D content") ||
      !require(viewport_content_frame.display.sequence > viewport_content_frame.grid.sequence &&
                   viewport_content_frame.display.sequence >
                       viewport_content_frame.background.sequence,
               "VIEW_3D trace keeps both region passes before the display composite") ||
      !require(ghost_web::note_viewport_content_presented(viewport_content_frame, frame_episode) &&
                   ghost_web::viewport_content_present_count() == 1,
               "the first validated VIEW_3D present publishes loader readiness") ||
      !require(!ghost_web::note_viewport_content_presented(viewport_content_frame, frame_episode) &&
                   ghost_web::viewport_content_present_count() == 1,
               "VIEW_3D loader readiness is a one-shot edge"))
  {
    return 1;
  }

  /* Beginning the next frame must retire the prior frame's semantic admission facts while
   * preserving episode-wide diagnostic counters. */
  const ghost_web::RedrawTraceSnapshot completed_frame = ghost_web::redraw_trace_snapshot();
  ghost_web::redraw_trace_frame_begin(frame_episode);
  const ghost_web::RedrawTraceSnapshot empty_next_frame = ghost_web::redraw_trace_snapshot();
  if (!require(empty_next_frame.draw_count == completed_frame.draw_count &&
                   empty_next_frame.window_draw_count == completed_frame.window_draw_count,
               "frame reset preserves episode-wide diagnostic counts") ||
      !require(ghost_web::redraw_present_frame_matches_episode(frame_episode, frame_episode),
               "the adopted resize episode remains current") ||
      !require(!ghost_web::redraw_present_trace_complete(empty_next_frame, frame_episode),
               "a prior frame composite cannot authorize an empty later frame"))
  {
    return 1;
  }
  ghost_web::redraw_trace_note(ghost_web::RedrawTracePass::Other,
                               true,
                               1100,
                               640,
                               0,
                               0,
                               1100,
                               640,
                               false,
                               0,
                               0,
                               0,
                               0);
  if (!require(!ghost_web::redraw_present_trace_complete(
                   ghost_web::redraw_trace_snapshot(), frame_episode),
               "window-only work cannot authorize resize presentation") ||
      !require(!ghost_web::redraw_present_frame_matches_episode(frame_episode - 1u,
                                                                 frame_episode),
               "frame-local completeness cannot override an adopted episode mismatch"))
  {
    return 1;
  }
  episode_generation_seen = frame_episode;

  heartbeat = ghost_web::FIRST_PIXEL_SETTLE_TICKS - 1u;
  retry_generation_seen = resize_request;
  drop_generation_seen = active_drop;
  ghost_web::note_redraw_drop();
  const uint64_t final_drop = ghost_web::redraw_drop_generation();
  if (!require(recovery_tick() && drop_generation_seen == final_drop &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_TICKS,
               "an incomplete draw on the final bounded tick gets one retry"))
  {
    return 1;
  }
  ghost_web::note_redraw_drop();
  const uint64_t repeated_drop = ghost_web::redraw_drop_generation();
  if (!require(!recovery_tick() && drop_generation_seen == repeated_drop &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_TICKS,
               "repeated incomplete draws cannot rearm the hard ceiling"))
  {
    return 1;
  }

  ghost_web::request_redraw_retry();
  const uint64_t settled_request = ghost_web::redraw_retry_generation();
  if (!require(recovery_tick() && retry_generation_seen == settled_request && heartbeat == 1,
               "accepted readiness can rearm after a bounded drop episode") ||
      !require(!ghost_web::redraw_trace_active(frame_episode),
               "semantic tracing stays retired after VIEW_3D readiness"))
  {
    return 1;
  }

  /* A replacement drawable may commit after the previous episode's barrier is already ready but
   * before GHOST enters swapBufferRelease(). The commit must retire that obsolete barrier only
   * after publishing the replacement episode; otherwise GHOST can copy the new, untouched
   * backbuffer under the old episode. */
  bool commit_superseded_completion_called = false;
  bool commit_superseded_completion_valid = true;
  const uint64_t ready_commit_episode = ghost_web::redraw_episode_generation();
  const uint64_t commit_superseded_episode = ready_commit_episode + 1u;
  if (!require(ghost_web::schedule_redraw_present_barrier(
                   ready_commit_episode, ghost_web::RedrawTraceSnapshot{}) &&
                   ghost_web::arrive_redraw_present_barrier(
                       ready_commit_episode, [&](const bool valid) {
                         commit_superseded_completion_called = true;
                         commit_superseded_completion_valid = valid;
                       }),
               "an older ready barrier can overlap a replacement drawable commit"))
  {
    return 1;
  }
  const uint64_t published_commit_episode = ghost_web::request_redraw_episode();
  if (!require(published_commit_episode == commit_superseded_episode,
               "a replacement commit returns its published episode") ||
      !require(ghost_web::cancel_superseded_redraw_present_barrier(
                   published_commit_episode) &&
                   commit_superseded_completion_called &&
                   !commit_superseded_completion_valid,
               "a replacement commit cancels the older ready barrier") ||
      !require(!ghost_web::redraw_present_barrier_is_scheduled(),
               "commit-time supersession cannot leave stale present suppression active"))
  {
    return 1;
  }

  constexpr uint64_t wrapped_generation = std::numeric_limits<uint64_t>::max();
  retry_generation_seen = wrapped_generation;
  episode_generation_seen = ghost_web::redraw_episode_generation();
  drop_generation_seen = ghost_web::redraw_drop_generation();
  heartbeat = ghost_web::FIRST_PIXEL_SETTLE_TICKS;
  if (!require(ghost_web::redraw_recovery_tick(0,
                                               retry_generation_seen,
                                               episode_generation_seen,
                                               episode_generation_seen,
                                               drop_generation_seen,
                                               drop_generation_seen,
                                               heartbeat) &&
                   retry_generation_seen == 0 && heartbeat == 1,
               "retry generation wrap re-arms a terminal burst"))
  {
    return 1;
  }

  episode_generation_seen = wrapped_generation;
  heartbeat = ghost_web::FIRST_PIXEL_SETTLE_TICKS;
  if (!require(ghost_web::redraw_recovery_tick(retry_generation_seen,
                                               retry_generation_seen,
                                               0,
                                               episode_generation_seen,
                                               drop_generation_seen,
                                               drop_generation_seen,
                                               heartbeat) &&
                   episode_generation_seen == 0 && heartbeat == 1,
               "episode generation wrap starts a fresh bounded burst"))
  {
    return 1;
  }

  std::printf(
      "CONTRACT ghost_redraw_recovery PASS cases=%d periodic=15 "
      "late=immediate drops=bounded readiness=rearmed resize_commit=fresh "
      "present_barrier=ordered-sync-commit-superseded trace=bounded-exact "
      "viewport_ready=grid-validated-one-shot wrap=rearmed\n",
      checks);
  return checks == 66 ? 0 : 1;
}
