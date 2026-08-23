#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Device-free native/Wasm parity driver for the canonical in-tree WebGPU
# render-pipeline enum mappings, direct/indirect draw and dispatch spans, clipped
# multi-viewport/window-backbuffer rectangles, transient uniform and pipeline
# cache publication, color-blit resource guards, dummy-attribute binding plan,
# and shader-lifetime cache separation.
# Invoke through buildwrap.sh.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WEBGPU_SOURCE="$ROOT/upstream/source/blender/gpu/webgpu"
DAWN_SRC="${DAWN_SRC:-$ROOT/build-dawn/dawn}"
DAWN_PIN="36cf1fae0cd8a81a4fb4580751648b80b2e6255c"
NATIVE_BUILD="${NATIVE_BUILD:-$ROOT/build-dawn/probe-build}"
WASM_BUILD="${WASM_BUILD:-$ROOT/build-deps/t10-pipeline-integrated/wasm-build}"
OUT="${OUT:-$ROOT/build-deps/t10-pipeline-integrated/evidence}"
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

require_fixed_count()
{
  local expected="$1"
  local needle="$2"
  local source_file="$3"
  local actual
  actual="$(grep -Fc -- "$needle" "$source_file" || true)"
  if [ "$actual" -ne "$expected" ]; then
    echo "ERROR: expected $expected exact '$needle' occurrence(s) in $source_file, got $actual" >&2
    exit 1
  fi
}

source_digest()
{
  local files=(
    source/blender/gpu/webgpu/wgpu_pipeline.cc
    source/blender/gpu/webgpu/wgpu_pipeline.hh
    source/blender/gpu/webgpu/wgpu_common.hh
    source/blender/gpu/webgpu/wgpu_backend.cc
    source/blender/gpu/webgpu/wgpu_context.cc
    source/blender/gpu/webgpu/wgpu_context.hh
    source/blender/gpu/webgpu/wgpu_batch.cc
    source/blender/gpu/webgpu/wgpu_framebuffer.cc
    source/blender/gpu/webgpu/wgpu_shader.cc
    source/blender/gpu/webgpu/wgpu_shader.hh
    source/blender/gpu/webgpu/wgpu_state_table.hh
    source/blender/gpu/intern/gpu_shader_interface.hh
    source/blender/gpu/intern/gpu_state_private.hh
    source/blender/gpu/intern/gpu_vertex_format.cc
    source/blender/gpu/intern/gpu_vertex_format_private.hh
    source/blender/gpu/GPU_batch.hh
    source/blender/gpu/GPU_common_types.hh
    source/blender/gpu/GPU_primitive.hh
    source/blender/gpu/GPU_vertex_format.hh
    source/blender/blenlib/BLI_assert.h
    source/blender/blenlib/intern/BLI_assert.cc
  )
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$ROOT/upstream" && sha256sum "${files[@]}" | sha256sum | awk '{print $1}')
  else
    (cd "$ROOT/upstream" && shasum -a 256 "${files[@]}" | shasum -a 256 | awk '{print $1}')
  fi
}

require_file "$PYBIN"
require_file "$HOST_CMAKE"
require_file "$ROOT/scripts/ninja-locked.sh"
require_file "$ROOT/sandbox/series-replay/verify.py"
require_file "$HERE/integrated_pipeline_test.cc"
require_file "$ROOT/sandbox/wgpu-pipeline-wasm-smoke/CMakeLists.txt"
require_file "$DAWN_SRC/src/dawn/tests/unittests/validation/VertexStateValidationTests.cpp"
require_file "$DAWN_SRC/src/dawn/tests/unittests/validation/DrawIndirectValidationTests.cpp"
require_file "$DAWN_SRC/src/dawn/tests/unittests/validation/DrawVertexAndIndexBufferOOBValidationTests.cpp"
require_file "$DAWN_SRC/src/dawn/tests/unittests/validation/ComputeValidationTests.cpp"
require_file "$DAWN_SRC/src/dawn/tests/unittests/validation/ComputeIndirectValidationTests.cpp"
require_file "$DAWN_SRC/src/dawn/tests/unittests/validation/DynamicStateCommandValidationTests.cpp"
require_file "$DAWN_SRC/src/dawn/native/CommandBufferStateTracker.cpp"
require_file "$DAWN_SRC/src/dawn/native/RenderEncoderBase.cpp"
require_file "$DAWN_SRC/src/dawn/native/RenderPassEncoder.cpp"
require_file "$EMSDK/emsdk_env.sh"
require_file "$EMSDK/upstream/emscripten/emcmake"
require_file "$NODE"
for source_name in \
  wgpu_pipeline.cc \
  wgpu_pipeline.hh \
  wgpu_common.hh \
  wgpu_backend.cc \
  wgpu_context.cc \
  wgpu_context.hh \
  wgpu_batch.cc \
  wgpu_framebuffer.cc \
  wgpu_shader.cc \
  wgpu_shader.hh \
  wgpu_state_table.hh
do
  require_file "$WEBGPU_SOURCE/$source_name"
done
for source_path in \
  source/blender/gpu/intern/gpu_shader_interface.hh \
  source/blender/gpu/intern/gpu_state_private.hh \
  source/blender/gpu/intern/gpu_vertex_format.cc \
  source/blender/gpu/intern/gpu_vertex_format_private.hh \
  source/blender/gpu/GPU_batch.hh \
  source/blender/gpu/GPU_common_types.hh \
  source/blender/gpu/GPU_primitive.hh \
  source/blender/gpu/GPU_vertex_format.hh \
  source/blender/blenlib/BLI_assert.h \
  source/blender/blenlib/intern/BLI_assert.cc
do
  require_file "$ROOT/upstream/$source_path"
done
require_file "$NATIVE_FMT_INCLUDE/fmt/ranges.h"
require_file "$WASM_INCLUDE/fmt/ranges.h"
if ! cmp -s "$NATIVE_FMT_INCLUDE/fmt/ranges.h" "$WASM_INCLUDE/fmt/ranges.h"; then
  echo "ERROR: native and Wasm fmt/ranges.h inputs differ" >&2
  exit 1
fi
FMT_SHA256="$(sha256_file "$WASM_INCLUDE/fmt/ranges.h")"

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
require_fixed_count 1 'TEST_F(VertexStateTest, StrideZero)' \
  "$DAWN_SRC/src/dawn/tests/unittests/validation/VertexStateValidationTests.cpp"
require_fixed_count 2 'if (arrayStride == 0) {' \
  "$DAWN_SRC/src/dawn/native/CommandBufferStateTracker.cpp"
require_fixed_count 1 'TEST_F(DrawIndirectValidationTest, DrawIndirectOffsetBounds)' \
  "$DAWN_SRC/src/dawn/tests/unittests/validation/DrawIndirectValidationTests.cpp"
require_fixed_count 1 'TEST_F(DrawIndirectValidationTest, DrawIndexedIndirectOffsetBounds)' \
  "$DAWN_SRC/src/dawn/tests/unittests/validation/DrawIndirectValidationTests.cpp"
require_fixed_count 4 'Indirect offset (%u) is not a multiple of 4.' \
  "$DAWN_SRC/src/dawn/native/RenderEncoderBase.cpp"
require_fixed_count 1 \
  'TEST_F(DrawVertexAndIndexBufferOOBValidationTests, DrawBasic)' \
  "$DAWN_SRC/src/dawn/tests/unittests/validation/DrawVertexAndIndexBufferOOBValidationTests.cpp"
require_fixed_count 1 \
  'TEST_F(DrawVertexAndIndexBufferOOBValidationTests, DrawIndexedIndexBufferOOB)' \
  "$DAWN_SRC/src/dawn/tests/unittests/validation/DrawVertexAndIndexBufferOOBValidationTests.cpp"
require_fixed_count 1 'void RenderEncoderBase::APIDraw(uint32_t vertexCount,' \
  "$DAWN_SRC/src/dawn/native/RenderEncoderBase.cpp"
require_fixed_count 1 \
  'TEST_F(ComputeDispatchValidationTest, PerDimensionDispatchSizeLimits_LargestValid)' \
  "$DAWN_SRC/src/dawn/tests/unittests/validation/ComputeValidationTests.cpp"
require_fixed_count 1 'TEST_F(ComputeIndirectValidationTest, IndirectOffsetBounds)' \
  "$DAWN_SRC/src/dawn/tests/unittests/validation/ComputeIndirectValidationTests.cpp"
require_fixed_count 1 'TEST_F(SetScissorTest, ScissorLargerThanFramebuffer)' \
  "$DAWN_SRC/src/dawn/tests/unittests/validation/DynamicStateCommandValidationTests.cpp"
require_fixed_count 1 'TEST_F(SetScissorTest, EmptyScissor)' \
  "$DAWN_SRC/src/dawn/tests/unittests/validation/DynamicStateCommandValidationTests.cpp"
require_fixed_count 1 'TEST_F(SetViewportTest, ViewportLargerThanLimit)' \
  "$DAWN_SRC/src/dawn/tests/unittests/validation/DynamicStateCommandValidationTests.cpp"
require_fixed_count 1 'TEST_F(SetViewportTest, EmptyViewport)' \
  "$DAWN_SRC/src/dawn/tests/unittests/validation/DynamicStateCommandValidationTests.cpp"
require_fixed_count 1 'TEST_F(SetViewportTest, NegativeXYWidthHeight)' \
  "$DAWN_SRC/src/dawn/tests/unittests/validation/DynamicStateCommandValidationTests.cpp"
require_fixed_count 1 'void RenderPassEncoder::APISetViewport(' \
  "$DAWN_SRC/src/dawn/native/RenderPassEncoder.cpp"
require_fixed_count 1 'x < -maxViewportBounds || y < -maxViewportBounds' \
  "$DAWN_SRC/src/dawn/native/RenderPassEncoder.cpp"
require_fixed_count 1 'x + width > maxViewportBounds - 1 || y + height > maxViewportBounds - 1' \
  "$DAWN_SRC/src/dawn/native/RenderPassEncoder.cpp"
require_fixed_count 1 'void RenderPassEncoder::APISetScissorRect(' \
  "$DAWN_SRC/src/dawn/native/RenderPassEncoder.cpp"
require_fixed_count 1 'static_cast<uint64_t>(x) + static_cast<uint64_t>(width) >' \
  "$DAWN_SRC/src/dawn/native/RenderPassEncoder.cpp"
require_fixed_count 1 'struct ComputeDispatchPlan {' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 'inline bool compute_dispatch_plan(' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline bool compute_indirect_dispatch_range(' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'if (!webgpu::compute_dispatch_plan(' "$WEBGPU_SOURCE/wgpu_backend.cc"
require_fixed_count 1 \
  'if (!webgpu::compute_indirect_dispatch_range(0, indirect_gpu.size()))' \
  "$WEBGPU_SOURCE/wgpu_backend.cc"
require_fixed_count 1 \
  'inline bool command_pass_encode_submit_if_valid(const DeviceT &device,' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 2 \
  'if (!webgpu::command_pass_encode_submit_if_valid(' \
  "$WEBGPU_SOURCE/wgpu_backend.cc"
require_fixed_count 0 \
  'wgpu::CommandEncoder enc = device.CreateCommandEncoder();' \
  "$WEBGPU_SOURCE/wgpu_backend.cc"
require_fixed_count 1 'struct DirectDrawPlan {' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 'inline bool direct_draw_plan(' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'if (!webgpu::direct_draw_plan(' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 'struct ViewportScissorPlan {' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 'inline bool viewport_scissor_plan(' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'if (width < 0 || height < 0 || target_width <= 0 || target_height <= 0 ||' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 'const bool viewport_fully_clipped =' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 2 \
  'if (!webgpu::viewport_scissor_plan(' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'inline bool multi_viewport_uniform_buffer_create(' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline bool buffer_create_if_valid(' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'return buffer_create_if_valid(device, descriptor, result);' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 2 \
  'if (!webgpu::multi_viewport_uniform_buffer_create(device, mv_buf)) {' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 0 \
  'wgpu::Buffer mv_buf = device.CreateBuffer(&bd);' "$WEBGPU_SOURCE/wgpu_batch.cc"
mapfile -t MULTIVIEW_ALLOCATION_LINES < <(
  grep -nF 'if (!webgpu::multi_viewport_uniform_buffer_create(device, mv_buf)) {' \
    "$WEBGPU_SOURCE/wgpu_batch.cc" | cut -d: -f1
)
mapfile -t MULTIVIEW_WRITE_LINES < <(
  grep -nF 'WriteBuffer(mv_buf, 0, mv_vals, sizeof(mv_vals));' \
    "$WEBGPU_SOURCE/wgpu_batch.cc" | cut -d: -f1
)
mapfile -t PUSH_CONSTANT_FLUSH_LINES < <(
  grep -nF 'shader->push_constants_flush();' "$WEBGPU_SOURCE/wgpu_batch.cc" | cut -d: -f1
)
if [ "${#MULTIVIEW_ALLOCATION_LINES[@]}" -ne 2 ] ||
   [ "${#MULTIVIEW_WRITE_LINES[@]}" -ne 2 ] ||
   [ "${#PUSH_CONSTANT_FLUSH_LINES[@]}" -ne 4 ] ||
   [ "${MULTIVIEW_ALLOCATION_LINES[0]}" -ge "${PUSH_CONSTANT_FLUSH_LINES[0]}" ] ||
   [ "${PUSH_CONSTANT_FLUSH_LINES[0]}" -ge "${MULTIVIEW_WRITE_LINES[0]}" ] ||
   [ "${MULTIVIEW_ALLOCATION_LINES[1]}" -ge "${PUSH_CONSTANT_FLUSH_LINES[2]}" ] ||
   [ "${PUSH_CONSTANT_FLUSH_LINES[2]}" -ge "${MULTIVIEW_WRITE_LINES[1]}" ]
then
  echo "ERROR: multi-viewport allocation guards do not precede state flushes and queue writes" >&2
  exit 1
fi
require_fixed_count 1 \
  'if (!webgpu::buffer_create_if_valid(device_, bd, blit_uniform)) {' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 \
  'wgpu::Buffer blit_uniform = device_.CreateBuffer(&bd);' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 2 \
  'if (selected_module == nullptr) {' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 3 \
  'if (bind_group == nullptr) {' "$WEBGPU_SOURCE/wgpu_context.cc"
COLOR_MODULE_CREATE_LINE="$(grep -nF \
  'selected_module = device_.CreateShaderModule(&md);' \
  "$WEBGPU_SOURCE/wgpu_context.cc" | cut -d: -f1)"
COLOR_MODULE_GUARD_LINE="$(grep -nF \
  'if (selected_module == nullptr) {' "$WEBGPU_SOURCE/wgpu_context.cc" | tail -n 1 | cut -d: -f1)"
COLOR_PIPELINE_KEY_LINE="$(grep -nF \
  'const uint32_t fmt_key = uint32_t(dst_format)' \
  "$WEBGPU_SOURCE/wgpu_context.cc" | cut -d: -f1)"
COLOR_UNIFORM_GUARD_LINE="$(grep -nF \
  'if (!webgpu::buffer_create_if_valid(device_, bd, blit_uniform)) {' \
  "$WEBGPU_SOURCE/wgpu_context.cc" | cut -d: -f1)"
COLOR_QUEUE_WRITE_LINE="$(grep -nF \
  'queue_.WriteBuffer(blit_uniform, 0, blit_data, sizeof(blit_data));' \
  "$WEBGPU_SOURCE/wgpu_context.cc" | cut -d: -f1)"
COLOR_BIND_CREATE_LINE="$(grep -nF \
  'wgpu::BindGroup bind_group = device_.CreateBindGroup(&bgd);' \
  "$WEBGPU_SOURCE/wgpu_context.cc" | head -n 1 | cut -d: -f1)"
COLOR_BIND_GUARD_LINE="$(grep -nF \
  'if (bind_group == nullptr) {' "$WEBGPU_SOURCE/wgpu_context.cc" | head -n 1 | cut -d: -f1)"
COLOR_ENCODER_LINE="$(grep -nF \
  'wgpu::CommandEncoder enc = device_.CreateCommandEncoder();' \
  "$WEBGPU_SOURCE/wgpu_context.cc" | head -n 1 | cut -d: -f1)"
if [ -z "$COLOR_MODULE_CREATE_LINE" ] || [ -z "$COLOR_MODULE_GUARD_LINE" ] ||
   [ -z "$COLOR_PIPELINE_KEY_LINE" ] || [ -z "$COLOR_UNIFORM_GUARD_LINE" ] ||
   [ -z "$COLOR_QUEUE_WRITE_LINE" ] || [ -z "$COLOR_BIND_CREATE_LINE" ] ||
   [ -z "$COLOR_BIND_GUARD_LINE" ] || [ -z "$COLOR_ENCODER_LINE" ] ||
   [ "$COLOR_MODULE_CREATE_LINE" -ge "$COLOR_MODULE_GUARD_LINE" ] ||
   [ "$COLOR_MODULE_GUARD_LINE" -ge "$COLOR_PIPELINE_KEY_LINE" ] ||
   [ "$COLOR_UNIFORM_GUARD_LINE" -ge "$COLOR_QUEUE_WRITE_LINE" ] ||
   [ "$COLOR_BIND_CREATE_LINE" -ge "$COLOR_BIND_GUARD_LINE" ] ||
   [ "$COLOR_BIND_GUARD_LINE" -ge "$COLOR_ENCODER_LINE" ]
then
  echo "ERROR: color-blit resource guards do not precede queue and pass work" >&2
  exit 1
fi
require_fixed_count 1 \
  'inline bool cache_handle_if_valid(' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline bool cache_variant_if_valid(' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'if (!webgpu::cache_handle_if_valid(sampler_cache_, key, sampler)) {' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 \
  'if (!webgpu::cache_handle_if_valid(blit_pipelines_, fmt_key, pipeline)) {' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 \
  'if (!cache_handle_if_valid(cache_, key, pipeline)) {' \
  "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 4 \
  'if (!webgpu::cache_handle_if_valid(' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 \
  'depth_blit_pipelines_, uint32_t(dst_format), pipeline))' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 \
  'depth_upload_pipelines_, uint32_t(format), pipeline))' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 'sampler_cache_[key] = sampler;' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 'blit_pipelines_[fmt_key] = pipeline;' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 \
  'depth_blit_pipelines_[uint32_t(dst_format)] = pipeline;' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 \
  'depth_upload_pipelines_[uint32_t(format)] = pipeline;' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 'cache_.emplace(key, pipeline);' "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 \
  'if (!wgi::cache_variant_if_valid(compute_pipelines_, key, pipeline)) {' \
  "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 0 \
  'compute_pipelines_.push_back({key, pipeline});' "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 1 \
  'using WindowViewportPlan = FramebufferViewportPlan;' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline bool window_viewport_scissor_plan(' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 'struct FramebufferViewportPlan {' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline bool offscreen_viewport_scissor_plan(' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 0 'bool convert_bottom_origin' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'if (!webgpu::window_viewport_scissor_plan(' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 1 \
  'if (!webgpu::offscreen_viewport_scissor_plan(' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 0 'std::clamp(vp[' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 0 'std::clamp(sc[' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 1 \
  'pass.SetViewport(float(draw_viewport.viewport.viewport_x),' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 1 \
  'pass.SetScissorRect(draw_viewport.scissor_x,' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
WINDOW_PLAN_LINE="$(grep -nF 'if (!webgpu::window_viewport_scissor_plan(' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc" | cut -d: -f1)"
OFFSCREEN_PLAN_LINE="$(grep -nF 'if (!webgpu::offscreen_viewport_scissor_plan(' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc" | cut -d: -f1)"
LAYERED_CLEAR_LINE="$(grep -nF 'if (!materialize_layered_loadstore_clears())' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc" | cut -d: -f1)"
BEGIN_PASS_LINE="$(grep -nF 'wgpu::RenderPassEncoder pass = encoder.BeginRenderPass(&rp);' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc" | cut -d: -f1)"
if [ -z "$WINDOW_PLAN_LINE" ] || [ -z "$OFFSCREEN_PLAN_LINE" ] ||
   [ -z "$LAYERED_CLEAR_LINE" ] || [ -z "$BEGIN_PASS_LINE" ] ||
   [ "$WINDOW_PLAN_LINE" -ge "$LAYERED_CLEAR_LINE" ] ||
   [ "$OFFSCREEN_PLAN_LINE" -ge "$LAYERED_CLEAR_LINE" ] ||
   [ "$LAYERED_CLEAR_LINE" -ge "$BEGIN_PASS_LINE" ]
then
  echo "ERROR: framebuffer viewport preflight no longer precedes layered clears and pass allocation" >&2
  exit 1
fi
require_fixed_count 0 'uint32_t(rect[0])' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 0 'uint32_t(rect[1])' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 0 'uint32_t(rect[2])' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 0 'uint32_t(rect[3])' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 0 'uint32_t(vertex_first)' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 0 'uint32_t(vertex_count)' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 0 'uint32_t(instance_first)' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 0 'uint32_t(instance_count)' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 'struct IndirectDrawSpan {' "$WEBGPU_SOURCE/wgpu_pipeline.hh"
require_fixed_count 1 'bool indirect_draw_span(' "$WEBGPU_SOURCE/wgpu_pipeline.hh"
require_fixed_count 1 'bool indirect_draw_span(' "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 \
  'if (!webgpu::indirect_draw_span(' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 'static VertexBinding dummy_vertex_binding(' \
  "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 'binding.array_stride = 0;' "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 'binding.step_mode = wgpu::VertexStepMode::Vertex;' \
  "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 'plan.push_back(dummy_vertex_binding(' "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 \
  'hash_shader_identity(h, info.shader, info.shader_cache_identity);' \
  "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 'static void hash_shader_identity(' "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 'hash_bytes(h, &a.name_len, sizeof(a.name_len));' \
  "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 \
  'const uint32_t name_length = nm != nullptr ? uint32_t(std::strlen(nm)) : UINT32_MAX;' \
  "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 'hash_bytes(h, &name_length, sizeof(name_length));' \
  "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 \
  'BLI_assert(info.shader_cache_identity == info.shader->pipeline_cache_identity());' \
  "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 'static std::atomic<uint64_t> next_identity{1};' \
  "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 1 \
  'next_identity.fetch_add(1, std::memory_order_relaxed);' \
  "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 2 \
  'webgpu::PipelineInfo info(shader, shader->pipeline_cache_identity());' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'webgpu::PipelineInfo info(shader, shader->pipeline_cache_identity());' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
require_fixed_count 1 \
  '/* Every dummy slot has arrayStride zero, so all vertex and instance ranges read the same' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
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

if [ "$(grep -Fc \
       'info.strip_index_format = webgpu::to_wgpu_strip_index_format(' \
       "$WEBGPU_SOURCE/wgpu_batch.cc")" -ne 2 ]
then
  echo "ERROR: direct/indirect indexed-strip pipeline binding differs" >&2
  exit 1
fi

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

echo "== [1/3] canonical native render-pipeline mappings =="
"$HOST_CMAKE" -G Ninja -S "$ROOT/sandbox/dawn-probe" -B "$NATIVE_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CMAKE_HOST_ARGS[@]}" \
  "${CCACHE_ARGS[@]}" \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DBW_UPSTREAM_DIR="$ROOT/upstream" \
  -DBW_INTEGRATED_PIPELINE_SOURCE_DIR="$WEBGPU_SOURCE" \
  -DBW_NATIVE_FMT_INCLUDE_DIR="$NATIVE_FMT_INCLUDE" \
  -DPython3_EXECUTABLE="$PYBIN"
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" wgpu_pipeline_integrated_test

echo "== [2/3] canonical Wasm render-pipeline mappings =="
"$EMSDK/upstream/emscripten/emcmake" "$HOST_CMAKE" -G Ninja \
  -S "$ROOT/sandbox/wgpu-pipeline-wasm-smoke" -B "$WASM_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CCACHE_ARGS[@]}" \
  -DBW_UPSTREAM_DIR="$ROOT/upstream" \
  -DBW_INTEGRATED_PIPELINE_SOURCE_DIR="$WEBGPU_SOURCE" \
  -DBW_WASM_INCLUDE_DIR="$WASM_INCLUDE"
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" wgpu_pipeline_integrated_smoke

echo "== [3/3] exact native/Wasm parity =="
NATIVE_STDOUT="$OUT/native.stdout"
NATIVE_STDERR="$OUT/native.stderr"
WASM_STDOUT="$OUT/wasm.stdout"
WASM_STDERR="$OUT/wasm.stderr"
"$NATIVE_BUILD/wgpu_pipeline_integrated_test" >"$NATIVE_STDOUT" 2>"$NATIVE_STDERR"
"$NODE" "$WASM_BUILD/integrated_pipeline.js" >"$WASM_STDOUT" 2>"$WASM_STDERR"

for stdout_file in "$NATIVE_STDOUT" "$WASM_STDOUT"; do
  if [ "$(wc -l <"$stdout_file" | tr -d ' ')" -ne 19 ] ||
     ! grep -qx 'CONTRACT primitive_topology PASS cases=11' "$stdout_file" ||
     ! grep -qx 'CONTRACT strip_index_format PASS cases=33 selected=6' "$stdout_file" ||
     ! grep -qx \
       'CONTRACT multiview_uniform_allocation PASS cases=2 creates=2 failure=atomic bytes=16' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT cache_handle_publication PASS attempts=2 failure=unpublished retry=published entries=2' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT compute_pipeline_cache_publication PASS attempts=2 failure=unpublished retry=published entries=2' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT indirect_draw_span PASS cases=19 accepted=7 rejected=12 first_sum=36 stride_sum=144 end_sum=380' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT direct_draw_plan PASS cases=16 accepted=5 rejected=11 value_sum=17179869214' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT viewport_scissor_plan PASS cases=28 accepted=17 rejected=11 area=616503' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT window_viewport_scissor_plan PASS cases=32 accepted=23 rejected=9 viewport_sum=16208 scissor_area=1764' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT offscreen_viewport_scissor_plan PASS cases=21 accepted=17 rejected=4 scissors=8 scissor_area=113' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT compute_dispatch_range PASS direct_cases=15 accepted=6 rejected=9 indirect_cases=13 accepted=5 rejected=8 group_sum=40' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT compute_command_transaction PASS cases=4 accepted=1 encoder_fail=closed pass_fail=closed command_fail=closed' \
       "$stdout_file" ||
     ! grep -qx 'CONTRACT format_32bit PASS cases=36' "$stdout_file" ||
     ! grep -qx 'CONTRACT format_subword PASS cases=48' "$stdout_file" ||
     ! grep -qx 'CONTRACT format_i10 PASS cases=12 normalized=4' "$stdout_file" ||
     ! grep -qx 'CONTRACT dummy_vertex PASS cases=32 stride=0 step=vertex' "$stdout_file" ||
     ! grep -qx 'CONTRACT shader_lifetime_cache PASS cases=4096 unique=4096' "$stdout_file" ||
     ! grep -qx 'CONTRACT vertex_alias_cache_key PASS cases=2 aliases=4 unique=2' "$stdout_file" ||
     ! grep -qx \
       'INTEGRATED_PIPELINE_PASS contracts=18 primitives=11 strip_cases=33 multiview_allocations=2 indirect_spans=19 direct_draws=16 viewport_scissors=28 window_rects=32 offscreen_rects=21 compute_direct=15 compute_indirect=13 compute_command_cases=4 formats=96 i10=12 dummy=32 cache_publications=2 compute_cache_publications=2 shader_lifetimes=4096 alias_keys=2' \
       "$stdout_file"
  then
    echo "ERROR: integrated pipeline evidence differs: $stdout_file" >&2
    exit 1
  fi
done
for stderr_file in "$NATIVE_STDERR" "$WASM_STDERR"; do
  if [ "$(wc -l <"$stderr_file" | tr -d ' ')" -ne 2 ] ||
     [ "$(sed -n '1p' "$stderr_file")" != \
       'Code marked as unreachable has been executed. Please report this as a bug.' ]
  then
    echo "ERROR: triangle-fan fail-visible evidence differs: $stderr_file" >&2
    exit 1
  fi
  case "$(sed -n '2p' "$stderr_file")" in
    "Error found at $WEBGPU_SOURCE/wgpu_pipeline.cc:"*" in to_wgpu_topology.") ;;
    *)
      echo "ERROR: triangle-fan source binding differs: $stderr_file" >&2
      exit 1
      ;;
  esac
done
if ! cmp -s "$NATIVE_STDOUT" "$WASM_STDOUT" ||
   ! cmp -s "$NATIVE_STDERR" "$WASM_STDERR"
then
  echo "ERROR: native and Wasm integrated pipeline evidence differs" >&2
  exit 1
fi

"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" -n wgpu_pipeline_integrated_test
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" -n wgpu_pipeline_integrated_smoke

OUTPUT_BYTES="$(wc -c <"$WASM_STDOUT" | tr -d ' ')"
OUTPUT_SHA256="$(sha256_file "$WASM_STDOUT")"
SOURCE_SHA256="$(source_digest)"
printf 'PASS integrated-pipeline native/wasm bytes=%s sha256=%s source_sha256=%s fmt_sha256=%s dawn=%s emcc=%s node=%s\n' \
  "$OUTPUT_BYTES" "$OUTPUT_SHA256" "$SOURCE_SHA256" "$FMT_SHA256" \
  "$DAWN_PIN" "$EMCC_VERSION" "$NODE_VERSION"
