/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_uniform_buffer.hh @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * `UniformBuf` on the WebGPU backend: a `webgpu::Buffer` (Uniform kind) created
 * lazily on first update. Binding is deferred to bind-group / pipeline assembly
 * (T7 / lane B), so bind/unbind are no-ops here; create + update + clear are
 * live through the proven buffer wrapper (sandbox/wgpu-buffers/).
 */

#pragma once

#include "gpu_uniform_buffer_private.hh"

#include "wgpu_buffer.hh"

#include "MEM_guardedalloc.h"

namespace blender::gpu {

class WGPUUniformBuffer : public UniformBuf {
 public:
  WGPUUniformBuffer(size_t size, const char *name) : UniformBuf(size, name) {}
  ~WGPUUniformBuffer() override = default;

  void update(const void *data) override;
  void clear_to_zero() override;
  void bind(int slot) override;
  void bind_as_ssbo(int slot) override;
  void unbind() override;

  const webgpu::Buffer &buffer() const
  {
    return buffer_;
  }

 private:
  /** Create the underlying buffer on first use. Returns false if no context. */
  bool ensure();

  webgpu::Buffer buffer_;

  MEM_CXX_CLASS_ALLOC_FUNCS("WGPUUniformBuffer")
};

}  // namespace blender::gpu
