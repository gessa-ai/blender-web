/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm contract for the canonical WebGPU shader frontend's
 * private type, format, qualifier, and std140 layout helpers.
 */

#include <array>
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#ifndef BW_WGPU_SHADER_SOURCE
#  error "BW_WGPU_SHADER_SOURCE must name the canonical wgpu_shader.cc"
#endif
#ifndef BW_WGPU_PUSH_CONSTANT_SET_SOURCE
#  error "BW_WGPU_PUSH_CONSTANT_SET_SOURCE must name the extracted shipping method"
#endif

namespace blender::gpu {

/* The build driver extracts WGPUShader::push_constant_set byte-for-byte from
 * the canonical translation unit. Renaming only its class qualifier lets this
 * device-free harness execute the shipping method without constructing the
 * full polymorphic shader and retaining its live-device vtable. */
class PushPackingHarness {
 public:
  struct PushConstantSlot {
    int32_t location;
    uint32_t offset;
    uint32_t size;
  };

  std::vector<PushConstantSlot> push_constants_;
  std::vector<uint8_t> push_constants_data_;
  bool push_constants_dirty_ = false;

  void push_constant_set(int location, int comp_len, int array_size, const void *data);
};

#define WGPUShader PushPackingHarness
#include BW_WGPU_PUSH_CONSTANT_SET_SOURCE
#undef WGPUShader

}  // namespace blender::gpu

/* Include the shipping translation unit exactly once so the private helpers are
 * exercised rather than copied into the test. Uncalled live-device sections are
 * removed by function/data section garbage collection. */
#include BW_WGPU_SHADER_SOURCE

namespace blender::gpu::webgpu::frontend_test {

using shader::ImageType;
using shader::Qualifier;
using shader::ShaderCreateInfo;
using shader::Type;

struct ImageTypeCase {
  ImageType type;
  const char *sampler;
  const char *image;
};

static std::string image_type_string(ImageType type, ShaderCreateInfo::Resource::BindType bind)
{
  std::ostringstream output;
  print_image_type(output, type, bind);
  return output.str();
}

static bool image_type_contract()
{
  using BindType = ShaderCreateInfo::Resource::BindType;
  static constexpr std::array<ImageTypeCase, 39> cases = {{
      {ImageType::undefined, "sampler ", "image "},
      {ImageType::Float1D, "sampler1D ", "image1D "},
      {ImageType::Uint1D, "usampler1D ", "uimage1D "},
      {ImageType::Int1D, "isampler1D ", "iimage1D "},
      {ImageType::Float1DArray, "sampler1DArray ", "image1DArray "},
      {ImageType::Uint1DArray, "usampler1DArray ", "uimage1DArray "},
      {ImageType::Int1DArray, "isampler1DArray ", "iimage1DArray "},
      {ImageType::Float2D, "sampler2D ", "image2D "},
      {ImageType::Uint2D, "usampler2D ", "uimage2D "},
      {ImageType::Int2D, "isampler2D ", "iimage2D "},
      {ImageType::Float2DArray, "sampler2DArray ", "image2DArray "},
      {ImageType::Uint2DArray, "usampler2DArray ", "uimage2DArray "},
      {ImageType::Int2DArray, "isampler2DArray ", "iimage2DArray "},
      {ImageType::Float3D, "sampler3D ", "image3D "},
      {ImageType::Uint3D, "usampler3D ", "uimage3D "},
      {ImageType::Int3D, "isampler3D ", "iimage3D "},
      {ImageType::FloatCube, "samplerCube ", "imageCube "},
      {ImageType::UintCube, "usamplerCube ", "uimageCube "},
      {ImageType::IntCube, "isamplerCube ", "iimageCube "},
      {ImageType::FloatCubeArray, "samplerCubeArray ", "imageCubeArray "},
      {ImageType::UintCubeArray, "usamplerCubeArray ", "uimageCubeArray "},
      {ImageType::IntCubeArray, "isamplerCubeArray ", "iimageCubeArray "},
      {ImageType::FloatBuffer, "samplerBuffer ", "imageBuffer "},
      {ImageType::UintBuffer, "usamplerBuffer ", "uimageBuffer "},
      {ImageType::IntBuffer, "isamplerBuffer ", "iimageBuffer "},
      {ImageType::Shadow2D, "sampler2DShadow ", "image2DShadow "},
      {ImageType::Depth2D, "sampler2D ", "image2D "},
      {ImageType::Shadow2DArray, "sampler2DArrayShadow ", "image2DArrayShadow "},
      {ImageType::Depth2DArray, "sampler2DArray ", "image2DArray "},
      {ImageType::ShadowCube, "samplerCubeShadow ", "imageCubeShadow "},
      {ImageType::DepthCube, "samplerCube ", "imageCube "},
      {ImageType::ShadowCubeArray, "samplerCubeArrayShadow ", "imageCubeArrayShadow "},
      {ImageType::DepthCubeArray, "samplerCubeArray ", "imageCubeArray "},
      {ImageType::AtomicUint2D, "usampler2D ", "uimage2D "},
      {ImageType::AtomicInt2D, "isampler2D ", "iimage2D "},
      {ImageType::AtomicUint2DArray, "usampler2DArray ", "uimage2DArray "},
      {ImageType::AtomicInt2DArray, "isampler2DArray ", "iimage2DArray "},
      {ImageType::AtomicUint3D, "usampler3D ", "uimage3D "},
      {ImageType::AtomicInt3D, "isampler3D ", "iimage3D "},
  }};

  for (const ImageTypeCase &test : cases) {
    const std::string sampler = image_type_string(test.type, BindType::SAMPLER);
    const std::string image = image_type_string(test.type, BindType::IMAGE);
    if (sampler != test.sampler || image != test.image) {
      std::cerr << "image-type mismatch enum=" << int(test.type) << " sampler='" << sampler
                << "' image='" << image << "'\n";
      return false;
    }
  }
  std::cout << "CONTRACT image-types PASS cases=39 bindings=78 signed-atomic-array=1\n";
  return true;
}

struct FormatCase {
  TextureFormat format;
  const char *spelling;
};

static bool storage_format_contract()
{
#define BW_FORMAT_VALUE(a, b, c, blender_enum, d, e, f, g, h) TextureFormat::blender_enum,
  static constexpr TextureFormat all_formats[] = {GPU_TEXTURE_FORMAT_EXPAND(BW_FORMAT_VALUE)};
#undef BW_FORMAT_VALUE
  static_assert(std::size(all_formats) == 63);

  size_t promotions = 0;
  for (uint32_t qualifier_bits = 0; qualifier_bits <= uint32_t(Qualifier::QUALIFIER_MAX);
       qualifier_bits++)
  {
    const Qualifier qualifiers = Qualifier(qualifier_bits);
    for (const TextureFormat format : all_formats) {
      TextureFormat expected = format;
      if (format == TextureFormat::UFLOAT_11_11_10) {
        expected = TextureFormat::SFLOAT_16_16_16_16;
      }
      else if (format == TextureFormat::SFLOAT_16_16 &&
               bool(qualifiers & Qualifier::read) && bool(qualifiers & Qualifier::write))
      {
        expected = TextureFormat::SFLOAT_16_16_16_16;
      }
      else if (format == TextureFormat::UNORM_16_16) {
        expected = TextureFormat::SFLOAT_32_32_32_32;
      }
      if (storage_image_format(format, qualifiers) != expected) {
        std::cerr << "storage-format promotion mismatch enum=" << int(format)
                  << " qualifiers=" << qualifier_bits << "\n";
        return false;
      }
      promotions += expected != format;
    }
  }

  static constexpr std::array<FormatCase, 32> spellings = {{
      {TextureFormat::UINT_8_8_8_8, "rgba8ui"},
      {TextureFormat::SINT_8_8_8_8, "rgba8i"},
      {TextureFormat::UNORM_8_8_8_8, "rgba8"},
      {TextureFormat::UINT_32_32_32_32, "rgba32ui"},
      {TextureFormat::SINT_32_32_32_32, "rgba32i"},
      {TextureFormat::SFLOAT_32_32_32_32, "rgba32f"},
      {TextureFormat::UINT_16_16_16_16, "rgba16ui"},
      {TextureFormat::SINT_16_16_16_16, "rgba16i"},
      {TextureFormat::SFLOAT_16_16_16_16, "rgba16f"},
      {TextureFormat::UNORM_16_16_16_16, "rgba16"},
      {TextureFormat::UINT_8_8, "rg8ui"},
      {TextureFormat::SINT_8_8, "rg8i"},
      {TextureFormat::UNORM_8_8, "rg8"},
      {TextureFormat::UINT_32_32, "rg32ui"},
      {TextureFormat::SINT_32_32, "rg32i"},
      {TextureFormat::SFLOAT_32_32, "rg32f"},
      {TextureFormat::UINT_16_16, "rg16ui"},
      {TextureFormat::SINT_16_16, "rg16i"},
      {TextureFormat::SFLOAT_16_16, "rg16f"},
      {TextureFormat::UNORM_16_16, "rg16"},
      {TextureFormat::UINT_8, "r8ui"},
      {TextureFormat::SINT_8, "r8i"},
      {TextureFormat::UNORM_8, "r8"},
      {TextureFormat::UINT_32, "r32ui"},
      {TextureFormat::SINT_32, "r32i"},
      {TextureFormat::SFLOAT_32, "r32f"},
      {TextureFormat::UINT_16, "r16ui"},
      {TextureFormat::SINT_16, "r16i"},
      {TextureFormat::SFLOAT_16, "r16f"},
      {TextureFormat::UNORM_16, "r16"},
      {TextureFormat::UFLOAT_11_11_10, "r11f_g11f_b10f"},
      {TextureFormat::UNORM_10_10_10_2, "rgb10_a2"},
  }};
  for (const FormatCase &test : spellings) {
    if (std::string(blender::gpu::to_string(test.format)) != test.spelling) {
      std::cerr << "storage-format spelling mismatch enum=" << int(test.format) << "\n";
      return false;
    }
  }
  if (promotions != 18 ||
      std::string(blender::gpu::to_string(TextureFormat::Invalid)) != "unknown")
  {
    std::cerr << "storage-format census mismatch\n";
    return false;
  }
  std::cout << "CONTRACT storage-formats PASS formats=63 qualifiers=8 helper-cases=504 "
               "promotions=18 spellings=32 shipping-call-sites=3\n";
  return true;
}

static std::string image_qualifier_string(Qualifier value)
{
  std::ostringstream output;
  print_qualifier(output, value);
  return output.str();
}

static std::string buffer_qualifier_string(Qualifier value)
{
  std::ostringstream output;
  print_storage_buffer_qualifier(output, value);
  return output.str();
}

static bool qualifier_contract()
{
  static constexpr std::array<const char *, 8> image_expected = {
      "restrict writeonly readonly ",
      "writeonly readonly ",
      "restrict readonly ",
      "readonly ",
      "restrict writeonly ",
      "writeonly ",
      "restrict ",
      "",
  };
  static constexpr std::array<const char *, 8> buffer_expected = {
      "restrict ", "", "restrict readonly ", "readonly ", "restrict ", "", "restrict ", "",
  };
  for (uint32_t bits = 0; bits < 8; bits++) {
    const Qualifier value = Qualifier(bits);
    if (image_qualifier_string(value) != image_expected[bits] ||
        buffer_qualifier_string(value) != buffer_expected[bits])
    {
      std::cerr << "qualifier mismatch bits=" << bits << "\n";
      return false;
    }
  }
  std::cout << "CONTRACT qualifiers PASS bit-patterns=8 outputs=16 writeonly-promoted=1\n";
  return true;
}

template<int Tag> class LayoutHandleProbe {
 public:
  LayoutHandleProbe() = default;
  explicit LayoutHandleProbe(const int identity) : identity_(identity) {}

  bool operator==(std::nullptr_t) const
  {
    return identity_ == 0;
  }

  int identity() const
  {
    return identity_;
  }

 private:
  int identity_ = 0;
};

struct LayoutAllocationProbe {
  LayoutHandleProbe<1> bind_group_layout;
  LayoutHandleProbe<2> pipeline_layout;

  bool operator==(std::nullptr_t) const
  {
    return bind_group_layout == nullptr || pipeline_layout == nullptr;
  }
  bool operator!=(std::nullptr_t) const
  {
    return !(*this == nullptr);
  }
};

static bool explicit_layout_scoped_publication_contract()
{
  using BindGroupLayoutProbe = LayoutHandleProbe<1>;
  using PipelineLayoutProbe = LayoutHandleProbe<2>;
  using LayoutCache = ScopedHandleCache<uint8_t, LayoutAllocationProbe>;

  LayoutCache cache;
  int bind_group_calls = 0;
  int pipeline_calls = 0;
  int scope_begins = 0;
  int scope_ends = 0;
  std::function<void(bool)> settle;
  auto create = [&](LayoutCache &target, const int bind_group_id, const int pipeline_id) {
    return target.get_or_create_scoped(
        uint8_t(0),
        [&]() { scope_begins++; },
        [&]() {
          bind_group_calls++;
          BindGroupLayoutProbe bind_group(bind_group_id);
          if (bind_group == nullptr) {
            return LayoutAllocationProbe{};
          }
          pipeline_calls++;
          PipelineLayoutProbe pipeline(pipeline_id);
          if (pipeline == nullptr) {
            return LayoutAllocationProbe{};
          }
          return LayoutAllocationProbe{bind_group, pipeline};
        },
        [&](auto completion) {
          scope_ends++;
          settle = std::move(completion);
        });
  };

  LayoutAllocationProbe result = create(cache, 11, 13);
  if (result != nullptr || !cache.pending(uint8_t(0)) || cache.size() != 0 || !settle ||
      bind_group_calls != 1 || pipeline_calls != 1)
  {
    std::cerr << "explicit-layout error pair escaped pending state\n";
    return false;
  }
  result = create(cache, 17, 19);
  if (result != nullptr || bind_group_calls != 1 || pipeline_calls != 1) {
    std::cerr << "explicit-layout pending request was not deduplicated\n";
    return false;
  }
  settle(false);
  if (cache.pending(uint8_t(0)) || cache.size() != 0 || cache.lookup(uint8_t(0)) != nullptr) {
    std::cerr << "explicit-layout non-null error pair was published\n";
    return false;
  }

  result = create(cache, 23, 29);
  if (result != nullptr || !settle) {
    std::cerr << "explicit-layout retry did not remain pending\n";
    return false;
  }
  settle(true);
  result = cache.lookup(uint8_t(0));
  if (result.bind_group_layout.identity() != 23 || result.pipeline_layout.identity() != 29 ||
      cache.size() != 1 || cache.pending(uint8_t(0)))
  {
    std::cerr << "explicit-layout accepted pair was not atomically published\n";
    return false;
  }
  result = create(cache, 31, 37);
  if (result.bind_group_layout.identity() != 23 || result.pipeline_layout.identity() != 29 ||
      bind_group_calls != 2 || pipeline_calls != 2)
  {
    std::cerr << "explicit-layout cache hit replaced an accepted pair\n";
    return false;
  }

  LayoutCache missing_bind_group;
  result = create(missing_bind_group, 0, 41);
  settle(true);
  if (result != nullptr || missing_bind_group.lookup(uint8_t(0)) != nullptr ||
      pipeline_calls != 2)
  {
    std::cerr << "explicit-layout null bind-group candidate reached pipeline creation\n";
    return false;
  }
  LayoutCache missing_pipeline;
  result = create(missing_pipeline, 43, 0);
  settle(true);
  if (result != nullptr || missing_pipeline.lookup(uint8_t(0)) != nullptr ||
      bind_group_calls != 4 || pipeline_calls != 3)
  {
    std::cerr << "explicit-layout null pipeline candidate was published\n";
    return false;
  }
  if (scope_begins != 4 || scope_ends != 4) {
    std::cerr << "explicit-layout scope census mismatch\n";
    return false;
  }

  std::cout << "CONTRACT explicit-layout-scoped-publication PASS cases=7 attempts=4 "
               "pending=deduplicated error-object=rejected retry=published nulls=atomic\n";
  return true;
}

struct LayoutCase {
  Type type;
  uint32_t align;
  uint32_t size;
  uint32_t array_size;
};

static bool std140_contract()
{
  static constexpr std::array<LayoutCase, 30> cases = {{
      {Type::float_t, 4, 4, 0},       {Type::float2_t, 8, 8, 0},
      {Type::float3_t, 16, 12, 0},    {Type::float4_t, 16, 16, 0},
      {Type::float3x3_t, 16, 48, 0},  {Type::float4x4_t, 16, 64, 0},
      {Type::uint_t, 4, 4, 0},        {Type::uint2_t, 8, 8, 0},
      {Type::uint3_t, 16, 12, 0},     {Type::uint4_t, 16, 16, 0},
      {Type::int_t, 4, 4, 0},         {Type::int2_t, 8, 8, 0},
      {Type::int3_t, 16, 12, 0},      {Type::int4_t, 16, 16, 0},
      {Type::bool_t, 4, 4, 0},        {Type::float_t, 16, 48, 3},
      {Type::float2_t, 16, 48, 3},    {Type::float3_t, 16, 48, 3},
      {Type::float4_t, 16, 48, 3},    {Type::float3x3_t, 16, 144, 3},
      {Type::float4x4_t, 16, 192, 3}, {Type::uint_t, 16, 48, 3},
      {Type::uint2_t, 16, 48, 3},     {Type::uint3_t, 16, 48, 3},
      {Type::uint4_t, 16, 48, 3},     {Type::int_t, 16, 48, 3},
      {Type::int2_t, 16, 48, 3},      {Type::int3_t, 16, 48, 3},
      {Type::int4_t, 16, 48, 3},      {Type::bool_t, 16, 48, 3},
  }};
  for (const LayoutCase &test : cases) {
    uint32_t align = 0;
    uint32_t size = 0;
    std140_align_size(test.type, int(test.array_size), align, size);
    if (align != test.align || size != test.size) {
      std::cerr << "std140 mismatch type=" << int(test.type)
                << " array=" << test.array_size << " align=" << align << " size=" << size
                << "\n";
      return false;
    }
  }
  std::cout << "CONTRACT std140 PASS cases=30 scalars=15 arrays=15\n";
  return true;
}

static bool push_array_packing_contract()
{
  PushPackingHarness shader;
  shader.push_constants_ = {
      {1024, 0, 80}, {1025, 80, 48}, {1026, 128, 48}, {1027, 176, 48}, {1028, 224, 80}};
  shader.push_constants_data_.assign(304, 0);

  static constexpr std::array<float, 5> float_values = {1.25f, -2.5f, 3.75f, -4.0f, 5.5f};
  static constexpr std::array<float, 6> float2_values = {
      11.0f, 12.0f, 21.0f, 22.0f, 31.0f, 32.0f};
  static constexpr std::array<float, 9> float3_values = {
      101.0f, 102.0f, 103.0f, 201.0f, 202.0f, 203.0f, 301.0f, 302.0f, 303.0f};
  static constexpr std::array<float, 12> float4_values = {1001.0f,
                                                          1002.0f,
                                                          1003.0f,
                                                          1004.0f,
                                                          2001.0f,
                                                          2002.0f,
                                                          2003.0f,
                                                          2004.0f,
                                                          3001.0f,
                                                          3002.0f,
                                                          3003.0f,
                                                          3004.0f};
  static constexpr std::array<int, 5> int_values = {7, -11, 13, -17, 19};

  shader.push_constant_set(1024, 1, int(float_values.size()), float_values.data());
  shader.push_constant_set(1025, 2, 3, float2_values.data());
  shader.push_constant_set(1026, 3, 3, float3_values.data());
  shader.push_constant_set(1027, 4, 3, float4_values.data());
  shader.push_constant_set(1028, 1, int(int_values.size()), int_values.data());

  if (shader.push_constants_.size() != 5 || !shader.push_constants_dirty_) {
    std::cerr << "push-array layout census mismatch slots=" << shader.push_constants_.size()
              << " dirty="
              << shader.push_constants_dirty_ << "\n";
    return false;
  }

  const auto bytes_equal = [&](uint32_t offset, const void *expected, size_t size) {
    return offset + size <= shader.push_constants_data_.size() &&
           std::memcmp(shader.push_constants_data_.data() + offset, expected, size) == 0;
  };
  const auto padding_zero = [&](uint32_t offset, size_t size) {
    if (offset + size > shader.push_constants_data_.size()) {
      return false;
    }
    for (size_t index = 0; index < size; index++) {
      if (shader.push_constants_data_[offset + index] != 0) {
        return false;
      }
    }
    return true;
  };

  size_t payload_bytes = 0;
  size_t padding_bytes = 0;
  const auto check_strided = [&](uint32_t base,
                                 const void *source,
                                 uint32_t source_stride,
                                 uint32_t count) {
    const uint8_t *source_bytes = static_cast<const uint8_t *>(source);
    for (uint32_t index = 0; index < count; index++) {
      const uint32_t destination = base + index * 16;
      if (!bytes_equal(destination, source_bytes + index * source_stride, source_stride) ||
          !padding_zero(destination + source_stride, 16 - source_stride))
      {
        return false;
      }
      payload_bytes += source_stride;
      padding_bytes += 16 - source_stride;
    }
    return true;
  };

  if (!check_strided(0, float_values.data(), 4, 5) ||
      !check_strided(80, float2_values.data(), 8, 3) ||
      !check_strided(128, float3_values.data(), 12, 3) ||
      !bytes_equal(176, float4_values.data(), sizeof(float4_values)) ||
      !check_strided(224, int_values.data(), 4, 5))
  {
    std::cerr << "push-array std140 payload/padding mismatch\n";
    return false;
  }
  payload_bytes += sizeof(float4_values);

  std::cout << "CONTRACT push-array-packing PASS arrays=5 elements=19 payload="
            << payload_bytes << " padding=" << padding_bytes << " block=304\n";
  return true;
}

struct Mat3PackingCase {
  int location;
  uint32_t offset;
  const char *create_info;
  const char *name;
  std::array<float, 9> values;
};

static bool push_mat3_packing_contract()
{
  static constexpr std::array<Mat3PackingCase, 4> cases = {{
      {2048,
       0,
       "gpu_shader_simple_lighting",
       "NormalMatrix",
       {1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f, 7.0f, 8.0f, 9.0f}},
      {2049,
       48,
       "gpu_scene_linear_to_rec709_space",
       "gpu_scene_linear_to_rec709",
       {11.0f, 12.0f, 13.0f, 14.0f, 15.0f, 16.0f, 17.0f, 18.0f, 19.0f}},
      {2050,
       96,
       "gpu_shader_sequencer_scope_raster",
       "scope_gamut_to_rec709",
       {21.0f, 22.0f, 23.0f, 24.0f, 25.0f, 26.0f, 27.0f, 28.0f, 29.0f}},
      {2051,
       144,
       "gpu_shader_sequencer_scope_raster",
       "scope_yuv_matrix",
       {31.0f, 32.0f, 33.0f, 34.0f, 35.0f, 36.0f, 37.0f, 38.0f, 39.0f}},
  }};

  PushPackingHarness shader;
  for (const Mat3PackingCase &test : cases) {
    shader.push_constants_.push_back({test.location, test.offset, 48});
  }
  shader.push_constants_data_.assign(192, 0);
  for (const Mat3PackingCase &test : cases) {
    shader.push_constant_set(test.location, 9, 1, test.values.data());
  }

  if (shader.push_constants_.size() != cases.size() || !shader.push_constants_dirty_) {
    std::cerr << "push-mat3 layout census mismatch slots=" << shader.push_constants_.size()
              << " dirty=" << shader.push_constants_dirty_ << "\n";
    return false;
  }

  size_t payload_bytes = 0;
  size_t padding_bytes = 0;
  for (const Mat3PackingCase &test : cases) {
    const uint8_t *source = reinterpret_cast<const uint8_t *>(test.values.data());
    for (uint32_t column = 0; column < 3; column++) {
      const uint32_t destination = test.offset + column * 16;
      if (std::memcmp(shader.push_constants_data_.data() + destination,
                      source + column * 12,
                      12) != 0)
      {
        std::cerr << "push-mat3 payload mismatch create-info=" << test.create_info
                  << " name=" << test.name << " column=" << column << "\n";
        return false;
      }
      for (uint32_t byte = destination + 12; byte < destination + 16; byte++) {
        if (shader.push_constants_data_[byte] != 0) {
          std::cerr << "push-mat3 padding mismatch create-info=" << test.create_info
                    << " name=" << test.name << " column=" << column << "\n";
          return false;
        }
      }
      payload_bytes += 12;
      padding_bytes += 4;
    }
  }

  std::cout << "CONTRACT push-mat3-packing PASS create-infos=4 matrices=4 columns=12 payload="
            << payload_bytes << " padding=" << padding_bytes << " block=192\n";
  return true;
}

static size_t count_occurrences(const std::string &text, const std::string &needle)
{
  size_t count = 0;
  size_t position = 0;
  while ((position = text.find(needle, position)) != std::string::npos) {
    count++;
    position += needle.size();
  }
  return count;
}

static bool buffer_helper_rewrite_contract()
{
  std::string no_buffer = "float keep(float value) { return value + 1.0; }\n";
  const std::string no_buffer_expected = no_buffer;
  inline_buffer_param_helpers(no_buffer);
  if (no_buffer != no_buffer_expected) {
    std::cerr << "buffer-helper rewrote a source with no texel-buffer type\n";
    return false;
  }

  std::string simple =
      "float read_value(int index, const samplerBuffer values) { return texelFetch(values, "
      "index).x; }\n"
      "float result = read_value(3 + 4, global_values);\n";
  inline_buffer_param_helpers(simple);
  if (simple.find("read_value") != std::string::npos ||
      simple.find("texelFetch(global_values, (3 + 4)).x") == std::string::npos)
  {
    std::cerr << "single texel-buffer helper did not inline faithfully\n" << simple;
    return false;
  }

  std::string nested =
      "float inner(const isamplerBuffer values, int index) { return texelFetch(values, "
      "index).x; }\n"
      "float outer(int index, const isamplerBuffer values) { return inner(values, index + 1); "
      "}\n"
      "float result = outer(7, global_values);\n";
  inline_buffer_param_helpers(nested);
  if (nested.find("inner") != std::string::npos || nested.find("outer") != std::string::npos ||
      count_occurrences(nested, "texelFetch(global_values") != 1)
  {
    std::cerr << "nested texel-buffer helpers did not fully inline\n" << nested;
    return false;
  }

  std::cout << "CONTRACT buffer-helper-rewrite PASS cases=3 nested-passes=1\n";
  return true;
}

static bool integer_sampler_rewrite_contract()
{
  std::string source =
      "uniform usampler1D u1;\n"
      "uniform isampler2D i2;\n"
      "uniform usampler3D u3;\n"
      "uniform usampler1DArray ua;\n"
      "uniform sampler2D color_tex;\n"
      "uvec4 a = texture(u1, x);\n"
      "ivec4 b = textureLod(i2, uv, mip);\n"
      "uvec4 c = textureOffset(u3, uvw, off3);\n"
      "ivec4 d = textureLodOffset(i2, uv, mip, off2);\n"
      "uvec4 e = textureGrad(u3, uvw, dx3, dy3);\n"
      "ivec4 f = textureGradOffset(i2, uv, dx2, dy2, off2);\n"
      "uvec4 g = texture(ua, array_uv);\n"
      "vec4 h = texture(color_tex, uv);\n"
      "uvec4 i = mytexture(u1, x);\n";
  rewrite_integer_sampler_sampling(source);

  if (count_occurrences(source, "texelFetch(") != 7 ||
      count_occurrences(source, "int(mip)") != 4 ||
      source.find("textureSize(u1, 0)") == std::string::npos ||
      source.find("textureSize(i2, int(mip))") == std::string::npos ||
      source.find("textureSize(u3, 0)") == std::string::npos ||
      source.find("textureSize(ua, 0)") == std::string::npos ||
      source.find("clamp(int(floor((array_uv).y + 0.5)), 0, (textureSize(ua, 0)).y - 1)") ==
          std::string::npos ||
      source.find("texture(color_tex, uv)") == std::string::npos ||
      source.find("mytexture(u1, x)") == std::string::npos)
  {
    std::cerr << "integer-sampler rewrite contract mismatch\n" << source;
    return false;
  }
  for (const char *rewritten : {"textureLod(i2",
                                "textureOffset(u3",
                                "textureLodOffset(i2",
                                "textureGrad(u3",
                                "textureGradOffset(i2",
                                "= texture(u1",
                                "= texture(ua"})
  {
    if (source.find(rewritten) != std::string::npos) {
      std::cerr << "integer-sampler call survived rewrite: " << rewritten << "\n";
      return false;
    }
  }

  std::cout << "CONTRACT integer-sampler-rewrite PASS cases=9 rewritten=7 controls=2\n";
  return true;
}

struct RewriteCase {
  const char *input;
  const char *expected;
};

static bool one_d_array_rewrite_contract()
{
  static constexpr std::array<RewriteCase, 10> sampled_cases = {{
      {"uniform sampler1DArray tex;\nvec4 r = texture(tex, uv);",
       "uniform sampler2DArray tex;\nvec4 r = texture(tex, vec3((uv).x, 0.5, (uv).y));"},
      {"uniform sampler1DArray tex;\nvec4 r = textureLod(tex, uv, level);",
       "uniform sampler2DArray tex;\nvec4 r = textureLod(tex, vec3((uv).x, 0.5, "
       "(uv).y), level);"},
      {"uniform sampler1DArray tex;\nvec4 r = textureLodOffset(tex, uv, level, offset);",
       "uniform sampler2DArray tex;\nvec4 r = textureLodOffset(tex, vec3((uv).x, 0.5, "
       "(uv).y), level, ivec2(offset, 0));"},
      {"uniform sampler1DArray tex;\nvec4 r = textureGrad(tex, uv, dx, dy);",
       "uniform sampler2DArray tex;\nvec4 r = textureGrad(tex, vec3((uv).x, 0.5, "
       "(uv).y), vec2(dx, 0.0), vec2(dy, 0.0));"},
      {"uniform sampler1DArray tex;\nvec4 r = textureOffset(tex, uv, offset);",
       "uniform sampler2DArray tex;\nvec4 r = textureOffset(tex, vec3((uv).x, 0.5, "
       "(uv).y), ivec2(offset, 0));"},
      {"uniform sampler1DArray tex;\nvec4 r = textureGradOffset(tex, uv, dx, dy, offset);",
       "uniform sampler2DArray tex;\nvec4 r = textureGradOffset(tex, vec3((uv).x, 0.5, "
       "(uv).y), vec2(dx, 0.0), vec2(dy, 0.0), ivec2(offset, 0));"},
      {"uniform sampler1DArray tex;\nvec2 r = textureQueryLod(tex, coord);",
       "uniform sampler2DArray tex;\nvec2 r = textureQueryLod(tex, vec2(coord, 0.5));"},
      {"uniform sampler1DArray tex;\nvec4 r = texelFetch(tex, point, level);",
       "uniform sampler2DArray tex;\nvec4 r = texelFetch(tex, ivec3((point).x, 0, "
       "(point).y), level);"},
      {"uniform sampler1DArray tex;\nvec4 r = texelFetchOffset(tex, point, level, offset);",
       "uniform sampler2DArray tex;\nvec4 r = texelFetchOffset(tex, ivec3((point).x, 0, "
       "(point).y), level, ivec2(offset, 0));"},
      {"uniform sampler1DArray tex;\nivec2 r = textureSize(tex, level);",
       "uniform sampler2DArray tex;\nivec2 r = textureSize(tex, level).xz;"},
  }};
  for (size_t index = 0; index < sampled_cases.size(); index++) {
    std::string actual = sampled_cases[index].input;
    rewrite_1d_array_samplers(actual);
    if (actual != sampled_cases[index].expected) {
      std::cerr << "1D-array sampled rewrite mismatch case=" << index
                << "\nexpected: " << sampled_cases[index].expected << "\nactual: " << actual
                << "\n";
      return false;
    }
  }

  static constexpr std::array<RewriteCase, 3> image_cases = {{
      {"uniform iimage1DArray img;\nivec4 r = imageLoad(img, point);",
       "uniform iimage2DArray img;\nivec4 r = imageLoad(img, ivec3((point).x, 0, "
       "(point).y));"},
      {"uniform image1DArray img;\nimageStore(img, point, value);",
       "uniform image2DArray img;\nimageStore(img, ivec3((point).x, 0, (point).y), value);"},
      {"uniform image1DArray img;\nivec2 r = imageSize(img);",
       "uniform image2DArray img;\nivec2 r = imageSize(img).xz;"},
  }};
  for (size_t index = 0; index < image_cases.size(); index++) {
    std::string actual = image_cases[index].input;
    rewrite_1d_array_samplers(actual);
    if (actual != image_cases[index].expected) {
      std::cerr << "1D-array image rewrite mismatch case=" << index
                << "\nexpected: " << image_cases[index].expected << "\nactual: " << actual << "\n";
      return false;
    }
  }

  static constexpr std::array<const char *, 8> atomic_functions = {
      "imageAtomicAdd",
      "imageAtomicMin",
      "imageAtomicMax",
      "imageAtomicAnd",
      "imageAtomicXor",
      "imageAtomicOr",
      "imageAtomicExchange",
      "imageAtomicCompSwap",
  };
  for (const char *function : atomic_functions) {
    const bool compare_swap = std::string(function) == "imageAtomicCompSwap";
    std::string actual = "uniform uimage1DArray img;\nuint r = " + std::string(function) +
                         "(img, point, " + (compare_swap ? "compare, value);" : "value);");
    const std::string expected = "uniform uimage2DArray img;\nuint r = " + std::string(function) +
                                 "(img, ivec3((point).x, 0, (point).y), " +
                                 (compare_swap ? "compare, value);" : "value);");
    rewrite_1d_array_samplers(actual);
    if (actual != expected) {
      std::cerr << "1D-array atomic rewrite mismatch function=" << function
                << "\nexpected: " << expected << "\nactual: " << actual << "\n";
      return false;
    }
  }

  std::string type_census =
      "sampler1DArray a; isampler1DArray b; usampler1DArray c; image1DArray d; "
      "iimage1DArray e; uimage1DArray f;";
  rewrite_1d_array_samplers(type_census);
  if (type_census !=
      "sampler2DArray a; isampler2DArray b; usampler2DArray c; image2DArray d; "
      "iimage2DArray e; uimage2DArray f;")
  {
    std::cerr << "1D-array type census mismatch\n" << type_census << "\n";
    return false;
  }

  std::string control = "uniform sampler2DArray tex;\nvec4 r = texture(tex, uv);";
  const std::string control_expected = control;
  rewrite_1d_array_samplers(control);
  if (control != control_expected) {
    std::cerr << "1D-array rewrite changed a 2D-array control\n";
    return false;
  }

  std::cout << "CONTRACT 1d-array-rewrite PASS cases=23 sampled=10 image=11 controls=2\n";
  return true;
}

static bool finite_builtin_rewrite_contract()
{
  std::string no_builtin = "#version 450\nvoid main() { float y = abs(x); }\n";
  const std::string no_builtin_expected = no_builtin;
  rewrite_isnan_isinf(no_builtin);
  if (no_builtin != no_builtin_expected) {
    std::cerr << "finite-builtin rewrite changed a source without target calls\n";
    return false;
  }

  std::string longer_identifiers =
      "#version 450\nbool myisnan(float x) { return false; }\n"
      "bool myisinf(float x) { return false; }\n";
  const std::string longer_identifiers_expected = longer_identifiers;
  rewrite_isnan_isinf(longer_identifiers);
  if (longer_identifiers != longer_identifiers_expected) {
    std::cerr << "finite-builtin rewrite matched longer identifiers\n";
    return false;
  }

  std::string scalar =
      "#version 450\nvoid main() { bool a = isnan(value); bool b = isinf(value); }\n";
  rewrite_isnan_isinf(scalar);
  if (scalar.rfind("#version 450\n\nbool wgpu_isnan(float x)", 0) != 0 ||
      scalar.find("bool a = wgpu_isnan(value)") == std::string::npos ||
      scalar.find("bool b = wgpu_isinf(value)") == std::string::npos ||
      count_occurrences(scalar, "bool wgpu_isnan(float x)") != 1 ||
      count_occurrences(scalar, "bool wgpu_isinf(float x)") != 1)
  {
    std::cerr << "scalar finite-builtin rewrite mismatch\n" << scalar;
    return false;
  }

  std::string vector = "void main() { bvec3 a = isnan(values); bvec4 b = isinf(values4); }\n";
  rewrite_isnan_isinf(vector);
  if (vector.rfind("\nbool wgpu_isnan(float x)", 0) != 0 ||
      vector.find("bvec3 a = wgpu_isnan(values)") == std::string::npos ||
      vector.find("bvec4 b = wgpu_isinf(values4)") == std::string::npos)
  {
    std::cerr << "vector finite-builtin rewrite mismatch\n" << vector;
    return false;
  }

  std::cout << "CONTRACT finite-builtin-rewrite PASS cases=4 overloads=8 controls=2\n";
  return true;
}

}  // namespace blender::gpu::webgpu::frontend_test

int main()
{
  using namespace blender::gpu::webgpu::frontend_test;
  if (!image_type_contract() || !storage_format_contract() || !qualifier_contract() ||
      !explicit_layout_scoped_publication_contract() || !std140_contract() ||
      !push_array_packing_contract() || !push_mat3_packing_contract() ||
      !buffer_helper_rewrite_contract() || !integer_sampler_rewrite_contract() ||
      !one_d_array_rewrite_contract() || !finite_builtin_rewrite_contract())
  {
    return 1;
  }
  std::cout << "INTEGRATED_SHADER_FRONTEND_PASS contracts=11 cases=653\n";
  return 0;
}
