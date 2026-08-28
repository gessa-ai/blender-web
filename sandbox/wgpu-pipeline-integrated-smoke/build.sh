#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Device-free native/Wasm parity driver for the canonical in-tree WebGPU
# render-pipeline enum mappings, direct/indirect draw and dispatch spans, clipped
# multi-viewport/window-backbuffer rectangles, transient uniform and pipeline
# shader-module/pipeline cache publication, scoped transient bind-group validation,
# exact surviving-WGSL bind-group completeness,
# direct/indirect compute bind-group scope ordering,
# bounded-stack scheduler failure draining and failed-epoch pruning,
# layered load-action commit,
# ordinary load-action submission transactions,
# layered clear-before-draw ordering,
# fallback adapter/device owner-lifetime invalidation,
# fallback device-loss in-flight transaction cancellation,
# fail-closed vertex/index-buffer resolution,
# color-blit/indexed-fan resource guards,
# buffer/storage/context-render/
# framebuffer full/scissored-clear and copy, texture render-clear, batch, and immediate-draw
# command transactions,
# dummy-attribute binding
# plan, shader-lifetime cache separation, context-owned pipeline lifetimes, and
# overlapping-context backend-handle publication.
# Browser-main standard cursor shape/visibility publication is source- and behavior-bound too.
# Invoke through buildwrap.sh.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WEBGPU_SOURCE="${WEBGPU_SOURCE:-$ROOT/upstream/source/blender/gpu/webgpu}"
SOURCE_REPLAY_DRIVER="${SOURCE_REPLAY_DRIVER:-$ROOT/sandbox/series-replay/verify.py}"
GHOST_SOURCE="$ROOT/platform_web/ghost/GHOST_ContextWGPUWeb.cc"
GHOST_HEADER="$ROOT/platform_web/ghost/GHOST_ContextWGPUWeb.hh"
GHOST_WINDOW_SOURCE="$ROOT/platform_web/ghost/GHOST_WindowWeb.cc"
GHOST_SYSTEM_SOURCE="$ROOT/platform_web/ghost/GHOST_SystemWeb.cc"
GHOST_SYSTEM_HEADER="$ROOT/platform_web/ghost/GHOST_SystemWeb.hh"
GHOST_EVENT_BRIDGE_SOURCE="$ROOT/platform_web/ghost/GHOST_EventBridgeWeb.cc"
GHOST_IME_QUEUE_HEADER="$ROOT/platform_web/ghost/GHOST_IMEQueueWeb.hh"
GHOST_TRANSACTION_HEADER="$ROOT/platform_web/ghost/GHOST_WGPUTransaction.hh"
GHOST_WINDOW_HEADER="$ROOT/platform_web/ghost/GHOST_WindowWeb.hh"
GHOST_DISPLAY_HEADER="$ROOT/platform_web/ghost/GHOST_WebDisplayState.hh"
FIRST_PIXEL_SETTLE_CONTRACT="$HERE/first_pixel_settle_contract.py"
FIRST_PIXEL_SETTLE_TEST="$HERE/first_pixel_settle_test.cc"
VIEWPORT_CONTENT_LOADER_CONTRACT="$ROOT/sandbox/m4-viewport-content-loader/verify.py"
RESIZE_TRACE_CONTRACT="$ROOT/sandbox/m4-resize-recovery/verify_resize_trace.py"
BROWSER_SAME_TURN_CONTRACT="$ROOT/sandbox/m4-browser-same-turn-submission/verify.py"
WGPU_PREINIT_SOURCE="$ROOT/platform_web/shell/wgpu-preinit-worker.js"
DIAGNOSTICS_BOOTSTRAP_SOURCE="$ROOT/platform_web/shell/diagnostics-bootstrap.js"
WGPU_PREINIT_TEST="$HERE/preinit_worker_test.mjs"
LIVE_PREINIT_SOURCE="$HERE/live_preinit_boot.mjs"
LIVE_PREINIT_CONTRACT="$HERE/live_preinit_contract.mjs"
LIVE_PREINIT_CONTRACT_TEST="$HERE/live_preinit_contract_test.mjs"
WINDOW_ACTIVATION_CONTRACT="$HERE/window_activation_contract.py"
FRONTBUFFER_CAPABILITY_CONTRACT="$HERE/frontbuffer_capability_contract.py"
WEB_CAPABILITY_CONTRACT="$HERE/web_capability_contract.py"
WINDOW_TITLE_CONTRACT="$HERE/window_title_contract.py"
FULLSCREEN_STATE_CONTRACT="$HERE/fullscreen_state_contract.py"
POINTER_LOCK_CONTRACT="$HERE/pointer_lock_contract.py"
FOCUS_STATE_CONTRACT="$HERE/focus_state_contract.py"
BUTTON_CURSOR_CONTRACT="$ROOT/sandbox/p0-interaction-stress/verify_button_cursor.py"
INPUT_REDRAW_RECOVERY_CONTRACT="$ROOT/sandbox/p0-interaction-stress/verify_input_redraw_recovery.py"
AUXILIARY_CACHE_REDRAW_CONTRACT="$ROOT/sandbox/p0-interaction-stress/verify_auxiliary_cache_redraw.py"
KEYBOARD_FOCUS_CONTRACT="$ROOT/sandbox/m4-keyboard-focus/source_contract.py"
IME_NONCOMPOSING_KEY_CONTRACT="$ROOT/sandbox/m4-ime-noncomposing-key-bridge/source_contract.py"
IME_NONCOMPOSING_KEY_TEST="$ROOT/sandbox/m4-ime-noncomposing-key-bridge/ime_keyboard_test.mjs"
IME_NONCOMPOSING_PRODUCT_TEST="$ROOT/sandbox/m4-ime-noncomposing-key-bridge/product_text_state_test.mjs"
MODIFIER_SIDE_CONTRACT="$ROOT/sandbox/m4-modifier-side-state/source_contract.py"
MOUSE_RELEASE_OWNERSHIP_CONTRACT="$ROOT/sandbox/m4-mouse-release-ownership/source_contract.py"
MOUSE_RELEASE_OWNERSHIP_TEST="$ROOT/sandbox/m4-mouse-release-ownership/mouse_release_test.mjs"
WINDOW_LIFECYCLE_CONTRACT="$HERE/window_lifecycle_contract.py"
CALLBACK_REGISTRATION_SOAK_CONTRACT="$ROOT/sandbox/m8-callback-registration-soak/source_contract.py"
WINDOW_HIT_TEST_CONTRACT="$HERE/window_hit_test_contract.py"
CLIPBOARD_BRIDGE_CONTRACT="$HERE/clipboard_bridge_contract.py"
IME_BRIDGE_CONTRACT="$HERE/ime_bridge_contract.py"
IME_FOCUS_OWNERSHIP_CONTRACT="$ROOT/sandbox/m4-ime-focus-ownership/source_contract.py"
IME_FOCUS_OWNERSHIP_TEST="$ROOT/platform_web/ghost/harness/ime_composition_test.mjs"
FOCUS_TRANSITION_ORDER_CONTRACT="$ROOT/sandbox/m4-focus-transition-order/source_contract.py"
FOCUS_TRANSITION_ORDER_TEST="$ROOT/sandbox/m4-focus-transition-order/focus_transition_order_test.mjs"
CURSOR_BRIDGE_CONTRACT="$HERE/cursor_bridge_contract.py"
CURSOR_BRIDGE_TEST="$HERE/cursor_bridge_test.mjs"
GHOST_BASE_WINDOW_SOURCE="$ROOT/upstream/intern/ghost/intern/GHOST_Window.cc"
GHOST_TYPES_SOURCE="$ROOT/upstream/intern/ghost/GHOST_Types.hh"
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
  local webgpu_files=(
    wgpu_pipeline.cc
    wgpu_pipeline.hh
    wgpu_common.hh
    wgpu_buffer.cc
    wgpu_storage_buffer.cc
    wgpu_backend.cc
    wgpu_context.cc
    wgpu_context.hh
    wgpu_batch.cc
    wgpu_immediate.cc
    wgpu_framebuffer.cc
    wgpu_texture.cc
    wgpu_shader.cc
    wgpu_shader.hh
    wgpu_state_table.hh
  )
  local upstream_files=(
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
  local webgpu_digest
  local upstream_digest
  local ghost_digest
  if command -v sha256sum >/dev/null 2>&1; then
    webgpu_digest="$(cd "$WEBGPU_SOURCE" && sha256sum "${webgpu_files[@]}" | sha256sum | awk '{print $1}')"
    upstream_digest="$(cd "$ROOT/upstream" && sha256sum "${upstream_files[@]}" | sha256sum | awk '{print $1}')"
    ghost_digest="$(cd "$ROOT" && \
      sha256sum platform_web/ghost/GHOST_ContextWGPUWeb.cc \
                platform_web/ghost/GHOST_ContextWGPUWeb.hh \
                platform_web/ghost/GHOST_WindowWeb.cc \
                platform_web/ghost/GHOST_WindowWeb.hh \
                platform_web/ghost/GHOST_WebDisplayState.hh \
                platform_web/ghost/GHOST_EventBridgeWeb.cc \
                platform_web/ghost/GHOST_SystemWeb.cc \
                platform_web/ghost/GHOST_SystemWeb.hh \
                platform_web/ghost/GHOST_WGPUTransaction.hh \
                platform_web/shell/wgpu-preinit-worker.js \
                platform_web/shell/diagnostics-bootstrap.js | sha256sum | awk '{print $1}')"
    printf '%s\n%s\n%s\n' "$webgpu_digest" "$upstream_digest" "$ghost_digest" | sha256sum | awk '{print $1}'
  else
    webgpu_digest="$(cd "$WEBGPU_SOURCE" && \
      shasum -a 256 "${webgpu_files[@]}" | shasum -a 256 | awk '{print $1}')"
    upstream_digest="$(cd "$ROOT/upstream" && \
      shasum -a 256 "${upstream_files[@]}" | shasum -a 256 | awk '{print $1}')"
    ghost_digest="$(cd "$ROOT" && \
      shasum -a 256 platform_web/ghost/GHOST_ContextWGPUWeb.cc \
                    platform_web/ghost/GHOST_ContextWGPUWeb.hh \
                    platform_web/ghost/GHOST_WindowWeb.cc \
                    platform_web/ghost/GHOST_WindowWeb.hh \
                    platform_web/ghost/GHOST_WebDisplayState.hh \
                    platform_web/ghost/GHOST_EventBridgeWeb.cc \
                    platform_web/ghost/GHOST_SystemWeb.cc \
                    platform_web/ghost/GHOST_SystemWeb.hh \
                    platform_web/ghost/GHOST_WGPUTransaction.hh \
                    platform_web/shell/wgpu-preinit-worker.js \
                    platform_web/shell/diagnostics-bootstrap.js | \
      shasum -a 256 | awk '{print $1}')"
    printf '%s\n%s\n%s\n' "$webgpu_digest" "$upstream_digest" "$ghost_digest" | \
      shasum -a 256 | awk '{print $1}'
  fi
}

require_file "$PYBIN"
require_file "$HOST_CMAKE"
require_file "$ROOT/scripts/ninja-locked.sh"
require_file "$ROOT/sandbox/series-replay/verify.py"
require_file "$SOURCE_REPLAY_DRIVER"
if ! cmp -s "$ROOT/sandbox/series-replay/verify.py" "$SOURCE_REPLAY_DRIVER"; then
  echo "ERROR: source replay driver differs from the checked-in verifier" >&2
  exit 1
fi
SOURCE_REPLAY_ROOT="$(cd "$(dirname "$SOURCE_REPLAY_DRIVER")/../.." && pwd -P)"
WEBGPU_SOURCE_ROOT="$(cd "$WEBGPU_SOURCE/../../../.." && pwd -P)"
if [ "$(cd "$SOURCE_REPLAY_ROOT/patches" && pwd -P)" != "$(cd "$ROOT/patches" && pwd -P)" ] ||
   [ "$(cd "$SOURCE_REPLAY_ROOT/upstream" && pwd -P)" != "$WEBGPU_SOURCE_ROOT" ]
then
  echo "ERROR: source replay root does not bind the checked-in patches and selected source" >&2
  exit 1
fi
require_file "$HERE/integrated_pipeline_test.cc"
require_file "$HERE/ghost_acquisition_lifetime_test.cc"
require_file "$GHOST_SOURCE"
require_file "$GHOST_HEADER"
require_file "$GHOST_WINDOW_SOURCE"
require_file "$GHOST_WINDOW_HEADER"
require_file "$GHOST_EVENT_BRIDGE_SOURCE"
require_file "$GHOST_IME_QUEUE_HEADER"
require_file "$GHOST_DISPLAY_HEADER"
require_file "$FIRST_PIXEL_SETTLE_CONTRACT"
require_file "$VIEWPORT_CONTENT_LOADER_CONTRACT"
require_file "$BROWSER_SAME_TURN_CONTRACT"
require_file "$FIRST_PIXEL_SETTLE_TEST"
require_file "$GHOST_BASE_WINDOW_SOURCE"
require_file "$GHOST_TYPES_SOURCE"
require_file "$GHOST_SYSTEM_SOURCE"
require_file "$GHOST_SYSTEM_HEADER"
require_file "$GHOST_TRANSACTION_HEADER"
require_file "$WGPU_PREINIT_SOURCE"
require_file "$DIAGNOSTICS_BOOTSTRAP_SOURCE"
require_file "$WGPU_PREINIT_TEST"
require_file "$LIVE_PREINIT_SOURCE"
require_file "$LIVE_PREINIT_CONTRACT"
require_file "$LIVE_PREINIT_CONTRACT_TEST"
require_file "$WINDOW_ACTIVATION_CONTRACT"
require_file "$FRONTBUFFER_CAPABILITY_CONTRACT"
require_file "$WEB_CAPABILITY_CONTRACT"
require_file "$WINDOW_TITLE_CONTRACT"
require_file "$FULLSCREEN_STATE_CONTRACT"
require_file "$POINTER_LOCK_CONTRACT"
require_file "$FOCUS_STATE_CONTRACT"
require_file "$BUTTON_CURSOR_CONTRACT"
require_file "$INPUT_REDRAW_RECOVERY_CONTRACT"
require_file "$AUXILIARY_CACHE_REDRAW_CONTRACT"
require_file "$KEYBOARD_FOCUS_CONTRACT"
require_file "$IME_NONCOMPOSING_KEY_CONTRACT"
require_file "$IME_NONCOMPOSING_KEY_TEST"
require_file "$IME_NONCOMPOSING_PRODUCT_TEST"
require_file "$MOUSE_RELEASE_OWNERSHIP_CONTRACT"
require_file "$MODIFIER_SIDE_CONTRACT"
require_file "$MOUSE_RELEASE_OWNERSHIP_TEST"
require_file "$WINDOW_LIFECYCLE_CONTRACT"
require_file "$CALLBACK_REGISTRATION_SOAK_CONTRACT"
require_file "$WINDOW_HIT_TEST_CONTRACT"
require_file "$CLIPBOARD_BRIDGE_CONTRACT"
require_file "$IME_BRIDGE_CONTRACT"
require_file "$IME_FOCUS_OWNERSHIP_CONTRACT"
require_file "$FOCUS_TRANSITION_ORDER_CONTRACT"
require_file "$FOCUS_TRANSITION_ORDER_TEST"
require_file "$IME_FOCUS_OWNERSHIP_TEST"
require_file "$CURSOR_BRIDGE_CONTRACT"
require_file "$CURSOR_BRIDGE_TEST"
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
  wgpu_buffer.cc \
  wgpu_storage_buffer.cc \
  wgpu_backend.cc \
  wgpu_context.cc \
  wgpu_context.hh \
  wgpu_batch.cc \
  wgpu_immediate.cc \
  wgpu_framebuffer.cc \
  wgpu_texture.cc \
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
require_fixed_count 1 '"Vertex buffer slot %u required by %s was not set.",' \
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
  'class OrderedQueueScheduler {' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'std::unordered_map<uint64_t, size_t> queued_epoch_counts;' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'static void prune_failed_epoch_if_unreferenced(State &state, const uint64_t epoch)' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'static void prune_unreferenced_failed_epochs(State &state)' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'size_t failed_epoch_count() const' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'class ScopedHandleCache {' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'if (shader->explicit_layout_required() &&' \
  "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 \
  '!shader->ensure_explicit_layout(instance, device))' \
  "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 \
  'if (info.shader->explicit_layout_required() &&' \
  "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 \
  '!info.shader->ensure_explicit_layout(instance, device))' \
  "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 1 \
  'bool WGPUShader::ensure_shader_modules(const wgpu::Instance &instance,' \
  "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 1 \
  'shader_module_cache_.get_or_create(' \
  "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 1 \
  'compute_pipeline_cache_.get_or_create(' \
  "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 1 \
  'return cache_.get_or_create(' \
  "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 2 \
  'shader->ensure_shader_modules(ctx->instance_get(), ctx->device_get())' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'shader->ensure_shader_modules(ctx->instance_get(), ctx->device_get())' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
require_fixed_count 2 \
  'shader->compute_pipeline(ctx->instance_get(), device);' \
  "$WEBGPU_SOURCE/wgpu_backend.cc"
require_fixed_count 2 \
  'ctx->batch_pipeline_pool_get().get(' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'ctx->immediate_pipeline_pool_get().get(' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
require_fixed_count 0 \
  'static webgpu::WGPUPipelinePool' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 0 \
  'static webgpu::WGPUPipelinePool' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
require_fixed_count 1 \
  'webgpu::WGPUPipelinePool &batch_pipeline_pool_get()' \
  "$WEBGPU_SOURCE/wgpu_context.hh"
require_fixed_count 1 \
  'webgpu::WGPUPipelinePool &immediate_pipeline_pool_get()' \
  "$WEBGPU_SOURCE/wgpu_context.hh"
require_fixed_count 1 \
  'webgpu::ScopedHandleCache<uint8_t, wgpu::ComputePipeline> &triangle_fan_pipeline_cache_get()' \
  "$WEBGPU_SOURCE/wgpu_context.hh"
require_fixed_count 1 'webgpu::WGPUPipelinePool batch_pipeline_pool_;' \
  "$WEBGPU_SOURCE/wgpu_context.hh"
require_fixed_count 1 'webgpu::WGPUPipelinePool immediate_pipeline_pool_;' \
  "$WEBGPU_SOURCE/wgpu_context.hh"
require_fixed_count 1 \
  'webgpu::ScopedHandleCache<uint8_t, wgpu::ComputePipeline> triangle_fan_pipeline_cache_;' \
  "$WEBGPU_SOURCE/wgpu_context.hh"
require_fixed_count 1 \
  'class LatestOwnerHandleRegistry {' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'webgpu::LatestOwnerHandleRegistry<WGPUContext, BackendHandles> s_backend_handles;' \
  "$WEBGPU_SOURCE/wgpu_context.hh"
require_fixed_count 1 \
  's_backend_handles.publish(this, {instance_, device_, queue_});' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 \
  's_backend_handles.forget(this);' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 \
  'const WGPUContext::BackendHandles handles = WGPUContext::backend_handles();' \
  "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 0 'wgpu::Device WGPUContext::s_device' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 's_device = nullptr;' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 'ctx.triangle_fan_pipeline_cache_get();' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 0 \
  'static webgpu::ScopedHandleCache<uint8_t, wgpu::ComputePipeline>' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'sampler_cache_.get_or_create_ordered(' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 \
  'sampler_cache_.lookup(key);' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 2 \
  'HandleT get_or_create_ordered(' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'uint64_t current_epoch() const' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline auto dummy_vertex_buffer_create(DeviceT &device)' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'dummy_vertex_buffer_cache_.get_or_create(' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 \
  'return webgpu::dummy_vertex_buffer_create(device_);' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 \
  'webgpu::ScopedHandleCache<uint8_t, wgpu::Buffer> dummy_vertex_buffer_cache_;' \
  "$WEBGPU_SOURCE/wgpu_context.hh"
require_fixed_count 0 \
  'dummy_vertex_buffer_ = device_.CreateBuffer(&bd);' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 \
  'wgpu::Buffer dummy_vertex_buffer_;' \
  "$WEBGPU_SOURCE/wgpu_context.hh"
require_fixed_count 0 \
  'sampler_cache_.find(' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 \
  'cache_handle_if_valid(sampler_cache_' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 \
  'inline void command_pass_encode_submit_scoped(const InstanceT &instance,' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline void command_encode_submit_scoped(const InstanceT &instance,' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline auto transient_resource_gate_scoped(OrderedQueueScheduler &scheduler,' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline auto transient_resource_create_scoped(const InstanceT &instance,' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 3 \
  'webgpu::transient_resource_create_scoped(' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 \
  'webgpu::transient_resource_create_scoped(' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 2 \
  'webgpu::transient_resource_create_scoped(' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 1 \
  'bool Buffer::create_transient(const wgpu::Instance &instance,' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 3 '.create_transient(' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 2 '.create_transient(' "$WEBGPU_SOURCE/wgpu_immediate.cc"
require_fixed_count 0 \
  'command_pass_encode_submit_if_valid' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 0 \
  'command_encode_submit_if_valid' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
"$PYBIN" - "$WEBGPU_SOURCE" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
sources = tuple(root.glob("*.cc")) + tuple(root.glob("*.hh"))
common = root / "wgpu_common.hh"
for path in sources:
    text = path.read_text(encoding="utf-8")
    for obsolete in (
        "command_encode_submit_if_valid",
        "command_pass_encode_submit_if_valid",
    ):
        if obsolete in text:
            raise SystemExit(f"ERROR: {path.name} retains obsolete {obsolete}")
    if path != common:
        for direct in (".Submit(", ".WriteBuffer(", ".WriteTexture("):
            if direct in text:
                raise SystemExit(f"ERROR: {path.name} bypasses ordered queue helper with {direct}")

common_text = common.read_text(encoding="utf-8")
for direct in (".Submit(", ".WriteBuffer(", ".WriteTexture("):
    # Browser and native paths intentionally share the same helper but use different timing:
    # same-turn queue mutation in Wasm, validation-ordered scheduling on native Dawn.
    if common_text.count(direct) != 2:
        raise SystemExit(f"ERROR: common queue boundary is ambiguous for {direct}")
if common_text.count("device.PushErrorScope(") != 3:
    raise SystemExit("ERROR: command helper does not push validation/OOM/internal scopes")
if common_text.count("device.PopErrorScope(") != 6:
    raise SystemExit("ERROR: command helper does not pop all scopes on native and Wasm")
for marker in (
    "wgpu::CallbackMode::WaitAnyOnly",
    "wgpu::CallbackMode::AllowSpontaneous",
    "state->failed_epochs.insert(epoch);",
    "state_->current_epoch++;",
):
    if marker not in common_text:
        raise SystemExit(f"ERROR: ordered scope boundary is missing {marker}")

scheduler_start = common_text.index("class OrderedQueueScheduler {")
scheduler_end = common_text.index("/** Shared completion state", scheduler_start)
scheduler = common_text[scheduler_start:scheduler_end]
for marker in (
    "bool draining = false;",
    "if (state->draining) {",
    "state->draining = true;",
    "for (;;) {",
    "finish(state, entry->epoch, false);\n        continue;",
    "state_->queued_epoch_counts[entry->epoch]++;",
    "prune_unreferenced_failed_epochs(*state_);",
):
    if marker not in scheduler:
        raise SystemExit(f"ERROR: ordered scheduler drain/prune contract is missing {marker}")
PY
require_fixed_count 1 \
  'inline bool transient_handle_publish_if_valid(HandleT candidate, HandleT &result)' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline bool bind_group_binding_ids_complete(' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline BindGroupBindingStatus bind_group_binding_ids_status(' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'request_webgpu_redraw_retry();' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 1 \
  'bool bind_group_entries_complete(' \
  "$WEBGPU_SOURCE/wgpu_shader.hh"
require_fixed_count 1 \
  'const webgpu::BindGroupBindingStatus status = webgpu::bind_group_binding_ids_status(' \
  "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 1 \
  'if (!shader->bind_group_entries_complete(entries, pending_bindings)) {' \
  "$WEBGPU_SOURCE/wgpu_backend.cc"
require_fixed_count 4 \
  'if (!shader->bind_group_entries_complete(entries, pending_bindings)) {' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'if (!shader->bind_group_entries_complete(entries, pending_bindings)) {' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
require_fixed_count 2 \
  'mv_entry.binding = shader->multi_viewport_binding();' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
"$PYBIN" - "$WEBGPU_SOURCE/wgpu_backend.cc" "$WEBGPU_SOURCE/wgpu_batch.cc" \
  "$WEBGPU_SOURCE/wgpu_immediate.cc" <<'PY'
from pathlib import Path
import sys


def method(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise SystemExit(f"ERROR: unterminated method: {marker}")


backend = Path(sys.argv[1]).read_text(encoding="utf-8")
batch = Path(sys.argv[2]).read_text(encoding="utf-8")
immediate = Path(sys.argv[3]).read_text(encoding="utf-8")
guard = "if (!shader->bind_group_entries_complete(entries, pending_bindings)) {"
append = "ctx->append_resource_bind_entries(shader, entries, pending_bindings);"
command = "webgpu::command_encode_submit_scoped("

compute = method(backend, "static bool build_compute_bind_group(")
if compute.count(append) != 1 or compute.count(guard) != 1:
    raise SystemExit("ERROR: compute bind-group completeness transaction is ambiguous")
if not (compute.index(append) < compute.index(guard) < compute.index("if (entries.empty())")):
    raise SystemExit("ERROR: compute confuses missing resources with an empty layout")
resource_scope = "webgpu::transient_resource_create_scoped("
raw_create = "ctx->create_bind_group_checked(bgl, entries)"
if compute.count(resource_scope) != 1 or compute.count(raw_create) != 1:
    raise SystemExit("ERROR: compute bind-group creation is outside one scoped resource gate")
if compute.index(resource_scope) >= compute.index(raw_create):
    raise SystemExit("ERROR: compute bind-group scope begins after resource creation")

for label, body in (
    ("direct compute", method(backend, "void WGPUBackend::compute_dispatch(int groups_x_len,")),
    ("indirect compute", method(backend, "void WGPUBackend::compute_dispatch_indirect(")),
):
    build = "if (!build_compute_bind_group(ctx, shader, pipeline, bind_group, have_bg)) {"
    scoped_command = "webgpu::command_pass_encode_submit_scoped("
    if body.count(build) != 1 or body.count(scoped_command) != 1:
        raise SystemExit(f"ERROR: {label} bind/command transaction is ambiguous")
    if body.index(build) >= body.index(scoped_command):
        raise SystemExit(f"ERROR: {label} reserves command work before bind-group validation")

for label, body, expected in (
    ("direct batch", method(batch, "void WGPUBatch::draw(int vertex_first,"), 2),
    ("indirect batch", method(batch, "void WGPUBatch::multi_draw_indirect(StorageBuf *indirect_buf,"), 2),
    ("immediate", method(immediate, "void WGPUImmediate::end()"), 1),
):
    guards = []
    commands = []
    start = 0
    while (position := body.find(guard, start)) >= 0:
        guards.append(position)
        start = position + len(guard)
    start = 0
    while (position := body.find(command, start)) >= 0:
        commands.append(position)
        start = position + len(command)
    if len(guards) != expected or len(commands) != expected:
        raise SystemExit(f"ERROR: {label} completeness/command census differs")
    if any(guard_position >= command_position for guard_position, command_position in zip(guards, commands)):
        raise SystemExit(f"ERROR: {label} checks binding completeness after encoder work")
PY
require_fixed_count 1 \
  'inline bool framebuffer_load_action_commit_if_valid(' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'class FramebufferLoadActionTracker {' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'class FramebufferLoadActionCompletionGroup {' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'load_action_transaction() const' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.hh"
require_fixed_count 1 \
  'load_action_transaction_prepare(' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.hh"
require_fixed_count 1 \
  'inline bool vertex_buffer_handles_resolve_if_valid(const BindingRangeT &bindings,' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline bool index_buffer_handle_resolve_if_required(const bool required,' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 2 \
  'if (!webgpu::vertex_buffer_handles_resolve_if_valid(' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'if (!webgpu::vertex_buffer_handles_resolve_if_valid(' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
require_fixed_count 2 \
  'if (!webgpu::index_buffer_handle_resolve_if_required(' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'if (!webgpu::index_buffer_handle_resolve_if_required(' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
"$PYBIN" - "$WEBGPU_SOURCE/wgpu_batch.cc" "$WEBGPU_SOURCE/wgpu_immediate.cc" <<'PY'
from pathlib import Path
import re
import sys


def method(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise SystemExit(f"ERROR: unterminated method: {marker}")


batch = Path(sys.argv[1]).read_text(encoding="utf-8")
immediate = Path(sys.argv[2]).read_text(encoding="utf-8")
direct = method(batch, "void WGPUBatch::draw(int vertex_first,")
indirect = method(batch, "void WGPUBatch::multi_draw_indirect(StorageBuf *indirect_buf,")
immediate_end = method(immediate, "void WGPUImmediate::end()")
guard = "if (!webgpu::index_buffer_handle_resolve_if_required("

for label, body, set_count in (
    ("direct batch", direct, 4),
    ("indirect batch", indirect, 1),
    ("immediate", immediate_end, 1),
):
    if body.count(guard) != 1:
        raise SystemExit(f"ERROR: {label} lacks one index-buffer resolution transaction")
    if body.index(guard) >= body.index("wgpu::RenderPipeline pipeline"):
        raise SystemExit(f"ERROR: {label} resolves its index buffer after pipeline work")
    bindings = re.findall(r"SetIndexBuffer\(([^,\n]+)", body)
    if len(bindings) != set_count or any(binding.strip() != "index_buffer" for binding in bindings):
        raise SystemExit(f"ERROR: {label} does not bind only the resolved index buffer")

if "emulate_triangle_fan || elem != nullptr" not in direct:
    raise SystemExit("ERROR: direct batch index requirement omits fan or frontend index state")
if "const bool indexed = elem != nullptr;" not in indirect:
    raise SystemExit("ERROR: indirect batch still infers indexed semantics from allocation success")
if indirect.index(guard) >= indirect.index("webgpu::IndirectDrawSpan indirect_span;"):
    raise SystemExit("ERROR: indirect batch resolves its index buffer after command-shape selection")
if immediate_end.index(guard) >= immediate_end.index("webgpu::Buffer vbo;"):
    raise SystemExit("ERROR: immediate draw resolves its index buffer after vertex allocation")
PY
require_fixed_count 1 \
  'if (!webgpu::transient_handle_publish_if_valid(' \
  "$WEBGPU_SOURCE/wgpu_backend.cc"
require_fixed_count 4 \
  'if (!webgpu::transient_handle_publish_if_valid(' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'if (!webgpu::transient_handle_publish_if_valid(' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
require_fixed_count 2 \
  'if (!build_compute_bind_group(ctx, shader, pipeline, bind_group, have_bg)) {' \
  "$WEBGPU_SOURCE/wgpu_backend.cc"
require_fixed_count 0 \
  'SetBindGroup(0, ctx->create_bind_group_checked' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 0 \
  'SetBindGroup(0, ctx->create_bind_group_checked' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
require_fixed_count 3 \
  'webgpu::command_pass_encode_submit_scoped(' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
"$PYBIN" - "$WEBGPU_SOURCE/wgpu_context.cc" <<'PY'
from pathlib import Path
import sys


source = Path(sys.argv[1]).read_text(encoding="utf-8")


def method_body(marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated method: {marker}")


transactions = (
    (
        "bool WGPUContext::blit_color_render(",
        "[&](auto &encoder) { return encoder.BeginRenderPass(&rp); }",
        (
            "pass.SetPipeline(pipeline);",
            "pass.SetViewport(float(dst_x), float(dst_y), float(w), float(h), 0.0f, 1.0f);",
            "pass.SetScissorRect(dst_x, dst_y, w, h);",
            "pass.SetBindGroup(0, bind_group);",
            "pass.Draw(3, 1, 0, 0);",
        ),
    ),
    (
        "bool WGPUContext::blit_depth_render(",
        "[&](auto &encoder) { return encoder.BeginRenderPass(&pass_desc); }",
        (
            "pass.SetPipeline(pipeline);",
            "pass.SetBindGroup(0, bind_group);",
            "pass.SetViewport(0.0f, 0.0f, float(w), float(h), 0.0f, 1.0f);",
            "pass.SetScissorRect(0, 0, w, h);",
            "pass.Draw(3, 1, 0, 0);",
        ),
    ),
    (
        "bool WGPUContext::upload_depth_render(",
        "[&](auto &encoder) { return encoder.BeginRenderPass(&pass_desc); }",
        (
            "pass.SetPipeline(pipeline);",
            "pass.SetBindGroup(0, bind_group);",
            "pass.SetViewport(float(dst_x), float(dst_y), float(w), float(h), 0.0f, 1.0f);",
            "pass.SetScissorRect(dst_x, dst_y, w, h);",
            "pass.Draw(3, 1, 0, 0);",
        ),
    ),
)

for marker, begin_pass, pass_body in transactions:
    body = method_body(marker)
    helper = "webgpu::command_pass_encode_submit_scoped("
    resource_gate = "webgpu::transient_resource_create_scoped("
    if body.count(helper) != 1 or body.count(begin_pass) != 1 or body.count(resource_gate) != 1:
        raise SystemExit(f"ERROR: {marker} does not contain one checked render transaction")
    forbidden = (
        "CreateCommandEncoder()",
        ".Finish()",
        ".Submit(1,",
        ".End();",
    )
    if any(needle in body for needle in forbidden):
        raise SystemExit(f"ERROR: {marker} retains an unchecked command operation")
    helper_offset = body.index(helper)
    if body.index(resource_gate) >= helper_offset:
        raise SystemExit(f"ERROR: {marker} creates its bind group after command reservation")
    positions = [body.find(needle, helper_offset) for needle in pass_body]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise SystemExit(f"ERROR: {marker} render body is missing or reordered")
PY
require_fixed_count 4 \
  'webgpu::command_pass_encode_submit_scoped(' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
"$PYBIN" - "$WEBGPU_SOURCE/wgpu_framebuffer.cc" <<'PY'
from pathlib import Path
import sys


source = Path(sys.argv[1]).read_text(encoding="utf-8")


def method_body(marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated method: {marker}")


transactions = (
    (
        "bool WGPUFrameBuffer::submit_scissored_color_clear(",
        (
            "pass.SetPipeline(pipeline);",
            "pass.SetScissorRect(plan.x, plan.y, plan.width, plan.height);",
            "pass.SetBindGroup(0, bind_group);",
            "pass.Draw(3, 1, 0, 0);",
        ),
    ),
    (
        "bool WGPUFrameBuffer::submit_scissored_depth_stencil_clear(",
        (
            "pass.SetPipeline(pipeline);",
            "pass.SetScissorRect(plan.x, plan.y, plan.width, plan.height);",
            "pass.SetBindGroup(0, bind_group);",
            "if (clear_stencil) {",
            "pass.SetStencilReference(clear_stencil_value);",
            "pass.Draw(3, 1, 0, 0);",
        ),
    ),
)

for marker, pass_body in transactions:
    body = method_body(marker)
    helper = "webgpu::command_pass_encode_submit_scoped("
    resource_gate = "webgpu::transient_resource_create_scoped("
    begin_pass = "[&](auto &encoder) { return encoder.BeginRenderPass(&pass_descriptor); }"
    if body.count(helper) != 1 or body.count(begin_pass) != 1 or body.count(resource_gate) != 1:
        raise SystemExit(f"ERROR: {marker} does not contain one checked render transaction")
    forbidden = (
        "CreateCommandEncoder()",
        ".Finish()",
        ".Submit(1,",
        ".End();",
    )
    if any(needle in body for needle in forbidden):
        raise SystemExit(f"ERROR: {marker} retains an unchecked command operation")
    helper_offset = body.index(helper)
    if body.index(resource_gate) >= helper_offset:
        raise SystemExit(f"ERROR: {marker} creates its bind group after command reservation")
    positions = [body.find(needle, helper_offset) for needle in pass_body]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise SystemExit(f"ERROR: {marker} render body is missing or reordered")

full_clear_transactions = (
    "bool WGPUFrameBuffer::submit_clear(",
    "bool WGPUFrameBuffer::clear_attachment_full(",
)

for marker in full_clear_transactions:
    body = method_body(marker)
    helper = "webgpu::command_pass_encode_submit_scoped("
    begin_pass = "return encoder.BeginRenderPass(&rp);"
    empty_pass_body = "[](auto & /*pass*/) {}"
    if body.count(helper) != 1 or body.count(begin_pass) != 1 or body.count(empty_pass_body) != 1:
        raise SystemExit(f"ERROR: {marker} does not contain one checked full-clear transaction")
    forbidden = (
        "CreateCommandEncoder()",
        ".Finish()",
        ".Submit(1,",
        ".End();",
    )
    if any(needle in body for needle in forbidden):
        raise SystemExit(f"ERROR: {marker} retains an unchecked command operation")

materialize_body = method_body("bool WGPUFrameBuffer::load_action_transaction_prepare(")
ordered_commit = (
    "if (!load_pass_viewport_plan(draw_viewport))",
    "if (load_action->stage(uint32_t(index)))",
    "webgpu::FramebufferLoadActionCompletionGroup completions(",
    "draw_completion = completions.completion();",
    "std::function<void(bool)> clear_completion = completions.completion();",
    "if (!clear_attachment_full(",
)
positions = [materialize_body.find(needle) for needle in ordered_commit]
if any(position < 0 for position in positions) or positions != sorted(positions):
    raise SystemExit("ERROR: layered load clear does not share the draw completion barrier")
for obsolete in (
    "layered_load_clear_pending_mask_",
    "load_store_[index].load_action = GPU_LOADACTION_LOAD;",
    "framebuffer_load_action_commit_if_valid(",
    "load_action_transaction();",
):
    if obsolete in materialize_body:
        raise SystemExit(f"ERROR: layered load clear retains obsolete {obsolete}")

load_pass_body = method_body("wgpu::RenderPassEncoder WGPUFrameBuffer::begin_load_pass(")
load_pass_publication = """wgpu::RenderPassEncoder pass;
  if (!webgpu::transient_handle_publish_if_valid(encoder.BeginRenderPass(&rp), pass))
  {
    return nullptr;
  }"""
if load_pass_body.count(load_pass_publication) != 1:
    raise SystemExit("ERROR: framebuffer load pass is not published atomically")
if "wgpu::RenderPassEncoder pass = encoder.BeginRenderPass(&rp);" in load_pass_body:
    raise SystemExit("ERROR: framebuffer load pass retains unchecked direct publication")
if "materialize_layered_loadstore_clears(" in load_pass_body or \
   "load_action_transaction_prepare(" in load_pass_body:
    raise SystemExit("ERROR: framebuffer load pass reserves layered clears behind its draw")
if load_pass_body.count("load_action->stage(") != 2:
    raise SystemExit("ERROR: framebuffer load pass does not stage color and depth clears")
if "load_action = GPU_LOADACTION_LOAD" in load_pass_body or \
   ".load_action = GPU_LOADACTION_LOAD" in load_pass_body:
    raise SystemExit("ERROR: framebuffer load pass still commits during descriptor assembly")
late_view_positions = [
    load_pass_body.find("if (load_action->stage(uint32_t(attachment_index)))"),
    load_pass_body.find("dsa.view = attachment_view("),
    load_pass_body.find("if (dsa.view == nullptr)"),
    load_pass_body.find("const bool depth_clears = load_action->stage(uint32_t(depth_type));"),
]
if any(position < 0 for position in late_view_positions) or late_view_positions != sorted(
    late_view_positions
):
    raise SystemExit("ERROR: later depth view cannot reject an already staged color clear")
load_pass_positions = [
    load_pass_body.find(needle)
    for needle in (
        load_pass_publication,
        "pass.SetViewport(float(draw_viewport.viewport.viewport_x),",
        "pass.SetScissorRect(draw_viewport.scissor_x,",
        "return pass;",
    )
]
if any(position < 0 for position in load_pass_positions) or load_pass_positions != sorted(
    load_pass_positions
):
    raise SystemExit("ERROR: framebuffer load-pass guard does not precede dependent work")

blit_body = method_body("void WGPUFrameBuffer::blit_to(")
helper = "webgpu::command_encode_submit_scoped("
if blit_body.count(helper) != 2:
    raise SystemExit("ERROR: framebuffer blit does not contain two checked copy transactions")
forbidden = (
    "CreateCommandEncoder()",
    ".Finish()",
    ".Submit(1,",
)
if any(needle in blit_body for needle in forbidden):
    raise SystemExit("ERROR: framebuffer blit retains an unchecked command operation")

first_helper = blit_body.index(helper)
second_helper = blit_body.index(helper, first_helper + len(helper))
bridge_to_buffer = blit_body.index("encoder.CopyTextureToBuffer(")
bridge_to_texture = blit_body.index("encoder.CopyBufferToTexture(")
raw_copy = blit_body.index("encoder.CopyTextureToTexture(")
if not first_helper < bridge_to_buffer < bridge_to_texture < second_helper < raw_copy:
    raise SystemExit("ERROR: framebuffer copy operations are outside their checked transactions")
if any(
    blit_body.count(needle) != 1
    for needle in (
        "encoder.CopyTextureToBuffer(",
        "encoder.CopyBufferToTexture(",
        "encoder.CopyTextureToTexture(",
    )
):
    raise SystemExit("ERROR: framebuffer copy transaction is ambiguous")
PY
require_fixed_count 4 \
  'load_action = fb->load_action_transaction();' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 4 \
  'fb->load_action_transaction_prepare(load_action, load_action_completion)' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 4 \
  'load_action_completion(valid);' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'load_action = fb->load_action_transaction();' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
require_fixed_count 1 \
  'fb->load_action_transaction_prepare(load_action, load_action_completion)' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
require_fixed_count 1 \
  'load_action_completion(valid);' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
"$PYBIN" - "$WEBGPU_SOURCE/wgpu_batch.cc" "$WEBGPU_SOURCE/wgpu_immediate.cc" <<'PY'
from pathlib import Path
import sys

def method(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise SystemExit(f"ERROR: unterminated method {marker}")


batch = Path(sys.argv[1]).read_text(encoding="utf-8")
immediate = Path(sys.argv[2]).read_text(encoding="utf-8")
transactions = (
    ("direct batch", method(batch, "void WGPUBatch::draw(int vertex_first,"), 2),
    ("indirect batch", method(batch, "void WGPUBatch::multi_draw_indirect(StorageBuf *indirect_buf,"), 2),
    ("immediate", method(immediate, "void WGPUImmediate::end()"), 1),
)
markers = (
    "load_action = fb->load_action_transaction();",
    "load_action_completion;",
    "fb->load_action_transaction_prepare(load_action, load_action_completion)",
    "webgpu::command_encode_submit_scoped(",
    "fb->begin_load_pass(",
    "ctx->create_bind_group_checked(",
    "load_action_completion(valid);",
)
for label, body, expected in transactions:
    positions = []
    for marker in markers:
        found = []
        offset = 0
        while (position := body.find(marker, offset)) >= 0:
            found.append(position)
            offset = position + len(marker)
        if len(found) != expected:
            raise SystemExit(f"ERROR: {label} load-action boundary census differs for {marker}")
        positions.append(found)
    for index in range(expected):
        command_path = [marker_positions[index] for marker_positions in positions]
        if command_path != sorted(command_path):
            raise SystemExit(f"ERROR: {label} commits before its late bind/submission boundary")

for path in (Path(sys.argv[1]), Path(sys.argv[2])):
    source = path.read_text(encoding="utf-8")
    for obsolete in (
        "begin_load_pass(mv_enc, layer)",
        "begin_load_pass(enc);",
        "load_action->complete(valid);",
    ):
        if obsolete in source:
            raise SystemExit(f"ERROR: {path.name} retains uncommitted load-pass caller {obsolete}")
PY
"$PYBIN" - "$WEBGPU_SOURCE/wgpu_texture.cc" <<'PY'
from pathlib import Path
import re
import sys


source = Path(sys.argv[1]).read_text(encoding="utf-8")


def method_body(marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated method: {marker}")


def braced_block(body: str, marker: str) -> str:
    start = body.index(marker)
    opening = body.index("{", start)
    depth = 0
    for offset in range(opening, len(body)):
        if body[offset] == "{":
            depth += 1
        elif body[offset] == "}":
            depth -= 1
            if depth == 0:
                return body[start : offset + 1]
    raise ValueError(f"unterminated block: {marker}")


clear_body = method_body("void WGPUTexture::clear(const double4 data)")
branches = (
    braced_block(clear_body, "if (format_flag_ & GPU_FORMAT_DEPTH)"),
    braced_block(clear_body, "if (can_render_clear)"),
)
helper = "webgpu::command_encode_submit_scoped("
for label, branch in zip(("depth", "color"), branches, strict=True):
    if branch.count(helper) != 1:
        raise SystemExit(f"ERROR: texture {label} clear lacks one checked command transaction")
    required = (
        "wgpu::TextureView view =",
        "wgpu::RenderPassEncoder pass = encoder.BeginRenderPass(&rp);",
        "pass.End();",
        "return true;",
    )
    positions = [branch.find(needle) for needle in required]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise SystemExit(f"ERROR: texture {label} clear transaction is missing or reordered")
    for handle in ("view", "pass"):
        guard = rf"if \({handle} == nullptr\) \{{\s+return false;\s+\}}"
        if len(re.findall(guard, branch)) != 1:
            raise SystemExit(f"ERROR: texture {label} clear lacks one {handle} failure guard")
    forbidden = (
        "device.CreateCommandEncoder()",
        ".Finish()",
        ".Submit(1,",
        "if (view == nullptr) {\n          continue;\n        }",
    )
    if any(needle in branch for needle in forbidden):
        raise SystemExit(f"ERROR: texture {label} clear retains a partial command path")

read_body = method_body("void WGPUTexture::read_sub(")
helper = "webgpu::command_encode_submit_scoped("
copy = "encoder.CopyTextureToBuffer(&src, &dst, &copy_size);"
mapping = "wgpu::Future f = staging.MapAsync("
if read_body.count(helper) != 1 or read_body.count(copy) != 1:
    raise SystemExit("ERROR: native texture readback lacks one checked copy transaction")
positions = [read_body.find(needle) for needle in (helper, copy, mapping)]
if any(position < 0 for position in positions) or positions != sorted(positions):
    raise SystemExit("ERROR: native texture readback command transaction is missing or reordered")
forbidden = (
    "wgpu::CommandEncoder enc = device.CreateCommandEncoder();",
    "enc.CopyTextureToBuffer(",
    "wgpu::CommandBuffer cb = enc.Finish();",
    "ctx->queue_get().Submit(1, &cb);",
)
if any(needle in read_body for needle in forbidden):
    raise SystemExit("ERROR: native texture readback retains an unchecked command operation")

copy_body = method_body("void WGPUTexture::copy_to(")
helper = "webgpu::command_encode_submit_scoped("
mip_loop = "for (const int64_t mip : mip_levels) {"
compatibility = (
    "!resolve_subresource(int(mip), -1, src_region)",
    "!dst->resolve_subresource(int(mip), -1, dst_region)",
    "src_region.width != dst_region.width",
    "src_region.height != dst_region.height",
    "src_region.depth != dst_region.depth",
)
skip = "continue;"
copy = "encoder.CopyTextureToTexture(&s, &d, &size);"
if (
    copy_body.count(helper) != 1
    or copy_body.count(mip_loop) != 1
    or copy_body.count(copy) != 1
):
    raise SystemExit("ERROR: texture copy lacks one checked multi-mip command transaction")
positions = [
    copy_body.find(needle)
    for needle in (helper, mip_loop, *compatibility, skip, copy)
]
if any(position < 0 for position in positions) or positions != sorted(positions):
    raise SystemExit("ERROR: texture copy command transaction changed per-mip skip ordering")
forbidden = (
    "wgpu::CommandEncoder enc = device.CreateCommandEncoder();",
    "enc.CopyTextureToTexture(",
    "wgpu::CommandBuffer cb = enc.Finish();",
    "ctx->queue_get().Submit(1, &cb);",
)
if any(needle in copy_body for needle in forbidden):
    raise SystemExit("ERROR: texture copy retains an unchecked command operation")
PY
require_fixed_count 2 \
  'command_encode_submit_scoped(' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 0 \
  'wgpu::CommandEncoder enc = device.CreateCommandEncoder();' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
"$PYBIN" - "$WEBGPU_SOURCE/wgpu_buffer.cc" <<'PY'
from pathlib import Path
import sys


source = Path(sys.argv[1]).read_text(encoding="utf-8")


def method_body(marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated method: {marker}")


blocks = (
    (
        "bool Buffer::update_allocation(",
        "encoder.CopyBufferToBuffer(",
    ),
    (
        "std::vector<uint8_t> Buffer::read(",
        "encoder.CopyBufferToBuffer(",
    ),
)

for marker, copy in blocks:
    body = method_body(marker)
    helper = "command_encode_submit_scoped("
    if body.count(helper) != 1 or body.count(copy) != 1:
        raise SystemExit(f"ERROR: {marker} does not contain one scoped command transaction")
    if body.index(helper) >= body.index(copy):
        raise SystemExit(f"ERROR: {marker} copy escaped its scoped command transaction")
    if marker.startswith("std::vector") and body.index(copy) >= body.index("staging.MapAsync("):
        raise SystemExit("ERROR: buffer read maps before its scoped copy completes")
PY
require_fixed_count 1 \
  'webgpu::command_encode_submit_scoped(' \
  "$WEBGPU_SOURCE/wgpu_storage_buffer.cc"
require_fixed_count 0 \
  'wgpu::CommandEncoder enc = device.CreateCommandEncoder();' \
  "$WEBGPU_SOURCE/wgpu_storage_buffer.cc"
require_fixed_count 0 \
  'ctx->queue_get().Submit(1, &cb);' \
  "$WEBGPU_SOURCE/wgpu_storage_buffer.cc"
"$PYBIN" - "$WEBGPU_SOURCE/wgpu_storage_buffer.cc" <<'PY'
from pathlib import Path
import sys


source = Path(sys.argv[1]).read_text(encoding="utf-8")
marker = "void WGPUStorageBuffer::copy_sub("
start = source.index(marker)
opening = source.index("{", start)
depth = 0
for offset in range(opening, len(source)):
    if source[offset] == "{":
        depth += 1
    elif source[offset] == "}":
        depth -= 1
        if depth == 0:
            body = source[start : offset + 1]
            break
else:
    raise SystemExit("ERROR: unterminated WGPUStorageBuffer::copy_sub method")

helper = "webgpu::command_encode_submit_scoped("
copy = "encoder.CopyBufferToBuffer("
if body.count(helper) != 1 or body.count(copy) != 1:
    raise SystemExit(
        "ERROR: WGPUStorageBuffer::copy_sub does not contain one scoped command transaction"
    )
range_guard = "if (!webgpu::buffer_copy_range_valid(src_offset,"
if body.count(range_guard) != 1 or not body.index(range_guard) < body.index(helper) < body.index(copy):
    raise SystemExit("ERROR: storage command transaction does not follow range validation")
PY
require_fixed_count 2 \
  'webgpu::command_pass_encode_submit_scoped(' \
  "$WEBGPU_SOURCE/wgpu_backend.cc"
require_fixed_count 0 \
  'wgpu::CommandEncoder enc = device.CreateCommandEncoder();' \
  "$WEBGPU_SOURCE/wgpu_backend.cc"
require_fixed_count 1 \
  'if (module == nullptr) {' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'webgpu::command_pass_encode_submit_scoped(' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 0 \
  'wgpu::CommandEncoder encoder = ctx.device_get().CreateCommandEncoder();' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 0 \
  'wgpu::ComputePassEncoder pass = encoder.BeginComputePass();' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 4 \
  'webgpu::command_encode_submit_scoped(' "$WEBGPU_SOURCE/wgpu_batch.cc"
"$PYBIN" - "$WEBGPU_SOURCE/wgpu_batch.cc" <<'PY'
from pathlib import Path
import sys


source = Path(sys.argv[1]).read_text(encoding="utf-8")


def method_body(marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated method: {marker}")


methods = (
    ("void WGPUBatch::draw(", "direct multi-viewport draw", "direct batch draw"),
    (
        "void WGPUBatch::multi_draw_indirect(",
        "indirect multi-viewport draw",
        "indirect batch draw",
    ),
)

for method_marker, multi_label, ordinary_label in methods:
    body = method_body(method_marker)
    helper = "webgpu::command_encode_submit_scoped("
    if body.count(helper) != 2:
        raise SystemExit(f"ERROR: {method_marker} lacks two scoped draw transactions")
    for label in (multi_label, ordinary_label):
        if body.count(f'"{label}"') != 1:
            raise SystemExit(f"ERROR: {method_marker} lacks scoped transaction {label}")
    if any(needle in body for needle in ("CreateCommandEncoder()", ".Finish()", ".Submit(1,")):
        raise SystemExit(f"ERROR: {method_marker} retains an unchecked command operation")
    helpers = [body.index(helper), body.index(helper, body.index(helper) + len(helper))]
    passes = [body.index("fb->begin_load_pass(", offset) for offset in helpers]
    ends = [
        body.index("mv_pass.End();", helpers[0]),
        body.index("pass.End();", helpers[1]),
    ]
    if not helpers[0] < passes[0] < ends[0] < helpers[1] < passes[1] < ends[1]:
        raise SystemExit(f"ERROR: {method_marker} draw work escaped its scoped transaction")
PY
FAN_CACHE_LINE="$(grep -nF \
  'return pipeline_cache.get_or_create(' \
  "$WEBGPU_SOURCE/wgpu_batch.cc" | cut -d: -f1)"
FAN_MODULE_CREATE_LINE="$(grep -nF \
  'wgpu::ShaderModule module = device.CreateShaderModule(&shader_descriptor);' \
  "$WEBGPU_SOURCE/wgpu_batch.cc" | cut -d: -f1)"
FAN_MODULE_GUARD_LINE="$(grep -nF \
  'if (module == nullptr) {' "$WEBGPU_SOURCE/wgpu_batch.cc" | cut -d: -f1)"
FAN_PIPELINE_CREATE_LINE="$(grep -nF \
  'return device.CreateComputePipeline(&pipeline_descriptor);' \
  "$WEBGPU_SOURCE/wgpu_batch.cc" | cut -d: -f1)"
FAN_BIND_SCOPE_LINE="$(grep -nF \
  'const wgpu::BindGroup group = webgpu::transient_resource_create_scoped(' \
  "$WEBGPU_SOURCE/wgpu_batch.cc" | cut -d: -f1)"
FAN_BIND_GUARD_LINE="$(grep -nF \
  'if (group == nullptr) {' "$WEBGPU_SOURCE/wgpu_batch.cc" | cut -d: -f1)"
FAN_COMMAND_TRANSACTION_LINE="$(grep -nF \
  'webgpu::command_pass_encode_submit_scoped(' \
  "$WEBGPU_SOURCE/wgpu_batch.cc" | cut -d: -f1)"
if [ -z "$FAN_CACHE_LINE" ] || [ -z "$FAN_MODULE_CREATE_LINE" ] ||
   [ -z "$FAN_MODULE_GUARD_LINE" ] ||
   [ -z "$FAN_PIPELINE_CREATE_LINE" ] || [ -z "$FAN_BIND_GUARD_LINE" ] ||
   [ -z "$FAN_BIND_SCOPE_LINE" ] ||
   [ -z "$FAN_COMMAND_TRANSACTION_LINE" ] ||
   [ "$FAN_CACHE_LINE" -ge "$FAN_MODULE_CREATE_LINE" ] ||
   [ "$FAN_MODULE_CREATE_LINE" -ge "$FAN_MODULE_GUARD_LINE" ] ||
   [ "$FAN_MODULE_GUARD_LINE" -ge "$FAN_PIPELINE_CREATE_LINE" ] ||
   [ "$FAN_PIPELINE_CREATE_LINE" -ge "$FAN_BIND_SCOPE_LINE" ] ||
   [ "$FAN_BIND_SCOPE_LINE" -ge "$FAN_BIND_GUARD_LINE" ] ||
   [ "$FAN_BIND_GUARD_LINE" -ge "$FAN_COMMAND_TRANSACTION_LINE" ]
then
  echo "ERROR: indexed triangle-fan resource guards do not precede dependent work" >&2
  exit 1
fi
require_fixed_count 1 \
  'webgpu::command_encode_submit_scoped(' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
"$PYBIN" - "$WEBGPU_SOURCE/wgpu_immediate.cc" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
start = source.index("void WGPUImmediate::end()")
body = source[start : source.index("\n}", start) + 2]
helper = "webgpu::command_encode_submit_scoped("
ordered = (helper, "fb->begin_load_pass(", "pass.Draw")
positions = [body.find(needle) for needle in ordered]
if any(position < 0 for position in positions) or positions != sorted(positions):
    raise SystemExit("ERROR: immediate draw work escaped its scoped transaction")
if any(needle in body for needle in ("CreateCommandEncoder()", ".Finish()", ".Submit(1,")):
    raise SystemExit("ERROR: immediate draw retains an unchecked command operation")
PY
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
  grep -nF 'webgpu::queue_write_buffer_scoped(ctx->instance_get(),' \
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
require_fixed_count 1 \
  'if (selected_module == nullptr) {' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 3 \
  'if (bind_group == nullptr) {' "$WEBGPU_SOURCE/wgpu_context.cc"
COLOR_MODULE_CACHE_LINE="$(grep -nF \
  'const wgpu::ShaderModule selected_module = blit_modules_.get_or_create(' \
  "$WEBGPU_SOURCE/wgpu_context.cc" | cut -d: -f1)"
COLOR_MODULE_CREATE_LINE="$(grep -nF \
  'return device_.CreateShaderModule(&md);' \
  "$WEBGPU_SOURCE/wgpu_context.cc" | cut -d: -f1)"
COLOR_MODULE_GUARD_LINE="$(grep -nF \
  'if (selected_module == nullptr) {' "$WEBGPU_SOURCE/wgpu_context.cc" | tail -n 1 | cut -d: -f1)"
COLOR_PIPELINE_KEY_LINE="$(grep -nF \
  'const uint32_t fmt_key = uint32_t(dst_format)' \
  "$WEBGPU_SOURCE/wgpu_context.cc" | cut -d: -f1)"
COLOR_PIPELINE_CACHE_LINE="$(grep -nF \
  'const wgpu::RenderPipeline pipeline = blit_pipelines_.get_or_create(' \
  "$WEBGPU_SOURCE/wgpu_context.cc" | cut -d: -f1)"
COLOR_PIPELINE_GUARD_LINE="$(grep -nF \
  'if (pipeline == nullptr) {' "$WEBGPU_SOURCE/wgpu_context.cc" | head -n 1 | cut -d: -f1)"
COLOR_UNIFORM_GUARD_LINE="$(grep -nF \
  'if (!webgpu::buffer_create_if_valid(device_, bd, blit_uniform)) {' \
  "$WEBGPU_SOURCE/wgpu_context.cc" | cut -d: -f1)"
COLOR_QUEUE_WRITE_LINE="$(grep -nF \
  'webgpu::queue_write_buffer_scoped(instance_,' \
  "$WEBGPU_SOURCE/wgpu_context.cc" | tail -n 1 | cut -d: -f1)"
COLOR_BIND_CREATE_LINE="$(grep -nF \
  'wgpu::BindGroup bind_group = webgpu::transient_resource_create_scoped(' \
  "$WEBGPU_SOURCE/wgpu_context.cc" | head -n 1 | cut -d: -f1)"
COLOR_BIND_GUARD_LINE="$(grep -nF \
  'if (bind_group == nullptr) {' "$WEBGPU_SOURCE/wgpu_context.cc" | head -n 1 | cut -d: -f1)"
COLOR_COMMAND_TRANSACTION_LINE="$(grep -nF \
  'webgpu::command_pass_encode_submit_scoped(' \
  "$WEBGPU_SOURCE/wgpu_context.cc" | head -n 1 | cut -d: -f1)"
if [ -z "$COLOR_MODULE_CACHE_LINE" ] || [ -z "$COLOR_MODULE_CREATE_LINE" ] ||
   [ -z "$COLOR_MODULE_GUARD_LINE" ] ||
   [ -z "$COLOR_PIPELINE_KEY_LINE" ] || [ -z "$COLOR_UNIFORM_GUARD_LINE" ] ||
   [ -z "$COLOR_PIPELINE_CACHE_LINE" ] || [ -z "$COLOR_PIPELINE_GUARD_LINE" ] ||
   [ -z "$COLOR_QUEUE_WRITE_LINE" ] || [ -z "$COLOR_BIND_CREATE_LINE" ] ||
   [ -z "$COLOR_BIND_GUARD_LINE" ] || [ -z "$COLOR_COMMAND_TRANSACTION_LINE" ] ||
   [ "$COLOR_MODULE_CACHE_LINE" -ge "$COLOR_MODULE_CREATE_LINE" ] ||
   [ "$COLOR_MODULE_CREATE_LINE" -ge "$COLOR_MODULE_GUARD_LINE" ] ||
   [ "$COLOR_MODULE_GUARD_LINE" -ge "$COLOR_PIPELINE_KEY_LINE" ] ||
   [ "$COLOR_PIPELINE_KEY_LINE" -ge "$COLOR_PIPELINE_CACHE_LINE" ] ||
   [ "$COLOR_PIPELINE_CACHE_LINE" -ge "$COLOR_PIPELINE_GUARD_LINE" ] ||
   [ "$COLOR_PIPELINE_GUARD_LINE" -ge "$COLOR_UNIFORM_GUARD_LINE" ] ||
   [ "$COLOR_UNIFORM_GUARD_LINE" -ge "$COLOR_QUEUE_WRITE_LINE" ] ||
   [ "$COLOR_BIND_CREATE_LINE" -ge "$COLOR_BIND_GUARD_LINE" ] ||
   [ "$COLOR_BIND_GUARD_LINE" -ge "$COLOR_COMMAND_TRANSACTION_LINE" ]
then
  echo "ERROR: color-blit resource guards do not precede queue and command work" >&2
  exit 1
fi
require_fixed_count 0 \
  'inline bool cache_handle_if_valid(' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 0 \
  'inline bool cache_variant_if_valid(' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 'blit_modules_.get_or_create(' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 2 'blit_pipelines_.get_or_create(' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 'depth_blit_module_.get_or_create(' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 'depth_blit_pipelines_.get_or_create(' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 'depth_upload_module_.get_or_create(' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 'depth_upload_pipelines_.get_or_create(' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 2 'scissored_clear_modules_.get_or_create(' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 1 'scissored_color_clear_pipelines_.get_or_create(' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 1 'scissored_depth_clear_pipelines_.get_or_create(' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 1 'pipeline_cache.get_or_create(' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 '"texture mipmap shader/pipeline creation"' \
  "$WEBGPU_SOURCE/wgpu_texture.cc"
require_fixed_count 0 'sampler_cache_[key] = sampler;' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 'blit_pipelines_[fmt_key] = pipeline;' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 \
  'depth_blit_pipelines_[uint32_t(dst_format)] = pipeline;' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 \
  'depth_upload_pipelines_[uint32_t(format)] = pipeline;' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 'cache_.emplace(key, pipeline);' "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 0 \
  'compute_pipelines_.push_back({key, pipeline});' "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 0 'compute_pipelines_' "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 1 'device.CreateShaderModule(&desc)' "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 1 'device.CreateComputePipeline(&desc)' "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 1 'device.CreateRenderPipeline(&desc)' "$WEBGPU_SOURCE/wgpu_pipeline.cc"
require_fixed_count 3 'device_.CreateShaderModule(' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 3 'device_.CreateRenderPipeline(' "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 2 'device.CreateShaderModule(' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 2 'device.CreateRenderPipeline(' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 1 'device.CreateShaderModule(' "$WEBGPU_SOURCE/wgpu_texture.cc"
require_fixed_count 1 'device.CreateRenderPipeline(' "$WEBGPU_SOURCE/wgpu_texture.cc"
require_fixed_count 1 'device.CreateShaderModule(' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 'device.CreateComputePipeline(' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'using WindowViewportPlan = FramebufferViewportPlan;' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline bool window_viewport_scissor_plan(' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 'struct FramebufferViewportPlan {' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline bool offscreen_viewport_scissor_plan(' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 0 'bool convert_bottom_origin' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'return webgpu::window_viewport_scissor_plan(' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 1 \
  'return webgpu::offscreen_viewport_scissor_plan(' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 3 \
  'if (!load_pass_viewport_plan(draw_viewport))' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 0 \
  'layered_load_clear_pending_mask_.fetch_or(pending_bit, std::memory_order_acq_rel);' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 2 \
  'load_action_tracker_.requires_clear(' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 0 'std::clamp(vp[' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 0 'std::clamp(sc[' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 1 \
  'pass.SetViewport(float(draw_viewport.viewport.viewport_x),' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 1 \
  'pass.SetScissorRect(draw_viewport.scissor_x,' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
mapfile -t LOAD_PASS_PLAN_LINES < <(
  grep -nF 'if (!load_pass_viewport_plan(draw_viewport))' \
    "$WEBGPU_SOURCE/wgpu_framebuffer.cc" | cut -d: -f1
)
PREPARE_LINE="$(grep -nF 'bool WGPUFrameBuffer::load_action_transaction_prepare(' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc" | cut -d: -f1)"
DEBUG_NOTE_LINE="$(grep -nF 'void WGPUFrameBuffer::debug_note_draw(' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc" | cut -d: -f1)"
BEGIN_LOAD_PASS_LINE="$(grep -nF 'wgpu::RenderPassEncoder WGPUFrameBuffer::begin_load_pass(' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc" | cut -d: -f1)"
BEGIN_PASS_LINE="$(grep -nF \
  'if (!webgpu::transient_handle_publish_if_valid(encoder.BeginRenderPass(&rp), pass))' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc" | cut -d: -f1)"
if [ "${#LOAD_PASS_PLAN_LINES[@]}" -ne 3 ] ||
   [ -z "$PREPARE_LINE" ] || [ -z "$DEBUG_NOTE_LINE" ] ||
   [ -z "$BEGIN_LOAD_PASS_LINE" ] || [ -z "$BEGIN_PASS_LINE" ] ||
   [ "$PREPARE_LINE" -ge "${LOAD_PASS_PLAN_LINES[0]}" ] ||
   [ "${LOAD_PASS_PLAN_LINES[0]}" -ge "$DEBUG_NOTE_LINE" ] ||
   [ "$DEBUG_NOTE_LINE" -ge "${LOAD_PASS_PLAN_LINES[1]}" ] ||
   [ "${LOAD_PASS_PLAN_LINES[1]}" -ge "$BEGIN_LOAD_PASS_LINE" ] ||
   [ "$BEGIN_LOAD_PASS_LINE" -ge "${LOAD_PASS_PLAN_LINES[2]}" ] ||
   [ "${LOAD_PASS_PLAN_LINES[2]}" -ge "$BEGIN_PASS_LINE" ]
then
  echo "ERROR: framebuffer viewport preflight does not guard clear reservation and pass allocation" >&2
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
require_fixed_count 1 '#include "GHOST_WGPUTransaction.hh"' "$GHOST_SOURCE"
require_fixed_count 1 '#include "GHOST_WGPUTransaction.hh"' "$GHOST_WINDOW_SOURCE"
require_fixed_count 1 '#include "GHOST_WGPUTransaction.hh"' "$GHOST_SYSTEM_SOURCE"
require_fixed_count 1 'ghost_web::drawing_context_initialize_if_valid(' "$GHOST_WINDOW_SOURCE"
require_fixed_count 1 'ghost_web::window_publish_if_valid(' "$GHOST_SYSTEM_SOURCE"
require_fixed_count 2 'ghost_web::drawing_context_status_is_ready(' "$GHOST_SOURCE"
require_fixed_count 1 'ghost_web::DrawingContextMode::PresentableWindow' "$GHOST_WINDOW_SOURCE"
require_fixed_count 1 'ghost_web::DrawingContextMode::DeviceOnly' "$GHOST_SYSTEM_SOURCE"
"$PYBIN" "$WINDOW_ACTIVATION_CONTRACT" \
  "$GHOST_WINDOW_SOURCE" "$GHOST_BASE_WINDOW_SOURCE" --selfcheck
"$PYBIN" "$FRONTBUFFER_CAPABILITY_CONTRACT" \
  "$GHOST_SYSTEM_SOURCE" \
  "$ROOT/upstream/source/blender/windowmanager/intern/wm_draw.cc" \
  "$ROOT/upstream/source/blender/editors/interface/eyedroppers/eyedropper_color.cc" \
  "$WEBGPU_SOURCE/wgpu_texture.cc" \
  --selfcheck
"$PYBIN" "$WEB_CAPABILITY_CONTRACT" \
  "$GHOST_SYSTEM_SOURCE" "$GHOST_EVENT_BRIDGE_SOURCE" "$GHOST_WINDOW_SOURCE" \
  --selfcheck
"$PYBIN" "$WINDOW_TITLE_CONTRACT" "$GHOST_WINDOW_SOURCE" --selfcheck
"$PYBIN" "$FULLSCREEN_STATE_CONTRACT" "$GHOST_WINDOW_SOURCE" --selfcheck
"$PYBIN" "$POINTER_LOCK_CONTRACT" \
  "$GHOST_WINDOW_SOURCE" "$GHOST_WINDOW_HEADER" "$GHOST_EVENT_BRIDGE_SOURCE" \
  "$GHOST_SYSTEM_SOURCE" "$DIAGNOSTICS_BOOTSTRAP_SOURCE" \
  "$ROOT/platform_web/ghost/harness/pointer_lock_test.mjs" --selfcheck
"$PYBIN" "$FOCUS_STATE_CONTRACT" "$GHOST_EVENT_BRIDGE_SOURCE" --selfcheck
"$PYBIN" "$BUTTON_CURSOR_CONTRACT" --self-check
"$PYBIN" "$INPUT_REDRAW_RECOVERY_CONTRACT" --self-check
"$PYBIN" "$AUXILIARY_CACHE_REDRAW_CONTRACT" --self-check
"$PYBIN" "$KEYBOARD_FOCUS_CONTRACT" \
  "$GHOST_SYSTEM_SOURCE" \
  "$ROOT/sandbox/m4-keyboard-focus/keyboard_focus_test.mjs" \
  "$ROOT/platform_web/ghost/harness/window_lifecycle_test.mjs" --selfcheck
"$PYBIN" "$MODIFIER_SIDE_CONTRACT" \
  "$GHOST_SYSTEM_HEADER" "$GHOST_SYSTEM_SOURCE" "$GHOST_EVENT_BRIDGE_SOURCE" \
  "$ROOT/platform_web/ghost/harness/test_ghost_web.cc" \
  "$ROOT/sandbox/m4-modifier-side-state/modifier_side_test.mjs" --selfcheck
"$PYBIN" "$MOUSE_RELEASE_OWNERSHIP_CONTRACT" \
  "$GHOST_SYSTEM_SOURCE" "$MOUSE_RELEASE_OWNERSHIP_TEST" \
  "$WINDOW_LIFECYCLE_CONTRACT" --selfcheck
"$PYBIN" "$WINDOW_LIFECYCLE_CONTRACT" \
  "$GHOST_SYSTEM_HEADER" "$GHOST_SYSTEM_SOURCE" \
  "$ROOT/platform_web/ghost/harness/test_ghost_web.cc" \
  "$ROOT/platform_web/ghost/harness/window_lifecycle_test.mjs" \
  "$HERE/integrated_pipeline_test.cc" --selfcheck
"$PYBIN" "$CALLBACK_REGISTRATION_SOAK_CONTRACT" \
  "$GHOST_SYSTEM_SOURCE" \
  "$ROOT/platform_web/ghost/harness/window_lifecycle_test.mjs" --selfcheck
"$PYBIN" "$WINDOW_HIT_TEST_CONTRACT" \
  "$ROOT/upstream/intern/ghost/GHOST_ISystem.hh" \
  "$ROOT/upstream/intern/ghost/intern/GHOST_System.cc" \
  "$GHOST_SYSTEM_SOURCE" \
  "$ROOT/platform_web/ghost/harness/test_ghost_web.cc" \
  "$ROOT/platform_web/ghost/harness/window_lifecycle_test.mjs" \
  --selfcheck
"$PYBIN" "$FIRST_PIXEL_SETTLE_CONTRACT" \
  "$GHOST_DISPLAY_HEADER" "$GHOST_SYSTEM_HEADER" "$GHOST_SYSTEM_SOURCE" \
  "$ROOT/upstream/source/blender/windowmanager/intern/wm_window.cc" \
  "$WEBGPU_SOURCE/wgpu_shader.cc" "$WEBGPU_SOURCE/wgpu_pipeline.cc" \
  "$GHOST_SOURCE" --selfcheck
"$PYBIN" "$VIEWPORT_CONTENT_LOADER_CONTRACT" --selfcheck
"$PYBIN" "$RESIZE_TRACE_CONTRACT" --selfcheck
"$PYBIN" "$BROWSER_SAME_TURN_CONTRACT" --selfcheck
"$PYBIN" "$CLIPBOARD_BRIDGE_CONTRACT" \
  "$GHOST_SYSTEM_SOURCE" "$GHOST_SYSTEM_HEADER" --selfcheck
"$PYBIN" "$IME_BRIDGE_CONTRACT" \
  "$GHOST_EVENT_BRIDGE_SOURCE" "$GHOST_IME_QUEUE_HEADER" \
  "$ROOT/platform_web/ghost/GHOST_EventBridgeWeb.hh" \
  "$GHOST_SYSTEM_SOURCE" "$GHOST_WINDOW_SOURCE" "$GHOST_WINDOW_HEADER" \
  "$ROOT/patches/blender_web.cmake" "$ROOT/upstream/CMakeLists.txt" \
  "$ROOT/patches/0280-ghost-web-input-ime-option.patch" "$ROOT/patches/series" --selfcheck
"$PYBIN" "$IME_FOCUS_OWNERSHIP_CONTRACT" \
  "$GHOST_SYSTEM_HEADER" "$GHOST_SYSTEM_SOURCE" "$IME_FOCUS_OWNERSHIP_TEST" --selfcheck
"$PYBIN" "$IME_NONCOMPOSING_KEY_CONTRACT" \
  "$GHOST_SYSTEM_SOURCE" "$IME_NONCOMPOSING_KEY_TEST" \
  "$IME_NONCOMPOSING_PRODUCT_TEST" --selfcheck
"$PYBIN" "$FOCUS_TRANSITION_ORDER_CONTRACT" \
  "$GHOST_SYSTEM_HEADER" "$GHOST_SYSTEM_SOURCE" "$FOCUS_TRANSITION_ORDER_TEST" --selfcheck
"$PYBIN" "$CURSOR_BRIDGE_CONTRACT" \
  "$GHOST_WINDOW_SOURCE" "$GHOST_WINDOW_HEADER" "$GHOST_SYSTEM_SOURCE" \
  "$DIAGNOSTICS_BOOTSTRAP_SOURCE" \
  "$GHOST_TYPES_SOURCE" --selfcheck
for status in 1 2 3 4 5; do
  require_fixed_count 1 \
    "Module[\"preinitializedWebGPUPresentationStatus\"] = ${status};" \
    "$WGPU_PREINIT_SOURCE"
done
require_fixed_count 1 'Module["preinitializedWebGPUSurface"] = surface;' "$WGPU_PREINIT_SOURCE"
require_fixed_count 1 'Module["preinitializedWebGPUBackbuffer"] = backbuffer;' "$WGPU_PREINIT_SOURCE"
require_fixed_count 1 'PThread.receiveOffscreenCanvases(d);' "$WGPU_PREINIT_SOURCE"
require_fixed_count 1 '[bw] early receiveOffscreenCanvases failed:' "$WGPU_PREINIT_SOURCE"
require_fixed_count 1 'device.queue.submit([presentationCommands]);' "$WGPU_PREINIT_SOURCE"
require_fixed_count 1 \
  'await validateScoped(device, configureAndSubmitPresentationProbe, null);' \
  "$WGPU_PREINIT_SOURCE"
require_fixed_count 1 'await device.queue.onSubmittedWorkDone();' "$WGPU_PREINIT_SOURCE"
require_fixed_count 1 'adapter.info && typeof adapter.info.isFallbackAdapter === "boolean" ?' \
  "$WGPU_PREINIT_SOURCE"
require_fixed_count 1 '"fallback-diagnostic";' "$WGPU_PREINIT_SOURCE"
require_fixed_count 0 'onPresentationError' "$WGPU_PREINIT_SOURCE"
require_fixed_count 1 \
  'Module["preinitializedWebGPUDeviceLoss"] = deviceLossSignal;' \
  "$WGPU_PREINIT_SOURCE"
require_fixed_count 1 'device.lost.then(function (info) {' "$WGPU_PREINIT_SOURCE"
require_fixed_count 1 '"--use-webgpu-adapter=swiftshader",' "$LIVE_PREINIT_SOURCE"
require_fixed_count 1 '"--use-gpu-in-tests",' "$LIVE_PREINIT_SOURCE"
require_fixed_count 1 'Number(module._bw_wm_tick_count?.()) >= 2;' "$LIVE_PREINIT_SOURCE"
require_fixed_count 1 'await page.mouse.click(x, y);' "$LIVE_PREINIT_SOURCE"
require_fixed_count 1 'document.title !== initialTitle' "$LIVE_PREINIT_SOURCE"
require_fixed_count 1 'classifyLivePreinitDiagnostic({' "$LIVE_PREINIT_SOURCE"
for contract_shader in \
  '"overlay_grid_next"' \
  '"overlay_outline_detect"' \
  '"overlay_antialiasing_pipeline"' \
  '"OCIO_Display"'
do
  require_fixed_count 1 "$contract_shader" "$LIVE_PREINIT_SOURCE"
done
require_fixed_count 1 'counters.incompleteContractBindings++;' "$LIVE_PREINIT_SOURCE"
require_fixed_count 1 'if (counters.adapterFallback !== "true") {' "$LIVE_PREINIT_CONTRACT"
require_fixed_count 1 'if (!(afterInput.presents > second.presents)) {' \
  "$LIVE_PREINIT_CONTRACT"
require_fixed_count 1 'if (counters.deviceLost !== 0)' "$LIVE_PREINIT_CONTRACT"
require_fixed_count 1 'if (counters.presentSubmissionRejected !== 0)' \
  "$LIVE_PREINIT_CONTRACT"
require_fixed_count 1 'if (counters.presentTransactionRejected !== 0)' \
  "$LIVE_PREINIT_CONTRACT"
require_fixed_count 1 \
  'std::shared_ptr<ghost_web::DeviceCallbackState> device_state_' \
  "$GHOST_HEADER"
require_fixed_count 1 \
  'std::shared_ptr<CallbackLifetime> callback_lifetime_;' \
  "$GHOST_HEADER"
require_fixed_count 2 \
  'inline bool device_state_allows_callback_work(' \
  "$GHOST_TRANSACTION_HEADER"
require_fixed_count 1 \
  'callback_lifetime_(std::make_shared<CallbackLifetime>(*this))' \
  "$GHOST_SOURCE"
require_fixed_count 2 \
  'const std::shared_ptr<CallbackLifetime> callback_lifetime =' \
  "$GHOST_SOURCE"
require_fixed_count 1 \
  'std::make_shared<ghost_web::DeviceCallbackState>(' \
  "$GHOST_SOURCE"
require_fixed_count 1 \
  'ghost_web_preinit_device_loss_generation(), imported_device_loss_observation' \
  "$GHOST_SOURCE"
require_fixed_count 1 'desc.SetDeviceLostCallback(' "$GHOST_SOURCE"
require_fixed_count 2 'device_state_after_loss_signal(' "$GHOST_TRANSACTION_HEADER"
require_fixed_count 1 'ghost_web::device_state_mark_lost(' "$GHOST_SOURCE"
require_fixed_count 1 'ghost_web::fallback_device_loss_notify(' "$GHOST_SOURCE"
require_fixed_count 5 \
  'ghost_web::device_state_allows_callback_work(device_state)' \
  "$GHOST_SOURCE"
require_fixed_count 7 'lifetime->deliver' "$GHOST_SOURCE"
require_fixed_count 9 'auto owner_execution = lifetime->enter();' "$GHOST_SOURCE"
require_fixed_count 8 'auto owner_execution = lifetime->enter();' "$GHOST_HEADER"
require_fixed_count 1 'ghost_web::scoped_handle_create(' "$GHOST_SOURCE"
require_fixed_count 1 'ghost_web::present_pipeline_create_scoped(' "$GHOST_SOURCE"
require_fixed_count 1 'ghost_web::present_frame_encode_submit_scoped(' "$GHOST_SOURCE"
require_fixed_count 0 'ghost_web::texture_replace_if_valid(' "$GHOST_SOURCE"
require_fixed_count 0 'ghost_web::present_pipeline_create_if_valid(' "$GHOST_SOURCE"
require_fixed_count 0 'ghost_web::present_frame_encode_submit_if_valid(' "$GHOST_SOURCE"
require_fixed_count 3 'device.PushErrorScope(' "$GHOST_SOURCE"
require_fixed_count 3 'device.PopErrorScope(' "$GHOST_SOURCE"
require_fixed_count 1 'bool backbuffer_pending_ = false;' "$GHOST_HEADER"
require_fixed_count 1 'uint32_t requested_width_ = 0;' "$GHOST_HEADER"
require_fixed_count 1 'uint32_t requested_height_ = 0;' "$GHOST_HEADER"
require_fixed_count 1 'bool present_pipeline_pending_ = false;' "$GHOST_HEADER"
require_fixed_count 1 'bool present_pending_ = false;' "$GHOST_HEADER"
require_fixed_count 0 'PresentQueueEnqueue' "$GHOST_HEADER"
require_fixed_count 0 'PresentCompletion' "$GHOST_HEADER"
"$PYBIN" - "$GHOST_SOURCE" "$GHOST_HEADER" "$GHOST_TRANSACTION_HEADER" <<'PY'
from pathlib import Path
import sys


source = Path(sys.argv[1]).read_text(encoding="utf-8")
header = Path(sys.argv[2]).read_text(encoding="utf-8")
transaction = Path(sys.argv[3]).read_text(encoding="utf-8")


def method(marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise SystemExit(f"ERROR: unterminated GHOST method: {marker}")


def method_from(text: str, marker: str) -> str:
    start = text.index(marker)
    opening = text.index("{", start)
    depth = 0
    for offset in range(opening, len(text)):
        if text[offset] == "{":
            depth += 1
        elif text[offset] == "}":
            depth -= 1
            if depth == 0:
                return text[start : offset + 1]
    raise SystemExit(f"ERROR: unterminated method: {marker}")


configure = method("void GHOST_ContextWGPUWeb::configureSurface(uint32_t width, uint32_t height)")
destructor = method("GHOST_ContextWGPUWeb::~GHOST_ContextWGPUWeb()")
initialize = method("GHOST_TSuccess GHOST_ContextWGPUWeb::initializeDrawingContext()")
release_native = method("GHOST_TSuccess GHOST_ContextWGPUWeb::releaseNativeHandles()")
request_adapter = method("void GHOST_ContextWGPUWeb::requestAdapter()")
request_device = method("void GHOST_ContextWGPUWeb::requestDevice()")
finish = method("void GHOST_ContextWGPUWeb::finishSetup()")
backbuffer = method("void GHOST_ContextWGPUWeb::ensureBackbuffer()")
pipeline = method("void GHOST_ContextWGPUWeb::ensurePresentPipeline()")
swap_release = method("GHOST_TSuccess GHOST_ContextWGPUWeb::swapBufferRelease()")
swap_acquire = method("GHOST_TSuccess GHOST_ContextWGPUWeb::swapBufferAcquire()")
activate = method("GHOST_TSuccess GHOST_ContextWGPUWeb::activateDrawingContext()")
release_drawing = method("GHOST_TSuccess GHOST_ContextWGPUWeb::releaseDrawingContext()")
init_async = method("void GHOST_ContextWGPUWeb::initAsync(")
device_usable = method("bool GHOST_ContextWGPUWeb::deviceIsUsable()")
propagate_loss = method("void GHOST_ContextWGPUWeb::propagateDeviceLoss()")
present = method("bool GHOST_ContextWGPUWeb::presentBackbuffer()")
fallback_loss_notify = method_from(transaction, "bool fallback_device_loss_notify(")
present_transaction = method_from(transaction, "void present_frame_encode_submit_scoped(")

destructor_cancel = destructor.index("callback_lifetime_->cancel();")
destructor_invalidate = destructor.index("callback_lifetime_->invalidate();")
if destructor_cancel >= destructor_invalidate:
    raise SystemExit("ERROR: context destruction does not synchronize callback invalidation")

owner_boundary = "auto owner_execution = lifetime->enter();"
for label, body in (
    ("initialize", initialize),
    ("release-native", release_native),
    ("swap-acquire", swap_acquire),
    ("swap-release", swap_release),
    ("activate", activate),
    ("release-drawing", release_drawing),
    ("init-async", init_async),
    ("configure", configure),
    ("device-loss-cleanup", propagate_loss),
):
    if body.count(owner_boundary) != 1:
        raise SystemExit(f"ERROR: {label} lacks one shared owner-execution boundary")

for label, marker in (
    ("ready", "bool isReady() const"),
    ("instance", "wgpu::Instance getInstance() const"),
    ("adapter", "wgpu::Adapter getAdapter() const"),
    ("device", "wgpu::Device getDevice() const"),
    ("queue", "wgpu::Queue getQueue() const"),
    ("surface", "wgpu::Surface getSurface() const"),
    ("surface-format", "wgpu::TextureFormat getSurfaceFormat() const"),
    ("backbuffer-frame", "BackbufferFrameSnapshot getBackbufferFrameSnapshot() const"),
):
    body = method_from(header, marker)
    if body.count(owner_boundary) != 1:
        raise SystemExit(f"ERROR: {label} accessor lacks one shared owner-execution boundary")

invalidate_gate = method_from(transaction, "void invalidate()")
if invalidate_gate.index("cancel();") >= invalidate_gate.index("delivery_mutex_"):
    raise SystemExit("ERROR: callback admission does not close before invalidation waits")
enter_gate = method_from(transaction, "OwnerExecution enter() const")
if not (
    enter_gate.index("delivery_mutex_")
    < enter_gate.index("state_mutex_")
    < enter_gate.index("!accepting_")
):
    raise SystemExit("ERROR: owner execution does not serialize admission and owner access")

if fallback_loss_notify.index("device_state_mark_lost(*device_state);") >= \
        fallback_loss_notify.index("callback_lifetime->deliver("):
    raise SystemExit("ERROR: fallback loss is not published before owner delivery")

lost_callback = request_device[
    request_device.index("desc.SetDeviceLostCallback(") :
    request_device.index("desc.SetUncapturedErrorCallback(")
]
for needle in (
    "[device_state, device_loss_lifetime]",
    "ghost_web::fallback_device_loss_notify(",
    "owner.propagateDeviceLoss();",
):
    if lost_callback.count(needle) != 1:
        raise SystemExit(f"ERROR: fallback device-loss callback lacks one owner-safe boundary: {needle}")
if "this" in lost_callback:
    raise SystemExit("ERROR: fallback device-loss callback retains the raw GHOST owner")

for pending in (
    "backbuffer_pending_ = false;",
    "present_pipeline_pending_ = false;",
    "present_pending_ = false;",
):
    if propagate_loss.count(pending) != 1:
        raise SystemExit(f"ERROR: terminal device loss does not clear pending state: {pending}")
if propagate_loss.count("completeInitialization(false);") != 1 or \
        propagate_loss.index("completeInitialization(false);") < \
        propagate_loss.index("device_ = nullptr;"):
    raise SystemExit("ERROR: terminal device loss does not finally settle initialization failure")

for label, body, call, follow_on in (
    ("adapter", request_adapter, "instance_.RequestAdapter(", "owner.requestDevice();"),
    ("device", request_device, "adapter_.RequestDevice(", "owner.completeInitialization("),
):
    completion = body[body.index(call) :]
    if completion.count("[callback_lifetime]") != 1 or completion.count(
        "callback_lifetime->deliver("
    ) != 1:
        raise SystemExit(f"ERROR: fallback {label} completion lacks one shared lifetime gate")
    if "[this]" in completion or "this->" in completion:
        raise SystemExit(f"ERROR: fallback {label} completion captures the raw GHOST owner")
    if follow_on not in completion:
        raise SystemExit(f"ERROR: fallback {label} completion is not routed through its live owner")

for needle in ("requested_width_ = w;", "requested_height_ = h;", "ensureBackbuffer();"):
    if configure.count(needle) != 1:
        raise SystemExit(f"ERROR: resize request lacks one exact pending-state boundary: {needle}")
if "surface_.Configure(&config);" in configure:
    raise SystemExit("ERROR: resize configures the surface before candidate validation")

for needle in (
    "ghost_web_preinit_presentation_status()",
    "ghost_web_take_preinit_surface()",
    "ghost_web_take_preinit_backbuffer(device_.Get())",
    "ghost_web::drawing_context_status_is_ready(",
):
    if needle not in initialize:
        raise SystemExit(f"ERROR: synchronous context setup lacks pre-main presentation binding: {needle}")
if "surface deferred" in initialize or "finishSetup();" in initialize:
    raise SystemExit("ERROR: synchronous window setup still publishes a deferred surface")
if finish.count("ghost_web_canvas_resolvable(canvas_selector_.c_str())") != 1:
    raise SystemExit("ERROR: asynchronous surface setup does not reject an unresolved canvas")

for label, body, helper, scope_label, pending in (
    ("backbuffer", backbuffer, "ghost_web::scoped_handle_create(",
     'popErrorScopes(device, "backbuffer creation"', "backbuffer_pending_"),
    ("pipeline", pipeline, "ghost_web::present_pipeline_create_scoped(",
     'popErrorScopes(device, "present pipeline creation"', "present_pipeline_pending_"),
):
    if body.count(helper) != 1 or body.count(scope_label) != 1 or body.count(pending) < 2:
        raise SystemExit(f"ERROR: {label} is not bound to one completed error-scope publication")

for label, body, deliveries in (
    ("backbuffer", backbuffer, 2),
    ("pipeline", pipeline, 1),
    ("present", present, 2),
):
    if body.count("lifetime->deliver") != deliveries:
        raise SystemExit(f"ERROR: {label} callbacks do not all retain the synchronized owner gate")
if "[this" in source or "[&this" in source:
    raise SystemExit("ERROR: asynchronous GHOST source retains a raw owner capture")

terminal_guard = "ghost_web::device_state_allows_callback_work(device_state)"
if backbuffer.count(terminal_guard) != 2:
    raise SystemExit("ERROR: resize callbacks do not both consult terminal device state")
backbuffer_guards = [
    backbuffer.index(terminal_guard),
    backbuffer.index(terminal_guard, backbuffer.index(terminal_guard) + 1),
]
if not (
    backbuffer_guards[0] < backbuffer.index("surface_.Configure(&config);")
    < backbuffer_guards[1] < backbuffer.index("ghost_web::surface_resize_commit_if_current(")
):
    raise SystemExit("ERROR: terminal resize guards do not precede Configure and publication")
if pipeline.count(terminal_guard) != 1 or pipeline.index(terminal_guard) > pipeline.index(
    "present_bgl_ = std::move(bind_group_layout);"
):
    raise SystemExit("ERROR: terminal pipeline guard does not precede handle publication")
if present.count(terminal_guard) != 2:
    raise SystemExit("ERROR: present submission and completion do not both consult terminal state")
present_guards = [
    present.index(terminal_guard),
    present.index(terminal_guard, present.index(terminal_guard) + 1),
]
if not (
    present_guards[0] < present.index("queue.Submit(1, &command_buffer);")
    < present_guards[1] < present.index("ghost_web::note_present();")
):
    raise SystemExit("ERROR: terminal present guards do not precede Submit and present commit")

for needle in (
    "const uint32_t candidate_width = requested_width_;",
    "const uint32_t candidate_height = requested_height_;",
    "ghost_web::surface_resize_commit_if_current(",
    "surface_.Configure(&config);",
    "if (result == ghost_web::SurfaceResizeResult::Superseded) {",
):
    if backbuffer.count(needle) != 1:
        raise SystemExit(f"ERROR: backbuffer resize lacks one exact coherence boundary: {needle}")
configuration_positions = [
    backbuffer.index("pushErrorScopes(device);"),
    backbuffer.index("surface_.Configure(&config);"),
    backbuffer.index('"surface configuration"'),
    backbuffer.index("ghost_web::surface_resize_commit_if_current("),
]
if configuration_positions != sorted(configuration_positions):
    raise SystemExit("ERROR: surface configuration is not validated before resize publication")

for needle in (
    "ghost_web::present_frame_encode_submit_scoped(",
    'popErrorScopes(device, "present command encoding"',
    'popErrorScopes(device, "present queue submission"',
    "queue.Submit(1, &command_buffer);",
    "if (!valid) {",
    "ghost_web::note_present();",
):
    if present.count(needle) != 1:
        raise SystemExit(f"ERROR: present transaction lacks one exact boundary: {needle}")

source_positions = [
    present.index("queue.Submit(1, &command_buffer);"),
    present.index("if (!valid) {"),
    present.index("ghost_web::note_present();"),
]
if source_positions != sorted(source_positions):
    raise SystemExit("ERROR: present submission/commit boundaries are reordered")

for needle, expected in (
    ("if (!handles_valid) {", 1),
    ("std::forward<BeginSubmitScopeFn>(begin_submit_scope)();", 1),
    ("std::forward<SubmitFn>(submit)(command_buffer);", 1),
    ("std::forward<EndSubmitScopeFn>(end_submit_scope)(", 1),
    ("std::forward<EndEncodeScopeFn>(end_encode_scope)(", 2),
    ("std::atomic<int> pending{2};", 1),
    ("std::atomic<bool> valid{true};", 1),
):
    if present_transaction.count(needle) != expected:
        raise SystemExit(
            f"ERROR: present helper lacks exact same-tick dual-scope boundary: {needle}"
        )
transaction_positions = [
    present_transaction.index("if (!handles_valid) {"),
    present_transaction.index("std::forward<BeginSubmitScopeFn>(begin_submit_scope)();"),
    present_transaction.index("std::forward<SubmitFn>(submit)(command_buffer);"),
    present_transaction.rindex("std::forward<EndSubmitScopeFn>(end_submit_scope)("),
    present_transaction.rindex("std::forward<EndEncodeScopeFn>(end_encode_scope)("),
]
if transaction_positions != sorted(transaction_positions):
    raise SystemExit(
        "ERROR: surface submission can yield before queue submit or violates scope-pop order"
    )

for needle in (
    "ensureBackbuffer();",
    "backbuffer_pending_",
    "ghost_web::surface_resize_present_coherent(",
    "configureSurface(surface_width, surface_height);",
):
    if present.count(needle) != 1:
        raise SystemExit(f"ERROR: present resize coherence lacks one exact boundary: {needle}")
for needle in (
    "ghost_web::surface_acquire_action(",
    "st.status",
    "st.texture != nullptr",
    "ghost_web::SurfaceAcquireAction::Reconfigure",
    "ghost_web::SurfaceAcquireAction::Recreate",
):
    if present.count(needle) < 1:
        raise SystemExit(f"ERROR: surface acquisition failure lacks one exact propagation boundary: {needle}")
if swap_release.count("return presentBackbuffer() ? GHOST_kSuccess : GHOST_kFailure;") != 1:
    raise SystemExit("ERROR: GHOST swap status does not propagate the immediate present result")
for needle in (
    "present_queue_enqueue_",
    "PresentCompletion",
    "setPresentQueueEnqueue",
):
    if needle in swap_release or needle in present or needle in header:
        raise SystemExit(f"ERROR: deferred present seam remains reachable: {needle}")
if swap_acquire.count("deviceIsUsable()") != 1 or swap_release.count("deviceIsUsable()") != 1:
    raise SystemExit("ERROR: GHOST swap boundaries do not propagate terminal device state")
for needle in (
    "ghost_web::device_state_allows_callback_work(device_state_)",
    "propagateDeviceLoss();",
):
    if device_usable.count(needle) != 1:
        raise SystemExit(f"ERROR: imported device loss lacks one exact owned-state boundary: {needle}")
for needle in (
    "ghost_web_preinit_device_loss_generation()",
    "imported_device_loss_observation",
    "std::make_shared<ghost_web::DeviceCallbackState>(",
):
    if initialize.count(needle) != 1:
        raise SystemExit(f"ERROR: imported device state lacks one callback-time observer: {needle}")
loss_callback = request_device[
    request_device.index("desc.SetDeviceLostCallback("):
    request_device.index("desc.SetUncapturedErrorCallback(")
]
if "[device_state, device_loss_lifetime]" not in loss_callback or "this" in loss_callback:
    raise SystemExit("ERROR: fallback device-loss callback retains the GHOST context")
for needle in (
    "callback_lifetime_->cancel();",
    "ready_ = false;",
    "device_ = nullptr;",
):
    if propagate_loss.count(needle) != 1:
        raise SystemExit(f"ERROR: terminal device-loss propagation lacks one exact boundary: {needle}")
resize_positions = [
    present.index("deviceIsUsable()"),
    present.index("ensureBackbuffer();"),
    present.index("surface_.GetCurrentTexture(&st);"),
    present.index("ghost_web::surface_resize_present_coherent("),
    present.index("ensurePresentPipeline();"),
]
if resize_positions != sorted(resize_positions):
    raise SystemExit("ERROR: present acquires or encodes before resize coherence is established")
PY
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
SOURCE_PROOF="$("$PYBIN" "$SOURCE_REPLAY_DRIVER" --canonical-only)"
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
"$NODE" "$WGPU_PREINIT_TEST" "$WGPU_PREINIT_SOURCE" --selfcheck >"$OUT/preinit-worker.txt"
if ! grep -qx \
  'CONTRACT ghost_preinit_worker PASS cases=20 statuses=0,1,2,3,4,5 partial=unpublished device_only=preserved loss=pending,unknown,destroyed stale=ignored preentry=unpublished entry=once canvas_registration=early,idempotent,error-diagnosed presentation=scoped-work-done fallback=diagnostic telemetry=sync,delayed,omitted adapter=current,legacy,precedence,unknown' \
  "$OUT/preinit-worker.txt"
then
  echo "ERROR: worker preinit transaction evidence differs" >&2
  exit 1
fi
if ! grep -qx \
  'SELFCHECK ghost_preinit_source PASS positive=1 negative=4 adapter=3 registration=1' \
  "$OUT/preinit-worker.txt"
then
  echo "ERROR: worker adapter-info mutation evidence differs" >&2
  exit 1
fi
"$NODE" "$CURSOR_BRIDGE_TEST" "$DIAGNOSTICS_BOOTSTRAP_SOURCE" >"$OUT/cursor-bridge.txt"
if ! grep -qx \
  'CURSOR_BRIDGE_CONTRACT PASS standard=46 custom=rgba,xbm invalid=closed visibility=hidden,visible recovery=module,canvas,error' \
  "$OUT/cursor-bridge.txt"
then
  echo "ERROR: main-thread cursor bridge evidence differs" >&2
  exit 1
fi
"$NODE" "$LIVE_PREINIT_CONTRACT_TEST" >"$OUT/live-preinit-classifier.txt"
if ! grep -qx \
  'CONTRACT ghost_preinit_live_classifier PASS positive=1 negative=26' \
  "$OUT/live-preinit-classifier.txt"
then
  echo "ERROR: live preinit classifier evidence differs" >&2
  exit 1
fi

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
  -DBW_GHOST_PRESENT_TRANSACTION_HEADER="$GHOST_TRANSACTION_HEADER" \
  -DBW_GHOST_DISPLAY_STATE_HEADER="$GHOST_DISPLAY_HEADER" \
  -DBW_NATIVE_FMT_INCLUDE_DIR="$NATIVE_FMT_INCLUDE" \
  -DPython3_EXECUTABLE="$PYBIN"
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" \
  wgpu_pipeline_integrated_test ghost_acquisition_lifetime_asan ghost_first_pixel_settle_test

echo "== [2/3] canonical Wasm render-pipeline mappings =="
"$EMSDK/upstream/emscripten/emcmake" "$HOST_CMAKE" -G Ninja \
  -S "$ROOT/sandbox/wgpu-pipeline-wasm-smoke" -B "$WASM_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CCACHE_ARGS[@]}" \
  -DBW_UPSTREAM_DIR="$ROOT/upstream" \
  -DBW_INTEGRATED_PIPELINE_SOURCE_DIR="$WEBGPU_SOURCE" \
  -DBW_GHOST_PRESENT_TRANSACTION_HEADER="$GHOST_TRANSACTION_HEADER" \
  -DBW_GHOST_DISPLAY_STATE_HEADER="$GHOST_DISPLAY_HEADER" \
  -DBW_WASM_INCLUDE_DIR="$WASM_INCLUDE"
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" \
  wgpu_pipeline_integrated_smoke ghost_acquisition_lifetime_wasm ghost_first_pixel_settle_wasm

echo "== [3/3] exact native/Wasm parity =="
NATIVE_STDOUT="$OUT/native.stdout"
NATIVE_STDERR="$OUT/native.stderr"
WASM_STDOUT="$OUT/wasm.stdout"
WASM_STDERR="$OUT/wasm.stderr"
"$NATIVE_BUILD/wgpu_pipeline_integrated_test" >"$NATIVE_STDOUT" 2>"$NATIVE_STDERR"
"$NODE" "$WASM_BUILD/integrated_pipeline.js" >"$WASM_STDOUT" 2>"$WASM_STDERR"

FIRST_PIXEL_NATIVE_STDOUT="$OUT/first-pixel-native.stdout"
FIRST_PIXEL_NATIVE_STDERR="$OUT/first-pixel-native.stderr"
FIRST_PIXEL_WASM_STDOUT="$OUT/first-pixel-wasm.stdout"
FIRST_PIXEL_WASM_STDERR="$OUT/first-pixel-wasm.stderr"
"$NATIVE_BUILD/ghost_first_pixel_settle_test" \
  >"$FIRST_PIXEL_NATIVE_STDOUT" 2>"$FIRST_PIXEL_NATIVE_STDERR"
"$NODE" "$WASM_BUILD/ghost_first_pixel_settle.js" \
  >"$FIRST_PIXEL_WASM_STDOUT" 2>"$FIRST_PIXEL_WASM_STDERR"
FIRST_PIXEL_VERDICT='CONTRACT ghost_redraw_recovery PASS cases=68 periodic=15 late=immediate drops=bounded readiness=rearmed input=coalesced-full-tail resize_commit=fresh present_barrier=ordered-sync-commit-superseded trace=bounded-exact viewport_ready=grid-validated-one-shot wrap=rearmed'
for first_pixel_stdout in "$FIRST_PIXEL_NATIVE_STDOUT" "$FIRST_PIXEL_WASM_STDOUT"; do
  if ! grep -qx "$FIRST_PIXEL_VERDICT" "$first_pixel_stdout"; then
    echo "ERROR: first-pixel settle evidence differs: $first_pixel_stdout" >&2
    exit 1
  fi
done
if ! cmp -s "$FIRST_PIXEL_NATIVE_STDOUT" "$FIRST_PIXEL_WASM_STDOUT"; then
  echo "ERROR: native and Wasm first-pixel settle evidence differs" >&2
  exit 1
fi

ACQUISITION_NATIVE_STDOUT="$OUT/acquisition-native.stdout"
ACQUISITION_NATIVE_STDERR="$OUT/acquisition-native.stderr"
ACQUISITION_WASM_STDOUT="$OUT/acquisition-wasm.stdout"
ACQUISITION_WASM_STDERR="$OUT/acquisition-wasm.stderr"
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
  "$NATIVE_BUILD/ghost_acquisition_lifetime_asan" \
  >"$ACQUISITION_NATIVE_STDOUT" 2>"$ACQUISITION_NATIVE_STDERR"
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
  "$NODE" "$WASM_BUILD/ghost_acquisition_lifetime.js" \
  >"$ACQUISITION_WASM_STDOUT" 2>"$ACQUISITION_WASM_STDERR"
ACQUISITION_VERDICT='CONTRACT ghost_acquisition_lifetime PASS cases=4 delayed=2 live=2 owner_access_after_invalidate=0 completion_after_invalidate=0 follow_on_after_invalidate=0'
for acquisition_stdout in "$ACQUISITION_NATIVE_STDOUT" "$ACQUISITION_WASM_STDOUT"; do
  if ! grep -qx "$ACQUISITION_VERDICT" "$acquisition_stdout"; then
    echo "ERROR: GHOST acquisition lifetime evidence differs: $acquisition_stdout" >&2
    exit 1
  fi
done
if ! cmp -s "$ACQUISITION_NATIVE_STDOUT" "$ACQUISITION_WASM_STDOUT"; then
  echo "ERROR: native and Wasm GHOST acquisition lifetime evidence differs" >&2
  exit 1
fi
ASAN_UNSAFE_STDOUT="$OUT/acquisition-unsafe.stdout"
ASAN_UNSAFE_STDERR="$OUT/acquisition-unsafe.stderr"
if ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
     "$NATIVE_BUILD/ghost_acquisition_lifetime_asan" --unsafe-control \
     >"$ASAN_UNSAFE_STDOUT" 2>"$ASAN_UNSAFE_STDERR"
then
  echo "ERROR: unsafe raw-owner acquisition control escaped AddressSanitizer" >&2
  exit 1
fi
if ! grep -q 'AddressSanitizer: heap-use-after-free' "$ASAN_UNSAFE_STDERR"; then
  echo "ERROR: unsafe acquisition control did not produce the expected ASan diagnosis" >&2
  exit 1
fi

for stdout_file in "$NATIVE_STDOUT" "$WASM_STDOUT"; do
  if [ "$(wc -l <"$stdout_file" | tr -d ' ')" -ne 45 ] ||
     ! grep -qx 'CONTRACT primitive_topology PASS cases=11' "$stdout_file" ||
     ! grep -qx 'CONTRACT strip_index_format PASS cases=33 selected=6' "$stdout_file" ||
     ! grep -qx \
       'CONTRACT multiview_uniform_allocation PASS cases=2 creates=2 failure=atomic bytes=16' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT dummy_vertex_buffer_creation PASS cases=3 create_fail=closed map_fail=closed values=0,0,0,1' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT transient_handle_publication PASS attempts=2 failure=atomic success=published' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT bind_group_completeness PASS cases=13 complete=4 pending=2 incomplete=7 internal=2 unique=deduplicated' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT framebuffer_load_action_commit PASS cases=2 failure=pending retry=committed' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT framebuffer_load_action_transaction PASS cases=6 attachments=3 late_view=pending late_bind=pending same_epoch=load retry=committed generation=isolated' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT framebuffer_layered_clear_order PASS cases=4 clears=4 draws=3 canceled=1 loads=4 committed=1 rollback=2 generation=isolated' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT vertex_buffer_handle_resolution PASS cases=3 resolved=5 failure=atomic order=stable' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT shader_module_set_cache PASS cases=4 creates=2 error_object=rejected retry=atomic stable=preserved' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT scoped_handle_cache PASS cases=5 creates=2 pending=deduplicated error_object=rejected retry=published' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT auxiliary_cache_redraw_publication PASS cases=7 creates=4 accepted_edges=2 rejection=none hit=no-rearm' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT ordered_scoped_handle_cache PASS cases=5 creates=2 same_epoch=provisional later_epoch=gated rejection=canceled retry=published' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT context_owned_pipeline_cache PASS cases=8 caches=3 shared_reuse=stale context_reuse=isolated creates=6' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT context_backend_handle_registry PASS cases=7 owners=2 tuples=3 publication=atomic restoration=previous cleanup=idempotent' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT ordered_queue_scheduler_failure_drain PASS followers=100000 executed=0 canceled=100000 failed_epochs=100000 retained_peak=1 retained_final=0 stack=bounded retry=accepted' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT resize_present_barrier_queue PASS cases=39 frame_binding=3 order=prior,barrier,present,release,later recovery=incomplete-frame,failed-frame,failed-present,retry supersession=queued,ready,stale-completion' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT transient_resource_gate PASS cases=3 settle_orders=2 error_object=blocked dependent=1 canceled=2 retry=accepted' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT compute_bind_group_scope PASS cases=4 dispatch_kinds=2 error_objects=2 uncaptured=0 published=2 canceled=2 retry=accepted' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT compute_pipeline_cache_publication PASS cases=3 error_object=rejected retry=published entries=2' \
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
       'CONTRACT compute_command_transaction PASS cases=6 accepted=1 error_objects=2 encoder_fail=closed pass_fail=closed command_fail=closed' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT buffer_command_transaction PASS cases=6 accepted=1 error_objects=2 browser=same-turn native=validation-ordered retry_epochs=6' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT ghost_window_publication_transaction PASS cases=5 context=2 windows=3 accepted=2 invalid=destroyed publication=atomic' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT ghost_callback_registration_transaction PASS cases=19 failed_positions=16 replacement=rollback-retry publication=atomic' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT ghost_surface_publication_status PASS cases=13 accepted=2 canvas=required surface=required configuration=required backbuffer=required device_only=explicit' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT ghost_surface_acquisition_status PASS cases=12 optimal=1 suboptimal=1 retry=2 reconfigure=6 recreate=2 failure=propagated' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT ghost_device_loss_state PASS cases=13 transitions=7 lost=6 work=3 generation=bound terminal=sticky callback=lifetime_safe' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT ghost_device_loss_inflight_cancel PASS cases=10 active=5 lost=5 configure=0 publication=0 submit=0 present=0' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT ghost_present_resource_transaction PASS cases=18 backbuffer=3 pipeline=6 frame=9 error_objects=3 publication=scoped submit=3 same_tick=3 dual_scope=3 committed=1' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT ghost_resize_coherence PASS cases=17 candidates=10 present=7 failure=preserved superseded=retried commit=atomic retry=no_event' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT index_buffer_handle_resolution PASS cases=3 required=2 failure=atomic optional=empty' \
       "$stdout_file" ||
     ! grep -qx 'CONTRACT format_32bit PASS cases=36' "$stdout_file" ||
     ! grep -qx 'CONTRACT format_subword PASS cases=48' "$stdout_file" ||
     ! grep -qx 'CONTRACT format_i10 PASS cases=12 normalized=4' "$stdout_file" ||
     ! grep -qx 'CONTRACT dummy_vertex PASS cases=32 stride=0 step=vertex' "$stdout_file" ||
     ! grep -qx 'CONTRACT shader_lifetime_cache PASS cases=4096 unique=4096' "$stdout_file" ||
     ! grep -qx 'CONTRACT vertex_alias_cache_key PASS cases=2 aliases=4 unique=2' "$stdout_file" ||
     ! grep -qx \
       'INTEGRATED_PIPELINE_PASS contracts=44 primitives=11 strip_cases=33 multiview_allocations=2 dummy_buffer_creations=3 indirect_spans=19 direct_draws=16 viewport_scissors=28 window_rects=32 offscreen_rects=21 compute_direct=15 compute_indirect=13 compute_command_cases=6 buffer_command_cases=6 scheduler_failure_followers=100000 scheduler_failed_epochs=100000 resize_present_barrier_cases=39 ghost_window_cases=5 ghost_callback_registration_cases=17 ghost_surface_cases=13 ghost_acquire_cases=12 ghost_device_loss_cases=13 ghost_loss_inflight_cases=10 ghost_present_cases=14 ghost_resize_cases=17 formats=96 i10=12 dummy=32 transient_publications=2 vertex_binding_resolutions=3 bind_group_completeness_cases=6 index_binding_resolutions=3 shader_module_set_cases=4 scoped_cache_cases=5 auxiliary_cache_redraw_cases=7 ordered_scoped_cache_cases=5 context_pipeline_caches=3 context_handle_registry_cases=7 transient_resource_gates=3 compute_bind_group_scope_cases=4 compute_cache_publications=3 load_action_commits=2 load_action_transactions=6 layered_clear_orders=4 shader_lifetimes=4096 alias_keys=2' \
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
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" -n ghost_acquisition_lifetime_asan
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" -n wgpu_pipeline_integrated_smoke
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" -n ghost_acquisition_lifetime_wasm

OUTPUT_BYTES="$(wc -c <"$WASM_STDOUT" | tr -d ' ')"
OUTPUT_SHA256="$(sha256_file "$WASM_STDOUT")"
SOURCE_SHA256="$(source_digest)"
printf 'PASS integrated-pipeline native/wasm bytes=%s sha256=%s source_sha256=%s fmt_sha256=%s dawn=%s emcc=%s node=%s\n' \
  "$OUTPUT_BYTES" "$OUTPUT_SHA256" "$SOURCE_SHA256" "$FMT_SHA256" \
  "$DAWN_PIN" "$EMCC_VERSION" "$NODE_VERSION"
