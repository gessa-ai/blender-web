/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <vector>

/* The helpers under test intentionally have internal linkage. Including the
 * canonical translation unit keeps this contract on the shipping code instead
 * of copying the signed-I10 conversion into a test-only implementation. */
#include "wgpu_vertex_buffer.cc"

namespace blender::gpu {
namespace {

bool require(const bool condition, const char *message)
{
  if (!condition) {
    std::fprintf(stderr, "FAIL: %s\n", message);
    return false;
  }
  return true;
}

uint32_t pack_i10(const uint32_t x, const uint32_t y, const uint32_t z, const uint32_t w)
{
  return (x & 0x3ffu) | ((y & 0x3ffu) << 10) | ((z & 0x3ffu) << 20) |
         ((w & 0x3u) << 30);
}

void store_u32(uint8_t *dst, const uint32_t value)
{
  dst[0] = uint8_t(value);
  dst[1] = uint8_t(value >> 8);
  dst[2] = uint8_t(value >> 16);
  dst[3] = uint8_t(value >> 24);
}

uint8_t expected_component(const uint32_t bits)
{
  int value = int(bits & 0x3ffu);
  if (value & 0x200) {
    value -= 1024;
  }
  value = std::max(value, -511);
  const int magnitude = (std::abs(value) * 127 + 255) / 511;
  const int result = value < 0 ? -magnitude : magnitude;
  return uint8_t(int8_t(result));
}

uint8_t expected_w(const uint32_t bits)
{
  constexpr std::array<int8_t, 4> expected = {0, 127, -127, -127};
  return uint8_t(expected[bits & 0x3u]);
}

GPUVertFormat make_format(const std::initializer_list<gpu::VertAttrType> types,
                          const uint stride,
                          const bool deinterleaved)
{
  GPUVertFormat format{};
  format.attr_len = uint(types.size());
  format.stride = stride;
  format.packed = true;
  format.deinterleaved = deinterleaved;
  uint index = 0;
  uint offset = 0;
  for (const gpu::VertAttrType type : types) {
    format.attrs[index].type.format = type;
    format.attrs[index].offset = uint8_t(offset);
    offset += uint(format.attrs[index].type.size());
    index++;
  }
  return format;
}

bool component_contract()
{
  int minimum = 127;
  int maximum = -127;
  int previous = -128;
  for (uint32_t bits = 0; bits < 1024; bits++) {
    const uint8_t actual = uint8_t(i10_component_to_snorm8(bits));
    if (!require(actual == expected_component(bits), "exhaustive signed-I10 component mapping")) {
      return false;
    }
    const int signed_value = int(int8_t(actual));
    minimum = std::min(minimum, signed_value);
    maximum = std::max(maximum, signed_value);
    if (bits < 512) {
      if (!require(signed_value >= previous, "positive signed-I10 mapping is monotonic")) {
        return false;
      }
      previous = signed_value;
    }
  }
  if (!require(minimum == -127 && maximum == 127, "signed-I10 output range")) {
    return false;
  }
  std::puts("CONTRACT component PASS cases=1024 range=-127:127");
  return true;
}

bool detection_contract()
{
  GPUVertFormat format{};
  if (!require(!format_has_norm_i10(format), "empty format has no signed-I10 attribute")) {
    return false;
  }
  format = make_format({gpu::VertAttrType::SFLOAT_32}, 4, false);
  if (!require(!format_has_norm_i10(format), "float format has no signed-I10 attribute")) {
    return false;
  }
  format = make_format({gpu::VertAttrType::UNORM_10_10_10_2}, 4, false);
  if (!require(format_has_norm_i10(format),
               "legacy normalized-I10 alias follows the signed backend path"))
  {
    return false;
  }
  for (uint signed_index = 0; signed_index < GPU_VERT_ATTR_MAX_LEN; signed_index++) {
    format = GPUVertFormat{};
    format.attr_len = GPU_VERT_ATTR_MAX_LEN;
    for (uint index = 0; index < GPU_VERT_ATTR_MAX_LEN; index++) {
      format.attrs[index].type.format = index == signed_index ?
                                            gpu::VertAttrType::SNORM_10_10_10_2 :
                                            gpu::VertAttrType::SFLOAT_32;
    }
    if (!require(format_has_norm_i10(format), "signed-I10 detection at every attribute slot")) {
      return false;
    }
  }
  std::puts("CONTRACT detection PASS cases=19 slots=16 legacy-alias=1");
  return true;
}

bool interleaved_contract()
{
  constexpr uint vertex_len = 1024;
  constexpr size_t stride = 12;
  GPUVertFormat format = make_format({gpu::VertAttrType::UINT_32,
                                      gpu::VertAttrType::SNORM_10_10_10_2,
                                      gpu::VertAttrType::UNORM_8_8_8_8},
                                     stride,
                                     false);
  std::vector<uint8_t> bytes(vertex_len * stride);
  for (uint32_t vertex = 0; vertex < vertex_len; vertex++) {
    uint8_t *row = bytes.data() + size_t(vertex) * stride;
    store_u32(row, 0xa5000000u | vertex);
    store_u32(row + 4,
              pack_i10(vertex, 1023u - vertex, vertex * 37u + 13u, vertex));
    store_u32(row + 8, 0x5a000000u | (vertex * 17u));
  }
  const std::vector<uint8_t> before = bytes;
  transcode_i10_attrs(bytes.data(), bytes.size(), format, vertex_len);
  for (uint32_t vertex = 0; vertex < vertex_len; vertex++) {
    const size_t base = size_t(vertex) * stride;
    if (!require(std::memcmp(bytes.data() + base, before.data() + base, 4) == 0,
                 "interleaved leading attribute preserved") ||
        !require(std::memcmp(bytes.data() + base + 8, before.data() + base + 8, 4) == 0,
                 "interleaved non-I10 attribute preserved"))
    {
      return false;
    }
    const std::array<uint8_t, 4> expected = {
        expected_component(vertex),
        expected_component(1023u - vertex),
        expected_component(vertex * 37u + 13u),
        expected_w(vertex),
    };
    if (!require(std::memcmp(bytes.data() + base + 4, expected.data(), expected.size()) == 0,
                 "interleaved signed-I10 field transcode"))
    {
      return false;
    }
  }
  std::puts("CONTRACT interleaved PASS vertices=1024 fields=1024 preserved=8192");
  return true;
}

bool deinterleaved_contract()
{
  constexpr uint vertex_len = 17;
  constexpr size_t first_normal_base = size_t(vertex_len) * 8;
  constexpr size_t middle_base = first_normal_base + size_t(vertex_len) * 4;
  constexpr size_t second_normal_base = middle_base + size_t(vertex_len) * 4;
  constexpr size_t byte_count = second_normal_base + size_t(vertex_len) * 4;
  GPUVertFormat format = make_format({gpu::VertAttrType::SFLOAT_32_32,
                                      gpu::VertAttrType::SNORM_10_10_10_2,
                                      gpu::VertAttrType::UINT_32,
                                      gpu::VertAttrType::SNORM_10_10_10_2},
                                     20,
                                     true);
  std::vector<uint8_t> bytes(byte_count, 0x5a);
  for (uint32_t vertex = 0; vertex < vertex_len; vertex++) {
    store_u32(bytes.data() + first_normal_base + size_t(vertex) * 4,
              pack_i10(vertex * 61u, vertex * 17u, 1023u - vertex, vertex));
    store_u32(bytes.data() + second_normal_base + size_t(vertex) * 4,
              pack_i10(511u - vertex, 512u + vertex, vertex * 29u, 3u - vertex));
  }
  const std::vector<uint8_t> before = bytes;
  transcode_i10_attrs(bytes.data(), bytes.size(), format, vertex_len);
  if (!require(std::memcmp(bytes.data(), before.data(), first_normal_base) == 0,
               "deinterleaved leading block preserved") ||
      !require(std::memcmp(bytes.data() + middle_base,
                           before.data() + middle_base,
                           size_t(vertex_len) * 4) == 0,
               "deinterleaved middle block preserved"))
  {
    return false;
  }
  for (uint32_t vertex = 0; vertex < vertex_len; vertex++) {
    const std::array<uint8_t, 4> first = {
        expected_component(vertex * 61u),
        expected_component(vertex * 17u),
        expected_component(1023u - vertex),
        expected_w(vertex),
    };
    const std::array<uint8_t, 4> second = {
        expected_component(511u - vertex),
        expected_component(512u + vertex),
        expected_component(vertex * 29u),
        expected_w(3u - vertex),
    };
    if (!require(std::memcmp(bytes.data() + first_normal_base + size_t(vertex) * 4,
                             first.data(),
                             first.size()) == 0,
                 "first deinterleaved signed-I10 block") ||
        !require(std::memcmp(bytes.data() + second_normal_base + size_t(vertex) * 4,
                             second.data(),
                             second.size()) == 0,
                 "second deinterleaved signed-I10 block"))
    {
      return false;
    }
  }
  std::puts("CONTRACT deinterleaved PASS vertices=17 fields=34 preserved=204");
  return true;
}

bool bounds_contract()
{
  GPUVertFormat format = make_format({gpu::VertAttrType::SNORM_10_10_10_2}, 8, false);
  format.attrs[0].offset = 4;
  std::vector<uint8_t> bytes(24, 0xa5);
  store_u32(bytes.data() + 4, pack_i10(0, 511, 512, 2));
  store_u32(bytes.data() + 12, pack_i10(1, 2, 3, 1));
  const std::vector<uint8_t> before = bytes;
  transcode_i10_attrs(bytes.data(), 13, format, 3);
  const std::array<uint8_t, 4> expected = {
      expected_component(0), expected_component(511), expected_component(512), expected_w(2)};
  if (!require(std::memcmp(bytes.data() + 4, expected.data(), expected.size()) == 0,
               "last complete field before bound is transcoded") ||
      !require(std::memcmp(bytes.data() + 12, before.data() + 12, 12) == 0,
               "partial and out-of-range fields remain untouched"))
  {
    return false;
  }
  std::puts("CONTRACT bounds PASS nbytes=13 transformed=1 guarded=12");
  return true;
}

bool subrange_contract()
{
  constexpr uint interleaved_vertices = 8;
  constexpr size_t interleaved_stride = 12;
  GPUVertFormat interleaved = make_format({gpu::VertAttrType::UINT_32,
                                           gpu::VertAttrType::SNORM_10_10_10_2,
                                           gpu::VertAttrType::UNORM_8_8_8_8},
                                          interleaved_stride,
                                          false);
  std::vector<uint8_t> interleaved_source(interleaved_vertices * interleaved_stride, 0x5a);
  for (uint vertex = 0; vertex < interleaved_vertices; vertex++) {
    store_u32(interleaved_source.data() + size_t(vertex) * interleaved_stride + 4,
              pack_i10(vertex * 73u, 1023u - vertex * 31u, vertex * 19u, vertex));
  }
  std::vector<uint8_t> interleaved_expected = interleaved_source;
  transcode_i10_attrs(
      interleaved_expected.data(), interleaved_expected.size(), interleaved, interleaved_vertices);
  constexpr size_t interleaved_start = interleaved_stride + 4;
  constexpr size_t interleaved_length = 40;
  std::vector<uint8_t> interleaved_payload(
      interleaved_source.begin() + interleaved_start,
      interleaved_source.begin() + interleaved_start + interleaved_length);
  if (!require(transcode_i10_update_payload(interleaved_payload.data(),
                                            interleaved_payload.size(),
                                            interleaved_start,
                                            interleaved,
                                            interleaved_vertices),
               "interleaved signed-I10 subrange accepted") ||
      !require(std::memcmp(interleaved_payload.data(),
                           interleaved_expected.data() + interleaved_start,
                           interleaved_payload.size()) == 0,
               "interleaved signed-I10 subrange conversion"))
  {
    return false;
  }

  constexpr uint deinterleaved_vertices = 7;
  GPUVertFormat deinterleaved = make_format({gpu::VertAttrType::SFLOAT_32_32,
                                             gpu::VertAttrType::SNORM_10_10_10_2,
                                             gpu::VertAttrType::UINT_32,
                                             gpu::VertAttrType::SNORM_10_10_10_2},
                                            20,
                                            true);
  std::vector<uint8_t> deinterleaved_source(size_t(deinterleaved_vertices) * 20, 0xa5);
  constexpr size_t first_i10_base = size_t(deinterleaved_vertices) * 8;
  constexpr size_t second_i10_base = first_i10_base + size_t(deinterleaved_vertices) * 8;
  for (uint vertex = 0; vertex < deinterleaved_vertices; vertex++) {
    store_u32(deinterleaved_source.data() + first_i10_base + size_t(vertex) * 4,
              pack_i10(vertex * 41u, 511u - vertex, 512u + vertex, vertex));
    store_u32(deinterleaved_source.data() + second_i10_base + size_t(vertex) * 4,
              pack_i10(1023u - vertex * 17u, vertex * 29u, vertex * 67u, 3u - vertex));
  }
  std::vector<uint8_t> deinterleaved_expected = deinterleaved_source;
  transcode_i10_attrs(deinterleaved_expected.data(),
                      deinterleaved_expected.size(),
                      deinterleaved,
                      deinterleaved_vertices);
  auto verify_deinterleaved = [&](const size_t start,
                                  const size_t length,
                                  const char *accepted_message,
                                  const char *conversion_message) {
    std::vector<uint8_t> payload(deinterleaved_source.begin() + start,
                                 deinterleaved_source.begin() + start + length);
    return require(transcode_i10_update_payload(payload.data(),
                                                payload.size(),
                                                start,
                                                deinterleaved,
                                                deinterleaved_vertices),
                   accepted_message) &&
           require(std::memcmp(payload.data(),
                               deinterleaved_expected.data() + start,
                               payload.size()) == 0,
                   conversion_message);
  };
  if (!verify_deinterleaved(first_i10_base + 8,
                            12,
                            "first deinterleaved signed-I10 subrange accepted",
                            "first deinterleaved signed-I10 subrange conversion") ||
      !verify_deinterleaved(second_i10_base + 4,
                            20,
                            "second deinterleaved signed-I10 subrange accepted",
                            "second deinterleaved signed-I10 subrange conversion"))
  {
    return false;
  }

  std::vector<uint8_t> full_payload = interleaved_source;
  if (!require(transcode_i10_update_payload(full_payload.data(),
                                            full_payload.size(),
                                            0,
                                            interleaved,
                                            interleaved_vertices),
               "whole signed-I10 update accepted") ||
      !require(full_payload == interleaved_expected,
               "whole signed-I10 update matches initial upload conversion"))
  {
    return false;
  }

  auto require_rejected_unchanged = [&](const size_t start,
                                        const size_t length,
                                        const char *message) {
    std::vector<uint8_t> payload(interleaved_source.begin() + start,
                                 interleaved_source.begin() + start + length);
    const std::vector<uint8_t> before = payload;
    return require(!transcode_i10_update_payload(
                       payload.data(), payload.size(), start, interleaved, interleaved_vertices),
                   message) &&
           require(payload == before, "rejected signed-I10 update remains atomic");
  };
  if (!require_rejected_unchanged(17, 4, "leading partial signed-I10 field rejected") ||
      !require_rejected_unchanged(16, 3, "trailing partial signed-I10 field rejected") ||
      !require_rejected_unchanged(16, 15, "complete-then-partial signed-I10 range rejected"))
  {
    return false;
  }

  GPUVertFormat huge = make_format({gpu::VertAttrType::SNORM_10_10_10_2}, 4, false);
  std::array<uint8_t, 4> huge_payload{};
  store_u32(huge_payload.data(), pack_i10(511, 512, 1023, 1));
  std::array<uint8_t, 4> huge_expected = huge_payload;
  transcode_i10_attrs(huge_expected.data(), huge_expected.size(), huge, UINT32_MAX);
  if (!require(transcode_i10_update_payload(
                   huge_payload.data(), huge_payload.size(), 0, huge, UINT32_MAX),
               "constant-work signed-I10 update accepted at maximum vertex census") ||
      !require(huge_payload == huge_expected,
               "constant-work signed-I10 update conversion at maximum vertex census"))
  {
    return false;
  }

  std::array<uint8_t, 4> overflow_payload = {1, 2, 3, 4};
  const std::array<uint8_t, 4> overflow_before = overflow_payload;
  if (!require(!transcode_i10_update_payload(overflow_payload.data(),
                                             overflow_payload.size(),
                                             SIZE_MAX - 1,
                                             interleaved,
                                             interleaved_vertices),
               "overflowing signed-I10 update range rejected") ||
      !require(overflow_payload == overflow_before, "overflow rejection remains atomic"))
  {
    return false;
  }

  GPUVertFormat plain = make_format({gpu::VertAttrType::SFLOAT_32_32}, 8, false);
  std::array<uint8_t, 8> plain_payload = {0, 1, 2, 3, 4, 5, 6, 7};
  const std::array<uint8_t, 8> plain_before = plain_payload;
  if (!require(transcode_i10_update_payload(
                   plain_payload.data(), plain_payload.size(), 0, plain, 1),
               "non-I10 update accepted") ||
      !require(plain_payload == plain_before, "non-I10 update preserved") ||
      !require(transcode_i10_update_payload(
                   interleaved_payload.data(), 0, 16, interleaved, interleaved_vertices),
               "empty signed-I10 update accepted"))
  {
    return false;
  }

  std::puts("CONTRACT subrange PASS cases=11 fields=21 rejected=4 max_vertices=4294967295");
  return true;
}

bool usage_contract()
{
  constexpr std::array<webgpu::UsageType, 4> expected = {
      webgpu::UsageType::Stream,
      webgpu::UsageType::Static,
      webgpu::UsageType::Dynamic,
      webgpu::UsageType::DeviceOnly,
  };
  size_t cases = 0;
  for (uint flag = 0; flag <= uint(GPU_USAGE_FLAG_BUFFER_TEXTURE_ONLY); flag += 8) {
    for (uint base = 0; base < expected.size(); base++) {
      const auto usage = GPUUsageType(base | flag);
      if (!require(to_wgpu_usage(usage) == expected[base], "vertex usage low-bit mapping")) {
        return false;
      }
      cases++;
    }
  }
  if (!require(cases == 8, "vertex usage mapping census")) {
    return false;
  }
  std::puts("CONTRACT usage PASS cases=8 masked-flags=4");
  return true;
}

}  // namespace

int run_integrated_vertex_contracts()
{
  if (!component_contract() || !detection_contract() || !interleaved_contract() ||
      !deinterleaved_contract() || !bounds_contract() || !subrange_contract() ||
      !usage_contract())
  {
    return 1;
  }
  std::puts(
      "INTEGRATED_VERTEX_PASS contracts=7 components=1024 vertices=1041 fields=1080 usage=8");
  return 0;
}

}  // namespace blender::gpu

int main()
{
  return blender::gpu::run_integrated_vertex_contracts();
}
