/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free parity contract for the exact canonical large-buffer update
 * state machine. WebGPU handles are deterministic value fakes; no instance,
 * adapter, device, queue, or command encoder is created. */

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <functional>
#include <utility>
#include <vector>

#include "wgpu_common.hh"

#ifndef BW_WGPU_BUFFER_UPDATE_SOURCE
#  error "BW_WGPU_BUFFER_UPDATE_SOURCE must name the extracted shipping method"
#endif

namespace blender::gpu::webgpu {

namespace update_mock {

enum class Event : uint8_t {
  Create,
  Map,
  Unmap,
  Encoder,
  Copy,
  Finish,
  Write,
  Submit,
};

enum class BufferUsage : uint32_t {
  CopySrc = 1,
};

struct BufferDescriptor {
  size_t size = 0;
  BufferUsage usage = BufferUsage::CopySrc;
  bool mappedAtCreation = false;
};

struct Trace {
  bool create_success = true;
  bool map_success = true;
  bool defer_scopes = false;
  size_t create_calls = 0;
  size_t map_calls = 0;
  size_t unmap_calls = 0;
  size_t encoder_calls = 0;
  size_t copy_calls = 0;
  size_t finish_calls = 0;
  size_t write_calls = 0;
  size_t submit_calls = 0;
  size_t descriptor_size = 0;
  bool descriptor_mapped = false;
  size_t source_offset = 0;
  size_t destination_offset = 0;
  size_t copy_size = 0;
  std::vector<uint8_t> mapped_bytes;
  std::vector<uint8_t> written_bytes;
  std::vector<Event> events;
  std::deque<std::function<void(bool)>> scope_callbacks;
};

class Buffer {
 public:
  Buffer() = default;
  Buffer(Trace *trace, const bool valid) : trace_(trace), valid_(valid) {}

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }
  bool operator!=(std::nullptr_t) const
  {
    return valid_;
  }

  void *GetMappedRange(size_t /*offset*/, const size_t size)
  {
    trace_->map_calls++;
    trace_->events.push_back(Event::Map);
    if (!trace_->map_success) {
      return nullptr;
    }
    trace_->mapped_bytes.assign(size, 0xa5);
    return trace_->mapped_bytes.data();
  }

  void Unmap()
  {
    trace_->unmap_calls++;
    trace_->events.push_back(Event::Unmap);
  }

 private:
  Trace *trace_ = nullptr;
  bool valid_ = false;
};

class CommandBuffer {
 public:
  explicit CommandBuffer(const bool valid = false) : valid_(valid) {}

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

 private:
  bool valid_ = false;
};

class CommandEncoder {
 public:
  CommandEncoder() = default;
  explicit CommandEncoder(Trace *trace) : trace_(trace), valid_(true) {}

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

  void CopyBufferToBuffer(const Buffer & /*source*/,
                          const size_t source_offset,
                          const Buffer & /*destination*/,
                          const size_t destination_offset,
                          const size_t size)
  {
    trace_->copy_calls++;
    trace_->source_offset = source_offset;
    trace_->destination_offset = destination_offset;
    trace_->copy_size = size;
    trace_->events.push_back(Event::Copy);
  }

  CommandBuffer Finish()
  {
    trace_->finish_calls++;
    trace_->events.push_back(Event::Finish);
    return CommandBuffer(true);
  }

 private:
  Trace *trace_ = nullptr;
  bool valid_ = false;
};

class Device {
 public:
  explicit Device(Trace *trace) : trace_(trace) {}

  Buffer CreateBuffer(const BufferDescriptor *descriptor) const
  {
    trace_->create_calls++;
    trace_->descriptor_size = descriptor->size;
    trace_->descriptor_mapped = descriptor->mappedAtCreation;
    trace_->events.push_back(Event::Create);
    return Buffer(trace_, trace_->create_success);
  }

  CommandEncoder CreateCommandEncoder() const
  {
    trace_->encoder_calls++;
    trace_->events.push_back(Event::Encoder);
    return CommandEncoder(trace_);
  }

  void PushErrorScope(wgpu::ErrorFilter /*filter*/) const {}

  template<typename Callback>
  int PopErrorScope(wgpu::CallbackMode /*mode*/, Callback &&callback) const
  {
    auto settle = [callback = std::forward<Callback>(callback)](const bool valid) mutable {
      callback(wgpu::PopErrorScopeStatus::Success,
               valid ? wgpu::ErrorType::NoError : wgpu::ErrorType::Validation,
               wgpu::StringView{});
    };
    if (trace_->defer_scopes) {
      trace_->scope_callbacks.push_back(std::move(settle));
    }
    else {
      settle(true);
    }
    return 1;
  }

 private:
  Trace *trace_;
};

class Queue {
 public:
  explicit Queue(Trace *trace) : trace_(trace) {}

  bool operator==(std::nullptr_t) const
  {
    return false;
  }

  void WriteBuffer(const Buffer & /*destination*/,
                   size_t /*offset*/,
                   const void *data,
                   const size_t size) const
  {
    trace_->write_calls++;
    const auto *bytes = static_cast<const uint8_t *>(data);
    trace_->written_bytes.assign(bytes, bytes + size);
    trace_->events.push_back(Event::Write);
  }

  void Submit(size_t /*count*/, const CommandBuffer * /*commands*/) const
  {
    trace_->submit_calls++;
    trace_->events.push_back(Event::Submit);
  }

 private:
  Trace *trace_;
};

class Instance {
 public:
  wgpu::WaitStatus WaitAny(int /*future*/, uint64_t /*timeout*/) const
  {
    return wgpu::WaitStatus::Success;
  }
};

}  // namespace update_mock

class BufferUpdateHarness {
 public:
  struct Allocation {
    update_mock::Buffer handle;
    size_t size = 0;
    bool readable = false;

    bool operator==(std::nullptr_t) const
    {
      return handle == nullptr;
    }
  };

  class AllocationCache {
   public:
    explicit AllocationCache(Allocation allocation) : allocation_(std::move(allocation)) {}

    Allocation lookup(uint8_t /*key*/) const
    {
      return allocation_;
    }

   private:
    Allocation allocation_;
  };

  struct PendingUpdateContext {
    update_mock::Instance instance;
    update_mock::Device device;
    update_mock::Queue queue;
    OrderedQueueScheduler scheduler;
  };

  BufferUpdateHarness(update_mock::Trace &trace, const size_t capacity, const bool valid = true)
      : allocation_cache_(Allocation{update_mock::Buffer(&trace, valid), capacity, false})
  {
  }

  bool update_sub(const update_mock::Instance &instance,
                  const update_mock::Device &device,
                  const update_mock::Queue &queue,
                  OrderedQueueScheduler &scheduler,
                  size_t offset,
                  const void *data,
                  size_t size);

  bool update_sub(const update_mock::Instance &instance,
                  const update_mock::Device &device,
                  const update_mock::Queue &queue,
                  OrderedQueueScheduler &scheduler,
                  size_t offset,
                  const void *data,
                  size_t size,
                  BufferUpdateTransaction &transaction);

  size_t retry_pending_updates();

  size_t pending_update_count() const
  {
    return pending_updates_->size();
  }

 private:
  static bool update_allocation(PendingUpdateContext context,
                                const Allocation &allocation,
                                size_t offset,
                                const void *data,
                                size_t size,
                                std::function<void(bool)> complete);

  static constexpr uint8_t kAllocationKey = 0;
  AllocationCache allocation_cache_;
  std::shared_ptr<PendingBufferPayloadQueue<PendingUpdateContext>> pending_updates_ =
      std::make_shared<PendingBufferPayloadQueue<PendingUpdateContext>>();
};

/* Execute the shipping state machine with deterministic fallible mapping. Only
 * the owning class qualifier and WebGPU value namespace are substituted. */
#define wgpu update_mock
#include BW_WGPU_BUFFER_UPDATE_SOURCE
#undef wgpu

namespace {

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "FAIL %s\n", message);
    return false;
  }
  return true;
}

bool no_device_work(const update_mock::Trace &trace)
{
  return trace.create_calls == 0 && trace.map_calls == 0 && trace.unmap_calls == 0 &&
         trace.encoder_calls == 0 && trace.copy_calls == 0 && trace.finish_calls == 0 &&
         trace.write_calls == 0 && trace.submit_calls == 0;
}

bool settle_scope_batch(update_mock::Trace &trace, const bool valid)
{
  if (trace.scope_callbacks.size() < 3) {
    return false;
  }
  std::array<std::function<void(bool)>, 3> callbacks;
  for (std::function<void(bool)> &callback : callbacks) {
    callback = std::move(trace.scope_callbacks.front());
    trace.scope_callbacks.pop_front();
  }
  callbacks[0](valid);
  callbacks[1](true);
  callbacks[2](true);
  return true;
}

}  // namespace

bool run_integrated_buffer_update_contracts()
{
  constexpr size_t large_size = kWriteBufferStagingThreshold + kCopyAlignment;
  std::vector<uint8_t> large_payload(large_size);
  for (size_t index = 0; index < large_payload.size(); index++) {
    large_payload[index] = uint8_t((index * 29 + 7) & 0xff);
  }
  const std::vector<uint8_t> small_payload(kWriteBufferStagingThreshold, 0x4d);
  auto update = [](BufferUpdateHarness &buffer,
                   update_mock::Trace &trace,
                   const size_t offset,
                   const void *data,
                   const size_t size) {
    OrderedQueueScheduler scheduler;
    return buffer.update_sub(update_mock::Instance(),
                             update_mock::Device(&trace),
                             update_mock::Queue(&trace),
                             scheduler,
                             offset,
                             data,
                             size);
  };

  {
    update_mock::Trace trace;
    BufferUpdateHarness buffer(trace, 4, false);
    if (!require(!update(buffer, trace, 0, small_payload.data(), 4) &&
                     no_device_work(trace),
                 "invalid destination is rejected atomically"))
    {
      return false;
    }
  }
  {
    update_mock::Trace trace;
    BufferUpdateHarness buffer(trace, 4);
    if (!require(!update(buffer, trace, 0, nullptr, 4) &&
                     no_device_work(trace),
                 "null source is rejected atomically"))
    {
      return false;
    }
  }
  for (const auto [offset, size, capacity] :
       {std::array<size_t, 3>{2, 4, 8},
        std::array<size_t, 3>{0, 2, 8},
        std::array<size_t, 3>{4, 8, 8}})
  {
    update_mock::Trace trace;
    BufferUpdateHarness buffer(trace, capacity);
    if (!require(!update(buffer, trace, offset, small_payload.data(), size) &&
                     no_device_work(trace),
                 "invalid alignment or range is rejected atomically"))
    {
      return false;
    }
  }
  {
    update_mock::Trace trace;
    BufferUpdateHarness buffer(trace, small_payload.size());
    if (!require(update(buffer, trace, 0, small_payload.data(), small_payload.size()),
                 "threshold-sized update uses the direct path") ||
        !require(trace.write_calls == 1 && trace.written_bytes == small_payload &&
                     trace.events == std::vector<update_mock::Event>{update_mock::Event::Write},
                 "direct path writes exact bytes without staging"))
    {
      return false;
    }
  }
  {
    update_mock::Trace trace;
    trace.create_success = false;
    BufferUpdateHarness buffer(trace, large_payload.size());
    if (!require(!update(buffer, trace, 0, large_payload.data(), large_payload.size()),
                 "staging allocation failure is rejected") ||
        !require(trace.create_calls == 1 && trace.map_calls == 0 && trace.copy_calls == 0 &&
                     trace.submit_calls == 0 &&
                     trace.events == std::vector<update_mock::Event>{update_mock::Event::Create},
                 "allocation failure performs no later work"))
    {
      return false;
    }
  }
  {
    update_mock::Trace trace;
    trace.map_success = false;
    BufferUpdateHarness buffer(trace, large_payload.size());
    if (!require(!update(buffer, trace, 0, large_payload.data(), large_payload.size()),
                 "staging map failure is rejected") ||
        !require(trace.create_calls == 1 && trace.map_calls == 1 && trace.unmap_calls == 0 &&
                     trace.encoder_calls == 0 && trace.copy_calls == 0 &&
                     trace.submit_calls == 0 &&
                     trace.events == std::vector<update_mock::Event>{update_mock::Event::Create,
                                                                    update_mock::Event::Map},
                 "map failure performs no copy or submission"))
    {
      return false;
    }
  }
  {
    update_mock::Trace trace;
    BufferUpdateHarness buffer(trace, large_payload.size() + kCopyAlignment);
    if (!require(update(
                     buffer, trace, kCopyAlignment, large_payload.data(), large_payload.size()),
                 "large exact-fit update succeeds") ||
        !require(trace.descriptor_size == large_payload.size() && trace.descriptor_mapped,
                 "staging descriptor preserves size and mapped creation") ||
        !require(trace.mapped_bytes == large_payload,
                 "staging map receives every source byte") ||
        !require(trace.source_offset == 0 && trace.destination_offset == kCopyAlignment &&
                     trace.copy_size == large_payload.size(),
                 "copy preserves the proven source and destination span") ||
        !require(trace.create_calls == 1 && trace.map_calls == 1 && trace.unmap_calls == 1 &&
                     trace.encoder_calls == 1 && trace.copy_calls == 1 &&
                     trace.finish_calls == 1 && trace.submit_calls == 1 &&
                     trace.events ==
                         std::vector<update_mock::Event>{update_mock::Event::Create,
                                                        update_mock::Event::Map,
                                                        update_mock::Event::Unmap,
                                                        update_mock::Event::Encoder,
                                                        update_mock::Event::Copy,
                                                        update_mock::Event::Finish,
                                                        update_mock::Event::Submit},
                 "successful staging work is ordered exactly once"))
    {
      return false;
    }
  }

  {
    update_mock::Trace trace;
    trace.defer_scopes = true;
    BufferUpdateHarness buffer(trace, 16);
    OrderedQueueScheduler scheduler;
    BufferUpdateTransaction transaction;
    std::array<uint8_t, 16> payload = {0x00, 0x11, 0x22, 0x33,
                                       0x44, 0x55, 0x66, 0x77,
                                       0x88, 0x99, 0xaa, 0xbb,
                                       0xcc, 0xdd, 0xee, 0xff};
    if (!require(!buffer.update_sub(update_mock::Instance(),
                                    update_mock::Device(&trace),
                                    update_mock::Queue(&trace),
                                    scheduler,
                                    0,
                                    payload.data(),
                                    payload.size(),
                                    transaction) &&
                     transaction.pending() && buffer.pending_update_count() == 1 &&
                     scheduler.pending_count() == 1,
                 "direct upload remains pending until implementation scopes settle") ||
        !require(settle_scope_batch(trace, true) && transaction.accepted() &&
                     buffer.pending_update_count() == 0 && scheduler.pending_count() == 0,
                 "direct upload commits only after accepted scopes"))
    {
      return false;
    }
  }

  {
    update_mock::Trace trace;
    trace.defer_scopes = true;
    BufferUpdateHarness buffer(trace, 16);
    OrderedQueueScheduler scheduler;
    BufferUpdateTransaction transaction;
    const std::array<uint8_t, 16> original = {0xf0, 0xe1, 0xd2, 0xc3,
                                              0xb4, 0xa5, 0x96, 0x87,
                                              0x78, 0x69, 0x5a, 0x4b,
                                              0x3c, 0x2d, 0x1e, 0x0f};
    std::array<uint8_t, 16> caller = original;
    if (!require(!buffer.update_sub(update_mock::Instance(),
                                    update_mock::Device(&trace),
                                    update_mock::Queue(&trace),
                                    scheduler,
                                    0,
                                    caller.data(),
                                    caller.size(),
                                    transaction) &&
                     transaction.pending(),
                 "rejectable direct upload starts pending"))
    {
      return false;
    }
    caller.fill(0x5a);
    if (!require(settle_scope_batch(trace, false) && transaction.rejected() &&
                     buffer.pending_update_count() == 1,
                 "rejected direct upload retains retry state"))
    {
      return false;
    }
    scheduler.begin_epoch();
    if (!require(buffer.retry_pending_updates() == 1 && transaction.pending() &&
                     trace.written_bytes == std::vector<uint8_t>(original.begin(), original.end()),
                 "clean epoch retries the original direct-upload bytes") ||
        !require(settle_scope_batch(trace, true) && transaction.accepted() &&
                     buffer.pending_update_count() == 0,
                 "clean direct retry commits once accepted"))
    {
      return false;
    }
  }

  {
    update_mock::Trace trace;
    trace.defer_scopes = true;
    BufferUpdateHarness buffer(trace, large_payload.size());
    OrderedQueueScheduler scheduler;
    BufferUpdateTransaction transaction;
    const std::vector<uint8_t> original = large_payload;
    std::vector<uint8_t> caller = original;
    if (!require(!buffer.update_sub(update_mock::Instance(),
                                    update_mock::Device(&trace),
                                    update_mock::Queue(&trace),
                                    scheduler,
                                    0,
                                    caller.data(),
                                    caller.size(),
                                    transaction) &&
                     transaction.pending() && trace.submit_calls == 0,
                 "staged upload waits for encoding scopes before submission") ||
        !require(settle_scope_batch(trace, true) && transaction.pending() &&
                     trace.submit_calls == 1,
                 "accepted encoding advances staged upload to submission validation"))
    {
      return false;
    }
    caller.assign(caller.size(), 0x6b);
    if (!require(settle_scope_batch(trace, false) && transaction.rejected() &&
                     buffer.pending_update_count() == 1,
                 "rejected staged submission retains owned bytes"))
    {
      return false;
    }
    scheduler.begin_epoch();
    if (!require(buffer.retry_pending_updates() == 1 && transaction.pending() &&
                     trace.mapped_bytes == original,
                 "clean epoch remaps the exact retained staged bytes") ||
        !require(settle_scope_batch(trace, true) && transaction.pending() &&
                     trace.submit_calls == 2,
                 "staged retry validates encoding before its second submission") ||
        !require(settle_scope_batch(trace, true) && transaction.accepted() &&
                     buffer.pending_update_count() == 0,
                 "accepted staged retry commits exact owned bytes"))
    {
      return false;
    }
  }

  std::printf(
      "CONTRACT buffer-staging-map PASS cases=12 large_bytes=%zu map_failure=reject "
      "writes=validated submits=validated retry=owned\n",
      large_payload.size());
  return true;
}

}  // namespace blender::gpu::webgpu
