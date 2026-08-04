/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_vertex_buffer.hh @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * `VertBuf` on the WebGPU backend, backed by the common `webgpu::Buffer`
 * (Vertex | Storage | Copy* usage — a vertex buffer may also be read as an SSBO
 * by compute, and copied from as the source of GPU_storagebuf_copy_sub_from_vertbuf).
 * The GPU buffer is allocated lazily on first `upload()`; the host copy is kept
 * per the usage hint (dropped for STATIC after upload, as the Vulkan backend does).
 * `bind_as_ssbo` / `bind_as_texture` are deferred to bind-group assembly (T7 / lane B).
 */

#pragma once

#include "GPU_vertex_buffer.hh"

#include "wgpu_buffer.hh"

#include "MEM_guardedalloc.h"

namespace blender::gpu {

class WGPUVertexBuffer : public VertBuf {
 public:
  ~WGPUVertexBuffer() override;

  void bind_as_ssbo(uint binding) override;
  void bind_as_texture(uint binding) override;
  void wrap_handle(uint64_t handle) override;

  void update_sub(uint start, uint len, const void *data) override;
  void read(void *data) const override;

  const webgpu::Buffer &buffer() const
  {
    return buffer_;
  }

 protected:
  void acquire_data() override;
  void resize_data() override;
  void release_data() override;
  void upload_data() override;

 private:
  void allocate();

  webgpu::Buffer buffer_;
  bool data_uploaded_ = false;

  MEM_CXX_CLASS_ALLOC_FUNCS("WGPUVertexBuffer")
};

static inline WGPUVertexBuffer *unwrap(VertBuf *vertex_buffer)
{
  return static_cast<WGPUVertexBuffer *>(vertex_buffer);
}

}  // namespace blender::gpu
