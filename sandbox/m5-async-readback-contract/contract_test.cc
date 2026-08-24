/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <utility>
#include <vector>

#include "BLI_assert.h"
#include "BLI_rect.h"
#include "GPU_readback.hh"
#include "GPU_select.hh"
#include "MEM_guardedalloc.h"
#include "gpu_readback_private.hh"
#include "gpu_select_private.hh"

/* This contract compiles Blender's production sources without the rest of the
 * application. Supply only the allocator/assert/rectangle leaves those two
 * translation units import; no GPU backend or adapter is instantiated. */

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

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "M5_ASYNC_READBACK_CONTRACT_FAIL %s\n", message);
    return false;
  }
  return true;
}

template<typename T> std::vector<unsigned char> as_bytes(const T *values, const size_t count)
{
  std::vector<unsigned char> bytes(sizeof(T) * count);
  if (!bytes.empty()) {
    std::memcpy(bytes.data(), values, bytes.size());
  }
  return bytes;
}

class ControlledReadback final : public blender::GPUReadback {
 private:
  blender::eGPUReadbackStatus status_ = blender::GPU_READBACK_PENDING;
  blender::eGPUReadbackError error_ = blender::GPU_READBACK_ERROR_NONE;
  std::vector<unsigned char> bytes_;
  int *destroy_count_ = nullptr;

 public:
  ControlledReadback(std::vector<unsigned char> bytes, int *destroy_count)
      : bytes_(std::move(bytes)), destroy_count_(destroy_count)
  {
  }

  ~ControlledReadback() override
  {
    if (destroy_count_ != nullptr) {
      (*destroy_count_)++;
    }
  }

  void mark_ready()
  {
    status_ = blender::GPU_READBACK_READY;
  }

  void mark_failed(const blender::eGPUReadbackError error)
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

ControlledReadback *controlled_readback(std::vector<unsigned char> bytes, int &destroy_count)
{
  return MEM_new<ControlledReadback>(__func__, std::move(bytes), &destroy_count);
}

bool owned_result_contract()
{
  using namespace blender;
  std::vector<unsigned char> expected = {0x10, 0x20, 0x30, 0x40, 0xa5};
  GPUReadback *ready = gpu_readback_create_ready(std::vector<unsigned char>(expected));
  std::array<unsigned char, 8> destination;
  destination.fill(0xcc);
  GPUReadback *ready_identity = ready;
  if (!require(GPU_readback_status(ready) == GPU_READBACK_READY, "ready status") ||
      !require(GPU_readback_error(ready) == GPU_READBACK_ERROR_NONE, "ready error") ||
      !require(GPU_readback_size(ready) == expected.size(), "ready size") ||
      !require(!GPU_readback_consume(ready, destination.data(), expected.size() - 1),
               "undersized consume rejects") ||
      !require(ready == ready_identity, "undersized consume retains owner") ||
      !require(destination == std::array<unsigned char, 8>{0xcc, 0xcc, 0xcc, 0xcc,
                                                          0xcc, 0xcc, 0xcc, 0xcc},
               "undersized consume preserves destination") ||
      !require(GPU_readback_consume(ready, destination.data(), destination.size()),
               "ready consume") ||
      !require(ready == nullptr, "ready consume clears owner") ||
      !require(std::memcmp(destination.data(), expected.data(), expected.size()) == 0,
               "ready bytes"))
  {
    GPU_readback_cancel(ready);
    return false;
  }

  GPUReadback *failed = gpu_readback_create_failed(GPU_READBACK_ERROR_MAP_FAILED, 17);
  if (!require(GPU_readback_status(failed) == GPU_READBACK_FAILED, "failed status") ||
      !require(GPU_readback_error(failed) == GPU_READBACK_ERROR_MAP_FAILED, "failed error") ||
      !require(GPU_readback_size(failed) == 17, "failed final size") ||
      !require(!GPU_readback_consume(failed, destination.data(), destination.size()),
               "failed consume rejects"))
  {
    GPU_readback_cancel(failed);
    return false;
  }
  GPU_readback_cancel(failed);
  if (!require(failed == nullptr, "cancel clears failed owner") ||
      !require(GPU_readback_status(nullptr) == GPU_READBACK_INVALID, "null status") ||
      !require(GPU_readback_error(nullptr) == GPU_READBACK_ERROR_INVALID_ARGUMENT,
               "null error") ||
      !require(GPU_readback_size(nullptr) == 0, "null size") ||
      !require(!GPU_readback_consume(failed, destination.data(), destination.size()),
               "null consume rejects"))
  {
    return false;
  }
  GPU_readback_cancel(failed);
  std::printf("CONTRACT owned-result PASS cases=15 bytes=5\n");
  return true;
}

bool transform_result_contract()
{
  using namespace blender;
  int destroy_count = 0;
  int transform_count = 0;
  ControlledReadback *controlled = controlled_readback({10, 20, 30, 40, 50, 60}, destroy_count);
  GPUReadback *transformed = gpu_readback_create_transform(
      controlled,
      6,
      3,
      [&transform_count](const unsigned char *source,
                         const size_t source_size,
                         unsigned char *destination,
                         const size_t destination_size) {
        transform_count++;
        if (source_size != 6 || destination_size != 3) {
          return false;
        }
        destination[0] = source[5];
        destination[1] = source[2];
        destination[2] = source[0];
        return true;
      });
  std::array<unsigned char, 4> destination = {0xcc, 0xcc, 0xcc, 0xcc};
  if (!require(GPU_readback_status(transformed) == GPU_READBACK_PENDING,
               "transform pending") ||
      !require(GPU_readback_size(transformed) == 3, "transform final size") ||
      !require(destroy_count == 0 && transform_count == 0, "pending retains source"))
  {
    GPU_readback_cancel(transformed);
    return false;
  }
  controlled->mark_ready();
  if (!require(GPU_readback_status(transformed) == GPU_READBACK_READY, "transform ready") ||
      !require(GPU_readback_error(transformed) == GPU_READBACK_ERROR_NONE, "transform error") ||
      !require(destroy_count == 1 && transform_count == 1, "transform exactly once") ||
      !require(!GPU_readback_consume(transformed, destination.data(), 2),
               "transform undersized consume") ||
      !require(transformed != nullptr && transform_count == 1,
               "transform undersized retains") ||
      !require(GPU_readback_consume(transformed, destination.data(), destination.size()),
               "transform consume") ||
      !require(transformed == nullptr, "transform consume clears owner") ||
      !require(destination == std::array<unsigned char, 4>{60, 30, 10, 0xcc},
               "transform bytes"))
  {
    GPU_readback_cancel(transformed);
    return false;
  }

  ControlledReadback *failed_source = controlled_readback({1, 2}, destroy_count);
  failed_source->mark_failed(GPU_READBACK_ERROR_MAP_FAILED);
  GPUReadback *failed_transform = gpu_readback_create_transform(
      failed_source, 2, 1, [&transform_count](const unsigned char *, size_t, unsigned char *, size_t) {
        transform_count++;
        return true;
      });
  if (!require(GPU_readback_status(failed_transform) == GPU_READBACK_FAILED,
               "transform source failure") ||
      !require(GPU_readback_error(failed_transform) == GPU_READBACK_ERROR_MAP_FAILED,
               "transform source error") ||
      !require(destroy_count == 2 && transform_count == 1,
               "failed source retired without transform"))
  {
    GPU_readback_cancel(failed_transform);
    return false;
  }
  GPU_readback_cancel(failed_transform);

  ControlledReadback *rejected_source = controlled_readback({7, 8}, destroy_count);
  rejected_source->mark_ready();
  GPUReadback *rejected_transform = gpu_readback_create_transform(
      rejected_source, 2, 1, [](const unsigned char *, size_t, unsigned char *, size_t) {
        return false;
      });
  if (!require(GPU_readback_status(rejected_transform) == GPU_READBACK_FAILED,
               "transform rejection") ||
      !require(GPU_readback_error(rejected_transform) == GPU_READBACK_ERROR_BACKEND_FAILURE,
               "transform rejection error") ||
      !require(destroy_count == 3, "rejected source retired"))
  {
    GPU_readback_cancel(rejected_transform);
    return false;
  }
  GPU_readback_cancel(rejected_transform);

  GPUReadback *canceled_transform = gpu_readback_create_transform(
      controlled_readback({9}, destroy_count),
      1,
      1,
      [](const unsigned char *source, size_t, unsigned char *destination, size_t) {
        destination[0] = source[0];
        return true;
      });
  GPU_readback_cancel(canceled_transform);
  GPUReadback *invalid_transform = gpu_readback_create_transform(nullptr, 1, 2, {});
  if (!require(canceled_transform == nullptr && destroy_count == 4,
               "transform cancel owns source") ||
      !require(GPU_readback_status(invalid_transform) == GPU_READBACK_FAILED,
               "invalid transform status") ||
      !require(GPU_readback_error(invalid_transform) == GPU_READBACK_ERROR_INVALID_ARGUMENT,
               "invalid transform error") ||
      !require(GPU_readback_size(invalid_transform) == 2, "invalid transform size"))
  {
    GPU_readback_cancel(invalid_transform);
    return false;
  }
  GPU_readback_cancel(invalid_transform);
  std::printf("CONTRACT transform-result PASS cases=16 transforms=1 retired=4\n");
  return true;
}

bool expect_hit(const blender::GPUSelectBuffer &buffer,
                const size_t index,
                const uint32_t id,
                const uint32_t depth)
{
  return require(index < buffer.storage.size(), "hit index") &&
         require(buffer.storage[index].id == id, "hit id") &&
         require(buffer.storage[index].depth == depth, "hit depth");
}

bool async_selection_contract()
{
  using namespace blender;
  GPU_select_async_session_begin();
  if (!require(GPU_select_async_session_is_active(), "session active") ||
      !require(GPU_select_async_status() == GPU_READBACK_INVALID, "empty session invalid"))
  {
    GPU_select_async_session_end();
    return false;
  }

  int destroy_count = 0;
  const rcti all_rect{10, 20, 30, 40};
  GPUSelectBuffer request_buffer;
  gpu_select_next_begin(&request_buffer, &all_rect, 0, GPU_SELECT_ALL);
  uint32_t all_raw[] = {0b0101u};
  uint32_t all_ids[] = {101u, 102u, 103u, 104u};
  bool all_front[] = {false, false, false, false};
  ControlledReadback *all_readback = controlled_readback(as_bytes(all_raw, 1), destroy_count);
  gpu_select_next_async_readback_begin(
      all_readback, Span<uint>(all_ids, 4), Span<bool>(all_front, 4));
  all_ids[0] = all_ids[2] = 999u;
  if (!require(GPU_select_async_status() == GPU_READBACK_PENDING, "all pending")) {
    GPU_select_async_session_end();
    return false;
  }
  GPUSelectBuffer premature;
  int premature_hits = -7;
  if (!require(!GPU_select_async_result_replay(
                   &premature, &all_rect, 0, GPU_SELECT_ALL, &premature_hits),
               "pending replay rejects") ||
      !require(premature.storage.is_empty() && premature_hits == -7,
               "pending replay preserves output"))
  {
    GPU_select_async_session_end();
    return false;
  }
  all_readback->mark_ready();
  if (!require(GPU_select_async_status() == GPU_READBACK_READY, "all ready") ||
      !require(destroy_count == 1, "all owner retired"))
  {
    GPU_select_async_session_end();
    return false;
  }

  const rcti pick_all_rect{50, 60, 70, 80};
  gpu_select_next_begin(&request_buffer, &pick_all_rect, 3, GPU_SELECT_PICK_ALL);
  float front_depth = 50.0f;
  uint32_t front_depth_bits = 0;
  std::memcpy(&front_depth_bits, &front_depth, sizeof(front_depth_bits));
  uint32_t pick_all_raw[] = {front_depth_bits, 0xffffffffu, 0x00001234u};
  uint32_t pick_all_ids[] = {201u, 202u, 203u};
  bool pick_all_front[] = {true, false, false};
  ControlledReadback *pick_all_readback = controlled_readback(
      as_bytes(pick_all_raw, 3), destroy_count);
  gpu_select_next_async_readback_begin(
      pick_all_readback, Span<uint>(pick_all_ids, 3), Span<bool>(pick_all_front, 3));
  pick_all_ids[0] = 999u;
  pick_all_front[0] = false;
  pick_all_readback->mark_ready();
  if (!require(GPU_select_async_status() == GPU_READBACK_READY, "pick-all ready") ||
      !require(destroy_count == 2, "pick-all owner retired"))
  {
    GPU_select_async_session_end();
    return false;
  }

  const rcti nearest_rect{90, 100, 110, 120};
  gpu_select_next_begin(&request_buffer, &nearest_rect, 7, GPU_SELECT_PICK_NEAREST);
  uint32_t nearest_raw[] = {0x00003000u, 0x00001000u, 0x00002000u};
  uint32_t nearest_ids[] = {301u, 302u, 303u};
  bool nearest_front[] = {false, false, false};
  ControlledReadback *nearest_readback = controlled_readback(
      as_bytes(nearest_raw, 3), destroy_count);
  gpu_select_next_async_readback_begin(
      nearest_readback, Span<uint>(nearest_ids, 3), Span<bool>(nearest_front, 3));
  nearest_readback->mark_ready();
  if (!require(GPU_select_async_status() == GPU_READBACK_READY, "nearest ready") ||
      !require(destroy_count == 3, "nearest owner retired"))
  {
    GPU_select_async_session_end();
    return false;
  }

  GPUSelectBuffer all_result;
  int hits = -1;
  if (!require(GPU_select_async_result_replay(
                   &all_result, &all_rect, 0, GPU_SELECT_ALL, &hits),
               "all replay") ||
      !require(hits == 2 && all_result.storage.size() == 2, "all replay count") ||
      !expect_hit(all_result, 0, 101u, 0xffffu) ||
      !expect_hit(all_result, 1, 103u, 0xffffu))
  {
    GPU_select_async_session_end();
    return false;
  }

  float adjusted_front_depth = front_depth / 100.0f;
  uint32_t adjusted_front_bits = 0;
  std::memcpy(&adjusted_front_bits, &adjusted_front_depth, sizeof(adjusted_front_bits));
  GPUSelectBuffer pick_all_result;
  if (!require(GPU_select_async_result_replay(
                   &pick_all_result, &pick_all_rect, 3, GPU_SELECT_PICK_ALL, &hits),
               "pick-all replay") ||
      !require(hits == 2 && pick_all_result.storage.size() == 2, "pick-all count") ||
      !expect_hit(pick_all_result, 0, 201u, adjusted_front_bits) ||
      !expect_hit(pick_all_result, 1, 203u, 0x00001234u))
  {
    GPU_select_async_session_end();
    return false;
  }

  GPUSelectBuffer nearest_result;
  if (!require(GPU_select_async_result_replay(
                   &nearest_result, &nearest_rect, 7, GPU_SELECT_PICK_NEAREST, &hits),
               "nearest replay") ||
      !require(hits == 1 && nearest_result.storage.size() == 1, "nearest count") ||
      !expect_hit(nearest_result, 0, 302u, 0x00001000u))
  {
    GPU_select_async_session_end();
    return false;
  }

  rcti wrong_rect = nearest_rect;
  wrong_rect.xmin++;
  GPUSelectBuffer wrong_result;
  hits = -9;
  if (!require(!GPU_select_async_result_replay(
                   &wrong_result, &wrong_rect, 7, GPU_SELECT_PICK_NEAREST, &hits),
               "wrong key rejects") ||
      !require(wrong_result.storage.is_empty() && hits == -9, "wrong key preserves output"))
  {
    GPU_select_async_session_end();
    return false;
  }

  GPUSelectBuffer repeated_result;
  if (!require(GPU_select_async_result_replay(
                   &repeated_result, &nearest_rect, 7, GPU_SELECT_PICK_NEAREST, &hits),
               "repeat replay") ||
      !require(hits == 1, "repeat replay count") ||
      !expect_hit(repeated_result, 0, 302u, 0x00001000u))
  {
    GPU_select_async_session_end();
    return false;
  }

  GPU_select_async_session_end();
  if (!require(!GPU_select_async_session_is_active(), "session ended") ||
      !require(GPU_select_async_status() == GPU_READBACK_INVALID, "ended status invalid"))
  {
    return false;
  }
  std::printf("CONTRACT async-selection PASS modes=3 results=5 exact_keys=4\n");
  return true;
}

bool async_failure_contract()
{
  using namespace blender;
  int destroy_count = 0;
  const rcti rect{1, 2, 3, 4};
  GPUSelectBuffer request_buffer;
  uint32_t raw[] = {7u};
  uint32_t ids[] = {42u};
  bool front[] = {false};

  GPU_select_async_session_begin();
  gpu_select_next_begin(&request_buffer, &rect, 0, GPU_SELECT_PICK_ALL);
  ControlledReadback *failed = controlled_readback(as_bytes(raw, 1), destroy_count);
  failed->mark_failed(GPU_READBACK_ERROR_MAP_FAILED);
  gpu_select_next_async_readback_begin(failed, Span<uint>(ids, 1), Span<bool>(front, 1));
  if (!require(GPU_select_async_status() == GPU_READBACK_FAILED, "terminal failure status") ||
      !require(GPU_select_async_error() == GPU_READBACK_ERROR_MAP_FAILED,
               "terminal failure error") ||
      !require(destroy_count == 1, "terminal failure owner retired"))
  {
    GPU_select_async_session_end();
    return false;
  }
  GPU_select_async_session_end();

  GPU_select_async_session_begin();
  gpu_select_next_begin(&request_buffer, &rect, 0, GPU_SELECT_PICK_ALL);
  gpu_select_next_async_readback_begin(nullptr, Span<uint>(ids, 1), Span<bool>(front, 1));
  if (!require(GPU_select_async_status() == GPU_READBACK_FAILED, "null request fails") ||
      !require(GPU_select_async_error() == GPU_READBACK_ERROR_BACKEND_FAILURE,
               "null request error"))
  {
    GPU_select_async_session_end();
    return false;
  }
  GPU_select_async_session_end();

  GPU_select_async_session_begin();
  gpu_select_next_begin(&request_buffer, &rect, 0, GPU_SELECT_PICK_ALL);
  ControlledReadback *first = controlled_readback(as_bytes(raw, 1), destroy_count);
  ControlledReadback *second = controlled_readback(as_bytes(raw, 1), destroy_count);
  gpu_select_next_async_readback_begin(first, Span<uint>(ids, 1), Span<bool>(front, 1));
  gpu_select_next_async_readback_begin(second, Span<uint>(ids, 1), Span<bool>(front, 1));
  if (!require(GPU_select_async_status() == GPU_READBACK_FAILED, "overlap fails") ||
      !require(GPU_select_async_error() == GPU_READBACK_ERROR_BACKEND_FAILURE,
               "overlap error") ||
      !require(destroy_count == 3, "overlap retires both owners"))
  {
    GPU_select_async_session_end();
    return false;
  }
  GPU_select_async_session_end();
  std::printf("CONTRACT async-failure PASS cases=3 retired=3\n");
  return true;
}

int rect_width(const blender::rcti &rect)
{
  return rect.xmax - rect.xmin;
}

int rect_height(const blender::rcti &rect)
{
  return rect.ymax - rect.ymin;
}

void selection_stride_realign(const blender::rcti &source,
                              const blender::rcti &clamped,
                              std::vector<uint> &buffer)
{
  const int x = clamped.xmin - source.xmin;
  const int y = clamped.ymin - source.ymin;
  const int source_width = rect_width(source);
  const int source_height = rect_height(source);
  const int clamped_width = rect_width(clamped);
  const int clamped_height = rect_height(clamped);
  int last_pixel = source_width * (y + clamped_height - 1) + (x + clamped_width - 1);
  std::fill(buffer.begin() + last_pixel + 1, buffer.end(), 0u);
  int last_written = clamped_width * clamped_height - 1;
  const int skip = source_width - clamped_width;
  while (true) {
    for (int index = clamped_width; index--;) {
      buffer[last_pixel--] = buffer[last_written--];
    }
    if (last_written < 0) {
      break;
    }
    last_pixel -= skip;
    std::fill(buffer.begin() + last_pixel + 1, buffer.begin() + last_pixel + 1 + skip, 0u);
  }
  std::fill(buffer.begin(), buffer.begin() + last_pixel + 1, 0u);
}

class SelectionBufferRequest {
 private:
  blender::GPUReadback *gpu_readback_ = nullptr;
  blender::rcti rect_ = {};
  blender::rcti rect_clamp_ = {};
  size_t buffer_len_ = 0;
  size_t clamped_len_ = 0;
  blender::eGPUReadbackStatus status_ = blender::GPU_READBACK_PENDING;
  blender::eGPUReadbackError error_ = blender::GPU_READBACK_ERROR_NONE;

 public:
  SelectionBufferRequest(blender::GPUReadback *gpu_readback,
                         const blender::rcti rect,
                         const blender::rcti rect_clamp)
      : gpu_readback_(gpu_readback),
        rect_(rect),
        rect_clamp_(rect_clamp),
        buffer_len_(size_t(rect_width(rect)) * size_t(rect_height(rect))),
        clamped_len_(size_t(rect_width(rect_clamp)) * size_t(rect_height(rect_clamp)))
  {
  }

  SelectionBufferRequest()
  {
    status_ = blender::GPU_READBACK_READY;
  }

  ~SelectionBufferRequest()
  {
    blender::GPU_readback_cancel(gpu_readback_);
  }

  blender::eGPUReadbackStatus status()
  {
    using namespace blender;
    if (status_ != GPU_READBACK_PENDING) {
      return status_;
    }
    const eGPUReadbackStatus child_status = GPU_readback_status(gpu_readback_);
    if (child_status == GPU_READBACK_PENDING) {
      return child_status;
    }
    if (child_status != GPU_READBACK_READY) {
      error_ = GPU_readback_error(gpu_readback_);
      if (error_ == GPU_READBACK_ERROR_NONE) {
        error_ = GPU_READBACK_ERROR_BACKEND_FAILURE;
      }
      GPU_readback_cancel(gpu_readback_);
      status_ = GPU_READBACK_FAILED;
      return status_;
    }
    if (GPU_readback_size(gpu_readback_) != clamped_len_ * sizeof(uint)) {
      GPU_readback_cancel(gpu_readback_);
      error_ = GPU_READBACK_ERROR_BACKEND_FAILURE;
      status_ = GPU_READBACK_FAILED;
      return status_;
    }
    status_ = GPU_READBACK_READY;
    return status_;
  }

  blender::eGPUReadbackError error()
  {
    status();
    return error_;
  }

  bool consume(std::vector<uint> &buffer)
  {
    using namespace blender;
    if (status() != GPU_READBACK_READY) {
      return false;
    }
    if (buffer_len_ == 0) {
      buffer.clear();
      status_ = GPU_READBACK_INVALID;
      return true;
    }
    buffer.resize(buffer_len_);
    if (!GPU_readback_consume(gpu_readback_, buffer.data(), buffer.size() * sizeof(uint))) {
      buffer.clear();
      error_ = GPU_READBACK_ERROR_BACKEND_FAILURE;
      status_ = GPU_READBACK_FAILED;
      return false;
    }
    if (!BLI_rcti_compare(&rect_, &rect_clamp_)) {
      selection_stride_realign(rect_, rect_clamp_, buffer);
    }
    status_ = GPU_READBACK_INVALID;
    return true;
  }

  void cancel()
  {
    blender::GPU_readback_cancel(gpu_readback_);
    status_ = blender::GPU_READBACK_INVALID;
  }
};

bool selection_buffer_request_contract()
{
  using namespace blender;
  int destroy_count = 0;
  std::vector<uint> output = {99u};

  const rcti exact_rect{0, 2, 0, 2};
  const uint exact_values[] = {11u, 12u, 21u, 22u};
  ControlledReadback *exact_controlled = controlled_readback(
      as_bytes(exact_values, std::size(exact_values)), destroy_count);
  SelectionBufferRequest exact(exact_controlled, exact_rect, exact_rect);
  if (!require(exact.status() == GPU_READBACK_PENDING, "selection exact pending") ||
      !require(!exact.consume(output) && output == std::vector<uint>{99u},
               "selection pending consume retains output") ||
      !require(destroy_count == 0, "selection pending retains owner"))
  {
    return false;
  }
  exact_controlled->mark_ready();
  if (!require(exact.status() == GPU_READBACK_READY, "selection exact ready") ||
      !require(exact.consume(output), "selection exact consume") ||
      !require(output == std::vector<uint>({11u, 12u, 21u, 22u}),
               "selection exact bytes") ||
      !require(destroy_count == 1, "selection exact retires owner"))
  {
    return false;
  }

  const rcti full_rect{-1, 3, -1, 2};
  const rcti clamped_rect{0, 3, 0, 2};
  const uint clamped_values[] = {1u, 2u, 3u, 4u, 5u, 6u};
  ControlledReadback *clamped_controlled = controlled_readback(
      as_bytes(clamped_values, std::size(clamped_values)), destroy_count);
  clamped_controlled->mark_ready();
  SelectionBufferRequest clamped(clamped_controlled, full_rect, clamped_rect);
  if (!require(clamped.consume(output), "selection clamped consume") ||
      !require(output == std::vector<uint>({0u, 0u, 0u, 0u, 0u, 1u,
                                            2u, 3u, 0u, 4u, 5u, 6u}),
               "selection clamped realign") ||
      !require(destroy_count == 2, "selection clamped retires owner"))
  {
    return false;
  }

  SelectionBufferRequest empty;
  output = {7u};
  if (!require(empty.status() == GPU_READBACK_READY, "selection empty ready") ||
      !require(empty.consume(output) && output.empty(), "selection empty consume"))
  {
    return false;
  }

  const rcti two_pixel_rect{0, 2, 0, 1};
  ControlledReadback *wrong_size = controlled_readback(as_bytes(exact_values, 1), destroy_count);
  wrong_size->mark_ready();
  SelectionBufferRequest mismatched(wrong_size, two_pixel_rect, two_pixel_rect);
  if (!require(mismatched.status() == GPU_READBACK_FAILED, "selection size mismatch") ||
      !require(mismatched.error() == GPU_READBACK_ERROR_BACKEND_FAILURE,
               "selection size mismatch error") ||
      !require(destroy_count == 3, "selection size mismatch retires owner"))
  {
    return false;
  }

  ControlledReadback *failed = controlled_readback(as_bytes(exact_values, 2), destroy_count);
  failed->mark_failed(GPU_READBACK_ERROR_MAP_FAILED);
  SelectionBufferRequest failed_request(failed, two_pixel_rect, two_pixel_rect);
  if (!require(failed_request.status() == GPU_READBACK_FAILED, "selection backend failure") ||
      !require(failed_request.error() == GPU_READBACK_ERROR_MAP_FAILED,
               "selection backend error") ||
      !require(destroy_count == 4, "selection backend failure retires owner"))
  {
    return false;
  }

  ControlledReadback *canceled = controlled_readback(as_bytes(exact_values, 2), destroy_count);
  SelectionBufferRequest canceled_request(canceled, two_pixel_rect, two_pixel_rect);
  canceled_request.cancel();
  if (!require(canceled_request.status() == GPU_READBACK_INVALID, "selection cancel invalid") ||
      !require(destroy_count == 5, "selection cancel retires owner"))
  {
    return false;
  }

  std::printf("CONTRACT selection-buffer-request PASS cases=6 realign_pixels=12 retired=5\n");
  return true;
}

enum class SelectionQueryKind {
  Sample,
  Nearest,
};

struct SelectionQueryKey {
  SelectionQueryKind kind = SelectionQueryKind::Sample;
  blender::rcti rect = {};
  uint id_min = 0;
  uint id_max = 0;
  uint initial_distance = 0;
  int context_token = 0;
};

bool selection_query_key_equal(const SelectionQueryKey &left, const SelectionQueryKey &right)
{
  return left.kind == right.kind && BLI_rcti_compare(&left.rect, &right.rect) &&
         left.id_min == right.id_min && left.id_max == right.id_max &&
         left.initial_distance == right.initial_distance &&
         left.context_token == right.context_token;
}

struct SelectionQueryResult {
  SelectionQueryKey key;
  uint index = 0;
  uint distance = 0;
};

class SelectionQuerySession {
 private:
  bool active_ = false;
  bool failed_ = false;
  bool replay_required_ = false;
  blender::eGPUReadbackError error_ = blender::GPU_READBACK_ERROR_NONE;
  SelectionBufferRequest *pending_ = nullptr;
  SelectionQueryKey pending_key_;
  std::vector<SelectionQueryResult> results_;

  void fail(const blender::eGPUReadbackError error)
  {
    if (pending_ != nullptr) {
      pending_->cancel();
      delete pending_;
      pending_ = nullptr;
    }
    failed_ = true;
    error_ = error == blender::GPU_READBACK_ERROR_NONE ?
                 blender::GPU_READBACK_ERROR_BACKEND_FAILURE :
                 error;
  }

  static uint sample_result(const std::vector<uint> &buffer)
  {
    return buffer.empty() ? 0 : buffer[0];
  }

  static uint nearest_result(const SelectionQueryKey &key,
                             const std::vector<uint> &buffer,
                             uint &r_distance)
  {
    const int width = rect_width(key.rect);
    const int height = rect_height(key.rect);
    const int center_x = (width - 1) / 2;
    const int center_y = (height - 1) / 2;
    const int max_distance = width + height;
    for (int distance = 0; distance <= max_distance; distance++) {
      for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
          if (std::abs(x - center_x) + std::abs(y - center_y) != distance) {
            continue;
          }
          const uint hit_id = buffer[size_t(y) * size_t(width) + size_t(x)];
          if (hit_id != 0 && hit_id >= key.id_min && hit_id < key.id_max) {
            r_distance = uint(distance);
            return (hit_id - key.id_min) + 1;
          }
        }
      }
    }
    return 0;
  }

 public:
  ~SelectionQuerySession()
  {
    end();
  }

  void begin()
  {
    end();
    active_ = true;
  }

  void end()
  {
    if (pending_ != nullptr) {
      pending_->cancel();
      delete pending_;
      pending_ = nullptr;
    }
    active_ = false;
    failed_ = false;
    replay_required_ = false;
    error_ = blender::GPU_READBACK_ERROR_NONE;
    results_.clear();
  }

  blender::eGPUReadbackStatus poll()
  {
    using namespace blender;
    if (!active_) {
      return GPU_READBACK_INVALID;
    }
    if (failed_) {
      return GPU_READBACK_FAILED;
    }
    if (pending_ == nullptr) {
      return results_.empty() ? GPU_READBACK_INVALID : GPU_READBACK_READY;
    }

    const eGPUReadbackStatus status = pending_->status();
    if (status == GPU_READBACK_PENDING) {
      return status;
    }
    if (status != GPU_READBACK_READY) {
      const eGPUReadbackError error = pending_->error();
      fail(error);
      return GPU_READBACK_FAILED;
    }

    std::vector<uint> buffer;
    if (!pending_->consume(buffer)) {
      fail(pending_->error());
      return GPU_READBACK_FAILED;
    }
    delete pending_;
    pending_ = nullptr;

    SelectionQueryResult result;
    result.key = pending_key_;
    result.distance = pending_key_.initial_distance;
    const size_t expected_size = size_t(rect_width(pending_key_.rect)) *
                                 size_t(rect_height(pending_key_.rect));
    if (!buffer.empty() && buffer.size() != expected_size) {
      fail(GPU_READBACK_ERROR_BACKEND_FAILURE);
      return GPU_READBACK_FAILED;
    }
    if (pending_key_.kind == SelectionQueryKind::Sample) {
      if (buffer.size() > 1) {
        fail(GPU_READBACK_ERROR_BACKEND_FAILURE);
        return GPU_READBACK_FAILED;
      }
      result.index = sample_result(buffer);
    }
    else {
      result.index = nearest_result(pending_key_, buffer, result.distance);
    }
    results_.push_back(result);
    return GPU_READBACK_READY;
  }

  blender::eGPUReadbackError error() const
  {
    return failed_ ? error_ : blender::GPU_READBACK_ERROR_NONE;
  }

  bool needs_replay() const
  {
    return replay_required_;
  }

  bool query(const SelectionQueryKey &key,
             SelectionBufferRequest *request,
             uint &r_index,
             uint &r_distance,
             int &r_active_context)
  {
    using namespace blender;
    const eGPUReadbackStatus status = poll();
    if (status == GPU_READBACK_FAILED) {
      delete request;
      return false;
    }
    for (const SelectionQueryResult &result : results_) {
      if (selection_query_key_equal(result.key, key)) {
        delete request;
        r_index = result.index;
        r_distance = result.distance;
        r_active_context = result.key.context_token;
        replay_required_ = false;
        return true;
      }
    }
    if (pending_ != nullptr) {
      delete request;
      replay_required_ = true;
      if (!selection_query_key_equal(pending_key_, key)) {
        fail(GPU_READBACK_ERROR_BACKEND_FAILURE);
      }
      return false;
    }
    if (request == nullptr) {
      fail(GPU_READBACK_ERROR_INVALID_ARGUMENT);
      return false;
    }
    pending_key_ = key;
    pending_ = request;
    replay_required_ = true;
    if (poll() == GPU_READBACK_READY) {
      return query(key, nullptr, r_index, r_distance, r_active_context);
    }
    return false;
  }
};

bool selection_query_session_contract()
{
  using namespace blender;
  int destroy_count = 0;
  int active_context = 99;
  uint index = 900;
  uint distance = 700;
  SelectionQuerySession session;
  session.begin();

  const rcti sample_rect{4, 5, 7, 8};
  const SelectionQueryKey face_key{
      SelectionQueryKind::Sample, sample_rect, 0, 0, 0, 11};
  const uint face_value[] = {41u};
  ControlledReadback *face_readback = controlled_readback(as_bytes(face_value, 1), destroy_count);
  if (!require(!session.query(face_key,
                              new SelectionBufferRequest(face_readback, sample_rect, sample_rect),
                              index,
                              distance,
                              active_context),
               "query face pending") ||
      !require(session.poll() == GPU_READBACK_PENDING, "query pending status") ||
      !require(index == 900 && distance == 700 && active_context == 99,
               "query pending preserves outputs") ||
      !require(destroy_count == 0, "query pending retains request"))
  {
    return false;
  }
  face_readback->mark_ready();
  if (!require(session.poll() == GPU_READBACK_READY, "query face ready") ||
      !require(session.needs_replay(), "query face ready still requires replay") ||
      !require(index == 900 && distance == 700 && active_context == 99,
               "query ready-before-guard preserves outputs") ||
      !require(session.query(face_key, nullptr, index, distance, active_context),
               "query face replay") ||
      !require(index == 41 && distance == 0 && active_context == 11,
               "query face exact result") ||
      !require(!session.needs_replay(), "query face replay clears latch") ||
      !require(destroy_count == 1, "query face retires request"))
  {
    return false;
  }

  const rcti nearest_rect{10, 15, 20, 25};
  const SelectionQueryKey edge_key{
      SelectionQueryKind::Nearest, nearest_rect, 100, 200, 2, 22};
  uint nearest_values[25] = {};
  nearest_values[2 * 5 + 4] = 107u;
  ControlledReadback *edge_readback = controlled_readback(
      as_bytes(nearest_values, std::size(nearest_values)), destroy_count);
  index = 901;
  distance = edge_key.initial_distance;
  if (!require(!session.query(edge_key,
                              new SelectionBufferRequest(
                                  edge_readback, nearest_rect, nearest_rect),
                              index,
                              distance,
                              active_context),
               "query edge pending") ||
      !require(index == 901 && distance == 2 && active_context == 11,
               "query edge pending preserves outputs"))
  {
    return false;
  }
  edge_readback->mark_ready();
  if (!require(session.poll() == GPU_READBACK_READY, "query edge ready") ||
      !require(session.needs_replay(), "query edge ready still requires replay") ||
      !require(session.query(edge_key, nullptr, index, distance, active_context),
               "query edge replay") ||
      !require(index == 8 && distance == 2 && active_context == 22,
               "query nearest id and distance") ||
      !require(destroy_count == 2, "query edge retires request"))
  {
    return false;
  }

  active_context = 77;
  if (!require(session.query(face_key, nullptr, index, distance, active_context),
               "query face repeat") ||
      !require(index == 41 && active_context == 11, "query face restores context") ||
      !require(session.query(edge_key, nullptr, index, distance, active_context),
               "query edge repeat") ||
      !require(index == 8 && distance == 2 && active_context == 22,
               "query edge restores context"))
  {
    return false;
  }

  const SelectionQueryKey vertex_key{
      SelectionQueryKind::Sample, rcti{30, 31, 40, 41}, 0, 0, 0, 33};
  ControlledReadback *vertex_readback = controlled_readback(as_bytes(face_value, 1), destroy_count);
  if (!require(!session.query(vertex_key,
                              new SelectionBufferRequest(
                                  vertex_readback, vertex_key.rect, vertex_key.rect),
                              index,
                              distance,
                              active_context),
               "query vertex pending"))
  {
    return false;
  }
  SelectionQueryKey drifted_key = vertex_key;
  drifted_key.rect.xmin++;
  if (!require(!session.query(drifted_key, nullptr, index, distance, active_context),
               "query drift rejects") ||
      !require(session.poll() == GPU_READBACK_FAILED, "query drift fails closed") ||
      !require(session.error() == GPU_READBACK_ERROR_BACKEND_FAILURE,
               "query drift error") ||
      !require(destroy_count == 3, "query drift cancels pending"))
  {
    return false;
  }
  session.end();
  if (!require(session.poll() == GPU_READBACK_INVALID, "query ended invalid")) {
    return false;
  }

  std::printf(
      "CONTRACT selection-query-session PASS queries=3 replays=4 context_restores=4 "
      "distance=2 failures=1 retired=3\n");
  return true;
}

}  // namespace

namespace mem_guarded::internal {
void (*mem_freeN_ex)(void *, DestructorType) = guarded_free;
void *(*mem_mallocN_aligned_ex)(size_t, size_t, const char *, DestructorType) = guarded_allocate;
}  // namespace mem_guarded::internal

extern "C" void *MEM_new_uninitialized_aligned(const size_t size,
                                                const size_t alignment,
                                                const char *)
{
  return aligned_allocate(size, alignment);
}

extern "C" void MEM_delete_void(void *pointer)
{
  std::free(pointer);
}

void _BLI_assert_print_pos(const char *, int, const char *, const char *) {}
void _BLI_assert_print_extra(const char *) {}
void _BLI_assert_print_backtrace() {}
void _BLI_assert_abort()
{
  std::abort();
}
void _BLI_assert_unreachable_print(const char *, int, const char *)
{
  std::abort();
}

namespace blender {
bool BLI_rcti_compare(const rcti *left, const rcti *right)
{
  return left != nullptr && right != nullptr && left->xmin == right->xmin &&
         left->xmax == right->xmax && left->ymin == right->ymin && left->ymax == right->ymax;
}
}  // namespace blender

int main()
{
  if (!owned_result_contract() || !transform_result_contract() || !async_selection_contract() ||
      !async_failure_contract() || !selection_buffer_request_contract() ||
      !selection_query_session_contract())
  {
    return 1;
  }
  std::printf(
      "M5_ASYNC_READBACK_CONTRACT_PASS contracts=6 modes=3 failures=4 transforms=1 "
      "selection_cases=6 query_replays=4\n");
  return 0;
}
