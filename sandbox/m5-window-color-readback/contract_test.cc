/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <algorithm>
#include <cmath>
#include <cstdint>
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
    std::fprintf(stderr, "M5_WINDOW_COLOR_READBACK_CONTRACT_FAIL %s\n", message);
    return false;
  }
  return true;
}

bool near(const float actual, const float expected)
{
  return std::fabs(actual - expected) <= 1.0e-7f;
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

enum class SnapshotState {
  Invalid,
  Pending,
  Ready,
  Failed,
};

class WindowSnapshotSession {
 private:
  blender::GPUReadback *readback_ = nullptr;
  std::vector<unsigned char> pixels_;
  int width_ = 0;
  int height_ = 0;
  int window_key_ = 0;
  SnapshotState state_ = SnapshotState::Invalid;
  bool owner_live_ = false;
  std::string *lifetime_ = nullptr;

  void release_owner()
  {
    if (owner_live_) {
      owner_live_ = false;
      lifetime_->push_back('O');
    }
  }

 public:
  ~WindowSnapshotSession()
  {
    cancel();
  }

  void begin(blender::GPUReadback *readback,
             const int width,
             const int height,
             const int window_key,
             std::string *lifetime)
  {
    cancel();
    readback_ = readback;
    width_ = width;
    height_ = height;
    window_key_ = window_key;
    lifetime_ = lifetime;
    owner_live_ = true;
    state_ = SnapshotState::Pending;
  }

  SnapshotState state()
  {
    if (state_ != SnapshotState::Pending) {
      return state_;
    }
    const blender::eGPUReadbackStatus status = blender::GPU_readback_status(readback_);
    if (status == blender::GPU_READBACK_PENDING) {
      return state_;
    }
    const size_t expected_size = size_t(width_) * size_t(height_) * 4;
    if (status != blender::GPU_READBACK_READY ||
        blender::GPU_readback_size(readback_) != expected_size)
    {
      release_owner();
      blender::GPU_readback_cancel(readback_);
      state_ = SnapshotState::Failed;
      return state_;
    }

    release_owner();
    pixels_.resize(expected_size);
    if (!blender::GPU_readback_consume(readback_, pixels_.data(), pixels_.size())) {
      pixels_.clear();
      state_ = SnapshotState::Failed;
      return state_;
    }
    state_ = SnapshotState::Ready;
    return state_;
  }

  bool sample(const int x, const int y, float color[3])
  {
    if (color == nullptr || state() != SnapshotState::Ready || x < 0 || y < 0 || x >= width_ ||
        y >= height_)
    {
      return false;
    }
    const unsigned char *pixel = pixels_.data() +
                                 (size_t(y) * size_t(width_) + size_t(x)) * 4;
    color[0] = float(pixel[0]) / 255.0f;
    color[1] = float(pixel[1]) / 255.0f;
    color[2] = float(pixel[2]) / 255.0f;
    return true;
  }

  void cancel()
  {
    blender::GPU_readback_cancel(readback_);
    release_owner();
    pixels_.clear();
    width_ = 0;
    height_ = 0;
    window_key_ = 0;
    state_ = SnapshotState::Invalid;
  }

  int window_key() const
  {
    return window_key_;
  }
};

enum class ModalResult {
  Running,
  Finished,
  Cancelled,
};

class ModalConsumer {
 private:
  WindowSnapshotSession *session_;
  bool timer_ = false;
  int tick_count_ = 0;
  int completions_ = 0;
  int x_ = 0;
  int y_ = 0;

 public:
  explicit ModalConsumer(WindowSnapshotSession *session) : session_(session) {}

  ModalResult confirm(const int x, const int y)
  {
    float color[3];
    if (session_->sample(x, y, color)) {
      completions_++;
      timer_ = false;
      return ModalResult::Finished;
    }
    if (session_->state() == SnapshotState::Pending) {
      x_ = x;
      y_ = y;
      tick_count_ = 0;
      timer_ = true;
      return ModalResult::Running;
    }
    timer_ = false;
    return ModalResult::Cancelled;
  }

  ModalResult tick()
  {
    constexpr int max_tick_count = 240;
    if (!timer_) {
      return ModalResult::Cancelled;
    }
    if (++tick_count_ > max_tick_count) {
      timer_ = false;
      session_->cancel();
      return ModalResult::Cancelled;
    }
    if (session_->state() == SnapshotState::Pending) {
      return ModalResult::Running;
    }
    return confirm(x_, y_);
  }

  int completions() const
  {
    return completions_;
  }
};

const std::vector<unsigned char> pixels_2x2 = {
    0,   64,  128, 255,
    255, 128, 64,  255,
    10,  20,  30,  255,
    40,  50,  60,  255,
};

bool contract_native_immediate()
{
  std::string lifetime;
  auto *readback = new ControlledReadback(pixels_2x2, &lifetime);
  readback->ready();
  WindowSnapshotSession session;
  session.begin(readback, 2, 2, 7, &lifetime);
  float color[3];
  const bool ok = require(session.sample(1, 0, color), "native immediate sample") &&
                  require(near(color[0], 1.0f) && near(color[1], 128.0f / 255.0f) &&
                              near(color[2], 64.0f / 255.0f),
                          "native exact decode") &&
                  require(lifetime == "OR", "native terminal ownership");
  if (ok) {
    std::puts("CONTRACT native_immediate PASS cases=2");
  }
  return ok;
}

bool contract_pending_shared_snapshot()
{
  std::string lifetime;
  auto *readback = new ControlledReadback(pixels_2x2, &lifetime);
  WindowSnapshotSession session;
  session.begin(readback, 2, 2, 11, &lifetime);
  float color_a[3];
  float color_b[3];
  const bool pending = session.state() == SnapshotState::Pending &&
                       !session.sample(0, 0, color_a) && lifetime.empty();
  readback->ready();
  const bool shared = session.sample(0, 1, color_a) && session.sample(1, 1, color_b) &&
                      near(color_a[0], 10.0f / 255.0f) &&
                      near(color_b[2], 60.0f / 255.0f) && lifetime == "OR";
  const bool ok = require(pending, "pending snapshot") &&
                  require(shared, "ready snapshot reused");
  if (ok) {
    std::puts("CONTRACT pending_shared_snapshot PASS cases=2");
  }
  return ok;
}

bool contract_three_modal_consumers()
{
  bool ok = true;
  for (int consumer = 0; consumer < 3; consumer++) {
    std::string lifetime;
    auto *readback = new ControlledReadback(pixels_2x2, &lifetime);
    WindowSnapshotSession session;
    session.begin(readback, 2, 2, consumer + 20, &lifetime);
    ModalConsumer modal(&session);
    const bool started = modal.confirm(consumer % 2, consumer / 2) == ModalResult::Running;
    readback->ready();
    const bool finished = modal.tick() == ModalResult::Finished && modal.completions() == 1 &&
                          lifetime == "OR";
    ok &= require(started && finished, "modal consumer resume");
  }
  if (ok) {
    std::puts("CONTRACT three_modal_consumers PASS cases=3");
  }
  return ok;
}

bool contract_exact_failure_retry()
{
  std::string failed_lifetime;
  auto *short_readback = new ControlledReadback({1, 2, 3}, &failed_lifetime);
  short_readback->ready();
  WindowSnapshotSession session;
  session.begin(short_readback, 1, 1, 31, &failed_lifetime);
  const bool failed = session.state() == SnapshotState::Failed && failed_lifetime == "OR";

  std::string retry_lifetime;
  auto *retry = new ControlledReadback({4, 5, 6, 255}, &retry_lifetime);
  retry->ready();
  session.begin(retry, 1, 1, 31, &retry_lifetime);
  float color[3];
  const bool recovered = session.sample(0, 0, color) && near(color[1], 5.0f / 255.0f) &&
                         retry_lifetime == "OR";
  const bool ok = require(failed, "exact size failure") && require(recovered, "retry ready");
  if (ok) {
    std::puts("CONTRACT exact_failure_retry PASS cases=2");
  }
  return ok;
}

bool contract_replace_cancel()
{
  std::string first_lifetime;
  auto *first = new ControlledReadback({1, 2, 3, 4}, &first_lifetime);
  WindowSnapshotSession session;
  session.begin(first, 1, 1, 41, &first_lifetime);

  std::string second_lifetime;
  auto *second = new ControlledReadback({5, 6, 7, 8}, &second_lifetime);
  session.begin(second, 1, 1, 42, &second_lifetime);
  const bool replaced = first_lifetime == "RO" && session.window_key() == 42;
  session.cancel();
  const bool cancelled = second_lifetime == "RO" && session.state() == SnapshotState::Invalid;
  const bool ok = require(replaced, "window replacement order") &&
                  require(cancelled, "pending cancellation order");
  if (ok) {
    std::puts("CONTRACT replace_cancel PASS cases=2");
  }
  return ok;
}

bool contract_bounded_timeout()
{
  std::string lifetime;
  auto *readback = new ControlledReadback({1, 2, 3, 4}, &lifetime);
  WindowSnapshotSession session;
  session.begin(readback, 1, 1, 51, &lifetime);
  ModalConsumer modal(&session);
  const bool started = modal.confirm(0, 0) == ModalResult::Running;
  bool bounded = true;
  for (int tick = 0; tick < 240; tick++) {
    bounded &= modal.tick() == ModalResult::Running;
  }
  const bool timed_out = modal.tick() == ModalResult::Cancelled && lifetime == "RO";
  const bool ok = require(started && bounded, "bounded pending range") &&
                  require(timed_out, "timeout cancellation");
  if (ok) {
    std::puts("CONTRACT bounded_timeout PASS cases=2");
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
  const bool ok = contract_native_immediate() && contract_pending_shared_snapshot() &&
                  contract_three_modal_consumers() && contract_exact_failure_retry() &&
                  contract_replace_cancel() && contract_bounded_timeout();
  if (!ok) {
    return 1;
  }
  std::puts("M5_WINDOW_COLOR_READBACK_CONTRACT_PASS contracts=6 cases=13");
  return 0;
}
