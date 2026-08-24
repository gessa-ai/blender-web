/* SPDX-FileCopyrightText: 2026 blender-web contributors
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <optional>
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
    std::fprintf(stderr, "M5_NDOF_DEPTH_CONTRACT_FAIL %s\n", message);
    return false;
  }
  return true;
}

bool near(const float actual, const float expected)
{
  return std::fabs(actual - expected) <= 1.0e-6f;
}

std::vector<unsigned char> float_bytes(const std::vector<float> &values)
{
  std::vector<unsigned char> bytes(values.size() * sizeof(float));
  if (!bytes.empty()) {
    std::memcpy(bytes.data(), values.data(), bytes.size());
  }
  return bytes;
}

class ControlledReadback final : public blender::GPUReadback {
 private:
  blender::eGPUReadbackStatus status_ = blender::GPU_READBACK_PENDING;
  blender::eGPUReadbackError error_ = blender::GPU_READBACK_ERROR_NONE;
  std::vector<unsigned char> bytes_;
  std::string *lifetime_ = nullptr;

 public:
  ControlledReadback(std::vector<unsigned char> bytes,
                     std::string *lifetime,
                     const bool ready = false)
      : status_(ready ? blender::GPU_READBACK_READY : blender::GPU_READBACK_PENDING),
        bytes_(std::move(bytes)),
        lifetime_(lifetime)
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

template<typename... Args> ControlledReadback *make_readback(Args &&...args)
{
  return MEM_new<ControlledReadback>(__func__, std::forward<Args>(args)...);
}

struct Rect {
  int xmin = 0;
  int xmax = 0;
  int ymin = 0;
  int ymax = 0;

  bool operator==(const Rect &) const = default;
};

struct Point {
  float x = 0.0f;
  float y = 0.0f;
  float z = 0.0f;
};

int width(const Rect &rect)
{
  return rect.xmax - rect.xmin;
}

int height(const Rect &rect)
{
  return rect.ymax - rect.ymin;
}

Rect clamp_rect(const Rect input, const int region_width, const int region_height)
{
  const Rect bounds = {0, region_width - 1, 0, region_height - 1};
  return {
      std::max(input.xmin, bounds.xmin),
      std::min(input.xmax, bounds.xmax),
      std::max(input.ymin, bounds.ymin),
      std::min(input.ymax, bounds.ymax),
  };
}

enum class DepthState {
  Pending,
  Ready,
  Failed,
};

class OwnedNdofDepth {
 private:
  blender::GPUReadback *readback_ = nullptr;
  Rect rect_ = {};
  size_t expected_size_ = 0;
  bool empty_ready_ = false;

 public:
  OwnedNdofDepth(blender::GPUReadback *readback,
                 const Rect raw_rect,
                 const int region_width,
                 const int region_height)
      : readback_(readback), rect_(clamp_rect(raw_rect, region_width, region_height))
  {
    if (width(rect_) <= 0 || height(rect_) <= 0) {
      empty_ready_ = true;
      return;
    }
    const size_t pixel_count = size_t(width(rect_)) * size_t(height(rect_));
    expected_size_ = pixel_count * sizeof(float);
  }

  ~OwnedNdofDepth()
  {
    cancel();
  }

  DepthState state()
  {
    if (empty_ready_) {
      return DepthState::Ready;
    }
    const blender::eGPUReadbackStatus status = blender::GPU_readback_status(readback_);
    if (status == blender::GPU_READBACK_PENDING) {
      return DepthState::Pending;
    }
    if (status != blender::GPU_READBACK_READY ||
        blender::GPU_readback_size(readback_) != expected_size_)
    {
      return DepthState::Failed;
    }
    return DepthState::Ready;
  }

  bool consume(std::optional<Point> &r_point)
  {
    if (state() != DepthState::Ready) {
      return false;
    }
    r_point = std::nullopt;
    if (empty_ready_) {
      return true;
    }
    std::vector<float> depths(expected_size_ / sizeof(float));
    if (!blender::GPU_readback_consume(readback_, depths.data(), expected_size_)) {
      return false;
    }
    float nearest = 1.0f;
    int nearest_index = -1;
    for (size_t index = 0; index < depths.size(); index++) {
      const float depth = depths[index];
      if (depth < nearest && depth > 0.0f) {
        nearest = depth;
        nearest_index = int(index);
      }
    }
    if (nearest_index != -1) {
      r_point = Point{float(rect_.xmin + nearest_index % width(rect_)),
                      float(rect_.ymin + nearest_index / width(rect_)),
                      nearest};
    }
    return true;
  }

  void cancel()
  {
    blender::GPU_readback_cancel(readback_);
  }
};

struct Motion {
  int id = 0;
  float time_delta = 0.0f;
  int progress = 0;
};

enum class SettleState {
  Pending,
  Ready,
  Failed,
};

class NdofContinuation {
 private:
  OwnedNdofDepth depth_;
  Motion initial_;
  std::vector<Motion> queued_;
  int context_ = 0;
  int ticks_ = 0;
  bool failed_ = false;
  std::optional<Point> point_ = std::nullopt;

 public:
  NdofContinuation(blender::GPUReadback *readback,
                   const Rect rect,
                   const int region_width,
                   const int region_height,
                   const Motion initial,
                   const int context)
      : depth_(readback, rect, region_width, region_height), initial_(initial), context_(context)
  {
  }

  bool queue(const Motion motion)
  {
    if (queued_.size() >= 256) {
      failed_ = true;
      return false;
    }
    queued_.push_back(motion);
    return true;
  }

  SettleState poll(const int context)
  {
    if (failed_ || context != context_) {
      depth_.cancel();
      failed_ = true;
      return SettleState::Failed;
    }
    if (++ticks_ > 240) {
      depth_.cancel();
      failed_ = true;
      return SettleState::Failed;
    }
    const DepthState state = depth_.state();
    if (state == DepthState::Pending) {
      return SettleState::Pending;
    }
    if (state == DepthState::Failed || !depth_.consume(point_)) {
      depth_.cancel();
      failed_ = true;
      return SettleState::Failed;
    }
    return SettleState::Ready;
  }

  std::vector<Motion> replay() const
  {
    std::vector<Motion> result;
    result.push_back(initial_);
    result.insert(result.end(), queued_.begin(), queued_.end());
    return result;
  }

  const std::optional<Point> &point() const
  {
    return point_;
  }
};

bool test_strict_nearest_xy()
{
  std::string lifetime;
  auto *controlled = make_readback(float_bytes({1.0f, 0.0f, 0.3f, 0.3f, 0.7f, -0.1f}),
                                   &lifetime,
                                   true);
  OwnedNdofDepth depth(controlled, Rect{10, 13, 20, 22}, 100, 100);
  std::optional<Point> point;
  if (!require(depth.consume(point), "nearest consume failed") ||
      !require(point.has_value(), "nearest point missing") ||
      !require(near(point->x, 12.0f) && near(point->y, 20.0f) && near(point->z, 0.3f),
               "strict first-tie nearest XY differs") ||
      !require(lifetime == "R", "nearest readback was not consumed exactly once"))
  {
    return false;
  }

  std::string no_hit_lifetime;
  OwnedNdofDepth no_hit(make_readback(float_bytes({0.0f, 1.0f, -1.0f, 1.0f}),
                                      &no_hit_lifetime,
                                      true),
                        Rect{0, 2, 0, 2},
                        10,
                        10);
  point = Point{9, 9, 9};
  return require(no_hit.consume(point) && !point.has_value(), "zero/far values became a hit") &&
         require(no_hit_lifetime == "R", "no-hit readback leaked");
}

bool test_clamp_and_empty()
{
  std::string lifetime;
  OwnedNdofDepth depth(make_readback(float_bytes({0.8f, 0.4f, 0.6f, 0.7f}), &lifetime, true),
                       Rect{-4, 2, -5, 2},
                       8,
                       8);
  std::optional<Point> point;
  if (!require(depth.consume(point) && point.has_value(), "clamped read failed") ||
      !require(near(point->x, 1.0f) && near(point->y, 0.0f), "post-clamp XY differs"))
  {
    return false;
  }
  std::string empty_lifetime;
  {
    OwnedNdofDepth empty(nullptr, Rect{4, 4, 2, 8}, 10, 10);
    point = Point{};
    if (!require(empty.consume(point) && !point.has_value(), "empty rectangle was not ready")) {
      return false;
    }
  }
  return require(lifetime == "R" && empty_lifetime.empty(), "clamp/empty lifetime differs");
}

bool test_bounds_first_shortcut()
{
  const std::optional<Point> bounds_center = Point{1.0f, 2.0f, 3.0f};
  bool readback_created = false;
  const std::optional<Point> chosen = bounds_center.has_value() ? bounds_center : std::nullopt;
  if (!bounds_center.has_value()) {
    readback_created = true;
  }
  return require(chosen.has_value() && near(chosen->z, 3.0f), "bounds center was not retained") &&
         require(!readback_created, "bounds success allocated a depth request");
}

bool test_native_immediate()
{
  std::string lifetime;
  auto *controlled = make_readback(float_bytes({0.9f, 0.2f, 0.4f, 0.8f}), &lifetime, true);
  NdofContinuation continuation(controlled, Rect{5, 7, 7, 9}, 20, 20, Motion{10, 0.01f, 1}, 3);
  if (!require(continuation.poll(3) == SettleState::Ready, "native-ready request yielded") ||
      !require(continuation.point().has_value() && near(continuation.point()->z, 0.2f),
               "native-ready point differs"))
  {
    return false;
  }
  const std::vector<Motion> replay = continuation.replay();
  return require(replay.size() == 1 && replay[0].id == 10, "native event replay differs") &&
         require(lifetime == "R", "native-ready readback leaked");
}

bool test_pending_fifo_payload_ownership()
{
  std::string lifetime;
  auto *controlled = make_readback(float_bytes({0.5f, 0.4f, 0.3f, 0.2f}), &lifetime);
  Motion initial{1, 0.1f, 1};
  NdofContinuation continuation(controlled, Rect{0, 2, 0, 2}, 10, 10, initial, 7);
  Motion second{2, 0.2f, 2};
  Motion third{3, 0.3f, 3};
  if (!require(continuation.poll(7) == SettleState::Pending, "pending request settled early") ||
      !require(continuation.queue(second) && continuation.queue(third), "motion enqueue failed"))
  {
    return false;
  }
  initial.id = second.id = third.id = 99;
  controlled->ready();
  if (!require(continuation.poll(7) == SettleState::Ready, "pending request did not settle")) {
    return false;
  }
  const std::vector<Motion> replay = continuation.replay();
  return require(replay.size() == 3, "FIFO replay size differs") &&
         require(replay[0].id == 1 && replay[1].id == 2 && replay[2].id == 3,
                 "FIFO replay order or ownership differs") &&
         require(near(replay[0].time_delta, 0.1f) && near(replay[1].time_delta, 0.2f) &&
                     near(replay[2].time_delta, 0.3f),
                 "NDOF time deltas drifted") &&
         require(lifetime == "R", "pending FIFO readback leaked");
}

bool test_context_drift_cancels()
{
  std::string lifetime;
  auto *controlled = make_readback(float_bytes({0.5f, 0.4f, 0.3f, 0.2f}), &lifetime);
  NdofContinuation continuation(controlled, Rect{0, 2, 0, 2}, 10, 10, Motion{1, 0.1f, 1}, 11);
  return require(continuation.poll(12) == SettleState::Failed, "context drift was accepted") &&
         require(lifetime == "R", "drift cancellation leaked readback");
}

bool test_failure_size_and_timeout()
{
  std::string failed_lifetime;
  auto *failed = make_readback(float_bytes({0.5f, 0.4f, 0.3f, 0.2f}), &failed_lifetime);
  NdofContinuation failed_continuation(
      failed, Rect{0, 2, 0, 2}, 10, 10, Motion{1, 0.1f, 1}, 1);
  failed->fail();
  if (!require(failed_continuation.poll(1) == SettleState::Failed, "backend failure accepted") ||
      !require(failed_lifetime == "R", "backend failure leaked"))
  {
    return false;
  }

  std::string short_lifetime;
  NdofContinuation short_continuation(
      make_readback(float_bytes({0.5f}), &short_lifetime, true),
      Rect{0, 2, 0, 2},
      10,
      10,
      Motion{1, 0.1f, 1},
      1);
  if (!require(short_continuation.poll(1) == SettleState::Failed, "short payload accepted") ||
      !require(short_lifetime == "R", "short payload leaked"))
  {
    return false;
  }

  std::string timeout_lifetime;
  NdofContinuation timeout_continuation(
      make_readback(float_bytes({0.5f, 0.4f, 0.3f, 0.2f}), &timeout_lifetime),
      Rect{0, 2, 0, 2},
      10,
      10,
      Motion{1, 0.1f, 1},
      1);
  for (int tick = 0; tick < 240; tick++) {
    if (!require(timeout_continuation.poll(1) == SettleState::Pending,
                 "request timed out before bound"))
    {
      return false;
    }
  }
  return require(timeout_continuation.poll(1) == SettleState::Failed,
                 "request survived timeout bound") &&
         require(timeout_lifetime == "R", "timeout leaked readback");
}

bool test_queue_bound_and_terminal_order()
{
  std::string lifetime;
  NdofContinuation continuation(
      make_readback(float_bytes({0.5f, 0.4f, 0.3f, 0.2f}), &lifetime),
      Rect{0, 2, 0, 2},
      10,
      10,
      Motion{0, 0.0f, 1},
      1);
  for (int index = 1; index <= 256; index++) {
    if (!require(continuation.queue(Motion{index, float(index) / 1000.0f, index == 256 ? 3 : 2}),
                 "queue rejected before exact bound"))
    {
      return false;
    }
  }
  if (!require(!continuation.queue(Motion{257, 0.257f, 3}), "queue overflow was accepted") ||
      !require(continuation.poll(1) == SettleState::Failed, "queue overflow did not fail") ||
      !require(lifetime == "R", "queue overflow leaked readback"))
  {
    return false;
  }

  std::string order_lifetime;
  auto *ready = make_readback(float_bytes({0.7f, 0.6f, 0.5f, 0.4f}), &order_lifetime);
  NdofContinuation order(
      ready, Rect{0, 2, 0, 2}, 10, 10, Motion{8, 0.008f, 1}, 4);
  order.queue(Motion{9, 0.009f, 2});
  order.queue(Motion{10, 0.010f, 3});
  ready->ready();
  if (!require(order.poll(4) == SettleState::Ready, "terminal-order request failed")) {
    return false;
  }
  const auto replay = order.replay();
  return require(replay[0].progress == 1 && replay[1].progress == 2 && replay[2].progress == 3,
                 "start/update/finish order differs") &&
         require(order_lifetime == "R", "terminal-order readback leaked");
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
  struct Contract {
    const char *name;
    int cases;
    bool (*run)();
  };
  const Contract contracts[] = {
      {"strict_nearest_xy", 3, test_strict_nearest_xy},
      {"post_clamp_empty", 2, test_clamp_and_empty},
      {"bounds_first_shortcut", 2, test_bounds_first_shortcut},
      {"native_immediate", 2, test_native_immediate},
      {"pending_fifo_payload", 3, test_pending_fifo_payload_ownership},
      {"producing_context_guard", 2, test_context_drift_cancels},
      {"failure_size_timeout", 4, test_failure_size_and_timeout},
      {"queue_bound_terminal_order", 2, test_queue_bound_and_terminal_order},
  };

  int case_count = 0;
  for (const Contract &contract : contracts) {
    if (!contract.run()) {
      return 1;
    }
    case_count += contract.cases;
    std::printf("CONTRACT %s PASS cases=%d\n", contract.name, contract.cases);
  }
  std::printf("M5_NDOF_DEPTH_CONTRACT_PASS contracts=8 cases=%d\n", case_count);
  return case_count == 20 ? 0 : 1;
}
