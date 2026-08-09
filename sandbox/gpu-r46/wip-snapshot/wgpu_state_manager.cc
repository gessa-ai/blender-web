/* SPDX-FileCopyrightText: 2023 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_state_manager.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * Minimal WebGPU StateManager. See wgpu_state_manager.hh for the rationale behind
 * the no-op bodies. Constructing one in the WGPUContext ctor
 * (`state_manager = new WGPUStateManager()`) is what removes the null-deref in
 * `GPU_memory_barrier` and unblocks the texture / framebuffer test families. */

#include "wgpu_state_manager.hh"

#include <iterator>

namespace blender::gpu {

/* WebGPU has an implicit memory model: work submitted to the queue is ordered and
 * hazards between passes / submits are synchronised automatically by the
 * implementation. There is no `vkCmdPipelineBarrier` / `glMemoryBarrier` analog to
 * issue, so the frontend's `GPU_memory_barrier` is a genuine no-op here. (This was
 * the exact null-deref the missing state_manager caused — see gpu_state.cc:312 and
 * notes/gpu-laneB-integration.md.) */
void WGPUStateManager::issue_barrier(GPUBarrier /*barrier_bits*/) {}

/* Pipeline state (blend / depth / stencil / cull / write-mask) is immutable in
 * WebGPU: it is baked into the `wgpu::RenderPipeline` descriptor at pipeline
 * creation (via wgpu_state_table → wgpu_pipeline), read from `this->state` /
 * `this->mutable_state` at assembly time. There is no global "apply the tracked
 * state to the device" step to perform, so these are no-ops. */
void WGPUStateManager::apply_state() {}
void WGPUStateManager::force_state() {}

/* Texture / image bindings are resolved into a `wgpu::BindGroup` at draw-time /
 * dispatch-time bind-group assembly (wgpu_batch::draw / wgpu_backend::
 * compute_dispatch). The frontend passes the CREATE-INFO SLOT as `unit`
 * (GPU_shader_get_sampler_binding → ShaderInput::binding = res.slot since r44r2, the same
 * namespace fixed create-info-slot binds use), which the bind-group builders translate to the
 * dense WGSL @binding at emit via remap_*_binding. Recording `unit → resource` here is exactly
 * what those builders look up. Mirrors VKStateManager's textures_/images_
 * BindSpace. Binding with no active draw is legitimate call ordering — the entry is
 * simply consumed at the next dispatch/draw. */
void WGPUStateManager::texture_bind(Texture *tex, GPUSamplerState sampler, int unit)
{
  textures_[unit] = BoundTexture{tex, sampler};
}

void WGPUStateManager::texture_unbind(Texture *tex)
{
  for (auto it = textures_.begin(); it != textures_.end();) {
    it = (it->second.texture == tex) ? textures_.erase(it) : std::next(it);
  }
}

void WGPUStateManager::texture_unbind_all()
{
  textures_.clear();
}

void WGPUStateManager::image_bind(Texture *tex, int unit)
{
  images_[unit] = tex;
}

void WGPUStateManager::image_unbind(Texture *tex)
{
  for (auto it = images_.begin(); it != images_.end();) {
    it = (it->second == tex) ? images_.erase(it) : std::next(it);
  }
}

void WGPUStateManager::image_unbind_all()
{
  images_.clear();
}

}  // namespace blender::gpu
