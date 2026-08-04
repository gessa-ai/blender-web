/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_uniform_buffer.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 */

#include "wgpu_uniform_buffer.hh"

#include "GPU_context.hh"
#include "gpu_context_private.hh"

#include "wgpu_context.hh"

#include <vector>

namespace blender::gpu {

/** The active WebGPU context (owns the live Dawn device/queue). */
static WGPUContext *active_context()
{
  return static_cast<WGPUContext *>(unwrap(GPU_context_active_get()));
}

bool WGPUUniformBuffer::ensure()
{
  if (buffer_.valid()) {
    return true;
  }
  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return false;
  }
  return buffer_.create(ctx->device_get(),
                        webgpu::BufferKind::Uniform,
                        webgpu::UsageType::Dynamic,
                        size_in_bytes_,
                        nullptr,
                        false);
}

void WGPUUniformBuffer::update(const void *data)
{
  if (data == nullptr || !ensure()) {
    return;
  }
  WGPUContext *ctx = active_context();
  /* UBO payloads are std140-padded, so size is a multiple of 16; round to 4 for
   * the WebGPU copy granularity to be safe. */
  const size_t n = webgpu::align_up(size_in_bytes_, webgpu::kCopyAlignment);
  buffer_.update_sub(ctx->device_get(), ctx->queue_get(), 0, data, n);
}

void WGPUUniformBuffer::clear_to_zero()
{
  if (!ensure()) {
    return;
  }
  WGPUContext *ctx = active_context();
  const size_t n = webgpu::align_up(size_in_bytes_, webgpu::kCopyAlignment);
  std::vector<uint8_t> zeros(n, 0);
  buffer_.update_sub(ctx->device_get(), ctx->queue_get(), 0, zeros.data(), n);
}

/* Binding is resolved at bind-group / pipeline assembly (wgpu_bind_group, T7),
 * where the (group,binding) comes from the shader interface map. */
void WGPUUniformBuffer::bind(int /*slot*/) {}
void WGPUUniformBuffer::bind_as_ssbo(int /*slot*/) {}
void WGPUUniformBuffer::unbind() {}

}  // namespace blender::gpu
