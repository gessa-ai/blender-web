/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <algorithm>
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
    std::fprintf(stderr, "M5_SCREENSHOT_READBACK_CONTRACT_FAIL %s\n", message);
    return false;
  }
  return true;
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

enum class CaptureState {
  Invalid,
  Pending,
  Ready,
  Failed,
};

class Capture {
 private:
  blender::GPUReadback *readback_ = nullptr;
  int width_ = 0;
  int height_ = 0;
  size_t expected_size_ = 0;
  bool flip_rows_ = false;
  bool offscreen_live_ = true;
  std::string *lifetime_;

  void release_offscreen()
  {
    if (offscreen_live_) {
      offscreen_live_ = false;
      lifetime_->push_back('O');
    }
  }

 public:
  Capture(blender::GPUReadback *readback,
          const int width,
          const int height,
          const bool flip_rows,
          std::string *lifetime)
      : readback_(readback),
        width_(width),
        height_(height),
        expected_size_(size_t(width) * size_t(height) * 4),
        flip_rows_(flip_rows),
        lifetime_(lifetime)
  {
  }

  ~Capture()
  {
    blender::GPU_readback_cancel(readback_);
    release_offscreen();
  }

  CaptureState state()
  {
    const blender::eGPUReadbackStatus status = blender::GPU_readback_status(readback_);
    if (status == blender::GPU_READBACK_PENDING) {
      return CaptureState::Pending;
    }
    if (status != blender::GPU_READBACK_READY ||
        blender::GPU_readback_size(readback_) != expected_size_)
    {
      if (status != blender::GPU_READBACK_INVALID) {
        release_offscreen();
      }
      return CaptureState::Failed;
    }
    release_offscreen();
    return CaptureState::Ready;
  }

  bool consume(std::vector<unsigned char> &pixels)
  {
    if (state() != CaptureState::Ready) {
      return false;
    }
    pixels.resize(expected_size_);
    if (!blender::GPU_readback_consume(readback_, pixels.data(), pixels.size())) {
      pixels.clear();
      return false;
    }
    if (flip_rows_) {
      const size_t row_size = size_t(width_) * 4;
      for (int y = 0; y < height_ / 2; y++) {
        unsigned char *row_a = pixels.data() + size_t(y) * row_size;
        unsigned char *row_b = pixels.data() + size_t(height_ - 1 - y) * row_size;
        std::swap_ranges(row_a, row_a + row_size, row_b);
      }
    }
    return true;
  }
};

enum class OperatorResult {
  Running,
  Finished,
  Cancelled,
};

class ScreenshotSession {
 private:
  Capture *capture_ = nullptr;
  bool timer_ = false;
  bool modal_handler_ = false;
  bool file_selector_ = false;
  int tick_count_ = 0;
  int writes_ = 0;
  std::vector<unsigned char> pixels_;

  void cleanup()
  {
    timer_ = false;
    delete capture_;
    capture_ = nullptr;
  }

 public:
  ~ScreenshotSession()
  {
    cleanup();
  }

  void begin(Capture *capture)
  {
    cleanup();
    capture_ = capture;
    tick_count_ = 0;
  }

  OperatorResult invoke(const bool filepath_is_set)
  {
    if (filepath_is_set) {
      return exec();
    }
    file_selector_ = true;
    return OperatorResult::Running;
  }

  OperatorResult exec()
  {
    if (capture_ == nullptr) {
      return OperatorResult::Cancelled;
    }
    const CaptureState state = capture_->state();
    if (state == CaptureState::Pending) {
      if (!timer_) {
        timer_ = true;
        modal_handler_ = true;
        tick_count_ = 0;
      }
      return OperatorResult::Running;
    }
    if (state != CaptureState::Ready || !capture_->consume(pixels_)) {
      cleanup();
      return OperatorResult::Cancelled;
    }
    writes_++;
    cleanup();
    return OperatorResult::Finished;
  }

  OperatorResult modal_tick()
  {
    constexpr int max_tick_count = 240;
    if (!timer_ || capture_ == nullptr) {
      return OperatorResult::Cancelled;
    }
    if (capture_->state() == CaptureState::Pending) {
      tick_count_++;
      if (tick_count_ < max_tick_count) {
        return OperatorResult::Running;
      }
      cleanup();
      return OperatorResult::Cancelled;
    }
    return exec();
  }

  void cancel()
  {
    cleanup();
  }

  bool timer() const
  {
    return timer_;
  }

  bool modal_handler() const
  {
    return modal_handler_;
  }

  bool file_selector() const
  {
    return file_selector_;
  }

  int writes() const
  {
    return writes_;
  }

  const std::vector<unsigned char> &pixels() const
  {
    return pixels_;
  }
};

bool contract_native_immediate()
{
  std::string lifetime;
  auto *readback = new ControlledReadback({1, 2, 3, 4}, &lifetime);
  readback->ready();
  ScreenshotSession session;
  session.begin(new Capture(readback, 1, 1, false, &lifetime));
  const bool ok = require(session.invoke(true) == OperatorResult::Finished, "native result") &&
                  require(session.writes() == 1, "native write count") &&
                  require(session.pixels() == std::vector<unsigned char>({1, 2, 3, 4}),
                          "native bytes") &&
                  require(!session.timer(), "native timer") &&
                  require(lifetime == "OR", "native terminal lifetime");
  if (ok) {
    std::puts("CONTRACT native_immediate PASS cases=2");
  }
  return ok;
}

bool contract_file_selector_ownership()
{
  std::string lifetime;
  auto *readback = new ControlledReadback({1, 2, 3, 4, 5, 6, 7, 8}, &lifetime);
  ScreenshotSession session;
  session.begin(new Capture(readback, 1, 2, true, &lifetime));
  const bool invoke_ok = session.invoke(false) == OperatorResult::Running &&
                         session.file_selector() && !session.timer() && lifetime.empty();
  readback->ready();
  const bool exec_ok = session.exec() == OperatorResult::Finished && session.writes() == 1 &&
                       session.pixels() ==
                           std::vector<unsigned char>({5, 6, 7, 8, 1, 2, 3, 4}) &&
                       lifetime == "OR";
  const bool ok = require(invoke_ok, "file selector retains pending capture") &&
                  require(exec_ok, "file selector consumes ready capture");
  if (ok) {
    std::puts("CONTRACT file_selector_ownership PASS cases=2");
  }
  return ok;
}

bool contract_modal_resume()
{
  std::string lifetime;
  auto *readback = new ControlledReadback({9, 8, 7, 6}, &lifetime);
  ScreenshotSession session;
  session.begin(new Capture(readback, 1, 1, true, &lifetime));
  const bool pending_ok = session.exec() == OperatorResult::Running && session.timer() &&
                          session.modal_handler() &&
                          session.modal_tick() == OperatorResult::Running;
  readback->ready();
  const bool ready_ok = session.modal_tick() == OperatorResult::Finished &&
                        session.writes() == 1 && lifetime == "OR";
  const bool ok = require(pending_ok, "modal pending state") &&
                  require(ready_ok, "modal ready resume");
  if (ok) {
    std::puts("CONTRACT modal_resume PASS cases=2");
  }
  return ok;
}

bool contract_exact_size_failure()
{
  std::string lifetime;
  auto *readback = new ControlledReadback({1, 2, 3}, &lifetime);
  readback->ready();
  ScreenshotSession session;
  session.begin(new Capture(readback, 1, 1, true, &lifetime));
  const bool ok = require(session.exec() == OperatorResult::Cancelled, "wrong size result") &&
                  require(session.writes() == 0, "wrong size write count") &&
                  require(lifetime == "OR", "wrong size lifetime");
  if (ok) {
    std::puts("CONTRACT exact_size_failure PASS cases=2");
  }
  return ok;
}

bool contract_backend_failure_cancel()
{
  std::string failed_lifetime;
  auto *failed = new ControlledReadback({1, 2, 3, 4}, &failed_lifetime);
  failed->fail();
  ScreenshotSession failed_session;
  failed_session.begin(new Capture(failed, 1, 1, true, &failed_lifetime));
  const bool failure_ok = failed_session.exec() == OperatorResult::Cancelled &&
                          failed_session.writes() == 0 && failed_lifetime == "OR";

  std::string cancel_lifetime;
  auto *pending = new ControlledReadback({1, 2, 3, 4}, &cancel_lifetime);
  ScreenshotSession cancel_session;
  cancel_session.begin(new Capture(pending, 1, 1, true, &cancel_lifetime));
  cancel_session.cancel();
  const bool cancel_ok = cancel_session.writes() == 0 && cancel_lifetime == "RO";
  const bool ok = require(failure_ok, "backend failure") &&
                  require(cancel_ok, "pending cancel order");
  if (ok) {
    std::puts("CONTRACT failure_cancel PASS cases=2");
  }
  return ok;
}

bool contract_bounded_timeout()
{
  std::string lifetime;
  auto *pending = new ControlledReadback({1, 2, 3, 4}, &lifetime);
  ScreenshotSession session;
  session.begin(new Capture(pending, 1, 1, true, &lifetime));
  const bool started = session.exec() == OperatorResult::Running;
  bool bounded = true;
  for (int tick = 0; tick < 239; tick++) {
    bounded &= session.modal_tick() == OperatorResult::Running;
  }
  const bool timed_out = session.modal_tick() == OperatorResult::Cancelled;
  const bool ok = require(started && bounded, "timeout pending range") &&
                  require(timed_out && session.writes() == 0, "timeout terminal result") &&
                  require(lifetime == "RO", "timeout lifetime");
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
  const bool ok = contract_native_immediate() && contract_file_selector_ownership() &&
                  contract_modal_resume() && contract_exact_size_failure() &&
                  contract_backend_failure_cancel() && contract_bounded_timeout();
  if (!ok) {
    return 1;
  }
  std::puts("M5_SCREENSHOT_READBACK_CONTRACT_PASS contracts=6 cases=12");
  return 0;
}
