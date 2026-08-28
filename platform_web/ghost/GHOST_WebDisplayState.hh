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
#include <cstddef>
#include <cstdint>
#include <functional>
#include <mutex>
#include <utility>

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
 * Monotonic evidence that a newer swap was coalesced behind asynchronous surface validation and
 * that settlement requested the corresponding fresh surface blit. The suppressed counter is
 * diagnostic-only; the replay counter is also the release/acquire generation consumed by the WM
 * loop. Both remain cheap atomics on the single WebGPU-owning worker.
 */
inline std::atomic<uint64_t> present_suppressed_counter{0};
inline std::atomic<uint64_t> present_replay_counter{0};

inline void note_present_suppressed()
{
  present_suppressed_counter.fetch_add(1u, std::memory_order_relaxed);
}

inline uint64_t present_suppressed_count()
{
  return present_suppressed_counter.load(std::memory_order_relaxed);
}

/** Publish one coalesced request for the WM loop to redraw and present the latest backbuffer.
 * Unlike generic readiness, this generation is consumed only after a WindowUpdate is admitted. */
inline uint64_t request_present_replay()
{
  return present_replay_counter.fetch_add(1u, std::memory_order_release) + 1u;
}

inline uint64_t present_replay_generation()
{
  return present_replay_counter.load(std::memory_order_acquire);
}

inline uint64_t present_replay_count()
{
  return present_replay_generation();
}

/**
 * Bounded diagnosis for the stock dashed-line immediate shader used by the camera frame and
 * transform guides. Each stage is monotonic and diagnostic-only. A browser receipt can therefore
 * distinguish a draw that was never retried from one that encoded but later failed validation,
 * without parsing asynchronous warning text or changing draw scheduling.
 */
enum class ImmediateDashedStage : uint8_t {
  Attempt = 0,
  ModuleDeferred,
  GeometryDeferred,
  TargetDeferred,
  PipelineDeferred,
  VertexDeferred,
  BindingDeferred,
  LoadDeferred,
  PassDeferred,
  Encoded,
  Accepted,
  Rejected,
  Count,
};

inline std::atomic<uint64_t>
    immediate_dashed_stage_counters[size_t(ImmediateDashedStage::Count)]{};

inline void note_immediate_dashed_stage(const ImmediateDashedStage stage)
{
  const size_t index = size_t(stage);
  if (index < size_t(ImmediateDashedStage::Count)) {
    immediate_dashed_stage_counters[index].fetch_add(1u, std::memory_order_relaxed);
  }
}

inline uint64_t immediate_dashed_stage_count(const uint32_t stage)
{
  if (stage >= uint32_t(ImmediateDashedStage::Count)) {
    return 0;
  }
  return immediate_dashed_stage_counters[stage].load(std::memory_order_relaxed);
}

/**
 * Monotonic publication generation for a WebGPU draw that became retryable after Blender had
 * already asked for it. Browser Dawn validates shader modules, explicit layouts, pipelines, and
 * bind-group resources asynchronously; their first draw may therefore return before encoding.
 * The owning window consumes this generation and requests an ordinary full-screen update after
 * readiness settles instead of leaving that region stale until unrelated user input.
 */
inline std::atomic<uint64_t> redraw_retry_counter{0};
inline std::atomic<uint64_t> input_redraw_retry_counter{0};
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
  OverlayGrid,
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
  uint64_t frame_draw_count = 0;
  uint64_t frame_offscreen_draw_count = 0;
  uint64_t frame_window_draw_count = 0;
  uint64_t frame_first_offscreen_sequence = 0;
  uint64_t frame_last_window_sequence = 0;
  RedrawTracePlan last;
  RedrawTracePlan background;
  RedrawTracePlan grid;
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

/**
 * Start the trace facts for one adopted window-backbuffer frame without discarding the
 * episode-wide diagnostic counters. A coherent resize can commit while an older frame is still
 * encoding; clearing the frame-local facts at the next backbuffer adoption prevents those old
 * drawable commands from authorizing presentation of an untouched replacement texture.
 */
inline void redraw_trace_frame_begin(const uint64_t episode_generation)
{
  if (!redraw_trace_active(episode_generation)) {
    return;
  }
  redraw_trace_state.frame_draw_count = 0;
  redraw_trace_state.frame_offscreen_draw_count = 0;
  redraw_trace_state.frame_window_draw_count = 0;
  redraw_trace_state.frame_first_offscreen_sequence = 0;
  redraw_trace_state.frame_last_window_sequence = 0;
  redraw_trace_state.last = {};
  redraw_trace_state.background = {};
  redraw_trace_state.grid = {};
  redraw_trace_state.display = {};
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
  redraw_trace_state.frame_draw_count++;
  if (window_target) {
    redraw_trace_state.window_draw_count++;
    redraw_trace_state.frame_window_draw_count++;
    redraw_trace_state.frame_last_window_sequence = plan.sequence;
  }
  else {
    redraw_trace_state.frame_offscreen_draw_count++;
    if (redraw_trace_state.frame_first_offscreen_sequence == 0) {
      redraw_trace_state.frame_first_offscreen_sequence = plan.sequence;
    }
  }
  if (pass == RedrawTracePass::OverlayBackground) {
    redraw_trace_state.background = plan;
  }
  else if (pass == RedrawTracePass::OverlayGrid) {
    redraw_trace_state.grid = plan;
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
 * Ordinary input needs a full bounded recovery tail after its final accepted callback. Keep a
 * distinct generation so an input arriving near the end of a shader-readiness burst can restart
 * that tail without changing the hard-ceiling semantics of asynchronous resource publication.
 * The aggregate retry generation still advances for the browser diagnostic and immediate update.
 */
inline void request_input_redraw_retry()
{
  input_redraw_retry_counter.fetch_add(1u, std::memory_order_release);
  redraw_retry_counter.fetch_add(1u, std::memory_order_release);
}

inline uint64_t input_redraw_retry_generation()
{
  return input_redraw_retry_counter.load(std::memory_order_acquire);
}

/**
 * Start a fresh bounded recovery episode after a replacement drawable becomes coherent. Unlike a
 * shader-readiness retry, this signal resets an already-active episode: a resize can spend the
 * tail of an older episode while its asynchronously validated surface/backbuffer is still pending.
 */
inline uint64_t request_redraw_episode()
{
  const uint64_t generation =
      redraw_episode_counter.fetch_add(1u, std::memory_order_release) + 1u;
  redraw_trace_begin(generation);
  return generation;
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
 * A resize barrier may represent only a frame that began after the same replacement drawable
 * became current. Browser validation callbacks can publish a newer resize episode while an older
 * frame is still encoding; accepting that frame would copy the untouched replacement backbuffer
 * while the real new-extent submissions remain queued behind the barrier.
 */
inline bool redraw_present_frame_matches_episode(const uint64_t frame_episode,
                                                 const uint64_t current_episode)
{
  return frame_episode == current_episode;
}

/**
 * True only when one adopted replacement-backbuffer frame encoded the visible 3D region's
 * background and a later direct-window display composite, with the frame ending on a window
 * target. Episode-wide trace history is intentionally insufficient: a resize callback can start a
 * new episode in the middle of an old drawable's frame, while generic offscreen/window work may
 * describe chrome without any replacement VIEW_3D content.
 */
inline bool redraw_present_trace_complete(const RedrawTraceSnapshot &trace,
                                           const uint64_t episode)
{
  return trace.episode_generation == episode && trace.frame_draw_count >= 2u &&
         trace.frame_offscreen_draw_count > 0u && trace.frame_window_draw_count > 0u &&
         trace.frame_first_offscreen_sequence > 0u &&
         trace.frame_last_window_sequence > trace.frame_first_offscreen_sequence &&
         trace.frame_last_window_sequence == trace.last.sequence &&
         trace.background.sequence > 0u && !trace.background.window_target &&
         trace.display.sequence > trace.background.sequence && trace.display.window_target;
}

/**
 * A generic complete VIEW_3D composite may still contain only its clear/background pass while
 * the lazily validated overlay pipeline is unavailable. Loader dismissal is stricter: require a
 * successfully encoded stock grid draw in the same frame before the final direct-window OCIO
 * composite. The live overlay manager may encode grid before or after `overlay_background`, so
 * the two offscreen passes are independently required without inventing an order between them.
 * `debug_note_draw()` runs only after bind-group completeness and draw encoding succeed, so this
 * cannot be satisfied by a dropped `overlay_grid_next` draw.
 */
inline bool viewport_content_trace_complete(const RedrawTraceSnapshot &trace,
                                             const uint64_t episode)
{
  return redraw_present_trace_complete(trace, episode) &&
         trace.grid.sequence > 0u && !trace.grid.window_target &&
         trace.display.sequence > trace.grid.sequence;
}

/** Successful surface submissions carrying a strict VIEW_3D frame. The first value is the
 * loader-readiness edge; the counter shape avoids a BigInt hop in the browser export. */
inline std::atomic<uint64_t> viewport_content_present_counter{0};

inline uint64_t viewport_content_present_count()
{
  return viewport_content_present_counter.load(std::memory_order_acquire);
}

inline bool note_viewport_content_presented(const RedrawTraceSnapshot &trace,
                                             const uint64_t episode)
{
  if (!viewport_content_trace_complete(trace, episode)) {
    return false;
  }
  uint64_t expected = 0;
  return viewport_content_present_counter.compare_exchange_strong(
      expected, 1u, std::memory_order_release, std::memory_order_relaxed);
}

/**
 * One resize-frame submission barrier between Blender's asynchronously validated WebGPU queue and
 * GHOST's synchronous window present.
 *
 * Browser command scopes settle only after the current JavaScript turn. WM can therefore reach
 * swapBufferRelease() while the frame it just encoded is still queued, and presenting the shared
 * persistent backbuffer at that point exposes an arbitrary intermediate pass. The backend appends
 * this barrier at end_frame(), together with the draw-plan snapshot from that exact frame tail.
 * Once all earlier queue entries have completed, the barrier admits exactly one synthetic
 * WindowUpdate while holding later submissions. GHOST then copies the completed backbuffer
 * synchronously and releases the queue after that copy has been submitted. Diagnostics use the
 * immutable barrier snapshot, never plans encoded by the later synthetic update.
 * A newer resize cancels an older waiter; a failed/canceled present leaves the same episode
 * retryable. This state is process-global because GHOST-web publishes exactly one canvas window.
 */
class RedrawPresentBarrier {
 public:
  using Completion = std::function<void(bool)>;

  bool schedule(const uint64_t episode, RedrawTraceSnapshot trace_snapshot = {})
  {
    Completion superseded;
    {
      std::lock_guard lock(mutex_);
      if ((phase_ != Phase::Idle && scheduled_episode_ == episode) ||
          (completed_valid_ && completed_episode_ == episode))
      {
        return false;
      }
      superseded = std::move(completion_);
      scheduled_episode_ = episode;
      scheduled_trace_snapshot_ =
          trace_snapshot.episode_generation == episode ? std::move(trace_snapshot) :
                                                         RedrawTraceSnapshot{};
      phase_ = Phase::Scheduled;
      update_requested_ = false;
    }
    if (superseded) {
      superseded(false);
    }
    return true;
  }

  bool arrive(const uint64_t episode, Completion completion)
  {
    bool accepted = false;
    {
      std::lock_guard lock(mutex_);
      if (phase_ == Phase::Scheduled && scheduled_episode_ == episode) {
        completion_ = std::move(completion);
        phase_ = Phase::Ready;
        update_requested_ = false;
        accepted = true;
      }
    }
    if (!accepted && completion) {
      completion(false);
    }
    return accepted;
  }

  /** Filter only the synthetic recovery update. Ordinary input remains owned by WM. */
  bool filter_update(const uint64_t episode, const bool requested)
  {
    std::lock_guard lock(mutex_);
    if (phase_ == Phase::Idle || scheduled_episode_ != episode) {
      return requested;
    }
    if (phase_ == Phase::Scheduled || !requested || update_requested_) {
      return false;
    }
    update_requested_ = true;
    return true;
  }

  bool complete(const uint64_t episode, const bool valid)
  {
    Completion completion;
    {
      std::lock_guard lock(mutex_);
      if (phase_ != Phase::Ready || scheduled_episode_ != episode) {
        return false;
      }
      completion = std::move(completion_);
      phase_ = Phase::Idle;
      scheduled_episode_ = 0;
      scheduled_trace_snapshot_ = {};
      update_requested_ = false;
      if (valid) {
        completed_valid_ = true;
        completed_episode_ = episode;
        completion_generation_++;
      }
    }
    if (completion) {
      completion(valid);
    }
    return true;
  }

  bool cancel(const uint64_t episode)
  {
    Completion completion;
    {
      std::lock_guard lock(mutex_);
      if (phase_ == Phase::Idle || scheduled_episode_ != episode) {
        return false;
      }
      completion = std::move(completion_);
      phase_ = Phase::Idle;
      scheduled_episode_ = 0;
      scheduled_trace_snapshot_ = {};
      update_requested_ = false;
    }
    if (completion) {
      completion(false);
    }
    return true;
  }

  /** Retire an older scheduled or ready barrier when a replacement drawable commits. */
  bool cancel_superseded(const uint64_t current_episode)
  {
    Completion completion;
    {
      std::lock_guard lock(mutex_);
      if (phase_ == Phase::Idle || scheduled_episode_ == current_episode) {
        return false;
      }
      completion = std::move(completion_);
      phase_ = Phase::Idle;
      scheduled_episode_ = 0;
      scheduled_trace_snapshot_ = {};
      update_requested_ = false;
    }
    if (completion) {
      completion(false);
    }
    return true;
  }

  bool is_scheduled() const
  {
    std::lock_guard lock(mutex_);
    return phase_ != Phase::Idle;
  }

  bool is_ready() const
  {
    std::lock_guard lock(mutex_);
    return phase_ == Phase::Ready;
  }

  uint64_t scheduled_episode() const
  {
    std::lock_guard lock(mutex_);
    return scheduled_episode_;
  }

  uint64_t ready_episode() const
  {
    std::lock_guard lock(mutex_);
    return phase_ == Phase::Ready ? scheduled_episode_ : 0;
  }

  RedrawTraceSnapshot ready_trace_snapshot() const
  {
    std::lock_guard lock(mutex_);
    return phase_ == Phase::Ready ? scheduled_trace_snapshot_ : RedrawTraceSnapshot{};
  }

  uint64_t completed_episode() const
  {
    std::lock_guard lock(mutex_);
    return completed_episode_;
  }

  uint64_t completion_generation() const
  {
    std::lock_guard lock(mutex_);
    return completion_generation_;
  }

 private:
  enum class Phase : uint8_t {
    Idle,
    Scheduled,
    Ready,
  };

  mutable std::mutex mutex_;
  Phase phase_ = Phase::Idle;
  uint64_t scheduled_episode_ = 0;
  RedrawTraceSnapshot scheduled_trace_snapshot_;
  bool update_requested_ = false;
  Completion completion_;
  bool completed_valid_ = false;
  uint64_t completed_episode_ = 0;
  uint64_t completion_generation_ = 0;
};

inline RedrawPresentBarrier redraw_present_barrier;

inline bool schedule_redraw_present_barrier(const uint64_t episode,
                                            RedrawTraceSnapshot trace_snapshot)
{
  return redraw_present_barrier.schedule(episode, std::move(trace_snapshot));
}

inline bool arrive_redraw_present_barrier(const uint64_t episode,
                                          RedrawPresentBarrier::Completion completion)
{
  const bool accepted = redraw_present_barrier.arrive(episode, std::move(completion));
  if (accepted) {
    request_redraw_retry();
  }
  return accepted;
}

inline bool filter_redraw_present_barrier_update(const uint64_t episode,
                                                 const bool requested)
{
  return redraw_present_barrier.filter_update(episode, requested);
}

inline bool redraw_present_barrier_is_scheduled()
{
  return redraw_present_barrier.is_scheduled();
}

inline bool redraw_present_barrier_is_ready()
{
  return redraw_present_barrier.is_ready();
}

inline uint64_t redraw_present_barrier_scheduled_episode()
{
  return redraw_present_barrier.scheduled_episode();
}

inline uint64_t redraw_present_barrier_ready_episode()
{
  return redraw_present_barrier.ready_episode();
}

inline RedrawTraceSnapshot redraw_present_barrier_ready_trace_snapshot()
{
  return redraw_present_barrier.ready_trace_snapshot();
}

inline bool complete_redraw_present_barrier(const uint64_t episode, const bool valid)
{
  const bool completed = redraw_present_barrier.complete(episode, valid);
  if (completed && !valid) {
    request_redraw_retry();
  }
  return completed;
}

inline bool cancel_redraw_present_barrier(const uint64_t episode)
{
  const bool canceled = redraw_present_barrier.cancel(episode);
  if (canceled) {
    request_redraw_retry();
  }
  return canceled;
}

inline bool cancel_superseded_redraw_present_barrier(const uint64_t current_episode)
{
  const bool canceled = redraw_present_barrier.cancel_superseded(current_episode);
  if (canceled) {
    request_redraw_retry();
  }
  return canceled;
}

inline uint64_t redraw_present_barrier_completed_episode()
{
  return redraw_present_barrier.completed_episode();
}

inline uint64_t redraw_present_barrier_completion_generation()
{
  return redraw_present_barrier.completion_generation();
}

/**
 * Bounded redraw recovery for one published window. Boot starts one burst even before a retry
 * signal so lazily created visible-region variants are discovered. A readiness signal requests an
 * immediate update; accepted readiness re-arms a completed burst, but neither accepted readiness
 * nor repeated incomplete draws reset an active burst's hard ceiling. Accepted ordinary input has
 * separate ownership: callbacks coalesce at the WM poll, then restart one complete bounded tail so
 * the final gesture frame cannot inherit only the last tick of an older burst. A newly committed
 * drawable extent starts its own bounded episode because updates issued while that extent was
 * pending could not draw into it. A drop is acknowledged at the ceiling without rearming, so
 * persistent failures consume at most one bounded episode while a later input or newly accepted
 * shader variant can still recover an otherwise idle region.
 */
inline constexpr uint32_t FIRST_PIXEL_SETTLE_TICKS = 180u;
inline constexpr uint32_t FIRST_PIXEL_SETTLE_INTERVAL = 12u;

inline bool redraw_recovery_tick(const uint64_t retry_generation,
                                 uint64_t &retry_generation_seen,
                                 const uint64_t episode_generation,
                                 uint64_t &episode_generation_seen,
                                 const uint64_t drop_generation,
                                 uint64_t &drop_generation_seen,
                                 const uint64_t input_retry_generation,
                                 uint64_t &input_retry_generation_seen,
                                 uint32_t &heartbeat)
{
  const bool readiness_published = retry_generation != retry_generation_seen;
  const bool episode_published = episode_generation != episode_generation_seen;
  const bool draw_dropped = drop_generation != drop_generation_seen;
  const bool input_published = input_retry_generation != input_retry_generation_seen;
  if (episode_published) {
    episode_generation_seen = episode_generation;
    heartbeat = 0;
  }
  if (input_published) {
    input_retry_generation_seen = input_retry_generation;
    const bool reopen_trace = heartbeat >= FIRST_PIXEL_SETTLE_TICKS;
    heartbeat = 0;
    if (reopen_trace && viewport_content_present_count() == 0u) {
      redraw_trace_begin(episode_generation);
    }
  }
  if (readiness_published) {
    retry_generation_seen = retry_generation;
    if (heartbeat >= FIRST_PIXEL_SETTLE_TICKS) {
      heartbeat = 0;
      if (viewport_content_present_count() == 0u) {
        /* A lazy browser pipeline may settle after the prior bounded trace ended. Reopen the
         * semantic snapshot for the already-supported recovery burst, but retire this path
         * permanently once a validated VIEW_3D present has published loader readiness. */
        redraw_trace_begin(episode_generation);
      }
    }
  }
  if (draw_dropped) {
    drop_generation_seen = drop_generation;
  }
  if (heartbeat >= FIRST_PIXEL_SETTLE_TICKS) {
    redraw_trace_finish(episode_generation);
    return false;
  }
  const bool request_update = episode_published || input_published || readiness_published ||
                              draw_dropped ||
                              (heartbeat % FIRST_PIXEL_SETTLE_INTERVAL) == 0u;
  heartbeat++;
  return request_update;
}

}  // namespace ghost_web
