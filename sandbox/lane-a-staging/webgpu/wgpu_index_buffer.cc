/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_index_buffer.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 */

#include "wgpu_index_buffer.hh"

#include "GPU_context.hh"
#include "gpu_context_private.hh"

#include "wgpu_context.hh"

#include "MEM_guardedalloc.h"

#include <cstring>
#include <vector>

namespace blender::gpu {

/** The active WebGPU context. */
static WGPUContext *active_context()
{
  return static_cast<WGPUContext *>(unwrap(GPU_context_active_get()));
}

void WGPUIndexBuffer::allocate()
{
  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return;
  }
  buffer_.create(ctx->device_get(),
                 webgpu::BufferKind::Index,
                 webgpu::UsageType::Static,
                 size_get(),
                 nullptr,
                 true);
}

void WGPUIndexBuffer::upload_data()
{
  if (is_subrange_) {
    src_->upload_data();
    return;
  }
  if (buffer_.valid()) {
    return; /* already uploaded (update_sub handles later edits). */
  }

  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return;
  }

  if (data_ == nullptr) {
    /* Build-on-device index buffer: allocate empty, filled by a compute pass. */
    allocate();
    return;
  }

  /* Upload via mappedAtCreation so an odd U16 byte size (not a multiple of 4)
   * still copies exactly. readable=true so read() can stage it back. */
  buffer_.create(ctx->device_get(),
                 webgpu::BufferKind::Index,
                 webgpu::UsageType::Static,
                 size_get(),
                 data_,
                 true);

  /* Ownership of the index data was transferred to this IndexBuf; free it now
   * (and null it) so the base destructor does not double-free. */
  MEM_SAFE_DELETE_VOID(data_);
  data_uploaded_ = true;
}

const webgpu::Buffer &WGPUIndexBuffer::buffer() const
{
  return is_subrange_ ? unwrap(src_)->buffer() : buffer_;
}

void WGPUIndexBuffer::read(uint32_t *data) const
{
  const webgpu::Buffer &buf = buffer();
  if (!buf.valid()) {
    return;
  }
  WGPUContext *ctx = active_context();
  std::vector<uint8_t> bytes = buf.read(
      ctx->instance_get(), ctx->device_get(), ctx->queue_get(), 0, size_get());
  if (!bytes.empty()) {
    std::memcpy(data, bytes.data(), bytes.size());
  }
}

/* Binding a index buffer as an SSBO is a draw/compute-time concern resolved by
 * the state manager (lane B); the object itself does nothing here. */
void WGPUIndexBuffer::bind_as_ssbo(uint /*binding*/) {}

void WGPUIndexBuffer::update_sub(uint /*start*/, uint /*len*/, const void * /*data*/)
{
  /* Not implemented (the Vulkan backend leaves this NOT_YET_IMPLEMENTED too). */
}

void WGPUIndexBuffer::strip_restart_indices()
{
  /* Not implemented (matches the Vulkan backend). */
}

}  // namespace blender::gpu
