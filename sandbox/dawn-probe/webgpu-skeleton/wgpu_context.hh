/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_context.hh @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * M3.T4 WGPUContext skeleton. Wraps the live Dawn device/queue carried by
 * GHOST_ContextWGPU. The 14 `Context` pure-virtuals are safe no-ops for the
 * bootstrap (no draws); StateManager/Immediate and the real frame machinery
 * arrive with T5/T10.
 */

#pragma once

#include "gpu_context_private.hh"

#include <string>
#include <webgpu/webgpu_cpp.h>

#include "MEM_guardedalloc.h"

namespace blender::gpu {

class WGPUContext : public Context {
 public:
  WGPUContext(GHOST_IWindow *ghost_window, GHOST_IContext *ghost_context);
  ~WGPUContext() override;

  void activate() override;
  void deactivate() override;
  void begin_frame() override;
  void end_frame() override;

  void flush() override;
  void finish() override;

  void memory_statistics_get(int *r_total_mem, int *r_free_mem) override;

  bool debug_capture_begin(const char *title) override;
  void debug_capture_end() override;
  void *debug_capture_scope_create(const char *name) override;
  bool debug_capture_scope_begin(void *scope) override;
  void debug_capture_scope_end(void *scope) override;
  void debug_unbind_all_ubo() override;
  void debug_unbind_all_ssbo() override;

  wgpu::Device device_get() const
  {
    return device_;
  }
  wgpu::Queue queue_get() const
  {
    return queue_;
  }
  const char *adapter_name() const
  {
    return adapter_name_.c_str();
  }

 private:
  wgpu::Device device_ = nullptr;
  wgpu::Queue queue_ = nullptr;
  std::string adapter_name_;

  MEM_CXX_CLASS_ALLOC_FUNCS("WGPUContext")
};

}  // namespace blender::gpu
