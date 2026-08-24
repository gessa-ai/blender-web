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
    std::fprintf(stderr, "M5_ZOOM_BORDER_DEPTH_CONTRACT_FAIL %s\n", message);
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
  std::string *lifetime_;

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

class OwnedRectDepth {
 private:
  blender::GPUReadback *readback_ = nullptr;
  Rect rect_ = {};
  size_t expected_size_ = 0;
  bool empty_ready_ = false;

 public:
  OwnedRectDepth(blender::GPUReadback *readback,
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

  ~OwnedRectDepth()
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

  bool consume(float &r_nearest)
  {
    if (state() != DepthState::Ready) {
      return false;
    }
    r_nearest = std::numeric_limits<float>::max();
    if (empty_ready_) {
      return true;
    }
    std::vector<float> depths(expected_size_ / sizeof(float));
    if (!blender::GPU_readback_consume(readback_, depths.data(), expected_size_)) {
      return false;
    }
    float nearest = 1.0f;
    for (const float depth : depths) {
      if (depth < nearest && depth > 0.0f) {
        nearest = depth;
      }
    }
    if (nearest != 1.0f) {
      r_nearest = nearest;
    }
    return true;
  }

  void cancel()
  {
    blender::GPU_readback_cancel(readback_);
  }

  const Rect &rect() const
  {
    return rect_;
  }
};

struct ViewState {
  int view3d = 1;
  int region_view = 2;
  int region = 3;
  int area = 4;
  int window = 5;
  int region_width = 100;
  int region_height = 80;
  int matrix_generation = 7;
  int smooth_state = 0;
  int smooth_timer = 0;
  int view_lock = 0;
  int camera = 0;
  int flag2 = 0;
  float ofs[3] = {-1.0f, -2.0f, -3.0f};
  float quat[4] = {1.0f, 0.0f, 0.0f, 0.0f};
  float dist = 10.0f;
  float camdx = 0.0f;
  float camdy = 0.0f;
  float camzoom = 0.0f;
  float lens = 50.0f;
  float clip_start = 0.1f;
  float clip_end = 1000.0f;
  float grid = 1.0f;
  int persp = 0;
  int view = 0;
  int axis_roll = 0;
  bool is_perspective = true;

  bool operator==(const ViewState &) const = default;
};

enum class ModalResult {
  Running,
  RunningPass,
  Finished,
  Cancelled,
};

class ZoomContinuation {
 private:
  OwnedRectDepth request_;
  ViewState producing_view_;
  int smooth_viewtx_ = 0;
  bool zoom_in_ = true;
  bool registered_ = false;
  bool attached_ = false;
  bool superseded_ = false;
  int tick_count_ = 0;
  int apply_count_ = 0;
  bool orthographic_fallback_ = false;
  float applied_depth_ = std::numeric_limits<float>::max();
  float target_dist_ = 0.0f;
  Rect applied_rect_ = {};

  static Rect aspect_fit(Rect rect, const ViewState &view)
  {
    const float region_aspect = float(view.region_width) / float(view.region_height);
    if ((float(width(rect)) / float(height(rect))) < region_aspect) {
      const int new_width = int(float(height(rect)) * region_aspect);
      const int center = (rect.xmin + rect.xmax) / 2;
      rect.xmin = center - new_width / 2;
      rect.xmax = rect.xmin + new_width;
    }
    else {
      const int new_height = int(float(width(rect)) / region_aspect);
      const int center = (rect.ymin + rect.ymax) / 2;
      rect.ymin = center - new_height / 2;
      rect.ymax = rect.ymin + new_height;
    }
    return rect;
  }

  ModalResult apply(const ViewState &current_view)
  {
    if (current_view != producing_view_) {
      request_.cancel();
      attached_ = false;
      return ModalResult::Cancelled;
    }
    float nearest;
    if (!request_.consume(nearest)) {
      request_.cancel();
      attached_ = false;
      return ModalResult::Cancelled;
    }
    if (producing_view_.is_perspective && nearest == std::numeric_limits<float>::max()) {
      attached_ = false;
      return ModalResult::Cancelled;
    }

    applied_rect_ = aspect_fit(request_.rect(), producing_view_);
    applied_depth_ = nearest;
    if (producing_view_.is_perspective) {
      target_dist_ = std::hypot(float(width(applied_rect_)), float(height(applied_rect_))) *
                     nearest * (producing_view_.lens / 36.0f);
    }
    else {
      orthographic_fallback_ = nearest == std::numeric_limits<float>::max();
      const float xscale = float(width(applied_rect_)) / float(producing_view_.region_width);
      const float yscale = float(height(applied_rect_)) / float(producing_view_.region_height);
      target_dist_ = producing_view_.dist * std::max(xscale, yscale);
    }
    if (!zoom_in_) {
      target_dist_ = producing_view_.dist * (producing_view_.dist / target_dist_);
    }
    const float minimum = producing_view_.is_perspective ? producing_view_.clip_start * 1.5f :
                                                           producing_view_.grid * 0.001f;
    target_dist_ = std::clamp(target_dist_, minimum, producing_view_.clip_end * 10.0f);
    apply_count_++;
    attached_ = false;
    return ModalResult::Finished;
  }

 public:
  ZoomContinuation(blender::GPUReadback *readback,
                   const Rect rect,
                   const ViewState view,
                   const bool zoom_in,
                   const int smooth_viewtx)
      : request_(readback, rect, view.region_width, view.region_height),
        producing_view_(view),
        smooth_viewtx_(smooth_viewtx),
        zoom_in_(zoom_in)
  {
  }

  ModalResult begin(const bool gesture_active, const ViewState &current_view)
  {
    const DepthState status = request_.state();
    if (status == DepthState::Ready) {
      return apply(current_view);
    }
    if (status == DepthState::Failed) {
      request_.cancel();
      return ModalResult::Cancelled;
    }
    registered_ = true;
    attached_ = !gesture_active;
    return ModalResult::Running;
  }

  ModalResult after_gesture(const ViewState &current_view)
  {
    if (!registered_ || attached_) {
      return ModalResult::Cancelled;
    }
    const DepthState status = request_.state();
    if (status == DepthState::Ready) {
      return apply(current_view);
    }
    if (status == DepthState::Failed) {
      request_.cancel();
      return ModalResult::Cancelled;
    }
    attached_ = true;
    return ModalResult::Running;
  }

  ModalResult event(const ViewState &current_view,
                    const bool exact_timer,
                    const bool escape = false,
                    const bool gesture_cancel = false)
  {
    if (!attached_ || superseded_ || current_view != producing_view_ || escape || gesture_cancel) {
      request_.cancel();
      attached_ = false;
      return ModalResult::Cancelled;
    }
    if (!exact_timer) {
      return ModalResult::RunningPass;
    }
    constexpr int max_tick_count = 240;
    if (++tick_count_ > max_tick_count) {
      request_.cancel();
      attached_ = false;
      return ModalResult::Cancelled;
    }
    const DepthState status = request_.state();
    if (status == DepthState::Pending) {
      return ModalResult::RunningPass;
    }
    if (status == DepthState::Failed) {
      request_.cancel();
      attached_ = false;
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
    request_.cancel();
    attached_ = false;
  }

  int apply_count() const
  {
    return apply_count_;
  }

  bool attached() const
  {
    return attached_;
  }

  bool registered() const
  {
    return registered_;
  }

  bool fallback() const
  {
    return orthographic_fallback_;
  }

  float depth() const
  {
    return applied_depth_;
  }

  float target_dist() const
  {
    return target_dist_;
  }

  int smooth_viewtx() const
  {
    return smooth_viewtx_;
  }

  const Rect &rect() const
  {
    return applied_rect_;
  }
};

bool contract_rect_nearest()
{
  std::string lifetime;
  const Rect raw = {-3, 6, -2, 5};
  const Rect expected = {0, 6, 0, 5};
  std::vector<float> values(30, 1.0f);
  values[0] = 0.0f;
  values[1] = std::numeric_limits<float>::quiet_NaN();
  values[7] = 0.75f;
  values[29] = 0.25f;
  auto *readback = make_readback(float_bytes(values), &lifetime, true);
  OwnedRectDepth request(readback, raw, 8, 6);
  float nearest = 0.0f;
  if (!require(request.rect() == expected, "stock rectangle clamp differs") ||
      !require(request.consume(nearest), "exact rectangle did not consume") ||
      !require(near(nearest, 0.25f), "strict nearest-depth reduction differs") ||
      !require(lifetime == "R", "consumed request was not released"))
  {
    return false;
  }

  OwnedRectDepth empty(nullptr, {20, 30, 20, 30}, 8, 6);
  if (!require(empty.state() == DepthState::Ready, "empty clamp did not settle") ||
      !require(empty.consume(nearest), "empty clamp did not preserve no-hit") ||
      !require(nearest == std::numeric_limits<float>::max(), "empty clamp hit depth"))
  {
    return false;
  }

  std::string short_lifetime;
  auto *short_readback = make_readback(
      std::vector<unsigned char>{0, 0, 0, 0}, &short_lifetime, true);
  OwnedRectDepth short_request(short_readback, {0, 2, 0, 2}, 8, 6);
  return require(short_request.state() == DepthState::Failed, "short result was accepted");
}

bool contract_native_immediate()
{
  ViewState view;
  view.region_width = 8;
  view.region_height = 6;
  std::string lifetime;
  auto *readback = make_readback(
      float_bytes({0.6f, 0.4f, 1.0f, 0.8f}), &lifetime, true);
  ZoomContinuation zoom(readback, {1, 3, 1, 3}, view, true, 180);
  return require(zoom.begin(true, view) == ModalResult::Finished,
                 "native-ready gesture did not finish immediately") &&
         require(zoom.apply_count() == 1, "native-ready result applied more than once") &&
         require(!zoom.registered() && !zoom.attached(), "native-ready path retained modal state") &&
         require(near(zoom.depth(), 0.4f), "native-ready nearest depth differs") &&
         require(zoom.smooth_viewtx() == 180, "smooth duration was not retained") &&
         require(lifetime == "R", "native-ready request was not consumed");
}

bool contract_gesture_handoff()
{
  ViewState view;
  view.region_width = 8;
  view.region_height = 6;
  std::string lifetime;
  auto *readback = make_readback(float_bytes({0.7f, 0.5f, 0.9f, 1.0f}), &lifetime);
  ZoomContinuation zoom(readback, {1, 3, 1, 3}, view, false, 90);
  if (!require(zoom.begin(true, view) == ModalResult::Running,
               "pending gesture did not stay modal") ||
      !require(zoom.registered() && !zoom.attached(), "request attached before gesture cleanup") ||
      !require(zoom.after_gesture(view) == ModalResult::Running,
               "gesture handoff did not attach continuation") ||
      !require(zoom.attached(), "gesture handoff lost timer ownership") ||
      !require(zoom.event(view, false) == ModalResult::RunningPass,
               "unrelated handoff event did not pass through"))
  {
    return false;
  }
  readback->ready();
  return require(zoom.event(view, true) == ModalResult::Finished,
                 "settled gesture continuation did not finish") &&
         require(zoom.apply_count() == 1, "gesture continuation did not apply exactly once") &&
         require(zoom.target_dist() > view.dist, "captured zoom-out mode was not replayed") &&
         require(lifetime == "R", "gesture result was not consumed");
}

bool contract_stock_zoom_modes()
{
  ViewState ortho;
  ortho.is_perspective = false;
  ortho.region_width = 100;
  ortho.region_height = 50;
  std::string lifetime;
  auto *no_hit = make_readback(
      float_bytes(std::vector<float>(400, 1.0f)), &lifetime, true);
  ZoomContinuation fallback(no_hit, {10, 30, 10, 30}, ortho, true, 0);
  if (!require(fallback.begin(false, ortho) == ModalResult::Finished,
               "orthographic no-hit did not finish") ||
      !require(fallback.fallback(), "orthographic no-hit lost stock fallback") ||
      !require(fallback.rect() == Rect{0, 40, 10, 30}, "aspect-fit rectangle differs"))
  {
    return false;
  }

  ViewState perspective = ortho;
  perspective.is_perspective = true;
  std::string miss_lifetime;
  auto *miss = make_readback(
      float_bytes(std::vector<float>(400, 1.0f)), &miss_lifetime, true);
  ZoomContinuation rejected(miss, {10, 30, 10, 30}, perspective, true, 0);
  return require(rejected.begin(false, perspective) == ModalResult::Cancelled,
                 "perspective no-hit did not preserve stock cancellation") &&
         require(rejected.apply_count() == 0, "perspective no-hit mutated the view");
}

bool contract_producing_drift()
{
  ViewState view;
  std::string lifetime;
  auto *readback = make_readback(float_bytes(std::vector<float>(400, 0.5f)), &lifetime);
  ZoomContinuation zoom(readback, {10, 30, 10, 30}, view, true, 0);
  if (!require(zoom.begin(false, view) == ModalResult::Running, "direct pending path did not attach")) {
    return false;
  }
  ViewState changed = view;
  changed.matrix_generation++;
  readback->ready();
  if (!require(zoom.event(changed, true) == ModalResult::Cancelled,
               "matrix drift was not rejected") ||
      !require(zoom.apply_count() == 0, "matrix drift applied stale depth") ||
      !require(lifetime == "R", "drifted request was not canceled"))
  {
    return false;
  }

  std::string lock_lifetime;
  auto *lock_readback = make_readback(
      float_bytes(std::vector<float>(400, 0.5f)), &lock_lifetime);
  ZoomContinuation lock_zoom(lock_readback, {10, 30, 10, 30}, view, true, 0);
  lock_zoom.begin(false, view);
  changed = view;
  changed.view_lock = 1;
  return require(lock_zoom.event(changed, false) == ModalResult::Cancelled,
                 "view-lock drift was not rejected");
}

bool contract_supersession_cancel()
{
  ViewState view;
  std::string superseded_lifetime;
  auto *superseded_readback = make_readback(
      float_bytes(std::vector<float>(400, 0.5f)), &superseded_lifetime);
  ZoomContinuation superseded(superseded_readback, {10, 30, 10, 30}, view, true, 0);
  superseded.begin(false, view);
  superseded.supersede();
  if (!require(superseded.event(view, false) == ModalResult::Cancelled,
               "superseded request remained active") ||
      !require(superseded_lifetime == "R", "superseded request was not canceled"))
  {
    return false;
  }

  std::string escape_lifetime;
  auto *escape_readback = make_readback(
      float_bytes(std::vector<float>(400, 0.5f)), &escape_lifetime);
  ZoomContinuation escaped(escape_readback, {10, 30, 10, 30}, view, true, 0);
  escaped.begin(false, view);
  if (!require(escaped.event(view, false, true) == ModalResult::Cancelled,
               "Escape did not cancel request"))
  {
    return false;
  }

  std::string external_lifetime;
  auto *external_readback = make_readback(
      float_bytes(std::vector<float>(400, 0.5f)), &external_lifetime);
  ZoomContinuation external(external_readback, {10, 30, 10, 30}, view, true, 0);
  external.begin(false, view);
  external.cancel();
  return require(external_lifetime == "R", "external cancel leaked request") &&
         require(external.apply_count() == 0, "external cancel mutated view");
}

bool contract_bounded_failure()
{
  ViewState view;
  std::string failure_lifetime;
  auto *failed_readback = make_readback(
      float_bytes(std::vector<float>(400, 0.5f)), &failure_lifetime);
  ZoomContinuation failed(failed_readback, {10, 30, 10, 30}, view, true, 0);
  failed.begin(false, view);
  failed_readback->fail();
  if (!require(failed.event(view, true) == ModalResult::Cancelled,
               "terminal failure did not cancel") ||
      !require(failure_lifetime == "R", "failed result was not released"))
  {
    return false;
  }

  std::string timeout_lifetime;
  auto *timeout_readback = make_readback(
      float_bytes(std::vector<float>(400, 0.5f)), &timeout_lifetime);
  ZoomContinuation timeout(timeout_readback, {10, 30, 10, 30}, view, true, 0);
  timeout.begin(false, view);
  for (int i = 0; i < 240; i++) {
    if (!require(timeout.event(view, true) == ModalResult::RunningPass,
                 "request timed out before bound"))
    {
      return false;
    }
  }
  return require(timeout.event(view, true) == ModalResult::Cancelled,
                 "request exceeded bounded continuation") &&
         require(timeout_lifetime == "R", "timed-out request was not canceled") &&
         require(timeout.apply_count() == 0, "timed-out request mutated view");
}

bool contract_unrelated_passthrough()
{
  ViewState view;
  std::string lifetime;
  auto *readback = make_readback(float_bytes(std::vector<float>(400, 0.5f)), &lifetime);
  ZoomContinuation zoom(readback, {10, 30, 10, 30}, view, true, 0);
  zoom.begin(false, view);
  if (!require(zoom.event(view, false) == ModalResult::RunningPass,
               "unrelated event was consumed") ||
      !require(zoom.attached() && zoom.apply_count() == 0,
               "unrelated event retired continuation"))
  {
    return false;
  }
  zoom.cancel();
  return require(lifetime == "R", "passthrough cleanup leaked request");
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
  const struct {
    const char *name;
    bool (*function)();
    int cases;
  } contracts[] = {
      {"rect_nearest", contract_rect_nearest, 3},
      {"native_immediate", contract_native_immediate, 2},
      {"gesture_handoff", contract_gesture_handoff, 3},
      {"stock_zoom_modes", contract_stock_zoom_modes, 3},
      {"producing_drift", contract_producing_drift, 3},
      {"supersession_cancel", contract_supersession_cancel, 3},
      {"bounded_failure", contract_bounded_failure, 2},
      {"unrelated_passthrough", contract_unrelated_passthrough, 1},
  };

  int case_count = 0;
  for (const auto &contract : contracts) {
    if (!contract.function()) {
      return 1;
    }
    case_count += contract.cases;
    std::printf("CONTRACT %s PASS cases=%d\n", contract.name, contract.cases);
  }
  std::printf("M5_ZOOM_BORDER_DEPTH_CONTRACT_PASS contracts=8 cases=%d\n", case_count);
  return case_count == 20 ? 0 : 1;
}
