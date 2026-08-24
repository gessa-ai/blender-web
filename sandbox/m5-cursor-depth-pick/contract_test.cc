/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <string>
#include <utility>
#include <vector>

#include "GPU_readback.hh"
#include "MEM_guardedalloc.h"
#include "gpu_readback_private.hh"

namespace {

void *aligned_allocate(const size_t size, size_t alignment)
{
  alignment = std::max(alignment, sizeof(void *));
  void *pointer = nullptr;
  if (posix_memalign(&pointer, alignment, std::max(size, size_t(1))) != 0) {
    std::abort();
  }
  return pointer;
}

void guarded_free(void *pointer, mem_guarded::internal::DestructorType)
{
  std::free(pointer);
}

void *guarded_allocate(const size_t size,
                       const size_t alignment,
                       const char *,
                       mem_guarded::internal::DestructorType)
{
  return aligned_allocate(size, alignment);
}

void *guarded_array_allocate(const size_t length,
                             const size_t element_size,
                             const size_t alignment,
                             const char *)
{
  if (element_size != 0 && length > std::numeric_limits<size_t>::max() / element_size) {
    return nullptr;
  }
  return aligned_allocate(length * element_size, alignment);
}

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "M5_CURSOR_DEPTH_PICK_CONTRACT_FAIL %s\n", message);
    return false;
  }
  return true;
}

bool near(const float actual, const float expected)
{
  return std::fabs(actual - expected) <= 1.0e-7f;
}

std::vector<unsigned char> depth_bytes(const std::vector<float> &depths)
{
  std::vector<unsigned char> bytes(depths.size() * sizeof(float));
  std::memcpy(bytes.data(), depths.data(), bytes.size());
  return bytes;
}

class ControlledReadback final : public blender::GPUReadback {
 private:
  blender::eGPUReadbackStatus status_ = blender::GPU_READBACK_PENDING;
  blender::eGPUReadbackError error_ = blender::GPU_READBACK_ERROR_NONE;
  std::vector<unsigned char> bytes_;
  std::string *lifetime_;

 public:
  ControlledReadback(std::vector<unsigned char> bytes, std::string *lifetime)
      : bytes_(std::move(bytes)), lifetime_(lifetime)
  {
  }

  ~ControlledReadback() override
  {
    lifetime_->push_back('R');
  }

  void ready()
  {
    status_ = blender::GPU_READBACK_READY;
    error_ = blender::GPU_READBACK_ERROR_NONE;
  }

  void fail()
  {
    status_ = blender::GPU_READBACK_FAILED;
    error_ = blender::GPU_READBACK_ERROR_MAP_FAILED;
  }

  blender::eGPUReadbackStatus status() override
  {
    return status_;
  }

  blender::eGPUReadbackError error() override
  {
    return error_;
  }

  size_t size() override
  {
    return bytes_.size();
  }

  bool consume(void *dst, const size_t dst_len) override
  {
    if (status_ != blender::GPU_READBACK_READY || dst == nullptr || dst_len < bytes_.size()) {
      return false;
    }
    std::memcpy(dst, bytes_.data(), bytes_.size());
    return true;
  }
};

struct Rect {
  int xmin;
  int xmax;
  int ymin;
  int ymax;
};

struct ContextKey {
  int region = 0;
  int view = 0;
  int width = 0;
  int height = 0;
  int transform = 0;
  int scene = 0;
  int window = 0;

  bool operator==(const ContextKey &) const = default;
};

enum class DepthState {
  Pending,
  Ready,
  Failed,
};

class DepthPickSession {
 private:
  blender::GPUReadback *readback_ = nullptr;
  ContextKey context_;
  Rect request_ = {};
  std::vector<Rect> samples_;
  std::vector<float> depths_;
  int mval_[2] = {0, 0};
  float depth_ = 1.0f;
  DepthState state_ = DepthState::Pending;

 public:
  DepthPickSession(blender::GPUReadback *readback,
                   const ContextKey context,
                   const Rect request,
                   std::vector<Rect> samples,
                   const int x,
                   const int y)
      : readback_(readback),
        context_(context),
        request_(request),
        samples_(std::move(samples))
  {
    mval_[0] = x;
    mval_[1] = y;
  }

  ~DepthPickSession()
  {
    cancel();
  }

  DepthState state()
  {
    if (state_ != DepthState::Pending) {
      return state_;
    }
    const blender::eGPUReadbackStatus status = blender::GPU_readback_status(readback_);
    if (status == blender::GPU_READBACK_PENDING) {
      return state_;
    }
    const int width = request_.xmax - request_.xmin;
    const int height = request_.ymax - request_.ymin;
    const size_t expected_size = size_t(width) * size_t(height) * sizeof(float);
    if (status != blender::GPU_READBACK_READY ||
        blender::GPU_readback_size(readback_) != expected_size)
    {
      blender::GPU_readback_cancel(readback_);
      state_ = DepthState::Failed;
      return state_;
    }

    depths_.resize(size_t(width) * size_t(height));
    if (!blender::GPU_readback_consume(readback_, depths_.data(), expected_size)) {
      blender::GPU_readback_cancel(readback_);
      depths_.clear();
      state_ = DepthState::Failed;
      return state_;
    }

    for (const Rect sample : samples_) {
      float nearest = 1.0f;
      for (int y = sample.ymin; y < sample.ymax; y++) {
        for (int x = sample.xmin; x < sample.xmax; x++) {
          const size_t index = size_t(y - request_.ymin) * size_t(width) +
                               size_t(x - request_.xmin);
          const float depth = depths_[index];
          if (depth > 0.0f && depth < nearest) {
            nearest = depth;
          }
        }
      }
      if (nearest < 1.0f) {
        depth_ = nearest;
        break;
      }
    }
    state_ = DepthState::Ready;
    return state_;
  }

  bool sample(const ContextKey context, float world[3])
  {
    if (state() != DepthState::Ready || context != context_) {
      if (state_ == DepthState::Ready) {
        state_ = DepthState::Failed;
        depths_.clear();
      }
      return false;
    }
    if (depth_ >= 1.0f) {
      return false;
    }
    world[0] = float(mval_[0]) + 0.5f;
    world[1] = float(mval_[1]) + 0.5f;
    world[2] = depth_;
    return true;
  }

  void cancel()
  {
    blender::GPU_readback_cancel(readback_);
  }
};

enum class ModalResult {
  Running,
  Finished,
  Cancelled,
};

class CursorContinuation {
 private:
  DepthPickSession *session_;
  ContextKey context_;
  int mval_[2];
  int orientation_;
  int tick_count_ = 0;
  int apply_count_ = 0;
  bool timer_ = false;
  bool fallback_ = false;
  bool superseded_ = false;
  int cursor_version_before_ = 0;
  int cursor_version_current_ = 0;
  float location_[3] = {0.0f, 0.0f, 0.0f};

  ModalResult apply()
  {
    if (cursor_version_current_ != cursor_version_before_) {
      timer_ = false;
      session_->cancel();
      return ModalResult::Cancelled;
    }
    float depth_location[3];
    const bool has_depth = session_->sample(context_, depth_location);
    if (!has_depth && session_->state() == DepthState::Failed) {
      timer_ = false;
      session_->cancel();
      return ModalResult::Cancelled;
    }
    if (has_depth) {
      std::memcpy(location_, depth_location, sizeof(location_));
    }
    else {
      fallback_ = true;
      location_[0] = -float(mval_[0]);
      location_[1] = -float(mval_[1]);
      location_[2] = 0.0f;
    }
    apply_count_++;
    timer_ = false;
    return ModalResult::Finished;
  }

 public:
  CursorContinuation(DepthPickSession *session,
                     const ContextKey context,
                     const int x,
                     const int y,
                     const int orientation,
                     const int cursor_version = 0)
      : session_(session),
        context_(context),
        mval_{x, y},
        orientation_(orientation),
        cursor_version_before_(cursor_version),
        cursor_version_current_(cursor_version)
  {
  }

  ModalResult begin()
  {
    const DepthState state = session_->state();
    if (state == DepthState::Ready) {
      return apply();
    }
    if (state == DepthState::Failed) {
      session_->cancel();
      return ModalResult::Cancelled;
    }
    timer_ = true;
    return ModalResult::Running;
  }

  ModalResult unrelated_event() const
  {
    return timer_ ? ModalResult::Running : ModalResult::Cancelled;
  }

  ModalResult tick()
  {
    constexpr int max_tick_count = 240;
    if (!timer_) {
      return ModalResult::Cancelled;
    }
    if (superseded_) {
      timer_ = false;
      session_->cancel();
      return ModalResult::Cancelled;
    }
    if (++tick_count_ > max_tick_count) {
      timer_ = false;
      session_->cancel();
      return ModalResult::Cancelled;
    }
    const DepthState state = session_->state();
    if (state == DepthState::Pending) {
      return ModalResult::Running;
    }
    if (state == DepthState::Failed) {
      timer_ = false;
      session_->cancel();
      return ModalResult::Cancelled;
    }
    return apply();
  }

  void set_context(const ContextKey context)
  {
    context_ = context;
  }

  void supersede()
  {
    superseded_ = true;
  }

  void set_cursor_version(const int cursor_version)
  {
    cursor_version_current_ = cursor_version;
  }

  int apply_count() const
  {
    return apply_count_;
  }

  int orientation() const
  {
    return orientation_;
  }

  bool fallback() const
  {
    return fallback_;
  }

  const float *location() const
  {
    return location_;
  }
};

constexpr ContextKey context_a = {11, 22, 800, 600, 33, 44, 55};
constexpr Rect request = {0, 8, 0, 8};
const std::vector<Rect> samples = {{4, 5, 4, 5}, {2, 6, 2, 6}, {0, 8, 0, 8}};

bool contract_margin_precedence()
{
  std::vector<float> depths(64, 1.0f);
  depths[4 * 8 + 4] = 0.75f;
  depths[0] = 0.10f;
  std::string lifetime;
  auto *readback = MEM_new<ControlledReadback>(__func__, depth_bytes(depths), &lifetime);
  readback->ready();
  DepthPickSession session(readback, context_a, request, samples, 4, 4);
  float world[3];
  const bool ok = require(session.state() == DepthState::Ready, "margin request not ready") &&
                  require(session.sample(context_a, world), "margin sample missing") &&
                  require(near(world[2], 0.75f), "outer hit defeated inner precedence") &&
                  require(lifetime == "R", "ready request not retired once");
  if (ok) {
    std::printf("CONTRACT margin_precedence PASS depth=0.750 lifetime=R\n");
  }
  return ok;
}

bool contract_pending_exact_replay()
{
  std::vector<float> depths(64, 1.0f);
  depths[4 * 8 + 4] = 0.625f;
  std::string lifetime;
  auto *readback = MEM_new<ControlledReadback>(__func__, depth_bytes(depths), &lifetime);
  DepthPickSession session(readback, context_a, request, samples, 31, 47);
  CursorContinuation cursor(&session, context_a, 31, 47, 3);
  const bool before = cursor.begin() == ModalResult::Running && cursor.apply_count() == 0 &&
                      cursor.unrelated_event() == ModalResult::Running;
  readback->ready();
  const ModalResult result = cursor.tick();
  const float *location = cursor.location();
  std::string superseded_lifetime;
  auto *superseded_readback = MEM_new<ControlledReadback>(
      __func__, depth_bytes(depths), &superseded_lifetime);
  DepthPickSession superseded_session(
      superseded_readback, context_a, request, samples, 7, 8);
  CursorContinuation superseded_cursor(&superseded_session, context_a, 7, 8, 1);
  const bool superseded_started = superseded_cursor.begin() == ModalResult::Running;
  superseded_cursor.supersede();
  const bool superseded_cancelled = superseded_cursor.tick() == ModalResult::Cancelled;

  const bool ok = require(before, "pending cursor mutated or swallowed unrelated event") &&
                  require(result == ModalResult::Finished, "ready replay did not finish") &&
                  require(cursor.apply_count() == 1, "ready replay count differs") &&
                  require(cursor.orientation() == 3, "orientation was not retained") &&
                  require(near(location[0], 31.5f) && near(location[1], 47.5f) &&
                              near(location[2], 0.625f),
                          "stored event/depth replay differs") &&
                  require(lifetime == "R", "pending request not retired once") &&
                  require(superseded_started && superseded_cancelled,
                          "superseded cursor was not cancelled") &&
                  require(superseded_cursor.apply_count() == 0,
                          "superseded cursor mutated state") &&
                  require(superseded_lifetime == "R",
                          "superseded request not retired once");
  if (ok) {
    std::printf(
        "CONTRACT pending_exact_replay PASS xy=31,47 orientation=3 applies=1 superseded=1\n");
  }
  return ok;
}

bool contract_native_immediate()
{
  std::vector<float> depths(64, 1.0f);
  depths[4 * 8 + 4] = 0.5f;
  std::string lifetime;
  auto *readback = MEM_new<ControlledReadback>(__func__, depth_bytes(depths), &lifetime);
  readback->ready();
  DepthPickSession session(readback, context_a, request, samples, 9, 13);
  CursorContinuation cursor(&session, context_a, 9, 13, 1);
  const bool ok = require(cursor.begin() == ModalResult::Finished,
                          "immediate backend entered modal state") &&
                  require(cursor.apply_count() == 1, "immediate apply count differs") &&
                  require(lifetime == "R", "immediate request not retired once");
  if (ok) {
    std::printf("CONTRACT native_immediate PASS applies=1 modal=0\n");
  }
  return ok;
}

bool contract_no_depth_fallback()
{
  std::vector<float> depths(64, 1.0f);
  std::string lifetime;
  auto *readback = MEM_new<ControlledReadback>(__func__, depth_bytes(depths), &lifetime);
  readback->ready();
  DepthPickSession session(readback, context_a, request, samples, 15, 27);
  CursorContinuation cursor(&session, context_a, 15, 27, 2);
  const bool ok = require(cursor.begin() == ModalResult::Finished,
                          "no-depth fallback did not finish") &&
                  require(cursor.fallback(), "no-depth result skipped fallback") &&
                  require(cursor.apply_count() == 1, "fallback apply count differs") &&
                  require(lifetime == "R", "no-depth request not retired once");
  if (ok) {
    std::printf("CONTRACT no_depth_fallback PASS xy=15,27 applies=1\n");
  }
  return ok;
}

bool contract_failure_and_timeout()
{
  std::vector<float> depths(64, 1.0f);
  std::string failure_lifetime;
  auto *failed = MEM_new<ControlledReadback>(
      __func__, depth_bytes(depths), &failure_lifetime);
  DepthPickSession failure_session(failed, context_a, request, samples, 1, 2);
  CursorContinuation failure_cursor(&failure_session, context_a, 1, 2, 0);
  const bool failure_started = failure_cursor.begin() == ModalResult::Running;
  failed->fail();
  const bool failure_cancelled = failure_cursor.tick() == ModalResult::Cancelled;

  std::string timeout_lifetime;
  auto *pending = MEM_new<ControlledReadback>(
      __func__, depth_bytes(depths), &timeout_lifetime);
  DepthPickSession timeout_session(pending, context_a, request, samples, 3, 4);
  CursorContinuation timeout_cursor(&timeout_session, context_a, 3, 4, 0);
  bool timeout_running = timeout_cursor.begin() == ModalResult::Running;
  for (int tick = 0; tick < 240; tick++) {
    timeout_running &= timeout_cursor.tick() == ModalResult::Running;
  }
  const bool timed_out = timeout_cursor.tick() == ModalResult::Cancelled;

  const bool ok = require(failure_started && failure_cancelled,
                          "terminal failure did not cancel") &&
                  require(failure_cursor.apply_count() == 0,
                          "terminal failure mutated cursor") &&
                  require(failure_lifetime == "R", "failed request not retired once") &&
                  require(timeout_running && timed_out, "bounded timeout differs") &&
                  require(timeout_cursor.apply_count() == 0, "timeout mutated cursor") &&
                  require(timeout_lifetime == "R", "timed-out request not retired once");
  if (ok) {
    std::printf("CONTRACT failure_timeout PASS failures=1 timeout_ticks=241 applies=0\n");
  }
  return ok;
}

bool contract_context_drift()
{
  std::vector<float> depths(64, 1.0f);
  depths[4 * 8 + 4] = 0.25f;
  std::string lifetime;
  auto *readback = MEM_new<ControlledReadback>(__func__, depth_bytes(depths), &lifetime);
  DepthPickSession session(readback, context_a, request, samples, 5, 6);
  CursorContinuation cursor(&session, context_a, 5, 6, 2);
  const bool started = cursor.begin() == ModalResult::Running;
  readback->ready();
  ContextKey changed = context_a;
  changed.transform++;
  cursor.set_context(changed);
  const bool view_cancelled = cursor.tick() == ModalResult::Cancelled;

  std::string scene_lifetime;
  auto *scene_readback = MEM_new<ControlledReadback>(
      __func__, depth_bytes(depths), &scene_lifetime);
  DepthPickSession scene_session(scene_readback, context_a, request, samples, 5, 6);
  CursorContinuation scene_cursor(&scene_session, context_a, 5, 6, 2);
  const bool scene_started = scene_cursor.begin() == ModalResult::Running;
  scene_readback->ready();
  ContextKey changed_scene = context_a;
  changed_scene.scene++;
  scene_cursor.set_context(changed_scene);
  const bool scene_cancelled = scene_cursor.tick() == ModalResult::Cancelled;

  std::string cursor_lifetime;
  auto *cursor_readback = MEM_new<ControlledReadback>(
      __func__, depth_bytes(depths), &cursor_lifetime);
  DepthPickSession cursor_session(cursor_readback, context_a, request, samples, 5, 6);
  CursorContinuation changed_cursor(&cursor_session, context_a, 5, 6, 2, 17);
  const bool cursor_started = changed_cursor.begin() == ModalResult::Running;
  cursor_readback->ready();
  changed_cursor.set_cursor_version(18);
  const bool cursor_cancelled = changed_cursor.tick() == ModalResult::Cancelled;

  const bool ok = require(started && view_cancelled, "transform drift did not fail closed") &&
                  require(cursor.apply_count() == 0, "transform drift mutated cursor") &&
                  require(lifetime == "R", "drifted request not retired once") &&
                  require(scene_started && scene_cancelled,
                          "scene context drift did not fail closed") &&
                  require(scene_cursor.apply_count() == 0,
                          "scene context drift mutated cursor") &&
                  require(scene_lifetime == "R",
                          "scene-drift request not retired once") &&
                  require(cursor_started && cursor_cancelled,
                          "late cursor mutation did not fail closed") &&
                  require(changed_cursor.apply_count() == 0,
                          "late cursor mutation was overwritten") &&
                  require(cursor_lifetime == "R",
                          "cursor-drift request not retired once");
  if (ok) {
    std::printf(
        "CONTRACT context_drift PASS view=1 scene=1 cursor=1 applies=0 lifetime=R\n");
  }
  return ok;
}

}  // namespace

void *(*MEM_new_array_uninitialized_aligned)(size_t, size_t, size_t, const char *) =
    guarded_array_allocate;

namespace mem_guarded::internal {
void *(*mem_mallocN_aligned_ex)(size_t, size_t, const char *, DestructorType) = guarded_allocate;
void (*mem_freeN_ex)(void *, DestructorType) = guarded_free;
}  // namespace mem_guarded::internal

int main()
{
  const bool ok = contract_margin_precedence() && contract_pending_exact_replay() &&
                  contract_native_immediate() && contract_no_depth_fallback() &&
                  contract_failure_and_timeout() && contract_context_drift();
  if (!ok) {
    return 1;
  }
  std::printf("M5_CURSOR_DEPTH_PICK_CONTRACT_PASS contracts=6 cases=12\n");
  return 0;
}
