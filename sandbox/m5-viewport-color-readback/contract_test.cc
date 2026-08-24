/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
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
    std::fprintf(stderr, "M5_VIEWPORT_COLOR_READBACK_CONTRACT_FAIL %s\n", message);
    return false;
  }
  return true;
}

class ControlledReadback final : public blender::GPUReadback {
 private:
  blender::eGPUReadbackStatus status_ = blender::GPU_READBACK_PENDING;
  blender::eGPUReadbackError error_ = blender::GPU_READBACK_ERROR_NONE;
  std::vector<unsigned char> bytes_;
  int *destroy_count_;

 public:
  ControlledReadback(std::vector<unsigned char> bytes, int *destroy_count)
      : bytes_(std::move(bytes)), destroy_count_(destroy_count)
  {
  }

  ~ControlledReadback() override
  {
    (*destroy_count_)++;
  }

  void ready()
  {
    status_ = blender::GPU_READBACK_READY;
  }

  void fail(const blender::eGPUReadbackError error)
  {
    status_ = blender::GPU_READBACK_FAILED;
    error_ = error;
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

  bool consume(void *destination, const size_t destination_size) override
  {
    if (status_ != blender::GPU_READBACK_READY || destination == nullptr ||
        destination_size < bytes_.size())
    {
      return false;
    }
    if (!bytes_.empty()) {
      std::memcpy(destination, bytes_.data(), bytes_.size());
    }
    return true;
  }
};

class ViewportReadbackSession {
 public:
  enum class State { Pending, Ready, Failed };

 private:
  blender::GPUReadback *readback_ = nullptr;
  unsigned char *data_ = nullptr;
  size_t expected_size_ = 0;
  State state_ = State::Failed;

 public:
  ~ViewportReadbackSession()
  {
    blender::GPU_readback_cancel(readback_);
    MEM_delete(data_);
  }

  bool begin(blender::GPUReadback *readback, const size_t expected_size)
  {
    blender::GPU_readback_cancel(readback_);
    MEM_delete(data_);
    data_ = nullptr;
    readback_ = readback;
    expected_size_ = expected_size;
    state_ = State::Pending;
    return poll() != State::Failed;
  }

  State poll()
  {
    if (state_ != State::Pending) {
      return state_;
    }
    const blender::eGPUReadbackStatus status = blender::GPU_readback_status(readback_);
    if (status == blender::GPU_READBACK_PENDING) {
      return state_;
    }
    if (status != blender::GPU_READBACK_READY ||
        blender::GPU_readback_size(readback_) != expected_size_)
    {
      blender::GPU_readback_cancel(readback_);
      state_ = State::Failed;
      return state_;
    }
    unsigned char *result = MEM_new_array_uninitialized<unsigned char>(expected_size_, __func__);
    if (result == nullptr ||
        !blender::GPU_readback_consume(readback_, result, expected_size_))
    {
      MEM_delete(result);
      blender::GPU_readback_cancel(readback_);
      state_ = State::Failed;
      return state_;
    }
    data_ = result;
    state_ = State::Ready;
    return state_;
  }

  const unsigned char *data() const
  {
    return data_;
  }
};

ControlledReadback *controlled(std::vector<unsigned char> bytes, int &destroy_count)
{
  return MEM_new<ControlledReadback>(__func__, std::move(bytes), &destroy_count);
}

bool immediate_ready_contract()
{
  int destroyed = 0;
  std::vector<unsigned char> expected = {0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80};
  ControlledReadback *request = controlled(expected, destroyed);
  request->ready();
  ViewportReadbackSession session;
  if (!require(session.begin(request, expected.size()), "immediate begin") ||
      !require(session.poll() == ViewportReadbackSession::State::Ready, "immediate ready") ||
      !require(session.data() != nullptr, "immediate data") ||
      !require(std::memcmp(session.data(), expected.data(), expected.size()) == 0,
               "immediate bytes") ||
      !require(destroyed == 1, "immediate owner retired"))
  {
    return false;
  }
  std::printf("CONTRACT immediate-ready PASS bytes=8 destroyed=%d\n", destroyed);
  return true;
}

bool pending_ready_contract()
{
  int destroyed = 0;
  std::vector<unsigned char> expected = {0xa1, 0xb2, 0xc3, 0xd4};
  ControlledReadback *request = controlled(expected, destroyed);
  ViewportReadbackSession session;
  if (!require(session.begin(request, expected.size()), "pending begin") ||
      !require(session.poll() == ViewportReadbackSession::State::Pending, "pending state") ||
      !require(session.data() == nullptr, "pending owns no destination") ||
      !require(destroyed == 0, "pending owner retained"))
  {
    return false;
  }
  request->ready();
  if (!require(session.poll() == ViewportReadbackSession::State::Ready, "later ready") ||
      !require(session.data() != nullptr, "later data") ||
      !require(std::memcmp(session.data(), expected.data(), expected.size()) == 0,
               "later bytes") ||
      !require(destroyed == 1, "later owner retired"))
  {
    return false;
  }
  std::printf("CONTRACT pending-ready PASS polls=3 destroyed=%d\n", destroyed);
  return true;
}

bool failure_retry_contract()
{
  int destroyed = 0;
  ViewportReadbackSession session;
  ControlledReadback *failed = controlled({1, 2, 3, 4}, destroyed);
  failed->fail(blender::GPU_READBACK_ERROR_MAP_FAILED);
  if (!require(!session.begin(failed, 4), "failed begin") ||
      !require(session.poll() == ViewportReadbackSession::State::Failed, "failed state") ||
      !require(session.data() == nullptr, "failed no data") ||
      !require(destroyed == 1, "failed owner retired"))
  {
    return false;
  }
  ControlledReadback *retry = controlled({9, 8, 7, 6}, destroyed);
  retry->ready();
  if (!require(session.begin(retry, 4), "retry begin") ||
      !require(session.poll() == ViewportReadbackSession::State::Ready, "retry ready") ||
      !require(session.data()[0] == 9 && session.data()[3] == 6, "retry bytes") ||
      !require(destroyed == 2, "retry owner retired"))
  {
    return false;
  }
  std::printf("CONTRACT failure-retry PASS attempts=2 destroyed=%d\n", destroyed);
  return true;
}

bool mismatch_cancel_contract()
{
  int destroyed = 0;
  ViewportReadbackSession session;
  ControlledReadback *mismatch = controlled({1, 2, 3}, destroyed);
  mismatch->ready();
  if (!require(!session.begin(mismatch, 4), "size mismatch rejects") ||
      !require(session.poll() == ViewportReadbackSession::State::Failed, "mismatch failed") ||
      !require(session.data() == nullptr, "mismatch no data") ||
      !require(destroyed == 1, "mismatch owner retired"))
  {
    return false;
  }
  {
    ViewportReadbackSession pending;
    if (!require(pending.begin(controlled({5, 6}, destroyed), 2), "cancel pending begin") ||
        !require(destroyed == 1, "cancel pending retained"))
    {
      return false;
    }
  }
  if (!require(destroyed == 2, "destructor cancels pending")) {
    return false;
  }
  std::printf("CONTRACT mismatch-cancel PASS cases=2 destroyed=%d\n", destroyed);
  return true;
}

enum class ConfirmResult { Running, Finished, Canceled };

ConfirmResult confirm_tick(ViewportReadbackSession &session, int &tick_count)
{
  constexpr int max_tick_count = 240;
  if (++tick_count > max_tick_count) {
    return ConfirmResult::Canceled;
  }
  const ViewportReadbackSession::State state = session.poll();
  if (state == ViewportReadbackSession::State::Pending) {
    return ConfirmResult::Running;
  }
  return state == ViewportReadbackSession::State::Ready ? ConfirmResult::Finished :
                                                         ConfirmResult::Canceled;
}

bool confirm_continuation_contract()
{
  int destroyed = 0;
  {
    ViewportReadbackSession session;
    ControlledReadback *request = controlled({0xde, 0xad, 0xbe, 0xef}, destroyed);
    if (!require(session.begin(request, 4), "confirm pending begin")) {
      return false;
    }
    int tick_count = 0;
    if (!require(confirm_tick(session, tick_count) == ConfirmResult::Running,
                 "confirm remains modal while pending"))
    {
      return false;
    }
    request->ready();
    if (!require(confirm_tick(session, tick_count) == ConfirmResult::Finished,
                 "confirm finishes after ready") ||
        !require(destroyed == 1, "confirm ready owner retired"))
    {
      return false;
    }

    ControlledReadback *failed = controlled({1, 2, 3, 4}, destroyed);
    if (!require(session.begin(failed, 4), "confirm failure begin")) {
      return false;
    }
    failed->fail(blender::GPU_READBACK_ERROR_MAP_FAILED);
    tick_count = 0;
    if (!require(confirm_tick(session, tick_count) == ConfirmResult::Canceled,
                 "confirm failure cancels") ||
        !require(destroyed == 2, "confirm failure owner retired"))
    {
      return false;
    }

    if (!require(session.begin(controlled({5, 6, 7, 8}, destroyed), 4),
                 "confirm timeout begin"))
    {
      return false;
    }
    tick_count = 0;
    for (int tick = 0; tick < 240; tick++) {
      if (!require(confirm_tick(session, tick_count) == ConfirmResult::Running,
                   "confirm bounded pending tick"))
      {
        return false;
      }
    }
    if (!require(confirm_tick(session, tick_count) == ConfirmResult::Canceled,
                 "confirm bounded timeout") ||
        !require(destroyed == 2, "timeout retains request until cleanup"))
    {
      return false;
    }
  }
  if (!require(destroyed == 3, "timeout cleanup cancels owner")) {
    return false;
  }
  std::printf("CONTRACT confirm-continuation PASS paths=3 max_ticks=240 destroyed=%d\n",
              destroyed);
  return true;
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
  if (!immediate_ready_contract() || !pending_ready_contract() || !failure_retry_contract() ||
      !mismatch_cancel_contract() || !confirm_continuation_contract())
  {
    return 1;
  }
  std::printf("M5_VIEWPORT_COLOR_READBACK_CONTRACT_PASS contracts=5 cases=12\n");
  return 0;
}
