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
      !async_failure_contract())
  {
    return 1;
  }
  std::printf(
      "M5_ASYNC_READBACK_CONTRACT_PASS contracts=4 modes=3 failures=3 transforms=1\n");
  return 0;
}
