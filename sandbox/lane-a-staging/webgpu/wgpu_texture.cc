/* SPDX-FileCopyrightText: 2022 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_texture.cc @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * WGPUTexture — the WebGPU gpu::Texture implementation. See wgpu_texture.hh.
 *
 * Device textures are created via the T9 format table (wgpu_texture_format); host
 * pixel data is converted to/from the device byte layout on the CPU (WebGPU copies
 * transfer raw bytes — no format conversion happens on the queue), then moved with
 * queue.writeTexture (upload; no row-alignment requirement) and CopyTextureToBuffer
 * + a MAP_READ staging buffer (readback; 256-byte bytesPerRow alignment). The
 * standalone round-trip proof of the format/conversion paths is
 * sandbox/wgpu-texture-formats/ (notes/gpu-t9pre-findings.md). */

#include "wgpu_texture.hh"

#include "wgpu_common.hh"
#include "wgpu_context.hh"
#include "wgpu_data_conversion.hh"

#include "GPU_context.hh"
#include "gpu_context_private.hh"

#include "BLI_math_base.h"
#include "BLI_math_half.hh"
#include "BLI_math_vector_types.hh"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <vector>

namespace blender::gpu::webgpu {

/* -------------------------------------------------------------------- */
/** \name Active context / device access
 * \{ */

/** The active WebGPU context (owns the live Dawn instance/device/queue). Mirrors
 * the helper in wgpu_storage_buffer.cc. */
static WGPUContext *active_context()
{
  return static_cast<WGPUContext *>(unwrap(GPU_context_active_get()));
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Per-component representation + scalar conversion
 *
 * The conversion works between HOST bytes (an eGPUDataFormat scalar per logical
 * component, tightly packed) and the DEVICE byte layout of the Blender
 * TextureFormat. The wgpu::Texture then stores those device bytes verbatim, so the
 * device representation below is derived from Blender's format_, never from the
 * wgpu format (they always agree byte-for-byte — RGBA8Unorm holds unorm8 bytes,
 * etc.). Promotion (3→4 channels) pads an opaque alpha; SNORM_16 is emulated as a
 * *Uint* texture whose bytes are the identical SNORM two's-complement pattern.
 * \{ */

/** Per-component storage kind of a Blender color TextureFormat. */
enum class Repr : uint8_t {
  Unorm8,
  Snorm8,
  Unorm16,
  Snorm16,
  Uint8,
  Uint16,
  Uint32,
  Sint8,
  Sint16,
  Sint32,
  F16,
  F32,
  PackedR11G11B10, /* whole 32-bit texel; 3 logical comps */
  Packed32,        /* whole 32-bit texel copied verbatim (RGB10A2 UNORM/UINT) */
  Depth16,         /* unorm16 depth */
  Depth32F,        /* float32 depth */
  Depth32FS8,      /* float32 depth (+ separate stencil8) */
  Compressed,      /* BC block-compressed */
  Unsupported,
};

/** true when the component is stored as an integer (uint/sint) — selects the
 * integer conversion path; false selects the float/normalized path. */
static bool repr_is_integer(Repr r)
{
  switch (r) {
    case Repr::Uint8:
    case Repr::Uint16:
    case Repr::Uint32:
    case Repr::Sint8:
    case Repr::Sint16:
    case Repr::Sint32:
      return true;
    default:
      return false;
  }
}

/** Bytes of one component in the device representation (0 for special/packed). */
static uint32_t repr_comp_bytes(Repr r)
{
  switch (r) {
    case Repr::Unorm8:
    case Repr::Snorm8:
    case Repr::Uint8:
    case Repr::Sint8:
      return 1;
    case Repr::Unorm16:
    case Repr::Snorm16:
    case Repr::Uint16:
    case Repr::Sint16:
    case Repr::F16:
    case Repr::Depth16:
      return 2;
    case Repr::Uint32:
    case Repr::Sint32:
    case Repr::F32:
    case Repr::Depth32F:
    case Repr::Depth32FS8:
      return 4;
    default:
      return 0;
  }
}

/** The device component representation for a Blender texture format. */
static Repr repr_of(TextureFormat f)
{
  switch (f) {
    /* 8-bit */
    case TextureFormat::UNORM_8:
    case TextureFormat::UNORM_8_8:
    case TextureFormat::UNORM_8_8_8:
    case TextureFormat::UNORM_8_8_8_8:
    case TextureFormat::SRGBA_8_8_8:      /* sRGB curve not applied on the CPU path */
    case TextureFormat::SRGBA_8_8_8_8:
      return Repr::Unorm8;
    case TextureFormat::SNORM_8:
    case TextureFormat::SNORM_8_8:
    case TextureFormat::SNORM_8_8_8:
    case TextureFormat::SNORM_8_8_8_8:
      return Repr::Snorm8;
    case TextureFormat::UINT_8:
    case TextureFormat::UINT_8_8:
    case TextureFormat::UINT_8_8_8:
    case TextureFormat::UINT_8_8_8_8:
      return Repr::Uint8;
    case TextureFormat::SINT_8:
    case TextureFormat::SINT_8_8:
    case TextureFormat::SINT_8_8_8:
    case TextureFormat::SINT_8_8_8_8:
      return Repr::Sint8;
    /* 16-bit */
    case TextureFormat::UNORM_16:
    case TextureFormat::UNORM_16_16:
    case TextureFormat::UNORM_16_16_16:
    case TextureFormat::UNORM_16_16_16_16:
      return Repr::Unorm16;
    case TextureFormat::SNORM_16:
    case TextureFormat::SNORM_16_16:
    case TextureFormat::SNORM_16_16_16:
    case TextureFormat::SNORM_16_16_16_16:
      return Repr::Snorm16;
    case TextureFormat::UINT_16:
    case TextureFormat::UINT_16_16:
    case TextureFormat::UINT_16_16_16:
    case TextureFormat::UINT_16_16_16_16:
      return Repr::Uint16;
    case TextureFormat::SINT_16:
    case TextureFormat::SINT_16_16:
    case TextureFormat::SINT_16_16_16:
    case TextureFormat::SINT_16_16_16_16:
      return Repr::Sint16;
    case TextureFormat::SFLOAT_16:
    case TextureFormat::SFLOAT_16_16:
    case TextureFormat::SFLOAT_16_16_16:
    case TextureFormat::SFLOAT_16_16_16_16:
      return Repr::F16;
    /* 32-bit */
    case TextureFormat::UINT_32:
    case TextureFormat::UINT_32_32:
    case TextureFormat::UINT_32_32_32:
    case TextureFormat::UINT_32_32_32_32:
      return Repr::Uint32;
    case TextureFormat::SINT_32:
    case TextureFormat::SINT_32_32:
    case TextureFormat::SINT_32_32_32:
    case TextureFormat::SINT_32_32_32_32:
      return Repr::Sint32;
    case TextureFormat::SFLOAT_32:
    case TextureFormat::SFLOAT_32_32:
    case TextureFormat::SFLOAT_32_32_32:
    case TextureFormat::SFLOAT_32_32_32_32:
      return Repr::F32;
    /* Packed / special. */
    case TextureFormat::UFLOAT_11_11_10:
      return Repr::PackedR11G11B10;
    /* RGB10A2 (UNORM/UINT): WebGPU RGB10A2Unorm/Uint have the same packed bit
     * layout as GPU_DATA_2_10_10_10_REV (R low 10 bits … A high 2) — verbatim copy. */
    case TextureFormat::UNORM_10_10_10_2:
    case TextureFormat::UINT_10_10_10_2:
      return Repr::Packed32;
    case TextureFormat::UNORM_16_DEPTH:
      return Repr::Depth16;
    case TextureFormat::SFLOAT_32_DEPTH:
      return Repr::Depth32F;
    case TextureFormat::SFLOAT_32_DEPTH_UINT_8:
      return Repr::Depth32FS8;
    case TextureFormat::SRGB_DXT1:
    case TextureFormat::SRGB_DXT3:
    case TextureFormat::SRGB_DXT5:
    case TextureFormat::SNORM_DXT1:
    case TextureFormat::SNORM_DXT3:
    case TextureFormat::SNORM_DXT5:
      return Repr::Compressed;
    default:
      /* UFLOAT_9_9_9_EXP_5 (RGB9E5): shared-exponent pack not implemented (its gate
       * test is disabled); no CPU upload/read path. */
      return Repr::Unsupported;
  }
}

/* --- Host scalar extraction (one logical component) ----------------------- */

static float host_read_float(const uint8_t *p, eGPUDataFormat host)
{
  switch (host) {
    case GPU_DATA_FLOAT: {
      float v;
      std::memcpy(&v, p, 4);
      return v;
    }
    case GPU_DATA_HALF_FLOAT: {
      uint16_t v;
      std::memcpy(&v, p, 2);
      return math::half_to_float(v);
    }
    case GPU_DATA_UBYTE:
      /* Normalized read: byte/255 → the unorm8 store below round-trips to the
       * identical byte, so GPU_DATA_UBYTE uploads to UNORM/SRGB are byte-exact. */
      return float(*p) / 255.0f;
    default:
      return 0.0f;
  }
}

static int64_t host_read_int(const uint8_t *p, eGPUDataFormat host)
{
  switch (host) {
    case GPU_DATA_UINT: {
      uint32_t v;
      std::memcpy(&v, p, 4);
      return int64_t(v);
    }
    case GPU_DATA_INT: {
      int32_t v;
      std::memcpy(&v, p, 4);
      return int64_t(v);
    }
    case GPU_DATA_UBYTE:
      return int64_t(*p);
    default:
      return 0;
  }
}

static void host_write_float(uint8_t *p, eGPUDataFormat host, float v)
{
  switch (host) {
    case GPU_DATA_FLOAT:
      std::memcpy(p, &v, 4);
      break;
    case GPU_DATA_HALF_FLOAT: {
      uint16_t h = math::float_to_half(v);
      std::memcpy(p, &h, 2);
      break;
    }
    case GPU_DATA_UBYTE:
      p[0] = uint8_t(std::lround(std::clamp(v, 0.0f, 1.0f) * 255.0f));
      break;
    default:
      break;
  }
}

static void host_write_int(uint8_t *p, eGPUDataFormat host, int64_t v)
{
  switch (host) {
    case GPU_DATA_UINT: {
      uint32_t u = uint32_t(v);
      std::memcpy(p, &u, 4);
      break;
    }
    case GPU_DATA_INT: {
      int32_t i = int32_t(v);
      std::memcpy(p, &i, 4);
      break;
    }
    case GPU_DATA_UBYTE:
      p[0] = uint8_t(v);
      break;
    default:
      break;
  }
}

/* --- Device scalar store/load (one logical component) --------------------- */

static void dev_write_float(uint8_t *p, Repr r, float v)
{
  switch (r) {
    case Repr::Unorm8:
      p[0] = uint8_t(std::lround(std::clamp(v, 0.0f, 1.0f) * 255.0f));
      break;
    case Repr::Snorm8: {
      int8_t s = int8_t(std::lround(std::clamp(v, -1.0f, 1.0f) * 127.0f));
      std::memcpy(p, &s, 1);
      break;
    }
    case Repr::Unorm16: {
      uint16_t u = uint16_t(std::lround(std::clamp(v, 0.0f, 1.0f) * 65535.0f));
      std::memcpy(p, &u, 2);
      break;
    }
    case Repr::Snorm16: {
      int16_t s = int16_t(std::lround(std::clamp(v, -1.0f, 1.0f) * 32767.0f));
      std::memcpy(p, &s, 2);
      break;
    }
    case Repr::F16: {
      uint16_t h = math::float_to_half(v);
      std::memcpy(p, &h, 2);
      break;
    }
    case Repr::F32:
    case Repr::Depth32F:
    case Repr::Depth32FS8:
      std::memcpy(p, &v, 4);
      break;
    case Repr::Depth16: {
      uint16_t u = uint16_t(std::lround(std::clamp(v, 0.0f, 1.0f) * 65535.0f));
      std::memcpy(p, &u, 2);
      break;
    }
    default:
      break;
  }
}

static float dev_read_float(const uint8_t *p, Repr r)
{
  switch (r) {
    case Repr::Unorm8:
      return float(p[0]) / 255.0f;
    case Repr::Snorm8: {
      int8_t s;
      std::memcpy(&s, p, 1);
      return std::max(float(s) / 127.0f, -1.0f);
    }
    case Repr::Unorm16:
    case Repr::Depth16: {
      uint16_t u;
      std::memcpy(&u, p, 2);
      return float(u) / 65535.0f;
    }
    case Repr::Snorm16: {
      int16_t s;
      std::memcpy(&s, p, 2);
      return std::max(float(s) / 32767.0f, -1.0f);
    }
    case Repr::F16: {
      uint16_t h;
      std::memcpy(&h, p, 2);
      return math::half_to_float(h);
    }
    case Repr::F32:
    case Repr::Depth32F:
    case Repr::Depth32FS8: {
      float v;
      std::memcpy(&v, p, 4);
      return v;
    }
    default:
      return 0.0f;
  }
}

static void dev_write_int(uint8_t *p, Repr r, int64_t v)
{
  switch (r) {
    case Repr::Uint8:
      p[0] = uint8_t(v);
      break;
    case Repr::Sint8: {
      int8_t s = int8_t(v);
      std::memcpy(p, &s, 1);
      break;
    }
    case Repr::Uint16: {
      uint16_t u = uint16_t(v);
      std::memcpy(p, &u, 2);
      break;
    }
    case Repr::Sint16: {
      int16_t s = int16_t(v);
      std::memcpy(p, &s, 2);
      break;
    }
    case Repr::Uint32: {
      uint32_t u = uint32_t(v);
      std::memcpy(p, &u, 4);
      break;
    }
    case Repr::Sint32: {
      int32_t s = int32_t(v);
      std::memcpy(p, &s, 4);
      break;
    }
    default:
      break;
  }
}

static int64_t dev_read_int(const uint8_t *p, Repr r)
{
  switch (r) {
    case Repr::Uint8:
      return int64_t(p[0]);
    case Repr::Sint8: {
      int8_t s;
      std::memcpy(&s, p, 1);
      return int64_t(s);
    }
    case Repr::Uint16: {
      uint16_t u;
      std::memcpy(&u, p, 2);
      return int64_t(u);
    }
    case Repr::Sint16: {
      int16_t s;
      std::memcpy(&s, p, 2);
      return int64_t(s);
    }
    case Repr::Uint32: {
      uint32_t u;
      std::memcpy(&u, p, 4);
      return int64_t(u);
    }
    case Repr::Sint32: {
      int32_t s;
      std::memcpy(&s, p, 4);
      return int64_t(s);
    }
    default:
      return 0;
  }
}

/* --- Packed R11G11B10 (unsigned float) ------------------------------------ */

/** Pack a non-negative float to an N-bit unsigned float (5-bit exponent, bias 15,
 * mantissa = N-5 bits, no sign/inf/nan). Matches the WebGPU RG11B10Ufloat layout
 * (R:0..10, G:11..21, B:22..31). Sufficient for the [0,1] test data. */
static uint32_t float_to_ufloat(float f, int mant_bits)
{
  if (!(f > 0.0f)) {
    return 0;
  }
  uint32_t bits;
  std::memcpy(&bits, &f, 4);
  int exp = int((bits >> 23) & 0xFF) - 127; /* unbias float32 */
  uint32_t mant = bits & 0x7FFFFF;          /* 23-bit mantissa */
  int e = exp + 15;                         /* rebias to 5-bit */
  if (e <= 0) {
    return 0; /* underflow to zero (denormals unsupported — negligible for data). */
  }
  if (e > 31) {
    e = 31; /* clamp to max finite. */
    mant = 0x7FFFFF;
  }
  uint32_t m = mant >> (23 - mant_bits);
  return (uint32_t(e) << mant_bits) | m;
}

static float ufloat_to_float(uint32_t v, int mant_bits)
{
  int e = int(v >> mant_bits) & 0x1F;
  uint32_t m = v & ((1u << mant_bits) - 1u);
  if (e == 0) {
    return 0.0f; /* zero / denormal-as-zero. */
  }
  uint32_t mant32 = m << (23 - mant_bits);
  uint32_t exp32 = uint32_t(e - 15 + 127);
  uint32_t bits = (exp32 << 23) | mant32;
  float f;
  std::memcpy(&f, &bits, 4);
  return f;
}

static uint32_t pack_r11g11b10(float r, float g, float b)
{
  return (float_to_ufloat(r, 6) & 0x7FF) | ((float_to_ufloat(g, 6) & 0x7FF) << 11) |
         ((float_to_ufloat(b, 5) & 0x3FF) << 22);
}

static void unpack_r11g11b10(uint32_t p, float out[3])
{
  out[0] = ufloat_to_float(p & 0x7FF, 6);
  out[1] = ufloat_to_float((p >> 11) & 0x7FF, 6);
  out[2] = ufloat_to_float((p >> 22) & 0x3FF, 5);
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Format / type mapping
 * \{ */

/** WebGPU texture dimension for a Blender texture type. 1D arrays and cube maps
 * are represented as 2D (layers → depthOrArrayLayers / height). */
static wgpu::TextureDimension to_wgpu_dimension(GPUTextureType type)
{
  if (type == GPU_TEXTURE_1D) {
    return wgpu::TextureDimension::e1D;
  }
  if (type == GPU_TEXTURE_3D) {
    return wgpu::TextureDimension::e3D;
  }
  return wgpu::TextureDimension::e2D;
}

/** WGSL view dimension for a bind-group texture/image binding. Mirrors the
 * create-info ImageType → WGSL mapping (wgpu_shader_interface_map infer_view_
 * dimension): 1D arrays are stored as 2D layers, cubes stay cube for sampling. A
 * storage-image binding forbids cube — the caller collapses those (no cube storage
 * image exists at the pin). */
static wgpu::TextureViewDimension to_wgpu_view_dimension(GPUTextureType type)
{
  switch (type) {
    case GPU_TEXTURE_1D:
      return wgpu::TextureViewDimension::e1D;
    case GPU_TEXTURE_3D:
      return wgpu::TextureViewDimension::e3D;
    case GPU_TEXTURE_2D_ARRAY:
    case GPU_TEXTURE_1D_ARRAY:
      return wgpu::TextureViewDimension::e2DArray;
    case GPU_TEXTURE_CUBE:
      return wgpu::TextureViewDimension::Cube;
    case GPU_TEXTURE_CUBE_ARRAY:
      return wgpu::TextureViewDimension::CubeArray;
    default:
      return wgpu::TextureViewDimension::e2D;
  }
}

/** eGPUTextureUsage → wgpu::TextureUsage. CopyDst/CopySrc are always added so
 * host upload (writeTexture / update_sub) and readback (read / copy_to) work; the
 * gpu module never flags those explicitly. `renderable`/`storable` gate the
 * attachment/storage bits: Blender flags GPU_TEXTURE_USAGE_ATTACHMENT broadly, but
 * WebGPU CreateTexture REJECTS RenderAttachment on a non-renderable format (e.g.
 * every SNORM-8, RGB9E5, compressed) and StorageBinding on a non-storage format —
 * so a texture that is only ever uploaded+read (as the format tests do) must not
 * request bits its format can't support, or creation fails outright. */
static wgpu::TextureUsage to_wgpu_usage(eGPUTextureUsage usage,
                                        bool compressed,
                                        bool renderable,
                                        bool storable)
{
  wgpu::TextureUsage u = wgpu::TextureUsage::CopySrc | wgpu::TextureUsage::CopyDst;
  if (usage & GPU_TEXTURE_USAGE_SHADER_READ) {
    u |= wgpu::TextureUsage::TextureBinding;
  }
  if ((usage & GPU_TEXTURE_USAGE_SHADER_WRITE) && storable && !compressed) {
    u |= wgpu::TextureUsage::StorageBinding;
  }
  if ((usage & GPU_TEXTURE_USAGE_ATTACHMENT) && renderable && !compressed) {
    u |= wgpu::TextureUsage::RenderAttachment;
  }
  return u;
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name WGPUTexture
 * \{ */

WGPUTexture::~WGPUTexture()
{
  texture_ = nullptr; /* wgpu::Texture is ref-counted; release the handle. */
}

bool WGPUTexture::allocate()
{
  BLI_assert(texture_ == nullptr);
  BLI_assert(!is_texture_view());

  const FormatInfo &fi = format_info(format_);
  conv_ = fi.conv;
  wgpu_format_ = fi.wgpu;
  snorm16_emulated_ = false;

  /* SNORM_16 family: no WebGPU format at the pin. Emulate in a matching-width Uint
   * texture (byte-identical SNORM patterns; exact CPU round-trip). See §5. */
  if (fi.gate == FeatureGate::Snorm16) {
    snorm16_emulated_ = true;
    switch (format_) {
      case TextureFormat::SNORM_16:
        wgpu_format_ = wgpu::TextureFormat::R16Uint;
        break;
      case TextureFormat::SNORM_16_16:
        wgpu_format_ = wgpu::TextureFormat::RG16Uint;
        break;
      default: /* SNORM_16_16_16 (promoted) / SNORM_16_16_16_16 */
        wgpu_format_ = wgpu::TextureFormat::RGBA16Uint;
        break;
    }
  }

  if (wgpu_format_ == wgpu::TextureFormat::Undefined) {
    return false;
  }

  const bool compressed = (format_flag_ & GPU_FORMAT_COMPRESSED) != 0;
  /* Renderable = the format's spec cap, OR any depth/stencil format (needed for the
   * render-pass depth clear). SNORM16 is emulated as a Uint texture, whose Uint
   * target is not renderable. WebGPU forbids RenderAttachment on 1D textures
   * (dimension=1D) — a 1D array is created as 2D so it stays eligible. */
  const bool renderable = (fi.caps.renderable || (format_flag_ & GPU_FORMAT_DEPTH) != 0) &&
                          type_ != GPU_TEXTURE_1D;
  const bool storable = fi.caps.storage && !snorm16_emulated_;

  /* Base (mip-0) size. Layers/faces map to depthOrArrayLayers; a 1D array becomes
   * a 2D texture whose height is the layer count. */
  wgpu::Extent3D size = {};
  size.width = uint32_t(std::max(w_, 1));
  switch (type_) {
    case GPU_TEXTURE_1D:
      size.height = 1;
      size.depthOrArrayLayers = 1;
      break;
    case GPU_TEXTURE_1D_ARRAY:
      size.height = uint32_t(std::max(h_, 1)); /* layers */
      size.depthOrArrayLayers = 1;
      break;
    case GPU_TEXTURE_2D:
      size.height = uint32_t(std::max(h_, 1));
      size.depthOrArrayLayers = 1;
      break;
    case GPU_TEXTURE_2D_ARRAY:
      size.height = uint32_t(std::max(h_, 1));
      size.depthOrArrayLayers = uint32_t(std::max(d_, 1)); /* layers */
      break;
    case GPU_TEXTURE_CUBE:
    case GPU_TEXTURE_CUBE_ARRAY:
      size.height = uint32_t(std::max(w_, 1));
      size.depthOrArrayLayers = uint32_t(std::max(d_, 1)); /* 6 * layers */
      break;
    case GPU_TEXTURE_3D:
      size.height = uint32_t(std::max(h_, 1));
      size.depthOrArrayLayers = uint32_t(std::max(d_, 1));
      break;
    default:
      return false;
  }

  wgpu::TextureDescriptor desc = {};
  desc.label = name_.c_str();
  desc.usage = to_wgpu_usage(gpu_image_usage_flags_, compressed, renderable, storable);
  desc.dimension = to_wgpu_dimension(type_);
  desc.size = size;
  desc.format = wgpu_format_;
  desc.mipLevelCount = uint32_t(std::max(mipmaps_, 1));
  desc.sampleCount = 1;

  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return false;
  }
  texture_ = ctx->device_get().CreateTexture(&desc);
  return texture_ != nullptr;
}

bool WGPUTexture::init_internal()
{
  if (!allocate()) {
    return false;
  }
  this->mip_range_set(0, mipmaps_ - 1);
  return true;
}

bool WGPUTexture::init_internal(VertBuf *vbo)
{
  /* WebGPU has no texel-buffer texture; sampling of a buffer texture is forwarded
   * to the vertex buffer at bind-group assembly (lane A). Store the source; no
   * device texture is created. Mirrors VKTexture::init_internal(VertBuf*). */
  BLI_assert(source_buffer_ == nullptr);
  source_buffer_ = vbo;
  conv_ = ConvClass::Direct;
  wgpu_format_ = format_info(format_).wgpu;
  return true;
}

bool WGPUTexture::init_internal(gpu::Texture *src,
                                int mip_offset,
                                int layer_offset,
                                bool use_stencil)
{
  /* Texture view. The base class has already set w_/h_/d_/format_/type_ and
   * is_texture_view_. Alias the source's device texture; a distinct wgpu view is
   * created lazily at bind/attachment time (bind-group assembly, lane A). */
  BLI_assert(source_ == nullptr);
  BLI_assert(src != nullptr);
  source_ = static_cast<WGPUTexture *>(src);
  mip_offset_ = mip_offset;
  layer_offset_ = layer_offset;
  use_stencil_ = use_stencil;
  conv_ = source_->conv_;
  wgpu_format_ = source_->wgpu_format_;
  snorm16_emulated_ = source_->snorm16_emulated_;
  return true;
}

/* --- Geometry helpers ----------------------------------------------------- */

/** Number of components the device stores per texel (promotion widens 3→4). */
static int device_channels(TextureFormat format, ConvClass conv)
{
  if (conv == ConvClass::PromoteRGBA) {
    return 4;
  }
  return to_component_len(format);
}

/** Device bytes per (uncompressed) texel. */
static uint32_t device_texel_bytes(TextureFormat format, ConvClass conv, Repr repr)
{
  if (repr == Repr::PackedR11G11B10 || repr == Repr::Packed32) {
    return 4;
  }
  return uint32_t(device_channels(format, conv)) * repr_comp_bytes(repr);
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Host <-> device pixel conversion
 * \{ */

/** Convert `sample_count` tightly-packed host texels (logical components in
 * `host_format`) into the device byte layout for `format_`/`conv_`. */
void WGPUTexture::convert_host_to_device(uint8_t *dst,
                                         const uint8_t *src,
                                         size_t sample_count,
                                         eGPUDataFormat host_format) const
{
  const Repr repr = snorm16_emulated_ ? Repr::Snorm16 : repr_of(format_);
  const int logical = to_component_len(format_);
  const int channels = device_channels(format_, conv_);
  const uint32_t hbytes = uint32_t(to_bytesize(host_format));
  const uint32_t dbytes = repr_comp_bytes(repr);
  const size_t hstride = size_t(logical) * hbytes;
  const size_t dstride = size_t(channels) * dbytes;

  /* Packed R11G11B10: one 32-bit texel per pixel. */
  if (repr == Repr::PackedR11G11B10) {
    for (size_t p = 0; p < sample_count; p++) {
      const uint8_t *s = src + p * (host_format == GPU_DATA_10_11_11_REV ? 4 : hstride);
      uint8_t *d = dst + p * 4;
      uint32_t packed;
      if (host_format == GPU_DATA_10_11_11_REV) {
        std::memcpy(&packed, s, 4); /* already packed — copy verbatim. */
      }
      else {
        packed = pack_r11g11b10(host_read_float(s, GPU_DATA_FLOAT),
                                host_read_float(s + hbytes, GPU_DATA_FLOAT),
                                host_read_float(s + 2 * hbytes, GPU_DATA_FLOAT));
      }
      std::memcpy(d, &packed, 4);
    }
    return;
  }

  /* RGB10A2 packed: GPU_DATA_2_10_10_10_REV matches the device layout verbatim. */
  if (repr == Repr::Packed32) {
    for (size_t p = 0; p < sample_count; p++) {
      std::memcpy(dst + p * 4, src + p * 4, 4);
    }
    return;
  }

  const bool integer = repr_is_integer(repr);
  for (size_t p = 0; p < sample_count; p++) {
    const uint8_t *s = src + p * hstride;
    uint8_t *d = dst + p * dstride;
    for (int c = 0; c < channels; c++) {
      uint8_t *dc = d + size_t(c) * dbytes;
      if (c < logical) {
        if (integer) {
          dev_write_int(dc, repr, host_read_int(s + size_t(c) * hbytes, host_format));
        }
        else {
          dev_write_float(dc, repr, host_read_float(s + size_t(c) * hbytes, host_format));
        }
      }
      else {
        /* Opaque-alpha padding for promoted 3→4 channel formats. */
        if (integer) {
          dev_write_int(dc, repr, 1);
        }
        else {
          dev_write_float(dc, repr, 1.0f);
        }
      }
    }
  }
}

/** Convert `sample_count` device texels back into tightly-packed host texels
 * (logical components in `host_format`). */
void WGPUTexture::convert_device_to_host(uint8_t *dst,
                                         const uint8_t *src,
                                         size_t sample_count,
                                         eGPUDataFormat host_format) const
{
  const Repr repr = snorm16_emulated_ ? Repr::Snorm16 : repr_of(format_);
  const int logical = to_component_len(format_);
  const int channels = device_channels(format_, conv_);
  const uint32_t hbytes = uint32_t(to_bytesize(host_format));
  const uint32_t dbytes = repr_comp_bytes(repr);
  const size_t hstride = size_t(logical) * hbytes;
  const size_t dstride = size_t(channels) * dbytes;

  if (repr == Repr::PackedR11G11B10) {
    for (size_t p = 0; p < sample_count; p++) {
      const uint8_t *s = src + p * 4;
      uint8_t *d = dst + p * (host_format == GPU_DATA_10_11_11_REV ? 4 : hstride);
      if (host_format == GPU_DATA_10_11_11_REV) {
        std::memcpy(d, s, 4);
      }
      else {
        uint32_t packed;
        std::memcpy(&packed, s, 4);
        float rgb[3];
        unpack_r11g11b10(packed, rgb);
        host_write_float(d, GPU_DATA_FLOAT, rgb[0]);
        host_write_float(d + hbytes, GPU_DATA_FLOAT, rgb[1]);
        host_write_float(d + 2 * hbytes, GPU_DATA_FLOAT, rgb[2]);
      }
    }
    return;
  }

  /* RGB10A2 packed: verbatim to GPU_DATA_2_10_10_10_REV. */
  if (repr == Repr::Packed32) {
    for (size_t p = 0; p < sample_count; p++) {
      std::memcpy(dst + p * 4, src + p * 4, 4);
    }
    return;
  }

  const bool integer = repr_is_integer(repr);
  for (size_t p = 0; p < sample_count; p++) {
    const uint8_t *s = src + p * dstride;
    uint8_t *d = dst + p * hstride;
    for (int c = 0; c < logical; c++) {
      const uint8_t *sc = s + size_t(c) * dbytes;
      if (integer) {
        host_write_int(d + size_t(c) * hbytes, host_format, dev_read_int(sc, repr));
      }
      else {
        host_write_float(d + size_t(c) * hbytes, host_format, dev_read_float(sc, repr));
      }
    }
  }
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Upload / clear
 * \{ */

void WGPUTexture::update_sub(int mip,
                             int offset[3],
                             int extent[3],
                             eGPUDataFormat format,
                             const void *data,
                             uint unpack_row_length)
{
  BLI_assert(!is_texture_view());
  if (texture_ == nullptr || data == nullptr) {
    return;
  }
  const Repr repr = snorm16_emulated_ ? Repr::Snorm16 : repr_of(format_);

  /* Depth aspects and BC compression: buffer→texture upload of arbitrary depth
   * data is not permitted for Depth32Float in WebGPU (needs a render/compute
   * path — coordinate with lane A). Compressed upload is deferred. */
  if (repr == Repr::Depth32F || repr == Repr::Depth32FS8 || repr == Repr::Compressed ||
      repr == Repr::Unsupported)
  {
    return;
  }

  const int ex = std::max(extent[0], 1);
  const int ey = std::max(extent[1], 1);
  const int ez = std::max(extent[2], 1);
  const size_t sample_count = size_t(ex) * ey * ez;
  const uint32_t texel_bytes = device_texel_bytes(format_, conv_, repr);

  std::vector<uint8_t> device_data(sample_count * texel_bytes);
  const uint8_t *src = static_cast<const uint8_t *>(data);
  /* Non-zero unpack_row_length that differs from the sub-region width means the
   * source rows are strided (the caller uploads a window of a larger image): gather
   * `ex` texels per row from the wider source stride. Matches vk_texture.cc. */
  if (unpack_row_length != 0u && int(unpack_row_length) != ex) {
    const size_t host_texel = size_t(to_component_len(format_)) * to_bytesize(format);
    const size_t src_row_stride = size_t(unpack_row_length) * host_texel;
    const size_t dst_row_bytes = size_t(ex) * texel_bytes;
    const int rows = ey * ez;
    for (int row = 0; row < rows; row++) {
      convert_host_to_device(device_data.data() + size_t(row) * dst_row_bytes,
                             src + size_t(row) * src_row_stride,
                             size_t(ex),
                             format);
    }
  }
  else {
    convert_host_to_device(device_data.data(), src, sample_count, format);
  }

  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return;
  }

  wgpu::TexelCopyTextureInfo dst = {};
  dst.texture = texture_;
  dst.mipLevel = uint32_t(mip);
  dst.origin = {uint32_t(offset[0]), uint32_t(offset[1]), uint32_t(offset[2])};
  dst.aspect = wgpu::TextureAspect::All;

  wgpu::TexelCopyBufferLayout layout = {};
  layout.offset = 0;
  layout.bytesPerRow = uint32_t(ex) * texel_bytes; /* writeTexture needs no 256 align. */
  layout.rowsPerImage = uint32_t(ey);

  wgpu::Extent3D write_size = {uint32_t(ex), uint32_t(ey), uint32_t(ez)};
  ctx->queue_get().WriteTexture(&dst, device_data.data(), device_data.size(), &layout, &write_size);
}

void WGPUTexture::update_sub(int /*offset*/[3],
                             int /*extent*/[3],
                             eGPUDataFormat /*format*/,
                             GPUPixelBuffer * /*pixbuf*/)
{
  /* Pixel-buffer-sourced upload requires the WebGPU pixel-buffer backend
   * (pixelbuf_alloc, still a placeholder in wgpu_backend.cc). Deferred. */
  BLI_assert_msg(0, "WGPUTexture: pixel-buffer update_sub not implemented yet");
}

wgpu::TextureView WGPUTexture::image_view()
{
  if (texture_ == nullptr) {
    return nullptr;
  }
  /* A storage-image binding requires a SINGLE mip level and a non-cube view
   * dimension (WebGPU forbids cube storage textures; none exist at the pin). */
  wgpu::TextureViewDimension dim = to_wgpu_view_dimension(type_);
  if (dim == wgpu::TextureViewDimension::Cube ||
      dim == wgpu::TextureViewDimension::CubeArray)
  {
    dim = wgpu::TextureViewDimension::e2DArray;
  }
  wgpu::TextureViewDescriptor d = {};
  d.format = wgpu_format_;
  d.dimension = dim;
  d.baseMipLevel = uint32_t(std::max(mip_offset_, 0));
  d.mipLevelCount = 1;
  d.baseArrayLayer = 0;
  /* arrayLayerCount left at its UNDEFINED default → all remaining layers (1 for a
   * plain 2D texture, the full array for an array texture). */
  d.aspect = wgpu::TextureAspect::All;
  return texture_.CreateView(&d);
}

wgpu::TextureView WGPUTexture::sampled_view()
{
  /* A gpu::Texture VIEW (GPU_texture_create_view) has no device texture of its own —
   * it aliases source_'s, applying mip_offset_/layer_offset_. Resolve to the source so
   * a bound view (UI icon/region composite textures are frequently views) still yields
   * a sampled view instead of null (which would silently drop the texture bind-group
   * entry and leave its sampler orphaned -> Dawn "entries did not match"). */
  wgpu::Texture tex = (texture_ != nullptr) ? texture_ :
                      (source_ != nullptr ? source_->texture_ : wgpu::Texture(nullptr));
  if (tex == nullptr) {
    return nullptr;
  }
  /* Whole-texture sampled view (all mips + layers from the offset) at the native view
   * dimension. Cube textures (stored as 2D + 6 layers) get an explicit Cube view so
   * WGSL `texture_cube` sampling binds. */
  wgpu::TextureViewDescriptor d = {};
  d.format = wgpu_format_;
  d.dimension = to_wgpu_view_dimension(type_);
  d.baseMipLevel = uint32_t(std::max(mip_offset_, 0));
  d.baseArrayLayer = uint32_t(std::max(layer_offset_, 0));
  d.aspect = wgpu::TextureAspect::All;
  return tex.CreateView(&d);
}

void WGPUTexture::adopt_external(const wgpu::Texture &texture,
                                 wgpu::TextureFormat wgpu_format,
                                 int width,
                                 int height)
{
  /* Wrap an externally-owned device texture (the window surface's per-frame
   * GetCurrentTexture()) as this gpu::Texture. No allocate(): the surface owns the
   * device texture. Only the fields the framebuffer color path reads are set —
   * texture_/wgpu_format_ (attachment view + pipeline target format) and w_/h_
   * (update_size); format_/format_flag_ are set to a plain colour so the depth
   * branch in begin_load_pass never misfires. */
  texture_ = texture;
  wgpu_format_ = wgpu_format;
  conv_ = ConvClass::Direct;
  source_ = nullptr;
  source_buffer_ = nullptr;
  snorm16_emulated_ = false;
  is_texture_view_ = false;
  w_ = std::max(width, 1);
  h_ = std::max(height, 1);
  d_ = 1;
  type_ = GPU_TEXTURE_2D;
  mipmaps_ = 1;
  mip_min_ = 0;
  mip_max_ = 0;
  format_ = TextureFormat::UNORM_8_8_8_8;
  format_flag_ = GPU_FORMAT_NORMALIZED_INTEGER;
  gpu_image_usage_flags_ = GPU_TEXTURE_USAGE_ATTACHMENT;
}

void WGPUTexture::clear(const double4 data)
{
  if (texture_ == nullptr) {
    return;
  }
  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return;
  }

  /* Depth/stencil: cleared via a render pass with a depth clear (no draw / shader
   * needed). Colour: fill a host buffer with the packed clear texel and upload
   * with writeTexture — works for every CopyDst format regardless of
   * renderability, and reuses the proven writeTexture path. */
  if (format_flag_ & GPU_FORMAT_DEPTH) {
    /* Depth/stencil clear to a uniform value: a render pass with only a
     * depth-stencil attachment and loadOp=Clear (no draw, no pipeline, no shader).
     * Requires RenderAttachment usage (GPU_TEXTURE_USAGE_ATTACHMENT). Proven live
     * in sandbox/wgpu-texture-formats/ (Depth32Float clear+readback). */
    wgpu::TextureView view = texture_.CreateView();

    wgpu::RenderPassDepthStencilAttachment dsa = {};
    dsa.view = view;
    dsa.depthLoadOp = wgpu::LoadOp::Clear;
    dsa.depthStoreOp = wgpu::StoreOp::Store;
    /* Dawn rejects a non-finite depthClearValue at beginRenderPass; clamp to a finite
     * far value (1.0) so a NaN/Inf clear value cannot abort the render pass. */
    dsa.depthClearValue = std::isfinite(float(data[0])) ? float(data[0]) : 1.0f;
    if (format_ == TextureFormat::SFLOAT_32_DEPTH_UINT_8) {
      dsa.stencilLoadOp = wgpu::LoadOp::Clear;
      dsa.stencilStoreOp = wgpu::StoreOp::Store;
      dsa.stencilClearValue = uint32_t(data[1]);
    }

    wgpu::RenderPassDescriptor rp = {};
    rp.colorAttachmentCount = 0;
    rp.colorAttachments = nullptr;
    rp.depthStencilAttachment = &dsa;

    wgpu::Device device = ctx->device_get();
    wgpu::CommandEncoder enc = device.CreateCommandEncoder();
    wgpu::RenderPassEncoder pass = enc.BeginRenderPass(&rp);
    pass.End();
    wgpu::CommandBuffer cb = enc.Finish();
    ctx->queue_get().Submit(1, &cb);
    return;
  }

  const Repr repr = snorm16_emulated_ ? Repr::Snorm16 : repr_of(format_);
  if (repr == Repr::Compressed || repr == Repr::Unsupported) {
    return;
  }
  const int logical = to_component_len(format_);
  const int channels = device_channels(format_, conv_);
  const uint32_t texel_bytes = device_texel_bytes(format_, conv_, repr);
  const bool integer = repr_is_integer(repr);

  /* Build a single clear texel in the device layout. */
  std::vector<uint8_t> texel(texel_bytes, 0);
  if (repr == Repr::PackedR11G11B10) {
    uint32_t packed = pack_r11g11b10(float(data[0]), float(data[1]), float(data[2]));
    std::memcpy(texel.data(), &packed, 4);
  }
  else {
    const uint32_t dbytes = repr_comp_bytes(repr);
    for (int c = 0; c < channels; c++) {
      uint8_t *dc = texel.data() + size_t(c) * dbytes;
      const double v = (c < logical) ? data[c] : (integer ? 1.0 : 1.0);
      if (integer) {
        dev_write_int(dc, repr, int64_t(v));
      }
      else {
        dev_write_float(dc, repr, float(v));
      }
    }
  }

  /* Replicate across every mip level in [mip_min_, mip_max_] and all layers. */
  for (int mip = mip_min_; mip <= mip_max_; mip++) {
    int mip_size[3] = {1, 1, 1};
    mip_size_get(mip, mip_size);
    const uint32_t ex = uint32_t(std::max(mip_size[0], 1));
    const uint32_t ey = uint32_t(std::max(mip_size[1], 1));
    const uint32_t ez = uint32_t(std::max(mip_size[2], 1));
    const size_t sample_count = size_t(ex) * ey * ez;

    std::vector<uint8_t> buffer(sample_count * texel_bytes);
    for (size_t i = 0; i < sample_count; i++) {
      std::memcpy(buffer.data() + i * texel_bytes, texel.data(), texel_bytes);
    }

    wgpu::TexelCopyTextureInfo dst = {};
    dst.texture = texture_;
    dst.mipLevel = uint32_t(mip);
    dst.origin = {0, 0, 0};
    dst.aspect = wgpu::TextureAspect::All;

    wgpu::TexelCopyBufferLayout layout = {};
    layout.offset = 0;
    layout.bytesPerRow = ex * texel_bytes;
    layout.rowsPerImage = ey;

    wgpu::Extent3D write_size = {ex, ey, ez};
    ctx->queue_get().WriteTexture(&dst, buffer.data(), buffer.size(), &layout, &write_size);
  }
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Read / copy / mipmap / view state
 * \{ */

void WGPUTexture::read(int mip, eGPUDataFormat format, void *data)
{
  if (texture_ == nullptr || data == nullptr) {
    return;
  }
  const Repr repr = snorm16_emulated_ ? Repr::Snorm16 : repr_of(format_);
  if (repr == Repr::Compressed || repr == Repr::Unsupported) {
    BLI_assert_msg(0, "WGPUTexture::read: compressed / unsupported format readback");
    return;
  }
  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return;
  }

  int mip_size[3] = {1, 1, 1};
  mip_size_get(mip, mip_size);
  const uint32_t ex = uint32_t(std::max(mip_size[0], 1));
  const uint32_t ey = uint32_t(std::max(mip_size[1], 1));
  const uint32_t ez = uint32_t(std::max(mip_size[2], 1));
  const uint32_t texel_bytes = device_texel_bytes(format_, conv_, repr);

  /* CopyTextureToBuffer requires a 256-byte-aligned bytesPerRow; the padded rows
   * are stripped after mapping. */
  const uint32_t row_bytes = ex * texel_bytes;
  const uint32_t bytes_per_row = uint32_t(align_up(row_bytes, 256));
  const size_t staging_size = size_t(bytes_per_row) * ey * ez;

  const wgpu::TextureAspect aspect = (format_flag_ & GPU_FORMAT_DEPTH) ?
                                         wgpu::TextureAspect::DepthOnly :
                                         wgpu::TextureAspect::All;

  wgpu::Device device = ctx->device_get();

  wgpu::BufferDescriptor bd = {};
  bd.size = staging_size;
  bd.usage = wgpu::BufferUsage::MapRead | wgpu::BufferUsage::CopyDst;
  wgpu::Buffer staging = device.CreateBuffer(&bd);
  if (staging == nullptr) {
    return;
  }

  wgpu::TexelCopyTextureInfo src = {};
  src.texture = texture_;
  src.mipLevel = uint32_t(mip);
  src.origin = {0, 0, 0};
  src.aspect = aspect;

  wgpu::TexelCopyBufferInfo dst = {};
  dst.buffer = staging;
  dst.layout.offset = 0;
  dst.layout.bytesPerRow = bytes_per_row;
  dst.layout.rowsPerImage = ey;

  wgpu::Extent3D copy_size = {ex, ey, ez};
  wgpu::CommandEncoder enc = device.CreateCommandEncoder();
  enc.CopyTextureToBuffer(&src, &dst, &copy_size);
  wgpu::CommandBuffer cb = enc.Finish();
  ctx->queue_get().Submit(1, &cb);

  bool ok = false;
  wgpu::Future f = staging.MapAsync(wgpu::MapMode::Read,
                                    0,
                                    staging_size,
                                    wgpu::CallbackMode::WaitAnyOnly,
                                    [&](wgpu::MapAsyncStatus s, wgpu::StringView) {
                                      ok = (s == wgpu::MapAsyncStatus::Success);
                                    });
  ctx->instance_get().WaitAny(f, UINT64_MAX);
  if (!ok) {
    return;
  }
  const uint8_t *mapped = static_cast<const uint8_t *>(
      staging.GetConstMappedRange(0, staging_size));
  if (mapped == nullptr) {
    staging.Unmap();
    return;
  }

  /* Strip the 256-byte row padding into a tightly-packed device buffer. */
  const size_t sample_count = size_t(ex) * ey * ez;
  std::vector<uint8_t> device_data(sample_count * texel_bytes);
  for (uint32_t z = 0; z < ez; z++) {
    for (uint32_t y = 0; y < ey; y++) {
      const uint8_t *s = mapped + (size_t(z) * ey + y) * bytes_per_row;
      uint8_t *d = device_data.data() + (size_t(z) * ey + y) * ex * texel_bytes;
      std::memcpy(d, s, row_bytes);
    }
  }
  staging.Unmap();

  convert_device_to_host(static_cast<uint8_t *>(data), device_data.data(), sample_count, format);
}

void WGPUTexture::copy_to(Texture *tex, IndexRange mip_levels)
{
  WGPUTexture *dst = static_cast<WGPUTexture *>(tex);
  if (texture_ == nullptr || dst == nullptr || dst->texture_ == nullptr) {
    return;
  }
  if (mip_levels.is_empty()) {
    return;
  }
  WGPUContext *ctx = active_context();
  if (ctx == nullptr) {
    return;
  }

  wgpu::Device device = ctx->device_get();
  wgpu::CommandEncoder enc = device.CreateCommandEncoder();
  for (const int64_t mip : mip_levels) {
    int mip_size[3] = {1, 1, 1};
    mip_size_get(int(mip), mip_size);

    wgpu::TexelCopyTextureInfo s = {};
    s.texture = texture_;
    s.mipLevel = uint32_t(mip);
    s.origin = {0, 0, 0};
    s.aspect = wgpu::TextureAspect::All;

    wgpu::TexelCopyTextureInfo d = {};
    d.texture = dst->texture_;
    d.mipLevel = uint32_t(mip);
    d.origin = {0, 0, 0};
    d.aspect = wgpu::TextureAspect::All;

    wgpu::Extent3D size = {uint32_t(std::max(mip_size[0], 1)),
                           uint32_t(std::max(mip_size[1], 1)),
                           uint32_t(std::max(mip_size[2], 1))};
    enc.CopyTextureToTexture(&s, &d, &size);
  }
  wgpu::CommandBuffer cb = enc.Finish();
  ctx->queue_get().Submit(1, &cb);
}

void WGPUTexture::generate_mipmap()
{
  /* WebGPU has no built-in mipmap generation; a blit-chain pipeline lands with the
   * shader/pipeline path. No-op for now (single-mip textures are unaffected). */
}

void WGPUTexture::swizzle_set(const char swizzle_mask[4])
{
  std::memcpy(swizzle_, swizzle_mask, 4);
}

void WGPUTexture::mip_range_set(int min, int max)
{
  mip_min_ = min;
  mip_max_ = max;
}

/** \} */

}  // namespace blender::gpu::webgpu
