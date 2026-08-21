/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm contract for the canonical WebGPU shader frontend's
 * private type, format, qualifier, and std140 layout helpers.
 */

#include <array>
#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>

#ifndef BW_WGPU_SHADER_SOURCE
#  error "BW_WGPU_SHADER_SOURCE must name the canonical wgpu_shader.cc"
#endif

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
  for (const TextureFormat format : all_formats) {
    TextureFormat expected = format;
    if (format == TextureFormat::UFLOAT_11_11_10 || format == TextureFormat::SFLOAT_16_16) {
      expected = TextureFormat::SFLOAT_16_16_16_16;
    }
    else if (format == TextureFormat::UNORM_16_16) {
      expected = TextureFormat::SFLOAT_32_32_32_32;
    }
    if (storage_image_format(format) != expected) {
      std::cerr << "storage-format promotion mismatch enum=" << int(format) << "\n";
      return false;
    }
    promotions += expected != format;
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
  if (promotions != 3 || std::string(blender::gpu::to_string(TextureFormat::Invalid)) != "unknown") {
    std::cerr << "storage-format census mismatch\n";
    return false;
  }
  std::cout << "CONTRACT storage-formats PASS formats=63 promotions=3 spellings=32\n";
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

}  // namespace blender::gpu::webgpu::frontend_test

int main()
{
  using namespace blender::gpu::webgpu::frontend_test;
  if (!image_type_contract() || !storage_format_contract() || !qualifier_contract() ||
      !std140_contract())
  {
    return 1;
  }
  std::cout << "INTEGRATED_SHADER_FRONTEND_PASS contracts=4 cases=140\n";
  return 0;
}
