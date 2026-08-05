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
#include "wgpu_state_manager.hh"
#include "wgpu_storage_buffer.hh"
#include "wgpu_texture.hh"
#include "wgpu_uniform_buffer.hh"
#include "wgpu_vertex_buffer.hh"

#include "GPU_capabilities.hh"
#include "GPU_context.hh"
#include "GPU_platform.hh"
#include "GPU_worker.hh"
#include "gpu_context_private.hh"
#include "gpu_platform_private.hh"
#include "gpu_shader_private.hh"
#include "gpu_texture_pool_private.hh"

#include "BLI_assert.h"

#include "MEM_guardedalloc.h"

#include <vector>

namespace blender::gpu {

void WGPUBackend::platform_init()
{
  /* Static platform identity, mirroring VKBackend::platform_init() (vk_backend.cc:411).
   * WebGPU abstracts the concrete adapter, so use the ANY device/driver values; the OS
   * follows the build host (Emscripten builds fall to the UNIX branch). */
#ifdef _WIN32
  const GPUOSType os = GPU_OS_WIN;
#elif defined(__APPLE__)
  const GPUOSType os = GPU_OS_MAC;
#else
  const GPUOSType os = GPU_OS_UNIX;
#endif
  GPG.init(GPU_DEVICE_ANY,
           os,
           GPU_DRIVER_ANY,
           GPU_SUPPORT_LEVEL_SUPPORTED,
           GPU_BACKEND_WEBGPU,
           "",
           "",
           "",
           GPU_ARCHITECTURE_IMR);
}

void WGPUBackend::platform_exit()
{
  GPG.clear();
}

void WGPUBackend::init_resources()
{
  /* Publish the platform identity before anything reads GPU_platform_* (the frontend
   * asserts GPG.initialized). VKBackend does this from its constructor; init_resources
   * (GPU_init) is early enough and is where the backend-owned resources come up. */
  platform_init();

  /* The shader compiler is the backend-agnostic base ShaderCompiler; it drives the
   * async builtin warm-up GPU_init kicks off. Mirrors VKBackend::init_resources. */
  compiler_ = MEM_new<ShaderCompiler>(
      __func__, GPU_max_parallel_compilations(), GPUWorker::ContextType::Main);
}

void WGPUBackend::delete_resources()
{
  MEM_delete(compiler_);
  compiler_ = nullptr;
  platform_exit();
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

/* --- Compute dispatch ----------------------------------------------------- */

/** The active WebGPU context (holds the live Dawn device/queue + the SSBO
 * bind-space). Same resolution the draw path uses (wgpu_batch.cc). */
static WGPUContext *active_context()
{
  return static_cast<WGPUContext *>(unwrap(GPU_context_active_get()));
}

/** Assemble group-0 for a compute pass from the bound shader's resources: the
 * emulated push-constant UBO (WebGPU has no push constants) plus every StorageBuf
 * bound via GPU_storagebuf_bind (tracked in the context's bind-space). The bind
 * group's layout comes from the pipeline's auto layout so it matches the WGSL. */
static bool build_compute_bind_group(WGPUContext *ctx,
                                     WGPUShader *shader,
                                     const wgpu::ComputePipeline &pipeline,
                                     wgpu::BindGroup &r_bind_group)
{
  std::vector<wgpu::BindGroupEntry> entries;

  if (shader->has_push_constants()) {
    shader->push_constants_flush();
    const webgpu::Buffer &pc = shader->push_constants_buffer();
    if (pc.valid()) {
      wgpu::BindGroupEntry entry = {};
      entry.binding = shader->push_constants_binding();
      entry.buffer = pc.handle();
      entry.offset = 0;
      entry.size = pc.size();
      entries.push_back(entry);
    }
  }

  for (const auto &item : ctx->bound_storage_buffers()) {
    WGPUStorageBuffer *ssbo = item.second;
    if (ssbo == nullptr) {
      continue;
    }
    const webgpu::Buffer &buf = ssbo->buffer();
    if (!buf.valid()) {
      continue;
    }
    wgpu::BindGroupEntry entry = {};
    entry.binding = uint32_t(item.first);
    entry.buffer = buf.handle();
    entry.offset = 0;
    entry.size = buf.size();
    entries.push_back(entry);
  }

  /* Storage images bound via GPU_texture_image_bind (state_manager->image_bind).
   * The dense WGSL @binding is the `unit` the frontend recorded; the storage view
   * is a single-mip view matching the `texture_storage_*` binding Tint emitted. */
  WGPUStateManager *sm = static_cast<WGPUStateManager *>(ctx->state_manager);
  if (sm != nullptr) {
    for (const auto &item : sm->bound_images()) {
      webgpu::WGPUTexture *tex = static_cast<webgpu::WGPUTexture *>(item.second);
      if (tex == nullptr) {
        continue;
      }
      wgpu::TextureView view = tex->image_view();
      if (view == nullptr) {
        continue;
      }
      wgpu::BindGroupEntry entry = {};
      entry.binding = uint32_t(item.first);
      entry.textureView = view;
      entries.push_back(entry);
    }
  }

  if (entries.empty()) {
    return false;
  }

  wgpu::BindGroupDescriptor bgd = {};
  bgd.layout = pipeline.GetBindGroupLayout(0);
  bgd.entryCount = entries.size();
  bgd.entries = entries.data();
  r_bind_group = ctx->device_get().CreateBindGroup(&bgd);
  return true;
}

void WGPUBackend::compute_dispatch(int groups_x_len, int groups_y_len, int groups_z_len)
{
  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return;
  }
  WGPUShader *shader = static_cast<WGPUShader *>(ctx->shader);
  /* A failed compile leaves a null module — cannot build a pipeline. */
  if (shader == nullptr || shader->compute_module() == nullptr) {
    return;
  }

  wgpu::Device device = ctx->device_get();
  wgpu::ComputePipeline pipeline = shader->compute_pipeline(device);
  if (pipeline == nullptr) {
    return;
  }

  wgpu::BindGroup bind_group;
  const bool have_bg = build_compute_bind_group(ctx, shader, pipeline, bind_group);

  wgpu::CommandEncoder enc = device.CreateCommandEncoder();
  wgpu::ComputePassEncoder pass = enc.BeginComputePass();
  pass.SetPipeline(pipeline);
  if (have_bg) {
    pass.SetBindGroup(0, bind_group);
  }
  pass.DispatchWorkgroups(
      uint32_t(groups_x_len), uint32_t(groups_y_len), uint32_t(groups_z_len));
  pass.End();
  wgpu::CommandBuffer cb = enc.Finish();
  ctx->queue_get().Submit(1, &cb);
}

void WGPUBackend::compute_dispatch_indirect(StorageBuf *indirect_buf)
{
  BLI_assert(indirect_buf != nullptr);
  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return;
  }
  WGPUShader *shader = static_cast<WGPUShader *>(ctx->shader);
  if (shader == nullptr || shader->compute_module() == nullptr) {
    return;
  }
  /* The indirect buffer is a StorageBuf carrying the [x,y,z] group counts; its
   * webgpu::Buffer is created with the Indirect usage bit (wgpu_storage_buffer). */
  WGPUStorageBuffer *indirect = static_cast<WGPUStorageBuffer *>(indirect_buf);
  const webgpu::Buffer &indirect_gpu = indirect->buffer();
  if (!indirect_gpu.valid()) {
    return;
  }

  wgpu::Device device = ctx->device_get();
  wgpu::ComputePipeline pipeline = shader->compute_pipeline(device);
  if (pipeline == nullptr) {
    return;
  }

  wgpu::BindGroup bind_group;
  const bool have_bg = build_compute_bind_group(ctx, shader, pipeline, bind_group);

  wgpu::CommandEncoder enc = device.CreateCommandEncoder();
  wgpu::ComputePassEncoder pass = enc.BeginComputePass();
  pass.SetPipeline(pipeline);
  if (have_bg) {
    pass.SetBindGroup(0, bind_group);
  }
  pass.DispatchWorkgroupsIndirect(indirect_gpu.handle(), 0);
  pass.End();
  wgpu::CommandBuffer cb = enc.Finish();
  ctx->queue_get().Submit(1, &cb);
}

/* --- Placeholders: not reached by the M3.T4 bootstrap. -------------------- */
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
