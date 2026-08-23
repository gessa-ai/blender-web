#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Device-free native/Wasm parity driver for the canonical in-tree WebGPU
# render-pipeline enum mappings, direct/indirect draw and dispatch spans, clipped
# multi-viewport/window-backbuffer rectangles, transient uniform and pipeline
# shader-module/pipeline cache publication, scoped transient bind-group validation,
# exact surviving-WGSL bind-group completeness,
# layered load-action commit,
# ordinary load-action submission transactions,
# fail-closed vertex/index-buffer resolution,
# color-blit/indexed-fan resource guards,
# buffer/storage/context-render/
# framebuffer full/scissored-clear and copy, texture render-clear, batch, and immediate-draw
# command transactions,
# dummy-attribute binding
# plan, and shader-lifetime cache separation.
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
GHOST_TRANSACTION_HEADER="$ROOT/platform_web/ghost/GHOST_WGPUTransaction.hh"
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
                platform_web/ghost/GHOST_SystemWeb.cc \
                platform_web/ghost/GHOST_WGPUTransaction.hh | sha256sum | awk '{print $1}')"
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
                    platform_web/ghost/GHOST_SystemWeb.cc \
                    platform_web/ghost/GHOST_WGPUTransaction.hh | \
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
require_file "$GHOST_SOURCE"
require_file "$GHOST_HEADER"
require_file "$GHOST_WINDOW_SOURCE"
require_file "$GHOST_SYSTEM_SOURCE"
require_file "$GHOST_TRANSACTION_HEADER"
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
  'cache_.get_or_create(instance,' \
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
  'pipeline_pool().get(' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'pipeline_pool().get(' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
require_fixed_count 1 \
  'sampler_cache_.get_or_create(' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 1 \
  'sampler_cache_.lookup(key);' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
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
    if common_text.count(direct) != 1:
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
PY
require_fixed_count 1 \
  'inline bool transient_handle_publish_if_valid(HandleT candidate, HandleT &result)' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline bool bind_group_binding_ids_complete(' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'bool bind_group_entries_complete(' \
  "$WEBGPU_SOURCE/wgpu_shader.hh"
require_fixed_count 1 \
  'if (webgpu::bind_group_binding_ids_complete(surviving_bindings_,' \
  "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 1 \
  'if (!shader->bind_group_entries_complete(entries)) {' \
  "$WEBGPU_SOURCE/wgpu_backend.cc"
require_fixed_count 4 \
  'if (!shader->bind_group_entries_complete(entries)) {' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'if (!shader->bind_group_entries_complete(entries)) {' \
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
guard = "if (!shader->bind_group_entries_complete(entries)) {"
append = "ctx->append_resource_bind_entries(shader, entries);"
command = "webgpu::command_encode_submit_scoped("

compute = method(backend, "static bool build_compute_bind_group(")
if compute.count(append) != 1 or compute.count(guard) != 1:
    raise SystemExit("ERROR: compute bind-group completeness transaction is ambiguous")
if not (compute.index(append) < compute.index(guard) < compute.index("if (entries.empty())")):
    raise SystemExit("ERROR: compute confuses missing resources with an empty layout")

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
  'load_action_transaction() const' \
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

materialize_body = method_body("bool WGPUFrameBuffer::materialize_layered_loadstore_clears(")
ordered_commit = (
    "load_action_transaction();",
    "if (!load_action->stage(uint32_t(index)))",
    "if (!clear_attachment_full(",
    "[load_action](const bool valid) { load_action->complete(valid); }",
)
positions = [materialize_body.find(needle) for needle in ordered_commit]
if any(position < 0 for position in positions) or positions != sorted(positions):
    raise SystemExit("ERROR: layered load clear is not committed by its scoped completion")
for obsolete in (
    "layered_load_clear_pending_mask_",
    "load_store_[index].load_action = GPU_LOADACTION_LOAD;",
    "framebuffer_load_action_commit_if_valid(",
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
  'load_action->complete(valid);' \
  "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 \
  'load_action = fb->load_action_transaction();' \
  "$WEBGPU_SOURCE/wgpu_immediate.cc"
require_fixed_count 1 \
  'load_action->complete(valid);' \
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
    "webgpu::command_encode_submit_scoped(",
    "fb->begin_load_pass(",
    "ctx->create_bind_group_checked(",
    "load_action->complete(valid);",
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
    for obsolete in ("begin_load_pass(mv_enc, layer)", "begin_load_pass(enc);"):
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
        "bool Buffer::update_sub(",
        "encoder.CopyBufferToBuffer(\n                                     staging, 0, allocation.handle, offset, size);",
    ),
    (
        "std::vector<uint8_t> Buffer::read(",
        "encoder.CopyBufferToBuffer(\n                                     allocation.handle, offset, staging, 0, copy);",
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
  'if (!webgpu::window_viewport_scissor_plan(' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
require_fixed_count 1 \
  'if (!webgpu::offscreen_viewport_scissor_plan(' "$WEBGPU_SOURCE/wgpu_framebuffer.cc"
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
WINDOW_PLAN_LINE="$(grep -nF 'if (!webgpu::window_viewport_scissor_plan(' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc" | cut -d: -f1)"
OFFSCREEN_PLAN_LINE="$(grep -nF 'if (!webgpu::offscreen_viewport_scissor_plan(' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc" | cut -d: -f1)"
LAYERED_CLEAR_LINE="$(grep -nF 'if (!materialize_layered_loadstore_clears())' \
  "$WEBGPU_SOURCE/wgpu_framebuffer.cc" | cut -d: -f1)"
BEGIN_PASS_LINE="$(grep -nF \
  'if (!webgpu::transient_handle_publish_if_valid(encoder.BeginRenderPass(&rp), pass))' \
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
require_fixed_count 1 '#include "GHOST_WGPUTransaction.hh"' "$GHOST_SOURCE"
require_fixed_count 1 '#include "GHOST_WGPUTransaction.hh"' "$GHOST_WINDOW_SOURCE"
require_fixed_count 1 '#include "GHOST_WGPUTransaction.hh"' "$GHOST_SYSTEM_SOURCE"
require_fixed_count 1 'ghost_web::drawing_context_initialize_if_valid(' "$GHOST_WINDOW_SOURCE"
require_fixed_count 1 'ghost_web::window_publish_if_valid(' "$GHOST_SYSTEM_SOURCE"
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
"$PYBIN" - "$GHOST_SOURCE" <<'PY'
from pathlib import Path
import sys


source = Path(sys.argv[1]).read_text(encoding="utf-8")


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


configure = method("void GHOST_ContextWGPUWeb::configureSurface(uint32_t width, uint32_t height)")
backbuffer = method("void GHOST_ContextWGPUWeb::ensureBackbuffer()")
pipeline = method("void GHOST_ContextWGPUWeb::ensurePresentPipeline()")
present = method("void GHOST_ContextWGPUWeb::presentBackbuffer()")

for needle in ("requested_width_ = w;", "requested_height_ = h;", "ensureBackbuffer();"):
    if configure.count(needle) != 1:
        raise SystemExit(f"ERROR: resize request lacks one exact pending-state boundary: {needle}")
if "surface_.Configure(&config);" in configure:
    raise SystemExit("ERROR: resize configures the surface before candidate validation")

for label, body, helper, scope_label, pending in (
    ("backbuffer", backbuffer, "ghost_web::scoped_handle_create(",
     'popErrorScopes(device, "backbuffer creation"', "backbuffer_pending_"),
    ("pipeline", pipeline, "ghost_web::present_pipeline_create_scoped(",
     'popErrorScopes(device, "present pipeline creation"', "present_pipeline_pending_"),
):
    if body.count(helper) != 1 or body.count(scope_label) != 1 or body.count(pending) < 2:
        raise SystemExit(f"ERROR: {label} is not bound to one completed error-scope publication")

for needle in (
    "const uint32_t candidate_width = requested_width_;",
    "const uint32_t candidate_height = requested_height_;",
    "ghost_web::surface_resize_commit_if_current(",
    "surface_.Configure(&config);",
    "if (result == ghost_web::SurfaceResizeResult::Superseded) {",
):
    if backbuffer.count(needle) != 1:
        raise SystemExit(f"ERROR: backbuffer resize lacks one exact coherence boundary: {needle}")

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

positions = [
    present.index('popErrorScopes(device, "present command encoding"'),
    present.index("queue.Submit(1, &command_buffer);"),
    present.index('popErrorScopes(device, "present queue submission"'),
    present.index("if (!valid) {"),
    present.index("ghost_web::note_present();"),
]
if positions != sorted(positions):
    raise SystemExit("ERROR: present validation/submission/commit boundaries are reordered")

for needle in (
    "ensureBackbuffer();",
    "ghost_web::surface_resize_present_coherent(",
    "configureSurface(surface_width, surface_height);",
):
    if present.count(needle) != 1:
        raise SystemExit(f"ERROR: present resize coherence lacks one exact boundary: {needle}")
resize_positions = [
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
  -DBW_GHOST_PRESENT_TRANSACTION_HEADER="$GHOST_TRANSACTION_HEADER" \
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
  if [ "$(wc -l <"$stdout_file" | tr -d ' ')" -ne 32 ] ||
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
       'CONTRACT bind_group_completeness PASS cases=6 accepted=3 rejected=3 internal=2 unique=deduplicated' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT framebuffer_load_action_commit PASS cases=2 failure=pending retry=committed' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT framebuffer_load_action_transaction PASS cases=6 attachments=3 late_view=pending late_bind=pending same_epoch=load retry=committed generation=isolated' \
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
       'CONTRACT transient_resource_gate PASS cases=3 settle_orders=2 error_object=blocked dependent=1 canceled=2 retry=accepted' \
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
       'CONTRACT buffer_command_transaction PASS cases=6 accepted=1 error_objects=2 ordered=1 canceled=5 retry_epochs=6' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT ghost_window_publication_transaction PASS cases=5 context=2 windows=3 accepted=2 invalid=destroyed publication=atomic' \
       "$stdout_file" ||
     ! grep -qx \
       'CONTRACT ghost_present_resource_transaction PASS cases=18 backbuffer=3 pipeline=6 frame=9 error_objects=3 publication=scoped submit=2 committed=1' \
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
       'INTEGRATED_PIPELINE_PASS contracts=31 primitives=11 strip_cases=33 multiview_allocations=2 dummy_buffer_creations=3 indirect_spans=19 direct_draws=16 viewport_scissors=28 window_rects=32 offscreen_rects=21 compute_direct=15 compute_indirect=13 compute_command_cases=6 buffer_command_cases=6 ghost_window_cases=5 ghost_present_cases=14 ghost_resize_cases=17 formats=96 i10=12 dummy=32 transient_publications=2 vertex_binding_resolutions=3 bind_group_completeness_cases=6 index_binding_resolutions=3 shader_module_set_cases=4 scoped_cache_cases=5 transient_resource_gates=3 compute_cache_publications=3 load_action_commits=2 load_action_transactions=6 shader_lifetimes=4096 alias_keys=2' \
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
