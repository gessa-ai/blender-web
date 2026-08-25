/* SPDX-FileCopyrightText: 2026 blender-web contributors
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <cstdint>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

enum class CacheState { Ready, Pending, Failed };
enum class OperationState { Running, Pending, Failed, Finished, Cancelled };
enum class FinishType { Release, Enter, Space };

struct Sample {
  int x;
  int y;
  int pressure;

  bool operator==(const Sample &) const = default;
};

struct Context {
  int manager;
  int window;
  int screen;
  int area;
  int region;
  int region_view;
  int view3d;
  int depsgraph;
  int scene;
  int object;
  int evaluated_object;
  int grease_pencil;
  int layer;
  int frame;

  bool operator==(const Context &) const = default;
};

struct FinishEvent {
  FinishType type;
  int mouse_x;
  int mouse_y;
  bool has_next;
  bool has_prev;
  int custom;
  bool has_customdata;
  bool customdata_free;
};

[[noreturn]] void fail(const std::string &message)
{
  throw std::runtime_error(message);
}

void expect(const bool condition, const std::string &message)
{
  if (!condition) {
    fail(message);
  }
}

uint64_t mix(uint64_t hash, const uint64_t value)
{
  hash ^= value;
  hash *= UINT64_C(1099511628211);
  return hash;
}

class PaintDepthContinuation {
 public:
  static constexpr int max_ticks = 240;
  static constexpr int max_samples = 256;

  void begin(const bool needs_depth,
             const CacheState cache,
             const Sample sample,
             const Context &context)
  {
    expect(state_ == OperationState::Running && !initialized_, "begin state");
    if (!needs_depth) {
      initialize(sample);
      return;
    }
    if (cache == CacheState::Failed) {
      fail_closed();
      return;
    }
    if (cache == CacheState::Ready) {
      initialize(sample);
      return;
    }
    producing_context_ = context;
    start_sample_ = sample;
    request_owned_ = true;
    timer_owned_ = true;
    state_ = OperationState::Pending;
  }

  void extend(const Sample sample)
  {
    if (state_ == OperationState::Pending) {
      if (queued_samples_.size() >= max_samples) {
        fail_closed();
        return;
      }
      queued_samples_.push_back(sample);
      return;
    }
    if (state_ == OperationState::Running && initialized_) {
      applied_samples_.push_back(sample);
    }
  }

  void finish(const FinishEvent &event)
  {
    if (state_ == OperationState::Pending) {
      FinishEvent safe = event;
      safe.has_next = false;
      safe.has_prev = false;
      safe.custom = 0;
      safe.has_customdata = false;
      safe.customdata_free = false;
      deferred_finish_ = safe;
      return;
    }
    if (state_ == OperationState::Running && initialized_) {
      apply_finish(event);
    }
  }

  OperationState tick(const Context &context, const CacheState cache)
  {
    if (state_ != OperationState::Pending) {
      return state_;
    }
    if (context != producing_context_ || ++ticks_ > max_ticks || cache == CacheState::Failed) {
      fail_closed();
      return state_;
    }
    if (cache == CacheState::Pending) {
      return state_;
    }

    expect(start_sample_.has_value(), "pending start sample");
    const Sample start = *start_sample_;
    std::vector<Sample> queued = std::move(queued_samples_);
    start_sample_.reset();
    queued_samples_.clear();
    request_owned_ = false;
    timer_owned_ = false;
    ticks_ = 0;
    state_ = OperationState::Running;
    initialize(start);
    for (const Sample sample : queued) {
      extend(sample);
    }
    if (deferred_finish_) {
      const FinishEvent finish_event = *deferred_finish_;
      deferred_finish_.reset();
      apply_finish(finish_event);
    }
    return state_;
  }

  void cancel()
  {
    cleanup_pending();
    state_ = OperationState::Cancelled;
  }

  OperationState state() const
  {
    return state_;
  }
  bool initialized() const
  {
    return initialized_;
  }
  bool request_owned() const
  {
    return request_owned_;
  }
  bool timer_owned() const
  {
    return timer_owned_;
  }
  int line_end_count() const
  {
    return line_end_count_;
  }
  const std::vector<Sample> &applied_samples() const
  {
    return applied_samples_;
  }
  size_t queued_sample_count() const
  {
    return queued_samples_.size();
  }
  const std::optional<FinishEvent> &deferred_finish() const
  {
    return deferred_finish_;
  }

  uint64_t digest() const
  {
    uint64_t hash = UINT64_C(1469598103934665603);
    hash = mix(hash, static_cast<uint64_t>(state_));
    hash = mix(hash, initialized_);
    hash = mix(hash, request_owned_);
    hash = mix(hash, timer_owned_);
    hash = mix(hash, static_cast<uint64_t>(line_end_count_));
    for (const Sample &sample : applied_samples_) {
      hash = mix(hash, static_cast<uint32_t>(sample.x));
      hash = mix(hash, static_cast<uint32_t>(sample.y));
      hash = mix(hash, static_cast<uint32_t>(sample.pressure));
    }
    return hash;
  }

 private:
  void initialize(const Sample sample)
  {
    expect(!initialized_, "double initialization");
    initialized_ = true;
    applied_samples_.push_back(sample);
  }

  void apply_finish(const FinishEvent &event)
  {
    expect(initialized_, "finish before initialization");
    if (event.type == FinishType::Release) {
      ++line_end_count_;
    }
    state_ = OperationState::Finished;
  }

  void cleanup_pending()
  {
    request_owned_ = false;
    timer_owned_ = false;
    start_sample_.reset();
    queued_samples_.clear();
    deferred_finish_.reset();
  }

  void fail_closed()
  {
    cleanup_pending();
    state_ = OperationState::Failed;
  }

  OperationState state_ = OperationState::Running;
  Context producing_context_ = {};
  std::optional<Sample> start_sample_;
  std::vector<Sample> queued_samples_;
  std::optional<FinishEvent> deferred_finish_;
  std::vector<Sample> applied_samples_;
  int ticks_ = 0;
  int line_end_count_ = 0;
  bool request_owned_ = false;
  bool timer_owned_ = false;
  bool initialized_ = false;
};

const Context base_context = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14};
const Sample start_sample = {20, 30, 700};
const Sample second_sample = {21, 32, 710};
const Sample third_sample = {25, 38, 720};

uint64_t contract_native_immediate()
{
  PaintDepthContinuation surface;
  surface.begin(true, CacheState::Ready, start_sample, base_context);
  expect(surface.state() == OperationState::Running, "ready state");
  expect(surface.applied_samples() == std::vector<Sample>({start_sample}), "ready sample");

  PaintDepthContinuation view_plane;
  view_plane.begin(false, CacheState::Pending, second_sample, base_context);
  expect(view_plane.state() == OperationState::Running, "non-depth state");
  expect(!view_plane.request_owned(), "non-depth request");

  PaintDepthContinuation failed;
  failed.begin(true, CacheState::Failed, third_sample, base_context);
  expect(failed.state() == OperationState::Failed, "initial failure");
  return surface.digest() ^ view_plane.digest() ^ failed.digest();
}

uint64_t contract_pending_fifo_and_copy()
{
  PaintDepthContinuation continuation;
  Sample mutable_second = second_sample;
  continuation.begin(true, CacheState::Pending, start_sample, base_context);
  continuation.extend(mutable_second);
  mutable_second = {99, 99, 99};
  continuation.extend(third_sample);
  expect(continuation.tick(base_context, CacheState::Pending) == OperationState::Pending,
         "pending tick");
  expect(continuation.tick(base_context, CacheState::Ready) == OperationState::Running,
         "ready tick");
  expect(continuation.applied_samples() ==
             std::vector<Sample>({start_sample, second_sample, third_sample}),
         "fifo replay");
  expect(!continuation.request_owned() && !continuation.timer_owned(), "settled ownership");
  return continuation.digest();
}

uint64_t contract_terminal_replay()
{
  PaintDepthContinuation release;
  release.begin(true, CacheState::Pending, start_sample, base_context);
  const FinishEvent unsafe = {
      FinishType::Release, 40, 50, true, true, 17, true, true};
  release.finish(unsafe);
  expect(release.deferred_finish().has_value(), "deferred finish");
  const FinishEvent &safe = *release.deferred_finish();
  expect(!safe.has_next && !safe.has_prev && safe.custom == 0 && !safe.has_customdata &&
             !safe.customdata_free,
         "finish sanitization");
  expect(release.tick(base_context, CacheState::Ready) == OperationState::Finished,
         "release finish");
  expect(release.line_end_count() == 1, "release line end");

  PaintDepthContinuation enter;
  enter.begin(true, CacheState::Pending, second_sample, base_context);
  enter.finish({FinishType::Enter, 0, 0, false, false, 0, false, false});
  expect(enter.tick(base_context, CacheState::Ready) == OperationState::Finished,
         "enter finish");
  expect(enter.line_end_count() == 0, "enter does not release-line-end");
  return release.digest() ^ enter.digest();
}

uint64_t contract_context_guards()
{
  uint64_t digest = 0;
  for (const int lane : {0, 1, 2, 3}) {
    PaintDepthContinuation continuation;
    continuation.begin(true, CacheState::Pending, start_sample, base_context);
    Context drift = base_context;
    if (lane == 0) {
      drift.manager += 100;
    }
    else if (lane == 1) {
      drift.region += 100;
    }
    else if (lane == 2) {
      drift.scene += 100;
    }
    else {
      drift.layer += 100;
    }
    expect(continuation.tick(drift, CacheState::Ready) == OperationState::Failed,
           "context drift");
    expect(!continuation.initialized(), "drift mutation");
    digest ^= continuation.digest();
  }
  return digest;
}

uint64_t contract_failure_and_timeout()
{
  PaintDepthContinuation backend_failure;
  backend_failure.begin(true, CacheState::Pending, start_sample, base_context);
  backend_failure.extend(second_sample);
  expect(backend_failure.tick(base_context, CacheState::Failed) == OperationState::Failed,
         "backend failure");
  expect(backend_failure.queued_sample_count() == 0 && !backend_failure.request_owned(),
         "backend cleanup");

  PaintDepthContinuation timeout;
  timeout.begin(true, CacheState::Pending, start_sample, base_context);
  for (int i = 0; i < PaintDepthContinuation::max_ticks; ++i) {
    expect(timeout.tick(base_context, CacheState::Pending) == OperationState::Pending,
           "bounded pending tick");
  }
  expect(timeout.tick(base_context, CacheState::Pending) == OperationState::Failed,
         "timeout boundary");
  return backend_failure.digest() ^ timeout.digest();
}

uint64_t contract_queue_bound()
{
  PaintDepthContinuation accepted;
  accepted.begin(true, CacheState::Pending, start_sample, base_context);
  for (int i = 0; i < PaintDepthContinuation::max_samples; ++i) {
    accepted.extend({i, i + 1, 500 + i});
  }
  expect(accepted.state() == OperationState::Pending, "exact queue bound");
  expect(accepted.queued_sample_count() == PaintDepthContinuation::max_samples,
         "exact queue size");

  PaintDepthContinuation overflow;
  overflow.begin(true, CacheState::Pending, start_sample, base_context);
  for (int i = 0; i <= PaintDepthContinuation::max_samples; ++i) {
    overflow.extend({i, i, i});
  }
  expect(overflow.state() == OperationState::Failed, "queue overflow");
  expect(overflow.queued_sample_count() == 0 && !overflow.timer_owned(), "overflow cleanup");
  return accepted.digest() ^ overflow.digest();
}

uint64_t contract_external_cancel()
{
  PaintDepthContinuation continuation;
  continuation.begin(true, CacheState::Pending, start_sample, base_context);
  continuation.extend(second_sample);
  continuation.finish({FinishType::Space, 0, 0, true, true, 9, true, true});
  continuation.cancel();
  expect(continuation.state() == OperationState::Cancelled, "cancel state");
  expect(!continuation.initialized() && !continuation.request_owned() &&
             !continuation.timer_owned() && continuation.queued_sample_count() == 0 &&
             !continuation.deferred_finish(),
         "cancel cleanup");
  return continuation.digest();
}

uint64_t contract_exact_once()
{
  PaintDepthContinuation continuation;
  continuation.begin(true, CacheState::Pending, start_sample, base_context);
  continuation.extend(second_sample);
  expect(continuation.tick(base_context, CacheState::Ready) == OperationState::Running,
         "first settlement");
  expect(continuation.tick(base_context, CacheState::Ready) == OperationState::Running,
         "second settlement observation");
  expect(continuation.applied_samples() == std::vector<Sample>({start_sample, second_sample}),
         "exact once replay");
  return continuation.digest();
}

void emit(const char *name, const int cases, const uint64_t digest)
{
  std::cout << "CONTRACT " << name << " PASS cases=" << cases << " digest=" << digest << '\n';
}

}  // namespace

int main()
{
  try {
    emit("native_immediate", 3, contract_native_immediate());
    emit("pending_fifo_copy", 2, contract_pending_fifo_and_copy());
    emit("terminal_replay", 2, contract_terminal_replay());
    emit("context_guards", 4, contract_context_guards());
    emit("failure_timeout", 2, contract_failure_and_timeout());
    emit("queue_bound", 2, contract_queue_bound());
    emit("external_cancel", 1, contract_external_cancel());
    emit("exact_once", 2, contract_exact_once());
    std::cout << "M5_GREASE_PENCIL_DEPTH_CACHE_CONTRACT_PASS contracts=8 cases=18\n";
  }
  catch (const std::exception &error) {
    std::cerr << "M5_GREASE_PENCIL_DEPTH_CACHE_CONTRACT_FAIL " << error.what() << '\n';
    return 1;
  }
  return 0;
}
