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
#include "wgpu_context.hh"
#include "wgpu_storage_buffer.hh"

#include "gpu_texture_pool_private.hh"

#include "BLI_assert.h"

namespace blender::gpu {

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
  BLI_assert_unreachable();
  return nullptr;
}
Fence *WGPUBackend::fence_alloc()
{
  BLI_assert_unreachable();
  return nullptr;
}
FrameBuffer *WGPUBackend::framebuffer_alloc(const char * /*name*/)
{
  BLI_assert_unreachable();
  return nullptr;
}
IndexBuf *WGPUBackend::indexbuf_alloc()
{
  BLI_assert_unreachable();
  return nullptr;
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
Shader *WGPUBackend::shader_alloc(const char * /*name*/)
{
  BLI_assert_unreachable();
  return nullptr;
}
Texture *WGPUBackend::texture_alloc(const char * /*name*/)
{
  BLI_assert_unreachable();
  return nullptr;
}
TexturePool *WGPUBackend::texturepool_alloc()
{
  /* Required by Context::Context() (gpu_context.cc) for EVERY context — not a
   * draw-time allocator. Use the backend-agnostic frontend pool (as VKBackend
   * does via its texture_pool_workaround path); it only calls texture_alloc
   * lazily on acquire, which the M3.T4 bootstrap never reaches. */
  return new TexturePoolImpl();
}
UniformBuf *WGPUBackend::uniformbuf_alloc(size_t /*size*/, const char * /*name*/)
{
  BLI_assert_unreachable();
  return nullptr;
}
StorageBuf *WGPUBackend::storagebuf_alloc(size_t size, GPUUsageType usage, const char *name)
{
  /* The bootstrap's DebugDraw allocates one storage buffer; a no-op stub
   * survives bring-up (see wgpu_storage_buffer.hh). Real impl = T6. */
  return new WGPUStorageBuffer(size, usage, name);
}
VertBuf *WGPUBackend::vertbuf_alloc()
{
  BLI_assert_unreachable();
  return nullptr;
}

}  // namespace blender::gpu
