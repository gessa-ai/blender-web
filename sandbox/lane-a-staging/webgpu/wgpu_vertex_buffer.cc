/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_vertex_buffer.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 */

#include "wgpu_vertex_buffer.hh"

#include "GPU_context.hh"
#include "gpu_context_private.hh"

#include "wgpu_context.hh"

#include "MEM_guardedalloc.h"

#include "BLI_utildefines.h"

#include <cstring>
#include <vector>

namespace blender::gpu {

/** The active WebGPU context. */
static WGPUContext *active_context()
{
  return static_cast<WGPUContext *>(unwrap(GPU_context_active_get()));
}

/** Map Blender's base `GPUUsageType` (low bits) to the buffer wrapper's usage. */
static webgpu::UsageType to_wgpu_usage(GPUUsageType usage)
{
  switch (usage & 0x3) {
    case GPU_USAGE_STREAM:
      return webgpu::UsageType::Stream;
    case GPU_USAGE_STATIC:
      return webgpu::UsageType::Static;
    case GPU_USAGE_DYNAMIC:
      return webgpu::UsageType::Dynamic;
    case GPU_USAGE_DEVICE_ONLY:
      return webgpu::UsageType::DeviceOnly;
    default:
      return webgpu::UsageType::Static;
  }
}

WGPUVertexBuffer::~WGPUVertexBuffer()
{
  release_data();
}

void WGPUVertexBuffer::allocate()
{
  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return;
  }
  /* Vertex | Storage | Copy* (readable=true so it can be the CopySrc of
   * GPU_storagebuf_copy_sub_from_vertbuf and of read()). */
  buffer_.create(ctx->device_get(),
                 webgpu::BufferKind::Vertex,
                 to_wgpu_usage(usage_),
                 size_alloc_get(),
                 nullptr,
                 true);
}

void WGPUVertexBuffer::upload_data()
{
  if (!buffer_.valid()) {
    allocate();
    if (!buffer_.valid()) {
      return; /* allocation failed (e.g. no active context). */
    }
  }

  /* DEVICE_ONLY buffers hold no host copy and are never uploaded from host. */
  if (!ELEM(usage_ & 0x3, GPU_USAGE_STATIC, GPU_USAGE_STREAM, GPU_USAGE_DYNAMIC)) {
    return;
  }

  if (flag & GPU_VERTBUF_DATA_DIRTY) {
    const size_t used = size_used_get();
    if (data_ != nullptr && used > 0) {
      WGPUContext *ctx = active_context();
      buffer_.update_sub(ctx->device_get(), ctx->queue_get(), 0, data_, used);
    }
    if ((usage_ & 0x3) == GPU_USAGE_STATIC) {
      MEM_SAFE_DELETE(data_);
    }
    data_uploaded_ = true;
    flag &= ~GPU_VERTBUF_DATA_DIRTY;
    flag |= GPU_VERTBUF_DATA_UPLOADED;
  }
}

void WGPUVertexBuffer::update_sub(uint start, uint len, const void *data)
{
  if (!buffer_.valid() || data == nullptr) {
    return;
  }
  WGPUContext *ctx = active_context();
  buffer_.update_sub(ctx->device_get(), ctx->queue_get(), start, data, len);
}

void WGPUVertexBuffer::read(void *data) const
{
  if (!buffer_.valid()) {
    return;
  }
  WGPUContext *ctx = active_context();
  std::vector<uint8_t> bytes = buffer_.read(
      ctx->instance_get(), ctx->device_get(), ctx->queue_get(), 0, size_used_get());
  if (!bytes.empty()) {
    std::memcpy(data, bytes.data(), bytes.size());
  }
}

void WGPUVertexBuffer::acquire_data()
{
  if ((usage_ & 0x3) == GPU_USAGE_DEVICE_ONLY) {
    return;
  }
  /* Discard previous data if any. */
  MEM_SAFE_DELETE(data_);
  data_ = MEM_new_array_uninitialized<uchar>(this->size_alloc_get(), __func__);
}

void WGPUVertexBuffer::resize_data()
{
  if ((usage_ & 0x3) == GPU_USAGE_DEVICE_ONLY) {
    return;
  }
  data_ = static_cast<uchar *>(
      MEM_realloc_uninitialized(data_, sizeof(uchar) * this->size_alloc_get()));
}

void WGPUVertexBuffer::release_data()
{
  /* Drop the GPU buffer (RAII releases the wgpu::Buffer handle). */
  buffer_ = webgpu::Buffer();
  MEM_SAFE_DELETE(data_);
}

/* Binding paths are deferred to the state manager / bind-group assembly (lane B,
 * T7): a vertex buffer read as an SSBO or bound as a texel buffer is a draw-time
 * concern the buffer object does not resolve on its own. */
void WGPUVertexBuffer::bind_as_ssbo(uint /*binding*/) {}
void WGPUVertexBuffer::bind_as_texture(uint /*binding*/) {}

void WGPUVertexBuffer::wrap_handle(uint64_t /*handle*/)
{
  /* Importing an externally-owned GPU buffer handle is not supported yet
   * (the Vulkan backend also leaves this NOT_YET_IMPLEMENTED). */
}

}  // namespace blender::gpu
