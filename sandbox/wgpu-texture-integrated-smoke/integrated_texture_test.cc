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

#include "wgpu_data_conversion.hh"
#include "wgpu_texture_format.hh"

namespace bw = blender::gpu::webgpu;

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

bool render_attachment_contract()
{
  enum FeatureMask : uint8_t {
    Unorm16 = 1u << 0,
    Tier1 = 1u << 1,
    Depth32Stencil8 = 1u << 2,
    RG11B10 = 1u << 3,
  };
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
    bw::RenderAttachmentFeatures features;
    features.unorm16_texture_formats = (test.features & Unorm16) != 0;
    features.texture_formats_tier1 = (test.features & Tier1) != 0;
    features.depth32_float_stencil8 = (test.features & Depth32Stencil8) != 0;
    features.rg11b10_ufloat_renderable = (test.features & RG11B10) != 0;
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

}  // namespace

int main()
{
  if (!table_contract() || !capabilities_contract() || !render_attachment_contract() ||
      !view_format_contract() || !promotion_contract() || !rgb9e5_contract() ||
      !rg11b10_contract() || !boundary_contract())
  {
    return 1;
  }
  std::printf(
      "INTEGRATED_TEXTURE_PASS contracts=8 formats=63 promotions=13 view_pairs=10 rgb9e5=10 "
      "rg11b10=25\n");
  return 0;
}
