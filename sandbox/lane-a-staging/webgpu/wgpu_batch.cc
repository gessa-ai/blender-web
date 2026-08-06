/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_batch.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * WGPUBatch — the WebGPU draw path (lane B ownership, transferred from lane A's
 * bootstrap). A draw opens a render pass over the context's active framebuffer
 * (loadOp=Load, so it appends to prior clears/draws), selects a cached
 * `wgpu::RenderPipeline` for the current (shader, geometry, state, targets,
 * primitive) tuple, binds the batch's vertex/index buffers and the shader's
 * resources, and records a Draw / DrawIndexed. */

#include "wgpu_batch.hh"

#include <vector>

#include "wgpu_context.hh"
#include "wgpu_framebuffer.hh"
#include "wgpu_index_buffer.hh"
#include "wgpu_pipeline.hh"
#include "wgpu_shader.hh"
#include "wgpu_storage_buffer.hh"
#include "wgpu_vertex_buffer.hh"

#include "GPU_context.hh"
#include "gpu_context_private.hh"
#include "gpu_state_private.hh"

#include "BLI_assert.h"

namespace blender::gpu {

static WGPUContext *active_context()
{
  return static_cast<WGPUContext *>(unwrap(GPU_context_active_get()));
}

/** The render-pipeline cache. TODO: move to WGPUContext once its ownership of
 * device-lifetime caches is wired (lane A file); a function-static pool is correct
 * for the single-device native test harness. */
static webgpu::WGPUPipelinePool &pipeline_pool()
{
  static webgpu::WGPUPipelinePool pool;
  return pool;
}

void WGPUBatch::draw(int vertex_first, int vertex_count, int instance_first, int instance_count)
{
  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return;
  }
  Context *base_ctx = Context::get();
  WGPUFrameBuffer *fb = static_cast<WGPUFrameBuffer *>(base_ctx->active_fb);
  WGPUShader *shader = static_cast<WGPUShader *>(base_ctx->shader);
  if (fb == nullptr || shader == nullptr) {
    return;
  }
  /* A failed shader compile leaves null modules — cannot build a pipeline. */
  if (shader->vertex_module() == nullptr || shader->fragment_module() == nullptr) {
    return;
  }

  /* Resolve the first vertex buffer (single interleaved layout for now) and ensure
   * it is uploaded to the device. */
  WGPUVertexBuffer *wvbo = nullptr;
  for (int i = 0; i < GPU_BATCH_VBO_MAX_LEN; i++) {
    if (verts[i] != nullptr) {
      verts[i]->upload();
      wvbo = unwrap(verts[i]);
      break;
    }
  }

  /* Assemble the pipeline key from the shader, geometry, fixed-function state, and
   * the bound framebuffer's target formats. */
  webgpu::PipelineInfo info;
  info.shader = shader;
  info.vertex_format = (wvbo != nullptr) ? &wvbo->format : nullptr;
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

  /* Multi-viewport / layered emulation (M3.F7). WebGPU has no viewport array and no
   * vertex-stage gl_Layer / gl_ViewportIndex routing, so render one pass per (array
   * layer, viewport rect): a single-layer attachment view selects the layer, a
   * per-viewport SetViewport + SetScissorRect selects the rect, and the shader discards
   * every primitive whose vertex-carried gpu_Layer / gpu_ViewportIndex != this pass's
   * (layer, viewport) — supplied in the _wgpu_mv UBO. Each 1x1 viewport therefore
   * receives exactly the primitive routed to it, matching the GL/Vulkan reference. This
   * path only runs when GPU_framebuffer_multi_viewports_set() is active (the gpu suite's
   * framebuffer_multi_viewport test); every other draw takes the single-pass path below. */
  if (fb->is_multi_viewport()) {
    wgpu::Device device = ctx->device_get();
    const int layers = fb->attachment_layer_count();

    /* Per-pass (layer, viewport) UBO: std140 { int; int; } padded to 16 bytes. Reused
     * across passes — a queue WriteBuffer is ordered before the Submit that follows it,
     * so each pass reads its own value before the next overwrite. */
    wgpu::BufferDescriptor bd = {};
    bd.size = 16;
    bd.usage = wgpu::BufferUsage::Uniform | wgpu::BufferUsage::CopyDst;
    wgpu::Buffer mv_buf = device.CreateBuffer(&bd);

    if (shader->has_push_constants()) {
      shader->push_constants_flush();
    }

    for (int layer = 0; layer < layers; layer++) {
      for (int vp = 0; vp < GPU_MAX_VIEWPORTS; vp++) {
        int rect[4];
        fb->get_viewport(vp, rect);
        if (rect[2] <= 0 || rect[3] <= 0) {
          continue; /* unused viewport slot */
        }
        const int32_t mv_vals[2] = {layer, vp};
        ctx->queue_get().WriteBuffer(mv_buf, 0, mv_vals, sizeof(mv_vals));

        wgpu::CommandEncoder mv_enc = device.CreateCommandEncoder();
        wgpu::RenderPassEncoder mv_pass = fb->begin_load_pass(mv_enc, layer);
        mv_pass.SetPipeline(pipeline);
        mv_pass.SetViewport(
            float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]), 0.0f, 1.0f);
        mv_pass.SetScissorRect(
            uint32_t(rect[0]), uint32_t(rect[1]), uint32_t(rect[2]), uint32_t(rect[3]));
        if (wvbo != nullptr && wvbo->buffer().valid()) {
          mv_pass.SetVertexBuffer(0, wvbo->buffer().handle(), 0);
        }

        std::vector<wgpu::BindGroupEntry> entries;
        wgpu::BindGroupEntry mv_entry = {};
        mv_entry.binding = shader->multi_viewport_binding();
        mv_entry.buffer = mv_buf;
        mv_entry.offset = 0;
        mv_entry.size = 16;
        entries.push_back(mv_entry);
        if (shader->has_push_constants() && shader->push_constants_buffer().valid()) {
          wgpu::BindGroupEntry pc = {};
          pc.binding = shader->push_constants_binding();
          pc.buffer = shader->push_constants_buffer().handle();
          pc.offset = 0;
          pc.size = shader->push_constants_buffer().size();
          entries.push_back(pc);
        }
        wgpu::BindGroupDescriptor bgd = {};
        bgd.layout = pipeline.GetBindGroupLayout(0);
        bgd.entryCount = uint32_t(entries.size());
        bgd.entries = entries.data();
        mv_pass.SetBindGroup(0, device.CreateBindGroup(&bgd));

        if (elem != nullptr) {
          WGPUIndexBuffer *wibo = unwrap(elem);
          if (wibo->buffer().valid()) {
            mv_pass.SetIndexBuffer(wibo->buffer().handle(), wibo->index_format(), 0);
            mv_pass.DrawIndexed(uint32_t(vertex_count),
                                uint32_t(instance_count),
                                uint32_t(vertex_first),
                                0,
                                uint32_t(instance_first));
          }
        }
        else {
          mv_pass.Draw(uint32_t(vertex_count),
                       uint32_t(instance_count),
                       uint32_t(vertex_first),
                       uint32_t(instance_first));
        }
        mv_pass.End();
        wgpu::CommandBuffer mv_cb = mv_enc.Finish();
        ctx->queue_get().Submit(1, &mv_cb);
      }
    }
    return;
  }

  wgpu::Device device = ctx->device_get();
  wgpu::CommandEncoder enc = device.CreateCommandEncoder();
  wgpu::RenderPassEncoder pass = fb->begin_load_pass(enc);
  pass.SetPipeline(pipeline);

  /* Vertex buffers. */
  if (wvbo != nullptr && wvbo->buffer().valid()) {
    pass.SetVertexBuffer(0, wvbo->buffer().handle(), 0);
  }

  /* Bind group 0: the push-constant UBO (lane A's shadow+flush+getter) plus every
   * declared resource — sampled textures + samplers, storage buffers, storage
   * images, bound UBOs — assembled by the context's shared builder. */
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
      wgpu::BindGroupDescriptor bgd = {};
      bgd.layout = pipeline.GetBindGroupLayout(0);
      bgd.entryCount = uint32_t(entries.size());
      bgd.entries = entries.data();
      pass.SetBindGroup(0, device.CreateBindGroup(&bgd));
    }
  }

  if (elem != nullptr) {
    WGPUIndexBuffer *wibo = unwrap(elem);
    if (wibo->buffer().valid()) {
      pass.SetIndexBuffer(wibo->buffer().handle(), wibo->index_format(), 0);
      /* TODO(lane-B): baseVertex from IndexBuf index_base_ once exposed. */
      pass.DrawIndexed(uint32_t(vertex_count),
                       uint32_t(instance_count),
                       uint32_t(vertex_first),
                       0,
                       uint32_t(instance_first));
    }
  }
  else {
    pass.Draw(uint32_t(vertex_count),
              uint32_t(instance_count),
              uint32_t(vertex_first),
              uint32_t(instance_first));
  }

  pass.End();
  wgpu::CommandBuffer cb = enc.Finish();
  ctx->queue_get().Submit(1, &cb);
}

void WGPUBatch::draw_indirect(StorageBuf *indirect_buf, intptr_t offset)
{
  multi_draw_indirect(indirect_buf, 1, offset, 0);
}

/* Indirect draw. WebGPU has native DrawIndirect / DrawIndexedIndirect reading the
 * draw arguments from a GPU buffer (the StorageBuf carries the Indirect usage bit —
 * wgpu_buffer.cc). WebGPU exposes no core multi-draw, so `count` draws are recorded
 * in a loop, each reading its argument block at offset + i*stride (matches the
 * frontend's contiguous GPUIndirect layout). Mirrors VKBatch::multi_draw_indirect. */
void WGPUBatch::multi_draw_indirect(StorageBuf *indirect_buf,
                                    int count,
                                    intptr_t offset,
                                    intptr_t stride)
{
  if (indirect_buf == nullptr || count <= 0) {
    return;
  }
  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return;
  }
  Context *base_ctx = Context::get();
  WGPUFrameBuffer *fb = static_cast<WGPUFrameBuffer *>(base_ctx->active_fb);
  WGPUShader *shader = static_cast<WGPUShader *>(base_ctx->shader);
  if (fb == nullptr || shader == nullptr) {
    return;
  }
  if (shader->vertex_module() == nullptr || shader->fragment_module() == nullptr) {
    return;
  }

  WGPUStorageBuffer *indirect = static_cast<WGPUStorageBuffer *>(indirect_buf);
  const webgpu::Buffer &indirect_gpu = indirect->buffer();
  if (!indirect_gpu.valid()) {
    return;
  }

  WGPUVertexBuffer *wvbo = nullptr;
  for (int i = 0; i < GPU_BATCH_VBO_MAX_LEN; i++) {
    if (verts[i] != nullptr) {
      verts[i]->upload();
      wvbo = unwrap(verts[i]);
      break;
    }
  }

  webgpu::PipelineInfo info;
  info.shader = shader;
  info.vertex_format = (wvbo != nullptr) ? &wvbo->format : nullptr;
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

  if (wvbo != nullptr && wvbo->buffer().valid()) {
    pass.SetVertexBuffer(0, wvbo->buffer().handle(), 0);
  }

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
      wgpu::BindGroupDescriptor bgd = {};
      bgd.layout = pipeline.GetBindGroupLayout(0);
      bgd.entryCount = uint32_t(entries.size());
      bgd.entries = entries.data();
      pass.SetBindGroup(0, device.CreateBindGroup(&bgd));
    }
  }

  WGPUIndexBuffer *wibo = (elem != nullptr) ? unwrap(elem) : nullptr;
  const bool indexed = (wibo != nullptr && wibo->buffer().valid());
  if (indexed) {
    pass.SetIndexBuffer(wibo->buffer().handle(), wibo->index_format(), 0);
  }

  for (int i = 0; i < count; i++) {
    const uint64_t byte_offset = uint64_t(offset) + uint64_t(i) * uint64_t(stride);
    if (indexed) {
      pass.DrawIndexedIndirect(indirect_gpu.handle(), byte_offset);
    }
    else {
      pass.DrawIndirect(indirect_gpu.handle(), byte_offset);
    }
  }

  pass.End();
  wgpu::CommandBuffer cb = enc.Finish();
  ctx->queue_get().Submit(1, &cb);
}

}  // namespace blender::gpu
