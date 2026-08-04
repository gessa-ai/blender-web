/* SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * M3.T9.pre — WebGPU pixel data conversion (standalone, drop-in for
 * `source/blender/gpu/webgpu/wgpu_data_conversion.cc`).
 *
 * WebGPU (like Metal) has no 3-channel texture formats, so the 13 three-channel
 * Blender formats (ConvClass::PromoteRGBA in the format table) must be widened to
 * 4 channels on UPLOAD, with an opaque alpha appended per element. This is the
 * dominant real conversion the table demands (the rest are Direct memcpy). Depth
 * and compressed formats have their own copy semantics handled by the harness.
 *
 * The transform is Blender-source (tightly-packed RGB rows) → WebGPU-source
 * (tightly-packed RGBA rows). Copy-layout row alignment (WebGPU's 256-byte
 * bytesPerRow for CopyBufferToTexture) is a separate concern applied at copy time,
 * not here (queue.writeTexture has no such requirement). */

#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

#include "wgpu_texture_format.hh"

namespace blender::gpu::webgpu {

/** Scalar element type — selects the opaque-alpha value for promotion. */
enum class ScalarType : uint8_t { Unorm, Snorm, Uint, Sint, Float };

/** How to promote one PromoteRGBA format. `needed` is false for non-promoted
 * formats (they upload verbatim). */
struct PromotionPlan {
  bool needed = false;
  uint32_t comp_bytes = 0; /* bytes per channel (1/2/4) */
  ScalarType type = ScalarType::Unorm;
};

/** The plan for a Blender format (PromoteRGBA formats only need promotion). */
PromotionPlan promotion_plan(TextureFormat format);

/** Bytes of the promoted (RGBA) buffer for a width×height image. */
size_t promoted_byte_size(uint32_t width, uint32_t height, uint32_t comp_bytes);

/** Widen tightly-packed RGB rows to tightly-packed RGBA rows, appending the
 * type's opaque alpha per pixel. `src` is width*height*3*comp_bytes bytes; `dst`
 * must be promoted_byte_size(). Returns false on a size mismatch. */
bool promote_rgb_to_rgba(const uint8_t *src, size_t src_size,
                         uint8_t *dst, size_t dst_size,
                         uint32_t width, uint32_t height,
                         const PromotionPlan &plan);

/** Convenience: allocate + promote a source RGB buffer for `format`. */
std::vector<uint8_t> promote_for_upload(TextureFormat format,
                                        const std::vector<uint8_t> &rgb_src,
                                        uint32_t width, uint32_t height);

/** The opaque-alpha byte pattern for a (type, comp_bytes), little-endian.
 * Exposed for tests. Writes `comp_bytes` bytes to `out`. */
void opaque_alpha_bytes(ScalarType type, uint32_t comp_bytes, uint8_t *out);

}  // namespace blender::gpu::webgpu
