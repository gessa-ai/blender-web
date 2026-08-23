/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free parity contract for the point-restart cleanup delegated by
 * Blender's real IndexBuf::init() to the canonical WebGPU backend method. */

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

#include "MEM_guardedalloc.h"

#include "GPU_index_buffer.hh"
#include "wgpu_index_buffer.hh"

#ifndef BW_WGPU_INDEX_STRIP_SOURCE
#  error "BW_WGPU_INDEX_STRIP_SOURCE must name the extracted shipping method"
#endif
#ifndef BW_WGPU_INDEX_UPLOAD_SOURCE
#  error "BW_WGPU_INDEX_UPLOAD_SOURCE must name the extracted shipping method"
#endif

namespace blender::gpu {

class IndexStripHarness : public IndexBuf {
 public:
  void upload_data() override {}
  void bind_as_ssbo(uint /*binding*/) override {}
  void read(uint32_t * /*data*/) const override {}
  void update_sub(uint /*start*/, uint /*len*/, const void * /*data*/) override {}

  uint32_t stored_length() const
  {
    return index_len_;
  }
  bool is_subrange() const
  {
    return is_subrange_;
  }
  const IndexBuf *source() const
  {
    return is_subrange_ ? src_ : nullptr;
  }
  const uint16_t *u16_data() const
  {
    return static_cast<const uint16_t *>(data_);
  }
  const uint32_t *u32_data() const
  {
    return static_cast<const uint32_t *>(data_);
  }

 private:
  void strip_restart_indices() override;
};

/* Execute the shipping method without retaining WGPUIndexBuffer's live-device
 * vtable. The build driver extracts this definition byte-for-byte. */
#define WGPUIndexBuffer IndexStripHarness
#include BW_WGPU_INDEX_STRIP_SOURCE
#undef WGPUIndexBuffer

namespace {

struct IndexUploadDevice {};
struct IndexUploadInstance {};

class IndexUploadContext {
 public:
  const IndexUploadDevice &device_get() const
  {
    return device_;
  }
  const IndexUploadInstance &instance_get() const
  {
    return instance_;
  }

 private:
  IndexUploadDevice device_;
  IndexUploadInstance instance_;
};

static IndexUploadContext *index_upload_context = nullptr;

static IndexUploadContext *active_context()
{
  return index_upload_context;
}

class IndexUploadBuffer {
 public:
  bool valid() const
  {
    return valid_;
  }

  template<typename Instance, typename Device>
  bool create_scoped(const Instance & /*instance*/,
              const Device & /*device*/,
              const webgpu::BufferKind kind,
              const webgpu::UsageType usage,
              const size_t size,
              const void *initial_data,
              const bool readable)
  {
    create_calls_++;
    last_kind_ = kind;
    last_usage_ = usage;
    last_readable_ = readable;
    last_payload_.assign(static_cast<const uint8_t *>(initial_data),
                         static_cast<const uint8_t *>(initial_data) + size);
    valid_ = create_result_;
    return create_result_;
  }

  bool creation_pending() const
  {
    return create_pending_;
  }

  void set_valid(const bool valid)
  {
    valid_ = valid;
  }
  void set_create_result(const bool result)
  {
    create_result_ = result;
  }
  void set_create_pending(const bool pending)
  {
    create_pending_ = pending;
  }
  size_t create_calls() const
  {
    return create_calls_;
  }
  webgpu::BufferKind last_kind() const
  {
    return last_kind_;
  }
  webgpu::UsageType last_usage() const
  {
    return last_usage_;
  }
  bool last_readable() const
  {
    return last_readable_;
  }
  const std::vector<uint8_t> &last_payload() const
  {
    return last_payload_;
  }

 private:
  bool valid_ = false;
  bool create_result_ = true;
  bool create_pending_ = false;
  size_t create_calls_ = 0;
  webgpu::BufferKind last_kind_ = webgpu::BufferKind::Vertex;
  webgpu::UsageType last_usage_ = webgpu::UsageType::Dynamic;
  bool last_readable_ = false;
  std::vector<uint8_t> last_payload_;
};

class IndexUploadHarness {
 public:
  ~IndexUploadHarness()
  {
    MEM_SAFE_DELETE_VOID(data_);
  }

  void upload_data();

  void seed_data(const std::array<uint8_t, 6> &bytes)
  {
    MEM_SAFE_DELETE_VOID(data_);
    auto *owned = MEM_new_array_uninitialized<uint8_t>(bytes.size(), __func__);
    std::memcpy(owned, bytes.data(), bytes.size());
    data_ = owned;
    size_ = bytes.size();
  }

  void make_subrange(IndexUploadHarness &source)
  {
    is_subrange_ = true;
    src_ = &source;
  }
  void set_buffer_valid(const bool valid)
  {
    buffer_.set_valid(valid);
  }
  void set_create_result(const bool result)
  {
    buffer_.set_create_result(result);
  }
  void settle_pending_create()
  {
    buffer_.set_valid(true);
    buffer_.set_create_pending(false);
  }
  void set_allocate_result(const bool result)
  {
    allocate_result_ = result;
  }
  bool has_data() const
  {
    return data_ != nullptr;
  }
  bool uploaded() const
  {
    return data_uploaded_;
  }
  bool buffer_valid() const
  {
    return buffer_.valid();
  }
  size_t create_calls() const
  {
    return buffer_.create_calls();
  }
  size_t allocate_calls() const
  {
    return allocate_calls_;
  }
  const IndexUploadBuffer &mock_buffer() const
  {
    return buffer_;
  }

 private:
  size_t size_get() const
  {
    return size_;
  }
  void allocate()
  {
    allocate_calls_++;
    buffer_.set_valid(allocate_result_);
  }

  bool is_subrange_ = false;
  IndexUploadHarness *src_ = nullptr;
  void *data_ = nullptr;
  size_t size_ = 0;
  IndexUploadBuffer buffer_;
  bool data_uploaded_ = false;
  bool initial_upload_pending_ = false;
  bool allocate_result_ = true;
  size_t allocate_calls_ = 0;
};

/* Execute the shipping upload state machine with a deterministic allocation
 * seam. Only the class and context type tokens are substituted. */
#define WGPUIndexBuffer IndexUploadHarness
#define WGPUContext IndexUploadContext
#include BW_WGPU_INDEX_UPLOAD_SOURCE
#undef WGPUContext
#undef WGPUIndexBuffer

}  // namespace

namespace {

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "FAIL %s\n", message);
    return false;
  }
  return true;
}

template<size_t Size>
uint32_t *owned_indices(const std::array<uint32_t, Size> &source)
{
  uint32_t *result = MEM_new_array_uninitialized<uint32_t>(Size, "index restart contract");
  std::memcpy(result, source.data(), sizeof(source));
  return result;
}

template<size_t Size>
bool equal_u16(const IndexStripHarness &buffer, const std::array<uint16_t, Size> &expected)
{
  return std::memcmp(buffer.u16_data(), expected.data(), sizeof(expected)) == 0;
}

template<size_t Size>
bool equal_u32(const IndexStripHarness &buffer, const std::array<uint32_t, Size> &expected)
{
  return std::memcmp(buffer.u32_data(), expected.data(), sizeof(expected)) == 0;
}

bool point_restart_contract()
{
  size_t removed = 0;
  size_t survivors = 0;

  {
    constexpr std::array<uint32_t, 6> input = {7, RESTART_INDEX, 9, 11, RESTART_INDEX, 13};
    constexpr std::array<uint16_t, 4> expected = {7, 9, 11, 13};
    IndexStripHarness buffer;
    buffer.init(input.size(), owned_indices(input), 7, 13, GPU_PRIM_POINTS, true);
    if (!require(buffer.stored_length() == expected.size(), "mixed restart count") ||
        !require(buffer.index_len_get() == expected.size(), "mixed drawable count") ||
        !require(!buffer.is_32bit(), "mixed restart compression") ||
        !require(equal_u16(buffer, expected), "mixed restart stable order"))
    {
      return false;
    }
    removed += input.size() - expected.size();
    survivors += expected.size();
  }

  {
    constexpr std::array<uint32_t, 4> input = {
        RESTART_INDEX, RESTART_INDEX, RESTART_INDEX, RESTART_INDEX};
    IndexStripHarness buffer;
    buffer.init(input.size(),
                owned_indices(input),
                UINT32_MAX,
                0,
                GPU_PRIM_POINTS,
                true);
    if (!require(buffer.stored_length() == 0, "all-restart storage is empty") ||
        !require(buffer.index_len_get() == 0, "all-restart draw is empty"))
    {
      return false;
    }
    removed += input.size();
  }

  {
    constexpr std::array<uint32_t, 5> input = {3, RESTART_INDEX, 70000, RESTART_INDEX, 42};
    constexpr std::array<uint32_t, 3> expected = {3, 70000, 42};
    IndexStripHarness buffer;
    buffer.init(input.size(), owned_indices(input), 3, 70000, GPU_PRIM_POINTS, true);
    if (!require(buffer.stored_length() == expected.size(), "wide restart count") ||
        !require(buffer.is_32bit(), "wide indices remain u32") ||
        !require(equal_u32(buffer, expected), "wide restart stable order"))
    {
      return false;
    }
    removed += input.size() - expected.size();
    survivors += expected.size();
  }

  {
    constexpr std::array<uint32_t, 3> input = {65536, RESTART_INDEX, 65538};
    constexpr std::array<uint16_t, 2> expected = {0, 2};
    IndexStripHarness buffer;
    buffer.init(input.size(), owned_indices(input), 65536, 65538, GPU_PRIM_POINTS, true);
    if (!require(buffer.stored_length() == expected.size(), "rebased restart count") ||
        !require(!buffer.is_32bit(), "rebased indices compress to u16") ||
        !require(buffer.index_base_get() == 65536, "rebased index base") ||
        !require(equal_u16(buffer, expected), "restart removal precedes squeezing"))
    {
      return false;
    }
    removed += input.size() - expected.size();
    survivors += expected.size();
  }

  if (!require(removed == 9, "restart removal census") ||
      !require(survivors == 9, "restart survivor census"))
  {
    return false;
  }
  std::printf(
      "CONTRACT index-point-restart PASS cases=4 removed=%zu survivors=%zu order=stable\n",
      removed,
      survivors);
  return true;
}

bool index_metadata_contract()
{
  constexpr std::array<uint32_t, 4> source = {65536, 65537, 65538, 65539};
  IndexStripHarness parent;
  parent.init(source.size(), owned_indices(source), 65536, 65539, GPU_PRIM_TRIS, false);
  IndexStripHarness child;
  child.init_subrange(&parent, 1, 2);
  constexpr std::array<uint32_t, 4> wide_source = {3, 70000, 42, 90000};
  IndexStripHarness wide_parent;
  wide_parent.init(
      wide_source.size(), owned_indices(wide_source), 3, 90000, GPU_PRIM_TRIS, false);
  IndexStripHarness wide_child;
  wide_child.init_subrange(&wide_parent, 3, 1);
  IndexStripHarness device_only;
  device_only.init_build_on_device(17);

  const webgpu::IndexBindingPlan child_binding = webgpu::index_binding_plan(
      child, webgpu::IndexBindingMode::Direct);
  const webgpu::IndexBindingPlan child_indirect_binding = webgpu::index_binding_plan(
      child, webgpu::IndexBindingMode::Indirect);
  const webgpu::IndexBindingPlan wide_binding = webgpu::index_binding_plan(
      wide_child, webgpu::IndexBindingMode::Direct);
  const webgpu::IndexBindingPlan wide_indirect_binding = webgpu::index_binding_plan(
      wide_child, webgpu::IndexBindingMode::Indirect);

  if (!require(!parent.is_32bit(), "parent compresses to u16") ||
      !require(parent.index_base_get() == 65536, "parent base") ||
      !require(child.is_subrange(), "subrange marker") ||
      !require(child.source() == &parent, "subrange parent identity") ||
      !require(child.index_start_get() == 1 && child.index_len_get() == 2,
               "subrange span") ||
      !require(child.index_base_get() == parent.index_base_get(), "subrange base inheritance") ||
      !require(!child.is_32bit() && child.size_get() == 4, "subrange u16 byte size") ||
      !require(child_binding.byte_offset == 2 && child_binding.base_vertex == 65536,
               "subrange u16 draw binding") ||
      !require(child_indirect_binding.byte_offset == 0 &&
                   child_indirect_binding.base_vertex == 65536,
               "subrange u16 indirect binding") ||
      !require(wide_child.is_32bit() && wide_child.index_start_get() == 3,
               "subrange u32 metadata") ||
      !require(wide_binding.byte_offset == 12 && wide_binding.base_vertex == 0,
               "subrange u32 draw binding") ||
      !require(wide_indirect_binding.byte_offset == 0 &&
                   wide_indirect_binding.base_vertex == 0,
               "subrange u32 indirect binding") ||
      !require(device_only.is_32bit(), "device-built indices are u32") ||
      !require(device_only.index_start_get() == 0 && device_only.index_len_get() == 17,
               "device-built span") ||
      !require(device_only.size_get() == 68, "device-built byte size"))
  {
    return false;
  }

  std::puts(
      "CONTRACT index-metadata PASS subranges=2 "
      "direct=u16@2+65536/u32@12+0 indirect=u16@0+65536/u32@0+0 device-u32=17");
  return true;
}

bool index_upload_commit_contract()
{
  constexpr std::array<uint8_t, 6> payload = {0x10, 0x21, 0x32, 0x43, 0x54, 0x65};
  IndexUploadContext context;
  size_t create_calls = 0;

  {
    IndexUploadHarness source;
    source.seed_data(payload);
    IndexUploadHarness subrange;
    subrange.make_subrange(source);
    index_upload_context = &context;
    subrange.upload_data();
    if (!require(source.uploaded() && !source.has_data() && source.buffer_valid(),
                 "subrange delegates upload to its source") ||
        !require(subrange.create_calls() == 0, "subrange does not allocate itself"))
    {
      return false;
    }
    create_calls += source.create_calls();
  }

  {
    IndexUploadHarness existing;
    existing.seed_data(payload);
    existing.set_buffer_valid(true);
    existing.upload_data();
    if (!require(existing.has_data() && !existing.uploaded(),
                 "existing device buffer leaves pending host data untouched") ||
        !require(existing.create_calls() == 0, "existing device buffer skips create"))
    {
      return false;
    }
  }

  {
    IndexUploadHarness no_context;
    no_context.seed_data(payload);
    index_upload_context = nullptr;
    no_context.upload_data();
    if (!require(no_context.has_data() && !no_context.uploaded(),
                 "missing context preserves host data") ||
        !require(no_context.create_calls() == 0, "missing context skips create"))
    {
      return false;
    }
  }

  {
    IndexUploadHarness device_built;
    device_built.set_allocate_result(true);
    index_upload_context = &context;
    device_built.upload_data();
    if (!require(device_built.allocate_calls() == 1 && device_built.buffer_valid(),
                 "device-built index buffer allocates empty storage") ||
        !require(!device_built.uploaded() && device_built.create_calls() == 0,
                 "device-built allocation is not a host upload"))
    {
      return false;
    }
  }

  {
    IndexUploadHarness retry;
    retry.seed_data(payload);
    retry.set_create_result(false);
    index_upload_context = &context;
    retry.upload_data();
    if (!require(retry.has_data() && !retry.uploaded() && !retry.buffer_valid(),
                 "failed create preserves retryable host data and state") ||
        !require(retry.create_calls() == 1, "failed create attempted exactly once"))
    {
      return false;
    }
    retry.set_create_result(true);
    retry.upload_data();
    if (!require(!retry.has_data() && retry.uploaded() && retry.buffer_valid(),
                 "successful retry commits upload state") ||
        !require(retry.create_calls() == 2, "successful retry creates once more") ||
        !require(retry.mock_buffer().last_kind() == webgpu::BufferKind::Index &&
                     retry.mock_buffer().last_usage() == webgpu::UsageType::Static &&
                     retry.mock_buffer().last_readable(),
                 "index upload preserves buffer kind usage and readability") ||
        !require(retry.mock_buffer().last_payload() ==
                     std::vector<uint8_t>(payload.begin(), payload.end()),
                 "successful retry preserves all initial bytes"))
    {
      return false;
    }
    create_calls += retry.create_calls();
  }

  {
    IndexUploadHarness pending;
    pending.seed_data(payload);
    pending.set_create_result(false);
    index_upload_context = &context;
    pending.upload_data();
    if (!require(pending.has_data() && !pending.uploaded() && !pending.buffer_valid(),
                 "pending scoped create preserves host upload ownership") ||
        !require(pending.create_calls() == 1,
                 "pending scoped create allocates one candidate"))
    {
      return false;
    }
    pending.settle_pending_create();
    pending.upload_data();
    if (!require(!pending.has_data() && pending.uploaded() && pending.buffer_valid(),
                 "settled scoped create commits host upload ownership") ||
        !require(pending.create_calls() == 1,
                 "settled scoped create does not allocate a duplicate"))
    {
      return false;
    }
    create_calls += pending.create_calls();
  }

  {
    IndexUploadHarness success;
    success.seed_data(payload);
    success.set_create_result(true);
    success.upload_data();
    if (!require(!success.has_data() && success.uploaded() && success.buffer_valid(),
                 "first successful create commits upload state") ||
        !require(success.create_calls() == 1, "first successful create count"))
    {
      return false;
    }
    create_calls += success.create_calls();
  }

  index_upload_context = nullptr;
  std::printf(
      "CONTRACT index-upload-commit PASS cases=7 creates=%zu failure=retain pending=retain retry=commit bytes=%zu\n",
      create_calls,
      payload.size());
  return create_calls == 5;
}

}  // namespace

bool run_integrated_index_contracts()
{
  return point_restart_contract() && index_metadata_contract() && index_upload_commit_contract();
}

}  // namespace blender::gpu
