/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Blender→WebGPU texture-format table + spec capability classification.
 * See wgpu_texture_format.hh. Data provenance: GPU_format.hh @ the pin. */

#include "wgpu_texture_format.hh"

namespace blender::gpu::webgpu {

using F = wgpu::TextureFormat;

/* ---- Spec capability predicates (WebGPU core §"Texture Format Capabilities") -
 * The live harness DISCOVERS renderable/storage/multisample via CreateTexture and
 * cross-checks these; filterable/blendable are pipeline-level and stay spec-only. */

static bool is_color_renderable(F f)
{
  switch (f) {
    case F::R8Unorm: case F::RG8Unorm: case F::RGBA8Unorm: case F::RGBA8UnormSrgb:
    case F::R8Uint: case F::RG8Uint: case F::RGBA8Uint:
    case F::R8Sint: case F::RG8Sint: case F::RGBA8Sint:
    case F::R16Uint: case F::RG16Uint: case F::RGBA16Uint:
    case F::R16Sint: case F::RG16Sint: case F::RGBA16Sint:
    case F::R16Float: case F::RG16Float: case F::RGBA16Float:
    case F::R32Uint: case F::RG32Uint: case F::RGBA32Uint:
    case F::R32Sint: case F::RG32Sint: case F::RGBA32Sint:
    case F::R32Float: case F::RG32Float: case F::RGBA32Float:
    case F::RGB10A2Unorm: case F::RGB10A2Uint:
    case F::RG11B10Ufloat: /* only with RG11B10UfloatRenderable */
      return true;
    default:
      return false;
  }
}

static bool is_depth(F f)
{
  return f == F::Depth16Unorm || f == F::Depth32Float || f == F::Depth32FloatStencil8 ||
         f == F::Depth24Plus || f == F::Depth24PlusStencil8;
}

static bool is_uint_or_sint(F f)
{
  switch (f) {
    case F::R8Uint: case F::RG8Uint: case F::RGBA8Uint:
    case F::R16Uint: case F::RG16Uint: case F::RGBA16Uint:
    case F::R32Uint: case F::RG32Uint: case F::RGBA32Uint:
    case F::R8Sint: case F::RG8Sint: case F::RGBA8Sint:
    case F::R16Sint: case F::RG16Sint: case F::RGBA16Sint:
    case F::R32Sint: case F::RG32Sint: case F::RGBA32Sint:
    case F::RGB10A2Uint:
      return true;
    default:
      return false;
  }
}

static bool is_storage(F f)
{
  switch (f) {
    case F::RGBA8Unorm: case F::RGBA8Snorm: case F::RGBA8Uint: case F::RGBA8Sint:
    case F::RGBA16Uint: case F::RGBA16Sint: case F::RGBA16Float:
    case F::R32Uint: case F::R32Sint: case F::R32Float:
    case F::RG32Uint: case F::RG32Sint: case F::RG32Float:
    case F::RGBA32Uint: case F::RGBA32Sint: case F::RGBA32Float:
      return true;
    default:
      return false;
  }
}

static bool is_filterable(F f)
{
  if (is_uint_or_sint(f) || is_depth(f)) {
    return false;
  }
  /* 32-bit float only filterable with the Float32Filterable feature. */
  if (f == F::R32Float || f == F::RG32Float || f == F::RGBA32Float) {
    return false; /* baseline; caps_of upgrades if the feature is present */
  }
  return true; /* unorm/snorm/srgb/16-float/packed-float/rgb9e5/BC */
}

static bool is_blendable(F f)
{
  switch (f) {
    case F::R8Unorm: case F::RG8Unorm: case F::RGBA8Unorm: case F::RGBA8UnormSrgb:
    case F::R16Float: case F::RG16Float: case F::RGBA16Float:
    case F::RGB10A2Unorm: case F::RG11B10Ufloat:
      return true;
    default:
      return false;
  }
}

static bool is_multisample(F f)
{
  /* Renderable non-integer color + depth support sampleCount>1. */
  if (is_depth(f)) {
    return true;
  }
  return is_color_renderable(f) && !is_uint_or_sint(f);
}

FormatCaps caps_of(F f)
{
  FormatCaps c;
  c.renderable = is_color_renderable(f) || is_depth(f);
  c.filterable = is_filterable(f);
  c.storage = is_storage(f);
  c.blendable = is_blendable(f);
  c.multisample = is_multisample(f);
  return c;
}

/* ---- The table ------------------------------------------------------------- */

static const FormatInfo g_table[] = {
#define WGPU_FMT(name, bytes, comps, wgpu_fmt, conv, gate) \
  {TextureFormat::name, #name, bytes, comps, wgpu_fmt, conv, gate, {}},
#include "wgpu_texture_format_list.h"
#undef WGPU_FMT
};
static constexpr size_t g_table_count = sizeof(g_table) / sizeof(g_table[0]);

/* Fill caps once (can't do it in the aggregate initializer above). */
static const FormatInfo *build_table()
{
  static FormatInfo table[g_table_count];
  for (size_t i = 0; i < g_table_count; i++) {
    table[i] = g_table[i];
    table[i].caps = caps_of(table[i].wgpu);
  }
  return table;
}

const FormatInfo *format_table(size_t &count)
{
  static const FormatInfo *t = build_table();
  count = g_table_count;
  return t;
}

const FormatInfo &format_info(TextureFormat format)
{
  size_t count = 0;
  const FormatInfo *t = format_table(count);
  for (size_t i = 0; i < count; i++) {
    if (t[i].blender == format) {
      return t[i];
    }
  }
  static const FormatInfo invalid = {
      TextureFormat::Invalid, "Invalid", 0, 0, wgpu::TextureFormat::Undefined,
      ConvClass::Direct, FeatureGate::None, {}};
  return invalid;
}

wgpu::TextureFormat to_wgpu_format(TextureFormat format)
{
  return format_info(format).wgpu;
}

const char *to_string(ConvClass c)
{
  switch (c) {
    case ConvClass::Direct: return "Direct";
    case ConvClass::PromoteRGBA: return "PromoteRGBA";
    case ConvClass::Depth: return "Depth";
    case ConvClass::Compressed: return "Compressed";
  }
  return "?";
}

const char *to_string(FeatureGate g)
{
  switch (g) {
    case FeatureGate::None: return "None";
    case FeatureGate::TextureCompressionBC: return "TextureCompressionBC";
    case FeatureGate::Depth32FloatStencil8: return "Depth32FloatStencil8";
    case FeatureGate::Unorm16: return "Unorm16TextureFormats";
    case FeatureGate::Snorm16: return "Snorm16(UNSUPPORTED-no WebGPU format)";
    case FeatureGate::Float32Filterable: return "Float32Filterable";
    case FeatureGate::RG11B10UfloatRenderable: return "RG11B10UfloatRenderable";
  }
  return "?";
}

}  // namespace blender::gpu::webgpu
