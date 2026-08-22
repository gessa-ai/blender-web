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

#include "wgpu_pipeline.hh"

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

}  // namespace

int main()
{
  if (!primitive_topology_contract() || !strip_index_format_contract() ||
      !format_32bit_contract() ||
      !format_subword_contract() || !format_i10_contract())
  {
    return 1;
  }
  std::puts(
      "INTEGRATED_PIPELINE_PASS contracts=5 primitives=11 strip_cases=33 formats=96 i10=12");
  return 0;
}
