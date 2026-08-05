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
#include <unordered_map>
#include <webgpu/webgpu_cpp.h>

#include "MEM_guardedalloc.h"

namespace blender::gpu {

class WGPUStorageBuffer;

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

  /* --- Bound storage-buffer tracking ---------------------------------------
   * WebGPU has no global binding state (bindings live in a per-draw/-dispatch
   * BindGroup), so the backend tracks which StorageBuf is bound to which WGSL
   * @binding slot here. Recorded by WGPUStorageBuffer::bind()/unbind(); consumed
   * by WGPUBackend::compute_dispatch to assemble the group-0 bind group. Mirrors
   * VKStateManager's storage-buffer bind-space. Keyed by binding slot; last bind
   * to a slot wins (matches the frontend rebinding a slot per dispatch). */
  void storage_buffer_bind(int slot, WGPUStorageBuffer *ssbo)
  {
    bound_storage_buffers_[slot] = ssbo;
  }
  void storage_buffer_unbind(WGPUStorageBuffer *ssbo)
  {
    for (auto it = bound_storage_buffers_.begin(); it != bound_storage_buffers_.end();) {
      if (it->second == ssbo) {
        it = bound_storage_buffers_.erase(it);
      }
      else {
        ++it;
      }
    }
  }
  const std::unordered_map<int, WGPUStorageBuffer *> &bound_storage_buffers() const
  {
    return bound_storage_buffers_;
  }

  /* Backend-wide device/instance/queue, reachable from any thread (there is a
   * single Dawn device). Used by the async shader-compile worker, which has no
   * thread-local active GPU context. */
  static wgpu::Device backend_device()
  {
    return s_device;
  }
  static wgpu::Instance backend_instance()
  {
    return s_instance;
  }
  static wgpu::Queue backend_queue()
  {
    return s_queue;
  }

 private:
  /** Probe the live device limits into the global `GPUCapabilities` (GCaps).
   * Device-probed, mirroring VKBackend::capabilities_init (vk_backend.cc:905). */
  void capabilities_init();

  static wgpu::Device s_device;
  static wgpu::Instance s_instance;
  static wgpu::Queue s_queue;

  wgpu::Instance instance_ = nullptr;
  wgpu::Adapter adapter_ = nullptr;
  wgpu::Device device_ = nullptr;
  wgpu::Queue queue_ = nullptr;
  std::string adapter_name_;
  /** Set between activate() and deactivate(); guards double-activation. */
  bool is_active_ = false;
  /** Bound storage buffers keyed by WGSL @binding slot (see storage_buffer_bind). */
  std::unordered_map<int, WGPUStorageBuffer *> bound_storage_buffers_;

  MEM_CXX_CLASS_ALLOC_FUNCS("WGPUContext")
};

}  // namespace blender::gpu
