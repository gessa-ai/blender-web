/* SPDX-FileCopyrightText: 2023 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_immediate.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 */

#include "wgpu_immediate.hh"

#include "wgpu_buffer.hh"
#include "wgpu_context.hh"
#include "wgpu_framebuffer.hh"
#include "wgpu_pipeline.hh"
#include "wgpu_shader.hh"

#include "GPU_context.hh"
#include "GPU_matrix.hh"
#include "gpu_context_private.hh"
#include "gpu_state_private.hh"
#include "gpu_vertex_format_private.hh"

#include <vector>

namespace blender::gpu {

static WGPUContext *active_context()
{
  return static_cast<WGPUContext *>(unwrap(GPU_context_active_get()));
}

/** Immediate shares the render-pipeline cache shape with wgpu_batch; a dedicated
 * pool here avoids cross-file coupling (the cache is just a memo — a few duplicate
 * pipelines at worst). TODO: fold both into a context-owned pool. */
static webgpu::WGPUPipelinePool &pipeline_pool()
{
  static webgpu::WGPUPipelinePool pool;
  return pool;
}

uchar *WGPUImmediate::begin()
{
  const size_t bytes_needed = vertex_buffer_size(&vertex_format, vertex_len);
  if (cpu_buffer_.size() < bytes_needed) {
    cpu_buffer_.resize(bytes_needed);
  }
  return cpu_buffer_.data();
}

void WGPUImmediate::end()
{
  BLI_assert_msg(prim_type != GPU_PRIM_NONE, "Illegal state: not between an immBegin/End pair.");
  if (vertex_idx == 0) {
    return;
  }

  WGPUContext *ctx = active_context();
  Context *base_ctx = Context::get();
  if (ctx == nullptr || base_ctx == nullptr) {
    return;
  }
  WGPUFrameBuffer *fb = static_cast<WGPUFrameBuffer *>(base_ctx->active_fb);
  WGPUShader *shader = static_cast<WGPUShader *>(base_ctx->shader);
  if (fb == nullptr || shader == nullptr) {
    return;
  }
  if (shader->vertex_module() == nullptr || shader->fragment_module() == nullptr) {
    return;
  }

  /* Push the current matrix stack into the shader's uniforms (matches the other
   * backends): immediate draws rely on ModelViewProjectionMatrix. */
  GPU_matrix_bind(base_ctx->shader);

  /* Upload the recorded vertices to a transient vertex buffer. */
  const size_t data_size = vertex_buffer_size(&vertex_format, vertex_idx);
  webgpu::Buffer vbo;
  if (!vbo.create(ctx->device_get(),
                  webgpu::BufferKind::Vertex,
                  webgpu::UsageType::Static,
                  data_size,
                  cpu_buffer_.data(),
                  false))
  {
    return;
  }

  /* Select the pipeline for (shader, immediate vertex format, state, targets, prim). */
  webgpu::PipelineInfo info;
  info.shader = shader;
  info.vertex_format = &vertex_format;
  if (base_ctx->state_manager != nullptr) {
    info.state = base_ctx->state_manager->state;
    info.mutable_state = base_ctx->state_manager->mutable_state;
  }
  fb->target_formats(info.color_formats, info.color_count, info.depth_format);
  info.prim_type = prim_type;
  info.flip_y = !ctx->is_window_backbuffer(fb);

  wgpu::RenderPipeline pipeline = pipeline_pool().get(ctx->device_get(), info);
  if (pipeline == nullptr) {
    return;
  }

  wgpu::Device device = ctx->device_get();
  wgpu::CommandEncoder enc = device.CreateCommandEncoder();
  wgpu::RenderPassEncoder pass = fb->begin_load_pass(enc);
  pass.SetPipeline(pipeline);
  pass.SetVertexBuffer(0, vbo.handle(), 0);

  /* Bind group 0: the push-constant UBO (uniform colour + matrices) plus any
   * declared resources (e.g. an immBindTexture'd image + sampler) via the shared
   * builder. */
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
    ctx->append_resource_bind_entries(shader, entries);
    if (!entries.empty()) {
      pass.SetBindGroup(0, ctx->create_bind_group_checked(pipeline.GetBindGroupLayout(0), entries));
    }
  }

  pass.Draw(uint32_t(vertex_idx), 1, 0, 0);
  pass.End();
  wgpu::CommandBuffer cb = enc.Finish();
  ctx->queue_get().Submit(1, &cb);
}

}  // namespace blender::gpu
