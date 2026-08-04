/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_context.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 */

#include "wgpu_context.hh"

/* GHOST-private: the WITH_WEBGPU_BACKEND block in gpu/CMakeLists.txt adds
 * intern/ghost/intern to this TU's include path. Production should instead route
 * the handle through a GHOST_IContext virtual (mirroring getVulkanHandles) so
 * the gpu module never sees a GHOST-private header — noted in the T4 findings. */
#include "GHOST_ContextWGPU.hh"

namespace blender::gpu {

WGPUContext::WGPUContext(GHOST_IWindow *ghost_window, GHOST_IContext *ghost_context) : Context()
{
  ghost_window_ = ghost_window;

  /* The context was created by GHOST_SystemHeadless::createOffscreenContext for
   * GHOST_kDrawingContextTypeWebGPU, so it is a GHOST_ContextWGPU. Borrow its
   * already-initialized Dawn device/queue (ownership stays with GHOST). */
  GHOST_ContextWGPU *wgpu_ghost = static_cast<GHOST_ContextWGPU *>(ghost_context);
  device_ = wgpu_ghost->getDevice();
  queue_ = wgpu_ghost->getQueue();
  adapter_name_ = wgpu_ghost->getAdapterName();
}

WGPUContext::~WGPUContext()
{
  free_resources();
}

/* --- Bootstrap-safe no-ops (no draws exercised at M3.T4). ----------------- */
void WGPUContext::activate() {}
void WGPUContext::deactivate() {}
void WGPUContext::begin_frame() {}
void WGPUContext::end_frame() {}
void WGPUContext::flush() {}
void WGPUContext::finish() {}

void WGPUContext::memory_statistics_get(int *r_total_mem, int *r_free_mem)
{
  *r_total_mem = 0;
  *r_free_mem = 0;
}

bool WGPUContext::debug_capture_begin(const char * /*title*/)
{
  return false;
}
void WGPUContext::debug_capture_end() {}
void *WGPUContext::debug_capture_scope_create(const char * /*name*/)
{
  return nullptr;
}
bool WGPUContext::debug_capture_scope_begin(void * /*scope*/)
{
  return false;
}
void WGPUContext::debug_capture_scope_end(void * /*scope*/) {}
void WGPUContext::debug_unbind_all_ubo() {}
void WGPUContext::debug_unbind_all_ssbo() {}

}  // namespace blender::gpu
