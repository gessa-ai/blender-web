/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_storage_buffer.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 */

#include "wgpu_storage_buffer.hh"

#include "GPU_context.hh"
#include "GPU_vertex_buffer.hh"
#include "gpu_context_private.hh"

#include "wgpu_context.hh"
#include "wgpu_vertex_buffer.hh"

#include <cstring>
#include <vector>

namespace blender::gpu {

/** The active WebGPU context (owns the live Dawn instance/device/queue). */
static WGPUContext *active_context()
{
  return static_cast<WGPUContext *>(unwrap(GPU_context_active_get()));
}

bool WGPUStorageBuffer::ensure()
{
  if (buffer_.valid()) {
    return true;
  }
  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return false;
  }
  const webgpu::UsageType usage = (usage_ == GPU_USAGE_DEVICE_ONLY) ?
                                      webgpu::UsageType::DeviceOnly :
                                      webgpu::UsageType::Dynamic;
  /* readable=true: storage buffers can be read back (GPU_storagebuf_read). */
  return buffer_.create(
      ctx->device_get(), webgpu::BufferKind::Storage, usage, size_in_bytes_, nullptr, true);
}

void WGPUStorageBuffer::update(const void *data)
{
  if (data == nullptr || !ensure()) {
    return;
  }
  WGPUContext *ctx = active_context();
  const size_t n = webgpu::align_up(usage_size_in_bytes_, webgpu::kCopyAlignment);
  buffer_.update_sub(ctx->device_get(), ctx->queue_get(), 0, data, n);
}

void WGPUStorageBuffer::clear(uint32_t clear_value)
{
  if (!ensure()) {
    return;
  }
  WGPUContext *ctx = active_context();
  /* WebGPU has no fill-with-value primitive; upload a host vector of the 32-bit
   * pattern. size_in_bytes_ is a multiple of 4 for storage buffers. */
  const size_t words = webgpu::align_up(size_in_bytes_, webgpu::kCopyAlignment) / sizeof(uint32_t);
  std::vector<uint32_t> pattern(words, clear_value);
  buffer_.update_sub(
      ctx->device_get(), ctx->queue_get(), 0, pattern.data(), words * sizeof(uint32_t));
}

void WGPUStorageBuffer::copy_sub(VertBuf *src, uint dst_offset, uint src_offset, uint copy_size)
{
  if (!ensure()) {
    return;
  }
  WGPUContext *ctx = active_context();

  /* Make sure the source vertex buffer's GPU buffer exists and is uploaded. */
  WGPUVertexBuffer *src_vbo = unwrap(src);
  src_vbo->upload();
  const webgpu::Buffer &src_buffer = src_vbo->buffer();
  if (!src_buffer.valid()) {
    return;
  }

  wgpu::Device device = ctx->device_get();
  wgpu::CommandEncoder enc = device.CreateCommandEncoder();
  enc.CopyBufferToBuffer(
      src_buffer.handle(), src_offset, buffer_.handle(), dst_offset, copy_size);
  wgpu::CommandBuffer cb = enc.Finish();
  ctx->queue_get().Submit(1, &cb);
}

void WGPUStorageBuffer::read(void *data)
{
  if (data == nullptr || !ensure()) {
    return;
  }
  WGPUContext *ctx = active_context();
  std::vector<uint8_t> bytes = buffer_.read(
      ctx->instance_get(), ctx->device_get(), ctx->queue_get(), 0, size_in_bytes_);
  if (bytes.size() == size_in_bytes_) {
    std::memcpy(data, bytes.data(), size_in_bytes_);
  }
}

/* Binding is resolved at bind-group / pipeline assembly (wgpu_bind_group, T7). */
void WGPUStorageBuffer::bind(int /*slot*/) {}
void WGPUStorageBuffer::unbind() {}

/* read() is synchronous (blocks on the instance), so the async flush is a no-op;
 * the Indirect usage bit is set at creation, so no explicit sync is needed. */
void WGPUStorageBuffer::async_flush_to_host() {}
void WGPUStorageBuffer::sync_as_indirect_buffer() {}

}  // namespace blender::gpu
