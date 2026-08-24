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
    std::fprintf(stderr, "M5_CENTER_DEPTH_CONTRACT_FAIL %s\n", message);
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

struct ViewState {
  int view3d = 1;
  int region_view = 2;
  int region = 3;
  int window = 4;
  float ofs[3] = {-1.0f, -2.0f, -3.0f};
  float quat[4] = {1.0f, 0.0f, 0.0f, 0.0f};
  float dist = 10.0f;
  float camdx = 0.0f;
  float camdy = 0.0f;
  float camzoom = 0.0f;
  int persp = 1;
  int view = 0;
  int axis_roll = 0;
  bool smooth_active = false;

  bool operator==(const ViewState &) const = default;
};

enum class DepthState {
  Pending,
  Ready,
  Failed,
};

class OwnedDepthRequest {
 private:
  blender::GPUReadback *readback_ = nullptr;
  ViewState producing_view_;
  int mval_[2] = {0, 0};
  float depth_ = 1.0f;
  DepthState state_ = DepthState::Pending;

 public:
  OwnedDepthRequest(blender::GPUReadback *readback,
                    const ViewState producing_view,
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

  bool sample(const ViewState current_view, float world[3])
  {
    if (state() != DepthState::Ready || current_view != producing_view_ ||
        current_view.smooth_active)
    {
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

enum class ModalResult {
  Running,
  RunningPass,
  Finished,
  Cancelled,
};

class CenterContinuation {
 private:
  OwnedDepthRequest *request_;
  ViewState producing_view_;
  int mval_[2];
  int smooth_viewtx_;
  int tick_count_ = 0;
  int apply_count_ = 0;
  bool timer_ = false;
  bool superseded_ = false;
  bool fallback_ = false;
  float target_[3] = {0.0f, 0.0f, 0.0f};

  ModalResult apply(const ViewState current_view)
  {
    if (current_view != producing_view_ || current_view.smooth_active) {
      request_->cancel();
      timer_ = false;
      return ModalResult::Cancelled;
    }
    float world[3];
    const bool has_depth = request_->sample(current_view, world);
    if (!has_depth && request_->state() == DepthState::Failed) {
      request_->cancel();
      timer_ = false;
      return ModalResult::Cancelled;
    }
    if (has_depth) {
      target_[0] = -world[0];
      target_[1] = -world[1];
      target_[2] = -world[2];
    }
    else {
      fallback_ = true;
      target_[0] = producing_view_.ofs[0] - float(mval_[0]);
      target_[1] = producing_view_.ofs[1] - float(mval_[1]);
      target_[2] = producing_view_.ofs[2];
    }
    apply_count_++;
    timer_ = false;
    return ModalResult::Finished;
  }

 public:
  CenterContinuation(OwnedDepthRequest *request,
                     const ViewState producing_view,
                     const int x,
                     const int y,
                     const int smooth_viewtx)
      : request_(request),
        producing_view_(producing_view),
        mval_{x, y},
        smooth_viewtx_(smooth_viewtx)
  {
  }

  ModalResult begin(const ViewState current_view)
  {
    const DepthState state = request_->state();
    if (state == DepthState::Ready) {
      return apply(current_view);
    }
    if (state == DepthState::Failed) {
      request_->cancel();
      return ModalResult::Cancelled;
    }
    timer_ = true;
    return ModalResult::Running;
  }

  ModalResult event(const ViewState current_view,
                    const bool exact_timer,
                    const bool escape = false)
  {
    if (!timer_ || superseded_ || current_view != producing_view_ ||
        current_view.smooth_active || escape)
    {
      request_->cancel();
      timer_ = false;
      return ModalResult::Cancelled;
    }
    if (!exact_timer) {
      return ModalResult::RunningPass;
    }
    constexpr int max_tick_count = 240;
    if (++tick_count_ > max_tick_count) {
      request_->cancel();
      timer_ = false;
      return ModalResult::Cancelled;
    }
    const DepthState state = request_->state();
    if (state == DepthState::Pending) {
      return ModalResult::RunningPass;
    }
    if (state == DepthState::Failed) {
      request_->cancel();
      timer_ = false;
      return ModalResult::Cancelled;
    }
    return apply(current_view);
  }

  void supersede()
  {
    superseded_ = true;
  }

  void cancel()
  {
    request_->cancel();
    timer_ = false;
  }

  int apply_count() const
  {
    return apply_count_;
  }

  int smooth_viewtx() const
  {
    return smooth_viewtx_;
  }

  bool fallback() const
  {
    return fallback_;
  }

  const float *target() const
  {
    return target_;
  }
};

const ViewState view_a;

bool contract_pending_exact_replay()
{
  std::string lifetime;
  auto *readback = MEM_new<ControlledReadback>(__func__, depth_bytes(0.625f), &lifetime);
  OwnedDepthRequest request(readback, view_a, 31, 47);
  CenterContinuation center(&request, view_a, 31, 47, 175);
  const bool pending = center.begin(view_a) == ModalResult::Running &&
                       center.event(view_a, false) == ModalResult::RunningPass &&
                       center.apply_count() == 0;
  readback->ready();
  const ModalResult result = center.event(view_a, true);
  const float *target = center.target();
  const bool ok = require(pending, "pending center applied or swallowed an unrelated event") &&
                  require(result == ModalResult::Finished, "settled center did not finish") &&
                  require(center.apply_count() == 1, "settled center apply count differs") &&
                  require(center.smooth_viewtx() == 175, "smooth-view duration drifted") &&
                  require(near(target[0], -31.5f) && near(target[1], -47.5f) &&
                              near(target[2], -0.625f),
                          "event/depth replay differs") &&
                  require(lifetime == "R", "settled readback was not retired once");
  if (ok) {
    std::printf("CONTRACT pending_exact_replay PASS xy=31,47 smooth=175 applies=1\n");
  }
  return ok;
}

bool contract_native_immediate()
{
  std::string lifetime;
  auto *readback = MEM_new<ControlledReadback>(__func__, depth_bytes(0.5f), &lifetime);
  readback->ready();
  OwnedDepthRequest request(readback, view_a, 9, 13);
  CenterContinuation center(&request, view_a, 9, 13, 200);
  const bool ok = require(center.begin(view_a) == ModalResult::Finished,
                          "native-ready request entered modal state") &&
                  require(center.apply_count() == 1, "native-ready apply count differs") &&
                  require(lifetime == "R", "native-ready request was not retired once");
  if (ok) {
    std::printf("CONTRACT native_immediate PASS modal=0 applies=1\n");
  }
  return ok;
}

bool contract_no_hit_fallback()
{
  std::string lifetime;
  auto *readback = MEM_new<ControlledReadback>(__func__, depth_bytes(1.0f), &lifetime);
  readback->ready();
  OwnedDepthRequest request(readback, view_a, 15, 27);
  CenterContinuation center(&request, view_a, 15, 27, 90);
  const bool ok = require(center.begin(view_a) == ModalResult::Finished,
                          "no-hit fallback did not finish") &&
                  require(center.fallback(), "no-hit result skipped simple-pan fallback") &&
                  require(center.apply_count() == 1, "fallback apply count differs") &&
                  require(lifetime == "R", "fallback request was not retired once");
  if (ok) {
    std::printf("CONTRACT no_hit_fallback PASS xy=15,27 applies=1\n");
  }
  return ok;
}

bool contract_view_drift_rejected()
{
  std::vector<ViewState> drifts(5, view_a);
  drifts[0].region++;
  drifts[1].ofs[0] += 1.0f;
  drifts[2].quat[1] = 0.25f;
  drifts[3].camzoom += 2.0f;
  drifts[4].smooth_active = true;
  bool ok = true;
  int rejected = 0;
  for (ViewState drift : drifts) {
    std::string lifetime;
    auto *readback = MEM_new<ControlledReadback>(__func__, depth_bytes(0.25f), &lifetime);
    OwnedDepthRequest request(readback, view_a, 4, 5);
    CenterContinuation center(&request, view_a, 4, 5, 100);
    const bool started = center.begin(view_a) == ModalResult::Running;
    readback->ready();
    const bool cancelled = center.event(drift, true) == ModalResult::Cancelled;
    ok &= require(started && cancelled, "drifted producing view was not cancelled") &&
          require(center.apply_count() == 0, "drifted view started smooth transition") &&
          require(lifetime == "R", "drifted request was not retired once");
    rejected += cancelled ? 1 : 0;
  }
  if (ok) {
    std::printf("CONTRACT view_drift_rejected PASS cases=5 applies=0 retired=5\n");
  }
  return ok && rejected == 5;
}

bool contract_supersede_escape_cancel()
{
  bool ok = true;
  std::string superseded_lifetime;
  auto *superseded_readback = MEM_new<ControlledReadback>(
      __func__, depth_bytes(0.4f), &superseded_lifetime);
  OwnedDepthRequest superseded_request(superseded_readback, view_a, 1, 2);
  CenterContinuation superseded(&superseded_request, view_a, 1, 2, 100);
  ok &= require(superseded.begin(view_a) == ModalResult::Running,
                "superseded request did not start");
  superseded.supersede();
  ok &= require(superseded.event(view_a, true) == ModalResult::Cancelled,
                "superseded request was not cancelled") &&
        require(superseded_lifetime == "R", "superseded request was not retired once");

  std::string escape_lifetime;
  auto *escape_readback = MEM_new<ControlledReadback>(__func__, depth_bytes(0.4f), &escape_lifetime);
  OwnedDepthRequest escape_request(escape_readback, view_a, 3, 4);
  CenterContinuation escape(&escape_request, view_a, 3, 4, 100);
  ok &= require(escape.begin(view_a) == ModalResult::Running &&
                    escape.event(view_a, false, true) == ModalResult::Cancelled,
                "Escape did not cancel pending center") &&
        require(escape_lifetime == "R", "Escape request was not retired once");

  std::string cancel_lifetime;
  auto *cancel_readback = MEM_new<ControlledReadback>(__func__, depth_bytes(0.4f), &cancel_lifetime);
  OwnedDepthRequest cancel_request(cancel_readback, view_a, 5, 6);
  CenterContinuation cancelled(&cancel_request, view_a, 5, 6, 100);
  ok &= require(cancelled.begin(view_a) == ModalResult::Running,
                "externally cancelled request did not start");
  cancelled.cancel();
  ok &= require(cancel_lifetime == "R", "external cancel did not retire once") &&
        require(superseded.apply_count() == 0 && escape.apply_count() == 0 &&
                    cancelled.apply_count() == 0,
                "terminal cancellation started a smooth transition");
  if (ok) {
    std::printf("CONTRACT supersede_escape_cancel PASS cases=3 applies=0 retired=3\n");
  }
  return ok;
}

bool contract_failure_and_timeout()
{
  bool ok = true;
  std::string failure_lifetime;
  auto *failed_readback = MEM_new<ControlledReadback>(
      __func__, depth_bytes(0.4f), &failure_lifetime);
  OwnedDepthRequest failed_request(failed_readback, view_a, 7, 8);
  CenterContinuation failed(&failed_request, view_a, 7, 8, 100);
  ok &= require(failed.begin(view_a) == ModalResult::Running, "failed request did not start");
  failed_readback->fail();
  ok &= require(failed.event(view_a, true) == ModalResult::Cancelled,
                "failed request was not cancelled") &&
        require(failure_lifetime == "R", "failed request was not retired once");

  std::string timeout_lifetime;
  auto *timeout_readback = MEM_new<ControlledReadback>(
      __func__, depth_bytes(0.4f), &timeout_lifetime);
  OwnedDepthRequest timeout_request(timeout_readback, view_a, 9, 10);
  CenterContinuation timeout(&timeout_request, view_a, 9, 10, 100);
  ok &= require(timeout.begin(view_a) == ModalResult::Running, "timeout request did not start");
  ModalResult result = ModalResult::Running;
  for (int tick = 0; tick < 241; tick++) {
    result = timeout.event(view_a, true);
  }
  ok &= require(result == ModalResult::Cancelled, "bounded timeout did not cancel") &&
        require(timeout.apply_count() == 0 && failed.apply_count() == 0,
                "failure or timeout started smooth transition") &&
        require(timeout_lifetime == "R", "timed-out request was not retired once");
  if (ok) {
    std::printf("CONTRACT failure_timeout PASS cases=2 ticks=241 applies=0 retired=2\n");
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
  const bool ok = contract_pending_exact_replay() && contract_native_immediate() &&
                  contract_no_hit_fallback() && contract_view_drift_rejected() &&
                  contract_supersede_escape_cancel() && contract_failure_and_timeout();
  if (!ok) {
    return 1;
  }
  std::printf("M5_CENTER_DEPTH_CONTRACT_PASS contracts=6 cases=13\n");
  return 0;
}
