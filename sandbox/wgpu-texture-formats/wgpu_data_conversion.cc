/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * Implements the RGB→RGBA promotion for the 13 three-channel Blender formats.
 * See wgpu_data_conversion.hh. */

#include "wgpu_data_conversion.hh"

#include <cstring>

namespace blender::gpu::webgpu {

PromotionPlan promotion_plan(TextureFormat format)
{
  /* Only the ConvClass::PromoteRGBA formats need widening; {comp_bytes, type}
   * per the format's element type. */
  switch (format) {
    case TextureFormat::UNORM_8_8_8:   return {true, 1, ScalarType::Unorm};
    case TextureFormat::UNORM_16_16_16:return {true, 2, ScalarType::Unorm};
    case TextureFormat::SNORM_8_8_8:   return {true, 1, ScalarType::Snorm};
    case TextureFormat::SNORM_16_16_16:return {true, 2, ScalarType::Snorm};
    case TextureFormat::UINT_8_8_8:    return {true, 1, ScalarType::Uint};
    case TextureFormat::UINT_16_16_16: return {true, 2, ScalarType::Uint};
    case TextureFormat::UINT_32_32_32: return {true, 4, ScalarType::Uint};
    case TextureFormat::SINT_8_8_8:    return {true, 1, ScalarType::Sint};
    case TextureFormat::SINT_16_16_16: return {true, 2, ScalarType::Sint};
    case TextureFormat::SINT_32_32_32: return {true, 4, ScalarType::Sint};
    case TextureFormat::SFLOAT_16_16_16: return {true, 2, ScalarType::Float};
    case TextureFormat::SFLOAT_32_32_32: return {true, 4, ScalarType::Float};
    case TextureFormat::SRGBA_8_8_8:   return {true, 1, ScalarType::Unorm};
    default:                           return {false, 0, ScalarType::Unorm};
  }
}

void opaque_alpha_bytes(ScalarType type, uint32_t comp_bytes, uint8_t *out)
{
  std::memset(out, 0, comp_bytes);
  switch (type) {
    case ScalarType::Unorm:
      /* max value: 0xFF / 0xFFFF / 0xFFFFFFFF */
      std::memset(out, 0xFF, comp_bytes);
      break;
    case ScalarType::Snorm:
      /* max positive: 0x7F / 0x7FFF (little-endian: high byte holds 0x7F) */
      std::memset(out, 0xFF, comp_bytes);
      out[comp_bytes - 1] = 0x7F;
      break;
    case ScalarType::Uint:
    case ScalarType::Sint:
      out[0] = 0x01; /* integer 1, little-endian */
      break;
    case ScalarType::Float:
      if (comp_bytes == 2) {           /* half 1.0 = 0x3C00 */
        out[0] = 0x00; out[1] = 0x3C;
      }
      else if (comp_bytes == 4) {      /* float 1.0 = 0x3F800000 */
        out[0] = 0x00; out[1] = 0x00; out[2] = 0x80; out[3] = 0x3F;
      }
      break;
  }
}

size_t promoted_byte_size(uint32_t width, uint32_t height, uint32_t comp_bytes)
{
  return size_t(width) * height * 4u * comp_bytes;
}

bool promote_rgb_to_rgba(const uint8_t *src, size_t src_size,
                         uint8_t *dst, size_t dst_size,
                         uint32_t width, uint32_t height,
                         const PromotionPlan &plan)
{
  if (!plan.needed || plan.comp_bytes == 0) {
    return false;
  }
  const uint32_t cb = plan.comp_bytes;
  const size_t need_src = size_t(width) * height * 3u * cb;
  const size_t need_dst = promoted_byte_size(width, height, cb);
  if (src_size < need_src || dst_size < need_dst) {
    return false;
  }
  uint8_t alpha[4];
  opaque_alpha_bytes(plan.type, cb, alpha);

  const size_t pixels = size_t(width) * height;
  for (size_t p = 0; p < pixels; p++) {
    const uint8_t *s = src + p * 3u * cb;
    uint8_t *d = dst + p * 4u * cb;
    std::memcpy(d, s, 3u * cb);       /* R,G,B verbatim */
    std::memcpy(d + 3u * cb, alpha, cb); /* opaque A */
  }
  return true;
}

std::vector<uint8_t> promote_for_upload(TextureFormat format,
                                        const std::vector<uint8_t> &rgb_src,
                                        uint32_t width, uint32_t height)
{
  const PromotionPlan plan = promotion_plan(format);
  if (!plan.needed) {
    return rgb_src; /* Direct formats upload verbatim */
  }
  std::vector<uint8_t> out(promoted_byte_size(width, height, plan.comp_bytes));
  promote_rgb_to_rgba(rgb_src.data(), rgb_src.size(), out.data(), out.size(), width, height, plan);
  return out;
}

}  // namespace blender::gpu::webgpu
