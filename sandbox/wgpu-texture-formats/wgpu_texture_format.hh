/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * M3.T9.pre — WebGPU texture-format table (standalone, drop-in for
 * `source/blender/gpu/webgpu/wgpu_texture_format.cc`).
 *
 * Maps Blender's `gpu::TextureFormat` (every value at the pin) to
 * `wgpu::TextureFormat`, plus capability flags {renderable, filterable, storage,
 * blendable, multisample}, a conversion class, and a device feature gate.
 *
 * SOURCE OF TRUTH (read-only recon): `upstream/source/blender/gpu/GPU_format.hh`
 * — an X-macro table carrying, per format, {C-type, byte-size, channel-count,
 * blender enum, VkFormat, MTLPixelFormat, MTLVertexFormat, GL enum, shader enum}.
 * The enum set is `GPU_TEXTURE_FORMAT_EXPAND` in `GPU_texture.hh:45-124`. The
 * Vulkan backend's equivalent mapping (the model) is
 * `vulkan/vk_common.cc::to_vk_format` (a big switch over `TextureFormat::…`).
 *
 * KEY STRUCTURE (see notes/gpu-t9pre-findings.md):
 *   - WebGPU, like Metal, has NO 3-channel texture formats. The 13 three-channel
 *     Blender formats are PROMOTED to their 4-channel sibling with an RGB→RGBA
 *     data conversion on upload (GPU_format.hh already aliases them to RGBA in the
 *     MTLPixelFormat column, e.g. UNORM_8_8_8 → RGBA8Unorm). See
 *     wgpu_data_conversion.{hh,cc}.
 *   - All other formats map directly. 3 gates: BC/DXT compression
 *     (texture-compression-bc), Depth32FloatStencil8 (its own feature), and the
 *     non-core 16-bit UNORM/SNORM formats (adapter-dependent). Every Blender
 *     format has SOME WebGPU target — none is unmappable, only feature-gated. */

#pragma once

#include <cstdint>

#include "webgpu/webgpu_cpp.h"

namespace blender::gpu::webgpu {

/** Mirror of `blender::gpu::TextureFormat` (GPU_texture.hh:40). Same member names
 * and order as `GPU_TEXTURE_FORMAT_EXPAND`, so the in-tree drop-in keys on the
 * real enum 1:1. Values here are local ordinals (not the upstream DataFormat
 * ordinals) — only the mapping matters. */
enum class TextureFormat : uint8_t {
  Invalid = 0,
#define WGPU_FMT(name, bytes, comps, wgpu_fmt, conv, gate) name,
#include "wgpu_texture_format_list.h"
#undef WGPU_FMT
};

/** How the pixel bytes must be transformed before upload / after readback. */
enum class ConvClass : uint8_t {
  Direct,        /* memcpy; src layout == wgpu layout (incl. 32-bit packed). */
  PromoteRGBA,   /* 3-channel → 4-channel sibling; add opaque alpha (RGB→RGBA). */
  Depth,         /* depth/stencil aspect; restricted copy semantics. */
  Compressed,    /* block-compressed (BC); block-aligned copy. */
};

/** Optional device feature a format needs to be creatable/usable. */
enum class FeatureGate : uint8_t {
  None,
  TextureCompressionBC,   /* BC1/2/3 (DXT). */
  Depth32FloatStencil8,   /* SFLOAT_32_DEPTH_UINT_8. */
  Unorm16,                /* non-core R/RG/RGBA 16-bit UNORM (feature Unorm16TextureFormats). */
  Snorm16,                /* 16-bit SNORM: NO WebGPU/Dawn support at the pin — must emulate. */
  Float32Filterable,      /* filtering of 32-bit float formats (cap only, not creatability). */
  RG11B10UfloatRenderable,/* render-target use of RG11B10Ufloat (cap only). */
};

/** WebGPU capability bits for a format (spec-derived; the harness validates the
 * creation-observable ones: renderable/storage/multisample + round-trip). */
struct FormatCaps {
  bool renderable = false;   /* usable as a color/depth RENDER_ATTACHMENT. */
  bool filterable = false;   /* a Filtering sampler may sample it. */
  bool storage = false;      /* usable as a STORAGE_BINDING (write-only baseline). */
  bool blendable = false;    /* supports fixed-function blending as a color target. */
  bool multisample = false;  /* supports sampleCount > 1. */
};

struct FormatInfo {
  TextureFormat blender;
  const char *name;               /* blender enum spelling */
  uint32_t src_bytes_per_pixel;   /* Blender's source bpp (GPU_format.hh size col) */
  uint8_t src_components;         /* 1..4 (GPU_format.hh comps col) */
  wgpu::TextureFormat wgpu;       /* the actual texture format created on the device */
  ConvClass conv;
  FeatureGate gate;
  FormatCaps caps;
};

/** Look up the full record for a Blender format. */
const FormatInfo &format_info(TextureFormat format);

/** The WebGPU texture format the backend creates for a Blender format (promotion
 * applied — a 3-channel format returns its 4-channel target). */
wgpu::TextureFormat to_wgpu_format(TextureFormat format);

/** Iterate the whole table (for the harness / reflection). */
const FormatInfo *format_table(size_t &count);

/** Spec capability classification from a wgpu::TextureFormat (used to fill
 * FormatInfo::caps; exposed for the harness cross-check). */
FormatCaps caps_of(wgpu::TextureFormat wgpu);

const char *to_string(ConvClass c);
const char *to_string(FeatureGate g);

}  // namespace blender::gpu::webgpu
