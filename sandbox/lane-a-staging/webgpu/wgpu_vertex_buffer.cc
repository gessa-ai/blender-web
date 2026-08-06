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

#include <cstdio>
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
  /* Drop any binding this buffer holds in the active context's SSBO bind-space so a
   * freed VBO can never leave a dangling pointer for the next dispatch/draw. */
  if (WGPUContext *ctx = active_context()) {
    ctx->buffer_ssbo_unbind(&buffer_);
  }
  /* Drop the GPU buffer (RAII releases the wgpu::Buffer handle). */
  buffer_ = webgpu::Buffer();
  MEM_SAFE_DELETE(data_);
}

/* Bind this vertex buffer as a read/write storage buffer at the given WGSL @binding
 * (GPU_vertbuf_bind_as_ssbo — compute writes vertex data, e.g. the compute_vbo test /
 * subdiv). Every VBO is allocated Vertex|Storage (wgpu_buffer.cc), so no reallocation
 * is needed; the device buffer is ensured here (a DEVICE_ONLY VBO is never uploaded,
 * so nothing else would create it before the dispatch reads/writes it) and recorded in
 * the context's SSBO bind-space, which the compute/-draw bind-group builder consumes. */
void WGPUVertexBuffer::bind_as_ssbo(uint binding)
{
  if (!buffer_.valid()) {
    allocate();
  }
  if (!buffer_.valid()) {
    return;
  }
  if (WGPUContext *ctx = active_context()) {
    ctx->buffer_ssbo_bind(int(binding), &buffer_);
  }
}

/* Bind this vertex buffer as an emulated texel buffer (GPU_vertbuf_bind_as_texture — the
 * runtime source of a `samplerBuffer`). The buffer-sampler emulation (wgpu_shader.cc
 * is_buffer_sampler / print_resource) rewrites the samplerBuffer into a read-only std430
 * storage buffer, so the runtime bind is identical to bind_as_ssbo (patch 0085): ensure
 * the device buffer exists and register it in the context's SSBO bind-space at the WGSL
 * @binding the frontend recorded (GPU_shader_get_sampler_binding), which the compute/-draw
 * bind-group builder consumes.
 *
 * FORMAT GUARD (M3.F12 decision): the storage emulation reads a FloatBuffer texel as vec4
 * (RGBA32F, 16-byte stride) and an Int/UintBuffer texel as a single 32-bit scalar (4-byte
 * stride). A source VertBuf of any other texel stride (RG32F=8, RGB32F=12, ...) is read
 * with the wrong stride; a strided R32F FloatBuffer (4-byte, e.g. gpu_buffer_texture_test)
 * is likewise read as a 16-byte vec4. True component-count-generic access needs a
 * per-pipeline override constant (the 0079 re-specialization mechanism) — deferred; see
 * notes/gpu-gate-census.md (gpu_buffer_texture_test blacklist candidate). Warn on the
 * clearly-unsupported strides so the mismatch is characterized, not silently garbage. */
void WGPUVertexBuffer::bind_as_texture(uint binding)
{
  if (!buffer_.valid()) {
    allocate();
  }
  if (!buffer_.valid()) {
    return;
  }
  const uint stride = format.stride;
  if (stride != 16 && stride != 4) {
    fprintf(stderr,
            "[WebGPU] buffer-texture texel stride %u is unsupported by the storage-buffer "
            "emulation (only RGBA32F/16B and R32*/4B accepted); reads will be incorrect.\n",
            stride);
  }
  if (WGPUContext *ctx = active_context()) {
    ctx->buffer_ssbo_bind(int(binding), &buffer_);
  }
}

void WGPUVertexBuffer::wrap_handle(uint64_t /*handle*/)
{
  /* Importing an externally-owned GPU buffer handle is not supported yet
   * (the Vulkan backend also leaves this NOT_YET_IMPLEMENTED). */
}

}  // namespace blender::gpu
