/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * The Blender `gpu::TextureFormat` → WebGPU mapping table, as an X-macro so it
 * generates both the enum and the lookup table from one source. Every row of
 * `GPU_TEXTURE_FORMAT_EXPAND` (upstream/source/blender/gpu/GPU_texture.hh:45-124)
 * is present. Data (byte-size, channel-count) is from GPU_format.hh @ the pin.
 *
 *   WGPU_FMT(blender_name, src_bytes_per_pixel, src_components, wgpu_format,
 *            ConvClass, FeatureGate)
 *
 * 3-channel rows map to their 4-channel WebGPU sibling with ConvClass::PromoteRGBA
 * (WebGPU has no 3-channel formats — same as Metal, which aliases them likewise).
 * Intentionally NOT a header guard: included multiple times with different
 * WGPU_FMT definitions. */

/* clang-format off */
/*        blender_name            bytes  comps  wgpu_format                              conv                    gate */

/* --- SNORM ------------------------------------------------------------------ */
WGPU_FMT(SNORM_8,                 1,     1,     wgpu::TextureFormat::R8Snorm,            ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(SNORM_8_8,               2,     2,     wgpu::TextureFormat::RG8Snorm,           ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(SNORM_8_8_8,             3,     3,     wgpu::TextureFormat::RGBA8Snorm,         ConvClass::PromoteRGBA, FeatureGate::None)
WGPU_FMT(SNORM_8_8_8_8,           4,     4,     wgpu::TextureFormat::RGBA8Snorm,         ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(SNORM_16,                2,     1,     wgpu::TextureFormat::R16Snorm,           ConvClass::Direct,      FeatureGate::Snorm16)
WGPU_FMT(SNORM_16_16,             4,     2,     wgpu::TextureFormat::RG16Snorm,          ConvClass::Direct,      FeatureGate::Snorm16)
WGPU_FMT(SNORM_16_16_16,          6,     3,     wgpu::TextureFormat::RGBA16Snorm,        ConvClass::PromoteRGBA, FeatureGate::Snorm16)
WGPU_FMT(SNORM_16_16_16_16,       8,     4,     wgpu::TextureFormat::RGBA16Snorm,        ConvClass::Direct,      FeatureGate::Snorm16)

/* --- UNORM ------------------------------------------------------------------ */
WGPU_FMT(UNORM_8,                 1,     1,     wgpu::TextureFormat::R8Unorm,            ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(UNORM_8_8,               2,     2,     wgpu::TextureFormat::RG8Unorm,           ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(UNORM_8_8_8,             3,     3,     wgpu::TextureFormat::RGBA8Unorm,         ConvClass::PromoteRGBA, FeatureGate::None)
WGPU_FMT(UNORM_8_8_8_8,           4,     4,     wgpu::TextureFormat::RGBA8Unorm,         ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(UNORM_16,                2,     1,     wgpu::TextureFormat::R16Unorm,           ConvClass::Direct,      FeatureGate::Unorm16)
WGPU_FMT(UNORM_16_16,             4,     2,     wgpu::TextureFormat::RG16Unorm,          ConvClass::Direct,      FeatureGate::Unorm16)
WGPU_FMT(UNORM_16_16_16,          6,     3,     wgpu::TextureFormat::RGBA16Unorm,        ConvClass::PromoteRGBA, FeatureGate::Unorm16)
WGPU_FMT(UNORM_16_16_16_16,       8,     4,     wgpu::TextureFormat::RGBA16Unorm,        ConvClass::Direct,      FeatureGate::Unorm16)

/* --- SINT ------------------------------------------------------------------- */
WGPU_FMT(SINT_8,                  1,     1,     wgpu::TextureFormat::R8Sint,             ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(SINT_8_8,                2,     2,     wgpu::TextureFormat::RG8Sint,            ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(SINT_8_8_8,              3,     3,     wgpu::TextureFormat::RGBA8Sint,          ConvClass::PromoteRGBA, FeatureGate::None)
WGPU_FMT(SINT_8_8_8_8,            4,     4,     wgpu::TextureFormat::RGBA8Sint,          ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(SINT_16,                 2,     1,     wgpu::TextureFormat::R16Sint,            ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(SINT_16_16,              4,     2,     wgpu::TextureFormat::RG16Sint,           ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(SINT_16_16_16,          6,     3,     wgpu::TextureFormat::RGBA16Sint,         ConvClass::PromoteRGBA, FeatureGate::None)
WGPU_FMT(SINT_16_16_16_16,        8,     4,     wgpu::TextureFormat::RGBA16Sint,         ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(SINT_32,                 4,     1,     wgpu::TextureFormat::R32Sint,            ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(SINT_32_32,              8,     2,     wgpu::TextureFormat::RG32Sint,           ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(SINT_32_32_32,          12,     3,     wgpu::TextureFormat::RGBA32Sint,         ConvClass::PromoteRGBA, FeatureGate::None)
WGPU_FMT(SINT_32_32_32_32,       16,     4,     wgpu::TextureFormat::RGBA32Sint,         ConvClass::Direct,      FeatureGate::None)

/* --- UINT ------------------------------------------------------------------- */
WGPU_FMT(UINT_8,                  1,     1,     wgpu::TextureFormat::R8Uint,             ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(UINT_8_8,                2,     2,     wgpu::TextureFormat::RG8Uint,            ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(UINT_8_8_8,              3,     3,     wgpu::TextureFormat::RGBA8Uint,          ConvClass::PromoteRGBA, FeatureGate::None)
WGPU_FMT(UINT_8_8_8_8,            4,     4,     wgpu::TextureFormat::RGBA8Uint,          ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(UINT_16,                 2,     1,     wgpu::TextureFormat::R16Uint,            ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(UINT_16_16,              4,     2,     wgpu::TextureFormat::RG16Uint,           ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(UINT_16_16_16,          6,     3,     wgpu::TextureFormat::RGBA16Uint,         ConvClass::PromoteRGBA, FeatureGate::None)
WGPU_FMT(UINT_16_16_16_16,        8,     4,     wgpu::TextureFormat::RGBA16Uint,         ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(UINT_32,                 4,     1,     wgpu::TextureFormat::R32Uint,            ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(UINT_32_32,              8,     2,     wgpu::TextureFormat::RG32Uint,           ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(UINT_32_32_32,          12,     3,     wgpu::TextureFormat::RGBA32Uint,         ConvClass::PromoteRGBA, FeatureGate::None)
WGPU_FMT(UINT_32_32_32_32,       16,     4,     wgpu::TextureFormat::RGBA32Uint,         ConvClass::Direct,      FeatureGate::None)

/* --- SFLOAT ----------------------------------------------------------------- */
WGPU_FMT(SFLOAT_16,               2,     1,     wgpu::TextureFormat::R16Float,           ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(SFLOAT_16_16,            4,     2,     wgpu::TextureFormat::RG16Float,          ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(SFLOAT_16_16_16,        6,     3,     wgpu::TextureFormat::RGBA16Float,        ConvClass::PromoteRGBA, FeatureGate::None)
WGPU_FMT(SFLOAT_16_16_16_16,      8,     4,     wgpu::TextureFormat::RGBA16Float,        ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(SFLOAT_32,               4,     1,     wgpu::TextureFormat::R32Float,           ConvClass::Direct,      FeatureGate::Float32Filterable)
WGPU_FMT(SFLOAT_32_32,            8,     2,     wgpu::TextureFormat::RG32Float,          ConvClass::Direct,      FeatureGate::Float32Filterable)
WGPU_FMT(SFLOAT_32_32_32,        12,     3,     wgpu::TextureFormat::RGBA32Float,        ConvClass::PromoteRGBA, FeatureGate::Float32Filterable)
WGPU_FMT(SFLOAT_32_32_32_32,     16,     4,     wgpu::TextureFormat::RGBA32Float,        ConvClass::Direct,      FeatureGate::Float32Filterable)

/* --- Packed ----------------------------------------------------------------- */
WGPU_FMT(UNORM_10_10_10_2,        4,     4,     wgpu::TextureFormat::RGB10A2Unorm,       ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(UINT_10_10_10_2,         4,     4,     wgpu::TextureFormat::RGB10A2Uint,        ConvClass::Direct,      FeatureGate::None)
WGPU_FMT(UFLOAT_11_11_10,         4,     3,     wgpu::TextureFormat::RG11B10Ufloat,      ConvClass::Direct,      FeatureGate::RG11B10UfloatRenderable)
WGPU_FMT(UFLOAT_9_9_9_EXP_5,      4,     3,     wgpu::TextureFormat::RGB9E5Ufloat,       ConvClass::Direct,      FeatureGate::None)

/* --- Depth / stencil -------------------------------------------------------- */
WGPU_FMT(UNORM_16_DEPTH,          2,     1,     wgpu::TextureFormat::Depth16Unorm,       ConvClass::Depth,       FeatureGate::None)
WGPU_FMT(SFLOAT_32_DEPTH,         4,     1,     wgpu::TextureFormat::Depth32Float,       ConvClass::Depth,       FeatureGate::None)
WGPU_FMT(SFLOAT_32_DEPTH_UINT_8,  8,     1,     wgpu::TextureFormat::Depth32FloatStencil8, ConvClass::Depth,     FeatureGate::Depth32FloatStencil8)

/* --- sRGB ------------------------------------------------------------------- */
WGPU_FMT(SRGBA_8_8_8,             3,     3,     wgpu::TextureFormat::RGBA8UnormSrgb,     ConvClass::PromoteRGBA, FeatureGate::None)
WGPU_FMT(SRGBA_8_8_8_8,           4,     4,     wgpu::TextureFormat::RGBA8UnormSrgb,     ConvClass::Direct,      FeatureGate::None)

/* --- Compressed (S3TC / DXT → BC) ------------------------------------------- */
WGPU_FMT(SNORM_DXT1,              8,     4,     wgpu::TextureFormat::BC1RGBAUnorm,       ConvClass::Compressed,  FeatureGate::TextureCompressionBC)
WGPU_FMT(SNORM_DXT3,             16,     4,     wgpu::TextureFormat::BC2RGBAUnorm,       ConvClass::Compressed,  FeatureGate::TextureCompressionBC)
WGPU_FMT(SNORM_DXT5,             16,     4,     wgpu::TextureFormat::BC3RGBAUnorm,       ConvClass::Compressed,  FeatureGate::TextureCompressionBC)
WGPU_FMT(SRGB_DXT1,               8,     4,     wgpu::TextureFormat::BC1RGBAUnormSrgb,   ConvClass::Compressed,  FeatureGate::TextureCompressionBC)
WGPU_FMT(SRGB_DXT3,              16,     4,     wgpu::TextureFormat::BC2RGBAUnormSrgb,   ConvClass::Compressed,  FeatureGate::TextureCompressionBC)
WGPU_FMT(SRGB_DXT5,              16,     4,     wgpu::TextureFormat::BC3RGBAUnormSrgb,   ConvClass::Compressed,  FeatureGate::TextureCompressionBC)
/* clang-format on */
