/* SPDX-FileCopyrightText: 2026 blender-web contributors
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
    std::fprintf(stderr, "M5_NAVIGATION_DEPTH_CONTRACT_FAIL %s\n", message);
    return false;
  }
  return true;
}

bool near(const float actual, const float expected)
{
  return std::fabs(actual - expected) <= 1.0e-7f;
}

std::vector<unsigned char> depth_bytes(const float depth)
{
  std::vector<unsigned char> bytes(sizeof(depth));
  std::memcpy(bytes.data(), &depth, sizeof(depth));
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

struct ViewSnapshot {
  int window = 1;
  int screen = 2;
  int area = 3;
  int region = 4;
  float ofs[3] = {-1.0f, -2.0f, -3.0f};
  float quat[4] = {1.0f, 0.0f, 0.0f, 0.0f};
  float dist = 10.0f;
  int perspective = 1;

  bool operator==(const ViewSnapshot &) const = default;
};

struct NavigationState {
  ViewSnapshot view;
  float pivot[3] = {0.0f, 0.0f, 0.0f};
  bool initialized = false;

  bool operator==(const NavigationState &) const = default;
};

enum class DepthState {
  Pending,
  Ready,
  Failed,
};

class OwnedDepthRequest {
 private:
  blender::GPUReadback *readback_ = nullptr;
  ViewSnapshot producing_view_;
  int mval_[2] = {0, 0};
  float depth_ = 1.0f;
  DepthState state_ = DepthState::Pending;

 public:
  OwnedDepthRequest(blender::GPUReadback *readback,
                    const ViewSnapshot producing_view,
                    const int x,
                    const int y)
      : readback_(readback), producing_view_(producing_view), mval_{x, y}
  {
  }

  ~OwnedDepthRequest()
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
    if (status != blender::GPU_READBACK_READY ||
        blender::GPU_readback_size(readback_) != sizeof(depth_))
    {
      blender::GPU_readback_cancel(readback_);
      state_ = DepthState::Failed;
      return state_;
    }
    if (!blender::GPU_readback_consume(readback_, &depth_, sizeof(depth_))) {
      blender::GPU_readback_cancel(readback_);
      state_ = DepthState::Failed;
      return state_;
    }
    state_ = DepthState::Ready;
    return state_;
  }

  bool sample(const ViewSnapshot &current_view, float world[3])
  {
    if (state() != DepthState::Ready || current_view != producing_view_) {
      if (state_ == DepthState::Ready) {
        state_ = DepthState::Failed;
      }
      return false;
    }
    if (!(depth_ > 0.0f && depth_ < 1.0f)) {
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

enum class EventType {
  Motion,
  Release,
  Other,
  Escape,
};

struct Event {
  EventType type = EventType::Other;
  int x = 0;
  int y = 0;
  bool custom_data = false;
};

enum class ModalResult {
  Running,
  RunningPass,
  Finished,
  Cancelled,
};

class NavigationContinuation {
 private:
  OwnedDepthRequest *request_;
  NavigationState &state_;
  NavigationState backup_;
  ViewSnapshot producing_view_;
  Event invoke_event_;
  Event queued_event_;
  float fallback_[3];
  int tick_count_ = 0;
  int prelude_count_ = 0;
  int backup_count_ = 0;
  int initialize_count_ = 0;
  int replay_count_ = 0;
  int restore_count_ = 0;
  bool timer_ = false;
  bool queued_event_valid_ = false;
  bool fallback_used_ = false;

  bool context_matches(const ViewSnapshot &current_view) const
  {
    return current_view == producing_view_;
  }

  ModalResult cancel()
  {
    request_->cancel();
    timer_ = false;
    state_ = backup_;
    restore_count_++;
    return ModalResult::Cancelled;
  }

  ModalResult initialize(const float pivot[3])
  {
    state_.pivot[0] = pivot[0];
    state_.pivot[1] = pivot[1];
    state_.pivot[2] = pivot[2];
    state_.initialized = true;
    initialize_count_++;
    timer_ = false;
    if (queued_event_valid_) {
      replay_count_++;
      return queued_event_.type == EventType::Release ? ModalResult::Finished :
                                                        ModalResult::Running;
    }
    return ModalResult::Running;
  }

  ModalResult settle(const ViewSnapshot &current_view, const bool immediate_failure_fallback)
  {
    if (!context_matches(current_view)) {
      return cancel();
    }
    float pivot[3];
    const bool has_depth = request_->sample(current_view, pivot);
    if (!has_depth && request_->state() == DepthState::Failed && !immediate_failure_fallback) {
      return cancel();
    }
    if (!has_depth) {
      pivot[0] = fallback_[0];
      pivot[1] = fallback_[1];
      pivot[2] = fallback_[2];
      fallback_used_ = true;
    }
    return initialize(pivot);
  }

 public:
  NavigationContinuation(OwnedDepthRequest *request,
                         NavigationState &state,
                         const Event invoke_event,
                         const float fallback[3])
      : request_(request),
        state_(state),
        producing_view_(state.view),
        invoke_event_(invoke_event),
        fallback_{fallback[0], fallback[1], fallback[2]}
  {
  }

  ModalResult begin()
  {
    prelude_count_++;
    backup_ = state_;
    backup_count_++;

    const DepthState depth_state = request_->state();
    if (depth_state == DepthState::Pending) {
      timer_ = true;
      return ModalResult::Running;
    }
    return settle(state_.view, depth_state == DepthState::Failed);
  }

  ModalResult event(const ViewSnapshot &current_view,
                    const Event &event,
                    const bool exact_timer)
  {
    if (!timer_ || !context_matches(current_view) || event.type == EventType::Escape) {
      return cancel();
    }
    if (!exact_timer) {
      if (!event.custom_data) {
        queued_event_ = event;
        queued_event_valid_ = true;
      }
      return ModalResult::RunningPass;
    }
    constexpr int max_tick_count = 240;
    if (++tick_count_ > max_tick_count) {
      return cancel();
    }
    const DepthState depth_state = request_->state();
    if (depth_state == DepthState::Pending) {
      return ModalResult::Running;
    }
    if (depth_state == DepthState::Failed) {
      return cancel();
    }
    return settle(current_view, false);
  }

  ModalResult external_cancel()
  {
    return cancel();
  }

  int prelude_count() const
  {
    return prelude_count_;
  }

  int backup_count() const
  {
    return backup_count_;
  }

  int initialize_count() const
  {
    return initialize_count_;
  }

  int replay_count() const
  {
    return replay_count_;
  }

  int restore_count() const
  {
    return restore_count_;
  }

  bool timer() const
  {
    return timer_;
  }

  bool fallback_used() const
  {
    return fallback_used_;
  }

  const Event &queued_event() const
  {
    return queued_event_;
  }

  const Event &invoke_event() const
  {
    return invoke_event_;
  }
};

const NavigationState initial_state;
const float fallback[3] = {7.0f, 8.0f, 9.0f};

bool contract_native_immediate()
{
  NavigationState state = initial_state;
  std::string lifetime;
  auto *readback = MEM_new<ControlledReadback>(__func__, depth_bytes(0.25f), &lifetime);
  readback->ready();
  OwnedDepthRequest request(readback, state.view, 11, 19);
  NavigationContinuation nav(&request, state, {EventType::Motion, 11, 19, false}, fallback);
  const ModalResult result = nav.begin();
  const bool ok = require(result == ModalResult::Running, "native-ready navigation did not run") &&
                  require(nav.prelude_count() == 1 && nav.backup_count() == 1,
                          "native-ready stock prelude count differs") &&
                  require(nav.initialize_count() == 1 && !nav.timer(),
                          "native-ready initialization count differs") &&
                  require(near(state.pivot[0], 11.5f) && near(state.pivot[1], 19.5f) &&
                              near(state.pivot[2], 0.25f),
                          "native-ready pivot differs") &&
                  require(lifetime == "R", "native-ready request was not retired once");
  if (ok) {
    std::printf("CONTRACT native_immediate PASS prelude=1 init=1 modal_wait=0\n");
  }
  return ok;
}

bool contract_pending_barrier_resume()
{
  NavigationState state = initial_state;
  std::string lifetime;
  auto *readback = MEM_new<ControlledReadback>(__func__, depth_bytes(0.625f), &lifetime);
  OwnedDepthRequest request(readback, state.view, 3, 4);
  NavigationContinuation nav(&request, state, {EventType::Motion, 3, 4, false}, fallback);
  const bool pending = nav.begin() == ModalResult::Running && nav.timer() &&
                       nav.initialize_count() == 0 && !state.initialized &&
                       state == initial_state;
  const Event custom = {EventType::Other, 99, 99, true};
  const Event motion = {EventType::Motion, 31, 47, false};
  const bool queued = nav.event(state.view, custom, false) == ModalResult::RunningPass &&
                      nav.replay_count() == 0 &&
                      nav.event(state.view, motion, false) == ModalResult::RunningPass;
  readback->ready();
  const ModalResult result = nav.event(state.view, {EventType::Other}, true);
  const bool ok = require(pending, "pending navigation crossed initialization barrier") &&
                  require(queued, "pending navigation swallowed or replayed early") &&
                  require(result == ModalResult::Running, "settled motion did not resume modal") &&
                  require(nav.prelude_count() == 1 && nav.backup_count() == 1 &&
                              nav.initialize_count() == 1,
                          "resume reran stock prelude or skipped initialization") &&
                  require(nav.replay_count() == 1 &&
                              nav.queued_event().type == EventType::Motion &&
                              nav.queued_event().x == 31 && nav.queued_event().y == 47,
                          "latest motion was not replayed once") &&
                  require(nav.invoke_event().x == 3 && nav.invoke_event().y == 4 &&
                              near(state.pivot[0], 3.5f) && near(state.pivot[1], 4.5f) &&
                              near(state.pivot[2], 0.625f),
                          "invoke event and depth were not resolved together") &&
                  require(lifetime == "R", "settled pending request was not retired once");
  if (ok) {
    std::printf("CONTRACT pending_barrier_resume PASS prelude=1 init=1 replay=1\n");
  }
  return ok;
}

bool contract_latest_release_replay()
{
  NavigationState state = initial_state;
  std::string lifetime;
  auto *readback = MEM_new<ControlledReadback>(__func__, depth_bytes(0.4f), &lifetime);
  OwnedDepthRequest request(readback, state.view, 5, 6);
  NavigationContinuation nav(&request, state, {EventType::Motion, 5, 6, false}, fallback);
  const bool started = nav.begin() == ModalResult::Running;
  nav.event(state.view, {EventType::Motion, 20, 21, false}, false);
  nav.event(state.view, {EventType::Release, 22, 23, false}, false);
  readback->ready();
  const ModalResult result = nav.event(state.view, {EventType::Other}, true);
  const bool ok = require(started && result == ModalResult::Finished,
                          "queued release did not finish resumed navigation") &&
                  require(nav.replay_count() == 1 &&
                              nav.queued_event().type == EventType::Release &&
                              nav.queued_event().x == 22 && nav.queued_event().y == 23,
                          "latest release replay differs") &&
                  require(nav.initialize_count() == 1 && lifetime == "R",
                          "release path did not initialize/retire exactly once");
  if (ok) {
    std::printf("CONTRACT latest_release_replay PASS latest=22,23 replay=1 finish=1\n");
  }
  return ok;
}

bool contract_no_hit_fallback()
{
  NavigationState state = initial_state;
  std::string lifetime;
  auto *readback = MEM_new<ControlledReadback>(__func__, depth_bytes(1.0f), &lifetime);
  readback->ready();
  OwnedDepthRequest request(readback, state.view, 7, 8);
  NavigationContinuation nav(&request, state, {EventType::Motion, 7, 8, false}, fallback);
  const bool ok = require(nav.begin() == ModalResult::Running,
                          "no-hit navigation did not initialize") &&
                  require(nav.fallback_used(), "no-hit navigation skipped stock fallback") &&
                  require(near(state.pivot[0], 7.0f) && near(state.pivot[1], 8.0f) &&
                              near(state.pivot[2], 9.0f),
                          "stock fallback pivot differs") &&
                  require(nav.initialize_count() == 1 && lifetime == "R",
                          "fallback did not initialize/retire exactly once");
  if (ok) {
    std::printf("CONTRACT no_hit_fallback PASS pivot=7,8,9 init=1\n");
  }
  return ok;
}

bool contract_restore_paths()
{
  bool ok = true;
  int restored = 0;

  NavigationState drift_state = initial_state;
  std::string drift_lifetime;
  auto *drift_readback = MEM_new<ControlledReadback>(
      __func__, depth_bytes(0.2f), &drift_lifetime);
  OwnedDepthRequest drift_request(drift_readback, drift_state.view, 1, 2);
  NavigationContinuation drift(
      &drift_request, drift_state, {EventType::Motion, 1, 2, false}, fallback);
  ok &= require(drift.begin() == ModalResult::Running, "drift path did not start");
  ViewSnapshot changed = drift_state.view;
  changed.region++;
  ok &= require(drift.event(changed, {EventType::Other}, true) == ModalResult::Cancelled &&
                    drift_state == initial_state && drift.restore_count() == 1 &&
                    drift_lifetime == "R",
                "context drift did not cancel and restore");
  restored++;

  NavigationState escape_state = initial_state;
  std::string escape_lifetime;
  auto *escape_readback = MEM_new<ControlledReadback>(
      __func__, depth_bytes(0.2f), &escape_lifetime);
  OwnedDepthRequest escape_request(escape_readback, escape_state.view, 3, 4);
  NavigationContinuation escape(
      &escape_request, escape_state, {EventType::Motion, 3, 4, false}, fallback);
  ok &= require(escape.begin() == ModalResult::Running &&
                    escape.event(escape_state.view, {EventType::Escape}, false) ==
                        ModalResult::Cancelled &&
                    escape_state == initial_state && escape.restore_count() == 1 &&
                    escape_lifetime == "R",
                "Escape did not cancel and restore");
  restored++;

  NavigationState external_state = initial_state;
  std::string external_lifetime;
  auto *external_readback = MEM_new<ControlledReadback>(
      __func__, depth_bytes(0.2f), &external_lifetime);
  OwnedDepthRequest external_request(external_readback, external_state.view, 5, 6);
  NavigationContinuation external(
      &external_request, external_state, {EventType::Motion, 5, 6, false}, fallback);
  ok &= require(external.begin() == ModalResult::Running &&
                    external.external_cancel() == ModalResult::Cancelled &&
                    external_state == initial_state && external.restore_count() == 1 &&
                    external_lifetime == "R",
                "external cancel did not restore") &&
        require(drift.initialize_count() == 0 && escape.initialize_count() == 0 &&
                    external.initialize_count() == 0,
                "cancel path initialized navigation");
  restored++;

  if (ok) {
    std::printf("CONTRACT restore_paths PASS cases=3 restored=%d init=0\n", restored);
  }
  return ok;
}

bool contract_failure_timeout()
{
  bool ok = true;

  NavigationState failure_state = initial_state;
  std::string failure_lifetime;
  auto *failure_readback = MEM_new<ControlledReadback>(
      __func__, depth_bytes(0.3f), &failure_lifetime);
  OwnedDepthRequest failure_request(failure_readback, failure_state.view, 7, 8);
  NavigationContinuation failure(
      &failure_request, failure_state, {EventType::Motion, 7, 8, false}, fallback);
  ok &= require(failure.begin() == ModalResult::Running, "failure path did not start");
  failure_readback->fail();
  ok &= require(failure.event(failure_state.view, {EventType::Other}, true) ==
                        ModalResult::Cancelled &&
                    failure_state == initial_state && failure.initialize_count() == 0 &&
                    failure_lifetime == "R",
                "failed readback did not cancel and restore");

  NavigationState timeout_state = initial_state;
  std::string timeout_lifetime;
  auto *timeout_readback = MEM_new<ControlledReadback>(
      __func__, depth_bytes(0.3f), &timeout_lifetime);
  OwnedDepthRequest timeout_request(timeout_readback, timeout_state.view, 9, 10);
  NavigationContinuation timeout(
      &timeout_request, timeout_state, {EventType::Motion, 9, 10, false}, fallback);
  ok &= require(timeout.begin() == ModalResult::Running, "timeout path did not start");
  ModalResult result = ModalResult::Running;
  for (int tick = 0; tick < 241; tick++) {
    result = timeout.event(timeout_state.view, {EventType::Other}, true);
  }
  ok &= require(result == ModalResult::Cancelled && timeout_state == initial_state &&
                    timeout.initialize_count() == 0 && timeout.restore_count() == 1 &&
                    timeout_lifetime == "R",
                "bounded timeout did not cancel and restore");
  if (ok) {
    std::printf("CONTRACT failure_timeout PASS cases=2 ticks=241 restored=2\n");
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
  const bool ok = contract_native_immediate() && contract_pending_barrier_resume() &&
                  contract_latest_release_replay() && contract_no_hit_fallback() &&
                  contract_restore_paths() && contract_failure_timeout();
  if (!ok) {
    return 1;
  }
  std::printf("M5_NAVIGATION_DEPTH_CONTRACT_PASS contracts=6 cases=9\n");
  return 0;
}
