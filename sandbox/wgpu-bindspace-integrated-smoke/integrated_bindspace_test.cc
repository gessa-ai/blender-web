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
#include <cstring>

#include "wgpu_state_manager.hh"

#ifndef BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE
#  error "BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE must name the extracted shipping policy"
#endif
#ifndef BW_WGPU_DUMMY_VERTEX_SOURCE
#  error "BW_WGPU_DUMMY_VERTEX_SOURCE must name the extracted shipping policy"
#endif

namespace wgpu {

enum class AddressMode : uint8_t {
  ClampToEdge,
  Repeat,
  MirrorRepeat,
};
enum class FilterMode : uint8_t {
  Nearest,
  Linear,
};
enum class MipmapFilterMode : uint8_t {
  Nearest,
  Linear,
};
enum class CompareFunction : uint8_t {
  Undefined,
  LessEqual,
};

struct SamplerDescriptor {
  AddressMode addressModeU = AddressMode::ClampToEdge;
  AddressMode addressModeV = AddressMode::ClampToEdge;
  AddressMode addressModeW = AddressMode::ClampToEdge;
  FilterMode magFilter = FilterMode::Nearest;
  FilterMode minFilter = FilterMode::Nearest;
  MipmapFilterMode mipmapFilter = MipmapFilterMode::Nearest;
  float lodMinClamp = 0.0f;
  float lodMaxClamp = 32.0f;
  CompareFunction compare = CompareFunction::Undefined;
  uint16_t maxAnisotropy = 1;
};

enum class BufferUsage : uint32_t {
  Vertex = 1u << 0,
  CopyDst = 1u << 1,
};

constexpr BufferUsage operator|(const BufferUsage lhs, const BufferUsage rhs)
{
  return BufferUsage(uint32_t(lhs) | uint32_t(rhs));
}

struct BufferDescriptor {
  uint64_t size = 0;
  BufferUsage usage = BufferUsage(0);
};

struct BufferStorage {
  std::array<uint8_t, 16> bytes = {};
  BufferDescriptor descriptor = {};
};

class Buffer {
 public:
  Buffer() = default;
  Buffer(std::nullptr_t) {}
  explicit Buffer(BufferStorage *storage) : storage_(storage) {}

  bool operator==(std::nullptr_t) const
  {
    return storage_ == nullptr;
  }

  bool operator!=(std::nullptr_t) const
  {
    return storage_ != nullptr;
  }

  BufferStorage *storage() const
  {
    return storage_;
  }

 private:
  BufferStorage *storage_ = nullptr;
};

class Device {
 public:
  Device(BufferStorage *storage, uint32_t *create_count)
      : storage_(storage), create_count_(create_count)
  {
  }

  Buffer CreateBuffer(const BufferDescriptor *descriptor)
  {
    storage_->bytes.fill(0);
    storage_->descriptor = *descriptor;
    ++*create_count_;
    return Buffer(storage_);
  }

 private:
  BufferStorage *storage_;
  uint32_t *create_count_;
};

class Queue {
 public:
  explicit Queue(uint32_t *write_count) : write_count_(write_count) {}

  void WriteBuffer(const Buffer &buffer,
                   const uint64_t offset,
                   const void *data,
                   const size_t size)
  {
    if (buffer.storage() == nullptr || offset + size > buffer.storage()->bytes.size()) {
      return;
    }
    std::memcpy(buffer.storage()->bytes.data() + offset, data, size);
    ++*write_count_;
  }

 private:
  uint32_t *write_count_;
};

}  // namespace wgpu

namespace blender::gpu {
struct DummyVertexContext {
  DummyVertexContext() : device_(&storage, &create_count), queue_(&write_count) {}

  wgpu::BufferStorage storage;
  uint32_t create_count = 0;
  uint32_t write_count = 0;
  wgpu::Device device_;
  wgpu::Queue queue_;
  wgpu::Buffer dummy_vertex_buffer_ = nullptr;
};

#include BW_WGPU_SAMPLER_DESCRIPTOR_SOURCE
#include BW_WGPU_DUMMY_VERTEX_SOURCE
}  // namespace blender::gpu

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

bool sampler_descriptor_contract()
{
  struct AnisotropyCase {
    blender::GPUSamplerFiltering flag;
    uint16_t samples;
  };
  static constexpr std::array<AnisotropyCase, 4> anisotropy_cases = {{
      {blender::GPU_SAMPLER_FILTERING_ANISOTROPIC_2, 2},
      {blender::GPU_SAMPLER_FILTERING_ANISOTROPIC_4, 4},
      {blender::GPU_SAMPLER_FILTERING_ANISOTROPIC_8, 8},
      {blender::GPU_SAMPLER_FILTERING_ANISOTROPIC_16, 16},
  }};

  for (const AnisotropyCase &test : anisotropy_cases) {
    GPUSamplerState state = GPUSamplerState::default_sampler();
    state.filtering = blender::GPUSamplerFiltering(
        int(blender::GPU_SAMPLER_FILTERING_LINEAR) |
        int(blender::GPU_SAMPLER_FILTERING_MIPMAP) | int(test.flag));
    const wgpu::SamplerDescriptor descriptor =
        blender::gpu::sampler_descriptor_for_test(state);
    if (!require(descriptor.maxAnisotropy == test.samples, "anisotropy sample count") ||
        !require(descriptor.magFilter == wgpu::FilterMode::Linear,
                 "anisotropy magnitude filter") ||
        !require(descriptor.minFilter == wgpu::FilterMode::Linear,
                 "anisotropy minimum filter") ||
        !require(descriptor.mipmapFilter == wgpu::MipmapFilterMode::Linear,
                 "anisotropy mipmap filter") ||
        !require(descriptor.lodMaxClamp == 1000.0f, "anisotropy mipmap LOD range"))
    {
      return false;
    }
  }

  GPUSamplerState nearest_anisotropic = GPUSamplerState::default_sampler();
  nearest_anisotropic.filtering = blender::GPUSamplerFiltering(
      int(blender::GPU_SAMPLER_FILTERING_MIPMAP) |
      int(blender::GPU_SAMPLER_FILTERING_ANISOTROPIC_4));
  const wgpu::SamplerDescriptor nearest_descriptor =
      blender::gpu::sampler_descriptor_for_test(nearest_anisotropic);
  if (!require(nearest_descriptor.maxAnisotropy == 4,
               "anisotropy survives a nearest-filter request") ||
      !require(nearest_descriptor.magFilter == wgpu::FilterMode::Linear &&
                   nearest_descriptor.minFilter == wgpu::FilterMode::Linear &&
                   nearest_descriptor.mipmapFilter == wgpu::MipmapFilterMode::Linear,
               "Dawn-valid anisotropy forces linear filters"))
  {
    return false;
  }

  GPUSamplerState gated = GPUSamplerState::default_sampler();
  gated.filtering = blender::GPU_SAMPLER_FILTERING_ANISOTROPIC_16;
  if (!require(blender::gpu::sampler_descriptor_for_test(gated).maxAnisotropy == 1,
               "anisotropy requires mipmapping"))
  {
    return false;
  }

  const wgpu::SamplerDescriptor icon =
      blender::gpu::sampler_descriptor_for_test(GPUSamplerState::icon_sampler());
  const wgpu::SamplerDescriptor compare =
      blender::gpu::sampler_descriptor_for_test(GPUSamplerState::compare_sampler());
  if (!require(icon.magFilter == wgpu::FilterMode::Linear &&
                   icon.minFilter == wgpu::FilterMode::Linear && icon.lodMaxClamp == 1.0f &&
                   icon.maxAnisotropy == 1,
               "icon sampler policy") ||
      !require(compare.magFilter == wgpu::FilterMode::Linear &&
                   compare.minFilter == wgpu::FilterMode::Linear &&
                   compare.compare == wgpu::CompareFunction::LessEqual &&
                   compare.maxAnisotropy == 1,
               "comparison sampler policy"))
  {
    return false;
  }

  struct AddressCase {
    blender::GPUSamplerExtendMode mode;
    wgpu::AddressMode expected;
  };
  static constexpr std::array<AddressCase, 4> address_cases = {{
      {blender::GPU_SAMPLER_EXTEND_MODE_EXTEND, wgpu::AddressMode::ClampToEdge},
      {blender::GPU_SAMPLER_EXTEND_MODE_REPEAT, wgpu::AddressMode::Repeat},
      {blender::GPU_SAMPLER_EXTEND_MODE_MIRRORED_REPEAT, wgpu::AddressMode::MirrorRepeat},
      {blender::GPU_SAMPLER_EXTEND_MODE_CLAMP_TO_BORDER, wgpu::AddressMode::ClampToEdge},
  }};
  for (const AddressCase &test : address_cases) {
    GPUSamplerState state = GPUSamplerState::default_sampler();
    state.extend_x = test.mode;
    state.extend_yz = test.mode;
    const wgpu::SamplerDescriptor descriptor =
        blender::gpu::sampler_descriptor_for_test(state);
    if (!require(descriptor.addressModeU == test.expected &&
                     descriptor.addressModeV == test.expected &&
                     descriptor.addressModeW == test.expected,
                 "sampler address mode"))
    {
      return false;
    }
  }

  std::printf(
      "CONTRACT sampler-descriptors PASS anisotropy=2,4,8,16 gated=1 custom=2 address=4\n");
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

bool dummy_vertex_default_contract()
{
  blender::gpu::DummyVertexContext context;
  const wgpu::Buffer first = blender::gpu::dummy_vertex_buffer_for_test(context);
  const wgpu::Buffer second = blender::gpu::dummy_vertex_buffer_for_test(context);
  std::array<uint32_t, 4> words = {};
  std::memcpy(words.data(), context.storage.bytes.data(), context.storage.bytes.size());
  const uint32_t expected_usage = uint32_t(wgpu::BufferUsage::Vertex) |
                                  uint32_t(wgpu::BufferUsage::CopyDst);

  if (!require(first != nullptr && second.storage() == first.storage(),
               "dummy vertex handle reuse") ||
      !require(context.create_count == 1, "dummy vertex created once") ||
      !require(context.write_count == 1, "dummy vertex initialized once") ||
      !require(context.storage.descriptor.size == 16, "dummy vertex byte size") ||
      !require(uint32_t(context.storage.descriptor.usage) == expected_usage,
               "dummy vertex usage") ||
      !require(words[0] == 0u && words[1] == 0u && words[2] == 0u,
               "dummy vertex xyz defaults") ||
      !require(words[3] == 0x3f800000u, "dummy vertex w defaults to one"))
  {
    return false;
  }

  std::printf("CONTRACT dummy-vertex-default PASS creates=1 writes=1 w=%08x\n", words[3]);
  return true;
}

}  // namespace

int main()
{
  if (!default_state_contract() || !texture_bind_space_contract() ||
      !image_bind_space_contract() || !sampler_descriptor_contract() ||
      !no_op_and_fence_contract() || !dummy_vertex_default_contract())
  {
    return 1;
  }
  std::printf(
      "INTEGRATED_BINDSPACE_PASS contracts=6 texture_binds=5 image_binds=5 dummy_w=3f800000\n");
  return 0;
}
