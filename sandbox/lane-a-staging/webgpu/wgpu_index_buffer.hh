/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_index_buffer.hh @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * `IndexBuf` on the WebGPU backend, backed by the common `webgpu::Buffer`
 * (Index | Storage | Copy* usage). Uploaded on first use via `mappedAtCreation`
 * (so odd U16 buffer sizes upload without the 4-byte writeBuffer constraint).
 * Blender uses both 16- and 32-bit index buffers; U16 buffers carry an
 * `index_base_` applied at draw time, handled by the draw encoder (lane B).
 * `update_sub` / `strip_restart_indices` are left unimplemented as on Vulkan.
 */

#pragma once

#include "GPU_index_buffer.hh"

#include "wgpu_buffer.hh"

#include "MEM_guardedalloc.h"

namespace blender::gpu {

class WGPUIndexBuffer : public IndexBuf {
 public:
  ~WGPUIndexBuffer() override = default;

  void upload_data() override;
  void bind_as_ssbo(uint binding) override;
  void read(uint32_t *data) const override;
  void update_sub(uint start, uint len, const void *data) override;

  /** WebGPU index format for this buffer (Uint16 / Uint32). */
  wgpu::IndexFormat index_format() const
  {
    return webgpu::to_wgpu_index_format(is_32bit());
  }

  const webgpu::Buffer &buffer() const;

 private:
  void strip_restart_indices() override;
  void allocate();

  webgpu::Buffer buffer_;
  bool data_uploaded_ = false;

  MEM_CXX_CLASS_ALLOC_FUNCS("WGPUIndexBuffer")
};

static inline WGPUIndexBuffer *unwrap(IndexBuf *index_buffer)
{
  return static_cast<WGPUIndexBuffer *>(index_buffer);
}

}  // namespace blender::gpu
