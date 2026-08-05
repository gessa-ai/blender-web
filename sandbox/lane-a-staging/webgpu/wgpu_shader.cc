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
#include <cstring>
#include <sstream>

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

/* Dense set-0 binding (the combined-sampler split + reserved sampler range are
 * applied later by the interface map / Tint, not in the GLSL). */
static void print_resource(std::ostream &os,
                           uint32_t binding,
                           const ShaderCreateInfo::Resource &res,
                           const ShaderCreateInfo &info)
{
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
  ss << "\n";

  /* Retarget depth from -1..1 (GL convention the GLSL is written in) to 0..1
   * (WebGPU/Vulkan clip space). The user main() is renamed via #define. */
  ss << "void main_function_();\n";
  ss << "void main() {\n";
  ss << "  main_function_();\n";
  ss << "  gl_Position.z = (gl_Position.z + gl_Position.w) * 0.5;\n";
  ss << "}\n";
  ss << "#define main main_function_\n";
  return ss.str();
}

std::string WGPUShader::fragment_interface_declare(const shader::ShaderCreateInfo &info) const
{
  std::stringstream ss;

  int location = 0;
  for (const StageInterfaceInfo *iface : info.vertex_out_interfaces_) {
    print_interface(ss, "in", *iface, location);
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

void WGPUShader::vertex_shader_from_glsl(const shader::ShaderCreateInfo & /*info*/,
                                         MutableSpan<StringRefNull> sources)
{
  vertex_glsl_ = preprocess(combine_with_patch(glsl_patch("#define GPU_VERTEX_SHADER\n"), sources));
}
void WGPUShader::geometry_shader_from_glsl(const shader::ShaderCreateInfo & /*info*/,
                                           MutableSpan<StringRefNull> /*sources*/)
{
}
void WGPUShader::fragment_shader_from_glsl(const shader::ShaderCreateInfo & /*info*/,
                                           MutableSpan<StringRefNull> sources)
{
  fragment_glsl_ = preprocess(
      combine_with_patch(glsl_patch("#define GPU_FRAGMENT_SHADER\n"), sources));
}
void WGPUShader::compute_shader_from_glsl(const shader::ShaderCreateInfo & /*info*/,
                                          MutableSpan<StringRefNull> sources)
{
  compute_glsl_ = preprocess(
      combine_with_patch(glsl_patch("#define GPU_COMPUTE_SHADER\n"), sources));
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
      d.kind = wgi::ResourceKind::Sampler;
      map_image_type(res.sampler.type, d.texel, d.dim);
      d.filtering = true;
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
  return true;
}

void WGPUShader::warm_cache(int /*limit*/) {}

/* Draw-time pipeline binding runs through lane B's pipeline assembly; no-op here. */
void WGPUShader::bind(const shader::SpecializationConstants * /*constants_state*/) {}
void WGPUShader::unbind() {}

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
   * resources_declare / the ResourceDesc list). */
  blender::Map<uint32_t, uint32_t> bindings;
  push_constants_binding_ = build_dense_bindings(info, bindings);
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
