#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Device-free native/Wasm parity driver for the canonical in-tree WebGPU
# buffer wrapper, pixel-upload buffer, readback registry, and index-buffer
# point-restart cleanup and direct/indirect indexed-draw subrange binding plans.
# The pure buffer arithmetic leg also binds fail-closed alignment and subrange
# validation at size_t's representable boundary.
# Invoke through harness/buildwrap.sh.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WEBGPU_SOURCE="${WEBGPU_SOURCE:-$ROOT/upstream/source/blender/gpu/webgpu}"
DAWN_SRC="${DAWN_SRC:-$ROOT/build-dawn/dawn}"
DAWN_PIN="36cf1fae0cd8a81a4fb4580751648b80b2e6255c"
NATIVE_BUILD="${NATIVE_BUILD:-$ROOT/build-dawn/probe-build}"
WASM_BUILD="${WASM_BUILD:-$ROOT/build-deps/t6-integrated/wasm-build}"
OUT="${OUT:-$ROOT/build-deps/t6-integrated/evidence}"
EMSDK="${EMSDK:-$ROOT/tools/emsdk}"
NODE="${NODE:-$EMSDK/node/22.16.0_64bit/bin/node}"
PYBIN="$ROOT/.host-tools/bin/python3.13"
HOST_CMAKE="${HOST_CMAKE:-$ROOT/.host-tools/bin/cmake}"
WASM_INCLUDE="$ROOT/lib/wasm/include"
INDEX_STRIP_SOURCE="$ROOT/build-deps/t6-integrated/generated/wgpu_index_strip.inc"
INDEX_UPLOAD_SOURCE="$ROOT/build-deps/t6-integrated/generated/wgpu_index_upload.inc"
BUFFER_UPDATE_SOURCE="$ROOT/build-deps/t6-integrated/generated/wgpu_buffer_update.inc"
BUFFER_CREATE_SOURCE="$ROOT/build-deps/t6-integrated/generated/wgpu_buffer_create.inc"
PENDING_PAYLOAD_FRONTEND_SOURCE="$ROOT/build-deps/t6-integrated/generated/wgpu_pending_payload_frontend.inc"
VERTEX_UPLOAD_FRONTEND_SOURCE="$ROOT/build-deps/t6-integrated/generated/wgpu_vertex_upload_frontend.inc"

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
    source/blender/gpu/webgpu/wgpu_buffer.cc
    source/blender/gpu/webgpu/wgpu_buffer.hh
    source/blender/gpu/webgpu/wgpu_common.hh
    source/blender/gpu/webgpu/wgpu_context.cc
    source/blender/gpu/webgpu/wgpu_pixel_buffer.cc
    source/blender/gpu/webgpu/wgpu_pixel_buffer.hh
    source/blender/gpu/webgpu/wgpu_readback.cc
    source/blender/gpu/webgpu/wgpu_readback.hh
    source/blender/gpu/webgpu/wgpu_storage_buffer.cc
    source/blender/gpu/webgpu/wgpu_storage_buffer.hh
    source/blender/gpu/webgpu/wgpu_uniform_buffer.cc
    source/blender/gpu/webgpu/wgpu_uniform_buffer.hh
    source/blender/gpu/webgpu/wgpu_vertex_buffer.cc
    source/blender/gpu/webgpu/wgpu_vertex_buffer.hh
    source/blender/gpu/webgpu/wgpu_shader.cc
    source/blender/gpu/webgpu/wgpu_index_buffer.cc
    source/blender/gpu/webgpu/wgpu_index_buffer.hh
    source/blender/gpu/webgpu/wgpu_batch.cc
    source/blender/gpu/intern/gpu_batch.cc
    source/blender/draw/intern/draw_shader_shared.hh
    source/blender/draw/intern/shaders/draw_command_generate_comp.glsl
    source/blender/draw/engines/eevee/eevee_shadow.cc
    source/blender/draw/intern/mesh_extractors/extract_mesh_ibo_tris.cc
    source/blender/gpu/intern/gpu_index_buffer.cc
    source/blender/gpu/intern/gpu_vertex_buffer.cc
    source/blender/gpu/intern/gpu_texture_private.hh
    source/blender/gpu/GPU_index_buffer.hh
    source/blender/gpu/GPU_primitive.hh
    source/blender/gpu/GPU_texture.hh
    source/blender/gpu/GPU_vertex_buffer.hh
    intern/guardedalloc/MEM_guardedalloc.h
    intern/guardedalloc/intern/leak_detector.cc
    intern/guardedalloc/intern/mallocn.cc
    intern/guardedalloc/intern/mallocn_guarded_impl.cc
    intern/guardedalloc/intern/mallocn_lockfree_impl.cc
    intern/guardedalloc/intern/memory_usage.cc
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
require_file "$HERE/integrated_buffer_test.cc"
require_file "$HERE/integrated_index_test.cc"
require_file "$HERE/extract_index_strip.py"
require_file "$HERE/extract_index_upload.py"
require_file "$HERE/extract_buffer_update.py"
require_file "$HERE/extract_buffer_create.py"
require_file "$HERE/extract_pending_payload_frontend.py"
require_file "$HERE/extract_vertex_upload_frontend.py"
require_file "$HERE/integrated_buffer_create_test.cc"
require_file "$HERE/integrated_buffer_update_test.cc"
require_file "$HERE/integrated_vertex_upload_generation_test.cc"
require_file "$ROOT/sandbox/wgpu-buffer-wasm-smoke/CMakeLists.txt"
require_file "$EMSDK/emsdk_env.sh"
require_file "$EMSDK/upstream/emscripten/emcmake"
require_file "$NODE"
for source_name in \
  wgpu_buffer.cc \
  wgpu_buffer.hh \
  wgpu_common.hh \
  wgpu_context.cc \
  wgpu_pixel_buffer.cc \
  wgpu_pixel_buffer.hh \
  wgpu_readback.cc \
  wgpu_readback.hh \
  wgpu_storage_buffer.cc \
  wgpu_storage_buffer.hh \
  wgpu_uniform_buffer.cc \
  wgpu_uniform_buffer.hh \
  wgpu_vertex_buffer.cc \
  wgpu_vertex_buffer.hh \
  wgpu_index_buffer.cc \
  wgpu_index_buffer.hh \
  wgpu_batch.cc
do
  require_file "$WEBGPU_SOURCE/$source_name"
done
require_file "$ROOT/upstream/source/blender/gpu/intern/gpu_texture_private.hh"
require_file "$ROOT/upstream/source/blender/gpu/intern/gpu_index_buffer.cc"
require_file "$ROOT/upstream/source/blender/gpu/intern/gpu_vertex_buffer.cc"
require_file "$ROOT/upstream/source/blender/gpu/GPU_index_buffer.hh"
require_file "$ROOT/upstream/source/blender/gpu/GPU_primitive.hh"
require_file "$ROOT/upstream/source/blender/gpu/GPU_texture.hh"
require_file "$ROOT/upstream/source/blender/gpu/GPU_vertex_buffer.hh"
require_file "$ROOT/upstream/source/blender/gpu/intern/gpu_batch.cc"
require_file "$ROOT/upstream/intern/guardedalloc/MEM_guardedalloc.h"
require_file "$ROOT/upstream/source/blender/draw/intern/draw_shader_shared.hh"
require_file \
  "$ROOT/upstream/source/blender/draw/intern/shaders/draw_command_generate_comp.glsl"
require_file "$ROOT/upstream/source/blender/draw/engines/eevee/eevee_shadow.cc"
require_file \
  "$ROOT/upstream/source/blender/draw/intern/mesh_extractors/extract_mesh_ibo_tris.cc"
for source_name in \
  leak_detector.cc \
  mallocn.cc \
  mallocn_guarded_impl.cc \
  mallocn_lockfree_impl.cc \
  memory_usage.cc
do
  require_file "$ROOT/upstream/intern/guardedalloc/intern/$source_name"
done
require_file "$NATIVE_FMT_INCLUDE/fmt/ranges.h"
require_file "$WASM_INCLUDE/fmt/ranges.h"
if ! cmp -s "$NATIVE_FMT_INCLUDE/fmt/ranges.h" "$WASM_INCLUDE/fmt/ranges.h"; then
  echo "ERROR: native and Wasm fmt/ranges.h inputs differ" >&2
  exit 1
fi
FMT_SHA256="$(sha256_file "$WASM_INCLUDE/fmt/ranges.h")"

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

# Bind the pure metadata contract to the shipping direct and indirect draw arms,
# then bind the indirect command producer and separately census real
# multi-viewport and mesh-subrange producers. Live combinations remain part of
# the hardware-owned M3 replay.
require_fixed_count 1 \
  'inline IndexBindingPlan index_binding_plan(const IndexBuf &index_buffer,' \
  "$WEBGPU_SOURCE/wgpu_index_buffer.hh"
require_fixed_count 1 'webgpu::IndexBindingMode::Direct' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 'webgpu::IndexBindingMode::Indirect' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 3 'index_binding.byte_offset' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 4 'index_binding.base_vertex' "$WEBGPU_SOURCE/wgpu_batch.cc"
require_fixed_count 1 '*r_vertex_first = batch->elem_()->index_start_get();' \
  "$ROOT/upstream/source/blender/gpu/intern/gpu_batch.cc"
require_fixed_count 1 '*r_base_index = batch->elem_()->index_base_get();' \
  "$ROOT/upstream/source/blender/gpu/intern/gpu_batch.cc"
require_fixed_count 2 'cmd_indexed.vertex_first = uint(group.vertex_first);' \
  "$ROOT/upstream/source/blender/draw/intern/shaders/draw_command_generate_comp.glsl"
require_fixed_count 2 'cmd_indexed.base_index = uint(group.base_index);' \
  "$ROOT/upstream/source/blender/draw/intern/shaders/draw_command_generate_comp.glsl"
require_fixed_count 1 'GPU_framebuffer_multi_viewports_set(render_fb_,' \
  "$ROOT/upstream/source/blender/draw/engines/eevee/eevee_shadow.cc"
require_fixed_count 2 'GPU_indexbuf_create_subrange' \
  "$ROOT/upstream/source/blender/draw/intern/mesh_extractors/extract_mesh_ibo_tris.cc"
require_fixed_count 1 \
  'inline bool checked_align_up(size_t v, size_t a, size_t &result)' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline bool buffer_allocation_size(size_t requested_size,' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline void command_encode_submit_scoped(const InstanceT &instance,' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 2 \
  'webgpu::command_encode_submit_scoped(' \
  "$WEBGPU_SOURCE/wgpu_readback.cc"
require_fixed_count 2 \
  'fail_reserved_pending(pending, TicketError::CommandEncodingFailed);' \
  "$WEBGPU_SOURCE/wgpu_readback.cc"
require_fixed_count 0 \
  'wgpu::CommandEncoder encoder = device.CreateCommandEncoder();' \
  "$WEBGPU_SOURCE/wgpu_readback.cc"
require_fixed_count 2 \
  'if (instance == nullptr || device == nullptr || !device.GetLimits(&limits) ||' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 2 \
  '!buffer_allocation_size(size, limits.maxBufferSize, allocated_size))' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 1 \
  'struct BufferUpdatePayload {' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'inline bool buffer_update_payload(const void *data,' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'if (!webgpu::buffer_update_payload(' \
  "$WEBGPU_SOURCE/wgpu_storage_buffer.cc"
require_fixed_count 1 \
  '#  include "GHOST_WebDisplayState.hh"' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 1 \
  'request_webgpu_redraw_retry();' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 1 \
  'payload.data(data),' \
  "$WEBGPU_SOURCE/wgpu_storage_buffer.cc"
if grep -Fq 'align_up(usage_size_in_bytes_, webgpu::kCopyAlignment)' \
  "$WEBGPU_SOURCE/wgpu_storage_buffer.cc"
then
  echo "ERROR: storage update still rounds beyond caller-owned payload" >&2
  exit 1
fi
STORAGE_UPDATE_GUARD_LINE="$(grep -nF 'if (!webgpu::buffer_update_payload(' \
  "$WEBGPU_SOURCE/wgpu_storage_buffer.cc" | cut -d: -f1)"
STORAGE_UPDATE_TRANSFER_LINE="$(grep -nF 'payload.data(data),' \
  "$WEBGPU_SOURCE/wgpu_storage_buffer.cc" | cut -d: -f1)"
if [ -z "$STORAGE_UPDATE_GUARD_LINE" ] || [ -z "$STORAGE_UPDATE_TRANSFER_LINE" ] ||
   [ "$STORAGE_UPDATE_GUARD_LINE" -ge "$STORAGE_UPDATE_TRANSFER_LINE" ]
then
  echo "ERROR: storage update payload guard does not precede transfer" >&2
  exit 1
fi
require_fixed_count 1 'bool Buffer::create_scoped(const wgpu::Instance &instance,' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 1 'bool Buffer::create_transient(const wgpu::Instance &instance,' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 1 'transient_allocation_ = transient_resource_create_scoped(' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 1 'const Allocation allocation = allocation_cache_.get_or_create(' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 2 'candidate.handle = device.CreateBuffer(&descriptor);' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 2 'candidate.size = allocated_size;' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 1 'ScopedHandleCache<uint8_t, Allocation> allocation_cache_;' \
  "$WEBGPU_SOURCE/wgpu_buffer.hh"
require_fixed_count 2 '.create_scoped(ctx->instance_get(),' \
  "$WEBGPU_SOURCE/wgpu_index_buffer.cc"
require_fixed_count 2 '.create_scoped(ctx->instance_get(),' \
  "$WEBGPU_SOURCE/wgpu_vertex_buffer.cc"
require_fixed_count 1 '.create_scoped(ctx->instance_get(),' \
  "$WEBGPU_SOURCE/wgpu_uniform_buffer.cc"
require_fixed_count 1 'return buffer_.create_scoped(' \
  "$WEBGPU_SOURCE/wgpu_storage_buffer.cc"
require_fixed_count 1 'class PendingBufferPayloadQueue {' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 'class BufferUpdateTransaction {' "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 'size_t retry_pending_updates();' "$WEBGPU_SOURCE/wgpu_buffer.hh"
require_fixed_count 1 'webgpu::BufferUpdateTransaction upload_transaction_;' \
  "$WEBGPU_SOURCE/wgpu_vertex_buffer.hh"
require_fixed_count 1 'void WGPUVertexBuffer::upload_data()' \
  "$WEBGPU_SOURCE/wgpu_vertex_buffer.cc"
require_fixed_count 1 'void WGPUVertexBuffer::bind_as_texture(uint binding)' \
  "$WEBGPU_SOURCE/wgpu_vertex_buffer.cc"
require_fixed_count 1 \
  'void GPU_vertbuf_attr_set(VertBuf *verts, uint a_idx, uint v_idx, const void *data)' \
  "$ROOT/upstream/source/blender/gpu/intern/gpu_vertex_buffer.cc"
require_fixed_count 1 'webgpu::BufferUpdateTransaction deferred_upload_transaction_;' \
  "$WEBGPU_SOURCE/wgpu_uniform_buffer.hh"
require_fixed_count 1 'payload.transfer_size,' "$WEBGPU_SOURCE/wgpu_vertex_buffer.cc"
require_fixed_count 2 'upload_transaction_))' "$WEBGPU_SOURCE/wgpu_vertex_buffer.cc"
require_fixed_count 2 'deferred_upload_transaction_.accepted()' \
  "$WEBGPU_SOURCE/wgpu_uniform_buffer.cc"
VERTEX_UPLOAD_ACCEPT_LINE="$(grep -nF 'if (!upload_transaction_.accepted())' \
  "$WEBGPU_SOURCE/wgpu_vertex_buffer.cc" | tail -n 1 | cut -d: -f1)"
VERTEX_UPLOAD_CLEANUP_LINE="$(grep -nF 'MEM_SAFE_DELETE(data_);' \
  "$WEBGPU_SOURCE/wgpu_vertex_buffer.cc" | tail -n 1 | cut -d: -f1)"
UNIFORM_UPLOAD_ACCEPT_LINE="$(grep -nF '!deferred_upload_transaction_.accepted()' \
  "$WEBGPU_SOURCE/wgpu_uniform_buffer.cc" | tail -n 1 | cut -d: -f1)"
UNIFORM_UPLOAD_CLEANUP_LINE="$(grep -nF 'MEM_SAFE_DELETE_VOID(data_);' \
  "$WEBGPU_SOURCE/wgpu_uniform_buffer.cc" | tail -n 1 | cut -d: -f1)"
if [ -z "$VERTEX_UPLOAD_ACCEPT_LINE" ] || [ -z "$VERTEX_UPLOAD_CLEANUP_LINE" ] ||
   [ "$VERTEX_UPLOAD_ACCEPT_LINE" -ge "$VERTEX_UPLOAD_CLEANUP_LINE" ] ||
   [ -z "$UNIFORM_UPLOAD_ACCEPT_LINE" ] || [ -z "$UNIFORM_UPLOAD_CLEANUP_LINE" ] ||
   [ "$UNIFORM_UPLOAD_ACCEPT_LINE" -ge "$UNIFORM_UPLOAD_CLEANUP_LINE" ]
then
  echo "ERROR: VBO/UBO upload acceptance does not precede CPU-state commit" >&2
  exit 1
fi
require_fixed_count 1 'pending_updates_->retain(' "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 1 'pending_updates->replay(' "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 3 'allocation_ready || buffer_.creation_pending_or_retryable()' \
  "$WEBGPU_SOURCE/wgpu_storage_buffer.cc"
require_fixed_count 6 'allocation_ready || buffer_.creation_pending_or_retryable()' \
  "$WEBGPU_SOURCE/wgpu_uniform_buffer.cc"
require_fixed_count 1 'push_constants_buffer_.create_scoped(ctx->instance_get(),' \
  "$WEBGPU_SOURCE/wgpu_shader.cc"
require_fixed_count 1 'return track_next_allocation_ && buffer_.creation_pending();' \
  "$WEBGPU_SOURCE/wgpu_vertex_buffer.cc"
require_fixed_count 0 'PushErrorScope(' "$WEBGPU_SOURCE/wgpu_vertex_buffer.cc"
require_fixed_count 1 'if (!range_fits(offset, size, allocation.size)) {' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 1 'void *mapped = staging.GetMappedRange(0, size);' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 3 'if (mapped == nullptr) {' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 1 'std::memcpy(mapped, data, size);' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 1 'wgpu::Buffer staging = transient_resource_create_scoped(' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
STAGING_SCOPE_LINE="$(grep -nF 'wgpu::Buffer staging = transient_resource_create_scoped(' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc" | cut -d: -f1)"
STAGING_COMMAND_LINE="$(grep -nF 'command_encode_submit_scoped(context.instance,' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc" | cut -d: -f1)"
if [ -z "$STAGING_SCOPE_LINE" ] || [ -z "$STAGING_COMMAND_LINE" ] ||
   [ "$STAGING_SCOPE_LINE" -ge "$STAGING_COMMAND_LINE" ]
then
  echo "ERROR: staged buffer resource gate does not precede its command ticket" >&2
  exit 1
fi
require_fixed_count 1 'inline bool mapped_buffer_write(' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 2 'if (!webgpu::mapped_buffer_write(' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
require_fixed_count 0 '.GetMappedRange(' \
  "$WEBGPU_SOURCE/wgpu_context.cc"
STAGING_MAP_LINE="$(grep -nF 'void *mapped = staging.GetMappedRange(0, size);' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc" | cut -d: -f1)"
STAGING_MAP_GUARD_LINE="$(grep -nF 'if (mapped == nullptr) {' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc" | tail -n 1 | cut -d: -f1)"
STAGING_COPY_LINE="$(grep -nF 'std::memcpy(mapped, data, size);' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc" | tail -n 1 | cut -d: -f1)"
if [ -z "$STAGING_MAP_LINE" ] || [ -z "$STAGING_MAP_GUARD_LINE" ] ||
   [ -z "$STAGING_COPY_LINE" ] ||
   [ "$STAGING_MAP_LINE" -ge "$STAGING_MAP_GUARD_LINE" ] ||
   [ "$STAGING_MAP_GUARD_LINE" -ge "$STAGING_COPY_LINE" ]
then
  echo "ERROR: staging mapped range is not checked before the large update copy" >&2
  exit 1
fi
require_fixed_count 1 \
  'if (!checked_align_up(size, kCopyAlignment, copy) ||' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 1 \
  '!buffer_copy_range_valid(offset, 0, copy, allocation.size, copy))' \
  "$WEBGPU_SOURCE/wgpu_buffer.cc"
require_fixed_count 1 \
  'inline bool buffer_copy_range_valid(size_t source_offset,' \
  "$WEBGPU_SOURCE/wgpu_common.hh"
require_fixed_count 1 \
  'if (!webgpu::buffer_copy_range_valid(src_offset,' \
  "$WEBGPU_SOURCE/wgpu_storage_buffer.cc"
require_fixed_count 1 \
  'if (!buffer_.create_scoped(ctx->instance_get(),' \
  "$WEBGPU_SOURCE/wgpu_index_buffer.cc"
INDEX_UPLOAD_GUARD_LINE="$(grep -nF 'if (!buffer_.create_scoped(ctx->instance_get(),' \
  "$WEBGPU_SOURCE/wgpu_index_buffer.cc" | cut -d: -f1)"
INDEX_UPLOAD_CLEANUP_LINE="$(grep -nF 'MEM_SAFE_DELETE_VOID(data_);' \
  "$WEBGPU_SOURCE/wgpu_index_buffer.cc" | tail -n 1 | cut -d: -f1)"
if [ -z "$INDEX_UPLOAD_GUARD_LINE" ] || [ -z "$INDEX_UPLOAD_CLEANUP_LINE" ] ||
   [ "$INDEX_UPLOAD_GUARD_LINE" -ge "$INDEX_UPLOAD_CLEANUP_LINE" ]
then
  echo "ERROR: index upload does not guard host-data cleanup on create success" >&2
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

INDEX_NEGATIVE_DIR="$(mktemp -d /tmp/blender-web-index-extract.XXXXXX)"
INDEX_NEGATIVE_OUTPUT="$INDEX_NEGATIVE_DIR/generated.inc"
if INDEX_NEGATIVE_MESSAGE="$("$PYBIN" "$HERE/extract_index_strip.py" \
  --source "$WEBGPU_SOURCE/wgpu_index_buffer.hh" \
  --output "$INDEX_NEGATIVE_OUTPUT" 2>&1)"
then
  echo "ERROR: malformed index-strip source was accepted" >&2
  exit 1
fi
if [ "$INDEX_NEGATIVE_MESSAGE" != \
     "INDEX_STRIP_EXTRACT_FAIL canonical index-strip method boundaries are not unique" ] ||
   [ -e "$INDEX_NEGATIVE_OUTPUT" ]
then
  echo "ERROR: malformed index-strip rejection differs" >&2
  exit 1
fi
"$PYBIN" "$HERE/extract_index_strip.py" \
  --source "$WEBGPU_SOURCE/wgpu_index_buffer.cc" \
  --output "$INDEX_STRIP_SOURCE"
require_file "$INDEX_STRIP_SOURCE"

INDEX_UPLOAD_NEGATIVE_OUTPUT="$INDEX_NEGATIVE_DIR/upload.inc"
if INDEX_UPLOAD_NEGATIVE_MESSAGE="$("$PYBIN" "$HERE/extract_index_upload.py" \
  --source "$WEBGPU_SOURCE/wgpu_index_buffer.hh" \
  --output "$INDEX_UPLOAD_NEGATIVE_OUTPUT" 2>&1)"
then
  echo "ERROR: malformed index-upload source was accepted" >&2
  exit 1
fi
if [ "$INDEX_UPLOAD_NEGATIVE_MESSAGE" != \
     "INDEX_UPLOAD_EXTRACT_FAIL canonical index-upload method boundaries are not unique" ] ||
   [ -e "$INDEX_UPLOAD_NEGATIVE_OUTPUT" ]
then
  echo "ERROR: malformed index-upload rejection differs" >&2
  exit 1
fi

"$PYBIN" "$HERE/extract_index_upload.py" \
  --source "$WEBGPU_SOURCE/wgpu_index_buffer.cc" \
  --output "$INDEX_UPLOAD_SOURCE"
require_file "$INDEX_UPLOAD_SOURCE"

BUFFER_UPDATE_NEGATIVE_OUTPUT="$INDEX_NEGATIVE_DIR/buffer-update.inc"
if BUFFER_UPDATE_NEGATIVE_MESSAGE="$("$PYBIN" "$HERE/extract_buffer_update.py" \
  --source "$WEBGPU_SOURCE/wgpu_buffer.hh" \
  --output "$BUFFER_UPDATE_NEGATIVE_OUTPUT" 2>&1)"
then
  echo "ERROR: malformed buffer-update source was accepted" >&2
  exit 1
fi
if [ "$BUFFER_UPDATE_NEGATIVE_MESSAGE" != \
     "BUFFER_UPDATE_EXTRACT_FAIL canonical buffer-update method boundaries are not unique" ] ||
   [ -e "$BUFFER_UPDATE_NEGATIVE_OUTPUT" ]
then
  echo "ERROR: malformed buffer-update rejection differs" >&2
  exit 1
fi
"$PYBIN" "$HERE/extract_buffer_update.py" \
  --source "$WEBGPU_SOURCE/wgpu_buffer.cc" \
  --output "$BUFFER_UPDATE_SOURCE"
require_file "$BUFFER_UPDATE_SOURCE"

BUFFER_CREATE_NEGATIVE_OUTPUT="$INDEX_NEGATIVE_DIR/buffer-create.inc"
if BUFFER_CREATE_NEGATIVE_MESSAGE="$("$PYBIN" "$HERE/extract_buffer_create.py" \
  --source "$WEBGPU_SOURCE/wgpu_buffer.hh" \
  --output "$BUFFER_CREATE_NEGATIVE_OUTPUT" 2>&1)"
then
  echo "ERROR: malformed scoped buffer-create source was accepted" >&2
  exit 1
fi
if [ "$BUFFER_CREATE_NEGATIVE_MESSAGE" != \
     "BUFFER_CREATE_EXTRACT_FAIL canonical scoped buffer-create method boundaries are not unique" ] ||
   [ -e "$BUFFER_CREATE_NEGATIVE_OUTPUT" ]
then
  echo "ERROR: malformed scoped buffer-create rejection differs" >&2
  exit 1
fi
"$PYBIN" "$HERE/extract_buffer_create.py" \
  --source "$WEBGPU_SOURCE/wgpu_buffer.cc" \
  --output "$BUFFER_CREATE_SOURCE"
require_file "$BUFFER_CREATE_SOURCE"

PENDING_PAYLOAD_NEGATIVE_OUTPUT="$INDEX_NEGATIVE_DIR/pending-payload.inc"
if PENDING_PAYLOAD_NEGATIVE_MESSAGE="$("$PYBIN" "$HERE/extract_pending_payload_frontend.py" \
  --storage-source "$WEBGPU_SOURCE/wgpu_storage_buffer.hh" \
  --uniform-source "$WEBGPU_SOURCE/wgpu_uniform_buffer.hh" \
  --output "$PENDING_PAYLOAD_NEGATIVE_OUTPUT" 2>&1)"
then
  echo "ERROR: malformed pending-payload frontend source was accepted" >&2
  exit 1
fi
if [[ "$PENDING_PAYLOAD_NEGATIVE_MESSAGE" != \
      PENDING_PAYLOAD_EXTRACT_FAIL\ canonical\ storage\ ensure\ method\ boundaries* ]] ||
   [ -e "$PENDING_PAYLOAD_NEGATIVE_OUTPUT" ]
then
  echo "ERROR: malformed pending-payload frontend rejection differs" >&2
  exit 1
fi
"$PYBIN" "$HERE/extract_pending_payload_frontend.py" \
  --storage-source "$WEBGPU_SOURCE/wgpu_storage_buffer.cc" \
  --uniform-source "$WEBGPU_SOURCE/wgpu_uniform_buffer.cc" \
  --output "$PENDING_PAYLOAD_FRONTEND_SOURCE"
require_file "$PENDING_PAYLOAD_FRONTEND_SOURCE"

VERTEX_UPLOAD_NEGATIVE_OUTPUT="$INDEX_NEGATIVE_DIR/vertex-upload.inc"
if VERTEX_UPLOAD_NEGATIVE_MESSAGE="$("$PYBIN" "$HERE/extract_vertex_upload_frontend.py" \
  --frontend-source "$ROOT/upstream/source/blender/gpu/GPU_vertex_buffer.hh" \
  --webgpu-source "$WEBGPU_SOURCE/wgpu_vertex_buffer.hh" \
  --output "$VERTEX_UPLOAD_NEGATIVE_OUTPUT" 2>&1)"
then
  echo "ERROR: malformed vertex-upload frontend source was accepted" >&2
  exit 1
fi
if [[ "$VERTEX_UPLOAD_NEGATIVE_MESSAGE" != \
      VERTEX_UPLOAD_FRONTEND_EXTRACT_FAIL\ canonical\ frontend\ attribute\ mutation* ]] ||
   [ -e "$VERTEX_UPLOAD_NEGATIVE_OUTPUT" ]
then
  echo "ERROR: malformed vertex-upload frontend rejection differs" >&2
  exit 1
fi
"$PYBIN" "$HERE/extract_vertex_upload_frontend.py" \
  --frontend-source "$ROOT/upstream/source/blender/gpu/intern/gpu_vertex_buffer.cc" \
  --webgpu-source "$WEBGPU_SOURCE/wgpu_vertex_buffer.cc" \
  --output "$VERTEX_UPLOAD_FRONTEND_SOURCE"
require_file "$VERTEX_UPLOAD_FRONTEND_SOURCE"
rmdir "$INDEX_NEGATIVE_DIR"

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

echo "== [1/3] canonical native buffer/readback module =="
"$HOST_CMAKE" -G Ninja -S "$ROOT/sandbox/dawn-probe" -B "$NATIVE_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CMAKE_HOST_ARGS[@]}" \
  "${CCACHE_ARGS[@]}" \
  -DDAWN_SRC_DIR="$DAWN_SRC" \
  -DBW_UPSTREAM_DIR="$ROOT/upstream" \
  -DBW_NATIVE_FMT_INCLUDE_DIR="$NATIVE_FMT_INCLUDE" \
  -DBW_INTEGRATED_BUFFER_SOURCE_DIR="$WEBGPU_SOURCE" \
  -DBW_WGPU_INDEX_STRIP_SOURCE="$INDEX_STRIP_SOURCE" \
  -DBW_WGPU_INDEX_UPLOAD_SOURCE="$INDEX_UPLOAD_SOURCE" \
  -DBW_WGPU_BUFFER_CREATE_SOURCE="$BUFFER_CREATE_SOURCE" \
  -DBW_WGPU_PENDING_PAYLOAD_FRONTEND_SOURCE="$PENDING_PAYLOAD_FRONTEND_SOURCE" \
  -DBW_WGPU_VERTEX_UPLOAD_FRONTEND_SOURCE="$VERTEX_UPLOAD_FRONTEND_SOURCE" \
  -DBW_WGPU_BUFFER_UPDATE_SOURCE="$BUFFER_UPDATE_SOURCE" \
  -DPython3_EXECUTABLE="$PYBIN"
"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" wgpu_buffer_integrated_test

echo "== [2/3] canonical Wasm buffer/readback module =="
"$EMSDK/upstream/emscripten/emcmake" "$HOST_CMAKE" -G Ninja \
  -S "$ROOT/sandbox/wgpu-buffer-wasm-smoke" -B "$WASM_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CCACHE_ARGS[@]}" \
  -DBW_UPSTREAM_DIR="$ROOT/upstream" \
  -DBW_WASM_INCLUDE_DIR="$WASM_INCLUDE" \
  -DBW_INTEGRATED_BUFFER_SOURCE_DIR="$WEBGPU_SOURCE" \
  -DBW_WGPU_INDEX_STRIP_SOURCE="$INDEX_STRIP_SOURCE" \
  -DBW_WGPU_INDEX_UPLOAD_SOURCE="$INDEX_UPLOAD_SOURCE" \
  -DBW_WGPU_BUFFER_CREATE_SOURCE="$BUFFER_CREATE_SOURCE" \
  -DBW_WGPU_PENDING_PAYLOAD_FRONTEND_SOURCE="$PENDING_PAYLOAD_FRONTEND_SOURCE" \
  -DBW_WGPU_VERTEX_UPLOAD_FRONTEND_SOURCE="$VERTEX_UPLOAD_FRONTEND_SOURCE" \
  -DBW_WGPU_BUFFER_UPDATE_SOURCE="$BUFFER_UPDATE_SOURCE"
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" wgpu_buffer_integrated_smoke

if [ "${BW_PENDING_BIND_ONLY:-0}" = "1" ]; then
  echo "== [3/3] pending bind-intent native/Wasm parity =="
  PENDING_NATIVE_STDOUT="$OUT/pending-bind-native.stdout"
  PENDING_WASM_STDOUT="$OUT/pending-bind-wasm.stdout"
  "$NATIVE_BUILD/wgpu_buffer_integrated_test" --pending-buffer-payload-only \
    >"$PENDING_NATIVE_STDOUT"
  "$NODE" "$WASM_BUILD/integrated_buffer.js" --pending-buffer-payload-only \
    >"$PENDING_WASM_STDOUT"
  if ! cmp -s "$PENDING_NATIVE_STDOUT" "$PENDING_WASM_STDOUT"; then
    echo "ERROR: pending bind-intent native and Wasm evidence differs" >&2
    diff -u "$PENDING_NATIVE_STDOUT" "$PENDING_WASM_STDOUT" | head -n 40 >&2
    exit 1
  fi
  if ! grep -qx \
    'CONTRACT pending-buffer-payload PASS cases=6 creates=6 payloads=12 order=fifo retry=retained bind_intent=pending concurrent_drainer=one final=E3' \
    "$PENDING_NATIVE_STDOUT"
  then
    echo "ERROR: pending bind-intent PASS verdict missing" >&2
    exit 1
  fi
  echo "PASS pending-bind-intent native/wasm source_sha256=$SOURCE_PROOF"
  exit 0
fi

echo "== [3/3] exact native/Wasm parity =="
NATIVE_STDOUT="$OUT/native.stdout"
NATIVE_STDERR="$OUT/native.stderr"
WASM_STDOUT="$OUT/wasm.stdout"
WASM_STDERR="$OUT/wasm.stderr"
"$NATIVE_BUILD/wgpu_buffer_integrated_test" >"$NATIVE_STDOUT" 2>"$NATIVE_STDERR"
"$NODE" "$WASM_BUILD/integrated_buffer.js" >"$WASM_STDOUT" 2>"$WASM_STDERR"

if ! cmp -s "$NATIVE_STDERR" "$WASM_STDERR"; then
  echo "ERROR: native and Wasm integrated buffer stderr differs" >&2
  diff -u "$NATIVE_STDERR" "$WASM_STDERR" | head -n 40 >&2
  exit 1
fi
if [ "$(grep -Fc '[WebGPU] buffer sub-update rejected' "$NATIVE_STDERR")" -ne 1 ] ||
   [ "$(grep -Fc '[WebGPU] staged buffer creation rejected' "$NATIVE_STDERR")" -ne 1 ] ||
   [ "$(grep -Fc '[WebGPU] staged buffer sub-update submission rejected' \
       "$NATIVE_STDERR")" -ne 1 ] ||
   [ "$(wc -l <"$NATIVE_STDERR" | tr -d ' ')" -ne 3 ]
then
  echo "ERROR: integrated buffer rejection diagnostics differ" >&2
  exit 1
fi
for stdout_file in "$NATIVE_STDOUT" "$WASM_STDOUT"; do
  if ! grep -qx \
    'INTEGRATED_BUFFER_PASS contracts=20 usage_cases=32 pixel_cases=7 exact_cap=256 buffer_create_cases=6 pending_payload_cases=6 buffer_update_cases=13 index_cases=4 index_upload_cases=7 vertex_generation_cases=2' \
    "$stdout_file" ||
     ! grep -qx \
    'CONTRACT index-point-restart PASS cases=4 removed=9 survivors=9 order=stable' \
    "$stdout_file" ||
     ! grep -qx \
    'CONTRACT index-metadata PASS subranges=2 direct=u16@2+65536/u32@12+0 indirect=u16@0+65536/u32@0+0 device-u32=17' \
    "$stdout_file" ||
     ! grep -qx \
    'CONTRACT index-upload-commit PASS cases=7 creates=5 failure=retain pending=retain retry=commit bytes=6' \
    "$stdout_file" ||
     ! grep -qx \
    'CONTRACT persistent-buffer-publication PASS cases=6 creates=4 pending=deduplicated failure=retry readiness=one bytes=6 allocation=8' \
    "$stdout_file" ||
     ! grep -qx \
    'CONTRACT pending-buffer-payload PASS cases=6 creates=6 payloads=12 order=fifo retry=retained bind_intent=pending concurrent_drainer=one final=E3' \
    "$stdout_file" ||
     ! grep -qx \
    'CONTRACT buffer-staging-map PASS cases=13 large_bytes=65540 map_failure=reject error_object=blocked uncaptured=0 canceled=1 writes=validated submits=validated retry=owned' \
    "$stdout_file" ||
     ! grep -qx \
    'CONTRACT mapped-buffer-write PASS cases=4 copied=8 map_failure=reject' \
    "$stdout_file" ||
     ! grep -qx \
    'CONTRACT readback-command PASS cases=5 copies=4 submits=1 scopes=complete' \
    "$stdout_file" ||
     ! grep -qx \
    'CONTRACT vertex-upload-generation PASS cases=2 writes=5 order=A:B final=B' \
    "$stdout_file"
  then
    echo "ERROR: integrated buffer PASS verdict missing: $stdout_file" >&2
    exit 1
  fi
  if [ "$(grep -c '^CONTRACT .* PASS ' "$stdout_file")" -ne 20 ]; then
    echo "ERROR: integrated buffer evidence census differs: $stdout_file" >&2
    exit 1
  fi
done
if ! cmp -s "$NATIVE_STDOUT" "$WASM_STDOUT"; then
  echo "ERROR: native and Wasm integrated buffer evidence differs" >&2
  diff -u "$NATIVE_STDOUT" "$WASM_STDOUT" | head -n 40 >&2
  exit 1
fi

"$ROOT/scripts/ninja-locked.sh" -C "$NATIVE_BUILD" -n wgpu_buffer_integrated_test
"$ROOT/scripts/ninja-locked.sh" -C "$WASM_BUILD" -n wgpu_buffer_integrated_smoke

OUTPUT_BYTES="$(wc -c <"$WASM_STDOUT" | tr -d ' ')"
OUTPUT_SHA256="$(sha256_file "$WASM_STDOUT")"
SOURCE_SHA256="$(source_digest)"
echo "PASS integrated-buffer native/wasm bytes=$OUTPUT_BYTES sha256=$OUTPUT_SHA256 source_sha256=$SOURCE_SHA256 fmt_sha256=$FMT_SHA256 dawn=$DAWN_PIN emcc=$EMCC_VERSION node=$NODE_VERSION"
