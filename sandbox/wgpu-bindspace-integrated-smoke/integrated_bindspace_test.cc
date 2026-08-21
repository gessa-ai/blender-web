/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm contract for the canonical in-tree WebGPU state
 * manager bind spaces and queue-ordered fence lifecycle. */

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>

#include "wgpu_state_manager.hh"

namespace {

using blender::GPUSamplerState;
using blender::GPU_BARRIER_SHADER_STORAGE;
using blender::GPU_BLEND_ALPHA;
using blender::GPU_BLEND_NONE;
using blender::GPU_CULL_NONE;
using blender::GPU_DEPTH_NONE;
using blender::GPU_STENCIL_NONE;
using blender::GPU_STENCIL_OP_NONE;
using blender::GPU_VERTEX_LAST;
using blender::GPU_WRITE_COLOR;
using blender::gpu::Texture;
using blender::gpu::TextureWriteFormat;
using blender::gpu::WGPUFence;
using blender::gpu::WGPUStateManager;

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "FAIL %s\n", message);
    return false;
  }
  return true;
}

class InspectableFence : public WGPUFence {
 public:
  bool signalled() const
  {
    return signalled_;
  }
};

struct TextureToken {
  alignas(std::max_align_t) std::array<std::byte, sizeof(void *)> storage = {};

  Texture *pointer()
  {
    return reinterpret_cast<Texture *>(storage.data());
  }
};

bool default_state_contract()
{
  WGPUStateManager manager;
  size_t invalid_formats = 0;
  for (const TextureWriteFormat format : manager.image_formats) {
    invalid_formats += format == TextureWriteFormat::Invalid;
  }

  if (!require(manager.state.write_mask == GPU_WRITE_COLOR, "default color write mask") ||
      !require(manager.state.blend == GPU_BLEND_NONE, "default blend") ||
      !require(manager.state.culling_test == GPU_CULL_NONE, "default cull mode") ||
      !require(manager.state.depth_test == GPU_DEPTH_NONE, "default depth test") ||
      !require(manager.state.stencil_test == GPU_STENCIL_NONE, "default stencil test") ||
      !require(manager.state.stencil_op == GPU_STENCIL_OP_NONE, "default stencil op") ||
      !require(manager.state.provoking_vert == GPU_VERTEX_LAST, "default provoking vertex") ||
      !require(manager.mutable_state.point_size == -1.0f, "default point size") ||
      !require(manager.mutable_state.line_width == 1.0f, "default line width") ||
      !require(manager.mutable_state.stencil_write_mask == 0u, "default stencil write mask") ||
      !require(manager.mutable_state.stencil_compare_mask == 0u,
               "default stencil compare mask") ||
      !require(manager.mutable_state.stencil_reference == 0u, "default stencil reference") ||
      !require(invalid_formats == manager.image_formats.size(), "default image formats"))
  {
    return false;
  }

  std::printf("CONTRACT default-state PASS image_formats=%zu\n", invalid_formats);
  return true;
}

bool texture_bind_space_contract()
{
  WGPUStateManager manager;
  TextureToken token_a;
  TextureToken token_b;
  TextureToken token_c;
  Texture *texture_a = token_a.pointer();
  Texture *texture_b = token_b.pointer();
  Texture *texture_c = token_c.pointer();

  manager.texture_bind(texture_a, GPUSamplerState::default_sampler(), 2);
  manager.texture_bind(texture_a, GPUSamplerState::icon_sampler(), 7);
  manager.texture_bind(texture_b, GPUSamplerState::compare_sampler(), 2);
  if (!require(manager.bound_textures().size() == 2, "texture bind census") ||
      !require(manager.bound_textures().at(2).texture == texture_b, "texture last bind wins") ||
      !require(manager.bound_textures().at(2).sampler == GPUSamplerState::compare_sampler(),
               "texture rebound sampler") ||
      !require(manager.bound_textures().at(7).texture == texture_a,
               "texture independent slot") ||
      !require(manager.bound_textures().at(7).sampler == GPUSamplerState::icon_sampler(),
               "texture independent sampler"))
  {
    return false;
  }

  manager.image_bind(texture_c, 2);
  if (!require(manager.bound_images().at(2) == texture_c,
               "texture and image namespaces are independent") ||
      !require(manager.bound_textures().at(2).texture == texture_b,
               "image bind preserves texture slot"))
  {
    return false;
  }

  manager.texture_unbind(texture_a);
  if (!require(manager.bound_textures().size() == 1, "texture unbind removes every alias") ||
      !require(manager.bound_textures().at(2).texture == texture_b,
               "texture unbind preserves other resource"))
  {
    return false;
  }
  manager.texture_bind(texture_b, GPUSamplerState::default_sampler(), 9);
  manager.texture_unbind(texture_b);
  if (!require(manager.bound_textures().empty(), "texture unbind removes two slots")) {
    return false;
  }

  manager.texture_bind(texture_c, GPUSamplerState::default_sampler(), 4);
  manager.texture_unbind_all();
  if (!require(manager.bound_textures().empty(), "texture unbind all") ||
      !require(manager.bound_images().size() == 1, "texture clear preserves image namespace"))
  {
    return false;
  }

  std::printf("CONTRACT texture-bind-space PASS binds=5 aliases_removed=3 namespaces=2\n");
  return true;
}

bool image_bind_space_contract()
{
  WGPUStateManager manager;
  TextureToken token_a;
  TextureToken token_b;
  TextureToken token_c;
  Texture *texture_a = token_a.pointer();
  Texture *texture_b = token_b.pointer();
  Texture *texture_c = token_c.pointer();

  manager.image_bind(texture_a, 1);
  manager.image_bind(texture_b, 4);
  manager.image_bind(texture_c, 1);
  if (!require(manager.bound_images().size() == 2, "image bind census") ||
      !require(manager.bound_images().at(1) == texture_c, "image last bind wins") ||
      !require(manager.bound_images().at(4) == texture_b, "image independent slot"))
  {
    return false;
  }

  manager.image_unbind(texture_c);
  if (!require(manager.bound_images().size() == 1, "image unbind one slot") ||
      !require(manager.bound_images().at(4) == texture_b, "image unbind preserves peer"))
  {
    return false;
  }
  manager.image_bind(texture_b, 8);
  manager.image_unbind(texture_b);
  if (!require(manager.bound_images().empty(), "image unbind removes every alias")) {
    return false;
  }

  manager.image_bind(texture_a, 5);
  manager.image_bind(texture_b, 6);
  manager.image_unbind_all();
  if (!require(manager.bound_images().empty(), "image unbind all")) {
    return false;
  }

  std::printf("CONTRACT image-bind-space PASS binds=5 aliases_removed=3\n");
  return true;
}

bool no_op_and_fence_contract()
{
  WGPUStateManager manager;
  TextureToken texture_token;
  manager.texture_bind(texture_token.pointer(), GPUSamplerState::default_sampler(), 3);
  manager.image_bind(texture_token.pointer(), 5);
  manager.state.blend = GPU_BLEND_ALPHA;
  manager.mutable_state.point_size = 7.25f;
  const blender::gpu::GPUState before_state = manager.state;
  const blender::gpu::GPUStateMutable before_mutable = manager.mutable_state;

  manager.apply_state();
  manager.force_state();
  manager.issue_barrier(GPU_BARRIER_SHADER_STORAGE);
  if (!require(manager.state == before_state, "implicit state apply preserves immutable state") ||
      !require(manager.mutable_state == before_mutable,
               "implicit state apply preserves mutable state") ||
      !require(manager.bound_textures().size() == 1, "barrier preserves texture binds") ||
      !require(manager.bound_images().size() == 1, "barrier preserves image binds"))
  {
    return false;
  }

  InspectableFence fence;
  if (!require(!fence.signalled(), "fence initially unsignalled")) {
    return false;
  }
  fence.wait();
  if (!require(!fence.signalled(), "wait before signal is inert")) {
    return false;
  }
  fence.signal();
  fence.signal();
  if (!require(fence.signalled(), "signal marks fence")) {
    return false;
  }
  fence.wait();
  if (!require(!fence.signalled(), "wait consumes signal")) {
    return false;
  }
  fence.wait();
  if (!require(!fence.signalled(), "repeated wait remains inert")) {
    return false;
  }

  std::printf("CONTRACT no-op-and-fence PASS barriers=1 signals=2 waits=3\n");
  return true;
}

}  // namespace

int main()
{
  if (!default_state_contract() || !texture_bind_space_contract() ||
      !image_bind_space_contract() || !no_op_and_fence_contract())
  {
    return 1;
  }
  std::printf("INTEGRATED_BINDSPACE_PASS contracts=4 texture_binds=5 image_binds=5\n");
  return 0;
}
