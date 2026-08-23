/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm contract for the exact persistent Buffer::create_scoped state machine.
 * Fake error scopes can remain pending after the creating stack returns, matching browser WebGPU. */

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>
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
    template<typename CreateFn>
    Allocation get_or_create(const create_mock::Instance & /*instance*/,
                             const create_mock::Device & /*device*/,
                             const uint8_t /*key*/,
                             const char *label,
                             CreateFn &&create)
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
  };

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
};

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
                 "scope rejection discards the non-null candidate"))
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
      "CONTRACT persistent-buffer-publication PASS cases=%zu creates=%zu pending=deduplicated failure=retry bytes=%zu allocation=8\n",
      cases,
      creates,
      payload.size());
  return cases == 6 && creates == 4;
}

}  // namespace blender::gpu::webgpu
