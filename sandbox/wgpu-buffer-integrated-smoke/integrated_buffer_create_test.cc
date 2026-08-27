/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm contract for the exact persistent Buffer::create_scoped state machine.
 * Fake error scopes can remain pending after the creating stack returns, matching browser WebGPU. */

#include <algorithm>
#include <array>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "wgpu_common.hh"

#ifndef BW_WGPU_BUFFER_CREATE_SOURCE
#  error "BW_WGPU_BUFFER_CREATE_SOURCE must name the extracted shipping method"
#endif

namespace blender::gpu::webgpu {

namespace create_mock {

enum class BufferUsage : uint32_t {
  None = 0,
  CopySrc = 1u << 0,
  CopyDst = 1u << 1,
  Index = 1u << 2,
  Vertex = 1u << 3,
  Uniform = 1u << 4,
  Storage = 1u << 5,
  Indirect = 1u << 6,
};

constexpr BufferUsage operator|(const BufferUsage a, const BufferUsage b)
{
  return BufferUsage(uint32_t(a) | uint32_t(b));
}

struct Limits {
  uint64_t maxBufferSize = 0;
};

struct BufferDescriptor {
  const char *label = nullptr;
  uint64_t size = 0;
  BufferUsage usage = BufferUsage::None;
  bool mappedAtCreation = false;
};

struct Trace {
  bool limits_success = true;
  bool create_success = true;
  bool map_success = true;
  uint64_t max_buffer_size = 64;
  size_t limit_calls = 0;
  size_t create_calls = 0;
  size_t map_calls = 0;
  size_t unmap_calls = 0;
  uint64_t descriptor_size = 0;
  BufferUsage descriptor_usage = BufferUsage::None;
  bool descriptor_mapped = false;
  std::string descriptor_label;
  std::vector<uint8_t> mapped_bytes;
};

class Instance {
 public:
  explicit Instance(const bool valid = true) : valid_(valid) {}

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

 private:
  bool valid_ = false;
};

class Buffer {
 public:
  Buffer() = default;
  Buffer(std::shared_ptr<Trace> trace, const bool valid)
      : trace_(std::move(trace)), valid_(valid)
  {
  }

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }
  bool operator!=(std::nullptr_t) const
  {
    return valid_;
  }

  void *GetMappedRange(const uint64_t offset, const size_t size)
  {
    trace_->map_calls++;
    if (!trace_->map_success || offset != 0 || size != trace_->descriptor_size) {
      return nullptr;
    }
    trace_->mapped_bytes.assign(size, 0);
    return trace_->mapped_bytes.data();
  }

  void Unmap()
  {
    trace_->unmap_calls++;
  }

 private:
  std::shared_ptr<Trace> trace_;
  bool valid_ = false;
};

class Device {
 public:
  Device() = default;
  explicit Device(std::shared_ptr<Trace> trace, const bool valid = true)
      : trace_(std::move(trace)), valid_(valid)
  {
  }

  bool operator==(std::nullptr_t) const
  {
    return !valid_;
  }

  bool GetLimits(Limits *limits) const
  {
    trace_->limit_calls++;
    if (!trace_->limits_success) {
      return false;
    }
    limits->maxBufferSize = trace_->max_buffer_size;
    return true;
  }

  Buffer CreateBuffer(const BufferDescriptor *descriptor) const
  {
    trace_->create_calls++;
    trace_->descriptor_size = descriptor->size;
    trace_->descriptor_usage = descriptor->usage;
    trace_->descriptor_mapped = descriptor->mappedAtCreation;
    trace_->descriptor_label = descriptor->label ? descriptor->label : "";
    return Buffer(trace_, trace_->create_success);
  }

 private:
  std::shared_ptr<Trace> trace_;
  bool valid_ = false;
};

}  // namespace create_mock

static create_mock::BufferUsage create_usage_flags(const BufferKind kind,
                                                   UsageType /*usage*/,
                                                   const bool readable)
{
  using Usage = create_mock::BufferUsage;
  Usage result = Usage::CopyDst;
  switch (kind) {
    case BufferKind::Vertex:
      result = result | Usage::Vertex | Usage::Storage;
      break;
    case BufferKind::Index:
      result = result | Usage::Index | Usage::Storage;
      break;
    case BufferKind::Uniform:
      result = result | Usage::Uniform | Usage::Storage;
      break;
    case BufferKind::Storage:
      result = result | Usage::Storage | Usage::Indirect;
      break;
  }
  if (readable) {
    result = result | Usage::CopySrc;
  }
  return result;
}

class BufferCreateHarness {
 public:
  struct Allocation {
    create_mock::Buffer handle;
    size_t size = 0;
    size_t requested = 0;
    BufferKind kind = BufferKind::Vertex;
    bool readable = false;

    bool operator==(std::nullptr_t) const
    {
      return handle == nullptr;
    }
    bool operator!=(std::nullptr_t) const
    {
      return handle != nullptr;
    }
  };

  class Cache {
   public:
    template<typename CreateFn, typename SettledFn>
    Allocation get_or_create(const create_mock::Instance & /*instance*/,
                             const create_mock::Device & /*device*/,
                             const uint8_t /*key*/,
                             const char *label,
                             CreateFn &&create,
                             SettledFn &&settled)
    {
      if (published_ != nullptr) {
        return published_;
      }
      if (pending_) {
        return {};
      }
      pending_ = true;
      label_ = label ? label : "";
      candidate_ = std::forward<CreateFn>(create)();
      settled_ = std::forward<SettledFn>(settled);
      if (settle_immediately_) {
        settle(immediate_scope_valid_);
      }
      return published_;
    }

    Allocation lookup(const uint8_t /*key*/) const
    {
      return published_;
    }

    bool pending(const uint8_t /*key*/) const
    {
      return pending_;
    }

    void defer()
    {
      settle_immediately_ = false;
    }

    void settle(const bool scope_valid)
    {
      if (!pending_) {
        return;
      }
      pending_ = false;
      if (scope_valid && candidate_ != nullptr) {
        published_ = std::move(candidate_);
      }
      candidate_ = {};
      if (settled_) {
        settled_(published_);
      }
    }

    const std::string &label() const
    {
      return label_;
    }

   private:
    Allocation published_;
    Allocation candidate_;
    bool pending_ = false;
    bool settle_immediately_ = true;
    bool immediate_scope_valid_ = true;
    std::string label_;
    std::function<void(Allocation)> settled_;
  };

  struct PendingUpdateContext {};

  static bool update_allocation(PendingUpdateContext,
                                const Allocation &,
                                size_t,
                                const void *,
                                size_t,
                                std::function<void(bool)> complete)
  {
    complete(true);
    return true;
  }

  bool create_scoped(const create_mock::Instance &instance,
                     const create_mock::Device &device,
                     BufferKind kind,
                     UsageType usage,
                     size_t size,
                     const void *initial_data,
                     bool readable,
                     const char *label = nullptr);

  bool valid() const
  {
    return allocation_cache_.lookup(kAllocationKey) != nullptr;
  }
  bool pending() const
  {
    return allocation_cache_.pending(kAllocationKey);
  }
  Allocation allocation() const
  {
    return allocation_cache_.lookup(kAllocationKey);
  }
  void defer()
  {
    allocation_cache_.defer();
  }
  void settle(const bool scope_valid)
  {
    allocation_cache_.settle(scope_valid);
  }
  const std::string &label() const
  {
    return allocation_cache_.label();
  }

 private:
  static constexpr uint8_t kAllocationKey = 0;
  Cache allocation_cache_;
  std::shared_ptr<PendingBufferPayloadQueue<PendingUpdateContext>> pending_updates_ =
      std::make_shared<PendingBufferPayloadQueue<PendingUpdateContext>>();
};

static size_t buffer_redraw_retry_count = 0;

static void request_webgpu_redraw_retry()
{
  buffer_redraw_retry_count++;
}

/* Execute the exact shipping method with deterministic handles and deferred scope status. */
#define wgpu create_mock
#define usage_flags create_usage_flags
#include BW_WGPU_BUFFER_CREATE_SOURCE
#undef usage_flags
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

}  // namespace

bool run_integrated_buffer_create_contracts()
{
  buffer_redraw_retry_count = 0;
  const std::array<uint8_t, 6> payload = {0x10, 0x21, 0x32, 0x43, 0x54, 0x65};
  size_t cases = 0;
  size_t creates = 0;

  {
    auto trace = std::make_shared<create_mock::Trace>();
    BufferCreateHarness buffer;
    if (!require(!buffer.create_scoped(create_mock::Instance(false),
                                       create_mock::Device(trace),
                                       BufferKind::Index,
                                       UsageType::Static,
                                       payload.size(),
                                       payload.data(),
                                       true),
                 "null instance is rejected") ||
        !require(trace->limit_calls == 0 && trace->create_calls == 0,
                 "null instance performs no device work"))
    {
      return false;
    }
    cases++;
  }
  {
    auto trace = std::make_shared<create_mock::Trace>();
    BufferCreateHarness buffer;
    if (!require(!buffer.create_scoped(create_mock::Instance(),
                                       create_mock::Device(trace, false),
                                       BufferKind::Index,
                                       UsageType::Static,
                                       payload.size(),
                                       payload.data(),
                                       true),
                 "null device is rejected") ||
        !require(trace->limit_calls == 0 && trace->create_calls == 0,
                 "null device performs no allocation work"))
    {
      return false;
    }
    cases++;
  }
  {
    auto trace = std::make_shared<create_mock::Trace>();
    trace->max_buffer_size = 7;
    BufferCreateHarness buffer;
    if (!require(!buffer.create_scoped(create_mock::Instance(),
                                       create_mock::Device(trace),
                                       BufferKind::Index,
                                       UsageType::Static,
                                       payload.size(),
                                       payload.data(),
                                       true),
                 "rounded allocation over the device limit is rejected") ||
        !require(trace->limit_calls == 1 && trace->create_calls == 0,
                 "limit rejection precedes allocation"))
    {
      return false;
    }
    cases++;
  }
  {
    auto trace = std::make_shared<create_mock::Trace>();
    trace->create_success = false;
    BufferCreateHarness buffer;
    if (!require(!buffer.create_scoped(create_mock::Instance(),
                                       create_mock::Device(trace),
                                       BufferKind::Index,
                                       UsageType::Static,
                                       payload.size(),
                                       payload.data(),
                                       true),
                 "null allocation remains unpublished") ||
        !require(!buffer.valid() && !buffer.pending(),
                 "null allocation settles without state") ||
        !require(trace->create_calls == 1 && trace->map_calls == 0,
                 "null allocation stops before mapping"))
    {
      return false;
    }
    creates += trace->create_calls;
    cases++;
  }
  {
    auto trace = std::make_shared<create_mock::Trace>();
    trace->map_success = false;
    BufferCreateHarness buffer;
    if (!require(!buffer.create_scoped(create_mock::Instance(),
                                       create_mock::Device(trace),
                                       BufferKind::Index,
                                       UsageType::Static,
                                       payload.size(),
                                       payload.data(),
                                       true),
                 "missing mapped range remains unpublished") ||
        !require(trace->create_calls == 1 && trace->map_calls == 1 &&
                     trace->unmap_calls == 0,
                 "map failure stops before unmap"))
    {
      return false;
    }
    creates += trace->create_calls;
    cases++;
  }
  {
    auto trace = std::make_shared<create_mock::Trace>();
    BufferCreateHarness buffer;
    buffer.defer();
    const create_mock::Instance instance;
    const create_mock::Device device(trace);
    if (!require(!buffer.create_scoped(instance,
                                       device,
                                       BufferKind::Index,
                                       UsageType::Static,
                                       payload.size(),
                                       payload.data(),
                                       true,
                                       "persistent index buffer"),
                 "candidate remains unpublished while scopes are pending") ||
        !require(buffer.pending() && !buffer.valid() && buffer.allocation().size == 0,
                 "pending candidate exposes no resource metadata") ||
        !require(!buffer.create_scoped(instance,
                                       device,
                                       BufferKind::Index,
                                       UsageType::Static,
                                       payload.size(),
                                       payload.data(),
                                       true,
                                       "persistent index buffer"),
                 "duplicate pending create remains unavailable") ||
        !require(trace->create_calls == 1, "pending allocation deduplicates") ||
        !require(buffer.label() == "persistent index buffer", "scope label is preserved"))
    {
      return false;
    }

    buffer.settle(false);
    if (!require(!buffer.pending() && !buffer.valid(),
                 "scope rejection discards the non-null candidate") ||
        !require(buffer_redraw_retry_count == 0,
                 "rejected allocation publishes no redraw readiness"))
    {
      return false;
    }

    trace->mapped_bytes.clear();
    if (!require(!buffer.create_scoped(instance,
                                       device,
                                       BufferKind::Index,
                                       UsageType::Static,
                                       payload.size(),
                                       payload.data(),
                                       true,
                                       "persistent index buffer"),
                 "clean retry remains pending until its scope settles") ||
        !require(trace->create_calls == 2, "rejected key retries exactly once"))
    {
      return false;
    }
    buffer.settle(true);
    const BufferCreateHarness::Allocation allocation = buffer.allocation();
    const auto expected_usage = create_usage_flags(BufferKind::Index, UsageType::Static, true);
    if (!require(buffer.valid() && !buffer.pending(), "clean retry publishes") ||
        !require(buffer_redraw_retry_count == 1,
                 "accepted allocation publishes one redraw readiness edge") ||
        !require(allocation.size == 8 && allocation.requested == payload.size() &&
                     allocation.kind == BufferKind::Index && allocation.readable,
                 "resource metadata publishes atomically") ||
        !require(trace->descriptor_size == 8 && trace->descriptor_usage == expected_usage &&
                     trace->descriptor_mapped && trace->descriptor_label ==
                         "persistent index buffer",
                 "persistent descriptor is exact") ||
        !require(trace->map_calls == 2 && trace->unmap_calls == 2 &&
                     trace->mapped_bytes.size() == 8 &&
                     std::equal(payload.begin(), payload.end(), trace->mapped_bytes.begin()) &&
                     trace->mapped_bytes[6] == 0 && trace->mapped_bytes[7] == 0,
                 "mapped upload preserves bytes and zero tail"))
    {
      return false;
    }
    creates += trace->create_calls;
    cases++;
  }

  std::printf(
      "CONTRACT persistent-buffer-publication PASS cases=%zu creates=%zu pending=deduplicated failure=retry readiness=one bytes=%zu allocation=8\n",
      cases,
      creates,
      payload.size());
  return cases == 6 && creates == 4 && buffer_redraw_retry_count == 1;
}

}  // namespace blender::gpu::webgpu

namespace blender::gpu {

namespace pending_frontend_mock {

using BufferKind = webgpu::BufferKind;
using BufferUpdatePayload = webgpu::BufferUpdatePayload;
using BufferUpdateTransaction = webgpu::BufferUpdateTransaction;
using UsageType = webgpu::UsageType;
using webgpu::align_up;
using webgpu::buffer_update_payload;
using webgpu::kCopyAlignment;

struct Trace {
  struct Write {
    size_t sequence = 0;
    size_t offset = 0;
    std::vector<uint8_t> bytes;
  };

  size_t creates = 0;
  size_t next_sequence = 0;
  bool upload_valid = true;
  std::vector<Write> writes;
};

struct Instance {};
struct Device {};
struct Queue {};
struct Scheduler {};

class Buffer {
 public:
  explicit Buffer(std::shared_ptr<Trace> trace) : trace_(std::move(trace)) {}

  bool valid() const
  {
    return valid_;
  }

  bool creation_pending_or_retryable() const
  {
    return pending_ || payloads_.retryable();
  }

  size_t update_capacity() const
  {
    return allocation_size_;
  }

  template<typename InstanceT, typename DeviceT>
  bool create_scoped(const InstanceT &,
                     const DeviceT &,
                     BufferKind,
                     UsageType,
                     const size_t size,
                     const void *,
                     bool,
                     const char *)
  {
    allocation_size_ = std::max<size_t>(kCopyAlignment, align_up(size, kCopyAlignment));
    if (!payloads_.begin(allocation_size_)) {
      return false;
    }
    if (valid_) {
      return true;
    }
    if (!pending_) {
      pending_ = true;
      trace_->creates++;
    }
    return false;
  }

  template<typename InstanceT,
           typename DeviceT,
           typename QueueT,
           typename SchedulerT>
  bool update_sub(const InstanceT &instance,
                  const DeviceT &device,
                  const QueueT &queue,
                  SchedulerT &scheduler,
                  const size_t offset,
                  const void *data,
                  const size_t size)
  {
    BufferUpdateTransaction transaction;
    return update_sub(instance, device, queue, scheduler, offset, data, size, transaction);
  }

  template<typename InstanceT,
           typename DeviceT,
           typename QueueT,
           typename SchedulerT>
  bool update_sub(const InstanceT &,
                  const DeviceT &,
                  const QueueT &,
                  SchedulerT &,
                  const size_t offset,
                  const void *data,
                  const size_t size,
                  BufferUpdateTransaction &transaction)
  {
    const size_t sequence = trace_->next_sequence++;
    if (!payloads_.retain(sequence, offset, data, size, &transaction)) {
      return false;
    }
    retry_pending_updates();
    return transaction.accepted();
  }

  size_t retry_pending_updates()
  {
    if (!valid_) {
      return 0;
    }
    return payloads_.replay(
        allocation_size_,
        [this](const size_t sequence,
               const size_t offset,
               const void *data,
               const size_t size,
               std::function<void(bool)> complete) {
          record(sequence, offset, data, size);
          complete(trace_->upload_valid);
          return true;
        });
  }

  void settle(const bool accepted)
  {
    if (!pending_) {
      return;
    }
    pending_ = false;
    if (!accepted) {
      return;
    }
    valid_ = true;
    payloads_.replay(
        allocation_size_,
        [this](const size_t sequence,
               const size_t offset,
               const void *data,
               const size_t size,
               std::function<void(bool)> complete) {
          record(sequence, offset, data, size);
          complete(trace_->upload_valid);
          return true;
        });
  }

  size_t retained() const
  {
    return payloads_.size();
  }

 private:
  void record(const size_t sequence, const size_t offset, const void *data, const size_t size)
  {
    Trace::Write write;
    write.sequence = sequence;
    write.offset = offset;
    const uint8_t *source = static_cast<const uint8_t *>(data);
    write.bytes.assign(source, source + size);
    trace_->writes.push_back(std::move(write));
  }

  std::shared_ptr<Trace> trace_;
  webgpu::PendingBufferPayloadQueue<size_t> payloads_;
  size_t allocation_size_ = 0;
  bool pending_ = false;
  bool valid_ = false;
};

}  // namespace pending_frontend_mock

enum GPUUsageType : uint8_t {
  GPU_USAGE_STATIC,
  GPU_USAGE_DEVICE_ONLY,
};

class PendingFrontendContext {
 public:
  pending_frontend_mock::Instance instance_get() const
  {
    return {};
  }
  pending_frontend_mock::Device device_get() const
  {
    return {};
  }
  pending_frontend_mock::Queue queue_get() const
  {
    return {};
  }
  pending_frontend_mock::Scheduler &queue_scheduler_get()
  {
    return scheduler_;
  }

  template<typename BufferT> void storage_buffer_bind(const int slot, BufferT *buffer)
  {
    storage_bind_slot = slot;
    storage_bind_pointer = buffer;
    storage_bind_count++;
  }

  int storage_bind_slot = -1;
  const void *storage_bind_pointer = nullptr;
  size_t storage_bind_count = 0;

 private:
  pending_frontend_mock::Scheduler scheduler_;
};

static PendingFrontendContext *pending_frontend_context = nullptr;

static PendingFrontendContext *pending_active_context()
{
  return pending_frontend_context;
}

class StorageFrontendHarness {
 public:
  StorageFrontendHarness(const size_t size,
                         const GPUUsageType usage,
                         std::shared_ptr<pending_frontend_mock::Trace> trace)
      : size_in_bytes_(size),
        usage_size_in_bytes_(size),
        usage_(usage),
        label_("pending storage frontend"),
        buffer_(std::move(trace))
  {
  }

  bool ensure();
  void update(const void *data);
  void clear(uint32_t clear_value);
  void bind(int slot);

  void settle(const bool accepted)
  {
    buffer_.settle(accepted);
  }
  size_t retained() const
  {
    return buffer_.retained();
  }
  bool valid() const
  {
    return buffer_.valid();
  }

 private:
  size_t size_in_bytes_ = 0;
  size_t usage_size_in_bytes_ = 0;
  GPUUsageType usage_ = GPU_USAGE_STATIC;
  std::string label_;
  pending_frontend_mock::Buffer buffer_;
};

class UniformFrontendHarness {
 public:
  UniformFrontendHarness(const size_t size,
                         std::shared_ptr<pending_frontend_mock::Trace> trace)
      : size_in_bytes_(size), label_("pending uniform frontend"), buffer_(std::move(trace))
  {
  }

  ~UniformFrontendHarness()
  {
    delete[] static_cast<uint8_t *>(data_);
  }

  bool ensure();
  bool ensure_updated();
  void update(const void *data);
  void clear_to_zero();

  void attach_for_test(const void *data)
  {
    delete[] static_cast<uint8_t *>(data_);
    uint8_t *owned = new uint8_t[size_in_bytes_];
    std::memcpy(owned, data, size_in_bytes_);
    data_ = owned;
  }
  bool has_attached_data() const
  {
    return data_ != nullptr;
  }
  void settle(const bool accepted)
  {
    buffer_.settle(accepted);
  }
  size_t retained() const
  {
    return buffer_.retained();
  }

 private:
  size_t size_in_bytes_ = 0;
  void *data_ = nullptr;
  std::string label_;
  pending_frontend_mock::Buffer buffer_;
  pending_frontend_mock::BufferUpdateTransaction deferred_upload_transaction_;
};

static constexpr size_t kUboMinBindingPad = 16384;

#define WGPUContext PendingFrontendContext
#define active_context pending_active_context
#define webgpu pending_frontend_mock
#define WGPUStorageBuffer StorageFrontendHarness
#define WGPUUniformBuffer UniformFrontendHarness
#define MEM_SAFE_DELETE_VOID(value) \
  do { \
    delete[] static_cast<uint8_t *>(value); \
    value = nullptr; \
  } while (false)
#include BW_WGPU_PENDING_PAYLOAD_FRONTEND_SOURCE
#undef MEM_SAFE_DELETE_VOID
#undef WGPUUniformBuffer
#undef WGPUStorageBuffer
#undef webgpu
#undef active_context
#undef WGPUContext

}  // namespace blender::gpu

namespace blender::gpu::webgpu {

bool run_pending_buffer_payload_contracts()
{
  using pending_frontend_mock::Trace;
  constexpr std::array<uint8_t, 8> storage_a = {0x10, 0x21, 0x32, 0x43,
                                                0x54, 0x65, 0x76, 0x87};
  constexpr std::array<uint8_t, 8> storage_b = {0xa8, 0xb9, 0xca, 0xdb,
                                                0xec, 0xfd, 0x0e, 0x1f};
  constexpr std::array<uint8_t, 16> uniform_a = {0x01, 0x12, 0x23, 0x34,
                                                 0x45, 0x56, 0x67, 0x78,
                                                 0x89, 0x9a, 0xab, 0xbc,
                                                 0xcd, 0xde, 0xef, 0xf0};
  constexpr std::array<uint8_t, 16> uniform_b = {0xf0, 0xe1, 0xd2, 0xc3,
                                                 0xb4, 0xa5, 0x96, 0x87,
                                                 0x78, 0x69, 0x5a, 0x4b,
                                                 0x3c, 0x2d, 0x1e, 0x0f};
  PendingFrontendContext context;
  pending_frontend_context = &context;
  size_t cases = 0;
  size_t payloads = 0;
  size_t creates = 0;

  {
    auto trace = std::make_shared<Trace>();
    StorageFrontendHarness storage(storage_a.size(), GPU_USAGE_STATIC, trace);
    storage.update(storage_a.data());
    storage.clear(0x44332211u);
    storage.update(storage_b.data());
    if (!require(trace->creates == 1 && trace->writes.empty() && storage.retained() == 3,
                 "storage frontend retains every pending payload"))
    {
      return false;
    }
    storage.settle(true);
    storage.settle(true);
    const std::array<uint8_t, 8> clear_bytes = {0x11, 0x22, 0x33, 0x44,
                                                0x11, 0x22, 0x33, 0x44};
    if (!require(trace->writes.size() == 3 && trace->writes[0].sequence == 0 &&
                     trace->writes[1].sequence == 1 && trace->writes[2].sequence == 2,
                 "storage pending payloads replay exactly once in order") ||
        !require(trace->writes[0].bytes ==
                         std::vector<uint8_t>(storage_a.begin(), storage_a.end()) &&
                     trace->writes[1].bytes ==
                         std::vector<uint8_t>(clear_bytes.begin(), clear_bytes.end()) &&
                     trace->writes[2].bytes ==
                         std::vector<uint8_t>(storage_b.begin(), storage_b.end()),
                 "storage replay preserves sentinel bytes"))
    {
      return false;
    }
    payloads += trace->writes.size();
    creates += trace->creates;
    cases++;
  }

  {
    auto trace = std::make_shared<Trace>();
    StorageFrontendHarness storage(storage_a.size(), GPU_USAGE_STATIC, trace);
    storage.bind(7);
    if (!require(trace->creates == 1 && !storage.valid() &&
                     context.storage_bind_count == 1 && context.storage_bind_slot == 7 &&
                     context.storage_bind_pointer == &storage,
                 "storage bind intent survives pending browser allocation"))
    {
      return false;
    }
    storage.settle(true);
    if (!require(storage.valid() && context.storage_bind_count == 1 &&
                     context.storage_bind_pointer == &storage,
                 "accepted allocation publishes behind the retained bind intent"))
    {
      return false;
    }
    creates += trace->creates;
    cases++;
  }

  {
    auto trace = std::make_shared<Trace>();
    StorageFrontendHarness storage(storage_a.size(), GPU_USAGE_STATIC, trace);
    storage.update(storage_a.data());
    storage.settle(false);
    if (!require(trace->writes.empty() && storage.retained() == 1,
                 "rejected allocation retains the one-shot frontend payload") ||
        !require(!storage.ensure() && trace->creates == 2,
                 "later resource use starts one clean allocation retry"))
    {
      return false;
    }
    storage.settle(true);
    if (!require(trace->writes.size() == 1 && trace->writes[0].bytes ==
                                                   std::vector<uint8_t>(storage_a.begin(),
                                                                        storage_a.end()),
                 "accepted retry replays without a second frontend update"))
    {
      return false;
    }
    payloads += trace->writes.size();
    creates += trace->creates;
    cases++;
  }

  {
    auto trace = std::make_shared<Trace>();
    UniformFrontendHarness uniform(uniform_a.size(), trace);
    uniform.update(uniform_a.data());
    uniform.clear_to_zero();
    uniform.update(uniform_b.data());
    if (!require(trace->creates == 1 && trace->writes.empty() && uniform.retained() == 3,
                 "uniform frontend retains update clear update order"))
    {
      return false;
    }
    uniform.settle(true);
    const std::vector<uint8_t> zeros(uniform_a.size(), uint8_t(0));
    if (!require(trace->writes.size() == 3 &&
                     trace->writes[0].bytes ==
                         std::vector<uint8_t>(uniform_a.begin(), uniform_a.end()) &&
                     trace->writes[1].bytes == zeros &&
                     trace->writes[2].bytes ==
                         std::vector<uint8_t>(uniform_b.begin(), uniform_b.end()),
                 "uniform pending payloads replay once with exact bytes"))
    {
      return false;
    }
    payloads += trace->writes.size();
    creates += trace->creates;
    cases++;
  }

  {
    auto trace = std::make_shared<Trace>();
    UniformFrontendHarness uniform(uniform_a.size(), trace);
    uniform.attach_for_test(uniform_b.data());
    trace->upload_valid = false;
    if (!require(!uniform.ensure_updated() && uniform.has_attached_data() &&
                     uniform.retained() == 1,
                 "attached uniform ownership remains pending until upload acceptance"))
    {
      return false;
    }
    uniform.settle(true);
    if (!require(uniform.has_attached_data() && trace->writes.size() == 1 &&
                     trace->writes[0].bytes ==
                                                   std::vector<uint8_t>(uniform_b.begin(),
                                                                        uniform_b.end()),
                 "rejected upload preserves the host owner and exact attempted bytes") ||
        !require(uniform.retained() == 1,
                 "rejected deferred upload remains retryable with its owner intact"))
    {
      return false;
    }
    trace->upload_valid = true;
    if (!require(uniform.ensure_updated() && !uniform.has_attached_data() &&
                     trace->writes.size() == 2 &&
                     trace->writes[1].bytes ==
                         std::vector<uint8_t>(uniform_b.begin(), uniform_b.end()) &&
                     uniform.retained() == 0,
                 "attached uniform ownership commits only after a clean accepted retry"))
    {
      return false;
    }
    payloads += trace->writes.size();
    creates += trace->creates;
    cases++;
  }

  {
    constexpr std::array<uint8_t, 4> payload_e1 = {0x11, 0x12, 0x13, 0x14};
    constexpr std::array<uint8_t, 4> payload_e2 = {0x21, 0x22, 0x23, 0x24};
    constexpr std::array<uint8_t, 4> payload_e3 = {0x31, 0x32, 0x33, 0x34};
    PendingBufferPayloadQueue<size_t> queue;
    BufferUpdateTransaction transaction_e1;
    BufferUpdateTransaction transaction_e2;
    BufferUpdateTransaction transaction_e3;
    OrderedQueueScheduler scheduler;
    std::array<uint8_t, 4> device_bytes = {};
    std::vector<size_t> reservation_order;
    std::vector<size_t> execution_order;
    std::mutex result_mutex;
    std::mutex barrier_mutex;
    std::condition_variable barrier_cv;
    bool first_reserved = false;
    bool concurrent_replay_done = false;
    bool concurrent_retain_ok = false;
    size_t concurrent_started = size_t(-1);

    if (!require(queue.begin(device_bytes.size()) &&
                     queue.retain(
                         1, 0, payload_e1.data(), payload_e1.size(), &transaction_e1) &&
                     queue.retain(
                         2, 0, payload_e2.data(), payload_e2.size(), &transaction_e2),
                 "concurrent replay fixture retains E1 and E2"))
    {
      return false;
    }

    auto reserve_payload = [&](const size_t sequence,
                               const size_t offset,
                               const void *data,
                               const size_t size,
                               std::function<void(bool)> complete) {
      OrderedQueueScheduler::Ticket ticket = scheduler.reserve();
      {
        std::lock_guard lock(result_mutex);
        reservation_order.push_back(sequence);
      }
      if (sequence == 1) {
        std::unique_lock lock(barrier_mutex);
        first_reserved = true;
        barrier_cv.notify_all();
        barrier_cv.wait(lock, [&] { return concurrent_replay_done; });
      }
      const uint8_t *source = static_cast<const uint8_t *>(data);
      std::vector<uint8_t> owned(source, source + size);
      ticket.resolve(
          [&, sequence, offset, owned = std::move(owned), complete = std::move(complete)](
              std::function<void(bool)> done) mutable {
            {
              std::lock_guard lock(result_mutex);
              execution_order.push_back(sequence);
              std::copy(owned.begin(), owned.end(), device_bytes.begin() + offset);
            }
            complete(true);
            done(true);
          });
      return true;
    };

    std::thread concurrent_replay([&] {
      {
        std::unique_lock lock(barrier_mutex);
        barrier_cv.wait(lock, [&] { return first_reserved; });
      }
      concurrent_retain_ok = queue.retain(
          3, 0, payload_e3.data(), payload_e3.size(), &transaction_e3);
      concurrent_started = queue.replay(device_bytes.size(), reserve_payload);
      {
        std::lock_guard lock(barrier_mutex);
        concurrent_replay_done = true;
      }
      barrier_cv.notify_all();
    });
    const size_t primary_started = queue.replay(device_bytes.size(), reserve_payload);
    concurrent_replay.join();

    const std::vector<size_t> expected_order = {1, 2, 3};
    if (!require(concurrent_retain_ok && primary_started == 3 && concurrent_started == 0,
                 "one replay drainer reserves the complete concurrent batch") ||
        !require(reservation_order == expected_order && execution_order == expected_order,
                 "concurrent payload replay preserves frontend FIFO") ||
        !require(device_bytes == payload_e3,
                 "latest overlapping payload remains the final device bytes") ||
        !require(transaction_e1.accepted() && transaction_e2.accepted() &&
                     transaction_e3.accepted() && queue.size() == 0 && !queue.retryable() &&
                     scheduler.pending_count() == 0,
                 "serialized replay accepts every payload exactly once"))
    {
      return false;
    }
    payloads += execution_order.size();
    cases++;
  }

  pending_frontend_context = nullptr;
  std::printf(
      "CONTRACT pending-buffer-payload PASS cases=%zu creates=%zu payloads=%zu order=fifo "
      "retry=retained bind_intent=pending concurrent_drainer=one final=E3\n",
      cases,
      creates,
      payloads);
  return cases == 6 && creates == 6 && payloads == 12;
}

}  // namespace blender::gpu::webgpu
