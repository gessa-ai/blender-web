/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm parity contract for the canonical in-tree WebGPU
 * texture-format table and RGB-to-RGBA conversion module. No instance, adapter,
 * device, or texture is created; live texture operations remain part of the
 * hardware-gated M3 replay. */

#include <array>
#include <cinttypes>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <vector>

#include "intern/gpu_texture_private.hh"

#include "wgpu_common.hh"
#include "wgpu_data_conversion.hh"
#include "wgpu_texture_format.hh"

namespace bw = blender::gpu::webgpu;
namespace gpu = blender::gpu;

namespace {

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "FAIL %s\n", message);
    return false;
  }
  return true;
}

uint64_t fnv_byte(uint64_t hash, const uint8_t value)
{
  return (hash ^ value) * UINT64_C(1099511628211);
}

uint64_t fnv_u64(uint64_t hash, const uint64_t value)
{
  for (uint32_t shift = 0; shift < 64; shift += 8) {
    hash = fnv_byte(hash, uint8_t(value >> shift));
  }
  return hash;
}

uint64_t fnv_string(uint64_t hash, const char *value)
{
  for (const unsigned char *p = reinterpret_cast<const unsigned char *>(value); *p != 0; p++) {
    hash = fnv_byte(hash, *p);
  }
  return fnv_byte(hash, 0);
}

uint8_t caps_mask(const bw::FormatCaps &caps)
{
  return uint8_t(caps.renderable) | (uint8_t(caps.filterable) << 1) |
         (uint8_t(caps.storage) << 2) | (uint8_t(caps.blendable) << 3) |
         (uint8_t(caps.multisample) << 4);
}

bool table_contract()
{
  size_t count = 0;
  const bw::FormatInfo *table = bw::format_table(count);
  std::array<size_t, 4> conv_counts = {};
  std::array<size_t, 7> gate_counts = {};
  uint64_t hash = UINT64_C(14695981039346656037);

  if (!require(table != nullptr, "format table is null") ||
      !require(count == 63, "format table census"))
  {
    return false;
  }

  for (size_t i = 0; i < count; i++) {
    const bw::FormatInfo &info = table[i];
    if (!require(info.blender != bw::TextureFormat::Invalid, "invalid format row") ||
        !require(info.name != nullptr && info.name[0] != '\0', "empty format name") ||
        !require(info.src_bytes_per_pixel > 0, "zero source bytes") ||
        !require(info.src_components >= 1 && info.src_components <= 4,
                 "source component range") ||
        !require(info.wgpu != wgpu::TextureFormat::Undefined, "undefined WebGPU target") ||
        !require(&bw::format_info(info.blender) == &info, "format lookup identity") ||
        !require(bw::to_wgpu_format(info.blender) == info.wgpu, "format lookup target") ||
        !require(caps_mask(info.caps) == caps_mask(bw::caps_of(info.wgpu)),
                 "capability lookup identity"))
    {
      return false;
    }
    for (size_t j = 0; j < i; j++) {
      if (!require(table[j].blender != info.blender, "duplicate Blender format")) {
        return false;
      }
    }

    const size_t conv_index = size_t(info.conv);
    const size_t gate_index = size_t(info.gate);
    if (!require(conv_index < conv_counts.size(), "conversion enum range") ||
        !require(gate_index < gate_counts.size(), "feature-gate enum range"))
    {
      return false;
    }
    conv_counts[conv_index]++;
    gate_counts[gate_index]++;
    if (info.conv == bw::ConvClass::PromoteRGBA &&
        !require(info.src_components == 3 && info.src_bytes_per_pixel % 3 == 0,
                 "promotion row shape"))
    {
      return false;
    }
    if (info.conv == bw::ConvClass::Depth &&
        !require(info.src_components == 1, "depth row shape"))
    {
      return false;
    }

    hash = fnv_string(hash, info.name);
    hash = fnv_u64(hash, uint64_t(info.blender));
    hash = fnv_u64(hash, info.src_bytes_per_pixel);
    hash = fnv_u64(hash, info.src_components);
    hash = fnv_u64(hash, uint64_t(info.wgpu));
    hash = fnv_u64(hash, uint64_t(info.conv));
    hash = fnv_u64(hash, uint64_t(info.gate));
    hash = fnv_byte(hash, caps_mask(info.caps));
  }

  const std::array<size_t, 4> expected_conv = {41, 13, 3, 6};
  const std::array<size_t, 7> expected_gates = {43, 6, 1, 4, 4, 4, 1};
  if (!require(conv_counts == expected_conv, "conversion census") ||
      !require(gate_counts == expected_gates, "feature-gate census"))
  {
    return false;
  }

  const bw::FormatInfo &invalid = bw::format_info(bw::TextureFormat::Invalid);
  if (!require(invalid.blender == bw::TextureFormat::Invalid, "invalid lookup enum") ||
      !require(invalid.wgpu == wgpu::TextureFormat::Undefined, "invalid lookup target"))
  {
    return false;
  }

  std::printf("CONTRACT table PASS formats=%zu direct=%zu promote=%zu depth=%zu compressed=%zu "
              "digest=%016" PRIx64 "\n",
              count,
              conv_counts[0],
              conv_counts[1],
              conv_counts[2],
              conv_counts[3],
              hash);
  return true;
}

bool caps_equal(const bw::FormatCaps &actual,
                const bool renderable,
                const bool filterable,
                const bool storage,
                const bool blendable,
                const bool multisample)
{
  return actual.renderable == renderable && actual.filterable == filterable &&
         actual.storage == storage && actual.blendable == blendable &&
         actual.multisample == multisample;
}

bool capabilities_contract()
{
  struct Case {
    wgpu::TextureFormat format;
    bool renderable;
    bool filterable;
    bool storage;
    bool blendable;
    bool multisample;
  };
  constexpr std::array<Case, 7> cases = {{{wgpu::TextureFormat::RGBA8Unorm,
                                           true,
                                           true,
                                           true,
                                           true,
                                           true},
                                          {wgpu::TextureFormat::RGBA8UnormSrgb,
                                           true,
                                           true,
                                           false,
                                           true,
                                           true},
                                          {wgpu::TextureFormat::RGBA8Uint,
                                           true,
                                           false,
                                           true,
                                           false,
                                           false},
                                          {wgpu::TextureFormat::R32Float,
                                           true,
                                           false,
                                           true,
                                           false,
                                           true},
                                          {wgpu::TextureFormat::R8Snorm,
                                           false,
                                           true,
                                           false,
                                           false,
                                           false},
                                          {wgpu::TextureFormat::Depth32Float,
                                           true,
                                           false,
                                           false,
                                           false,
                                           true},
                                          {wgpu::TextureFormat::BC1RGBAUnorm,
                                           false,
                                           true,
                                           false,
                                           false,
                                           false}}};
  for (const Case &test : cases) {
    if (!require(caps_equal(bw::caps_of(test.format),
                            test.renderable,
                            test.filterable,
                            test.storage,
                            test.blendable,
                            test.multisample),
                 "representative capability case"))
    {
      return false;
    }
  }

  size_t count = 0;
  const bw::FormatInfo *table = bw::format_table(count);
  std::array<size_t, 5> totals = {};
  for (size_t i = 0; i < count; i++) {
    const bw::FormatCaps &caps = table[i].caps;
    if (!require(!caps.blendable || caps.renderable, "blendable requires renderable") ||
        !require(!caps.multisample || caps.renderable, "multisample requires renderable"))
    {
      return false;
    }
    totals[0] += caps.renderable;
    totals[1] += caps.filterable;
    totals[2] += caps.storage;
    totals[3] += caps.blendable;
    totals[4] += caps.multisample;
  }

  std::printf("CONTRACT capabilities PASS cases=%zu totals=%zu/%zu/%zu/%zu/%zu\n",
              cases.size(),
              totals[0],
              totals[1],
              totals[2],
              totals[3],
              totals[4]);
  return true;
}

enum FeatureMask : uint8_t {
  CompressionBC = 1u << 0,
  Unorm16 = 1u << 1,
  Tier1 = 1u << 2,
  Depth32Stencil8 = 1u << 3,
  Float32 = 1u << 4,
  RG11B10 = 1u << 5,
};

bw::TextureFormatFeatures texture_features(const uint8_t mask)
{
  bw::TextureFormatFeatures features;
  features.texture_compression_bc = (mask & CompressionBC) != 0;
  features.unorm16_texture_formats = (mask & Unorm16) != 0;
  features.texture_formats_tier1 = (mask & Tier1) != 0;
  features.depth32_float_stencil8 = (mask & Depth32Stencil8) != 0;
  features.float32_filterable = (mask & Float32) != 0;
  features.rg11b10_ufloat_renderable = (mask & RG11B10) != 0;
  return features;
}

bool format_creation_contract()
{
  constexpr std::array<bw::FeatureGate, 7> gates = {bw::FeatureGate::None,
                                                     bw::FeatureGate::TextureCompressionBC,
                                                     bw::FeatureGate::Depth32FloatStencil8,
                                                     bw::FeatureGate::Unorm16,
                                                     bw::FeatureGate::Snorm16,
                                                     bw::FeatureGate::Float32Filterable,
                                                     bw::FeatureGate::RG11B10UfloatRenderable};
  size_t accepted = 0;
  size_t rejected = 0;
  for (const bw::FeatureGate gate : gates) {
    for (uint8_t mask = 0; mask < 64; mask++) {
      bool expected = true;
      switch (gate) {
        case bw::FeatureGate::TextureCompressionBC:
          expected = (mask & CompressionBC) != 0;
          break;
        case bw::FeatureGate::Depth32FloatStencil8:
          expected = (mask & Depth32Stencil8) != 0;
          break;
        case bw::FeatureGate::Unorm16:
          expected = (mask & (Unorm16 | Tier1)) != 0;
          break;
        default:
          break;
      }
      const bool actual = bw::format_creation_supported(gate, texture_features(mask));
      if (!require(actual == expected, "feature-aware format creation")) {
        return false;
      }
      accepted += actual;
      rejected += !actual;
    }
  }
  if (!require(!bw::format_creation_supported(static_cast<bw::FeatureGate>(UINT8_MAX),
                                               texture_features(UINT8_MAX)),
               "unknown creation gate fails closed"))
  {
    return false;
  }

  std::printf("CONTRACT format-creation PASS cases=%zu accepted=%zu rejected=%zu invalid=1\n",
              gates.size() * 64,
              accepted,
              rejected);
  return accepted == 368 && rejected == 80;
}

bool render_attachment_contract()
{
  struct Case {
    wgpu::TextureFormat format;
    uint8_t features;
    bool expected;
  };
  constexpr std::array<Case, 16> cases = {{{wgpu::TextureFormat::RGBA8Unorm, 0, true},
                                           {wgpu::TextureFormat::R32Float, 0, true},
                                           {wgpu::TextureFormat::Depth32Float, 0, true},
                                           {wgpu::TextureFormat::BC1RGBAUnorm, 0, false},
                                           {wgpu::TextureFormat::R16Unorm, 0, false},
                                           {wgpu::TextureFormat::R16Unorm, Unorm16, true},
                                           {wgpu::TextureFormat::RG16Unorm, Tier1, true},
                                           {wgpu::TextureFormat::RGBA16Unorm, Tier1, true},
                                           {wgpu::TextureFormat::R8Snorm, 0, false},
                                           {wgpu::TextureFormat::RG8Snorm, Tier1, true},
                                           {wgpu::TextureFormat::RGBA8Snorm, Tier1, true},
                                           {wgpu::TextureFormat::RG11B10Ufloat, 0, false},
                                           {wgpu::TextureFormat::RG11B10Ufloat, RG11B10, true},
                                           {wgpu::TextureFormat::RG11B10Ufloat, Tier1, false},
                                           {wgpu::TextureFormat::Depth32FloatStencil8, 0, false},
                                           {wgpu::TextureFormat::Depth32FloatStencil8,
                                            Depth32Stencil8,
                                            true}}};

  size_t accepted = 0;
  size_t rejected = 0;
  for (const Case &test : cases) {
    const bw::TextureFormatFeatures features = texture_features(test.features);
    if (!require(bw::render_attachment_supported(test.format, features) == test.expected,
                 "feature-aware render-attachment capability"))
    {
      return false;
    }
    accepted += test.expected;
    rejected += !test.expected;
  }

  std::printf("CONTRACT render-attachments PASS cases=%zu accepted=%zu rejected=%zu\n",
              cases.size(),
              accepted,
              rejected);
  return accepted == 10 && rejected == 6;
}

bool view_format_contract()
{
  using F = wgpu::TextureFormat;
  constexpr std::array<std::array<F, 2>, 5> pairs = {{{F::RGBA8Unorm, F::RGBA8UnormSrgb},
                                                       {F::BGRA8Unorm, F::BGRA8UnormSrgb},
                                                       {F::BC1RGBAUnorm, F::BC1RGBAUnormSrgb},
                                                       {F::BC2RGBAUnorm, F::BC2RGBAUnormSrgb},
                                                       {F::BC3RGBAUnorm, F::BC3RGBAUnormSrgb}}};
  size_t directed = 0;
  for (const auto &pair : pairs) {
    for (size_t i = 0; i < 2; i++) {
      const F from = pair[i];
      const F to = pair[1 - i];
      if (!require(bw::srgb_view_format_pair(from) == to, "sRGB pair direction") ||
          !require(bw::is_legal_view_format(from, from), "exact view legality") ||
          !require(bw::is_legal_view_format(from, to), "paired view legality"))
      {
        return false;
      }
      directed++;
    }
  }
  if (!require(bw::srgb_view_format_pair(F::R8Unorm) == F::Undefined,
               "unpaired format sentinel") ||
      !require(!bw::is_legal_view_format(F::Undefined, F::Undefined),
               "undefined backing rejected") ||
      !require(!bw::is_legal_view_format(F::RGBA8Unorm, F::BGRA8Unorm),
               "same-size alias rejected") ||
      !require(!bw::is_legal_view_format(F::BC1RGBAUnorm, F::BC2RGBAUnorm),
               "cross-family BC alias rejected"))
  {
    return false;
  }

  std::printf("CONTRACT view-formats PASS pairs=%zu directed=%zu illegal=3\n",
              pairs.size(),
              directed);
  return directed == 10;
}

std::array<uint8_t, 4> expected_alpha(const bw::ScalarType type, const uint32_t comp_bytes)
{
  std::array<uint8_t, 4> alpha = {};
  switch (type) {
    case bw::ScalarType::Unorm:
      alpha.fill(0xff);
      break;
    case bw::ScalarType::Snorm:
      alpha.fill(0xff);
      alpha[comp_bytes - 1] = 0x7f;
      break;
    case bw::ScalarType::Uint:
    case bw::ScalarType::Sint:
      alpha[0] = 1;
      break;
    case bw::ScalarType::Float:
      if (comp_bytes == 2) {
        alpha[1] = 0x3c;
      }
      else {
        alpha[2] = 0x80;
        alpha[3] = 0x3f;
      }
      break;
  }
  return alpha;
}

bool promotion_contract()
{
  size_t count = 0;
  const bw::FormatInfo *table = bw::format_table(count);
  size_t promotions = 0;
  size_t pixels = 0;
  uint64_t hash = UINT64_C(14695981039346656037);

  for (size_t i = 0; i < count; i++) {
    const bw::FormatInfo &info = table[i];
    const bw::PromotionPlan plan = bw::promotion_plan(info.blender);
    const bool expected = info.conv == bw::ConvClass::PromoteRGBA;
    if (!require(plan.needed == expected, "promotion plan/table agreement")) {
      return false;
    }
    if (!expected) {
      continue;
    }
    if (!require(plan.comp_bytes == info.src_bytes_per_pixel / 3,
                 "promotion component width") ||
        !require(plan.comp_bytes == 1 || plan.comp_bytes == 2 || plan.comp_bytes == 4,
                 "promotion component width domain"))
    {
      return false;
    }

    constexpr uint32_t width = 3;
    constexpr uint32_t height = 2;
    const size_t src_size = size_t(width) * height * 3 * plan.comp_bytes;
    const size_t dst_size = bw::promoted_byte_size(width, height, plan.comp_bytes);
    std::vector<uint8_t> src(src_size);
    for (size_t byte = 0; byte < src.size(); byte++) {
      src[byte] = uint8_t((byte * 37 + i * 11 + 3) & 0xff);
    }
    std::vector<uint8_t> dst(dst_size, 0xa5);
    if (!require(bw::promote_rgb_to_rgba(src.data(),
                                         src.size(),
                                         dst.data(),
                                         dst.size(),
                                         width,
                                         height,
                                         plan),
                 "exact promotion rejected"))
    {
      return false;
    }
    const std::vector<uint8_t> convenience =
        bw::promote_for_upload(info.blender, src, width, height);
    if (!require(convenience == dst, "convenience promotion differs")) {
      return false;
    }

    const std::array<uint8_t, 4> alpha = expected_alpha(plan.type, plan.comp_bytes);
    for (size_t pixel = 0; pixel < size_t(width) * height; pixel++) {
      const uint8_t *source = src.data() + pixel * 3 * plan.comp_bytes;
      const uint8_t *target = dst.data() + pixel * 4 * plan.comp_bytes;
      if (!require(std::memcmp(source, target, 3 * plan.comp_bytes) == 0,
                   "promotion changed RGB") ||
          !require(std::memcmp(target + 3 * plan.comp_bytes, alpha.data(), plan.comp_bytes) == 0,
                   "promotion alpha value"))
      {
        return false;
      }
    }
    for (const uint8_t byte : dst) {
      hash = fnv_byte(hash, byte);
    }
    promotions++;
    pixels += size_t(width) * height;
  }

  if (!require(promotions == 13, "promotion census") ||
      !require(pixels == 78, "promotion pixel census"))
  {
    return false;
  }

  std::printf("CONTRACT promotion PASS formats=%zu pixels=%zu digest=%016" PRIx64 "\n",
              promotions,
              pixels,
              hash);
  return true;
}

constexpr uint32_t rgb9e5_bits(
    const uint32_t red, const uint32_t green, const uint32_t blue, const uint32_t exponent)
{
  return red | (green << 9u) | (blue << 18u) | (exponent << 27u);
}

bool rgb9e5_contract()
{
  struct DecodeCase {
    uint32_t packed;
    std::array<float, 3> expected;
  };
  const float smallest = std::ldexp(1.0f, -24);
  const float largest_scale = std::ldexp(1.0f, 7);
  const std::array<DecodeCase, 3> decode_cases = {{
      {rgb9e5_bits(0, 1, 2, 0), {0.0f, smallest, 2.0f * smallest}},
      {rgb9e5_bits(2, 1, 0, 31), {2.0f * largest_scale, largest_scale, 0.0f}},
      {rgb9e5_bits(0, 1, 2, 24), {0.0f, 1.0f, 2.0f}},
  }};

  uint64_t hash = UINT64_C(14695981039346656037);
  for (const DecodeCase &test : decode_cases) {
    float actual[3] = {};
    bw::unpack_rgb9e5_ufloat(test.packed, actual);
    if (!require(actual[0] == test.expected[0] && actual[1] == test.expected[1] &&
                     actual[2] == test.expected[2],
                 "RGB9E5 decode vector"))
    {
      return false;
    }
    hash = fnv_u64(hash, test.packed);
    for (const float value : actual) {
      uint32_t bits = 0;
      std::memcpy(&bits, &value, sizeof(bits));
      hash = fnv_u64(hash, bits);
    }
  }

  struct EncodeCase {
    std::array<float, 3> source;
    uint32_t expected;
  };
  const float max_value = 511.0f * largest_scale;
  const std::array<EncodeCase, 7> encode_cases = {{
      {{0.0f, 0.0f, 0.0f}, 0},
      {{0.0f, smallest, 2.0f * smallest}, rgb9e5_bits(0, 1, 2, 0)},
      {{1.0f, 1.0f, 1.0f}, rgb9e5_bits(256, 256, 256, 16)},
      {{0.0f, 1.0f, 2.0f}, rgb9e5_bits(0, 128, 256, 17)},
      {{1023.0f / 512.0f, 1.0f, 0.0f}, rgb9e5_bits(256, 128, 0, 17)},
      {{max_value, max_value, max_value}, rgb9e5_bits(511, 511, 511, 31)},
      {{-1.0f,
        std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity()},
       rgb9e5_bits(0, 0, 511, 31)},
  }};
  for (const EncodeCase &test : encode_cases) {
    const uint32_t actual =
        bw::pack_rgb9e5_ufloat(test.source[0], test.source[1], test.source[2]);
    if (!require(actual == test.expected, "RGB9E5 encode vector")) {
      return false;
    }
    hash = fnv_u64(hash, actual);
  }

  std::printf("CONTRACT rgb9e5 PASS encode=%zu decode=%zu edge=3 digest=%016" PRIx64 "\n",
              encode_cases.size(),
              decode_cases.size(),
              hash);
  return true;
}

constexpr uint32_t rg11b10_bits(const uint32_t red,
                                const uint32_t green,
                                const uint32_t blue)
{
  return red | (green << 11u) | (blue << 22u);
}

float float_from_bits(const uint32_t bits)
{
  float value = 0.0f;
  std::memcpy(&value, &bits, sizeof(value));
  return value;
}

uint32_t float_bits(const float value)
{
  uint32_t bits = 0;
  std::memcpy(&bits, &value, sizeof(bits));
  return bits;
}

bool rg11b10_contract()
{
  /* These are the pinned Vulkan backend's FormatF32 -> FormatF11/F10 results,
   * including its deliberate truncation and boundary behavior. WebGPU must
   * preserve that CPU oracle rather than substitute a second conversion policy. */
  struct EncodeCase {
    uint32_t source_bits;
    uint32_t expected_f11;
    uint32_t expected_f10;
  };
  constexpr std::array<EncodeCase, 16> encode_cases = {{{0x00000000u, 0x000u, 0x000u},
                                                         {0x80000000u, 0x000u, 0x000u},
                                                         {0x3f800000u, 0x3c0u, 0x1e0u},
                                                         {0x40000000u, 0x400u, 0x200u},
                                                         {0xc0000000u, 0x000u, 0x000u},
                                                         {0x7f800000u, 0x7c0u, 0x3e0u},
                                                         {0xff800000u, 0x000u, 0x000u},
                                                         {0x7fc12345u, 0x7ffu, 0x3ffu},
                                                         {0xffc12345u, 0x7ffu, 0x3ffu},
                                                         {0x37800000u, 0x000u, 0x000u},
                                                         {0x38000000u, 0x000u, 0x000u},
                                                         {0x38400000u, 0x020u, 0x010u},
                                                         {0x38800000u, 0x040u, 0x020u},
                                                         {0x477fffffu, 0x7bfu, 0x3dfu},
                                                         {0x47800000u, 0x3ffu, 0x1ffu},
                                                         {0x7f7fffffu, 0x3ffu, 0x1ffu}}};

  uint64_t hash = UINT64_C(14695981039346656037);
  for (const EncodeCase &test : encode_cases) {
    const float value = float_from_bits(test.source_bits);
    const uint32_t actual = bw::pack_r11g11b10_ufloat(value, value, value);
    const uint32_t expected =
        rg11b10_bits(test.expected_f11, test.expected_f11, test.expected_f10);
    if (!require(actual == expected, "RG11B10 encode matches pinned Vulkan")) {
      return false;
    }
    hash = fnv_u64(hash, test.source_bits);
    hash = fnv_u64(hash, actual);
  }

  struct DecodeCase {
    uint32_t source_f11;
    uint32_t source_f10;
    uint32_t expected_f11_bits;
    uint32_t expected_f10_bits;
  };
  constexpr std::array<DecodeCase, 9> decode_cases = {{{0x000u,
                                                        0x000u,
                                                        0x00000000u,
                                                        0x00000000u},
                                                       {0x3c0u,
                                                        0x1e0u,
                                                        0x3f800000u,
                                                        0x3f800000u},
                                                       {0x400u,
                                                        0x200u,
                                                        0x40000000u,
                                                        0x40000000u},
                                                       {0x7c0u,
                                                        0x3e0u,
                                                        0x7f800000u,
                                                        0x7f800000u},
                                                       {0x7ffu,
                                                        0x3ffu,
                                                        0x7fffffffu,
                                                        0x7fffffffu},
                                                       {0x001u,
                                                        0x001u,
                                                        0x38020000u,
                                                        0x38040000u},
                                                       {0x020u,
                                                        0x010u,
                                                        0x38400000u,
                                                        0x38400000u},
                                                       {0x040u,
                                                        0x020u,
                                                        0x38800000u,
                                                        0x38800000u},
                                                       {0x7bfu,
                                                        0x3dfu,
                                                        0x477e0000u,
                                                        0x477c0000u}}};
  for (const DecodeCase &test : decode_cases) {
    const uint32_t packed = rg11b10_bits(test.source_f11, test.source_f11, test.source_f10);
    float actual[3] = {};
    bw::unpack_r11g11b10_ufloat(packed, actual);
    if (!require(float_bits(actual[0]) == test.expected_f11_bits &&
                     float_bits(actual[1]) == test.expected_f11_bits &&
                     float_bits(actual[2]) == test.expected_f10_bits,
                 "RG11B10 decode matches pinned Vulkan"))
    {
      return false;
    }
    hash = fnv_u64(hash, packed);
    hash = fnv_u64(hash, float_bits(actual[0]));
    hash = fnv_u64(hash, float_bits(actual[1]));
    hash = fnv_u64(hash, float_bits(actual[2]));
  }

  std::printf("CONTRACT rg11b10 PASS encode=%zu decode=%zu special=5 digest=%016" PRIx64 "\n",
              encode_cases.size(),
              decode_cases.size(),
              hash);
  return true;
}

bool boundary_contract()
{
  const bw::PromotionPlan plan = bw::promotion_plan(bw::TextureFormat::UNORM_8_8_8);
  const bw::PromotionPlan direct = bw::promotion_plan(bw::TextureFormat::UNORM_8_8_8_8);
  const bw::PromotionPlan zero_width = {true, 0, bw::ScalarType::Unorm};
  std::array<uint8_t, 6> src = {1, 2, 3, 4, 5, 6};
  std::array<uint8_t, 8> dst = {};
  size_t cases = 0;

  if (!require(!bw::promote_rgb_to_rgba(
                   src.data(), src.size(), dst.data(), dst.size(), 2, 1, direct),
               "direct plan accepted") ||
      !require(!bw::promote_rgb_to_rgba(
                   src.data(), src.size(), dst.data(), dst.size(), 2, 1, zero_width),
               "zero component width accepted") ||
      !require(!bw::promote_rgb_to_rgba(
                   src.data(), src.size() - 1, dst.data(), dst.size(), 2, 1, plan),
               "short source accepted") ||
      !require(!bw::promote_rgb_to_rgba(
                   src.data(), src.size(), dst.data(), dst.size() - 1, 2, 1, plan),
               "short destination accepted"))
  {
    return false;
  }
  cases += 4;

  if (!require(bw::promoted_byte_size(3, 2, 4) == 96, "promoted size") ||
      !require(bw::promoted_byte_size(0, 9, 4) == 0, "zero-width promoted size") ||
      !require(bw::promote_rgb_to_rgba(nullptr, 0, nullptr, 0, 0, 0, plan),
               "empty exact promotion"))
  {
    return false;
  }
  cases += 3;

  const std::vector<uint8_t> direct_source = {9, 8, 7, 6};
  if (!require(bw::promote_for_upload(
                   bw::TextureFormat::UNORM_8_8_8_8, direct_source, 1, 1) == direct_source,
               "direct convenience copy"))
  {
    return false;
  }
  cases++;

  std::printf("CONTRACT boundaries PASS cases=%zu short=reject empty=accept direct=copy\n", cases);
  return cases == 8;
}

bool allocation_limit_contract()
{
  wgpu::Limits limits = {};
  limits.maxTextureDimension1D = 8192;
  limits.maxTextureDimension2D = 4096;
  limits.maxTextureDimension3D = 2048;
  limits.maxTextureArrayLayers = 256;

  struct Case {
    wgpu::TextureDimension dimension;
    wgpu::Extent3D size;
    uint32_t mip_levels;
    bool accepted;
  };
  const std::array<Case, 25> cases = {{
      {wgpu::TextureDimension::Undefined, {1, 1, 1}, 1, false},
      {wgpu::TextureDimension::e1D, {1, 1, 1}, 1, true},
      {wgpu::TextureDimension::e1D, {8192, 1, 1}, 1, true},
      {wgpu::TextureDimension::e1D, {8193, 1, 1}, 1, false},
      {wgpu::TextureDimension::e1D, {8192, 2, 1}, 1, false},
      {wgpu::TextureDimension::e1D, {8192, 1, 2}, 1, false},
      {wgpu::TextureDimension::e1D, {8192, 1, 1}, 2, false},
      {wgpu::TextureDimension::e2D, {1, 1, 1}, 1, true},
      {wgpu::TextureDimension::e2D, {4096, 4096, 256}, 13, true},
      {wgpu::TextureDimension::e2D, {4097, 4096, 256}, 13, false},
      {wgpu::TextureDimension::e2D, {4096, 4097, 256}, 13, false},
      {wgpu::TextureDimension::e2D, {4096, 4096, 257}, 13, false},
      {wgpu::TextureDimension::e2D, {4096, 4096, 256}, 14, false},
      {wgpu::TextureDimension::e2D, {5, 3, 1}, 3, true},
      {wgpu::TextureDimension::e2D, {5, 3, 1}, 4, false},
      {wgpu::TextureDimension::e3D, {1, 1, 1}, 1, true},
      {wgpu::TextureDimension::e3D, {2048, 2048, 2048}, 12, true},
      {wgpu::TextureDimension::e3D, {2049, 2048, 2048}, 12, false},
      {wgpu::TextureDimension::e3D, {2048, 2049, 2048}, 12, false},
      {wgpu::TextureDimension::e3D, {2048, 2048, 2049}, 12, false},
      {wgpu::TextureDimension::e3D, {2048, 2048, 2048}, 13, false},
      {wgpu::TextureDimension::e2D, {0, 1, 1}, 1, false},
      {wgpu::TextureDimension::e2D, {1, 0, 1}, 1, false},
      {wgpu::TextureDimension::e2D, {1, 1, 0}, 1, false},
      {wgpu::TextureDimension::e2D, {1, 1, 1}, 0, false},
  }};

  size_t accepted = 0;
  size_t rejected = 0;
  for (const Case &test : cases) {
    const bool actual = bw::texture_allocation_supported(
        test.dimension, test.size, test.mip_levels, limits);
    if (!require(actual == test.accepted, "texture allocation-limit decision")) {
      return false;
    }
    accepted += actual ? 1 : 0;
    rejected += actual ? 0 : 1;
  }

  wgpu::Limits zero_limits = {};
  zero_limits.maxTextureDimension1D = 0;
  zero_limits.maxTextureDimension2D = 0;
  zero_limits.maxTextureDimension3D = 0;
  zero_limits.maxTextureArrayLayers = 0;
  if (!require(!bw::texture_allocation_supported(
                   wgpu::TextureDimension::e2D, {1, 1, 1}, 1, zero_limits),
               "zero texture limits accepted"))
  {
    return false;
  }
  rejected++;

  std::printf("CONTRACT allocation-limits PASS cases=%zu accepted=%zu rejected=%zu\n",
              cases.size() + 1,
              accepted,
              rejected);
  return accepted == 7 && rejected == 19;
}

bool upload_layout_contract()
{
  struct LayoutCase {
    uint32_t width;
    uint32_t height;
    uint32_t depth;
    uint32_t device_texel_bytes;
    size_t host_texel_bytes;
    uint32_t unpack_row_length;
    size_t sample_count;
    size_t device_data_size;
    size_t source_row_stride;
    size_t source_data_size;
    uint32_t bytes_per_row;
    size_t row_count;
  };
  const std::array<LayoutCase, 4> accepted_cases = {{
      {2, 3, 4, 4, 4, 0, 24, 96, 8, 96, 8, 12},
      {2, 3, 4, 8, 4, 5, 24, 192, 20, 228, 16, 12},
      {7, 1, 1, 4, 12, 7, 7, 28, 84, 84, 28, 1},
      {1, 256, 6, 16, 12, 0, 1536, 24576, 12, 18432, 16, 1536},
  }};

  uint64_t hash = UINT64_C(14695981039346656037);
  for (const LayoutCase &test : accepted_cases) {
    bw::TextureUploadLayout actual;
    if (!require(bw::texture_upload_layout(test.width,
                                           test.height,
                                           test.depth,
                                           test.device_texel_bytes,
                                           test.host_texel_bytes,
                                           test.unpack_row_length,
                                           actual),
                 "valid texture upload layout rejected") ||
        !require(actual.sample_count == test.sample_count, "upload sample count") ||
        !require(actual.device_data_size == test.device_data_size, "upload device size") ||
        !require(actual.source_row_stride == test.source_row_stride,
                 "upload source row stride") ||
        !require(actual.source_data_size == test.source_data_size, "upload source size") ||
        !require(actual.bytes_per_row == test.bytes_per_row, "upload bytes per row") ||
        !require(actual.row_count == test.row_count, "upload row count"))
    {
      return false;
    }
    hash = fnv_u64(hash, actual.sample_count);
    hash = fnv_u64(hash, actual.device_data_size);
    hash = fnv_u64(hash, actual.source_row_stride);
    hash = fnv_u64(hash, actual.source_data_size);
    hash = fnv_u64(hash, actual.bytes_per_row);
    hash = fnv_u64(hash, actual.row_count);
  }

  struct RejectedCase {
    uint32_t width;
    uint32_t height;
    uint32_t depth;
    uint32_t device_texel_bytes;
    size_t host_texel_bytes;
    uint32_t unpack_row_length;
  };
  const std::array<RejectedCase, 10> rejected_cases = {{
      {0, 1, 1, 1, 1, 0},
      {1, 0, 1, 1, 1, 0},
      {1, 1, 0, 1, 1, 0},
      {1, 1, 1, 0, 1, 0},
      {1, 1, 1, 1, 0, 0},
      {8, 1, 1, 1, 1, 7},
      {std::numeric_limits<uint32_t>::max(), 1, 1, 2, 1, 0},
      {std::numeric_limits<uint32_t>::max(),
       std::numeric_limits<uint32_t>::max(),
       std::numeric_limits<uint32_t>::max(),
       1,
       1,
       0},
      {1, 2, 1, 1, std::numeric_limits<size_t>::max(), 2},
      {1, 2, 1, 1, std::numeric_limits<size_t>::max(), 0},
  }};
  const bw::TextureUploadLayout sentinel = {11, 12, 13, 14, 15, 16};
  for (const RejectedCase &test : rejected_cases) {
    bw::TextureUploadLayout actual = sentinel;
    if (!require(!bw::texture_upload_layout(test.width,
                                            test.height,
                                            test.depth,
                                            test.device_texel_bytes,
                                            test.host_texel_bytes,
                                            test.unpack_row_length,
                                            actual),
                 "invalid texture upload layout accepted") ||
        !require(actual.sample_count == sentinel.sample_count &&
                     actual.device_data_size == sentinel.device_data_size &&
                     actual.source_row_stride == sentinel.source_row_stride &&
                     actual.source_data_size == sentinel.source_data_size &&
                     actual.bytes_per_row == sentinel.bytes_per_row &&
                     actual.row_count == sentinel.row_count,
                 "upload layout rejection is atomic"))
    {
      return false;
    }
  }

  struct RegionCase {
    wgpu::Origin3D origin;
    wgpu::Extent3D extent;
    wgpu::Extent3D capacity;
    bool accepted;
  };
  const std::array<RegionCase, 13> region_cases = {{
      {{0, 0, 0}, {1, 1, 1}, {1, 1, 1}, true},
      {{3, 4, 5}, {7, 8, 9}, {10, 12, 14}, true},
      {{UINT32_MAX - 1, 0, 0}, {1, 1, 1}, {UINT32_MAX, 1, 1}, true},
      {{0, 0, 0}, {0, 1, 1}, {1, 1, 1}, false},
      {{0, 0, 0}, {1, 0, 1}, {1, 1, 1}, false},
      {{0, 0, 0}, {1, 1, 0}, {1, 1, 1}, false},
      {{2, 0, 0}, {1, 1, 1}, {1, 1, 1}, false},
      {{0, 2, 0}, {1, 1, 1}, {1, 1, 1}, false},
      {{0, 0, 2}, {1, 1, 1}, {1, 1, 1}, false},
      {{1, 0, 0}, {2, 1, 1}, {2, 1, 1}, false},
      {{0, 1, 0}, {1, 2, 1}, {1, 2, 1}, false},
      {{0, 0, 1}, {1, 1, 2}, {1, 1, 2}, false},
      {{UINT32_MAX, 0, 0}, {2, 1, 1}, {UINT32_MAX, 1, 1}, false},
  }};
  size_t regions_accepted = 0;
  size_t regions_rejected = 0;
  for (const RegionCase &test : region_cases) {
    const bool actual = bw::texture_region_fits(test.origin, test.extent, test.capacity);
    if (!require(actual == test.accepted, "texture upload region decision")) {
      return false;
    }
    regions_accepted += actual ? 1 : 0;
    regions_rejected += actual ? 0 : 1;
    hash = fnv_byte(hash, uint8_t(actual));
  }

  std::printf("CONTRACT upload-layout PASS layouts=%zu accepted=%zu rejected=%zu "
              "regions=%zu/%zu digest=%016" PRIx64 "\n",
              accepted_cases.size() + rejected_cases.size(),
              accepted_cases.size(),
              rejected_cases.size(),
              regions_accepted,
              regions_rejected,
              hash);
  return regions_accepted == 3 && regions_rejected == 10;
}

bool clear_layout_contract()
{
  struct AcceptedCase {
    uint32_t width;
    uint32_t height;
    uint32_t depth;
    uint32_t texel_bytes;
    size_t sample_count;
    size_t data_size;
    uint32_t bytes_per_row;
    size_t row_count;
  };
  constexpr std::array<AcceptedCase, 3> accepted_cases = {{
      {3, 2, 4, 4, 24, 96, 12, 8},
      {257, 2, 3, 16, 1542, 24672, 4112, 6},
      {8192, 1, 1, 4, 8192, 32768, 32768, 1},
  }};

  uint64_t hash = UINT64_C(14695981039346656037);
  for (const AcceptedCase &test : accepted_cases) {
    bw::TextureUploadLayout actual;
    if (!require(bw::texture_upload_layout(test.width,
                                           test.height,
                                           test.depth,
                                           test.texel_bytes,
                                           test.texel_bytes,
                                           0,
                                           actual),
                 "valid texture clear layout rejected") ||
        !require(actual.sample_count == test.sample_count, "clear sample count") ||
        !require(actual.device_data_size == test.data_size, "clear data size") ||
        !require(actual.source_data_size == test.data_size, "clear source size") ||
        !require(actual.bytes_per_row == test.bytes_per_row, "clear row bytes") ||
        !require(actual.row_count == test.row_count, "clear row count"))
    {
      return false;
    }
    hash = fnv_u64(hash, actual.sample_count);
    hash = fnv_u64(hash, actual.device_data_size);
    hash = fnv_u64(hash, actual.bytes_per_row);
    hash = fnv_u64(hash, actual.row_count);
  }

  struct RejectedCase {
    uint32_t width;
    uint32_t height;
    uint32_t depth;
    uint32_t texel_bytes;
  };
  constexpr std::array<RejectedCase, 3> rejected_cases = {{
      {0, 1, 1, 4},
      {UINT32_MAX, 1, 1, 2},
      {UINT32_MAX, UINT32_MAX, UINT32_MAX, 1},
  }};
  const bw::TextureUploadLayout sentinel = {11, 12, 13, 14, 15, 16};
  for (const RejectedCase &test : rejected_cases) {
    bw::TextureUploadLayout actual = sentinel;
    if (!require(!bw::texture_upload_layout(test.width,
                                            test.height,
                                            test.depth,
                                            test.texel_bytes,
                                            test.texel_bytes,
                                            0,
                                            actual),
                 "invalid texture clear layout accepted") ||
        !require(actual.sample_count == sentinel.sample_count &&
                     actual.device_data_size == sentinel.device_data_size &&
                     actual.source_row_stride == sentinel.source_row_stride &&
                     actual.source_data_size == sentinel.source_data_size &&
                     actual.bytes_per_row == sentinel.bytes_per_row &&
                     actual.row_count == sentinel.row_count,
                 "clear layout rejection is atomic"))
    {
      return false;
    }
  }

  std::printf("CONTRACT clear-layout PASS cases=%zu accepted=%zu rejected=%zu "
              "digest=%016" PRIx64 "\n",
              accepted_cases.size() + rejected_cases.size(),
              accepted_cases.size(),
              rejected_cases.size(),
              hash);
  return true;
}

bool packed_row_stride_contract()
{
  struct Case {
    bw::TextureFormat texture_format;
    blender::eGPUDataFormat data_format;
    size_t expected_texel_bytes;
    bool packed;
  };
  constexpr std::array<Case, 6> cases = {{
      {bw::TextureFormat::UNORM_10_10_10_2, blender::GPU_DATA_2_10_10_10_REV, 4, true},
      {bw::TextureFormat::UINT_10_10_10_2, blender::GPU_DATA_2_10_10_10_REV, 4, true},
      {bw::TextureFormat::UFLOAT_11_11_10, blender::GPU_DATA_10_11_11_REV, 4, true},
      {bw::TextureFormat::UFLOAT_11_11_10, blender::GPU_DATA_FLOAT, 12, false},
      {bw::TextureFormat::UNORM_8_8_8_8, blender::GPU_DATA_UBYTE, 4, false},
      {bw::TextureFormat::SFLOAT_32_32, blender::GPU_DATA_FLOAT, 8, false},
  }};
  constexpr size_t row_length = 7;
  size_t packed = 0;
  size_t row_bytes = 0;
  for (const Case &test : cases) {
    const size_t texel_bytes = blender::gpu::to_bytesize(test.texture_format, test.data_format);
    if (!require(texel_bytes == test.expected_texel_bytes, "host texel size") ||
        !require(row_length * texel_bytes == row_length * test.expected_texel_bytes,
                 "strided upload row size"))
    {
      return false;
    }
    const size_t component_formula = size_t(blender::gpu::to_component_len(test.texture_format)) *
                                     blender::gpu::to_bytesize(test.data_format);
    if (test.packed &&
        !require(component_formula != texel_bytes, "packed texel must bypass component formula"))
    {
      return false;
    }
    packed += test.packed;
    row_bytes += row_length * texel_bytes;
  }

  std::printf("CONTRACT packed-row-stride PASS cases=%zu packed=%zu row_bytes=%zu\n",
              cases.size(),
              packed,
              row_bytes);
  return packed == 3 && row_bytes == 252;
}

bool readback_layout_contract()
{
  struct LayoutCase {
    uint32_t width;
    uint32_t height;
    uint32_t depth;
    uint32_t device_texel_bytes;
    size_t host_texel_bytes;
    uint64_t max_staging_size;
    size_t sample_count;
    size_t device_data_size;
    size_t staging_size;
    size_t host_data_size;
    uint32_t row_bytes;
    uint32_t bytes_per_row;
    size_t row_count;
  };
  const std::array<LayoutCase, 5> accepted_cases = {{
      {1, 1, 1, 4, 4, 256, 1, 4, 256, 4, 4, 256, 1},
      {2, 3, 4, 4, 8, 3072, 24, 96, 3072, 192, 8, 256, 12},
      {65, 3, 2, 4, 8, 3072, 390, 1560, 3072, 3120, 260, 512, 6},
      {257, 2, 1, 16, 12, 8704, 514, 8224, 8704, 6168, 4112, 4352, 2},
      {64, 64, 64, 4, 4, 1048576, 262144, 1048576, 1048576, 1048576, 256, 256, 4096},
  }};

  uint64_t hash = UINT64_C(14695981039346656037);
  for (const LayoutCase &test : accepted_cases) {
    bw::TextureReadbackLayout actual;
    if (!require(bw::texture_readback_layout(test.width,
                                             test.height,
                                             test.depth,
                                             test.device_texel_bytes,
                                             test.host_texel_bytes,
                                             test.max_staging_size,
                                             actual),
                 "valid texture readback layout rejected") ||
        !require(actual.sample_count == test.sample_count, "readback sample count") ||
        !require(actual.device_data_size == test.device_data_size, "readback device size") ||
        !require(actual.staging_size == test.staging_size, "readback staging size") ||
        !require(actual.host_data_size == test.host_data_size, "readback host size") ||
        !require(actual.row_bytes == test.row_bytes, "readback row bytes") ||
        !require(actual.bytes_per_row == test.bytes_per_row, "readback padded row bytes") ||
        !require(actual.row_count == test.row_count, "readback row count"))
    {
      return false;
    }
    hash = fnv_u64(hash, actual.sample_count);
    hash = fnv_u64(hash, actual.device_data_size);
    hash = fnv_u64(hash, actual.staging_size);
    hash = fnv_u64(hash, actual.host_data_size);
    hash = fnv_u64(hash, actual.row_bytes);
    hash = fnv_u64(hash, actual.bytes_per_row);
    hash = fnv_u64(hash, actual.row_count);
  }

  struct RejectedCase {
    uint32_t width;
    uint32_t height;
    uint32_t depth;
    uint32_t device_texel_bytes;
    size_t host_texel_bytes;
    uint64_t max_staging_size;
  };
  const std::array<RejectedCase, 10> rejected_cases = {{
      {0, 1, 1, 1, 1, 256},
      {1, 0, 1, 1, 1, 256},
      {1, 1, 0, 1, 1, 256},
      {1, 1, 1, 0, 1, 256},
      {1, 1, 1, 1, 0, 256},
      {1, 1, 1, 1, 1, 0},
      {1, 1, 1, 4, 4, 255},
      {UINT32_MAX, 1, 1, 1, 1, UINT64_MAX},
      {1, UINT32_MAX, UINT32_MAX, 1, 1, UINT64_MAX},
      {1, 2, 1, 1, std::numeric_limits<size_t>::max(), UINT64_MAX},
  }};
  const bw::TextureReadbackLayout sentinel = {11, 12, 13, 14, 15, 16, 17};
  for (const RejectedCase &test : rejected_cases) {
    bw::TextureReadbackLayout actual = sentinel;
    if (!require(!bw::texture_readback_layout(test.width,
                                              test.height,
                                              test.depth,
                                              test.device_texel_bytes,
                                              test.host_texel_bytes,
                                              test.max_staging_size,
                                              actual),
                 "invalid texture readback layout accepted") ||
        !require(actual.sample_count == sentinel.sample_count &&
                     actual.device_data_size == sentinel.device_data_size &&
                     actual.staging_size == sentinel.staging_size &&
                     actual.host_data_size == sentinel.host_data_size &&
                     actual.row_bytes == sentinel.row_bytes &&
                     actual.bytes_per_row == sentinel.bytes_per_row &&
                     actual.row_count == sentinel.row_count,
                 "readback layout rejection is atomic"))
    {
      return false;
    }
  }

  std::printf("CONTRACT readback-layout PASS layouts=%zu accepted=%zu rejected=%zu "
              "digest=%016" PRIx64 "\n",
              accepted_cases.size() + rejected_cases.size(),
              accepted_cases.size(),
              rejected_cases.size(),
              hash);
  return true;
}

bool compressed_upload_layout_contract()
{
  struct Case {
    bw::TextureFormat format;
    uint32_t width;
    uint32_t height;
    uint32_t layers;
    uint32_t unpack_row_length;
    uint32_t copy_width;
    uint32_t copy_height;
    uint32_t bytes_per_row;
    uint32_t rows_per_image;
    size_t data_size;
  };
  constexpr std::array<Case, 7> cases = {{
      {bw::TextureFormat::SNORM_DXT1, 8, 8, 1, 0, 8, 8, 16, 2, 32},
      {bw::TextureFormat::SRGB_DXT1, 2, 1, 1, 0, 4, 4, 8, 1, 8},
      {bw::TextureFormat::SNORM_DXT3, 12, 8, 1, 0, 12, 8, 48, 2, 96},
      {bw::TextureFormat::SRGB_DXT5, 7, 5, 1, 0, 8, 8, 32, 2, 64},
      {bw::TextureFormat::SNORM_DXT1, 8, 8, 3, 0, 8, 8, 16, 2, 96},
      {bw::TextureFormat::SNORM_DXT1, 8, 8, 1, 16, 8, 8, 32, 2, 64},
      {bw::TextureFormat::SRGB_DXT5, 1, 1, 6, 9, 4, 4, 48, 1, 288},
  }};

  uint64_t hash = UINT64_C(14695981039346656037);
  for (const Case &test : cases) {
    bw::CompressedUploadLayout actual;
    if (!require(bw::compressed_upload_layout(test.format,
                                              test.width,
                                              test.height,
                                              test.layers,
                                              test.unpack_row_length,
                                              actual),
                 "compressed layout accepted") ||
        !require(actual.copy_width == test.copy_width, "compressed copy width") ||
        !require(actual.copy_height == test.copy_height, "compressed copy height") ||
        !require(actual.bytes_per_row == test.bytes_per_row, "compressed bytes per row") ||
        !require(actual.rows_per_image == test.rows_per_image, "compressed rows per image") ||
        !require(actual.data_size == test.data_size, "compressed data size"))
    {
      return false;
    }
    hash = fnv_u64(hash, uint64_t(test.format));
    hash = fnv_u64(hash, actual.copy_width);
    hash = fnv_u64(hash, actual.copy_height);
    hash = fnv_u64(hash, actual.bytes_per_row);
    hash = fnv_u64(hash, actual.rows_per_image);
    hash = fnv_u64(hash, actual.data_size);
  }

  bw::CompressedUploadLayout sentinel = {17, 18, 19, 20, 21};
  const bw::CompressedUploadLayout unchanged = sentinel;
  const auto rejects_without_mutation = [&](bw::TextureFormat format,
                                            uint32_t width,
                                            uint32_t height,
                                            uint32_t layers,
                                            uint32_t unpack_row_length) {
    sentinel = unchanged;
    const bool accepted = bw::compressed_upload_layout(
        format, width, height, layers, unpack_row_length, sentinel);
    return require(!accepted, "compressed invalid layout rejected") &&
           require(std::memcmp(&sentinel, &unchanged, sizeof(sentinel)) == 0,
                   "compressed rejection is atomic");
  };
  if (!rejects_without_mutation(bw::TextureFormat::UNORM_8_8_8_8, 4, 4, 1, 0) ||
      !rejects_without_mutation(bw::TextureFormat::SNORM_DXT1, 0, 4, 1, 0) ||
      !rejects_without_mutation(bw::TextureFormat::SNORM_DXT1, 4, 0, 1, 0) ||
      !rejects_without_mutation(bw::TextureFormat::SNORM_DXT1, 4, 4, 0, 0) ||
      !rejects_without_mutation(bw::TextureFormat::SNORM_DXT1, 8, 4, 1, 7) ||
      !rejects_without_mutation(bw::TextureFormat::SNORM_DXT5,
                                std::numeric_limits<uint32_t>::max(),
                                4,
                                1,
                                0))
  {
    return false;
  }

  constexpr std::array<gpu::GPUTextureType, 9> types = {gpu::GPU_TEXTURE_1D,
                                                        gpu::GPU_TEXTURE_1D_ARRAY,
                                                        gpu::GPU_TEXTURE_2D,
                                                        gpu::GPU_TEXTURE_2D_ARRAY,
                                                        gpu::GPU_TEXTURE_3D,
                                                        gpu::GPU_TEXTURE_CUBE,
                                                        gpu::GPU_TEXTURE_CUBE_ARRAY,
                                                        gpu::GPU_TEXTURE_ARRAY,
                                                        gpu::GPU_TEXTURE_BUFFER};
  size_t supported = 0;
  for (gpu::GPUTextureType type : types) {
    const bool actual = bw::compressed_texture_type_supported(type);
    const bool expected = type == gpu::GPU_TEXTURE_2D || type == gpu::GPU_TEXTURE_2D_ARRAY ||
                          type == gpu::GPU_TEXTURE_CUBE || type == gpu::GPU_TEXTURE_CUBE_ARRAY;
    if (!require(actual == expected, "compressed texture type support")) {
      return false;
    }
    supported += actual;
    hash = fnv_byte(hash, uint8_t(actual));
  }

  std::printf("CONTRACT compressed-upload PASS cases=%zu supported_types=%zu digest=%016" PRIx64
              "\n",
              cases.size(),
              supported,
              hash);
  return supported == 4;
}

bool component_swizzle_contract()
{
  struct Case {
    char blender;
    wgpu::ComponentSwizzle webgpu;
  };
  constexpr std::array<Case, 10> cases = {{{'r', wgpu::ComponentSwizzle::R},
                                            {'x', wgpu::ComponentSwizzle::R},
                                            {'g', wgpu::ComponentSwizzle::G},
                                            {'y', wgpu::ComponentSwizzle::G},
                                            {'b', wgpu::ComponentSwizzle::B},
                                            {'z', wgpu::ComponentSwizzle::B},
                                            {'a', wgpu::ComponentSwizzle::A},
                                            {'w', wgpu::ComponentSwizzle::A},
                                            {'0', wgpu::ComponentSwizzle::Zero},
                                            {'1', wgpu::ComponentSwizzle::One}}};
  uint64_t hash = UINT64_C(14695981039346656037);
  for (const Case &test : cases) {
    const wgpu::ComponentSwizzle actual = bw::to_wgpu_component_swizzle(test.blender);
    if (!require(actual == test.webgpu, "component swizzle mapping")) {
      return false;
    }
    hash = fnv_byte(hash, uint8_t(test.blender));
    hash = fnv_u64(hash, uint64_t(actual));
  }
  if (!require(bw::to_wgpu_component_swizzle('\0') == wgpu::ComponentSwizzle::Undefined,
               "invalid component swizzle sentinel") ||
      !require(bw::to_wgpu_component_swizzle('R') == wgpu::ComponentSwizzle::Undefined,
               "uppercase component swizzle sentinel"))
  {
    return false;
  }
  std::printf("CONTRACT component-swizzle PASS cases=%zu aliases=4 constants=2 digest=%016" PRIx64
              "\n",
              cases.size(),
              hash);
  return true;
}

}  // namespace

int main()
{
  if (!table_contract() || !capabilities_contract() || !format_creation_contract() ||
      !render_attachment_contract() || !view_format_contract() || !promotion_contract() ||
      !rgb9e5_contract() || !rg11b10_contract() || !boundary_contract() ||
      !allocation_limit_contract() || !upload_layout_contract() || !clear_layout_contract() ||
      !packed_row_stride_contract() ||
      !readback_layout_contract() ||
      !compressed_upload_layout_contract() ||
      !component_swizzle_contract())
  {
    return 1;
  }
  std::printf(
      "INTEGRATED_TEXTURE_PASS contracts=16 formats=63 creation_cases=448 allocation_limits=26 "
      "upload_layouts=14 upload_regions=13 clear_layouts=6 "
      "readback_layouts=15 "
      "promotions=13 "
      "view_pairs=10 rgb9e5=10 rg11b10=25 packed_rows=6 compressed_layouts=7 swizzles=10\n");
  return 0;
}
