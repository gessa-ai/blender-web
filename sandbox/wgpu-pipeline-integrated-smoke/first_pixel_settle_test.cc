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
  uint32_t heartbeat = 0;
  constexpr uint64_t initial_baseline = 40;
  if (!require(ghost_web::first_pixel_settle_tick(initial_baseline,
                                                   initial_baseline,
                                                   heartbeat) &&
                   heartbeat == 1,
               "initial epoch requests an update"))
  {
    return 1;
  }

  bool early_request = false;
  for (uint32_t tick = 1; tick < ghost_web::FIRST_PIXEL_SETTLE_INTERVAL; tick++) {
    early_request |= ghost_web::first_pixel_settle_tick(
        initial_baseline, initial_baseline, heartbeat);
  }
  if (!require(!early_request && heartbeat == ghost_web::FIRST_PIXEL_SETTLE_INTERVAL,
               "settle interval is quiet between requests") ||
      !require(ghost_web::first_pixel_settle_tick(initial_baseline,
                                                  initial_baseline,
                                                  heartbeat) &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_INTERVAL + 1u,
               "settle interval requests its next update") ||
      !require(!ghost_web::first_pixel_settle_tick(initial_baseline + 1u,
                                                   initial_baseline,
                                                   heartbeat) &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_INTERVAL + 2u,
               "first submitted frame remains pending") ||
      !require(!ghost_web::first_pixel_settle_tick(initial_baseline + 2u,
                                                   initial_baseline,
                                                   heartbeat) &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_TICKS,
               "second submitted frame completes settling") ||
      !require(!ghost_web::first_pixel_settle_tick(initial_baseline + 3u,
                                                   initial_baseline,
                                                   heartbeat) &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_TICKS,
               "completed settling remains terminal"))
  {
    return 1;
  }

  constexpr uint64_t replacement_baseline = initial_baseline + 3u;
  heartbeat = 0;
  if (!require(ghost_web::first_pixel_settle_tick(replacement_baseline,
                                                  replacement_baseline,
                                                  heartbeat) &&
                   heartbeat == 1,
               "replacement window starts a new epoch") ||
      !require(!ghost_web::first_pixel_settle_tick(replacement_baseline + 1u,
                                                   replacement_baseline,
                                                   heartbeat) &&
                   heartbeat == 2,
               "replacement first frame remains pending") ||
      !require(!ghost_web::first_pixel_settle_tick(replacement_baseline + 2u,
                                                   replacement_baseline,
                                                   heartbeat) &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_TICKS,
               "replacement second frame completes its epoch"))
  {
    return 1;
  }

  heartbeat = ghost_web::FIRST_PIXEL_SETTLE_TICKS - 1u;
  if (!require(!ghost_web::first_pixel_settle_tick(100, 100, heartbeat) &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_TICKS,
               "final bounded tick retires without an off-interval request") ||
      !require(!ghost_web::first_pixel_settle_tick(100, 100, heartbeat) &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_TICKS,
               "timed-out settling remains terminal"))
  {
    return 1;
  }

  heartbeat = 0;
  if (!require(!ghost_web::first_pixel_settle_tick(2, 0, heartbeat) &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_TICKS,
               "already-complete epoch retires immediately"))
  {
    return 1;
  }

  constexpr uint64_t wrapped_baseline = std::numeric_limits<uint64_t>::max();
  heartbeat = 0;
  if (!require(!ghost_web::first_pixel_settle_tick(1, wrapped_baseline, heartbeat) &&
                   heartbeat == ghost_web::FIRST_PIXEL_SETTLE_TICKS,
               "monotonic counter wrap preserves two-present completion"))
  {
    return 1;
  }
  heartbeat = 0;
  if (!require(ghost_web::first_pixel_settle_tick(0, wrapped_baseline, heartbeat) &&
                   heartbeat == 1,
               "monotonic counter wrap keeps one-present epoch pending"))
  {
    return 1;
  }

  std::printf(
      "CONTRACT ghost_first_pixel_settle PASS cases=%d requests=4 initial=complete "
      "replacement=complete timeout=bounded wrap=complete\n",
      checks);
  return checks == 14 ? 0 : 1;
}
