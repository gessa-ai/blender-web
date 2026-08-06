/* SPDX-FileCopyrightText: 2024 Blender Authors
 * SPDX-FileCopyrightText: 2026 blender-web contributors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Ported for the web from source/blender/gpu/vulkan/vk_texture.hh @ fbe6228777e7 */

/** \file
 * \ingroup gpu
 *
 * WGPUTexture — the WebGPU `gpu::Texture` implementation. Wraps a `wgpu::Texture`
 * created from the T9 format table (wgpu_texture_format) with device-probed usage;
 * uploads dispatch on ConvClass (Direct memcpy vs RGB→RGBA promotion) via
 * wgpu_data_conversion with 256-byte bytesPerRow alignment; reads go through a
 * MAP_READ staging buffer. Modelled on VKTexture; the standalone proof of the
 * format/conversion/round-trip paths is sandbox/wgpu-texture-formats/. */

#pragma once

#include "webgpu/webgpu_cpp.h"

#include "gpu_texture_private.hh"

#include "wgpu_texture_format.hh"

namespace blender::gpu::webgpu {

class WGPUTexture : public Texture {
 private:
  /** The device texture (null until init_internal). */
  wgpu::Texture texture_ = nullptr;
  /** The WebGPU format actually created (promotion applied — see to_wgpu_format). */
  wgpu::TextureFormat wgpu_format_ = wgpu::TextureFormat::Undefined;
  /** How CPU pixel data maps to the device format (Direct / PromoteRGBA / ...). */
  ConvClass conv_ = ConvClass::Direct;
  /** For texture views: the source texture this view aliases (not owned). */
  WGPUTexture *source_ = nullptr;
  /** For buffer textures (GPU_texture_create_from_vertbuf): the backing vertex
   * buffer. Not owned. WebGPU has no texel-buffer texture, so sampling is
   * forwarded to the buffer (bind-group assembly, lane A) — see init_internal(VertBuf*). */
  VertBuf *source_buffer_ = nullptr;
  /** View parameters (set by init_internal(src, ...)). */
  int mip_offset_ = 0;
  int layer_offset_ = 0;
  bool use_stencil_ = false;
  /** SNORM_16 family has no WebGPU format at the pin (notes/gpu-t9pre-findings.md
   * §5): emulated in a matching-width *Uint* texture with byte-identical SNORM bit
   * patterns (exact CPU round-trip; shader-sample remap deferred). */
  bool snorm16_emulated_ = false;
  /** Current swizzle (GPU_texture_swizzle_set); applied at view creation. */
  char swizzle_[4] = {'r', 'g', 'b', 'a'};

 public:
  WGPUTexture(const char *name) : Texture(name) {}
  virtual ~WGPUTexture() override;

  void generate_mipmap() override;
  void copy_to(Texture *tex, IndexRange mip_levels) override;
  void clear(const double4 data) override;
  void swizzle_set(const char swizzle_mask[4]) override;
  void mip_range_set(int min, int max) override;
  void read(int mip, eGPUDataFormat format, void *data) override;

  void update_sub(int mip,
                  int offset[3],
                  int extent[3],
                  eGPUDataFormat format,
                  const void *data,
                  uint unpack_row_length) override;
  void update_sub(int offset[3],
                  int extent[3],
                  eGPUDataFormat format,
                  GPUPixelBuffer *pixbuf) override;

  /** The device texture (for framebuffer attachment / bind groups). */
  wgpu::Texture &texture() { return texture_; }
  wgpu::TextureFormat wgpu_format() const { return wgpu_format_; }

  /** A view suitable for a WGSL storage-image binding (`texture_storage_*`): a
   * single mip level with the texture's native format and view dimension. WebGPU
   * rejects a multi-mip or cube view for a storage binding. Consumed by the
   * compute-dispatch / draw bind-group builders (GPU_texture_image_bind path). */
  wgpu::TextureView image_view();

  /** A view suitable for a WGSL sampled-texture binding (`texture_*<f32>` etc.):
   * the whole texture (all mips/layers) at its native view dimension. Consumed by
   * the draw bind-group builder (GPU_texture_bind path). */
  wgpu::TextureView sampled_view(
      wgpu::TextureViewDimension override_dim = wgpu::TextureViewDimension::Undefined);

  /** True for a buffer texture (GPU_texture_create_from_vertbuf): it has NO device
   * texture (source_buffer_ set, texture_ null). WGSL has no texel-buffer type, so
   * such a bind is a read-only storage-buffer entry, not a texture+sampler — the
   * draw/compute bind-group builders skip it in their sampled-texture loop. */
  bool is_buffer_texture() const
  {
    return source_buffer_ != nullptr;
  }

  /** Adopt an externally-owned wgpu::Texture (a surface's GetCurrentTexture()) as
   * this gpu::Texture WITHOUT allocating a device texture, setting the base
   * dimensions/format so framebuffer attachment + target_formats resolve. The handle
   * is ref-held until re-adopted; the surface governs its per-frame validity, so
   * re-adopt each frame (WGPUContext::sync_backbuffer). Web windowed back-buffer. */
  void adopt_external(const wgpu::Texture &texture,
                      wgpu::TextureFormat wgpu_format,
                      int width,
                      int height);

 protected:
  bool init_internal() override;
  bool init_internal(VertBuf *vbo) override;
  bool init_internal(gpu::Texture *src, int mip_offset, int layer_offset, bool use_stencil)
      override;

 private:
  /** Create `texture_` from the base-class format_/type_/w_/h_/d_/usage; returns
   * false on failure. Shared by the 1D/2D/3D/cube init_internal path. */
  bool allocate();

  /** Convert `sample_count` tightly-packed host texels (`host_format` scalars, one
   * per logical component) into this texture's device byte layout, and the reverse.
   * WebGPU copies move raw bytes, so all pixel-format conversion is CPU-side here. */
  void convert_host_to_device(uint8_t *dst,
                              const uint8_t *src,
                              size_t sample_count,
                              eGPUDataFormat host_format) const;
  void convert_device_to_host(uint8_t *dst,
                              const uint8_t *src,
                              size_t sample_count,
                              eGPUDataFormat host_format) const;
};

}  // namespace blender::gpu::webgpu
