/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm regression for the exact Blender vertex mutation and
 * WebGPU VBO/float-buffer-texture upload frontends. */

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <functional>
#include <string>
#include <utility>
#include <vector>

#include "wgpu_common.hh"

#ifndef BW_WGPU_VERTEX_UPLOAD_FRONTEND_SOURCE
#  error "BW_WGPU_VERTEX_UPLOAD_FRONTEND_SOURCE must name the extracted shipping methods"
#endif

namespace blender::gpu::vertex_generation_contract {

using uint = unsigned int;
using uchar = unsigned char;

enum GPUVertBufStatus : uint32_t {
  GPU_VERTBUF_INVALID = 0,
  GPU_VERTBUF_INIT = 1u << 0,
  GPU_VERTBUF_DATA_DIRTY = 1u << 1,
  GPU_VERTBUF_DATA_UPLOADED = 1u << 2,
};

enum GPUUsageType : uint8_t {
  GPU_USAGE_STREAM = 0,
  GPU_USAGE_STATIC = 1,
  GPU_USAGE_DYNAMIC = 2,
  GPU_USAGE_DEVICE_ONLY = 3,
};

enum GPUCompType : uint8_t {
  GPU_COMP_F32,
};

struct GPUVertAttrType {
  GPUCompType component_type = GPU_COMP_F32;
  uint component_len = 1;

  GPUCompType comp_type() const
  {
    return component_type;
  }

  uint comp_len() const
  {
    return component_len;
  }

  size_t size() const
  {
    return size_t(component_len) * sizeof(float);
  }
};

struct GPUVertAttr {
  GPUVertAttrType type;
  uint8_t offset = 0;
};

struct GPUVertFormat {
  uint attr_len = 1;
  uint stride = sizeof(float);
  bool deinterleaved = false;
  std::array<GPUVertAttr, 1> attrs{};
};

struct Trace {
  struct Write {
    size_t sequence = 0;
    std::string target;
    size_t offset = 0;
    std::vector<uint8_t> bytes;
  };

  size_t next_sequence = 0;
  size_t binds = 0;
  size_t pending_binds = 0;
  size_t hard_missing_binds = 0;
  size_t readback_redraws = 0;
  std::vector<uint8_t> bound_bytes;
  std::vector<Write> writes;
};

namespace webgpu {

using BufferUpdatePayload = ::blender::gpu::webgpu::BufferUpdatePayload;
using BufferUpdateTransaction = ::blender::gpu::webgpu::BufferUpdateTransaction;
using ::blender::gpu::webgpu::buffer_update_payload;

enum class BufferKind : uint8_t {
  Vertex,
  Storage,
};

enum class UsageType : uint8_t {
  Stream,
  Static,
  Dynamic,
  DeviceOnly,
};

struct Instance {};
struct Device {};
struct Queue {};
struct Scheduler {};

class Buffer {
 public:
  Buffer() = default;

  void prime(Trace &trace,
             std::string target,
             const size_t capacity,
             const std::vector<uint8_t> &initial)
  {
    trace_ = &trace;
    target_ = std::move(target);
    capacity_ = capacity;
    valid_ = true;
    device_bytes_.assign(capacity_, 0);
    std::copy_n(initial.begin(), std::min(initial.size(), device_bytes_.size()),
                device_bytes_.begin());
    pending_ = ::blender::gpu::webgpu::PendingBufferPayloadQueue<int>();
    pending_.begin(capacity_);
  }

  bool valid() const
  {
    return valid_;
  }

  bool creation_pending_or_retryable() const
  {
    return creation_pending_ || pending_.retryable();
  }

  void mark_creation_pending()
  {
    valid_ = false;
    creation_pending_ = true;
  }

  void settle_creation(const bool accepted)
  {
    creation_pending_ = false;
    valid_ = accepted;
  }

  size_t size() const
  {
    return capacity_;
  }

  void defer_updates(const bool defer)
  {
    defer_updates_ = defer;
  }

  size_t pending_completions() const
  {
    return completions_.size();
  }

  void settle_next(const bool accepted)
  {
    if (completions_.empty()) {
      return;
    }
    std::function<void(bool)> completion = std::move(completions_.front());
    completions_.pop_front();
    completion(accepted);
  }

  const std::vector<uint8_t> &device_bytes() const
  {
    return device_bytes_;
  }

  void defer_readback()
  {
    readback_pending_ = true;
    readback_failed_ = false;
  }

  void settle_readback(const bool accepted)
  {
    readback_pending_ = false;
    readback_failed_ = !accepted;
    if (accepted && trace_ != nullptr) {
      trace_->readback_redraws++;
    }
  }

  template<typename InstanceT, typename DeviceT>
  bool create_scoped(const InstanceT &,
                     const DeviceT &,
                     BufferKind,
                     UsageType,
                     const size_t size,
                     const void *data,
                     bool,
                     const char *)
  {
    if (trace_ == nullptr || size == 0) {
      return false;
    }
    capacity_ = size;
    valid_ = true;
    device_bytes_.assign(size, 0);
    if (data != nullptr) {
      std::memcpy(device_bytes_.data(), data, size);
    }
    pending_ = ::blender::gpu::webgpu::PendingBufferPayloadQueue<int>();
    return pending_.begin(capacity_);
  }

  template<typename InstanceT, typename DeviceT, typename QueueT, typename SchedulerT>
  bool update_sub(const InstanceT &,
                  const DeviceT &,
                  const QueueT &,
                  SchedulerT &,
                  const size_t offset,
                  const void *data,
                  const size_t size,
                  BufferUpdateTransaction &transaction)
  {
    if (!valid_ || trace_ == nullptr ||
        !pending_.retain(0, offset, data, size, &transaction))
    {
      return false;
    }
    retry_pending_updates();
    return transaction.accepted();
  }

  size_t retry_pending_updates()
  {
    if (!valid_ || trace_ == nullptr) {
      return 0;
    }
    return pending_.replay(
        capacity_,
        [this](const int &,
               const size_t offset,
               const void *data,
               const size_t size,
               std::function<void(bool)> complete) {
          const uint8_t *source = static_cast<const uint8_t *>(data);
          std::vector<uint8_t> bytes(source, source + size);
          trace_->writes.push_back(
              Trace::Write{trace_->next_sequence++, target_, offset, bytes});
          auto settle = [this,
                         offset,
                         bytes = std::move(bytes),
                         complete = std::move(complete)](const bool accepted) mutable {
            if (accepted && offset <= device_bytes_.size() &&
                bytes.size() <= device_bytes_.size() - offset)
            {
              std::copy(bytes.begin(), bytes.end(), device_bytes_.begin() + offset);
            }
            complete(accepted);
          };
          if (defer_updates_) {
            completions_.push_back(std::move(settle));
          }
          else {
            settle(true);
          }
          return true;
        });
  }

  template<typename InstanceT, typename DeviceT, typename QueueT, typename SchedulerT>
  std::vector<uint8_t> read(const InstanceT &,
                            const DeviceT &,
                            const QueueT &,
                            SchedulerT &,
                            const size_t offset,
                            const size_t size,
                            bool *r_pending = nullptr) const
  {
    if (r_pending != nullptr) {
      *r_pending = readback_pending_;
    }
    if (readback_pending_ || readback_failed_) {
      return {};
    }
    if (!valid_ || offset > device_bytes_.size() || size > device_bytes_.size() - offset) {
      return {};
    }
    return std::vector<uint8_t>(device_bytes_.begin() + offset,
                                device_bytes_.begin() + offset + size);
  }

 private:
  Trace *trace_ = nullptr;
  std::string target_;
  size_t capacity_ = 0;
  bool valid_ = false;
  bool creation_pending_ = false;
  bool defer_updates_ = false;
  bool readback_pending_ = false;
  bool readback_failed_ = false;
  std::vector<uint8_t> device_bytes_;
  std::deque<std::function<void(bool)>> completions_;
  ::blender::gpu::webgpu::PendingBufferPayloadQueue<int> pending_;
};

}  // namespace webgpu

class WGPUContext {
 public:
  enum class BufferSSBOBindKind : uint8_t {
    Storage,
    Sampler,
  };

  explicit WGPUContext(Trace &trace) : trace_(&trace) {}

  webgpu::Instance instance_get() const
  {
    return {};
  }

  webgpu::Device device_get() const
  {
    return {};
  }

  webgpu::Queue queue_get() const
  {
    return {};
  }

  webgpu::Scheduler &queue_scheduler_get()
  {
    return scheduler_;
  }

  void buffer_ssbo_bind(int,
                        webgpu::Buffer *buffer,
                        BufferSSBOBindKind,
                        const webgpu::Buffer *pending_dependency = nullptr,
                        const bool pending_external = false)
  {
    const bool dependency_pending =
        pending_dependency != nullptr &&
        pending_dependency->creation_pending_or_retryable();
    if (pending_external || dependency_pending ||
        (!buffer->valid() && buffer->creation_pending_or_retryable()))
    {
      trace_->pending_binds++;
      return;
    }
    if (!buffer->valid()) {
      trace_->hard_missing_binds++;
      return;
    }
    trace_->binds++;
    trace_->bound_bytes = buffer->device_bytes();
  }

 private:
  Trace *trace_ = nullptr;
  webgpu::Scheduler scheduler_;
};

static WGPUContext *active_context_value = nullptr;

static WGPUContext *active_context()
{
  return active_context_value;
}

template<typename T> struct DataView {
  T *pointer = nullptr;

  T *data() const
  {
    return pointer;
  }
};

class VertexFrontendHarness {
 public:
  VertexFrontendHarness(Trace &trace,
                        const GPUUsageType usage,
                        const uint component_len,
                        const std::vector<uint8_t> &host,
                        const std::vector<uint8_t> &initial_device,
                        const bool dirty)
      : usage_(usage)
  {
    format.attr_len = 1;
    format.stride = component_len * sizeof(float);
    format.deinterleaved = false;
    format.attrs[0].type.component_len = component_len;
    format.attrs[0].offset = 0;
    vertex_len = vertex_alloc = uint(host.size() / format.stride);
    data_ = new uchar[host.size()];
    std::copy(host.begin(), host.end(), data_);
    flag = dirty ? GPU_VERTBUF_DATA_DIRTY : GPU_VERTBUF_DATA_UPLOADED;
    data_uploaded_ = !dirty;
    buffer_.prime(trace, "primary", host.size(), initial_device);
    buffer_texture_buffer_.prime(
        trace, "texture", size_t(vertex_len) * 4 * sizeof(float), {});
  }

  ~VertexFrontendHarness()
  {
    delete[] data_;
  }

  template<typename T> DataView<T> data()
  {
    return {reinterpret_cast<T *>(data_)};
  }

  GPUUsageType get_usage_type() const
  {
    return usage_;
  }

  size_t size_used_get() const
  {
    return size_t(vertex_len) * format.stride;
  }

  size_t size_alloc_get() const
  {
    return size_t(vertex_alloc) * format.stride;
  }

  void allocate() {}
  void upload_data();
  void bind_as_texture(uint binding);

  void defer_primary(const bool defer)
  {
    buffer_.defer_updates(defer);
  }

  void defer_texture(const bool defer)
  {
    buffer_texture_buffer_.defer_updates(defer);
  }

  void settle_primary(const bool accepted)
  {
    buffer_.settle_next(accepted);
  }

  void settle_texture(const bool accepted)
  {
    buffer_texture_buffer_.settle_next(accepted);
  }

  void mark_primary_creation_pending()
  {
    buffer_.mark_creation_pending();
  }

  void settle_primary_creation(const bool accepted)
  {
    buffer_.settle_creation(accepted);
  }

  void defer_primary_readback()
  {
    buffer_.defer_readback();
  }

  void settle_primary_readback(const bool accepted)
  {
    buffer_.settle_readback(accepted);
  }

  bool dirty() const
  {
    return (flag & GPU_VERTBUF_DATA_DIRTY) != 0;
  }

  bool host_data_present() const
  {
    return data_ != nullptr;
  }

  bool texture_dirty() const
  {
    return buffer_texture_buffer_dirty_;
  }

  size_t primary_pending() const
  {
    return buffer_.pending_completions();
  }

  size_t texture_pending() const
  {
    return buffer_texture_buffer_.pending_completions();
  }

  const std::vector<uint8_t> &primary_bytes() const
  {
    return buffer_.device_bytes();
  }

  const std::vector<uint8_t> &texture_bytes() const
  {
    return buffer_texture_buffer_.device_bytes();
  }

  GPUVertFormat format;
  uint vertex_len = 0;
  uint vertex_alloc = 0;
  uchar *data_ = nullptr;
  uint32_t flag = GPU_VERTBUF_INVALID;

 private:
  webgpu::Buffer buffer_;
  webgpu::Buffer buffer_texture_buffer_;
  bool buffer_texture_buffer_dirty_ = true;
  webgpu::BufferUpdateTransaction buffer_texture_upload_transaction_;
  bool data_uploaded_ = false;
  GPUUsageType usage_ = GPU_USAGE_STATIC;
  webgpu::BufferUpdateTransaction upload_transaction_;
};

static bool format_has_norm_i10(const GPUVertFormat &)
{
  return false;
}

static void transcode_i10_attrs(uint8_t *, size_t, const GPUVertFormat &, uint) {}

template<typename T, typename... Args> bool elem(const T value, const Args... args)
{
  return ((value == args) || ...);
}

}  // namespace blender::gpu::vertex_generation_contract

#ifdef ELEM
#  undef ELEM
#endif
#define ELEM(value, ...) \
  ::blender::gpu::vertex_generation_contract::elem(value, __VA_ARGS__)
#ifdef BLI_assert
#  undef BLI_assert
#endif
#define BLI_assert(condition)             \
  do {                                    \
    if (!(condition)) {                   \
      std::abort();                       \
    }                                     \
  } while (false)
#ifdef MEM_SAFE_DELETE
#  undef MEM_SAFE_DELETE
#endif
#define MEM_SAFE_DELETE(value) \
  do {                         \
    delete[] (value);          \
    (value) = nullptr;         \
  } while (false)
#include BW_WGPU_VERTEX_UPLOAD_FRONTEND_SOURCE
#undef MEM_SAFE_DELETE
#undef BLI_assert
#undef ELEM

namespace blender::gpu {
namespace {

using vertex_generation_contract::Trace;
using vertex_generation_contract::VertexFrontendHarness;

bool require_generation(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "FAIL vertex-upload-generation %s\n", message);
    return false;
  }
  return true;
}

template<size_t N> std::vector<uint8_t> bytes_of(const std::array<float, N> &values)
{
  std::vector<uint8_t> bytes(sizeof(values));
  std::memcpy(bytes.data(), values.data(), bytes.size());
  return bytes;
}

template<size_t N> std::vector<uint8_t> expanded_float_bytes(const std::array<float, N> &values)
{
  std::vector<float> expanded(values.size() * 4, 0.0f);
  for (size_t index = 0; index < values.size(); index++) {
    expanded[index * 4] = values[index];
    expanded[index * 4 + 3] = 1.0f;
  }
  std::vector<uint8_t> bytes(expanded.size() * sizeof(float));
  std::memcpy(bytes.data(), expanded.data(), bytes.size());
  return bytes;
}

bool ordinary_generation_contract()
{
  constexpr std::array<float, 4> sentinel_a = {1.25f, -2.5f, 3.75f, -4.0f};
  constexpr std::array<float, 4> sentinel_b = {-8.5f, 16.25f, -32.75f, 64.5f};
  const std::vector<uint8_t> bytes_a = bytes_of(sentinel_a);
  const std::vector<uint8_t> bytes_b = bytes_of(sentinel_b);
  Trace trace;
  vertex_generation_contract::WGPUContext context(trace);
  vertex_generation_contract::active_context_value = &context;
  VertexFrontendHarness vertex(
      trace, vertex_generation_contract::GPU_USAGE_STATIC, 4, bytes_a, {}, true);
  vertex.defer_primary(true);

  vertex.upload_data();
  if (!require_generation(trace.writes.size() == 1 &&
                              trace.writes[0].target == "primary" &&
                              trace.writes[0].bytes == bytes_a && !vertex.dirty() &&
                              vertex.host_data_present() && vertex.primary_pending() == 1,
                          "A scheduling consumes only A's dirty state"))
  {
    return false;
  }

  vertex_generation_contract::frontend_attr_set(&vertex, 0, 0, sentinel_b.data());
  if (!require_generation(vertex.dirty() && vertex.host_data_present(),
                          "frontend B mutation raises a new dirty state"))
  {
    return false;
  }

  vertex.settle_primary(true);
  vertex.upload_data();
  if (!require_generation(trace.writes.size() == 2 &&
                              trace.writes[1].target == "primary" &&
                              trace.writes[1].bytes == bytes_b && !vertex.dirty() &&
                              vertex.host_data_present() && vertex.primary_pending() == 1,
                          "A acceptance schedules B without freeing B"))
  {
    return false;
  }

  vertex.settle_primary(true);
  vertex.upload_data();
  vertex_generation_contract::active_context_value = nullptr;
  return require_generation(!vertex.dirty() && !vertex.host_data_present() &&
                                vertex.primary_pending() == 0 &&
                                vertex.primary_bytes() == bytes_b,
                            "B acceptance commits static host ownership exactly once");
}

bool float_texture_generation_contract()
{
  constexpr std::array<float, 2> sentinel_a = {0.125f, -7.5f};
  constexpr std::array<float, 2> sentinel_b = {31.75f, -63.125f};
  const std::vector<uint8_t> bytes_a = bytes_of(sentinel_a);
  const std::vector<uint8_t> bytes_b = bytes_of(sentinel_b);
  const std::vector<uint8_t> expanded_a = expanded_float_bytes(sentinel_a);
  const std::vector<uint8_t> expanded_b = expanded_float_bytes(sentinel_b);
  Trace trace;
  vertex_generation_contract::WGPUContext context(trace);
  vertex_generation_contract::active_context_value = &context;
  VertexFrontendHarness vertex(
      trace, vertex_generation_contract::GPU_USAGE_DYNAMIC, 1, bytes_a, bytes_a, false);
  vertex.defer_texture(true);

  vertex.bind_as_texture(7);
  if (!require_generation(trace.writes.size() == 1 &&
                              trace.writes[0].target == "texture" &&
                              trace.writes[0].bytes == expanded_a &&
                              !vertex.texture_dirty() && vertex.texture_pending() == 1 &&
                              trace.binds == 0,
                          "float expansion A consumes only A's dirty state"))
  {
    return false;
  }

  vertex_generation_contract::frontend_attr_set(&vertex, 0, 0, &sentinel_b[0]);
  vertex_generation_contract::frontend_attr_set(&vertex, 0, 1, &sentinel_b[1]);
  vertex.settle_texture(true);
  vertex.bind_as_texture(7);
  if (!require_generation(trace.writes.size() == 3 &&
                              trace.writes[1].target == "primary" &&
                              trace.writes[1].bytes == bytes_b &&
                              trace.writes[2].target == "texture" &&
                              trace.writes[2].bytes == expanded_b &&
                              !vertex.dirty() && !vertex.texture_dirty() &&
                              vertex.texture_pending() == 1 && trace.binds == 0,
                          "expansion A acceptance schedules expanded B in order"))
  {
    return false;
  }

  vertex.settle_texture(true);
  vertex.bind_as_texture(7);
  vertex_generation_contract::active_context_value = nullptr;
  return require_generation(trace.binds == 1 && trace.bound_bytes == expanded_b &&
                                vertex.texture_bytes() == expanded_b &&
                                vertex.texture_pending() == 0,
                            "expanded B acceptance publishes the B binding");
}

bool pending_float_texture_bind_intent_contract()
{
  constexpr std::array<float, 2> sentinel = {4.25f, -9.5f};
  const std::vector<uint8_t> source = bytes_of(sentinel);
  const std::vector<uint8_t> expanded = expanded_float_bytes(sentinel);
  Trace trace;
  vertex_generation_contract::WGPUContext context(trace);
  vertex_generation_contract::active_context_value = &context;
  VertexFrontendHarness vertex(
      trace, vertex_generation_contract::GPU_USAGE_DYNAMIC, 1, source, source, false);

  vertex.mark_primary_creation_pending();
  vertex.bind_as_texture(9);
  if (!require_generation(trace.pending_binds == 1 && trace.binds == 0 &&
                              trace.hard_missing_binds == 0,
                          "float sampler binding survives primary allocation pending"))
  {
    return false;
  }

  vertex.settle_primary_creation(true);
  vertex.bind_as_texture(9);
  vertex_generation_contract::active_context_value = nullptr;
  return require_generation(trace.pending_binds == 1 && trace.binds == 1 &&
                                trace.hard_missing_binds == 0 &&
                                trace.bound_bytes == expanded,
                            "accepted primary allocation publishes expanded sampler binding");
}

bool pending_float_texture_readback_contract()
{
  constexpr std::array<float, 2> sentinel = {-12.25f, 48.5f};
  const std::vector<uint8_t> source = bytes_of(sentinel);
  const std::vector<uint8_t> expanded = expanded_float_bytes(sentinel);
  Trace trace;
  vertex_generation_contract::WGPUContext context(trace);
  vertex_generation_contract::active_context_value = &context;
  VertexFrontendHarness vertex(
      trace, vertex_generation_contract::GPU_USAGE_DYNAMIC, 1, source, source, false);

  vertex.defer_primary_readback();
  vertex.bind_as_texture(11);
  if (!require_generation(trace.pending_binds == 1 && trace.binds == 0 &&
                              trace.hard_missing_binds == 0 && trace.readback_redraws == 0,
                          "float sampler binding survives primary readback pending"))
  {
    return false;
  }

  vertex.settle_primary_readback(true);
  vertex.bind_as_texture(11);
  vertex_generation_contract::active_context_value = nullptr;
  return require_generation(trace.pending_binds == 1 && trace.binds == 1 &&
                                trace.hard_missing_binds == 0 &&
                                trace.readback_redraws == 1 && trace.bound_bytes == expanded,
                            "readback readiness redraw publishes expanded sampler binding");
}

}  // namespace

bool run_vertex_upload_generation_contracts()
{
  if (!ordinary_generation_contract() || !float_texture_generation_contract() ||
      !pending_float_texture_bind_intent_contract() ||
      !pending_float_texture_readback_contract())
  {
    vertex_generation_contract::active_context_value = nullptr;
    return false;
  }
  std::puts(
      "CONTRACT vertex-upload-generation PASS cases=4 writes=6 order=A:B final=B "
      "pending_intent=1 pending_readback=1 redraw=1");
  return true;
}

}  // namespace blender::gpu
