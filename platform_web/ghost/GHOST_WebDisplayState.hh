/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * \ingroup GHOST-web
 *
 * Shared display-state handshake between the browser MAIN thread (the shell) and the
 * PROXY_TO_PTHREAD WM worker that owns the OffscreenCanvas + WebGPU surface.
 *
 * The two live-window facts the WM worker cannot read on its own are:
 *
 *   1. `window.devicePixelRatio` - the worker has no `window`/`document`, so a bare
 *      DPR probe returns 1.0 and Blender's UI draws at half physical size on a HiDPI
 *      display (`U.pixelsize` stays 1 while the backing store is 2x).
 *   2. A live browser resize - after boot the `#canvas` is an OffscreenCanvas owned by
 *      this worker; only this worker may call `emscripten_set_canvas_element_size`, so
 *      the main thread cannot grow the backing store and the shell can only CSS-stretch
 *      (blur) or letterbox (black bars).
 *
 * Both are pushed from the shell via the EMSCRIPTEN_KEEPALIVE export `bw_shell_set_display`
 * (defined in GHOST_SystemWeb.cc), which the main thread may call safely: it only performs
 * relaxed/release atomic stores into shared wasm linear memory (SharedArrayBuffer under
 * -pthread). The WM worker consumes them here - DPR via #device_pixel_ratio() (fed to
 * getNativePixelSize/getClientBounds/getDPIHint), and the pending backing size via
 * #poll_pending_backing() once per WM tick (GHOST_SystemWeb::processEvents), where the
 * worker performs the actual canvas resize + surface reconfigure + GHOST_kEventWindowSize.
 */

#pragma once

#include <atomic>
#include <cstdint>

namespace ghost_web {

/** Device pixel ratio last posted by the shell (main thread). Defaults to 1.0 until the
 * shell posts a value; safe to call on any thread (a single relaxed atomic load). */
double device_pixel_ratio();

/** If the shell has posted a NEW target backing extent (physical pixels =
 * cssPx * devicePixelRatio) since the previous call, returns true and fills \a w / \a h.
 * Returns false when nothing changed. Single-consumer: call only from the canvas-owning
 * (WM) worker's per-tick poll. */
bool poll_pending_backing(int32_t &w, int32_t &h);

/** Total WebGPU presents (surface submits) since boot. The inline variable keeps this
 * platform state available to both WebGPU and device-free GHOST builds without a link-time
 * dependency on the WebGPU context. It is bumped once per presentBackbuffer(). Read by
 * GHOST_SystemWeb::processEvents to tell whether a frame was drawn since the last tick
 * (idle-keepalive activity detection) and exported for the no-idle-burn proof
 * (bw_present_count). A single relaxed atomic load; safe to call on any thread. */
inline std::atomic<uint64_t> present_counter{0};

inline uint64_t present_count()
{
  return present_counter.load(std::memory_order_relaxed);
}

/** Called by GHOST_ContextWGPUWeb::presentBackbuffer() to record one present. */
inline void note_present()
{
  present_counter.fetch_add(1u, std::memory_order_relaxed);
}

/**
 * Monotonic publication generation for a WebGPU draw that became retryable after Blender had
 * already asked for it. Browser Dawn validates shader modules, explicit layouts, pipelines, and
 * bind-group resources asynchronously; their first draw may therefore return before encoding.
 * The owning window consumes this generation and requests an ordinary full-screen update after
 * readiness settles instead of leaving that region stale until unrelated user input.
 */
inline std::atomic<uint64_t> redraw_retry_counter{0};
inline std::atomic<uint64_t> redraw_episode_counter{0};
inline std::atomic<uint64_t> redraw_drop_counter{0};

/**
 * Episode-scoped draw-plan trace used to diagnose hardware-only resize composition failures.
 * Rendering and presentation both run on the OffscreenCanvas-owning WM worker, so the payload is
 * deliberately a plain single-writer snapshot; only the active flag crosses callback boundaries.
 * Recording stops at the recovery ceiling (or the present logger's smaller sample ceiling), so
 * the diagnostic adds no steady-state draw-path work after the bounded resize episode.
 */
enum class RedrawTracePass : uint8_t {
  Other = 0,
  OverlayBackground,
  OcioDisplay,
};

struct RedrawTracePlan {
  uint64_t sequence = 0;
  bool window_target = false;
  int32_t target_width = 0;
  int32_t target_height = 0;
  int32_t viewport_x = 0;
  int32_t viewport_y = 0;
  uint32_t viewport_width = 0;
  uint32_t viewport_height = 0;
  bool scissor_enabled = false;
  uint32_t scissor_x = 0;
  uint32_t scissor_y = 0;
  uint32_t scissor_width = 0;
  uint32_t scissor_height = 0;
};

struct RedrawTraceSnapshot {
  uint64_t episode_generation = 0;
  uint64_t draw_count = 0;
  uint64_t window_draw_count = 0;
  RedrawTracePlan last;
  RedrawTracePlan background;
  RedrawTracePlan display;
};

inline std::atomic<bool> redraw_trace_capture_active{false};
inline RedrawTraceSnapshot redraw_trace_state{};

inline void redraw_trace_begin(const uint64_t episode_generation)
{
  redraw_trace_capture_active.store(false, std::memory_order_release);
  redraw_trace_state = {};
  redraw_trace_state.episode_generation = episode_generation;
  redraw_trace_capture_active.store(true, std::memory_order_release);
}

inline bool redraw_trace_capturing()
{
  return redraw_trace_capture_active.load(std::memory_order_acquire);
}

inline bool redraw_trace_active(const uint64_t episode_generation)
{
  return redraw_trace_capturing() &&
         redraw_trace_state.episode_generation == episode_generation;
}

inline void redraw_trace_finish(const uint64_t episode_generation)
{
  if (redraw_trace_state.episode_generation == episode_generation) {
    redraw_trace_capture_active.store(false, std::memory_order_release);
  }
}

inline void redraw_trace_note(const RedrawTracePass pass,
                              const bool window_target,
                              const int32_t target_width,
                              const int32_t target_height,
                              const int32_t viewport_x,
                              const int32_t viewport_y,
                              const uint32_t viewport_width,
                              const uint32_t viewport_height,
                              const bool scissor_enabled,
                              const uint32_t scissor_x,
                              const uint32_t scissor_y,
                              const uint32_t scissor_width,
                              const uint32_t scissor_height)
{
  if (!redraw_trace_capturing()) {
    return;
  }
  RedrawTracePlan plan;
  plan.sequence = ++redraw_trace_state.draw_count;
  plan.window_target = window_target;
  plan.target_width = target_width;
  plan.target_height = target_height;
  plan.viewport_x = viewport_x;
  plan.viewport_y = viewport_y;
  plan.viewport_width = viewport_width;
  plan.viewport_height = viewport_height;
  plan.scissor_enabled = scissor_enabled;
  plan.scissor_x = scissor_x;
  plan.scissor_y = scissor_y;
  plan.scissor_width = scissor_width;
  plan.scissor_height = scissor_height;
  redraw_trace_state.last = plan;
  if (window_target) {
    redraw_trace_state.window_draw_count++;
  }
  if (pass == RedrawTracePass::OverlayBackground) {
    redraw_trace_state.background = plan;
  }
  else if (pass == RedrawTracePass::OcioDisplay) {
    redraw_trace_state.display = plan;
  }
}

inline RedrawTraceSnapshot redraw_trace_snapshot()
{
  return redraw_trace_state;
}

inline void request_redraw_retry()
{
  redraw_retry_counter.fetch_add(1u, std::memory_order_release);
}

inline uint64_t redraw_retry_generation()
{
  return redraw_retry_counter.load(std::memory_order_acquire);
}

/**
 * Start a fresh bounded recovery episode after a replacement drawable becomes coherent. Unlike a
 * shader-readiness retry, this signal resets an already-active episode: a resize can spend the
 * tail of an older episode while its asynchronously validated surface/backbuffer is still pending.
 */
inline void request_redraw_episode()
{
  const uint64_t generation =
      redraw_episode_counter.fetch_add(1u, std::memory_order_release) + 1u;
  redraw_trace_begin(generation);
}

inline uint64_t redraw_episode_generation()
{
  return redraw_episode_counter.load(std::memory_order_acquire);
}

inline void note_redraw_drop()
{
  redraw_drop_counter.fetch_add(1u, std::memory_order_release);
}

inline uint64_t redraw_drop_generation()
{
  return redraw_drop_counter.load(std::memory_order_acquire);
}

/**
 * Bounded redraw recovery for one published window. Boot starts one burst even before a retry
 * signal so lazily created visible-region variants are discovered. A readiness signal requests an
 * immediate update; accepted readiness re-arms a completed burst, but neither accepted readiness
 * nor repeated incomplete draws reset an active burst's hard ceiling. A newly committed drawable
 * extent starts its own bounded episode because updates issued while that extent was pending could
 * not draw into it. A drop is acknowledged at the ceiling without rearming, so persistent failures
 * consume at most one bounded episode while a later newly accepted shader variant can still
 * recover an otherwise idle region.
 */
inline constexpr uint32_t FIRST_PIXEL_SETTLE_TICKS = 180u;
inline constexpr uint32_t FIRST_PIXEL_SETTLE_INTERVAL = 12u;

inline bool redraw_recovery_tick(const uint64_t retry_generation,
                                 uint64_t &retry_generation_seen,
                                 const uint64_t episode_generation,
                                 uint64_t &episode_generation_seen,
                                 const uint64_t drop_generation,
                                 uint64_t &drop_generation_seen,
                                 uint32_t &heartbeat)
{
  const bool readiness_published = retry_generation != retry_generation_seen;
  const bool episode_published = episode_generation != episode_generation_seen;
  const bool draw_dropped = drop_generation != drop_generation_seen;
  if (episode_published) {
    episode_generation_seen = episode_generation;
    heartbeat = 0;
  }
  if (readiness_published) {
    retry_generation_seen = retry_generation;
    if (heartbeat >= FIRST_PIXEL_SETTLE_TICKS) {
      heartbeat = 0;
    }
  }
  if (draw_dropped) {
    drop_generation_seen = drop_generation;
  }
  if (heartbeat >= FIRST_PIXEL_SETTLE_TICKS) {
    redraw_trace_finish(episode_generation);
    return false;
  }
  const bool request_update = episode_published || readiness_published || draw_dropped ||
                              (heartbeat % FIRST_PIXEL_SETTLE_INTERVAL) == 0u;
  heartbeat++;
  return request_update;
}

}  // namespace ghost_web
