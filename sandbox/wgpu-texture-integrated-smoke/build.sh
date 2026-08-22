#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Device-free native/Wasm parity driver for the canonical in-tree WebGPU
# texture-format table and RGB-to-RGBA conversion module. Invoke through
# harness/buildwrap.sh.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WEBGPU_SOURCE="${BW_INTEGRATED_TEXTURE_SOURCE_DIR:-$ROOT/upstream/source/blender/gpu/webgpu}"
DAWN_SRC="${DAWN_SRC:-$ROOT/build-dawn/dawn}"
DAWN_PIN="36cf1fae0cd8a81a4fb4580751648b80b2e6255c"
NATIVE_BUILD="${NATIVE_BUILD:-$ROOT/build-dawn/probe-build}"
WASM_BUILD="${WASM_BUILD:-$ROOT/build-deps/t9-integrated/wasm-build}"
OUT="${OUT:-$ROOT/build-deps/t9-integrated/evidence}"
EMSDK="${EMSDK:-$ROOT/tools/emsdk}"
NODE="${NODE:-$EMSDK/node/22.16.0_64bit/bin/node}"
PYBIN="$ROOT/.host-tools/bin/python3.13"
HOST_CMAKE="${HOST_CMAKE:-$ROOT/.host-tools/bin/cmake}"
WASM_INCLUDE="$ROOT/lib/wasm/include"

case "$(uname -s):$(uname -m)" in
  Linux:x86_64)
    CMAKE_HOST_ARGS=(-U CMAKE_OSX_DEPLOYMENT_TARGET)
    NATIVE_FMT_INCLUDE="$ROOT/lib/linux_x64/fmt/include"
    ;;
  Darwin:arm64)
    CMAKE_HOST_ARGS=(-DCMAKE_OSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-11.2}")
    NATIVE_FMT_INCLUDE="$ROOT/lib/macos_arm64/fmt/include"
    ;;
  *)
    echo "ERROR: supported hosts are Linux x86_64 and macOS arm64" >&2
    exit 1
    ;;
esac

require_file()
{
  if [ ! -f "$1" ]; then
    echo "ERROR: required file missing: $1" >&2
    exit 1
  fi
}

sha256_file()
{
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo "ERROR: no SHA-256 tool available" >&2
    return 1
  fi
}

source_digest()
{
  local files=(
    GPU_format.hh
    GPU_framebuffer.hh
    GPU_texture.hh
    intern/gpu_texture_private.hh
    ../blenlib/BLI_assert.h
    ../blenlib/intern/BLI_assert.cc
    webgpu/wgpu_common.hh
    webgpu/wgpu_texture_format.cc
    webgpu/wgpu_texture_format.hh
    webgpu/wgpu_texture_format_list.h
    webgpu/wgpu_texture.cc
    webgpu/wgpu_texture.hh
    webgpu/wgpu_framebuffer.cc
    webgpu/wgpu_framebuffer.hh
    webgpu/wgpu_data_conversion.cc
    webgpu/wgpu_data_conversion.hh
    shaders/gpu_shader_2D_update_mipmaps.bsl.hh
    vulkan/vk_data_conversion.hh
    vulkan/tests/vk_data_conversion_test.cc
    intern/gpu_texture.cc
    ../draw/engines/gpencil/gpencil_engine_c.cc
    ../draw/engines/eevee/eevee_renderbuffers.cc
    ../editors/sculpt_paint/paint_cursor.cc
    ../imbuf/intern/util_gpu.cc
  )
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$ROOT/upstream/source/blender/gpu" && sha256sum "${files[@]}" | sha256sum | awk '{print $1}')
  else
    (cd "$ROOT/upstream/source/blender/gpu" && shasum -a 256 "${files[@]}" | shasum -a 256 | awk '{print $1}')
  fi
}

require_file "$PYBIN"
require_file "$HOST_CMAKE"
require_file "$ROOT/scripts/ninja-locked.sh"
require_file "$ROOT/sandbox/series-replay/verify.py"
require_file "$HERE/integrated_texture_test.cc"
require_file "$ROOT/sandbox/wgpu-texture-wasm-smoke/CMakeLists.txt"
require_file "$ROOT/upstream/source/blender/gpu/GPU_format.hh"
require_file "$ROOT/upstream/source/blender/gpu/GPU_texture.hh"
require_file "$ROOT/upstream/source/blender/gpu/GPU_framebuffer.hh"
require_file "$ROOT/upstream/source/blender/gpu/intern/gpu_texture_private.hh"
require_file "$ROOT/upstream/source/blender/gpu/vulkan/vk_data_conversion.hh"
require_file "$ROOT/upstream/source/blender/gpu/vulkan/tests/vk_data_conversion_test.cc"
require_file "$ROOT/upstream/source/blender/gpu/intern/gpu_texture.cc"
require_file "$ROOT/upstream/source/blender/gpu/shaders/gpu_shader_2D_update_mipmaps.bsl.hh"
require_file "$ROOT/upstream/source/blender/draw/engines/gpencil/gpencil_engine_c.cc"
require_file "$ROOT/upstream/source/blender/draw/engines/eevee/eevee_renderbuffers.cc"
require_file "$ROOT/upstream/source/blender/editors/sculpt_paint/paint_cursor.cc"
require_file "$ROOT/upstream/source/blender/imbuf/intern/util_gpu.cc"
require_file "$ROOT/platform_web/shell/wgpu-preinit-worker.js"
require_file "$EMSDK/emsdk_env.sh"
require_file "$EMSDK/upstream/emscripten/emcmake"
require_file "$NODE"
require_file "$NATIVE_FMT_INCLUDE/fmt/ranges.h"
require_file "$WASM_INCLUDE/fmt/ranges.h"
for source_name in \
  wgpu_texture_format.cc \
  wgpu_texture_format.hh \
  wgpu_texture_format_list.h \
  wgpu_common.hh \
  wgpu_texture.cc \
  wgpu_texture.hh \
  wgpu_framebuffer.cc \
  wgpu_framebuffer.hh \
  wgpu_data_conversion.cc \
  wgpu_data_conversion.hh
do
  require_file "$WEBGPU_SOURCE/$source_name"
done

if ! cmp -s "$NATIVE_FMT_INCLUDE/fmt/ranges.h" "$WASM_INCLUDE/fmt/ranges.h"; then
  echo "ERROR: native and Wasm fmt headers differ" >&2
  exit 1
fi

RGB9E5_TEXTURE_SOURCE="$WEBGPU_SOURCE/wgpu_texture.cc"
if [ "$(grep -Fc 'PackedRGB9E5' "$RGB9E5_TEXTURE_SOURCE")" -ne 6 ] ||
   [ "$(grep -Fc 'case TextureFormat::UFLOAT_9_9_9_EXP_5:' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   [ "$(grep -Ec '(^|[^[:alnum:]_])pack_rgb9e5_ufloat\(' "$RGB9E5_TEXTURE_SOURCE")" -ne 2 ] ||
   [ "$(grep -Fc 'unpack_rgb9e5_ufloat(packed, rgb);' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   grep -Fq 'shared-exponent pack not implemented' "$RGB9E5_TEXTURE_SOURCE"
then
  echo "ERROR: canonical RGB9E5 texture wiring differs" >&2
  exit 1
fi

R11_CONVERSION_SOURCE="$WEBGPU_SOURCE/wgpu_data_conversion.cc"
R11_CONVERSION_HEADER="$WEBGPU_SOURCE/wgpu_data_conversion.hh"
if [ "$(grep -Ec '^uint32_t pack_r11g11b10_ufloat\(' "$R11_CONVERSION_SOURCE")" -ne 1 ] ||
   [ "$(grep -Ec '^void unpack_r11g11b10_ufloat\(' "$R11_CONVERSION_SOURCE")" -ne 1 ] ||
   [ "$(grep -Ec '^uint32_t pack_r11g11b10_ufloat\(' "$R11_CONVERSION_HEADER")" -ne 1 ] ||
   [ "$(grep -Ec '^void unpack_r11g11b10_ufloat\(' "$R11_CONVERSION_HEADER")" -ne 1 ] ||
   [ "$(grep -Ec '(^|[^[:alnum:]_])pack_r11g11b10_ufloat\(' "$RGB9E5_TEXTURE_SOURCE")" -ne 2 ] ||
   [ "$(grep -Ec '(^|[^[:alnum:]_])unpack_r11g11b10_ufloat\(' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   grep -Fq 'float_to_ufloat' "$RGB9E5_TEXTURE_SOURCE" ||
   grep -Fq 'static uint32_t pack_r11g11b10' "$RGB9E5_TEXTURE_SOURCE"
then
  echo "ERROR: canonical RG11B10 Vulkan-parity wiring differs" >&2
  exit 1
fi

if [ "$(grep -Fc 'to_bytesize(format_, format)' "$RGB9E5_TEXTURE_SOURCE")" -ne 4 ] ||
   grep -Fq 'const size_t host_texel = size_t(to_component_len(format_)) * to_bytesize(format);' \
     "$RGB9E5_TEXTURE_SOURCE"
then
  echo "ERROR: canonical strided-upload host-texel sizing differs" >&2
  exit 1
fi

FORMAT_SOURCE="$WEBGPU_SOURCE/wgpu_texture_format.cc"
FORMAT_HEADER="$WEBGPU_SOURCE/wgpu_texture_format.hh"
COMMON_HEADER="$WEBGPU_SOURCE/wgpu_common.hh"
FRAMEBUFFER_SOURCE="$WEBGPU_SOURCE/wgpu_framebuffer.cc"
FRAMEBUFFER_HEADER="$WEBGPU_SOURCE/wgpu_framebuffer.hh"
TEXTURE_HEADER="$WEBGPU_SOURCE/wgpu_texture.hh"
MIPMAP_ORACLE="$ROOT/upstream/source/blender/gpu/shaders/gpu_shader_2D_update_mipmaps.bsl.hh"
if [ "$(grep -Fc 'inline bool mipmap_axis_plan(' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'inline const char *mipmap_float_shader_source()' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'wgsl_source = mipmap_float_shader_source();' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'return 2u | (input_size & 1u);' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc '1.0 / f32(2u * output_size + 1u)' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'int2 kernel_size_from_input_size(int2 input_size)' "$MIPMAP_ORACLE")" -ne 1 ] ||
   [ "$(grep -Fc 'float rcp = 1.0f / (2 * num_dst_pixels + 1);' "$MIPMAP_ORACLE")" -ne 1 ] ||
   [ "$(grep -Fc 'float w2 = 1.0f - w0 - w1;' "$MIPMAP_ORACLE")" -ne 1 ] ||
   grep -Fq 'odd edges clamp exactly as native blit fallbacks do' "$RGB9E5_TEXTURE_SOURCE"
then
  echo "ERROR: canonical odd-dimension mipmap kernel wiring differs" >&2
  exit 1
fi
if [ "$(grep -Ec '^bool format_creation_supported\(' "$FORMAT_SOURCE")" -ne 1 ] ||
   [ "$(grep -Ec '^bool format_creation_supported\(' "$FORMAT_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'if (!format_creation_supported(fi.gate, format_features)) {' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'TextureFormatFeatures format_features;' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'render_attachment_supported(wgpu_format_, format_features)' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   grep -Fq 'RenderAttachmentFeatures' "$FORMAT_HEADER" ||
   grep -Fq 'RenderAttachmentFeatures' "$FORMAT_SOURCE" ||
   grep -Fq 'RenderAttachmentFeatures' "$HERE/integrated_texture_test.cc"
then
  echo "ERROR: canonical feature-aware texture creation wiring differs" >&2
  exit 1
fi

if [ "$(grep -Fc 'inline bool texture_allocation_supported(' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc '!texture_allocation_supported(' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ]
then
  echo "ERROR: canonical texture allocation-limit wiring differs" >&2
  exit 1
fi

if [ "$(grep -Fc 'inline bool texture_upload_layout(' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'inline bool texture_region_fits(' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'texture_upload_layout(' "$RGB9E5_TEXTURE_SOURCE")" -ne 3 ] ||
   [ "$(grep -Fc 'texture_region_fits(' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ]
then
  echo "ERROR: canonical texture upload-layout wiring differs" >&2
  exit 1
fi

if [ "$(grep -Fc 'inline bool texture_readback_layout(' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'texture_readback_layout(' "$RGB9E5_TEXTURE_SOURCE")" -ne 2 ]
then
  echo "ERROR: canonical texture readback-layout wiring differs" >&2
  exit 1
fi

if [ "$(grep -Fc 'inline bool framebuffer_read_layout(' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'inline bool framebuffer_read_extract(' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'void read_sub(int mip, int layer,' "$TEXTURE_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'void WGPUTexture::read_sub(int mip,' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'framebuffer_read_layout(' "$FRAMEBUFFER_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'framebuffer_read_extract(' "$FRAMEBUFFER_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'wtex->read_sub(mip, layer, format, tmp.data());' "$FRAMEBUFFER_SOURCE")" -ne 1 ] ||
   grep -Fq 'tex->read(0, format, tmp.data());' "$FRAMEBUFFER_SOURCE" ||
   grep -Fq 'tex->read_size_get(0, format)' "$FRAMEBUFFER_SOURCE"
then
  echo "ERROR: canonical framebuffer subresource-read wiring differs" >&2
  exit 1
fi

if [ "$(grep -Fc 'inline FramebufferClearPassStatus framebuffer_clear_pass_layer(' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'framebuffer_clear_pass_layer(' "$FRAMEBUFFER_SOURCE")" -ne 5 ] ||
   [ "$(grep -Fc 'clear_status == webgpu::FramebufferClearPassStatus::Invalid' "$FRAMEBUFFER_SOURCE")" -ne 2 ] ||
   [ "$(grep -Fc 'clear_status == webgpu::FramebufferClearPassStatus::Inactive' "$FRAMEBUFFER_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'clear_status == webgpu::FramebufferClearPassStatus::Active' "$FRAMEBUFFER_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'attachment_view(att, att.layer < 0 ? pass_layer : -1)' "$FRAMEBUFFER_SOURCE")" -ne 0 ]
then
  echo "ERROR: canonical framebuffer layered-clear wiring differs" >&2
  exit 1
fi

if [ "$(grep -Fc 'enum class FramebufferClearMethod : uint8_t {' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'enum class FramebufferClearAspect : uint8_t {' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'inline bool framebuffer_clear_plan(' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'bool convert_bottom_origin' "$COMMON_HEADER")" -ne 0 ] ||
   [ "$(grep -Fc 'inline FramebufferClearShaderType framebuffer_clear_color_shader_type(' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'inline const char *framebuffer_clear_shader_source(' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'framebuffer_clear_plan(' "$FRAMEBUFFER_SOURCE")" -ne 2 ] ||
   [ "$(grep -Fc 'ctx->is_window_backbuffer(this),' "$FRAMEBUFFER_SOURCE")" -ne 0 ] ||
   [ "$(grep -Fc 'framebuffer_clear_shader_source(' "$FRAMEBUFFER_SOURCE")" -ne 2 ] ||
   [ "$(grep -Fc 'framebuffer_clear_color_shader_type(' "$FRAMEBUFFER_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'submit_scissored_clear(' "$FRAMEBUFFER_SOURCE")" -ne 3 ] ||
   [ "$(grep -Fc 'submit_scissored_color_clear(' "$FRAMEBUFFER_SOURCE")" -ne 3 ] ||
   [ "$(grep -Fc 'submit_scissored_depth_stencil_clear(' "$FRAMEBUFFER_SOURCE")" -ne 2 ] ||
   [ "$(grep -Fc 'clear_attachment_full(' "$FRAMEBUFFER_SOURCE")" -ne 3 ] ||
   [ "$(grep -Fc 'color.loadOp = wgpu::LoadOp::Load;' "$FRAMEBUFFER_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'depth_stencil.depthLoadOp = wgpu::LoadOp::Load;' "$FRAMEBUFFER_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'pass.SetScissorRect(plan.x, plan.y, plan.width, plan.height);' "$FRAMEBUFFER_SOURCE")" -ne 2 ] ||
   [ "$(grep -Fc 'descriptor.multisample.count = sample_count;' "$FRAMEBUFFER_SOURCE")" -ne 2 ] ||
   [ "$(grep -Fc 'wgpu::StencilOperation::Replace' "$FRAMEBUFFER_SOURCE")" -ne 2 ] ||
   [ "$(grep -Fc 'pass.SetStencilReference(clear_stencil_value);' "$FRAMEBUFFER_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'ca.loadOp = (buffers & GPU_COLOR_BIT) ? wgpu::LoadOp::Clear :' "$FRAMEBUFFER_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'ca.loadOp = wgpu::LoadOp::Clear;' "$FRAMEBUFFER_SOURCE")" -ne 2 ]
then
  echo "ERROR: canonical framebuffer scissored-clear wiring differs" >&2
  exit 1
fi

mapfile -t CLEAR_PIPELINE_CREATE_LINES < <(
  grep -nF 'pipeline = device.CreateRenderPipeline(&descriptor);' "$FRAMEBUFFER_SOURCE" |
    cut -d: -f1
)
mapfile -t CLEAR_PIPELINE_NULL_LINES < <(
  grep -nF 'if (pipeline == nullptr) {' "$FRAMEBUFFER_SOURCE" | cut -d: -f1
)
mapfile -t CLEAR_PIPELINE_CACHE_LINES < <(
  grep -nE 'scissored_(color|depth)_clear_pipelines_\[pipeline_key\] = pipeline;' \
    "$FRAMEBUFFER_SOURCE" | cut -d: -f1
)
if [ "${#CLEAR_PIPELINE_CREATE_LINES[@]}" -ne 2 ] ||
   [ "${#CLEAR_PIPELINE_NULL_LINES[@]}" -ne 2 ] ||
   [ "${#CLEAR_PIPELINE_CACHE_LINES[@]}" -ne 2 ] ||
   [ "${CLEAR_PIPELINE_CREATE_LINES[0]}" -ge "${CLEAR_PIPELINE_NULL_LINES[0]}" ] ||
   [ "${CLEAR_PIPELINE_NULL_LINES[0]}" -ge "${CLEAR_PIPELINE_CACHE_LINES[0]}" ] ||
   [ "${CLEAR_PIPELINE_CREATE_LINES[1]}" -ge "${CLEAR_PIPELINE_NULL_LINES[1]}" ] ||
   [ "${CLEAR_PIPELINE_NULL_LINES[1]}" -ge "${CLEAR_PIPELINE_CACHE_LINES[1]}" ]
then
  echo "ERROR: scissored-clear pipelines publish before successful creation" >&2
  exit 1
fi

if [ "$(grep -Fc 'struct FramebufferDrawPassCount {' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'inline bool framebuffer_draw_pass_count_update(' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'inline FramebufferClearPassStatus framebuffer_draw_pass_layer(' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'framebuffer_draw_pass_count_update(' "$FRAMEBUFFER_SOURCE")" -ne 2 ] ||
   [ "$(grep -Fc 'framebuffer_draw_pass_layer(' "$FRAMEBUFFER_SOURCE")" -ne 2 ] ||
   [ "$(grep -Fc 'attachment_view(attachments_[GPU_FB_COLOR_ATTACHMENT0 + slot], force_layer)' "$FRAMEBUFFER_SOURCE")" -ne 0 ] ||
   [ "$(grep -Fc 'attachment_view(depth_attachment(), force_layer)' "$FRAMEBUFFER_SOURCE")" -ne 0 ]
then
  echo "ERROR: canonical framebuffer layered-draw wiring differs" >&2
  exit 1
fi

if [ "$(grep -Fc 'enum class FramebufferLoadClearScope : uint8_t {' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'inline FramebufferLoadClearScope framebuffer_load_clear_scope(' "$COMMON_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'bool materialize_layered_loadstore_clears();' "$FRAMEBUFFER_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'bool WGPUFrameBuffer::materialize_layered_loadstore_clears()' "$FRAMEBUFFER_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'framebuffer_load_clear_scope(' "$FRAMEBUFFER_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'clear_attachment_full(static_cast<GPUAttachmentType>(index), clear_value);' "$FRAMEBUFFER_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'if (!materialize_layered_loadstore_clears()) {' "$FRAMEBUFFER_SOURCE")" -ne 1 ]
then
  echo "ERROR: canonical framebuffer layered load-clear wiring differs" >&2
  exit 1
fi

MATERIALIZE_LOAD_CLEAR_LINE="$(grep -nF \
  'if (!materialize_layered_loadstore_clears()) {' \
  "$FRAMEBUFFER_SOURCE" | cut -d: -f1)"
BEGIN_LOAD_PASS_LINE="$(grep -nF \
  'wgpu::RenderPassEncoder WGPUFrameBuffer::begin_load_pass(' \
  "$FRAMEBUFFER_SOURCE" | cut -d: -f1)"
BEGIN_LOAD_COLOR_ATTACHMENTS_LINE="$(grep -nF \
  'std::vector<wgpu::RenderPassColorAttachment> color_atts;' \
  "$FRAMEBUFFER_SOURCE" | tail -n 1 | cut -d: -f1)"
if [ -z "$MATERIALIZE_LOAD_CLEAR_LINE" ] ||
   [ -z "$BEGIN_LOAD_PASS_LINE" ] ||
   [ -z "$BEGIN_LOAD_COLOR_ATTACHMENTS_LINE" ] ||
   [ "$MATERIALIZE_LOAD_CLEAR_LINE" -le "$BEGIN_LOAD_PASS_LINE" ] ||
   [ "$MATERIALIZE_LOAD_CLEAR_LINE" -ge "$BEGIN_LOAD_COLOR_ATTACHMENTS_LINE" ]
then
  echo "ERROR: layered load-clear materialization does not precede render-pass assembly" >&2
  exit 1
fi

mapfile -t READBACK_LAYOUT_LINES < <(
  grep -nF 'texture_readback_layout(' "$RGB9E5_TEXTURE_SOURCE" | cut -d: -f1
)
ASYNC_READBACK_KICK_LINE="$(grep -nF \
  'const readback::Ticket ticket = readback::kick_texture(' \
  "$RGB9E5_TEXTURE_SOURCE" | cut -d: -f1)"
SYNC_READBACK_ALLOCATION_LINE="$(grep -nF \
  'std::vector<uint8_t> device_data(layout.device_data_size);' \
  "$RGB9E5_TEXTURE_SOURCE" | tail -n 2 | head -n 1 | cut -d: -f1)"
NATIVE_STAGING_ALLOCATION_LINE="$(grep -nF \
  'wgpu::Buffer staging = device.CreateBuffer(&bd);' \
  "$RGB9E5_TEXTURE_SOURCE" | cut -d: -f1)"
if [ "${#READBACK_LAYOUT_LINES[@]}" -ne 2 ] ||
   [ -z "$ASYNC_READBACK_KICK_LINE" ] ||
   [ -z "$SYNC_READBACK_ALLOCATION_LINE" ] ||
   [ -z "$NATIVE_STAGING_ALLOCATION_LINE" ] ||
   [ "${READBACK_LAYOUT_LINES[0]}" -ge "$ASYNC_READBACK_KICK_LINE" ] ||
   [ "${READBACK_LAYOUT_LINES[1]}" -ge "$SYNC_READBACK_ALLOCATION_LINE" ] ||
   [ "${READBACK_LAYOUT_LINES[1]}" -ge "$NATIVE_STAGING_ALLOCATION_LINE" ]
then
  echo "ERROR: texture readback sizing is not fail-closed before allocation" >&2
  exit 1
fi

UPLOAD_LAYOUT_LINE="$(grep -nF 'if (!texture_upload_layout(' \
  "$RGB9E5_TEXTURE_SOURCE" | head -n 1 | cut -d: -f1)"
UPLOAD_DEVICE_ALLOCATION_LINE="$(grep -nF 'std::vector<uint8_t> device_data(layout.device_data_size);' \
  "$RGB9E5_TEXTURE_SOURCE" | head -n 1 | cut -d: -f1)"
if [ -z "$UPLOAD_LAYOUT_LINE" ] || [ -z "$UPLOAD_DEVICE_ALLOCATION_LINE" ] ||
   [ "$UPLOAD_LAYOUT_LINE" -ge "$UPLOAD_DEVICE_ALLOCATION_LINE" ]
then
  echo "ERROR: texture upload sizing is not fail-closed before host allocation" >&2
  exit 1
fi

CLEAR_LAYOUT_LINE="$(awk '
  /^void WGPUTexture::clear\(const double4 data\)/ { in_clear = 1 }
  in_clear && /if \(!texture_upload_layout\(/ { print NR }
  /^bool WGPUTexture::resolve_read_region\(/ { exit }
' "$RGB9E5_TEXTURE_SOURCE")"
CLEAR_BUFFER_LINE="$(grep -nF \
  'std::vector<uint8_t> buffer(clear_layout.device_data_size);' \
  "$RGB9E5_TEXTURE_SOURCE" | cut -d: -f1)"
CLEAR_WRITE_LINE="$(awk '
  /^void WGPUTexture::clear\(const double4 data\)/ { in_clear = 1 }
  in_clear && /ctx->queue_get\(\)\.WriteTexture/ { print NR }
  /^bool WGPUTexture::resolve_read_region\(/ { exit }
' "$RGB9E5_TEXTURE_SOURCE")"
if [ -z "$CLEAR_LAYOUT_LINE" ] || [ -z "$CLEAR_BUFFER_LINE" ] || [ -z "$CLEAR_WRITE_LINE" ] ||
   [ "$(printf '%s\n' "$CLEAR_LAYOUT_LINE" | wc -l | tr -d ' ')" -ne 1 ] ||
   [ "$(printf '%s\n' "$CLEAR_WRITE_LINE" | wc -l | tr -d ' ')" -ne 1 ] ||
   [ "$CLEAR_LAYOUT_LINE" -ge "$CLEAR_BUFFER_LINE" ] ||
   [ "$CLEAR_BUFFER_LINE" -ge "$CLEAR_WRITE_LINE" ] ||
   grep -Fq 'const size_t sample_count = size_t(ex) * ey * ez;' "$RGB9E5_TEXTURE_SOURCE" ||
   grep -Fq 'std::vector<uint8_t> buffer(sample_count * texel_bytes);' "$RGB9E5_TEXTURE_SOURCE"
then
  echo "ERROR: texture clear sizing is not fail-closed before host allocation" >&2
  exit 1
fi

if [ "$(grep -Ec '^uint8_t srgb_clear_component_to_unorm8\(' "$R11_CONVERSION_SOURCE")" -ne 1 ] ||
   [ "$(grep -Ec '^uint8_t srgb_clear_component_to_unorm8\(' "$R11_CONVERSION_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'dc[0] = srgb_clear_component_to_unorm8(float(v));' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'subresources_.backing_format == wgpu::TextureFormat::RGBA8UnormSrgb' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ]
then
  echo "ERROR: canonical non-renderable sRGB clear wiring differs" >&2
  exit 1
fi

CREATION_GUARD_LINE="$(grep -nF 'if (!format_creation_supported(fi.gate, format_features)) {' \
  "$RGB9E5_TEXTURE_SOURCE" | cut -d: -f1)"
ALLOCATION_GUARD_LINE="$(grep -nF '!texture_allocation_supported(' \
  "$RGB9E5_TEXTURE_SOURCE" | cut -d: -f1)"
CREATE_TEXTURE_LINE="$(grep -nF 'texture_ = device.CreateTexture(&desc);' \
  "$RGB9E5_TEXTURE_SOURCE" | cut -d: -f1)"
if [ -z "$CREATION_GUARD_LINE" ] || [ -z "$ALLOCATION_GUARD_LINE" ] ||
   [ -z "$CREATE_TEXTURE_LINE" ] ||
   [ "$CREATION_GUARD_LINE" -ge "$CREATE_TEXTURE_LINE" ] ||
   [ "$ALLOCATION_GUARD_LINE" -ge "$CREATE_TEXTURE_LINE" ] ||
   [ "$(sed -n "$((CREATION_GUARD_LINE + 1))p" "$RGB9E5_TEXTURE_SOURCE")" != \
     '    return false;' ]
then
  echo "ERROR: format creation guard is not fail-closed before CreateTexture" >&2
  exit 1
fi

if [ "$(grep -Ec '^bool compressed_upload_layout\(' "$FORMAT_SOURCE")" -ne 1 ] ||
   [ "$(grep -Ec '^bool compressed_texture_type_supported\(' "$FORMAT_SOURCE")" -ne 1 ] ||
   [ "$(grep -Ec '^bool compressed_upload_layout\(' "$FORMAT_HEADER")" -ne 1 ] ||
   [ "$(grep -Ec '^bool compressed_texture_type_supported\(' "$FORMAT_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'compressed_upload_layout(' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'FeatureName::TextureCompressionBC' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'case GPU_TEXTURE_ARRAY:' "$FORMAT_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'case GPU_TEXTURE_BUFFER:' "$FORMAT_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'compressed_layout.data_size, &layout, &write_size' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'if (repr == Repr::Compressed || repr == Repr::Unsupported)' "$RGB9E5_TEXTURE_SOURCE")" -ne 3 ]
then
  echo "ERROR: canonical block-compressed upload wiring differs" >&2
  exit 1
fi

GPU_TEXTURE_FRONTEND="$ROOT/upstream/source/blender/gpu/intern/gpu_texture.cc"
IMBUF_GPU_SOURCE="$ROOT/upstream/source/blender/imbuf/intern/util_gpu.cc"
if [ "$(grep -Fc 'gpu::Texture *GPU_texture_create_compressed_2d(' "$GPU_TEXTURE_FRONTEND")" -ne 1 ] ||
   [ "$(grep -Fc 'size = ((extent[0] + 3) / 4) * ((extent[1] + 3) / 4) *' "$GPU_TEXTURE_FRONTEND")" -ne 1 ] ||
   [ "$(grep -Fc 'tex = GPU_texture_create_compressed_2d(name,' "$IMBUF_GPU_SOURCE")" -ne 1 ]
then
  echo "ERROR: pinned Blender compressed-texture caller contract differs" >&2
  exit 1
fi

GHOST_WGPU_SOURCE="$ROOT/upstream/intern/ghost/intern/GHOST_ContextWGPU.cc"
EEVEE_RENDERBUFFERS="$ROOT/upstream/source/blender/draw/engines/eevee/eevee_renderbuffers.cc"
PAINT_CURSOR_SOURCE="$ROOT/upstream/source/blender/editors/sculpt_paint/paint_cursor.cc"
WGPU_PREINIT_SOURCE="$ROOT/platform_web/shell/wgpu-preinit-worker.js"
if [ "$(grep -Ec '^wgpu::ComponentSwizzle to_wgpu_component_swizzle\(' "$FORMAT_SOURCE")" -ne 1 ] ||
   [ "$(grep -Ec '^wgpu::ComponentSwizzle to_wgpu_component_swizzle\(' "$FORMAT_HEADER")" -ne 1 ] ||
   [ "$(grep -Fc 'wgpu::TextureComponentSwizzleDescriptor swizzle_desc = {};' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'd.nextInChain = &swizzle_desc;' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'FeatureName::TextureComponentSwizzle' "$RGB9E5_TEXTURE_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'FeatureName::TextureComponentSwizzle' "$GHOST_WGPU_SOURCE")" -ne 2 ] ||
   [ "$(grep -Fc 'GPU_texture_swizzle_set(vector_tx, "rgrg")' "$EEVEE_RENDERBUFFERS")" -ne 1 ] ||
   [ "$(grep -Fc 'GPU_texture_swizzle_set(target->overlay_texture, "rrrr")' "$PAINT_CURSOR_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'GPU_texture_swizzle_set(tex, imb_gpu_get_swizzle(ibuf));' "$IMBUF_GPU_SOURCE")" -ne 2 ] ||
   [ "$(grep -Fc 'adapter.features.forEach(function (f) { requiredFeatures.push(f); });' "$WGPU_PREINIT_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'requiredFeatures: requiredFeatures,' "$WGPU_PREINIT_SOURCE")" -ne 1 ]
then
  echo "ERROR: canonical texture-component-swizzle wiring differs" >&2
  exit 1
fi

VK_CONVERSION_HEADER="$ROOT/upstream/source/blender/gpu/vulkan/vk_data_conversion.hh"
VK_CONVERSION_TEST="$ROOT/upstream/source/blender/gpu/vulkan/tests/vk_data_conversion_test.cc"
if ! grep -Fq 'using FormatF11 = FloatingPointFormat<false, 6, 5>;' "$VK_CONVERSION_HEADER" ||
   ! grep -Fq 'using FormatF10 = FloatingPointFormat<false, 5, 5>;' "$VK_CONVERSION_HEADER" ||
   ! grep -Fq 'convert_float_formats<FormatF11, FormatF32, true>' "$VK_CONVERSION_TEST" ||
   ! grep -Fq 'convert_float_formats<FormatF10, FormatF32, true>' "$VK_CONVERSION_TEST"
then
  echo "ERROR: pinned Vulkan RG11B10 oracle differs" >&2
  exit 1
fi

GPENCIL_MASK_SOURCE="$ROOT/upstream/source/blender/draw/engines/gpencil/gpencil_engine_c.cc"
if [ "$(grep -Fc 'const gpu::TextureFormat mask_format = this->is_render ? gpu::TextureFormat::UNORM_16 :' "$GPENCIL_MASK_SOURCE")" -ne 1 ] ||
   [ "$(grep -Fc 'this->mask_tx.acquire_2d(size, mask_format);' "$GPENCIL_MASK_SOURCE")" -ne 1 ]
then
  echo "ERROR: pinned Grease Pencil UNORM16 render-mask path differs" >&2
  exit 1
fi

if [ ! -d "$DAWN_SRC/.git" ]; then
  echo "ERROR: Dawn checkout missing at $DAWN_SRC" >&2
  exit 1
fi
ACTUAL_DAWN_PIN="$(git -C "$DAWN_SRC" rev-parse HEAD)"
if [ "$ACTUAL_DAWN_PIN" != "$DAWN_PIN" ]; then
  echo "ERROR: Dawn pin mismatch: expected $DAWN_PIN, got $ACTUAL_DAWN_PIN" >&2
  exit 1
fi
if [ -n "$(git -C "$DAWN_SRC" status --porcelain)" ]; then
  echo "ERROR: Dawn checkout is not clean at the pinned commit" >&2
  exit 1
fi
if ! "$PYBIN" -c 'import pyexpat, xml.etree.ElementTree' >/dev/null 2>&1; then
  echo "ERROR: pinned host Python lacks working XML modules" >&2
  exit 1
fi
if [ "$("$HOST_CMAKE" --version | sed -n '1s/^cmake version //p')" != "4.0.3" ]; then
  echo "ERROR: expected host CMake 4.0.3" >&2
  exit 1
fi

# Bind every shipping source byte to the canonical clean-pin reconstruction
# before any evidence directory is allocated.
SOURCE_PROOF="$("$PYBIN" "$ROOT/sandbox/series-replay/verify.py" --canonical-only)"
case "$SOURCE_PROOF" in
  CANONICAL_REPLAY_PASS\ *) ;;
  *)
    echo "ERROR: canonical source replay did not produce its exact verdict" >&2
    exit 1
    ;;
esac

NODE_VERSION="$("$NODE" --version)"
if [ "$NODE_VERSION" != "v22.16.0" ]; then
  echo "ERROR: expected Node v22.16.0, got $NODE_VERSION" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$EMSDK/emsdk_env.sh" >/dev/null
EMCC_VERSION="$(em++ --version | sed -n '1s/.* \([0-9][0-9.]*\) (.*/\1/p')"
if [ "$EMCC_VERSION" != "6.0.5" ]; then
  echo "ERROR: expected em++ 6.0.5, got ${EMCC_VERSION:-unknown}" >&2
  exit 1
fi

mkdir -p "$NATIVE_BUILD" "$WASM_BUILD" "$OUT"
printf '%s\n' "$SOURCE_PROOF" >"$OUT/source-replay.txt"

CCACHE_ARGS=()
if command -v ccache >/dev/null 2>&1; then
  CCACHE_ARGS=(-DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache)
fi

echo "== [1/3] canonical native texture-format/conversion module =="
"$HOST_CMAKE" -G Ninja -S "$ROOT/sandbox/dawn-probe" -B "$NATIVE_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CMAKE_HOST_ARGS[@]}" \
  "${CCACHE_ARGS[@]}" \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DBW_UPSTREAM_DIR="$ROOT/upstream" \
  -DBW_INTEGRATED_TEXTURE_SOURCE_DIR="$WEBGPU_SOURCE" \
  -DBW_NATIVE_FMT_INCLUDE_DIR="$NATIVE_FMT_INCLUDE" \
  -DPython3_EXECUTABLE="$PYBIN"
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" wgpu_texture_integrated_test

echo "== [2/3] canonical Wasm texture-format/conversion module =="
"$EMSDK/upstream/emscripten/emcmake" "$HOST_CMAKE" -G Ninja \
  -S "$ROOT/sandbox/wgpu-texture-wasm-smoke" -B "$WASM_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CCACHE_ARGS[@]}" \
  -DBW_UPSTREAM_DIR="$ROOT/upstream" \
  -DBW_WASM_INCLUDE_DIR="$WASM_INCLUDE" \
  -DBW_INTEGRATED_TEXTURE_SOURCE_DIR="$WEBGPU_SOURCE"
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" wgpu_texture_integrated_smoke

echo "== [3/3] exact native/Wasm parity =="
NATIVE_STDOUT="$OUT/native.stdout"
NATIVE_STDERR="$OUT/native.stderr"
WASM_STDOUT="$OUT/wasm.stdout"
WASM_STDERR="$OUT/wasm.stderr"
"$NATIVE_BUILD/wgpu_texture_integrated_test" >"$NATIVE_STDOUT" 2>"$NATIVE_STDERR"
"$NODE" "$WASM_BUILD/integrated_texture.js" >"$WASM_STDOUT" 2>"$WASM_STDERR"

for stderr_file in "$NATIVE_STDERR" "$WASM_STDERR"; do
  if [ -s "$stderr_file" ]; then
    echo "ERROR: integrated texture contract wrote stderr: $stderr_file" >&2
    exit 1
  fi
done
for stdout_file in "$NATIVE_STDOUT" "$WASM_STDOUT"; do
  if ! grep -qx \
    'INTEGRATED_TEXTURE_PASS contracts=23 formats=63 creation_cases=448 allocation_limits=26 upload_layouts=14 upload_regions=13 clear_layouts=6 srgb_clear=12 readback_layouts=15 framebuffer_reads=13 framebuffer_clear_cases=11 framebuffer_clear_plans=18 framebuffer_clear_formats=4 framebuffer_scissored_layers=4 framebuffer_draw_cases=16 framebuffer_load_clear_cases=10 promotions=13 view_pairs=10 rgb9e5=10 rg11b10=25 packed_rows=6 compressed_layouts=7 swizzles=10' \
    "$stdout_file"
  then
    echo "ERROR: integrated texture PASS verdict missing: $stdout_file" >&2
    exit 1
  fi
  if [ "$(grep -c '^CONTRACT .* PASS ' "$stdout_file")" -ne 23 ]; then
    echo "ERROR: integrated texture evidence census differs: $stdout_file" >&2
    exit 1
  fi
done
if ! cmp -s "$NATIVE_STDOUT" "$WASM_STDOUT"; then
  echo "ERROR: native and Wasm integrated texture evidence differs" >&2
  diff -u "$NATIVE_STDOUT" "$WASM_STDOUT" | head -n 40 >&2
  exit 1
fi

"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" -n wgpu_texture_integrated_test
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" -n wgpu_texture_integrated_smoke

OUTPUT_BYTES="$(wc -c <"$WASM_STDOUT" | tr -d ' ')"
OUTPUT_SHA256="$(sha256_file "$WASM_STDOUT")"
SOURCE_SHA256="$(source_digest)"
echo "PASS integrated-texture native/wasm bytes=$OUTPUT_BYTES sha256=$OUTPUT_SHA256 source_sha256=$SOURCE_SHA256 dawn=$DAWN_PIN emcc=$EMCC_VERSION node=$NODE_VERSION"
