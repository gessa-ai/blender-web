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

#include <algorithm>
#include <vector>

namespace blender::gpu {

/** The active WebGPU context (owns the live Dawn device/queue). */
static WGPUContext *active_context()
{
  return static_cast<WGPUContext *>(unwrap(GPU_context_active_get()));
}

/* Blender declares fixed-size *array* UBOs whose shader interface size is the full array
 * but binds a buffer holding only the used prefix — canonically the draw-manager view UBO
 * `ViewMatrices view_buf[64]` (draw_view_infos.hh:83), a 16 KiB container (draw_defines.hh:42,
 * DRW_VIEW_MAX 64) of which the single-view viewport binds one entry. GL/Vulkan allow binding
 * a buffer smaller than the declared block; WebGPU's auto-layout derives minBindingSize from
 * the WGSL struct and REJECTS the short bind ("Binding size (352) ... smaller than the minimum
 * binding size (16384)"), dropping every vertex draw that uses the view UBO — the whole 3D
 * viewport. Blender caps UBOs at the 16 KiB GL guarantee, so padding every UBO allocation up to
 * that ceiling makes the bound size always satisfy the declared minBindingSize, at a bounded
 * cost (a handful of UBOs, <2 MiB total). The extra tail is zero-initialised by WebGPU and never
 * indexed (single-view reads view_buf[0]); update()/clear write only the real payload below. */
static constexpr size_t kUboMinBindingPad = 16384;

bool WGPUUniformBuffer::ensure()
{
  if (buffer_.valid()) {
    return true;
  }
  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return false;
  }
  const size_t alloc = std::max(size_in_bytes_, kUboMinBindingPad);
  return buffer_.create(ctx->device_get(),
                        webgpu::BufferKind::Uniform,
                        webgpu::UsageType::Dynamic,
                        alloc,
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

/* Record the binding in the active context's uniform-buffer bind-space; the actual
 * wgpu::BindGroup is assembled at draw/dispatch time (append_resource_bind_entries).
 * ensure() the device buffer here so the handle is valid by assembly time, mirroring
 * WGPUStorageBuffer::bind(). `slot` is the CREATE-INFO SLOT the frontend recorded
 * (GPU_shader_get_ubo_binding → ShaderInput::binding = res.slot since r44r2); the bind-group
 * builder translates it to the dense WGSL @binding at emit via remap_ubo_binding. */
void WGPUUniformBuffer::bind(int slot)
{
  if (!ensure()) {
    return;
  }
  WGPUContext *ctx = active_context();
  if (ctx != nullptr) {
    ctx->uniform_buffer_bind(slot, this);
  }
}
void WGPUUniformBuffer::bind_as_ssbo(int /*slot*/) {}
void WGPUUniformBuffer::unbind()
{
  WGPUContext *ctx = active_context();
  if (ctx != nullptr) {
    ctx->uniform_buffer_unbind(this);
  }
}

}  // namespace blender::gpu
