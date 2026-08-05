/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_backend.hh @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * M3.T4 WGPUBackend skeleton. Registered `GPUBackend` for GPU_BACKEND_WEBGPU.
 * Only `context_alloc` is real (it returns a `WGPUContext` wrapping the live
 * Dawn device carried by GHOST_ContextWGPU); the resource allocators are
 * BLI_assert_unreachable placeholders (filled in by T6-T10), and the frame /
 * resource lifecycle hooks are safe no-ops so the gpu-test bootstrap can pass
 * through GPU_context_create + the pre-GPU_init path. See notes/gpu-t4-skeleton.md
 * for the deliberate no-op-vs-assert table.
 */

#pragma once

#include "gpu_backend.hh"

namespace blender::gpu {

class WGPUBackend : public GPUBackend {
 public:
  WGPUBackend() = default;
  ~WGPUBackend() override = default;

  static bool is_supported()
  {
    /* Dawn on Metal is always available on this host; a real capability probe
     * (RequestAdapter succeeds) lands with the device work in T5. */
    return true;
  }

  /* Lifecycle. init_resources constructs the shader compiler (the backend-agnostic
   * base ShaderCompiler, exactly as VKBackend does); delete_resources tears it down. */
  void init_resources() override;
  void delete_resources() override;
  void render_begin() override {}
  void render_end() override {}
  void render_step(bool force_resource_release = false) override;
  void shader_cache_dir_clear_old() override {}

  /* The real one: a context that wraps GHOST_ContextWGPU's device/queue. */
  Context *context_alloc(GHOST_IWindow *ghost_window, GHOST_IContext *ghost_context) override;

  /* Not exercised by the bootstrap — assert-unreachable until T6-T10. */
  void compute_dispatch(int groups_x_len, int groups_y_len, int groups_z_len) override;
  void compute_dispatch_indirect(StorageBuf *indirect_buf) override;
  Batch *batch_alloc() override;
  Fence *fence_alloc() override;
  FrameBuffer *framebuffer_alloc(const char *name) override;
  IndexBuf *indexbuf_alloc() override;
  PixelBuffer *pixelbuf_alloc(size_t size) override;
  QueryPool *querypool_alloc() override;
  Shader *shader_alloc(const char *name) override;
  Texture *texture_alloc(const char *name) override;
  TexturePool *texturepool_alloc() override;
  UniformBuf *uniformbuf_alloc(size_t size, const char *name) override;
  StorageBuf *storagebuf_alloc(size_t size, GPUUsageType usage, const char *name) override;
  VertBuf *vertbuf_alloc() override;
};

}  // namespace blender::gpu
