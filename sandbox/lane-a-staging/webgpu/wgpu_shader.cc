/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_shader.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * Real WGPUShader: create-info → GLSL codegen (dense set-0 bindings, ported from
 * the Vulkan backend) → shaderc(GLSL→SPIR-V 1.3) → Tint(→WGSL) → WGPUShaderModule,
 * via the in-tree wgpu_shader_compiler module.
 */

#include "wgpu_shader.hh"

#include "GPU_context.hh"
#include "gpu_context_private.hh"

#include "wgpu_context.hh"
#include "wgpu_shader_interface_map.hh"
#include "wgpu_texture_format.hh"

#include "gpu_shader_dependency_private.hh"

#include "BLI_map.hh"
#include "BLI_memory_utils.hh"
#include "BLI_string_ref.hh"
#include "BLI_vector.hh"

#include "CLG_log.h"

#include <algorithm>
#include <cctype>
#include <cstring>
#include <sstream>
#include <unordered_map>
#include <vector>

namespace blender::gpu {

using namespace shader;
namespace wgi = blender::gpu::webgpu;

static CLG_LogRef LOG = {"gpu.webgpu"};


/* -------------------------------------------------------------------------- */
/** \name GLSL type / format helpers (ported from vk_shader.cc)
 * \{ */

static const char *to_string(const Interpolation &interp)
{
  switch (interp) {
    case Interpolation::SMOOTH:
      return "smooth";
    case Interpolation::FLAT:
      return "flat";
    case Interpolation::NO_PERSPECTIVE:
      return "noperspective";
    default:
      return "unknown";
  }
}

static const char *to_string(const Type &type)
{
  switch (type) {
    case Type::float_t:
      return "float";
    case Type::float2_t:
      return "vec2";
    case Type::float3_t:
      return "vec3";
    case Type::float4_t:
      return "vec4";
    case Type::float3x3_t:
      return "mat3";
    case Type::float4x4_t:
      return "mat4";
    case Type::uint_t:
      return "uint";
    case Type::uint2_t:
      return "uvec2";
    case Type::uint3_t:
      return "uvec3";
    case Type::uint4_t:
      return "uvec4";
    case Type::int_t:
      return "int";
    case Type::int2_t:
      return "ivec2";
    case Type::int3_t:
      return "ivec3";
    case Type::int4_t:
      return "ivec4";
    case Type::bool_t:
      return "bool";
    default:
      return "unknown";
  }
}

static const char *to_string(const TextureFormat &type)
{
  switch (type) {
    case TextureFormat::UINT_8_8_8_8:
      return "rgba8ui";
    case TextureFormat::SINT_8_8_8_8:
      return "rgba8i";
    case TextureFormat::UNORM_8_8_8_8:
      return "rgba8";
    case TextureFormat::UINT_32_32_32_32:
      return "rgba32ui";
    case TextureFormat::SINT_32_32_32_32:
      return "rgba32i";
    case TextureFormat::SFLOAT_32_32_32_32:
      return "rgba32f";
    case TextureFormat::UINT_16_16_16_16:
      return "rgba16ui";
    case TextureFormat::SINT_16_16_16_16:
      return "rgba16i";
    case TextureFormat::SFLOAT_16_16_16_16:
      return "rgba16f";
    case TextureFormat::UNORM_16_16_16_16:
      return "rgba16";
    case TextureFormat::UINT_8_8:
      return "rg8ui";
    case TextureFormat::SINT_8_8:
      return "rg8i";
    case TextureFormat::UNORM_8_8:
      return "rg8";
    case TextureFormat::UINT_32_32:
      return "rg32ui";
    case TextureFormat::SINT_32_32:
      return "rg32i";
    case TextureFormat::SFLOAT_32_32:
      return "rg32f";
    case TextureFormat::UINT_16_16:
      return "rg16ui";
    case TextureFormat::SINT_16_16:
      return "rg16i";
    case TextureFormat::SFLOAT_16_16:
      return "rg16f";
    case TextureFormat::UNORM_16_16:
      return "rg16";
    case TextureFormat::UINT_8:
      return "r8ui";
    case TextureFormat::SINT_8:
      return "r8i";
    case TextureFormat::UNORM_8:
      return "r8";
    case TextureFormat::UINT_32:
      return "r32ui";
    case TextureFormat::SINT_32:
      return "r32i";
    case TextureFormat::SFLOAT_32:
      return "r32f";
    case TextureFormat::UINT_16:
      return "r16ui";
    case TextureFormat::SINT_16:
      return "r16i";
    case TextureFormat::SFLOAT_16:
      return "r16f";
    case TextureFormat::UNORM_16:
      return "r16";
    case TextureFormat::UFLOAT_11_11_10:
      return "r11f_g11f_b10f";
    case TextureFormat::UNORM_10_10_10_2:
      return "rgb10_a2";
    default:
      return "unknown";
  }
}

static void print_qualifier(std::ostream &os, const Qualifier &qualifiers)
{
  /* Restrict is on by default unless no_restrict is set. */
  if (bool(qualifiers & Qualifier::no_restrict) == false) {
    os << "restrict ";
  }
  if (bool(qualifiers & Qualifier::read) == false) {
    os << "writeonly ";
  }
  if (bool(qualifiers & Qualifier::write) == false) {
    os << "readonly ";
  }
}

/* Storage-buffer qualifier: WGSL has no write-only storage address space (Tint
 * rejects `var<storage>` without read/read_write). So a GLSL `writeonly` SSBO is
 * promoted to read_write; only a genuinely read-only buffer keeps `readonly`. */
static void print_storage_buffer_qualifier(std::ostream &os, const Qualifier &qualifiers)
{
  if (bool(qualifiers & Qualifier::no_restrict) == false) {
    os << "restrict ";
  }
  const bool readable = bool(qualifiers & Qualifier::read);
  const bool writable = bool(qualifiers & Qualifier::write);
  if (readable && !writable) {
    os << "readonly ";
  }
  /* write-only or read+write → emit no access qualifier (read_write in WGSL). */
}

static void print_image_type(std::ostream &os,
                             const ImageType &type,
                             const ShaderCreateInfo::Resource::BindType bind_type)
{
  switch (type) {
    case ImageType::IntBuffer:
    case ImageType::Int1D:
    case ImageType::Int1DArray:
    case ImageType::Int2D:
    case ImageType::Int2DArray:
    case ImageType::Int3D:
    case ImageType::IntCube:
    case ImageType::IntCubeArray:
    case ImageType::AtomicInt2D:
    case ImageType::AtomicInt2DArray:
    case ImageType::AtomicInt3D:
      os << "i";
      break;
    case ImageType::UintBuffer:
    case ImageType::Uint1D:
    case ImageType::Uint1DArray:
    case ImageType::Uint2D:
    case ImageType::Uint2DArray:
    case ImageType::Uint3D:
    case ImageType::UintCube:
    case ImageType::UintCubeArray:
    case ImageType::AtomicUint2D:
    case ImageType::AtomicUint2DArray:
    case ImageType::AtomicUint3D:
      os << "u";
      break;
    default:
      break;
  }

  if (bind_type == ShaderCreateInfo::Resource::BindType::IMAGE) {
    os << "image";
  }
  else {
    os << "sampler";
  }

  switch (type) {
    case ImageType::FloatBuffer:
    case ImageType::IntBuffer:
    case ImageType::UintBuffer:
      os << "Buffer";
      break;
    case ImageType::Float1D:
    case ImageType::Float1DArray:
    case ImageType::Int1D:
    case ImageType::Int1DArray:
    case ImageType::Uint1D:
    case ImageType::Uint1DArray:
      os << "1D";
      break;
    case ImageType::Float2D:
    case ImageType::Float2DArray:
    case ImageType::Int2D:
    case ImageType::Int2DArray:
    case ImageType::Uint2D:
    case ImageType::Uint2DArray:
    case ImageType::Shadow2D:
    case ImageType::Shadow2DArray:
    case ImageType::Depth2D:
    case ImageType::Depth2DArray:
    case ImageType::AtomicInt2D:
    case ImageType::AtomicInt2DArray:
    case ImageType::AtomicUint2D:
    case ImageType::AtomicUint2DArray:
      os << "2D";
      break;
    case ImageType::Float3D:
    case ImageType::Int3D:
    case ImageType::AtomicInt3D:
    case ImageType::Uint3D:
    case ImageType::AtomicUint3D:
      os << "3D";
      break;
    case ImageType::FloatCube:
    case ImageType::FloatCubeArray:
    case ImageType::IntCube:
    case ImageType::IntCubeArray:
    case ImageType::UintCube:
    case ImageType::UintCubeArray:
    case ImageType::ShadowCube:
    case ImageType::ShadowCubeArray:
    case ImageType::DepthCube:
    case ImageType::DepthCubeArray:
      os << "Cube";
      break;
    default:
      break;
  }

  switch (type) {
    case ImageType::Float1DArray:
    case ImageType::Float2DArray:
    case ImageType::FloatCubeArray:
    case ImageType::Int1DArray:
    case ImageType::Int2DArray:
    case ImageType::IntCubeArray:
    case ImageType::Uint1DArray:
    case ImageType::Uint2DArray:
    case ImageType::UintCubeArray:
    case ImageType::Shadow2DArray:
    case ImageType::ShadowCubeArray:
    case ImageType::Depth2DArray:
    case ImageType::DepthCubeArray:
    case ImageType::AtomicUint2DArray:
      os << "Array";
      break;
    default:
      break;
  }

  switch (type) {
    case ImageType::Shadow2D:
    case ImageType::Shadow2DArray:
    case ImageType::ShadowCube:
    case ImageType::ShadowCubeArray:
      os << "Shadow";
      break;
    default:
      break;
  }
  os << " ";
}

/* Assign each create-info resource a UNIQUE dense group-0 binding, in the canonical
 * pass→batch→geometry order. Blender's create-info `slot` collides across resource
 * classes (image/sampler/UBO/SSBO reuse slot numbers, since Vulkan gives each its
 * own descriptor space), but WGSL/WebGPU has one binding space per group and Tint
 * rejects duplicate `@group(0) @binding(N)`. Returns the resource count, which is
 * the binding used for the push-constant fallback UBO. */
static uint32_t build_dense_bindings(const shader::ShaderCreateInfo &info,
                                     blender::Map<uint32_t, uint32_t> &r_map)
{
  uint32_t binding = 0;
  auto scan = [&](const auto &list) {
    for (const ShaderCreateInfo::Resource &res : list) {
      r_map.add_overwrite((uint32_t(res.bind_type) << 24) | uint32_t(res.slot), binding);
      binding++;
    }
  };
  scan(info.pass_resources_);
  scan(info.batch_resources_);
  scan(info.geometry_resources_);
  return binding;
}

static uint32_t dense_binding_of(const blender::Map<uint32_t, uint32_t> &map,
                                 const ShaderCreateInfo::Resource &res)
{
  return map.lookup((uint32_t(res.bind_type) << 24) | uint32_t(res.slot));
}

/* A texel/buffer sampler — samplerBuffer / isamplerBuffer / usamplerBuffer, the GLSL
 * type of a Vulkan/GL *buffer texture* (`ImageType::{Float,Int,Uint}Buffer`). WGSL has
 * no texel-buffer type and Tint's SPIR-V reader hard-rejects the SampledBuffer
 * capability, so the WebGPU backend emulates it as a read-only std430 storage buffer
 * (option (a), notes/gpu-sampledbuffer-design.md): the resource is declared as a
 * `readonly buffer` and every `texelFetch(buf, i)` is rewritten to an indexed load
 * (rewrite_texel_buffers). This SMALL core handles the geometry position / indirection
 * buffers (curves / point cloud); the customdata-attribute helpers that take a
 * samplerBuffer *by function parameter* are the MEDIUM tail and stay blocked. */
static bool is_buffer_sampler(const ShaderCreateInfo::Resource &res)
{
  return res.bind_type == ShaderCreateInfo::Resource::BindType::SAMPLER &&
         (res.sampler.type == ImageType::FloatBuffer ||
          res.sampler.type == ImageType::IntBuffer ||
          res.sampler.type == ImageType::UintBuffer);
}

/* Element type of the storage buffer that emulates a texel buffer, chosen for the
 * LAUNCH texel format of the source VertBuf (which needs zero component conversion on
 * fetch): RGBA32F -> vec4, R32I -> int, R32UI -> uint. `texelFetch` on a texel buffer
 * always yields a gvec4 (format-expanded); the position buffers are RGBA32F so `buf[i]`
 * IS that gvec4, while the R32I/R32UI single-component buffers are wrapped back into a
 * gvec4 by rewrite_texel_buffers so `.r`/`.x` swizzles keep working. Non-launch formats
 * are rejected at bind time (WGPUTexture::init_internal(VertBuf*)). */
static const char *buffer_sampler_element_type(ImageType type)
{
  switch (type) {
    case ImageType::IntBuffer:
      return "int";
    case ImageType::UintBuffer:
      return "uint";
    default:
      return "vec4"; /* FloatBuffer (RGBA32F). */
  }
}

/* Dense set-0 binding (the combined-sampler split + reserved sampler range are
 * applied later by the interface map / Tint, not in the GLSL). */
static void print_resource(std::ostream &os,
                           uint32_t binding,
                           const ShaderCreateInfo::Resource &res,
                           const ShaderCreateInfo &info)
{
  /* Texel buffer -> read-only std430 storage buffer (see is_buffer_sampler). */
  if (is_buffer_sampler(res)) {
    os << "layout(binding = " << binding << ", std430) readonly buffer _" << res.sampler.name
       << " { " << buffer_sampler_element_type(res.sampler.type) << " " << res.sampler.name
       << "[]; };";
    return;
  }

  os << "layout(binding = " << binding;
  if (res.bind_type == ShaderCreateInfo::Resource::BindType::IMAGE) {
    os << ", " << to_string(res.image.format);
  }
  else if (res.bind_type == ShaderCreateInfo::Resource::BindType::UNIFORM_BUFFER) {
    os << ", std140";
  }
  else if (res.bind_type == ShaderCreateInfo::Resource::BindType::STORAGE_BUFFER) {
    os << ", std430";
  }
  os << ") ";

  switch (res.bind_type) {
    case ShaderCreateInfo::Resource::BindType::SAMPLER:
      os << "uniform ";
      print_image_type(os, res.sampler.type, res.bind_type);
      os << res.sampler.name << ";";
      break;
    case ShaderCreateInfo::Resource::BindType::IMAGE:
      os << "uniform ";
      print_qualifier(os, res.image.qualifiers);
      print_image_type(os, res.image.type, res.bind_type);
      os << res.image.name << ";";
      break;
    case ShaderCreateInfo::Resource::BindType::UNIFORM_BUFFER:
      os << "uniform _" << res.uniformbuf.name.str_no_array() << " { "
         << info.buffer_typename(res.uniformbuf.type_name, true) << " " << res.uniformbuf.name
         << "; };";
      break;
    case ShaderCreateInfo::Resource::BindType::STORAGE_BUFFER:
      print_storage_buffer_qualifier(os, res.storagebuf.qualifiers);
      os << "buffer _" << res.storagebuf.name.str_no_array() << " { "
         << info.buffer_typename(res.storagebuf.type_name) << " " << res.storagebuf.name << "; };";
      break;
  }
}

/* Defer a resource declaration into the create-info placeholder macro
 * (`#define CREATE_INFO_RES_<freq>_<info> \ …`), exactly as the Vulkan backend does
 * (vk_shader.cc:408). The shader-translation tool emits the matching placeholder
 * (`#ifdef CREATE_INFO_RES_<freq>_<info> … #endif`) in the resolved source AFTER the
 * (possibly `[[host_shared]]`) struct definitions and the `#define <Struct>_host_shared_
 * <Struct>` aliases they carry, so a buffer whose element type is `<Struct>_host_shared_`
 * resolves to the real struct at expansion time. Emitting the declaration inline in the
 * resources block (which precedes the resolved `code`) instead references that alias
 * before its `#define`, and shaderc rejects the still-suffixed identifier with a "syntax
 * error, unexpected IDENTIFIER" — the bug this fixes. Consecutive resources sharing an
 * `info_name` accumulate into one macro via `\`-continuation. */
static void print_resource_deferred(std::ostream &os,
                                    uint32_t binding,
                                    const ShaderCreateInfo::Resource &res,
                                    const ShaderCreateInfo &info,
                                    const char *frequency,
                                    StringRefNull &active_info_name)
{
  if (assign_if_different(active_info_name, res.info_name)) {
    os << "\n#define CREATE_INFO_RES_" << frequency << "_" << res.info_name << " \\\n";
  }
  print_resource(os, binding, res, info);
  os << " \\\n";
}

static inline int get_location_count(const Type &type)
{
  if (type == Type::float4x4_t) {
    return 4;
  }
  if (type == Type::float3x3_t) {
    return 3;
  }
  return 1;
}

static void print_interface_as_attributes(std::ostream &os,
                                          const std::string &prefix,
                                          const StageInterfaceInfo &iface,
                                          int &location)
{
  for (const StageInterfaceInfo::InOut &inout : iface.inouts) {
    os << "layout(location=" << location << ") " << prefix << " " << to_string(inout.interp) << " "
       << to_string(inout.type) << " " << inout.name << ";\n";
    location += get_location_count(inout.type);
  }
}

static void print_interface_as_struct(std::ostream &os,
                                      const std::string &prefix,
                                      const StageInterfaceInfo &iface,
                                      int &location,
                                      const StringRefNull &suffix)
{
  std::string struct_name = prefix + iface.name;
  Interpolation qualifier = iface.inouts[0].interp;

  os << "struct " << struct_name << " {\n";
  for (const StageInterfaceInfo::InOut &inout : iface.inouts) {
    os << "  " << to_string(inout.type) << " " << inout.name << ";\n";
  }
  os << "};\n";
  os << "layout(location=" << location << ") " << prefix << " " << to_string(qualifier) << " "
     << struct_name << " " << iface.instance_name << suffix << ";\n";

  for (const StageInterfaceInfo::InOut &inout : iface.inouts) {
    location += get_location_count(inout.type);
  }
}

static void print_interface(std::ostream &os,
                            const std::string &prefix,
                            const StageInterfaceInfo &iface,
                            int &location,
                            const StringRefNull &suffix = "")
{
  if (iface.instance_name.is_empty()) {
    print_interface_as_attributes(os, prefix, iface, location);
  }
  else {
    print_interface_as_struct(os, prefix, iface, location, suffix);
  }
}

/** \} */

/* -------------------------------------------------------------------------- */
/** \name Shader interface (name → location/binding) + std140 push-constant layout
 * \{ */

/* std140 base alignment + size for a create-info Type (single element or array). */
static void std140_align_size(Type t, int array_size, uint32_t &r_align, uint32_t &r_size)
{
  uint32_t a, s;
  switch (t) {
    case Type::float_t:
    case Type::int_t:
    case Type::uint_t:
    case Type::bool_t:
      a = 4;
      s = 4;
      break;
    case Type::float2_t:
    case Type::int2_t:
    case Type::uint2_t:
      a = 8;
      s = 8;
      break;
    case Type::float3_t:
    case Type::int3_t:
    case Type::uint3_t:
      a = 16;
      s = 12;
      break;
    case Type::float4_t:
    case Type::int4_t:
    case Type::uint4_t:
      a = 16;
      s = 16;
      break;
    case Type::float3x3_t:
      a = 16;
      s = 48;
      break;
    case Type::float4x4_t:
      a = 16;
      s = 64;
      break;
    default:
      a = 16;
      s = 16;
      break;
  }
  if (array_size > 0) {
    r_align = 16;
    const uint32_t stride = (s + 15u) & ~15u;
    r_size = stride * uint32_t(array_size);
  }
  else {
    r_align = a;
    r_size = s;
  }
}

static constexpr int32_t PUSH_CONSTANT_LOCATION_BASE = 1024;

/* Minimal ShaderInterface: name → location/binding for attributes, UBOs, samplers,
 * images, push-constants (as uniforms at 1024+i), SSBOs, constants. Mirrors
 * VKShaderInterface's ordering so the frontend name lookups resolve identically. */
class WGPUShaderInterface : public ShaderInterface {
 public:
  void init(const shader::ShaderCreateInfo &info)
  {
    using Resource = ShaderCreateInfo::Resource;
    static const char PUSH_FALLBACK[] = "push_constants_fallback";

    Vector<Resource> all;
    all.extend(info.pass_resources_);
    all.extend(info.batch_resources_);
    all.extend(info.geometry_resources_);

    /* Unique dense group-0 bindings (same assignment as the codegen + ResourceDesc). */
    blender::Map<uint32_t, uint32_t> bindings;
    build_dense_bindings(info, bindings);

    attr_len_ = info.vertex_inputs_.size();
    uniform_len_ = info.push_constants_.size();
    constant_len_ = info.specialization_constants_.size();
    ssbo_len_ = 0;
    ubo_len_ = 0;
    for (const Resource &res : all) {
      switch (res.bind_type) {
        case Resource::BindType::IMAGE:
        case Resource::BindType::SAMPLER:
          uniform_len_++;
          break;
        case Resource::BindType::UNIFORM_BUFFER:
          ubo_len_++;
          break;
        case Resource::BindType::STORAGE_BUFFER:
          ssbo_len_++;
          break;
      }
    }
    size_t names_size = info.interface_names_size_;
    const bool has_push = !info.push_constants_.is_empty();
    if (has_push) {
      ubo_len_++; /* fallback UBO for the push-constant block. */
      names_size += sizeof(PUSH_FALLBACK);
    }

    const int input_tot_len = attr_len_ + ubo_len_ + uniform_len_ + ssbo_len_ + constant_len_;
    inputs_ = MEM_new_array_zeroed<ShaderInput>(input_tot_len, __func__);
    name_buffer_ = MEM_new_array_uninitialized<char>(names_size, "name_buffer");
    uint32_t name_offset = 0;
    ShaderInput *in = inputs_;

    /* Attributes. */
    for (const ShaderCreateInfo::VertIn &attr : info.vertex_inputs_) {
      copy_input_name(in, attr.name, name_buffer_, name_offset);
      in->location = in->binding = attr.index;
      if (in->location != -1) {
        enabled_attr_mask_ |= (1 << in->location);
        attr_types_[in->location] = uint8_t(attr.type);
      }
      in++;
    }
    /* Uniform blocks. */
    for (const Resource &res : all) {
      if (res.bind_type == Resource::BindType::UNIFORM_BUFFER) {
        const uint32_t b = dense_binding_of(bindings, res);
        copy_input_name(in, res.uniformbuf.name, name_buffer_, name_offset);
        in->location = in->binding = int32_t(b);
        enabled_ubo_mask_ |= (1 << b);
        in++;
      }
    }
    if (has_push) {
      copy_input_name(in, PUSH_FALLBACK, name_buffer_, name_offset);
      in->location = in->binding = -1;
      in++;
    }
    /* Samplers + images (uniform section). */
    for (const Resource &res : all) {
      if (res.bind_type == Resource::BindType::SAMPLER) {
        const uint32_t b = dense_binding_of(bindings, res);
        copy_input_name(in, res.sampler.name, name_buffer_, name_offset);
        in->location = in->binding = int32_t(b);
        enabled_tex_mask_ |= (uint64_t(1) << b);
        in++;
      }
    }
    for (const Resource &res : all) {
      if (res.bind_type == Resource::BindType::IMAGE) {
        const uint32_t b = dense_binding_of(bindings, res);
        copy_input_name(in, res.image.name, name_buffer_, name_offset);
        in->location = in->binding = int32_t(b);
        enabled_ima_mask_ |= (1 << b);
        in++;
      }
    }
    /* Push-constants (uniform section, location base 1024). */
    int32_t push_location = PUSH_CONSTANT_LOCATION_BASE;
    for (const ShaderCreateInfo::PushConst &pc : info.push_constants_) {
      copy_input_name(in, pc.name, name_buffer_, name_offset);
      in->location = push_location++;
      in->binding = -1;
      in++;
    }
    /* Storage buffers. */
    for (const Resource &res : all) {
      if (res.bind_type == Resource::BindType::STORAGE_BUFFER) {
        const uint32_t b = dense_binding_of(bindings, res);
        copy_input_name(in, res.storagebuf.name, name_buffer_, name_offset);
        in->location = in->binding = int32_t(b);
        enabled_ssbo_mask_ |= (1 << b);
        in++;
      }
    }
    /* Specialization constants. */
    int constant_id = 0;
    for (const SpecializationConstant &c : info.specialization_constants_) {
      copy_input_name(in, c.name, name_buffer_, name_offset);
      in->location = constant_id++;
      in++;
    }

    set_image_formats_from_info(info);
    sort_inputs();

    /* Populate the builtin-uniform lookup tables. The base ShaderInterface ctor only
     * fills image_formats_ and leaves builtins_[]/builtin_blocks_[] uninitialised, so
     * without this loop uniform_builtin(GPU_UNIFORM_MVP) returns garbage and
     * GPU_matrix_bind uploads the MVP to the wrong location (leaving it zero → degenerate
     * geometry). Mirrors vk_shader_interface.cc:190-203. */
    for (int32_t u_int = 0; u_int < GPU_NUM_UNIFORMS; u_int++) {
      GPUUniformBuiltin u = static_cast<GPUUniformBuiltin>(u_int);
      const ShaderInput *uni = this->uniform_get(builtin_uniform_name(u));
      builtins_[u] = (uni != nullptr) ? uni->location : -1;
    }
    for (int32_t u_int = 0; u_int < GPU_NUM_UNIFORM_BLOCKS; u_int++) {
      GPUUniformBlockBuiltin u = static_cast<GPUUniformBlockBuiltin>(u_int);
      const ShaderInput *block = this->ubo_get(builtin_uniform_block_name(u));
      builtin_blocks_[u] = (block != nullptr) ? block->binding : -1;
    }
  }

  MEM_CXX_CLASS_ALLOC_FUNCS("WGPUShaderInterface")
};

/** \} */

/* -------------------------------------------------------------------------- */
/** \name WGPUShader
 * \{ */

WGPUShader::WGPUShader(const char *name) : Shader(name) {}

WGPUShader::~WGPUShader() {}

void WGPUShader::init(const shader::ShaderCreateInfo & /*info*/, bool /*is_codegen_only*/) {}

const shader::ShaderCreateInfo &WGPUShader::patch_create_info(
    const shader::ShaderCreateInfo &original_info)
{
  /* No geometry-injection patching: WebGPU has no geometry stage (those shaders are
   * skipped by the frontend when geometry_shader_support is false). */
  return original_info;
}

std::string WGPUShader::resources_declare(const shader::ShaderCreateInfo &info) const
{
  std::stringstream ss;

  /* Specialization constants (pass-through, mirrors vk_shader.cc:758-782). Declared
   * as GLSL constant_id constants so shaderc emits a SPIR-V OpSpecConstant that
   * Tint's reader lowers to a WGSL `override` (pipeline-overridable). The default
   * value is baked here; the specialised value is applied at pipeline creation.
   * Without these declarations every spec-constant reference is an "undeclared
   * identifier" at the shaderc front end. */
  {
    int constant_id = 0;
    for (const SpecializationConstant &sc : info.specialization_constants_) {
      ss << "layout(constant_id = " << constant_id++ << ") const ";
      switch (sc.type) {
        case Type::int_t:
          ss << "int " << sc.name << " = " << std::to_string(sc.value.i) << ";\n";
          break;
        case Type::uint_t:
          ss << "uint " << sc.name << " = " << std::to_string(sc.value.u) << "u;\n";
          break;
        case Type::bool_t:
          ss << "bool " << sc.name << " = " << (sc.value.u ? "true" : "false") << ";\n";
          break;
        case Type::float_t:
          /* uintBitsToFloat is not allowed in a global const initializer, so specialise
           * the uint bit pattern and alias the float via #define (exactly vk_shader.cc:772),
           * preserving the exact bits even for NaN defaults. */
          ss << "uint " << sc.name << "_uint = " << std::to_string(sc.value.u) << "u;\n";
          ss << "#define " << sc.name << " uintBitsToFloat(" << sc.name << "_uint)\n";
          break;
        default:
          break;
      }
    }
  }

  /* Compilation constants (pass-through, mirrors vk_shader.cc:784-801). Plain GLSL
   * const — baked at compile time, never overridable (scalar int/uint/bool only). */
  for (const CompilationConstant &sc : info.compilation_constants_) {
    switch (sc.type) {
      case Type::int_t:
        ss << "const int " << sc.name << " = " << std::to_string(sc.value.i) << ";\n";
        break;
      case Type::uint_t:
        ss << "const uint " << sc.name << " = " << std::to_string(sc.value.u) << "u;\n";
        break;
      case Type::bool_t:
        ss << "const bool " << sc.name << " = " << (sc.value.u ? "true" : "false") << ";\n";
        break;
      default:
        break;
    }
  }
  ss << "\n";

  /* Compute shared variables. A GLSL `shared` global lowers through shaderc to a
   * SPIR-V Workgroup-storage variable, which Tint reads into WGSL `var<workgroup>` --
   * WGSL's workgroup address space is the faithful target, so once declared the
   * translation chain carries it with no further work. Deferred into the per-create-info
   * CREATE_INFO_RES_SHARED_VARS_<info> placeholder macro (the shader-translation tool
   * emits the matching `#ifdef CREATE_INFO_RES_SHARED_VARS_<name>` in the resolved
   * source: shader_tool/processor.cc:383) exactly like the resource-frequency blocks
   * below, mirroring vk_shader.cc:803-811. The variable name carries its array dimensions
   * (e.g. "block[gl_WorkGroupSize.x][gl_WorkGroupSize.y]"), so gl_WorkGroupSize must be in
   * scope where the placeholder expands -- it is, because that placeholder follows the
   * compute layout(local_size) declaration. Without this every `shared`-variable
   * reference is an "undeclared identifier" at the shaderc front end (the compositor
   * parallel-reduction, summed-area-table and EEVEE reduction / tilemap compute set). */
  {
    StringRefNull active_info = "";
    for (const ShaderCreateInfo::SharedVariable &sv : info.shared_variables_) {
      if (assign_if_different(active_info, sv.info_name)) {
        ss << "\n#define CREATE_INFO_RES_SHARED_VARS_" << sv.info_name << " \\\n";
      }
      ss << "shared " << to_string(sv.type) << " " << sv.name << ";";
      ss << " \\\n";
    }
    ss << "\n";
  }

  blender::Map<uint32_t, uint32_t> bindings;
  const uint32_t resource_count = build_dense_bindings(info, bindings);
  /* Resource declarations are deferred into the per-create-info placeholder macros so
   * that `_host_shared_` struct-alias references resolve at expansion time (see
   * print_resource_deferred). Group by frequency exactly like vk_shader.cc:816. */
  {
    StringRefNull active_info = "";
    for (const ShaderCreateInfo::Resource &res : info.pass_resources_) {
      print_resource_deferred(ss, dense_binding_of(bindings, res), res, info, "PASS", active_info);
    }
    ss << "\n";
  }
  {
    StringRefNull active_info = "";
    for (const ShaderCreateInfo::Resource &res : info.batch_resources_) {
      print_resource_deferred(ss, dense_binding_of(bindings, res), res, info, "BATCH", active_info);
    }
    ss << "\n";
  }
  {
    StringRefNull active_info = "";
    for (const ShaderCreateInfo::Resource &res : info.geometry_resources_) {
      print_resource_deferred(
          ss, dense_binding_of(bindings, res), res, info, "GEOMETRY", active_info);
    }
    ss << "\n";
  }
  /* Push constants → a UBO (WebGPU has no push constants). Placed at the dense
   * binding after the last resource. */
  if (!info.push_constants_.is_empty()) {
    ss << "layout(binding = " << resource_count << ", std140) uniform constants\n{\n";
    for (const ShaderCreateInfo::PushConst &uniform : info.push_constants_) {
      ss << "  " << to_string(uniform.type) << " " << uniform.name;
      if (uniform.array_size > 0) {
        ss << "[" << uniform.array_size << "]";
      }
      ss << ";\n";
    }
    ss << "};\n";
  }

  /* Multi-viewport / layered emulation pass state (M3.F7): the (layer, viewport) this
   * render pass targets. The fragment wrapper (fragment_interface_declare) discards
   * primitives whose vertex-carried gpu_Layer / gpu_ViewportIndex != these. Placed at the
   * dense binding after the push-constant fallback UBO; the backend writes it per pass
   * (wgpu_batch.cc, binding = multi_viewport_binding()). Only emitted for VIEWPORT_INDEX
   * shaders (the multi-viewport path), so no other shader gains a binding. */
  if (flag_is_set(info.builtins_, BuiltinBits::VIEWPORT_INDEX)) {
    const uint32_t mv_binding = resource_count + (info.push_constants_.is_empty() ? 0u : 1u);
    ss << "layout(binding = " << mv_binding << ", std140) uniform _wgpu_mv {\n";
    ss << "  int wgpu_mv_layer;\n";
    ss << "  int wgpu_mv_viewport;\n";
    ss << "};\n";
  }
  ss << "\n";
  return ss.str();
}

std::string WGPUShader::vertex_interface_declare(const shader::ShaderCreateInfo &info) const
{
  std::stringstream ss;

  for (const ShaderCreateInfo::VertIn &attr : info.vertex_inputs_) {
    ss << "layout(location = " << attr.index << ") in " << to_string(attr.type) << " " << attr.name
       << ";\n";
  }
  int location = 0;
  for (const StageInterfaceInfo *iface : info.vertex_out_interfaces_) {
    print_interface(ss, "out", *iface, location);
  }

  /* WebGPU has no geometry stage, no writable gl_Layer / gl_ViewportIndex output
   * builtin, and no viewport-array — so layered / multi-viewport routing cannot be
   * expressed in the vertex stage here (faithful emulation is deferred: M3.F7).
   * Declare gpu_Layer / gpu_ViewportIndex as plain module-scope ints so shaders that
   * WRITE them still COMPILE; the stores are discarded (single-layer, single-viewport
   * behaviour). Without this, gpu_ViewportIndex is undeclared → shaderc fails → null
   * shader → GPU_shader_bind SEGV. Mirrors the builtin gate in vk_shader.cc:881-898
   * (the non-geometry branch), minus the gl_Layer/gl_ViewportIndex aliasing WebGPU
   * lacks. */
  if (flag_is_set(info.builtins_, BuiltinBits::VIEWPORT_INDEX)) {
    /* Multi-viewport / layered emulation (M3.F7). WebGPU has no viewport array and no
     * vertex-stage gl_Layer / gl_ViewportIndex output, so the backend renders one pass
     * per (layer, viewport) with a single-layer attachment view + per-viewport scissor
     * (wgpu_batch.cc / wgpu_framebuffer.cc) and DISCARDS in the fragment every primitive
     * whose routing target != the pass. To reach the fragment, the vertex-computed
     * gpu_Layer / gpu_ViewportIndex are carried as flat integer varyings (constant across
     * a primitive). The user main writes them as ordinary `out` ints. */
    ss << "layout(location = " << location++ << ") flat out int gpu_Layer;\n";
    ss << "layout(location = " << location++ << ") flat out int gpu_ViewportIndex;\n";
  }
  else if (flag_is_set(info.builtins_, BuiltinBits::LAYER)) {
    /* Pure layered rendering without a viewport array: no faithful single-pass route in
     * WebGPU either (deferred), so keep the write-only throwaway (renders to layer 0). */
    ss << "int gpu_Layer = 0;\n";
  }
  ss << "\n";

  /* Retarget depth from -1..1 (GL convention the GLSL is written in) to 0..1
   * (WebGPU/Vulkan clip space). The user main() is renamed via #define. */
  /* Y-orientation flip (ADR-005 decision 1) as a pipeline-overridable sign (M4.T14a).
   * WebGPU has +Y-up NDC and no negative-viewport-height escape hatch. OFFSCREEN targets
   * negate clip-space Y (default sign -1.0f, paired with the front-face swap + readback
   * row-flip) to match the GL convention the oracle tests encode. The WINDOW surface is
   * composited directly by the browser (no readback), and +Y-up NDC already displays
   * upright, so a negated window appears upside-down. The backend overrides the sign to
   * +1.0f for the surface-backed backbuffer only (wgpu_pipeline.cc, keyed by
   * PipelineInfo::flip_y) -- window passes render upright while every offscreen pipeline
   * keeps the -1.0f default byte-for-byte (the override is simply not set). Declared as
   * the uint bit pattern + a uintBitsToFloat alias, mirroring the float spec-constant
   * encoding in resources_declare (uintBitsToFloat is illegal in a global const
   * initializer). constant_id 1000 is reserved, above any create-info specialization
   * constant (which number from 0). */
  ss << "layout(constant_id = 1000) const uint gpu_clip_y_sign_uint = 0xBF800000u;\n";
  ss << "#define gpu_clip_y_sign uintBitsToFloat(gpu_clip_y_sign_uint)\n";
  ss << "void main_function_();\n";
  ss << "void main() {\n";
  ss << "  main_function_();\n";
  ss << "  gl_Position.z = (gl_Position.z + gl_Position.w) * 0.5;\n";
  ss << "  gl_Position.y = gl_Position.y * gpu_clip_y_sign;\n";
  ss << "}\n";
  ss << "#define main main_function_\n";

  /* WGSL/Tint dropped point-size support: a non-constant store to the SPIR-V
   * PointSize builtin fails Tint's IR reader ("store to point_size is not a
   * constant"), and WebGPU rasterises every point at 1px regardless. Redirect
   * gl_PointSize to a throwaway module-scope float so point-drawing vertex shaders
   * COMPILE (the size is discarded — faithful point sizing needs the point->quad
   * emulation, deferred with the multi-viewport/point work). gl_PointSize is
   * write-only in the vertex stage, so this loses only the point size; in shaders
   * that never write it the sink is an unused global that Tint dead-code-eliminates.
   * The #define + sink precede the (later) user source, so its writes are rewritten;
   * declared here (after the wrapper) to keep this codegen block clear of the
   * builtin-interface block above. Unconditional because ShaderCreateInfo exposes
   * only the source FILENAME here (vertex_source_), not the body, so a usage gate is
   * unreliable. Only the WebGPU codegen is touched — other backends are unchanged. */
  ss << "float gpu_PointSize_sink = 1.0;\n";
  ss << "#define gl_PointSize gpu_PointSize_sink\n";
  return ss.str();
}

std::string WGPUShader::fragment_interface_declare(const shader::ShaderCreateInfo &info) const
{
  std::stringstream ss;

  int location = 0;
  for (const StageInterfaceInfo *iface : info.vertex_out_interfaces_) {
    print_interface(ss, "in", *iface, location);
  }

  /* Match the vertex stage: declare gpu_Layer / gpu_ViewportIndex so fragment shaders
   * that READ them COMPILE. WebGPU exposes no gl_Layer / gl_ViewportIndex in the
   * fragment stage, so these read 0 (single-layer / single-viewport). Faithful
   * per-primitive routing is deferred (M3.F7). Mirrors vk_shader.cc:976-981. */
  if (flag_is_set(info.builtins_, BuiltinBits::VIEWPORT_INDEX)) {
    /* Match the vertex stage's flat-out varyings (M3.F7 multi-viewport emulation). */
    ss << "layout(location = " << location++ << ") flat in int gpu_Layer;\n";
    ss << "layout(location = " << location++ << ") flat in int gpu_ViewportIndex;\n";
  }
  else if (flag_is_set(info.builtins_, BuiltinBits::LAYER)) {
    ss << "int gpu_Layer = 0;\n";
  }

  /* gl_PointCoord (fragment builtin). Tint's SPIR-V reader hard-rejects the PointCoord
   * built-in ("unhandled SPIR-V BuiltIn: PointCoord") because WebGPU has no point
   * sprites -- points always rasterise at 1px (see gl_PointSize, M3.F6c), so there is no
   * in-point coordinate to hand back. Redirect gl_PointCoord to a zero-initialised
   * module-scope vec2 via #define so the point shaders that read it (AA point outlines,
   * keyframe shapes: gpu_shader_point_*_frag, overlay_edit_*_point) still COMPILE; the
   * read yields (0,0) instead of the position within the point -- a faithful degradation
   * (round points collapse to their centre) while point-sprite emulation (point->quad)
   * stays deferred with the multi-viewport / point work. Same declare-to-compile pattern
   * as gl_PointSize; gated on the POINT_COORD builtin bit exactly like
   * mtl_shader_generate.cc:1327 (Blender guarantees the bit is set whenever a shader
   * references gl_PointCoord -- other backends provide it the same way). */
  if (flag_is_set(info.builtins_, BuiltinBits::POINT_COORD)) {
    ss << "vec2 gpu_PointCoord_sink = vec2(0.0);\n";
    ss << "#define gl_PointCoord gpu_PointCoord_sink\n";
  }

  const bool use_gl_frag_depth = info.depth_write_ != DepthWrite::UNCHANGED &&
                                 info.fragment_source_.find("gl_FragDepth") != std::string::npos;
  if (use_gl_frag_depth) {
    ss << "out float gl_FragDepth;\n";
  }

  for (const ShaderCreateInfo::FragOut &output : info.fragment_outputs_) {
    ss << "layout(location = " << output.index;
    switch (output.blend) {
      case DualBlend::SRC_0:
        ss << ", index = 0";
        break;
      case DualBlend::SRC_1:
        ss << ", index = 1";
        break;
      default:
        break;
    }
    ss << ") out " << to_string(output.type) << " " << output.name << ";\n";
  }

  /* Subpass inputs (input attachments). WebGPU core has no subpass / input-attachment
   * concept; the faithful translation reads the previous color attachment as a
   * regular texture, which requires splitting the render pass and rebinding the
   * attachment as a sampler (lane B's framebuffer / bind-group flow) — deferred.
   * Declare each subpass input as a zero-initialised module-scope global so shaders
   * that read one still COMPILE: without a declaration the reference is an undeclared
   * identifier → null shader → GPU_shader_bind SEGV, which in a shared-process run
   * crashes and poisons sibling tests. With this, framebuffer_subpass_input becomes an
   * honest pixel FAIL (the read yields 0, not the previous attachment) instead of a
   * crash. Same declare-to-compile pattern as gpu_ViewportIndex (M3.F6c) and
   * gl_PointSize; faithful subpass emulation is M3.F7-class deferred work. Mirrors the
   * STRUCTURE of vk_shader.cc:1040-1078 (the texelFetch-from-sampler else-path) minus
   * the attachment binding WebGPU cannot yet wire here. */
  for (const ShaderCreateInfo::SubpassIn &input : info.subpass_inputs_) {
    ss << to_string(input.type) << " " << input.name << " = " << to_string(input.type) << "(0);\n";
  }

  if (flag_is_set(info.builtins_, BuiltinBits::VIEWPORT_INDEX)) {
    /* Per-pass discard: keep only the primitives routed to THIS pass's (layer, viewport),
     * supplied by the backend in the _wgpu_mv UBO (resources_declare). The user main is
     * renamed so the wrapper runs the discard test before it (M3.F7). */
    ss << "void main_function_();\n";
    ss << "void main() {\n";
    ss << "  if (gpu_Layer != wgpu_mv_layer || gpu_ViewportIndex != wgpu_mv_viewport) {\n";
    ss << "    discard;\n";
    ss << "  }\n";
    ss << "  main_function_();\n";
    ss << "}\n";
    ss << "#define main main_function_\n";
  }

  ss << "\n";
  return ss.str();
}

std::string WGPUShader::geometry_interface_declare(const shader::ShaderCreateInfo & /*info*/) const
{
  /* WebGPU has no geometry stage; such shaders are skipped by the frontend. */
  return "";
}

std::string WGPUShader::geometry_layout_declare(const shader::ShaderCreateInfo & /*info*/) const
{
  return "";
}

std::string WGPUShader::compute_layout_declare(const shader::ShaderCreateInfo &info) const
{
  std::stringstream ss;
  ss << "layout(local_size_x = " << info.compute_layout_.local_size_x
     << ", local_size_y = " << info.compute_layout_.local_size_y
     << ", local_size_z = " << info.compute_layout_.local_size_z << ") in;\n\n";
  return ss.str();
}

/* Capture the assembled per-stage GLSL. The base compiler hands us sources whose
 * slot 0 (SOURCES_INDEX_VERSION) is a placeholder to be filled with the version
 * patch; the rest is defines + resources + interface + resolved user source. */
/* Build the stage GLSL patch (slot 0): `#version 450` + Vulkan-GLSL aliases +
 * the resolved `gpu_shader_compat_glsl.glsl` compat lib (which #defines the BSL
 * scalar/vector type aliases float4→vec4, etc.). Mirrors VKDevice::glsl_*_patch_get. */
static std::string glsl_patch(const char *stage_define)
{
  std::stringstream ss;
  ss << "#version 450\n";
  /* Vulkan GLSL spells these differently than desktop GL. */
  ss << "#define gl_VertexID gl_VertexIndex\n";
  ss << "#define gpu_InstanceIndex (gl_InstanceIndex)\n";
  /* WebGPU has no base-instance / gl_BaseInstanceARB; gl_InstanceIndex already
   * includes firstInstance, so gpu_BaseInstance is 0 and gl_InstanceID maps to
   * gl_InstanceIndex (widget/instanced shaders reference gl_InstanceID). */
  ss << "#define gpu_BaseInstance 0\n";
  ss << "#define gl_InstanceID gl_InstanceIndex\n";
  ss << stage_define;

  shader::GeneratedSourceList sources{
      shader::GeneratedSource{"gpu_shader_glsl_extension.glsl", {}, ss.str()}};
  Vector<StringRefNull> resolved = gpu_shader_dependency_get_resolved_source(
      "gpu_shader_compat_glsl.glsl", sources);
  std::string out;
  for (StringRefNull s : resolved) {
    out += std::string(s);
  }
  return out;
}

static std::string combine_with_patch(const std::string &patch, MutableSpan<StringRefNull> sources)
{
  std::string out = patch;
  for (int i = 1; i < sources.size(); i++) {
    out += std::string(sources[i]);
  }
  return out;
}

/* Run Blender's BSL preprocessor to lower create-info GLSL dialect (float4/float2,
 * template/SRT constructs, dead-code elimination) into shaderc-consumable GLSL —
 * exactly as the Vulkan backend does before shaderc (vk_shader_compiler.cc:194). */
std::string WGPUShader::preprocess(const std::string &combined) const
{
  if (skip_preprocessor) {
    return combined;
  }
  return Shader::run_preprocessor(combined, false);
}

/* Inline single-`return` helper functions that take a texel buffer (samplerBuffer /
 * isamplerBuffer / usamplerBuffer) by *function parameter*. WGSL forbids passing a
 * buffer/handle as a function argument, and the buffer-sampler emulation (is_buffer_sampler
 * / print_resource) turns the global texel buffer into a `readonly buffer`, so a
 * `get_customdata_*(int, const samplerBuffer)` call no longer type-checks against its
 * definition (glslang: "no matching overloaded function"). These helpers
 * (draw_curves_lib / draw_pointcloud_lib / eevee_attributes_pointcloud_lib — the MEDIUM
 * tail of notes/gpu-sampledbuffer-design.md) all have a single `return <expr>;` body, so
 * every call is inlined by substituting its arguments into that expression and the now
 * uncalled definitions are deleted. Buffer-typed parameters are substituted *bare* (the
 * call always passes the global resource identifier) so the resulting `texelFetch(global,
 * i)` is still recognised by rewrite_texel_buffers; other parameters are parenthesised.
 * Nested helpers (attr_load_* -> get_customdata_*) resolve across inlining passes. Runs
 * BEFORE rewrite_texel_buffers so the inlined texelFetch is then lowered to an indexed
 * storage load. A shader with no texel-buffer type token is left untouched (early out). */
static void inline_buffer_param_helpers(std::string &src)
{
  auto is_ident = [](char c) { return std::isalnum((unsigned char)c) || c == '_'; };
  static const char *kBufTypes[] = {"samplerBuffer", "isamplerBuffer", "usamplerBuffer"};

  bool any = false;
  for (const char *t : kBufTypes) {
    if (src.find(t) != std::string::npos) {
      any = true;
      break;
    }
  }
  if (!any) {
    return;
  }

  auto match_bracket = [&](size_t open, char oc, char cc) -> size_t {
    int d = 1;
    for (size_t q = open + 1; q < src.size(); ++q) {
      const char c = src[q];
      if (c == oc) {
        d++;
      }
      else if (c == cc) {
        if (--d == 0) {
          return q;
        }
      }
    }
    return std::string::npos;
  };
  auto has_buf_word = [&](const std::string &s) -> bool {
    for (const char *t : kBufTypes) {
      const std::string tok = t;
      size_t p = 0;
      while ((p = s.find(tok, p)) != std::string::npos) {
        const bool l = (p == 0) || !is_ident(s[p - 1]);
        const size_t e = p + tok.size();
        const bool r = (e >= s.size()) || !is_ident(s[e]);
        if (l && r) {
          return true;
        }
        p = e;
      }
    }
    return false;
  };
  auto split_top = [&](const std::string &s) -> std::vector<std::string> {
    std::vector<std::string> parts;
    std::string cur;
    int d = 0;
    for (const char c : s) {
      if (c == '(' || c == '[') {
        d++;
      }
      else if (c == ')' || c == ']') {
        d--;
      }
      if (c == ',' && d == 0) {
        parts.push_back(cur);
        cur.clear();
      }
      else {
        cur += c;
      }
    }
    parts.push_back(cur);
    return parts;
  };
  auto trim = [](const std::string &a) -> std::string {
    size_t s = 0, e = a.size();
    while (s < e && std::isspace((unsigned char)a[s])) {
      s++;
    }
    while (e > s && std::isspace((unsigned char)a[e - 1])) {
      e--;
    }
    return a.substr(s, e - s);
  };

  struct Helper {
    std::string ret_expr;
    std::vector<std::string> params;
    std::vector<bool> is_buf;
  };
  std::unordered_map<std::string, Helper> helpers;

  /* PASS 1: collect + delete definitions. */
  {
    std::string out;
    out.reserve(src.size());
    size_t i = 0;
    while (i < src.size()) {
      const size_t op = src.find('(', i);
      if (op == std::string::npos) {
        out.append(src, i, src.size() - i);
        break;
      }
      const size_t cp = match_bracket(op, '(', ')');
      if (cp == std::string::npos) {
        out.append(src, i, src.size() - i);
        break;
      }
      const std::string params_str = src.substr(op + 1, cp - op - 1);
      size_t after = cp + 1;
      while (after < src.size() && std::isspace((unsigned char)src[after])) {
        after++;
      }
      const bool is_def = has_buf_word(params_str) && after < src.size() && src[after] == '{';
      if (!is_def) {
        out.append(src, i, (op + 1) - i);
        i = op + 1;
        continue;
      }
      size_t ne = op;
      while (ne > 0 && std::isspace((unsigned char)src[ne - 1])) {
        ne--;
      }
      size_t ns = ne;
      while (ns > 0 && is_ident(src[ns - 1])) {
        ns--;
      }
      const std::string name = src.substr(ns, ne - ns);
      size_t rte = ns;
      while (rte > 0 && std::isspace((unsigned char)src[rte - 1])) {
        rte--;
      }
      size_t rts = rte;
      while (rts > 0 && is_ident(src[rts - 1])) {
        rts--;
      }
      const size_t bo = after;
      const size_t bc = match_bracket(bo, '{', '}');
      if (name.empty() || bc == std::string::npos) {
        out.append(src, i, (op + 1) - i);
        i = op + 1;
        continue;
      }
      const std::string body = src.substr(bo + 1, bc - bo - 1);
      const size_t rp = body.find("return");
      const size_t sc = body.rfind(';');
      if (rp == std::string::npos || sc == std::string::npos || sc <= rp + 6) {
        out.append(src, i, (op + 1) - i);
        i = op + 1;
        continue;
      }
      Helper h;
      h.ret_expr = body.substr(rp + 6, sc - (rp + 6));
      for (std::string &p : split_top(params_str)) {
        const bool buf = has_buf_word(p);
        size_t e = p.size();
        while (e > 0 && !is_ident(p[e - 1])) {
          e--;
        }
        size_t s = e;
        while (s > 0 && is_ident(p[s - 1])) {
          s--;
        }
        h.params.push_back(p.substr(s, e - s));
        h.is_buf.push_back(buf);
      }
      helpers[name] = h;
      out.append(src, i, rts - i);
      i = bc + 1;
    }
    src = std::move(out);
  }
  if (helpers.empty()) {
    return;
  }

  /* Inline calls, iterating so nested helper calls introduced by an outer inline resolve. */
  for (int pass = 0; pass < 8; ++pass) {
    bool changed = false;
    std::string out;
    out.reserve(src.size());
    size_t p = 0;
    while (p < src.size()) {
      size_t best = std::string::npos;
      std::string hit;
      size_t q = p;
      while (q < src.size()) {
        if (is_ident(src[q]) && (q == 0 || !is_ident(src[q - 1]))) {
          size_t e = q;
          while (e < src.size() && is_ident(src[e])) {
            e++;
          }
          const std::string id = src.substr(q, e - q);
          if (helpers.count(id)) {
            size_t r = e;
            while (r < src.size() && std::isspace((unsigned char)src[r])) {
              r++;
            }
            if (r < src.size() && src[r] == '(') {
              best = q;
              hit = id;
              break;
            }
          }
          q = e;
        }
        else {
          q++;
        }
      }
      if (best == std::string::npos) {
        out.append(src, p, src.size() - p);
        break;
      }
      size_t np = best + hit.size();
      while (np < src.size() && std::isspace((unsigned char)src[np])) {
        np++;
      }
      const size_t cp = match_bracket(np, '(', ')');
      if (cp == std::string::npos) {
        out.append(src, p, (best + hit.size()) - p);
        p = best + hit.size();
        continue;
      }
      const std::vector<std::string> args = split_top(src.substr(np + 1, cp - np - 1));
      const Helper &h = helpers[hit];
      if (args.size() != h.params.size()) {
        out.append(src, p, (cp + 1) - p);
        p = cp + 1;
        continue;
      }
      const std::string &expr = h.ret_expr;
      std::string se;
      se.reserve(expr.size());
      size_t z = 0;
      while (z < expr.size()) {
        if (is_ident(expr[z]) && (z == 0 || !is_ident(expr[z - 1]))) {
          size_t e = z;
          while (e < expr.size() && is_ident(expr[e])) {
            e++;
          }
          const std::string id = expr.substr(z, e - z);
          int idx = -1;
          for (size_t k = 0; k < h.params.size(); ++k) {
            if (h.params[k] == id) {
              idx = int(k);
              break;
            }
          }
          if (idx >= 0) {
            const std::string a = trim(args[idx]);
            if (h.is_buf[idx]) {
              se += a;
            }
            else {
              se += '(';
              se += a;
              se += ')';
            }
          }
          else {
            se += id;
          }
          z = e;
        }
        else {
          se += expr[z];
          z++;
        }
      }
      out.append(src, p, best - p);
      out += '(';
      out += se;
      out += ')';
      p = cp + 1;
      changed = true;
    }
    src = std::move(out);
    if (!changed) {
      break;
    }
  }
}

/* Rewrite `texelFetch(buf, i)` on an emulated texel buffer (is_buffer_sampler) into an
 * indexed storage-buffer load, matching the `readonly buffer` print_resource declared.
 * texelFetch on a buffer sampler takes exactly two args (sampler, int index) and yields
 * a gvec4; a regular 2/3-arg texelFetch on a 2D texture is untouched because its first
 * argument is not one of the create-info buffer-sampler names. Runs on the fully
 * preprocessed GLSL (after run_preprocessor lowers the BSL `sampler_get` / reference
 * variables to the global buffer name), so the first argument is always the bare
 * resource identifier. R32I/R32UI buffers are wrapped back into a gvec4 so the source's
 * `.r`/`.x` swizzles still resolve (RGBA32F is already a gvec4). */
static void rewrite_texel_buffers(std::string &src, const shader::ShaderCreateInfo &info)
{
  struct BufInfo {
    std::string name;
    ImageType type;
  };
  std::vector<BufInfo> bufs;
  auto collect = [&](const auto &list) {
    for (const ShaderCreateInfo::Resource &res : list) {
      if (is_buffer_sampler(res)) {
        bufs.push_back({std::string(res.sampler.name), res.sampler.type});
      }
    }
  };
  collect(info.pass_resources_);
  collect(info.batch_resources_);
  collect(info.geometry_resources_);
  if (bufs.empty()) {
    return;
  }

  auto is_ident = [](char c) { return std::isalnum((unsigned char)c) || c == '_'; };
  static const std::string kFn = "texelFetch";
  const size_t n = src.size();
  std::string out;
  out.reserve(n);
  size_t i = 0;
  while (i < n) {
    const size_t hit = src.find(kFn, i);
    if (hit == std::string::npos) {
      out.append(src, i, n - i);
      break;
    }
    /* Whole-word `texelFetch` immediately followed by `(` (skip texelFetchOffset etc.). */
    const bool word_ok = (hit == 0) || !is_ident(src[hit - 1]);
    size_t p = hit + kFn.size();
    while (p < n && std::isspace((unsigned char)src[p])) {
      p++;
    }
    if (!word_ok || p >= n || src[p] != '(') {
      out.append(src, i, (hit + kFn.size()) - i);
      i = hit + kFn.size();
      continue;
    }
    const size_t open = p;
    size_t a = open + 1;
    while (a < n && std::isspace((unsigned char)src[a])) {
      a++;
    }
    const size_t id_start = a;
    while (a < n && is_ident(src[a])) {
      a++;
    }
    const std::string first_arg = src.substr(id_start, a - id_start);
    while (a < n && std::isspace((unsigned char)src[a])) {
      a++;
    }
    const BufInfo *match = nullptr;
    if (a < n && src[a] == ',') {
      for (const BufInfo &b : bufs) {
        if (b.name == first_arg) {
          match = &b;
          break;
        }
      }
    }
    if (match == nullptr) {
      out.append(src, i, (open + 1) - i);
      i = open + 1;
      continue;
    }
    /* Capture the index expression: everything after the comma up to the paren that
     * matches `open` (buffer texelFetch has exactly one index argument). */
    const size_t idx_start = a + 1;
    int depth = 1;
    size_t q = open + 1;
    size_t close = std::string::npos;
    while (q < n) {
      const char c = src[q];
      if (c == '(') {
        depth++;
      }
      else if (c == ')') {
        if (--depth == 0) {
          close = q;
          break;
        }
      }
      q++;
    }
    if (close == std::string::npos) {
      out.append(src, i, (open + 1) - i);
      i = open + 1;
      continue;
    }
    const std::string idx = src.substr(idx_start, close - idx_start);
    out.append(src, i, hit - i);
    switch (match->type) {
      case ImageType::IntBuffer:
        out += "ivec4(" + match->name + "[" + idx + "], 0, 0, 0)";
        break;
      case ImageType::UintBuffer:
        out += "uvec4(" + match->name + "[" + idx + "], 0u, 0u, 0u)";
        break;
      default:
        out += match->name + "[" + idx + "]";
        break;
    }
    i = close + 1;
  }
  src = std::move(out);
}

/* WGSL forbids filtered sampling of an integer texture: `texture()`/`textureLod()` on a
 * usampler / isampler lowers to textureSample(Level) on a texture_2d<u32> / <i32>, which
 * Tint rejects ("no matching call to textureSample(...)"). GL forces integer textures to
 * nearest sampling regardless of the sampler state, so the faithful equivalent is a
 * texelFetch at the rounded texel: texture(s, uv) == texelFetch(s, ivecN(uv * size), 0).
 * This rewrites those calls on the fully-preprocessed GLSL (where struct-member accesses
 * like `srt.stencil_tx` and function-parameter samplers have both resolved to the bare
 * resource / parameter name, and a compute-stage texture() has already lowered to an
 * explicit-lod sample). Integer-sampler names + dimensionality are recovered from their
 * `[iu]sampler{1,2,3}D name` declarations in the same source. Semantics: identical to GL
 * (integer textures are nearest-fetched), modulo out-of-range wrap (texelFetch clamps to
 * 0) — a faithful degradation for the object-id / stencil / volume-flag lookups. */
static void rewrite_integer_sampler_sampling(std::string &src)
{
  auto is_ident = [](char c) { return std::isalnum((unsigned char)c) || c == '_'; };

  /* 1. name -> coordinate dimensionality, from the integer-sampler declarations. */
  std::unordered_map<std::string, int> int_samplers;
  {
    static const struct {
      const char *tok;
      int dim;
    } kinds[] = {
        {"usampler1D", 1}, {"isampler1D", 1}, {"usampler2D", 2},
        {"isampler2D", 2}, {"usampler3D", 3}, {"isampler3D", 3},
    };
    for (const auto &k : kinds) {
      const std::string tok = k.tok;
      size_t pos = 0;
      while ((pos = src.find(tok, pos)) != std::string::npos) {
        const size_t p = pos + tok.size();
        const bool left_ok = (pos == 0) || !is_ident(src[pos - 1]);
        /* Reject a longer type token (usampler2DArray / MS): the char after the type
         * must be a delimiter, not another identifier char. */
        if (left_ok && p < src.size() && !is_ident(src[p])) {
          size_t q = p;
          while (q < src.size() && std::isspace((unsigned char)src[q])) {
            q++;
          }
          const size_t id0 = q;
          while (q < src.size() && is_ident(src[q])) {
            q++;
          }
          if (q > id0) {
            int_samplers[src.substr(id0, q - id0)] = k.dim;
          }
        }
        pos = p;
      }
    }
  }
  if (int_samplers.empty()) {
    return;
  }

  /* 2. Rewrite texture(NAME, uv[, bias]) / textureLod(NAME, uv, lod) whose NAME is an
   *    integer sampler into texelFetch(NAME, ivecN(uv * size), lod). */
  auto rewrite_call = [&](const std::string &fn, bool has_lod) {
    const size_t n = src.size();
    std::string out;
    out.reserve(n);
    size_t i = 0;
    while (i < n) {
      const size_t hit = src.find(fn, i);
      if (hit == std::string::npos) {
        out.append(src, i, n - i);
        break;
      }
      const bool word_ok = (hit == 0) || !is_ident(src[hit - 1]);
      size_t p = hit + fn.size();
      while (p < n && std::isspace((unsigned char)src[p])) {
        p++;
      }
      if (!word_ok || p >= n || src[p] != '(') {
        out.append(src, i, (hit + fn.size()) - i);
        i = hit + fn.size();
        continue;
      }
      const size_t open = p;
      int depth = 1;
      size_t q = open + 1;
      size_t close = std::string::npos;
      std::vector<size_t> commas;
      while (q < n) {
        const char c = src[q];
        if (c == '(') {
          depth++;
        }
        else if (c == ')') {
          if (--depth == 0) {
            close = q;
            break;
          }
        }
        else if (c == ',' && depth == 1) {
          commas.push_back(q);
        }
        q++;
      }
      if (close == std::string::npos || commas.empty()) {
        out.append(src, i, (open + 1) - i);
        i = open + 1;
        continue;
      }
      size_t a0 = open + 1;
      while (a0 < commas[0] && std::isspace((unsigned char)src[a0])) {
        a0++;
      }
      size_t a1 = commas[0];
      while (a1 > a0 && std::isspace((unsigned char)src[a1 - 1])) {
        a1--;
      }
      const std::string first = src.substr(a0, a1 - a0);
      bool bare = !first.empty();
      for (const char c : first) {
        if (!is_ident(c)) {
          bare = false;
          break;
        }
      }
      const auto it = bare ? int_samplers.find(first) : int_samplers.end();
      if (it == int_samplers.end()) {
        out.append(src, i, (open + 1) - i);
        i = open + 1;
        continue;
      }
      const int dim = it->second;
      const size_t coord_end = (has_lod && commas.size() >= 2) ? commas[1] : close;
      const std::string coord = src.substr(commas[0] + 1, coord_end - (commas[0] + 1));
      std::string lod = "0";
      if (has_lod && commas.size() >= 2) {
        lod = "int(" + src.substr(commas[1] + 1, close - (commas[1] + 1)) + ")";
      }
      const std::string sz = "textureSize(" + first + ", " + lod + ")";
      std::string texel;
      if (dim == 1) {
        texel = "int((" + coord + ") * float(" + sz + "))";
      }
      else if (dim == 2) {
        texel = "ivec2((" + coord + ") * vec2(" + sz + "))";
      }
      else {
        texel = "ivec3((" + coord + ") * vec3(" + sz + "))";
      }
      out.append(src, i, hit - i);
      out += "texelFetch(" + first + ", " + texel + ", " + lod + ")";
      i = close + 1;
    }
    src = std::move(out);
  };
  rewrite_call("textureLod", true);
  rewrite_call("texture", false);
}

/* WGSL has no 1D-array sampled texture, so Tint's SPIR-V reader degrades a Dim=1D /
 * Arrayed image to texture_1d, dropping the array; textureSize/textureDimensions then
 * returns a scalar u32 while the shader used the 2-component result → "textureDimensions:
 * call result type 'vec2<u32>' does not match builtin return type 'u32'" (the UDIM
 * imageTileData lookup in workbench, and the color-ramp valtorgb). A 1D-array is exactly
 * a 2D texture whose height IS the layer count (identical texelFetch / textureSize
 * signatures — both take ivec2), so emulate it as sampler2D: (1) rewrite the type token
 * everywhere it is declared (resource decls + function params); (2) texelFetch / texture
 * on integer coords is already identical, so nothing else is needed for the UDIM path;
 * (3) filtered texture(NAME, vec2(u, layer)) samples ARRAY layer `layer` (never filtered
 * across layers in GL) at position u — remap the layer to its row centre
 * (layer+0.5)/height so bilinear filtering returns that row exactly (no cross-layer
 * blend) while u keeps its intended linear filtering. The interface map's
 * infer_view_dimension(e1DArray) is set to the matching WGSL e2D. */
static void rewrite_1d_array_samplers(std::string &src)
{
  auto is_ident = [](char c) { return std::isalnum((unsigned char)c) || c == '_'; };
  static const std::string kTok = "sampler1DArray";

  /* Names of 1D-array samplers (any of sampler/isampler/usampler1DArray): the name
   * follows the shared "sampler1DArray" suffix regardless of the i/u prefix. */
  std::unordered_map<std::string, bool> names; /* set of names */
  {
    size_t pos = 0;
    while ((pos = src.find(kTok, pos)) != std::string::npos) {
      const size_t p = pos + kTok.size();
      if (p < src.size() && !is_ident(src[p])) {
        size_t q = p;
        while (q < src.size() && std::isspace((unsigned char)src[q])) {
          q++;
        }
        const size_t id0 = q;
        while (q < src.size() && is_ident(src[q])) {
          q++;
        }
        if (q > id0) {
          names.emplace(src.substr(id0, q - id0), true);
        }
      }
      pos = p;
    }
  }
  if (names.empty()) {
    return;
  }

  /* Remap the layer coordinate of any filtered texture(NAME, coord) on a 1D-array
   * sampler (done BEFORE the type-token swap so textureSize still refers to the sampler
   * by name; the sampler is still declared 1D-array here but 2D later — the layer count
   * lands in the .y component either way). */
  {
    const std::string fn = "texture";
    const size_t n = src.size();
    std::string out;
    out.reserve(n);
    size_t i = 0;
    while (i < n) {
      const size_t hit = src.find(fn, i);
      if (hit == std::string::npos) {
        out.append(src, i, n - i);
        break;
      }
      const bool word_ok = (hit == 0) || !is_ident(src[hit - 1]);
      size_t p = hit + fn.size();
      while (p < n && std::isspace((unsigned char)src[p])) {
        p++;
      }
      if (!word_ok || p >= n || src[p] != '(') {
        out.append(src, i, (hit + fn.size()) - i);
        i = hit + fn.size();
        continue;
      }
      const size_t open = p;
      int depth = 1;
      size_t q = open + 1;
      size_t close = std::string::npos;
      std::vector<size_t> commas;
      while (q < n) {
        const char c = src[q];
        if (c == '(') {
          depth++;
        }
        else if (c == ')') {
          if (--depth == 0) {
            close = q;
            break;
          }
        }
        else if (c == ',' && depth == 1) {
          commas.push_back(q);
        }
        q++;
      }
      if (close == std::string::npos || commas.empty()) {
        out.append(src, i, (open + 1) - i);
        i = open + 1;
        continue;
      }
      size_t a0 = open + 1;
      while (a0 < commas[0] && std::isspace((unsigned char)src[a0])) {
        a0++;
      }
      size_t a1 = commas[0];
      while (a1 > a0 && std::isspace((unsigned char)src[a1 - 1])) {
        a1--;
      }
      const std::string first = src.substr(a0, a1 - a0);
      bool bare = !first.empty();
      for (const char c : first) {
        if (!is_ident(c)) {
          bare = false;
          break;
        }
      }
      if (!bare || names.find(first) == names.end()) {
        out.append(src, i, (open + 1) - i);
        i = open + 1;
        continue;
      }
      const size_t coord_end = commas.size() >= 2 ? commas[1] : close;
      const std::string coord = src.substr(commas[0] + 1, coord_end - (commas[0] + 1));
      out.append(src, i, hit - i);
      out += "texture(" + first + ", vec2((" + coord + ").x, ((" + coord +
             ").y + 0.5) / float(textureSize(" + first + ", 0).y)))";
      i = close + 1;
    }
    src = std::move(out);
  }

  /* Swap every 1D-array type token for its 2D equivalent (one suffix replace covers the
   * plain / i / u prefixes: isampler1DArray -> isampler2D, etc.). */
  for (size_t pos = 0; (pos = src.find(kTok, pos)) != std::string::npos;) {
    src.replace(pos, kTok.size(), "sampler2D");
    pos += std::string("sampler2D").size();
  }
}

/* Tint's SPIR-V reader rejects OpIsNan / OpIsInf ("NaNs/Infinities cannot be represented
 * in WGSL"), so glslang's isnan()/isinf() builtins (EEVEE film / DoF / motion-blur /
 * volume, launch tier) break. Replace them with arithmetic equivalents that compile to
 * ordinary comparisons (no OpIsNan/OpIsInf) and survive to WGSL: isnan(x) == (x != x)
 * (a NaN is the only value unequal to itself — the operand is a runtime value so glslang
 * cannot fold it), isinf(x) == (abs(x) > FLT_MAX). Injected as type-overloaded helpers so
 * the scalar and vector (bvecN via notEqual/greaterThan) forms both resolve; only shaders
 * that reference isnan/isinf get them. Same non-foldable spirit as the NAN_FLT guard
 * (patch 0054). */
static void rewrite_isnan_isinf(std::string &src)
{
  if (src.find("isnan(") == std::string::npos && src.find("isinf(") == std::string::npos) {
    return;
  }
  static const char *kHelpers =
      "\nbool wgpu_isnan(float x) { return x != x; }\n"
      "bvec2 wgpu_isnan(vec2 v) { return notEqual(v, v); }\n"
      "bvec3 wgpu_isnan(vec3 v) { return notEqual(v, v); }\n"
      "bvec4 wgpu_isnan(vec4 v) { return notEqual(v, v); }\n"
      "bool wgpu_isinf(float x) { return abs(x) > 3.402823466e38; }\n"
      "bvec2 wgpu_isinf(vec2 v) { return greaterThan(abs(v), vec2(3.402823466e38)); }\n"
      "bvec3 wgpu_isinf(vec3 v) { return greaterThan(abs(v), vec3(3.402823466e38)); }\n"
      "bvec4 wgpu_isinf(vec4 v) { return greaterThan(abs(v), vec4(3.402823466e38)); }\n";

  /* Insert the helpers just after the `#version` line (must precede first use, and
   * `#version` must stay the very first token). */
  size_t ins = src.find("#version");
  if (ins != std::string::npos) {
    const size_t nl = src.find('\n', ins);
    ins = (nl == std::string::npos) ? src.size() : nl + 1;
  }
  else {
    ins = 0;
  }
  src.insert(ins, kHelpers);

  auto is_ident = [](char c) { return std::isalnum((unsigned char)c) || c == '_'; };
  for (const char *fn : {"isnan(", "isinf("}) {
    const std::string needle = fn;
    const std::string repl = std::string("wgpu_") + fn;
    size_t pos = ins + std::strlen(kHelpers); /* skip the helper block we just inserted */
    while ((pos = src.find(needle, pos)) != std::string::npos) {
      if (pos > 0 && is_ident(src[pos - 1])) {
        pos += needle.size(); /* part of a longer identifier (e.g. wgpu_isnan) */
        continue;
      }
      src.replace(pos, needle.size(), repl);
      pos += repl.size();
    }
  }
}

void WGPUShader::vertex_shader_from_glsl(const shader::ShaderCreateInfo &info,
                                         MutableSpan<StringRefNull> sources)
{
  vertex_glsl_ = preprocess(combine_with_patch(glsl_patch("#define GPU_VERTEX_SHADER\n"), sources));
  inline_buffer_param_helpers(vertex_glsl_);
  rewrite_texel_buffers(vertex_glsl_, info);
  rewrite_integer_sampler_sampling(vertex_glsl_);
  rewrite_1d_array_samplers(vertex_glsl_);
  rewrite_isnan_isinf(vertex_glsl_);
}
void WGPUShader::geometry_shader_from_glsl(const shader::ShaderCreateInfo & /*info*/,
                                           MutableSpan<StringRefNull> /*sources*/)
{
}
void WGPUShader::fragment_shader_from_glsl(const shader::ShaderCreateInfo &info,
                                           MutableSpan<StringRefNull> sources)
{
  fragment_glsl_ = preprocess(
      combine_with_patch(glsl_patch("#define GPU_FRAGMENT_SHADER\n"), sources));
  inline_buffer_param_helpers(fragment_glsl_);
  rewrite_texel_buffers(fragment_glsl_, info);
  rewrite_integer_sampler_sampling(fragment_glsl_);
  rewrite_1d_array_samplers(fragment_glsl_);
  rewrite_isnan_isinf(fragment_glsl_);
}
void WGPUShader::compute_shader_from_glsl(const shader::ShaderCreateInfo &info,
                                          MutableSpan<StringRefNull> sources)
{
  compute_glsl_ = preprocess(
      combine_with_patch(glsl_patch("#define GPU_COMPUTE_SHADER\n"), sources));
  inline_buffer_param_helpers(compute_glsl_);
  rewrite_texel_buffers(compute_glsl_, info);
  rewrite_integer_sampler_sampling(compute_glsl_);
  rewrite_1d_array_samplers(compute_glsl_);
  rewrite_isnan_isinf(compute_glsl_);
}

/* Map a create-info sampler/image ImageType to the interface-map texel + dim. */
static void map_image_type(ImageType t, wgi::TexelClass &texel, wgi::TexDim &dim)
{
  switch (t) {
    case ImageType::Int1D:
    case ImageType::Int1DArray:
    case ImageType::Int2D:
    case ImageType::Int2DArray:
    case ImageType::Int3D:
    case ImageType::IntCube:
    case ImageType::IntCubeArray:
    case ImageType::IntBuffer:
    case ImageType::AtomicInt2D:
    case ImageType::AtomicInt2DArray:
    case ImageType::AtomicInt3D:
      texel = wgi::TexelClass::Int;
      break;
    case ImageType::Uint1D:
    case ImageType::Uint1DArray:
    case ImageType::Uint2D:
    case ImageType::Uint2DArray:
    case ImageType::Uint3D:
    case ImageType::UintCube:
    case ImageType::UintCubeArray:
    case ImageType::UintBuffer:
    case ImageType::AtomicUint2D:
    case ImageType::AtomicUint2DArray:
    case ImageType::AtomicUint3D:
      texel = wgi::TexelClass::Uint;
      break;
    case ImageType::Shadow2D:
    case ImageType::Shadow2DArray:
    case ImageType::ShadowCube:
    case ImageType::ShadowCubeArray:
      texel = wgi::TexelClass::Shadow;
      break;
    case ImageType::Depth2D:
    case ImageType::Depth2DArray:
    case ImageType::DepthCube:
    case ImageType::DepthCubeArray:
      texel = wgi::TexelClass::Depth;
      break;
    default:
      texel = wgi::TexelClass::Float;
      break;
  }
  switch (t) {
    case ImageType::Float1D:
    case ImageType::Int1D:
    case ImageType::Uint1D:
      dim = wgi::TexDim::e1D;
      break;
    case ImageType::Float1DArray:
    case ImageType::Int1DArray:
    case ImageType::Uint1DArray:
      dim = wgi::TexDim::e1DArray;
      break;
    case ImageType::Float3D:
    case ImageType::Int3D:
    case ImageType::Uint3D:
    case ImageType::AtomicInt3D:
    case ImageType::AtomicUint3D:
      dim = wgi::TexDim::e3D;
      break;
    case ImageType::FloatCube:
    case ImageType::IntCube:
    case ImageType::UintCube:
    case ImageType::ShadowCube:
    case ImageType::DepthCube:
      dim = wgi::TexDim::Cube;
      break;
    case ImageType::FloatCubeArray:
    case ImageType::IntCubeArray:
    case ImageType::UintCubeArray:
    case ImageType::ShadowCubeArray:
    case ImageType::DepthCubeArray:
      dim = wgi::TexDim::CubeArray;
      break;
    case ImageType::Float2DArray:
    case ImageType::Int2DArray:
    case ImageType::Uint2DArray:
    case ImageType::Shadow2DArray:
    case ImageType::Depth2DArray:
    case ImageType::AtomicInt2DArray:
    case ImageType::AtomicUint2DArray:
      dim = wgi::TexDim::e2DArray;
      break;
    case ImageType::FloatBuffer:
    case ImageType::IntBuffer:
    case ImageType::UintBuffer:
      dim = wgi::TexDim::Buffer;
      break;
    default:
      dim = wgi::TexDim::e2D;
      break;
  }
}

static wgi::ResourceDesc resource_to_desc(const ShaderCreateInfo::Resource &res,
                                          uint32_t stages,
                                          uint32_t binding)
{
  wgi::ResourceDesc d;
  d.binding = binding;
  d.stages = stages;
  switch (res.bind_type) {
    case ShaderCreateInfo::Resource::BindType::UNIFORM_BUFFER:
      d.kind = wgi::ResourceKind::UniformBuffer;
      break;
    case ShaderCreateInfo::Resource::BindType::STORAGE_BUFFER:
      d.kind = wgi::ResourceKind::StorageBuffer;
      d.storage_readonly = (bool(res.storagebuf.qualifiers & Qualifier::write) == false);
      break;
    case ShaderCreateInfo::Resource::BindType::SAMPLER:
      if (is_buffer_sampler(res)) {
        /* Texel buffer emulated as a read-only storage buffer (option (a)): the
         * interface map emits a single ReadOnlyStorage bind-group entry at binding N
         * (no combined-sampler split, no sampler_mappings), matching the `readonly
         * buffer` the codegen declared. */
        d.kind = wgi::ResourceKind::StorageBuffer;
        d.storage_readonly = true;
      }
      else {
        d.kind = wgi::ResourceKind::Sampler;
        map_image_type(res.sampler.type, d.texel, d.dim);
        d.filtering = true;
      }
      break;
    case ShaderCreateInfo::Resource::BindType::IMAGE:
      d.kind = wgi::ResourceKind::StorageImage;
      map_image_type(res.image.type, d.texel, d.dim);
      d.image_format = wgi::to_wgpu_format(res.image.format);
      {
        const bool r = bool(res.image.qualifiers & Qualifier::read);
        const bool w = bool(res.image.qualifiers & Qualifier::write);
        d.image_access = (r && w) ? wgpu::StorageTextureAccess::ReadWrite :
                         (r)       ? wgpu::StorageTextureAccess::ReadOnly :
                                     wgpu::StorageTextureAccess::WriteOnly;
      }
      break;
  }
  return d;
}

static wgpu::ShaderModule make_module(const wgpu::Device &device, const std::string &wgsl)
{
  wgpu::ShaderSourceWGSL src;
  src.code = wgsl.c_str();
  wgpu::ShaderModuleDescriptor desc;
  desc.nextInChain = &src;
  return device.CreateShaderModule(&desc);
}

bool WGPUShader::finalize(const shader::ShaderCreateInfo *info)
{
  if (info == nullptr) {
    return false;
  }
  /* Shaders compile on the async worker thread, which has no thread-local active
   * GPU context — reach the device backend-side (one Dawn device). */
  wgpu::Device device = WGPUContext::backend_device();
  if (device == nullptr) {
    return false;
  }

  const bool is_compute = !compute_glsl_.empty();
  const uint32_t stages = is_compute ?
                              uint32_t(wgi::STAGE_COMPUTE) :
                              uint32_t(wgi::STAGE_VERTEX) | uint32_t(wgi::STAGE_FRAGMENT);

  blender::Map<uint32_t, uint32_t> bindings;
  const uint32_t resource_count = build_dense_bindings(*info, bindings);
  std::vector<wgi::ResourceDesc> resources;
  auto add = [&](const auto &list) {
    for (const ShaderCreateInfo::Resource &res : list) {
      resources.push_back(resource_to_desc(res, stages, dense_binding_of(bindings, res)));
    }
  };
  add(info->pass_resources_);
  add(info->batch_resources_);
  add(info->geometry_resources_);
  /* Push-constant UBO at the dense binding after the last resource (matches
   * resources_declare). */
  if (!info->push_constants_.is_empty()) {
    wgi::ResourceDesc pc;
    pc.kind = wgi::ResourceKind::UniformBuffer;
    pc.binding = resource_count;
    pc.stages = stages;
    resources.push_back(pc);
  }

  wgi::ShaderStageSources src;
  src.vertex = vertex_glsl_;
  src.fragment = fragment_glsl_;
  src.compute = compute_glsl_;
  src.name = std::string(name_get());

  wgi::CompileResult result = wgi::compile_shader(src, resources);
  if (!result.ok) {
    CLOG_WARN(&LOG, "WGPUShader '%s' compile failed: %s", src.name.c_str(), result.error.c_str());
    return false;
  }
  interface_map_ = result.interface;

  if (!result.vertex_wgsl.empty()) {
    vertex_module_ = make_module(device, result.vertex_wgsl);
    if (vertex_module_ == nullptr) {
      return false;
    }
  }
  if (!result.fragment_wgsl.empty()) {
    fragment_module_ = make_module(device, result.fragment_wgsl);
    if (fragment_module_ == nullptr) {
      return false;
    }
  }
  if (!result.compute_wgsl.empty()) {
    compute_module_ = make_module(device, result.compute_wgsl);
    if (compute_module_ == nullptr) {
      return false;
    }
  }

  /* Build the name→location interface + push-constant std140 layout (needed for
   * uniform_* and for lane B's bind-group assembly). */
  build_interface(*info);

  /* Build the explicit group-0 layout from the interface map, pruned to the WGSL's
   * surviving bindings (needs has_multi_viewport_ / multi_viewport_binding_ from
   * build_interface). Failure here just leaves has_explicit_layout() false -> the
   * draw/compute paths keep Dawn's auto layout. */
  build_explicit_layout(device, result.vertex_wgsl, result.fragment_wgsl, result.compute_wgsl);
  return true;
}

void WGPUShader::warm_cache(int /*limit*/) {}

/* Draw-time pipeline binding runs through lane B's pipeline assembly. Capture the
 * specialization constants so compute_pipeline() can build the matching variant
 * (WebGPU applies overrides at pipeline creation). */
void WGPUShader::bind(const shader::SpecializationConstants *constants_state)
{
  bound_constants_ = constants_state;
}
void WGPUShader::unbind() {}

wgpu::ComputePipeline WGPUShader::compute_pipeline(const wgpu::Device &device)
{
  if (compute_module_ == nullptr) {
    return nullptr;
  }
  /* Specialization key = the raw override bit patterns of the currently-bound
   * constants (empty when the shader declares none). WebGPU applies `override`
   * constants per pipeline, so each distinct value set needs its own variant. */
  std::vector<uint32_t> key;
  if (bound_constants_ != nullptr) {
    for (const SpecializationConstant::Value &v : bound_constants_->values) {
      key.push_back(v.u);
    }
  }
  for (const ComputePipelineVariant &variant : compute_pipelines_) {
    if (variant.key == key) {
      return variant.pipeline;
    }
  }

  /* Miss: build the variant. Each create-info specialization constant became a WGSL
   * `override` whose id is its constant_id (Tint's SPIR-V reader sets it from the
   * SpecId), so the ConstantEntry key is that id as a decimal string — Dawn matches
   * @id-specified overrides by std::to_string(id) (ShaderModule.cpp:816). The value
   * is a double; for a float spec constant the override is the uint bit pattern (see
   * resources_declare), which is exactly Value::u, so only int_t reads the signed
   * field. */
  std::vector<wgpu::ConstantEntry> constants;
  std::vector<std::string> key_strings;
  if (bound_constants_ != nullptr) {
    const int count = int(bound_constants_->values.size());
    key_strings.reserve(count);
    constants.reserve(count);
    for (int i = 0; i < count; i++) {
      key_strings.push_back(std::to_string(i));
      const SpecializationConstant::Value &v = bound_constants_->values[i];
      const bool is_int = (i < int(bound_constants_->types.size())) &&
                          (bound_constants_->types[i] == Type::int_t);
      wgpu::ConstantEntry entry = {};
      entry.key = key_strings.back().c_str();
      entry.value = is_int ? double(v.i) : double(v.u);
      constants.push_back(entry);
    }
  }

  wgpu::ComputePipelineDescriptor desc = {};
  /* Explicit group-0 layout (interface-map-derived, correct resource types) when the
   * shader has full coverage; else Dawn's auto layout inferred from the compute WGSL. */
  desc.layout = has_explicit_layout() ? explicit_pipeline_layout() : nullptr;
  desc.compute.module = compute_module_;
  /* Tint names the compute entry point "main" (from the GLSL main); the standalone
   * T7.pre proof created its compute pipeline with the same explicit entry point. */
  desc.compute.entryPoint = "main";
  desc.compute.constantCount = constants.size();
  desc.compute.constants = constants.empty() ? nullptr : constants.data();
  wgpu::ComputePipeline pipeline = device.CreateComputePipeline(&desc);
  compute_pipelines_.push_back({key, pipeline});
  return pipeline;
}

/* -------------------------------------------------------------------------- */
/** \name Explicit pipeline layout
 * \{ */

/* Scan an emitted WGSL stage for its surviving `@binding(N)` (group 0 by the backend's
 * single-set design), OR-ing `stage_bit` into r_survivors[N]. Tint prunes unused
 * module-scope resources, so the union across the present stages is exactly the binding
 * set Dawn's auto layout would expose — reused here as the explicit layout's binding set
 * AND its per-binding visibility, so the explicit layout is binding-/visibility-identical
 * to the auto layout and differs only in the resource TYPE fields (which is the point). */
static void scan_wgsl_bindings(const std::string &wgsl,
                               uint32_t stage_bit,
                               blender::Map<uint32_t, uint32_t> &r_survivors)
{
  static const char kTok[] = "@binding(";
  const size_t kLen = sizeof(kTok) - 1;
  size_t pos = 0;
  while ((pos = wgsl.find(kTok, pos)) != std::string::npos) {
    size_t i = pos + kLen;
    uint32_t value = 0;
    bool any = false;
    while (i < wgsl.size() && wgsl[i] >= '0' && wgsl[i] <= '9') {
      value = value * 10u + uint32_t(wgsl[i] - '0');
      any = true;
      i++;
    }
    if (any) {
      r_survivors.add_overwrite(value, r_survivors.lookup_default(value, 0u) | stage_bit);
    }
    pos = i;
  }
}

void WGPUShader::build_explicit_layout(const wgpu::Device &device,
                                       const std::string &vertex_wgsl,
                                       const std::string &fragment_wgsl,
                                       const std::string &compute_wgsl)
{
  explicit_layout_ok_ = false;
  explicit_entries_.clear();
  if (device == nullptr) {
    return;
  }

  blender::Map<uint32_t, uint32_t> survivors;
  scan_wgsl_bindings(vertex_wgsl, uint32_t(wgi::STAGE_VERTEX), survivors);
  scan_wgsl_bindings(fragment_wgsl, uint32_t(wgi::STAGE_FRAGMENT), survivors);
  scan_wgsl_bindings(compute_wgsl, uint32_t(wgi::STAGE_COMPUTE), survivors);

  auto to_visibility = [](uint32_t mask) {
    wgpu::ShaderStage v = wgpu::ShaderStage::None;
    if (mask & uint32_t(wgi::STAGE_VERTEX)) {
      v |= wgpu::ShaderStage::Vertex;
    }
    if (mask & uint32_t(wgi::STAGE_FRAGMENT)) {
      v |= wgpu::ShaderStage::Fragment;
    }
    if (mask & uint32_t(wgi::STAGE_COMPUTE)) {
      v |= wgpu::ShaderStage::Compute;
    }
    return v;
  };

  std::vector<wgpu::BindGroupLayoutEntry> entries;
  entries.reserve(survivors.size());
  for (auto item : survivors.items()) {
    const uint32_t binding = item.key;
    const wgpu::ShaderStage vis = to_visibility(item.value);

    /* Prefer the interface-map entry (correct sampleType / sampler.type / view dim /
     * buffer.type); override visibility with the WGSL-measured stage set. */
    const wgpu::BindGroupLayoutEntry *src = nullptr;
    for (const wgpu::BindGroupLayoutEntry &e : interface_map_.entries) {
      if (e.binding == binding) {
        src = &e;
        break;
      }
    }
    if (src != nullptr) {
      wgpu::BindGroupLayoutEntry e = *src;
      e.visibility = vis;
      /* Re-apply the interface map's RW-storage rule AFTER the WGSL-visibility
       * override: Tint can retain a read-write SSBO's module-scope declaration in
       * the vertex WGSL even when no vertex code touches it, so the scanned stage
       * set carries Vertex — and WebGPU rejects any RW-storage entry visible to
       * Vertex, collapsing the whole layout (the workbench-prepass killer). Same
       * rationale as the strip in wgpu_shader_interface_map.cc. */
      if (e.buffer.type == wgpu::BufferBindingType::Storage) {
        e.visibility = e.visibility & (wgpu::ShaderStage::Fragment | wgpu::ShaderStage::Compute);
      }
      entries.push_back(e);
      continue;
    }
    /* The one codegen-injected binding not in the interface map: the multi-viewport
     * pass-state UBO (patch 0083), a plain uniform buffer. */
    if (has_multi_viewport_ && binding == multi_viewport_binding_) {
      wgpu::BindGroupLayoutEntry e = {};
      e.binding = binding;
      e.visibility = vis;
      e.buffer.type = wgpu::BufferBindingType::Uniform;
      entries.push_back(e);
      continue;
    }
    /* Any other uncovered binding means the interface map does not describe this
     * shader's real WGSL. Do NOT guess — fall back to Dawn's auto layout for the whole
     * shader (loud, so an unexpected codegen-injected resource is caught, not masked). */
    CLOG_WARN(&LOG,
              "WGPUShader '%s': WGSL @binding(%u) not covered by interface map; auto layout",
              name_get().c_str(),
              binding);
    return;
  }

  wgpu::BindGroupLayoutDescriptor bgld = {};
  bgld.entryCount = entries.size();
  bgld.entries = entries.empty() ? nullptr : entries.data();
  wgpu::BindGroupLayout bgl = device.CreateBindGroupLayout(&bgld);
  if (bgl == nullptr) {
    return;
  }
  wgpu::PipelineLayoutDescriptor pld = {};
  pld.bindGroupLayoutCount = 1;
  pld.bindGroupLayouts = &bgl;
  wgpu::PipelineLayout pl = device.CreatePipelineLayout(&pld);
  if (pl == nullptr) {
    return;
  }

  explicit_entries_ = std::move(entries);
  explicit_bgl_ = bgl;
  explicit_pipeline_layout_ = pl;
  explicit_layout_ok_ = true;
}

/** \} */

/* -------------------------------------------------------------------------- */
/** \name Push-constant UBO plumbing
 * \{ */

void WGPUShader::build_interface(const shader::ShaderCreateInfo &info)
{
  WGPUShaderInterface *iface = new WGPUShaderInterface();
  iface->init(info);
  this->interface = iface;

  /* std140 layout of the push-constant block (offset per push-constant, keyed by
   * the interface location 1024 + i). */
  push_constants_.clear();
  uint32_t offset = 0;
  int32_t location = PUSH_CONSTANT_LOCATION_BASE;
  for (const ShaderCreateInfo::PushConst &pc : info.push_constants_) {
    uint32_t align, size;
    std140_align_size(pc.type, pc.array_size, align, size);
    offset = (offset + (align - 1)) & ~(align - 1);
    push_constants_.push_back({location++, offset, size});
    offset += size;
  }
  push_constants_size_ = (offset + 15u) & ~15u;
  push_constants_data_.assign(push_constants_size_, 0);

  /* UBO binding = the dense binding after the last resource (matches
   * resources_declare / the ResourceDesc list). Keep the full (bind_type,slot)->dense
   * map for remap_*_binding (frontend slot -> dense group-0 binding). */
  dense_bindings_.clear();
  push_constants_binding_ = build_dense_bindings(info, dense_bindings_);

  /* Multi-viewport emulation pass-state UBO (M3.F7): binding just after the push-constant
   * fallback, matching the resources_declare formula. */
  has_multi_viewport_ = flag_is_set(info.builtins_, BuiltinBits::VIEWPORT_INDEX);
  multi_viewport_binding_ = push_constants_binding_ +
                            (info.push_constants_.is_empty() ? 0u : 1u);
}

/* Frontend slot -> this shader's dense group-0 binding. Two frontend bind
 * flavors reach these: (a) fixed create-info slots (DRW-style) that need the
 * dense_bindings_ translation, and (b) name-resolved binds where the frontend
 * already queried the interface and passes the DENSE binding itself — those
 * miss the map and take the identity fallback. Identity alone let STALE
 * context-wide binds collide with mapped resources on one @binding (the
 * r18-r26 silent blank-viewport root cause), so the bind-group builder now
 * assembles MAPPED slots first and identity-fallback slots only into bindings
 * nothing mapped has claimed (slot_is_mapped_* below + the two-pass loops in
 * append_resource_bind_entries). */
int WGPUShader::remap_ssbo_binding(int slot) const
{
  const uint32_t key = (uint32_t(shader::ShaderCreateInfo::Resource::BindType::STORAGE_BUFFER)
                        << 24) |
                       uint32_t(slot);
  return int(dense_bindings_.lookup_default(key, uint32_t(slot)));
}
int WGPUShader::remap_ubo_binding(int slot) const
{
  const uint32_t key = (uint32_t(shader::ShaderCreateInfo::Resource::BindType::UNIFORM_BUFFER)
                        << 24) |
                       uint32_t(slot);
  return int(dense_bindings_.lookup_default(key, uint32_t(slot)));
}
int WGPUShader::remap_sampler_binding(int slot) const
{
  const uint32_t key = (uint32_t(shader::ShaderCreateInfo::Resource::BindType::SAMPLER) << 24) |
                       uint32_t(slot);
  return int(dense_bindings_.lookup_default(key, uint32_t(slot)));
}
int WGPUShader::remap_image_binding(int slot) const
{
  const uint32_t key = (uint32_t(shader::ShaderCreateInfo::Resource::BindType::IMAGE) << 24) |
                       uint32_t(slot);
  return int(dense_bindings_.lookup_default(key, uint32_t(slot)));
}

bool WGPUShader::slot_is_mapped(shader::ShaderCreateInfo::Resource::BindType type,
                                int slot) const
{
  const uint32_t key = (uint32_t(type) << 24) | uint32_t(slot);
  return dense_bindings_.contains(key);
}

void WGPUShader::push_constant_set(int location, int comp_len, int array_size, const void *data)
{
  for (const PushConstantSlot &slot : push_constants_) {
    if (slot.location != location) {
      continue;
    }
    const uint32_t n = uint32_t(comp_len) * uint32_t(array_size) * 4u;
    const uint32_t copy = std::min(n, slot.size);
    if (slot.offset + copy <= push_constants_data_.size()) {
      std::memcpy(push_constants_data_.data() + slot.offset, data, copy);
      push_constants_dirty_ = true;
    }
    return;
  }
}

void WGPUShader::uniform_float(int location, int comp_len, int array_size, const float *data)
{
  push_constant_set(location, comp_len, array_size, data);
}
void WGPUShader::uniform_int(int location, int comp_len, int array_size, const int *data)
{
  push_constant_set(location, comp_len, array_size, data);
}

void WGPUShader::push_constants_flush()
{
  if (push_constants_size_ == 0) {
    return;
  }
  wgpu::Device device = WGPUContext::backend_device();
  wgpu::Queue queue = WGPUContext::backend_queue();
  if (device == nullptr) {
    return;
  }
  if (!push_constants_buffer_.valid()) {
    if (!push_constants_buffer_.create(device,
                                       webgpu::BufferKind::Uniform,
                                       webgpu::UsageType::Dynamic,
                                       push_constants_size_,
                                       nullptr,
                                       false))
    {
      return;
    }
    push_constants_dirty_ = true;
  }
  if (push_constants_dirty_) {
    push_constants_buffer_.update_sub(
        device, queue, 0, push_constants_data_.data(), push_constants_size_);
    push_constants_dirty_ = false;
  }
}

/** \} */

/** \} */

}  // namespace blender::gpu
