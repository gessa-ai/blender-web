/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_storage_buffer.hh @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * `StorageBuf` on the WebGPU backend, backed by the common `webgpu::Buffer`
 * (Storage | Indirect | Copy* usage). Created lazily on first use.
 *   - `update`  → `queue.writeBuffer` / staging (proven buffer wrapper);
 *   - `clear`   → WebGPU has no fill-with-pattern, so a host-side vector of the
 *                 32-bit clear value is uploaded (faithful to the per-word clear
 *                 semantics the tests assert);
 *   - `copy_sub`→ `CopyBufferToBuffer` from a vertex buffer's GPU buffer;
 *   - `read`    → MAP_READ staging buffer + `CopyBufferToBuffer` (synchronous).
 * Binding is deferred to bind-group / pipeline assembly (T7 / lane B).
 */

#pragma once

#include "GPU_vertex_buffer.hh" /* GPUUsageType */

#include "gpu_storage_buffer_private.hh"

#include "wgpu_buffer.hh"

#include "MEM_guardedalloc.h"

namespace blender::gpu {

class WGPUStorageBuffer : public StorageBuf {
 public:
  WGPUStorageBuffer(size_t size, GPUUsageType usage, const char *name)
      : StorageBuf(size, name), usage_(usage)
  {
  }
  ~WGPUStorageBuffer() override = default;

  void update(const void *data) override;
  void bind(int slot) override;
  void unbind() override;
  void clear(uint32_t clear_value) override;
  void copy_sub(VertBuf *src, uint dst_offset, uint src_offset, uint copy_size) override;
  void read(void *data) override;
  void async_flush_to_host() override;
  void sync_as_indirect_buffer() override;

  const webgpu::Buffer &buffer() const
  {
    return buffer_;
  }

 private:
  /** Create the underlying buffer on first use. Returns false if no context. */
  bool ensure();

  webgpu::Buffer buffer_;
  GPUUsageType usage_ = GPU_USAGE_STATIC;

  MEM_CXX_CLASS_ALLOC_FUNCS("WGPUStorageBuffer")
};

}  // namespace blender::gpu
