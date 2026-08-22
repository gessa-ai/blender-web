/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Device-free native/Wasm parity contract for the canonical in-tree WebGPU
 * render-pipeline enum mappings. No instance, adapter, device, or pipeline is
 * created; live descriptor validation remains part of the hardware-gated M3
 * replay. */

#include <array>
#include <cstdio>
#include <limits>
#include <unordered_set>

#ifndef BW_WGPU_PIPELINE_SOURCE
#  error "BW_WGPU_PIPELINE_SOURCE must name the canonical wgpu_pipeline.cc"
#endif

/* The dummy-binding helper intentionally has internal linkage. Including the
 * canonical translation unit keeps this contract on the shipping vertex plan. */
#include BW_WGPU_PIPELINE_SOURCE

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

bool primitive_topology_contract()
{
  using PT = wgpu::PrimitiveTopology;
  struct Expected {
    blender::GPUPrimType primitive;
    PT topology;
  };
  constexpr std::array<Expected, 11> expected = {{
      {blender::GPU_PRIM_POINTS, PT::PointList},
      {blender::GPU_PRIM_LINES, PT::LineList},
      {blender::GPU_PRIM_TRIS, PT::TriangleList},
      {blender::GPU_PRIM_LINE_STRIP, PT::LineStrip},
      {blender::GPU_PRIM_LINE_LOOP, PT::LineStrip},
      {blender::GPU_PRIM_TRI_STRIP, PT::TriangleStrip},
      {blender::GPU_PRIM_TRI_FAN, PT::TriangleList},
      {blender::GPU_PRIM_LINES_ADJ, PT::TriangleList},
      {blender::GPU_PRIM_TRIS_ADJ, PT::TriangleList},
      {blender::GPU_PRIM_LINE_STRIP_ADJ, PT::TriangleList},
      {blender::GPU_PRIM_NONE, PT::TriangleList},
  }};

  for (const Expected &row : expected) {
    if (!require(bw::to_wgpu_topology(row.primitive) == row.topology,
                 "primitive topology mapping"))
    {
      return false;
    }
  }
  std::puts("CONTRACT primitive_topology PASS cases=11");
  return true;
}

bool strip_index_format_contract()
{
  using IF = wgpu::IndexFormat;
  constexpr std::array primitives = {
      blender::GPU_PRIM_POINTS,
      blender::GPU_PRIM_LINES,
      blender::GPU_PRIM_TRIS,
      blender::GPU_PRIM_LINE_STRIP,
      blender::GPU_PRIM_LINE_LOOP,
      blender::GPU_PRIM_TRI_STRIP,
      blender::GPU_PRIM_TRI_FAN,
      blender::GPU_PRIM_LINES_ADJ,
      blender::GPU_PRIM_TRIS_ADJ,
      blender::GPU_PRIM_LINE_STRIP_ADJ,
      blender::GPU_PRIM_NONE,
  };
  constexpr std::array index_formats = {IF::Undefined, IF::Uint16, IF::Uint32};

  size_t cases = 0;
  size_t selected = 0;
  for (const blender::GPUPrimType primitive : primitives) {
    const bool is_strip = primitive == blender::GPU_PRIM_LINE_STRIP ||
                          primitive == blender::GPU_PRIM_LINE_LOOP ||
                          primitive == blender::GPU_PRIM_TRI_STRIP;
    for (const IF index_format : index_formats) {
      const IF expected = is_strip ? index_format : IF::Undefined;
      if (!require(bw::to_wgpu_strip_index_format(primitive, index_format) == expected,
                   "strip index-format mapping"))
      {
        return false;
      }
      cases++;
      selected += expected != IF::Undefined ? 1 : 0;
    }
  }
  if (!require(cases == 33, "strip index-format census") ||
      !require(selected == 6, "selected strip index-format census"))
  {
    return false;
  }
  std::puts("CONTRACT strip_index_format PASS cases=33 selected=6");
  return true;
}

bool indirect_draw_span_contract()
{
  struct Case {
    int count;
    intptr_t offset;
    intptr_t stride;
    bool indexed;
    uint64_t buffer_size;
    bool accepted;
    uint64_t first_offset;
    uint64_t command_stride;
    uint64_t command_size;
    uint64_t end_offset;
  };
  constexpr intptr_t aligned_intptr_max =
      std::numeric_limits<intptr_t>::max() & ~intptr_t(3);
  constexpr std::array<Case, 19> cases = {{
      {1, 0, 0, false, 16, true, 0, 16, 16, 16},
      {1, 4, 0, true, 24, true, 4, 20, 20, 24},
      {3, 8, 0, false, 56, true, 8, 16, 16, 56},
      {3, 4, 32, true, 88, true, 4, 32, 20, 88},
      {2, 4, 4, false, 24, true, 4, 4, 16, 24},
      {2, 0, 24, true, 44, true, 0, 24, 20, 44},
      {4, 16, 32, false, 128, true, 16, 32, 16, 128},
      {0, 0, 0, false, 16, false, 0, 0, 0, 0},
      {-1, 0, 0, false, 16, false, 0, 0, 0, 0},
      {1, -4, 0, false, 16, false, 0, 0, 0, 0},
      {2, 0, -4, false, 32, false, 0, 0, 0, 0},
      {1, 2, 0, false, 32, false, 0, 0, 0, 0},
      {2, 0, 2, false, 32, false, 0, 0, 0, 0},
      {1, 0, 0, false, 15, false, 0, 0, 0, 0},
      {1, 0, 0, true, 19, false, 0, 0, 0, 0},
      {1, 4, 0, false, 16, false, 0, 0, 0, 0},
      {2, 0, 0, false, 31, false, 0, 0, 0, 0},
      {2, 0, 24, true, 43, false, 0, 0, 0, 0},
      {std::numeric_limits<int>::max(),
       aligned_intptr_max,
       aligned_intptr_max,
       false,
       1024,
       false,
       0,
       0,
       0,
       0},
  }};

  size_t accepted = 0;
  size_t rejected = 0;
  uint64_t first_sum = 0;
  uint64_t stride_sum = 0;
  uint64_t end_sum = 0;
  for (const Case &test : cases) {
    bw::IndirectDrawSpan actual = {11, 12, 13, 14};
    const bw::IndirectDrawSpan sentinel = actual;
    const bool result = bw::indirect_draw_span(
        test.count, test.offset, test.stride, test.indexed, test.buffer_size, actual);
    if (!require(result == test.accepted, "indirect draw span decision")) {
      return false;
    }
    if (!result) {
      if (!require(actual.first_offset == sentinel.first_offset &&
                       actual.command_stride == sentinel.command_stride &&
                       actual.command_size == sentinel.command_size &&
                       actual.end_offset == sentinel.end_offset,
                   "rejected indirect draw span preserves output"))
      {
        return false;
      }
      rejected++;
      continue;
    }
    if (!require(actual.first_offset == test.first_offset &&
                     actual.command_stride == test.command_stride &&
                     actual.command_size == test.command_size &&
                     actual.end_offset == test.end_offset,
                 "accepted indirect draw span geometry"))
    {
      return false;
    }
    accepted++;
    first_sum += actual.first_offset;
    stride_sum += actual.command_stride;
    end_sum += actual.end_offset;
  }

  if (!require(accepted == 7 && rejected == 12, "indirect draw span census") ||
      !require(first_sum == 36 && stride_sum == 144 && end_sum == 380,
               "indirect draw span aggregate"))
  {
    return false;
  }
  std::puts("CONTRACT indirect_draw_span PASS cases=19 accepted=7 rejected=12 "
            "first_sum=36 stride_sum=144 end_sum=380");
  return true;
}

wgpu::VertexFormat expected_32bit_format(const blender::GPUVertCompType component,
                                         const int component_len)
{
  using VF = wgpu::VertexFormat;
  if (component == blender::GPU_COMP_F32) {
    constexpr std::array<VF, 4> formats = {
        VF::Float32, VF::Float32x2, VF::Float32x3, VF::Float32x4};
    return formats[size_t(component_len - 1)];
  }
  if (component == blender::GPU_COMP_I32) {
    constexpr std::array<VF, 4> formats = {
        VF::Sint32, VF::Sint32x2, VF::Sint32x3, VF::Sint32x4};
    return formats[size_t(component_len - 1)];
  }
  constexpr std::array<VF, 4> formats = {
      VF::Uint32, VF::Uint32x2, VF::Uint32x3, VF::Uint32x4};
  return formats[size_t(component_len - 1)];
}

bool format_32bit_contract()
{
  constexpr std::array components = {
      blender::GPU_COMP_F32, blender::GPU_COMP_I32, blender::GPU_COMP_U32};
  constexpr std::array fetch_modes = {blender::GPU_FETCH_FLOAT,
                                      blender::GPU_FETCH_INT,
                                      blender::GPU_FETCH_INT_TO_FLOAT_UNIT};
  size_t cases = 0;
  for (const blender::GPUVertCompType component : components) {
    for (int component_len = 1; component_len <= 4; component_len++) {
      for (const blender::GPUVertFetchMode fetch : fetch_modes) {
        if (!require(bw::to_wgpu_vertex_format(component, component_len, fetch) ==
                         expected_32bit_format(component, component_len),
                     "32-bit vertex format mapping"))
        {
          return false;
        }
        cases++;
      }
    }
  }
  if (!require(cases == 36, "32-bit vertex format census")) {
    return false;
  }
  std::puts("CONTRACT format_32bit PASS cases=36");
  return true;
}

wgpu::VertexFormat expected_subword_format(const blender::GPUVertCompType component,
                                           const int component_len,
                                           const bool normalized)
{
  using VF = wgpu::VertexFormat;
  const bool pair = component_len <= 2;
  switch (component) {
    case blender::GPU_COMP_I8:
      return normalized ? (pair ? VF::Snorm8x2 : VF::Snorm8x4) :
                          (pair ? VF::Sint8x2 : VF::Sint8x4);
    case blender::GPU_COMP_U8:
      return normalized ? (pair ? VF::Unorm8x2 : VF::Unorm8x4) :
                          (pair ? VF::Uint8x2 : VF::Uint8x4);
    case blender::GPU_COMP_I16:
      return normalized ? (pair ? VF::Snorm16x2 : VF::Snorm16x4) :
                          (pair ? VF::Sint16x2 : VF::Sint16x4);
    case blender::GPU_COMP_U16:
      return normalized ? (pair ? VF::Unorm16x2 : VF::Unorm16x4) :
                          (pair ? VF::Uint16x2 : VF::Uint16x4);
    default:
      return VF::Float32x4;
  }
}

bool format_subword_contract()
{
  constexpr std::array components = {blender::GPU_COMP_I8,
                                     blender::GPU_COMP_U8,
                                     blender::GPU_COMP_I16,
                                     blender::GPU_COMP_U16};
  constexpr std::array fetch_modes = {blender::GPU_FETCH_FLOAT,
                                      blender::GPU_FETCH_INT,
                                      blender::GPU_FETCH_INT_TO_FLOAT_UNIT};
  size_t cases = 0;
  for (const blender::GPUVertCompType component : components) {
    for (int component_len = 1; component_len <= 4; component_len++) {
      for (const blender::GPUVertFetchMode fetch : fetch_modes) {
        const bool normalized = fetch == blender::GPU_FETCH_INT_TO_FLOAT_UNIT;
        if (!require(bw::to_wgpu_vertex_format(component, component_len, fetch) ==
                         expected_subword_format(component, component_len, normalized),
                     "subword vertex format mapping"))
        {
          return false;
        }
        cases++;
      }
    }
  }
  if (!require(cases == 48, "subword vertex format census")) {
    return false;
  }
  std::puts("CONTRACT format_subword PASS cases=48");
  return true;
}

bool format_i10_contract()
{
  constexpr std::array fetch_modes = {blender::GPU_FETCH_FLOAT,
                                      blender::GPU_FETCH_INT,
                                      blender::GPU_FETCH_INT_TO_FLOAT_UNIT};
  size_t cases = 0;
  size_t signed_cases = 0;
  for (int component_len = 1; component_len <= 4; component_len++) {
    for (const blender::GPUVertFetchMode fetch : fetch_modes) {
      const bool normalized = fetch == blender::GPU_FETCH_INT_TO_FLOAT_UNIT;
      const wgpu::VertexFormat expected = normalized ? wgpu::VertexFormat::Snorm8x4 :
                                                       wgpu::VertexFormat::Unorm10_10_10_2;
      if (!require(bw::to_wgpu_vertex_format(blender::GPU_COMP_I10, component_len, fetch) ==
                       expected,
                   "signed I10 vertex format mapping"))
      {
        return false;
      }
      cases++;
      signed_cases += normalized ? 1 : 0;
    }
  }
  if (!require(cases == 12, "I10 vertex format census") ||
      !require(signed_cases == 4, "normalized I10 census"))
  {
    return false;
  }
  std::puts("CONTRACT format_i10 PASS cases=12 normalized=4");
  return true;
}

bool dummy_vertex_contract()
{
  using T = blender::gpu::shader::Type;
  using VF = wgpu::VertexFormat;
  struct Expected {
    T type;
    VF format;
  };
  constexpr std::array<Expected, 32> expected = {{
      {T::float_t, VF::Float32},
      {T::float2_t, VF::Float32x2},
      {T::float3_t, VF::Float32x3},
      {T::float4_t, VF::Float32x4},
      {T::float3x3_t, VF::Float32x4},
      {T::float4x4_t, VF::Float32x4},
      {T::uint_t, VF::Uint32},
      {T::uint2_t, VF::Uint32x2},
      {T::uint3_t, VF::Uint32x3},
      {T::uint4_t, VF::Uint32x4},
      {T::int_t, VF::Sint32},
      {T::int2_t, VF::Sint32x2},
      {T::int3_t, VF::Sint32x3},
      {T::int4_t, VF::Sint32x4},
      {T::bool_t, VF::Uint32},
      {T::float3_10_10_10_2_t, VF::Float32x3},
      {T::uchar_t, VF::Uint32},
      {T::uchar2_t, VF::Uint32x2},
      {T::uchar3_t, VF::Uint32x3},
      {T::uchar4_t, VF::Uint32x4},
      {T::char_t, VF::Sint32},
      {T::char2_t, VF::Sint32x2},
      {T::char3_t, VF::Sint32x3},
      {T::char4_t, VF::Sint32x4},
      {T::ushort_t, VF::Uint32},
      {T::ushort2_t, VF::Uint32x2},
      {T::ushort3_t, VF::Uint32x3},
      {T::ushort4_t, VF::Uint32x4},
      {T::short_t, VF::Sint32},
      {T::short2_t, VF::Sint32x2},
      {T::short3_t, VF::Sint32x3},
      {T::short4_t, VF::Sint32x4},
  }};

  for (size_t index = 0; index < expected.size(); index++) {
    const uint32_t location = uint32_t(index % 16);
    const bw::VertexBinding binding =
        bw::dummy_vertex_binding(location, uint8_t(expected[index].type));
    if (!require(binding.vbo_index == -1 && binding.is_dummy,
                 "dummy source identity") ||
        !require(binding.buffer_offset == 0, "dummy buffer offset") ||
        !require(binding.array_stride == 0, "dummy zero stride") ||
        !require(binding.step_mode == wgpu::VertexStepMode::Vertex,
                 "dummy vertex step mode") ||
        !require(binding.attributes.size() == 1, "dummy attribute count") ||
        !require(binding.attributes[0].format == expected[index].format,
                 "dummy attribute format") ||
        !require(binding.attributes[0].offset == 0, "dummy attribute offset") ||
        !require(binding.attributes[0].shaderLocation == location,
                 "dummy shader location"))
    {
      return false;
    }
  }

  std::puts("CONTRACT dummy_vertex PASS cases=32 stride=0 step=vertex");
  return true;
}

bool shader_lifetime_cache_contract()
{
  /* Reproduce allocator address reuse without constructing a device-backed shader:
   * the render-pipeline hash must distinguish successive lifetimes at one address. */
  auto *reused_address =
      reinterpret_cast<blender::gpu::WGPUShader *>(uintptr_t{0x1000});
  constexpr uint64_t identity_count = 4096;
  const auto identity_hash = [](const bw::PipelineInfo &info) {
    uint64_t hash = 1469598103934665603ull;
    bw::hash_shader_identity(hash, info.shader, info.shader_cache_identity);
    return hash;
  };
  std::unordered_set<uint64_t> hashes;
  hashes.reserve(identity_count);
  for (uint64_t identity = 1; identity <= identity_count; identity++) {
    const bw::PipelineInfo info(reused_address, identity);
    hashes.insert(identity_hash(info));
  }

  const bw::PipelineInfo first(reused_address, 1);
  const bw::PipelineInfo same_lifetime(reused_address, 1);
  const bw::PipelineInfo replacement(reused_address, 2);
  if (!require(identity_hash(first) == identity_hash(same_lifetime),
               "same shader lifetime cache identity") ||
      !require(identity_hash(first) != identity_hash(replacement),
               "reused shader address cache separation") ||
      !require(hashes.size() == identity_count, "shader lifetime hash census"))
  {
    return false;
  }

  std::puts("CONTRACT shader_lifetime_cache PASS cases=4096 unique=4096");
  return true;
}

bool vertex_alias_cache_key_contract()
{
  /* Attribute aliases participate in shader-location matching. Distinct valid alias
   * sequences must therefore remain distinct in the render-pipeline cache key, even
   * when their bytes concatenate to the same undelimited string. */
  blender::GPUVertFormat split_after_first{};
  blender::GPU_vertformat_clear(&split_after_first);
  blender::GPU_vertformat_attr_add(
      &split_after_first, "a", blender::gpu::VertAttrType::SFLOAT_32);
  blender::GPU_vertformat_alias_add(&split_after_first, "bc");
  split_after_first.pack();

  blender::GPUVertFormat split_after_second{};
  blender::GPU_vertformat_clear(&split_after_second);
  blender::GPU_vertformat_attr_add(
      &split_after_second, "ab", blender::gpu::VertAttrType::SFLOAT_32);
  blender::GPU_vertformat_alias_add(&split_after_second, "c");
  split_after_second.pack();

  auto *shader = reinterpret_cast<blender::gpu::WGPUShader *>(uintptr_t{0x2000});
  bw::PipelineInfo first(shader, 1);
  first.vertex_formats[0] = &split_after_first;
  first.vertex_lens[0] = 1;
  first.vertex_formats_len = 1;
  bw::PipelineInfo second(shader, 1);
  second.vertex_formats[0] = &split_after_second;
  second.vertex_lens[0] = 1;
  second.vertex_formats_len = 1;

  const blender::GPUVertAttr &first_attr = split_after_first.attrs[0];
  const blender::GPUVertAttr &second_attr = split_after_second.attrs[0];
  const char *first_name = blender::GPU_vertformat_attr_name_get(
      &split_after_first, &first_attr, 0);
  const char *first_alias = blender::GPU_vertformat_attr_name_get(
      &split_after_first, &first_attr, 1);
  const char *second_name = blender::GPU_vertformat_attr_name_get(
      &split_after_second, &second_attr, 0);
  const char *second_alias = blender::GPU_vertformat_attr_name_get(
      &split_after_second, &second_attr, 1);
  if (!require(split_after_first.attrs[0].name_len == 2 &&
                   split_after_second.attrs[0].name_len == 2,
               "vertex alias-list census") ||
      !require(first_attr.type.format == second_attr.type.format &&
                   first_attr.offset == second_attr.offset &&
                   split_after_first.stride == split_after_second.stride,
               "vertex alias layouts otherwise match") ||
      !require(std::strcmp(first_name, "a") == 0 && std::strcmp(first_alias, "bc") == 0 &&
                   std::strcmp(second_name, "ab") == 0 && std::strcmp(second_alias, "c") == 0,
               "vertex alias collision inputs") ||
      !require(bw::pipeline_hash(first) != bw::pipeline_hash(second),
               "vertex alias-list cache separation"))
  {
    return false;
  }

  std::puts("CONTRACT vertex_alias_cache_key PASS cases=2 aliases=4 unique=2");
  return true;
}

}  // namespace

int main()
{
  if (!primitive_topology_contract() || !strip_index_format_contract() ||
      !indirect_draw_span_contract() ||
      !format_32bit_contract() ||
      !format_subword_contract() || !format_i10_contract() || !dummy_vertex_contract() ||
      !shader_lifetime_cache_contract() || !vertex_alias_cache_key_contract())
  {
    return 1;
  }
  std::puts(
      "INTEGRATED_PIPELINE_PASS contracts=9 primitives=11 strip_cases=33 indirect_spans=19 "
      "formats=96 i10=12 dummy=32 shader_lifetimes=4096 alias_keys=2");
  return 0;
}
