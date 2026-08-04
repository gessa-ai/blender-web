/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_buffer.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * WebGPU buffer wrapper. See wgpu_buffer.hh. Usage-flag mapping mirrors the
 * Vulkan backend's per-kind VkBufferUsageFlags (recon cited in
 * notes/gpu-t6-t10pre-findings.md): vertex/index buffers are also STORAGE-usable
 * (GPU-compute writes them), storage buffers are also INDIRECT.
 */

#include "wgpu_buffer.hh"

#include <cstring>

namespace blender::gpu::webgpu {

wgpu::BufferUsage usage_flags(BufferKind kind, UsageType usage, bool readable)
{
  wgpu::BufferUsage u = wgpu::BufferUsage::None;
  switch (kind) {
    case BufferKind::Vertex:
      /* VERTEX | STORAGE (subdiv/compute writes) — vk_vertex_buffer.cc:207. */
      u |= wgpu::BufferUsage::Vertex | wgpu::BufferUsage::Storage;
      break;
    case BufferKind::Index:
      /* INDEX | STORAGE — vk_index_buffer.cc:113. */
      u |= wgpu::BufferUsage::Index | wgpu::BufferUsage::Storage;
      break;
    case BufferKind::Uniform:
      /* UNIFORM only (+STORAGE in vk, omitted — WebGPU forbids Uniform+Storage on
       * one buffer). vk_uniform_buffer.cc:42. */
      u |= wgpu::BufferUsage::Uniform;
      break;
    case BufferKind::Storage:
      /* STORAGE | INDIRECT — vk_storage_buffer.cc:82. */
      u |= wgpu::BufferUsage::Storage | wgpu::BufferUsage::Indirect;
      break;
  }
  /* DEVICE_ONLY does no host->device transfer (GPU_USAGE_DEVICE_ONLY): no CopyDst. */
  if (usage != UsageType::DeviceOnly) {
    u |= wgpu::BufferUsage::CopyDst;
  }
  if (readable) {
    u |= wgpu::BufferUsage::CopySrc;
  }
  return u;
}

bool Buffer::create(const wgpu::Device &device,
                    BufferKind kind,
                    UsageType usage,
                    size_t size,
                    const void *initial_data,
                    bool readable)
{
  requested_ = size;
  size_ = align_up(size == 0 ? kCopyAlignment : size, kCopyAlignment);
  kind_ = kind;
  readable_ = readable;

  wgpu::BufferDescriptor bd = {};
  bd.size = size_;
  bd.usage = usage_flags(kind, usage, readable);
  bd.mappedAtCreation = (initial_data != nullptr);
  handle_ = device.CreateBuffer(&bd);
  if (handle_ == nullptr) {
    return false;
  }
  if (initial_data != nullptr) {
    void *p = handle_.GetMappedRange(0, size_);
    if (p == nullptr) {
      return false;
    }
    std::memcpy(p, initial_data, requested_);
    handle_.Unmap();
  }
  return true;
}

bool Buffer::update_sub(const wgpu::Device &device,
                        const wgpu::Queue &queue,
                        size_t offset,
                        const void *data,
                        size_t size)
{
  if (handle_ == nullptr || data == nullptr) {
    return false;
  }
  if ((offset % kCopyAlignment) != 0 || (size % kCopyAlignment) != 0) {
    return false; /* WebGPU copies require 4-byte alignment */
  }
  if (offset + size > size_) {
    return false;
  }

  if (size <= kWriteBufferStagingThreshold) {
    /* Direct path — analog of Blender's inline vkCmdUpdateBuffer (<=64 KiB). */
    queue.WriteBuffer(handle_, offset, data, size);
    return true;
  }

  /* Large path — dedicated staging buffer + CopyBufferToBuffer (the vk staging
   * path for device-local buffers). */
  wgpu::BufferDescriptor sd = {};
  sd.size = size;
  sd.usage = wgpu::BufferUsage::CopySrc;
  sd.mappedAtCreation = true;
  wgpu::Buffer staging = device.CreateBuffer(&sd);
  if (staging == nullptr) {
    return false;
  }
  std::memcpy(staging.GetMappedRange(0, size), data, size);
  staging.Unmap();
  wgpu::CommandEncoder enc = device.CreateCommandEncoder();
  enc.CopyBufferToBuffer(staging, 0, handle_, offset, size);
  wgpu::CommandBuffer cb = enc.Finish();
  queue.Submit(1, &cb);
  return true;
}

std::vector<uint8_t> Buffer::read(const wgpu::Instance &instance,
                                  const wgpu::Device &device,
                                  const wgpu::Queue &queue,
                                  size_t offset,
                                  size_t size) const
{
  std::vector<uint8_t> out;
  if (handle_ == nullptr || !readable_ || size == 0) {
    return out;
  }
  const size_t copy = align_up(size, kCopyAlignment);
  if (offset + copy > size_) {
    return out;
  }
  wgpu::BufferDescriptor sd = {};
  sd.size = copy;
  sd.usage = wgpu::BufferUsage::MapRead | wgpu::BufferUsage::CopyDst;
  wgpu::Buffer staging = device.CreateBuffer(&sd);
  if (staging == nullptr) {
    return out;
  }
  wgpu::CommandEncoder enc = device.CreateCommandEncoder();
  enc.CopyBufferToBuffer(handle_, offset, staging, 0, copy);
  wgpu::CommandBuffer cb = enc.Finish();
  queue.Submit(1, &cb);

  bool ok = false;
  wgpu::Future f = staging.MapAsync(
      wgpu::MapMode::Read, 0, copy, wgpu::CallbackMode::WaitAnyOnly,
      [&](wgpu::MapAsyncStatus s, wgpu::StringView) {
        ok = (s == wgpu::MapAsyncStatus::Success);
      });
  instance.WaitAny(f, UINT64_MAX);
  if (ok) {
    const uint8_t *p = static_cast<const uint8_t *>(staging.GetConstMappedRange(0, copy));
    if (p != nullptr) {
      out.assign(p, p + size);
    }
    staging.Unmap();
  }
  return out;
}

}  // namespace blender::gpu::webgpu
