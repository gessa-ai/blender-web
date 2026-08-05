/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_backend.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 */

#include "wgpu_backend.hh"
#include "wgpu_batch.hh"
#include "wgpu_context.hh"
#include "wgpu_framebuffer.hh"
#include "wgpu_index_buffer.hh"
#include "wgpu_shader.hh"
#include "wgpu_storage_buffer.hh"
#include "wgpu_texture.hh"
#include "wgpu_uniform_buffer.hh"
#include "wgpu_vertex_buffer.hh"

#include "GPU_capabilities.hh"
#include "GPU_worker.hh"
#include "gpu_shader_private.hh"
#include "gpu_texture_pool_private.hh"

#include "BLI_assert.h"

#include "MEM_guardedalloc.h"

namespace blender::gpu {

void WGPUBackend::init_resources()
{
  /* The shader compiler is the backend-agnostic base ShaderCompiler; it drives the
   * async builtin warm-up GPU_init kicks off. Mirrors VKBackend::init_resources. */
  compiler_ = MEM_new<ShaderCompiler>(
      __func__, GPU_max_parallel_compilations(), GPUWorker::ContextType::Main);
}

void WGPUBackend::delete_resources()
{
  MEM_delete(compiler_);
  compiler_ = nullptr;
}

void WGPUBackend::render_step(bool /*force_resource_release*/) {}

Context *WGPUBackend::context_alloc(GHOST_IWindow *ghost_window, GHOST_IContext *ghost_context)
{
  /* Mirror VKBackend::context_alloc: resolve the offscreen ghost context. */
  if (ghost_window) {
    BLI_assert(ghost_context == nullptr);
    ghost_context = ghost_window->getDrawingContext();
  }
  BLI_assert(ghost_context != nullptr);
  return new WGPUContext(ghost_window, ghost_context);
}

/* --- Placeholders: not reached by the M3.T4 bootstrap. -------------------- */
void WGPUBackend::compute_dispatch(int /*x*/, int /*y*/, int /*z*/)
{
  BLI_assert_unreachable();
}
void WGPUBackend::compute_dispatch_indirect(StorageBuf * /*indirect_buf*/)
{
  BLI_assert_unreachable();
}
Batch *WGPUBackend::batch_alloc()
{
  /* Bootstrap-minimal batch: base Batch owns vbo/ibo storage; the draw path is
   * lane B (WGPUBatch's draw virtuals assert until then). */
  return new WGPUBatch();
}
Fence *WGPUBackend::fence_alloc()
{
  BLI_assert_unreachable();
  return nullptr;
}
FrameBuffer *WGPUBackend::framebuffer_alloc(const char *name)
{
  /* Lane B's WGPUFrameBuffer (patch 0030). */
  return new WGPUFrameBuffer(name);
}
IndexBuf *WGPUBackend::indexbuf_alloc()
{
  return new WGPUIndexBuffer();
}
PixelBuffer *WGPUBackend::pixelbuf_alloc(size_t /*size*/)
{
  BLI_assert_unreachable();
  return nullptr;
}
QueryPool *WGPUBackend::querypool_alloc()
{
  BLI_assert_unreachable();
  return nullptr;
}
Shader *WGPUBackend::shader_alloc(const char *name)
{
  return new WGPUShader(name);
}
Texture *WGPUBackend::texture_alloc(const char *name)
{
  /* Lane B's WGPUTexture (patch 0016b) — the full gpu::Texture surface. */
  return new webgpu::WGPUTexture(name);
}
TexturePool *WGPUBackend::texturepool_alloc()
{
  /* Required by Context::Context() (gpu_context.cc) for EVERY context — not a
   * draw-time allocator. Use the backend-agnostic frontend pool (as VKBackend
   * does via its texture_pool_workaround path); it only calls texture_alloc
   * lazily on acquire, which the M3.T4 bootstrap never reaches. */
  return new TexturePoolImpl();
}
UniformBuf *WGPUBackend::uniformbuf_alloc(size_t size, const char *name)
{
  return new WGPUUniformBuffer(size, name);
}
StorageBuf *WGPUBackend::storagebuf_alloc(size_t size, GPUUsageType usage, const char *name)
{
  /* Functional GPUBuffer-backed storage buffer (update / clear / copy_sub / read). */
  return new WGPUStorageBuffer(size, usage, name);
}
VertBuf *WGPUBackend::vertbuf_alloc()
{
  return new WGPUVertexBuffer();
}

}  // namespace blender::gpu
