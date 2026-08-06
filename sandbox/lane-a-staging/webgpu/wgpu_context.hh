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
#include <vector>
#include <webgpu/webgpu_cpp.h>

#include "MEM_guardedalloc.h"

namespace blender {
struct GPUSamplerState;
}

namespace blender::gpu {

class Texture;
class WGPUShader;
class WGPUStorageBuffer;
class WGPUUniformBuffer;
namespace webgpu {
class Buffer;
}

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

  /* --- VBO / IBO bound as an SSBO ------------------------------------------
   * A VertBuf or IndexBuf may be bound as a storage buffer (GPU_vertbuf_bind_as_ssbo
   * / GPU_indexbuf_bind_as_ssbo — subdiv / compute readback paths). These are not
   * WGPUStorageBuffer objects, so they need their own bind-space: the raw
   * webgpu::Buffer they own is recorded here keyed by the WGSL @binding slot and
   * added to the group-0 bind group alongside the StorageBufs. Keyed by slot, last
   * bind wins; the owning VertBuf/IndexBuf unbinds itself on release. */
  void buffer_ssbo_bind(int slot, const webgpu::Buffer *buffer)
  {
    bound_buffer_ssbos_[slot] = buffer;
  }
  void buffer_ssbo_unbind(const webgpu::Buffer *buffer)
  {
    for (auto it = bound_buffer_ssbos_.begin(); it != bound_buffer_ssbos_.end();) {
      if (it->second == buffer) {
        it = bound_buffer_ssbos_.erase(it);
      }
      else {
        ++it;
      }
    }
  }
  const std::unordered_map<int, const webgpu::Buffer *> &bound_buffer_ssbos() const
  {
    return bound_buffer_ssbos_;
  }

  /* --- Bound uniform-buffer tracking ---------------------------------------
   * Separately-bound UBOs (GPU_uniformbuf_bind, distinct from the push-constant
   * emulation UBO) recorded per dense WGSL @binding slot; consumed by
   * append_resource_bind_entries. Mirrors the storage-buffer bind-space above. */
  void uniform_buffer_bind(int slot, WGPUUniformBuffer *ubo)
  {
    bound_uniform_buffers_[slot] = ubo;
  }
  void uniform_buffer_unbind(WGPUUniformBuffer *ubo)
  {
    for (auto it = bound_uniform_buffers_.begin(); it != bound_uniform_buffers_.end();) {
      if (it->second == ubo) {
        it = bound_uniform_buffers_.erase(it);
      }
      else {
        ++it;
      }
    }
  }
  const std::unordered_map<int, WGPUUniformBuffer *> &bound_uniform_buffers() const
  {
    return bound_uniform_buffers_;
  }

  /* Append group-0 bind-group entries for every resource the bound shader declares
   * (filtered by its interface map so stale binds never leak in): bound UBOs,
   * storage buffers, VBO/IBO-as-SSBO, storage images, and sampled textures + their
   * samplers (texture half at N, sampler half at SAMPLER_BASE + N). The caller adds
   * the push-constant UBO (+ multi-viewport UBO) itself. Shared by the draw,
   * immediate and compute bind-group builders. */
  void append_resource_bind_entries(WGPUShader *shader,
                                     std::vector<wgpu::BindGroupEntry> &entries);

  /* A cached wgpu::Sampler for a GPUSamplerState (created lazily, retained for the
   * context lifetime so the handle outlives every BindGroup that references it). */
  wgpu::Sampler get_sampler(const GPUSamplerState &state);

  /* A shared zero-filled vertex buffer bound to dummy VertexState slots — the WebGPU
   * stand-in for the constant an unbound/disabled GL vertex attribute reads (WebGPU
   * forbids Vulkan's arrayStride-0 trick). Instance-stepped in the plan, so a
   * non-instanced draw reads element 0 (zeros) for every vertex. Lazily created,
   * retained for the context lifetime. */
  wgpu::Buffer dummy_vertex_buffer();

  /* Blit one colour texture into another through a fullscreen textured-quad render
   * pass. Used by WGPUFrameBuffer::blit_to when the source and destination formats
   * are NOT copy-compatible (Dawn rejects CopyTextureToTexture across formats — the
   * dominant M4 viewport blocker: region RGBA8Unorm strips copied to the BGRA8Unorm
   * window surface). Reproduces the copy's texel mapping exactly (src texel (i,j) ->
   * dst texel (dst_x + i, dst_y + j), no flip), so it is a drop-in replacement for
   * the rejected copy. Returns false if the pipeline/views could not be built. */
  bool blit_color_render(Texture *src,
                         Texture *dst,
                         uint32_t w,
                         uint32_t h,
                         uint32_t dst_x,
                         uint32_t dst_y);

  /* Create a group-0 BindGroup from `entries`, dropping any entry whose resource
   * handle is null before handing it to Dawn. A null GPUBufferBinding throws an
   * uncaught TypeError at the emdawnwebgpu JS marshaling boundary that halts the WM
   * render loop (the M4 Tab -> edit-mode crash); an incomplete group only draws a
   * recoverable Dawn validation warning. Never let a null resource reach
   * CreateBindGroup. Shared by every draw/immediate/compute bind-group builder. */
  wgpu::BindGroup create_bind_group_checked(const wgpu::BindGroupLayout &layout,
                                            const std::vector<wgpu::BindGroupEntry> &entries);

  /* Point back_left/front_left's colour attachment at the window surface's current
   * texture (windowed web build only; no-op otherwise). Called from activate(),
   * mirroring VKContext::sync_backbuffer (vk_context.cc:67). */
  void sync_backbuffer();

  /* True when `fb` is the window's surface-backed default backbuffer (back_left/
   * front_left with a live surface texture). The present-path Y-flip (M4.T14a) renders
   * these upright; every other (offscreen) target keeps the ADR-005 clip-flip. Always
   * false in the headless/native gpu build (no surface). */
  bool is_window_backbuffer(const FrameBuffer *fb) const;

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
  /** VBO/IBO buffers bound as SSBOs keyed by WGSL @binding slot (see buffer_ssbo_bind). */
  std::unordered_map<int, const webgpu::Buffer *> bound_buffer_ssbos_;
  /** Separately-bound uniform buffers keyed by WGSL @binding slot. */
  std::unordered_map<int, WGPUUniformBuffer *> bound_uniform_buffers_;
  /** wgpu::Sampler cache keyed by GPUSamplerState::as_uint(). */
  std::unordered_map<uint32_t, wgpu::Sampler> sampler_cache_;

  /* --- Cross-format colour blit (blit_color_render) ------------------------- */
  /** Shared fullscreen-triangle blit shader module (built once, lazily). */
  wgpu::ShaderModule blit_module_;
  /** Nearest/clamp sampler for the blit (exact texel copy). */
  wgpu::Sampler blit_sampler_;
  /** Blit render pipeline cache keyed by destination wgpu::TextureFormat. */
  std::unordered_map<uint32_t, wgpu::RenderPipeline> blit_pipelines_;

  /** Shared zero buffer backing dummy vertex-attribute slots (see dummy_vertex_buffer). */
  wgpu::Buffer dummy_vertex_buffer_;

  /** The GHOST drawing context (retained for sync_backbuffer's surface access);
   * mirrors VKContext::ghost_context_ (vk_context.cc:40). */
  GHOST_IContext *ghost_context_ = nullptr;
  /** Back-buffer wrapper around the window surface's current texture (web windowed);
   * owned here, re-adopted each sync_backbuffer, freed in the dtor. */
  Texture *surface_texture_ = nullptr;

  MEM_CXX_CLASS_ALLOC_FUNCS("WGPUContext")
};

}  // namespace blender::gpu
