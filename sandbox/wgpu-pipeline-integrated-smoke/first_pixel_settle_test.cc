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
               "late readiness re-arms a terminal recovery burst"))
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
               "accepted readiness can rearm after a bounded drop episode"))
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
      "trace=bounded-exact wrap=rearmed\n",
      checks);
  return checks == 26 ? 0 : 1;
}
