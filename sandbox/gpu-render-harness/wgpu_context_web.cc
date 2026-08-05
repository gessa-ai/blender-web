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

#include "BLI_assert.h"
#include "BLI_threads.h"
#include "BLI_utildefines.h"

#include "gpu_capabilities_private.hh"

#include "wgpu_state_manager.hh"

/* GHOST-private: the WITH_WEBGPU_BACKEND block in gpu/CMakeLists.txt adds
 * intern/ghost/intern to this TU's include path. Production should instead route
 * the handle through a GHOST_IContext virtual (mirroring getVulkanHandles) so
 * the gpu module never sees a GHOST-private header — noted in the T4 findings. */
/* HARNESS/patch-0035: the browser GHOST context is GHOST_ContextWGPUWeb, a sibling
 * of native GHOST_ContextWGPU with the same instance/adapter/device/queue accessors.
 * Bind the concrete type per target. (Record: patches/0035-gpu-webgpu-context-web.patch.) */
#ifdef __EMSCRIPTEN__
#  include "GHOST_ContextWGPUWeb.hh"
using WGPUGhostContext = GHOST_ContextWGPUWeb;
#else
#  include "GHOST_ContextWGPU.hh"
using WGPUGhostContext = GHOST_ContextWGPU;
#endif

#include <algorithm>
#include <climits>

namespace blender::gpu {

WGPUContext::WGPUContext(GHOST_IWindow *ghost_window, GHOST_IContext *ghost_context) : Context()
{
  ghost_window_ = ghost_window;

  /* The context was created by GHOST_SystemHeadless::createOffscreenContext for
   * GHOST_kDrawingContextTypeWebGPU, so it is a GHOST_ContextWGPU. Borrow its
   * already-initialized Dawn instance/adapter/device/queue (ownership stays with
   * GHOST). */
  WGPUGhostContext *wgpu_ghost = static_cast<WGPUGhostContext *>(ghost_context);
  instance_ = wgpu_ghost->getInstance();
  adapter_ = wgpu_ghost->getAdapter();
  device_ = wgpu_ghost->getDevice();
  queue_ = wgpu_ghost->getQueue();
#ifdef __EMSCRIPTEN__
  adapter_name_ = "emdawnwebgpu"; /* GHOST_ContextWGPUWeb has no getAdapterName() */
#else
  adapter_name_ = wgpu_ghost->getAdapterName();
#endif

  /* Fill the global capability table from the live device limits. Device-probed
   * (per the T9 findings recommendation), not hard-coded to the WebGPU spec
   * floors — the M4 Pro / Dawn adapter reports much higher limits. */
  capabilities_init();

  /* Per-context state manager (lane B's WGPUStateManager). The base Context dtor
   * owns its lifetime (Context::~Context deletes state_manager). Immediate mode
   * (imm) is created by lane B alongside the render pipeline. */
  state_manager = new WGPUStateManager();
}

WGPUContext::~WGPUContext()
{
  free_resources();
}

/* --- Activation --------------------------------------------------------- */
/* Mirror VKContext::activate/deactivate but without the render-graph (WebGPU's
 * implicit model needs none) and without immActivate — the WGPUImmediate is a
 * lane-B class not yet constructed by this context. Once it lands, immActivate/
 * immDeactivate hook in here exactly as the Vulkan backend does. */
void WGPUContext::activate()
{
  BLI_assert(is_active_ == false);
  is_active_ = true;
}

void WGPUContext::deactivate()
{
  is_active_ = false;
}

void WGPUContext::capabilities_init()
{
  wgpu::Limits limits = {};
  /* ConvertibleStatus converts to bool == (status == Success). */
  if (device_ == nullptr || !device_.GetLimits(&limits)) {
    return;
  }

  /* Reset all capabilities from any previous context (mirrors vk_backend.cc:911). */
  GCaps = {};

  /* WebGPU has no geometry-shader stage and no shader stencil export. */
  GCaps.geometry_shader_support = false;
  GCaps.stencil_export_support = false;

  GCaps.max_texture_size = std::max(int(limits.maxTextureDimension1D),
                                    int(limits.maxTextureDimension2D));
  GCaps.max_texture_3d_size = int(std::min<uint64_t>(limits.maxTextureDimension3D, INT_MAX));
  GCaps.max_buffer_texture_size = uint32_t(std::min<uint64_t>(limits.maxBufferSize, UINT_MAX));
  GCaps.max_texture_layers = int(std::min<uint64_t>(limits.maxTextureArrayLayers, INT_MAX));
  GCaps.max_textures = int(std::min<uint64_t>(limits.maxSampledTexturesPerShaderStage, INT_MAX));
  GCaps.max_images = int(std::min<uint64_t>(limits.maxStorageTexturesPerShaderStage, INT_MAX));
  /* WebGPU exposes a single per-dimension workgroup-count cap (not per axis). */
  const int wg_count = int(std::min<uint64_t>(limits.maxComputeWorkgroupsPerDimension, INT_MAX));
  GCaps.max_work_group_count[0] = wg_count;
  GCaps.max_work_group_count[1] = wg_count;
  GCaps.max_work_group_count[2] = wg_count;
  GCaps.max_work_group_size[0] = int(std::min<uint64_t>(limits.maxComputeWorkgroupSizeX, INT_MAX));
  GCaps.max_work_group_size[1] = int(std::min<uint64_t>(limits.maxComputeWorkgroupSizeY, INT_MAX));
  GCaps.max_work_group_size[2] = int(std::min<uint64_t>(limits.maxComputeWorkgroupSizeZ, INT_MAX));
  GCaps.max_uniforms_vert = GCaps.max_uniforms_frag = int(
      std::min<uint64_t>(limits.maxUniformBuffersPerShaderStage, INT_MAX));
  /* No maxDrawIndirectCount / maxDrawIndexedIndexValue analogs in WebGPU; the
   * spec places no cap here, so use INT_MAX (as the VK path clamps to). */
  GCaps.max_batch_indices = INT_MAX;
  GCaps.max_batch_vertices = INT_MAX;
  GCaps.max_vertex_attribs = int(std::min<uint64_t>(limits.maxVertexAttributes, INT_MAX));
  /* maxInterStageShaderVariables counts vec4 slots; ×4 → float components. */
  GCaps.max_varying_floats = int(
      std::min<uint64_t>(uint64_t(limits.maxInterStageShaderVariables) * 4u, INT_MAX));
  GCaps.max_shader_storage_buffer_bindings = GCaps.max_compute_shader_storage_blocks = int(
      std::min<uint64_t>(limits.maxStorageBuffersPerShaderStage, INT_MAX));
  GCaps.max_uniform_buffer_size = size_t(limits.maxUniformBufferBindingSize);
  GCaps.max_storage_buffer_size = size_t(limits.maxStorageBufferBindingSize);
  GCaps.storage_buffer_alignment = limits.minStorageBufferOffsetAlignment;

  GCaps.max_parallel_compilations = BLI_system_thread_count();
  /* WebGPU exposes no device memory statistics — memory_statistics_get() → 0/0. */
  GCaps.mem_stats_support = false;
  /* No portable WebGPU device-extension enumeration; leave the extension table empty. */
  GCaps.extensions_len = 0;
  GCaps.extension_get = nullptr;

  /* Use the backend-agnostic frontend texture pool (texturepool_alloc returns
   * TexturePoolImpl), the same fallback the Vulkan backend selects. */
  GCaps.texture_pool_workaround = true;
}

/* --- Frame machinery: no-ops until the render pipeline lands (T10/lane B). - */
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
