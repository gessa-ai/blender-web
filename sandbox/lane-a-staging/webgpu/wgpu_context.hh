/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_context.hh @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * WGPUContext. Wraps the live Dawn instance/adapter/device/queue carried by
 * GHOST_ContextWGPU. T5 makes `activate`/`deactivate` real (single-context
 * bookkeeping) and probes the device limits into `GPUCapabilities` (GCaps).
 * StateManager/Immediate and the render frame machinery arrive with T10/lane B,
 * so `begin_frame`/`end_frame`/`flush`/`finish` remain no-ops for now.
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

  wgpu::Instance instance_get() const
  {
    return instance_;
  }
  wgpu::Adapter adapter_get() const
  {
    return adapter_;
  }
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
  /** Probe the live device limits into the global `GPUCapabilities` (GCaps).
   * Device-probed, mirroring VKBackend::capabilities_init (vk_backend.cc:905). */
  void capabilities_init();

  wgpu::Instance instance_ = nullptr;
  wgpu::Adapter adapter_ = nullptr;
  wgpu::Device device_ = nullptr;
  wgpu::Queue queue_ = nullptr;
  std::string adapter_name_;
  /** Set between activate() and deactivate(); guards double-activation. */
  bool is_active_ = false;

  MEM_CXX_CLASS_ALLOC_FUNCS("WGPUContext")
};

}  // namespace blender::gpu
