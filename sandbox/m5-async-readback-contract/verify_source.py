#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail-closed source census for owned GPU and framebuffer readback continuations."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SOURCE_PATHS = (
    "source/blender/gpu/GPU_framebuffer.hh",
    "source/blender/gpu/GPU_readback.hh",
    "source/blender/gpu/GPU_select.hh",
    "source/blender/gpu/GPU_storage_buffer.hh",
    "source/blender/gpu/GPU_texture.hh",
    "source/blender/gpu/CMakeLists.txt",
    "source/blender/gpu/intern/gpu_framebuffer.cc",
    "source/blender/gpu/intern/gpu_framebuffer_private.hh",
    "source/blender/gpu/intern/gpu_readback.cc",
    "source/blender/gpu/intern/gpu_readback_private.hh",
    "source/blender/gpu/intern/gpu_select_next.cc",
    "source/blender/gpu/intern/gpu_storage_buffer.cc",
    "source/blender/gpu/intern/gpu_texture.cc",
    "source/blender/gpu/tests/readback_test.cc",
    "source/blender/gpu/webgpu/wgpu_framebuffer.cc",
    "source/blender/gpu/webgpu/wgpu_framebuffer.hh",
    "source/blender/gpu/webgpu/wgpu_storage_buffer.cc",
    "source/blender/gpu/webgpu/wgpu_texture.cc",
    "source/blender/gpu/webgpu/wgpu_texture.hh",
    "source/blender/draw/DRW_select_buffer.hh",
    "source/blender/draw/engines/select/select_instance.hh",
    "source/blender/draw/intern/draw_select_buffer.cc",
    "source/blender/editors/include/ED_view3d.hh",
    "source/blender/editors/mesh/editmesh_select.cc",
    "source/blender/editors/sculpt_paint/paint_intern.hh",
    "source/blender/editors/sculpt_paint/mesh/paint_image_proj.cc",
    "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc",
    "source/blender/editors/screen/screendump.cc",
    "source/blender/editors/space_view3d/view3d_draw.cc",
    "source/blender/editors/space_view3d/view3d_navigate.cc",
    "source/blender/editors/space_view3d/view3d_navigate.hh",
    "source/blender/editors/space_view3d/view3d_navigate_view_dolly.cc",
    "source/blender/editors/space_view3d/view3d_select.cc",
    "source/blender/editors/space_view3d/view3d_view.cc",
    "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
    "source/blender/editors/interface/eyedroppers/eyedropper_colorband.cc",
    "source/blender/editors/interface/eyedroppers/eyedropper_depth.cc",
    "source/blender/editors/interface/eyedroppers/eyedropper_grease_pencil_color.cc",
    "source/blender/editors/interface/eyedroppers/eyedropper_intern.hh",
    "source/blender/windowmanager/WM_api.hh",
    "source/blender/windowmanager/intern/wm_draw.cc",
)


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def require_once(text: str, needle: str, label: str) -> None:
    count = text.count(needle)
    require(count == 1, f"{label}: expected one occurrence, found {count}")


def require_ordered(text: str, needles: tuple[str, ...], label: str) -> None:
    offset = 0
    for needle in needles:
        found = text.find(needle, offset)
        require(found >= 0, f"{label}: missing ordered fragment {needle!r}")
        offset = found + len(needle)


def braced_definition(text: str, marker: str, label: str) -> str:
    require_once(text, marker, label)
    start = text.index(marker)
    brace = text.find("{", start + len(marker))
    require(brace >= 0, f"{label}: opening brace missing")
    depth = 0
    index = brace
    state = "code"
    quote = ""
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if state == "line_comment":
            if char == "\n":
                state = "code"
        elif state == "block_comment":
            if char == "*" and next_char == "/":
                state = "code"
                index += 1
        elif state == "string":
            if char == "\\":
                index += 1
            elif char == quote:
                state = "code"
        else:
            if char == "/" and next_char == "/":
                state = "line_comment"
                index += 1
            elif char == "/" and next_char == "*":
                state = "block_comment"
                index += 1
            elif char in ('"', "'"):
                state = "string"
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        index += 1
    raise VerificationError(f"{label}: unterminated definition")


def read_sources(source_root: Path) -> dict[str, str]:
    sources: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = source_root / relative
        require(path.is_file(), f"missing source: {relative}")
        sources[relative] = path.read_text(encoding="utf-8")
    return sources


def source_digest(sources: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for relative in SOURCE_PATHS:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sources[relative].encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def validate(sources: dict[str, str]) -> dict[str, object]:
    framebuffer_header = sources["source/blender/gpu/GPU_framebuffer.hh"]
    framebuffer_private = sources["source/blender/gpu/intern/gpu_framebuffer_private.hh"]
    framebuffer_frontend = sources["source/blender/gpu/intern/gpu_framebuffer.cc"]
    framebuffer_backend_header = sources["source/blender/gpu/webgpu/wgpu_framebuffer.hh"]
    framebuffer_backend = sources["source/blender/gpu/webgpu/wgpu_framebuffer.cc"]
    readback_header = sources["source/blender/gpu/GPU_readback.hh"]
    readback_private = sources["source/blender/gpu/intern/gpu_readback_private.hh"]
    readback_impl = sources["source/blender/gpu/intern/gpu_readback.cc"]
    texture_header = sources["source/blender/gpu/GPU_texture.hh"]
    storage_header = sources["source/blender/gpu/GPU_storage_buffer.hh"]
    texture_frontend = sources["source/blender/gpu/intern/gpu_texture.cc"]
    storage_frontend = sources["source/blender/gpu/intern/gpu_storage_buffer.cc"]
    texture_backend = sources["source/blender/gpu/webgpu/wgpu_texture.cc"]
    texture_backend_header = sources["source/blender/gpu/webgpu/wgpu_texture.hh"]
    storage_backend = sources["source/blender/gpu/webgpu/wgpu_storage_buffer.cc"]
    select_state = sources["source/blender/gpu/intern/gpu_select_next.cc"]
    select_api = sources["source/blender/gpu/GPU_select.hh"]
    select_buffer_api = sources["source/blender/draw/DRW_select_buffer.hh"]
    select_buffer = sources["source/blender/draw/intern/draw_select_buffer.cc"]
    select_engine = sources["source/blender/draw/engines/select/select_instance.hh"]
    depth_api = sources["source/blender/editors/include/ED_view3d.hh"]
    editmesh_select = sources["source/blender/editors/mesh/editmesh_select.cc"]
    paint_api = sources["source/blender/editors/sculpt_paint/paint_intern.hh"]
    paint_projection = sources[
        "source/blender/editors/sculpt_paint/mesh/paint_image_proj.cc"
    ]
    paint_operator = sources[
        "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc"
    ]
    view_select = sources["source/blender/editors/space_view3d/view3d_select.cc"]
    view_query = sources["source/blender/editors/space_view3d/view3d_view.cc"]
    view_navigate = sources["source/blender/editors/space_view3d/view3d_navigate.cc"]
    view_navigate_header = sources[
        "source/blender/editors/space_view3d/view3d_navigate.hh"
    ]
    view_dolly = sources[
        "source/blender/editors/space_view3d/view3d_navigate_view_dolly.cc"
    ]
    eyedropper = sources[
        "source/blender/editors/interface/eyedroppers/eyedropper_color.cc"
    ]
    colorband = sources[
        "source/blender/editors/interface/eyedroppers/eyedropper_colorband.cc"
    ]
    depth_eyedropper = sources[
        "source/blender/editors/interface/eyedroppers/eyedropper_depth.cc"
    ]
    grease_pencil = sources[
        "source/blender/editors/interface/eyedroppers/eyedropper_grease_pencil_color.cc"
    ]
    eyedropper_api = sources[
        "source/blender/editors/interface/eyedroppers/eyedropper_intern.hh"
    ]
    wm_api = sources["source/blender/windowmanager/WM_api.hh"]
    wm_draw = sources["source/blender/windowmanager/intern/wm_draw.cc"]

    for needle in (
        "GPU_READBACK_PENDING",
        "GPU_READBACK_READY",
        "GPU_READBACK_FAILED",
        "eGPUReadbackStatus GPU_readback_status(GPUReadback *readback);",
        "eGPUReadbackError GPU_readback_error(GPUReadback *readback);",
        "size_t GPU_readback_size(GPUReadback *readback);",
        "bool GPU_readback_consume(GPUReadback *&readback, void *dst, size_t dst_len);",
        "void GPU_readback_cancel(GPUReadback *&readback);",
    ):
        require(needle in readback_header, f"owned API missing {needle!r}")

    for needle in (
        "struct DRWSelectBufferReadback;",
        "DRWSelectBufferReadback *DRW_select_buffer_read_async(",
        "eGPUReadbackStatus DRW_select_buffer_read_async_status(",
        "eGPUReadbackError DRW_select_buffer_read_async_error(",
        "uint *DRW_select_buffer_read_async_consume(DRWSelectBufferReadback *&readback",
        "void DRW_select_buffer_read_async_cancel(DRWSelectBufferReadback *&readback);",
    ):
        require(needle in select_buffer_api, f"owned selection-buffer API missing {needle!r}")

    for needle in (
        "void DRW_select_buffer_query_session_begin();",
        "void DRW_select_buffer_query_session_end();",
        "bool DRW_select_buffer_query_session_is_active();",
        "bool DRW_select_buffer_query_session_needs_replay();",
        "eGPUReadbackStatus DRW_select_buffer_query_session_status();",
        "eGPUReadbackError DRW_select_buffer_query_session_error();",
        "uint DRW_select_buffer_sample_point_async(",
        "uint DRW_select_buffer_find_nearest_to_point_async(",
    ):
        require(needle in select_buffer_api, f"selection query API missing {needle!r}")

    for needle in (
        "void DRW_select_buffer_bitmap_session_begin();",
        "void DRW_select_buffer_bitmap_session_end();",
        "bool DRW_select_buffer_bitmap_session_is_active();",
        "bool DRW_select_buffer_bitmap_session_needs_replay();",
        "eGPUReadbackStatus DRW_select_buffer_bitmap_session_status();",
        "eGPUReadbackError DRW_select_buffer_bitmap_session_error();",
        "uint *DRW_select_buffer_bitmap_from_rect_async(",
        "uint *DRW_select_buffer_bitmap_from_circle_async(",
        "uint *DRW_select_buffer_bitmap_from_poly_async(",
    ):
        require(needle in select_buffer_api, f"selection bitmap API missing {needle!r}")

    selection_state = braced_definition(
        select_buffer, "struct DRWSelectBufferReadback", "selection readback state"
    )
    for needle in (
        "GPUReadback *gpu_readback = nullptr;",
        "rcti rect",
        "rcti rect_clamp",
        "uint buffer_len = 0;",
        "uint clamped_len = 0;",
        "eGPUReadbackStatus status = GPU_READBACK_PENDING;",
        "eGPUReadbackError error = GPU_READBACK_ERROR_NONE;",
    ):
        require(needle in selection_state, f"selection readback state missing {needle!r}")

    selection_begin = braced_definition(
        select_buffer,
        "DRWSelectBufferReadback *DRW_select_buffer_read_async(",
        "selection readback begin",
    )
    require_ordered(
        selection_begin,
        (
            "MEM_new<DRWSelectBufferReadback>",
            "BLI_rcti_isect(",
            "DRW_gpu_context_enable();",
            "select_ctx->is_dirty(depsgraph, rv3d)",
            "DRW_draw_select_id(depsgraph, region, v3d);",
            "GPU_framebuffer_read_color_async(",
            "GPU_framebuffer_restore();",
            "DRW_gpu_context_disable();",
        ),
        "selection readback begin",
    )

    selection_status = braced_definition(
        select_buffer,
        "eGPUReadbackStatus DRW_select_buffer_read_async_status(",
        "selection readback status",
    )
    require_ordered(
        selection_status,
        (
            "readback == nullptr",
            "readback->status != GPU_READBACK_PENDING",
            "GPU_readback_status(readback->gpu_readback)",
            "status == GPU_READBACK_PENDING",
            "status != GPU_READBACK_READY",
            "GPU_readback_error(readback->gpu_readback)",
            "GPU_readback_size(readback->gpu_readback) != expected_size",
            "GPU_READBACK_ERROR_BACKEND_FAILURE",
            "readback->status = GPU_READBACK_READY;",
        ),
        "selection readback status",
    )

    selection_consume = braced_definition(
        select_buffer,
        "uint *DRW_select_buffer_read_async_consume(",
        "selection readback consume",
    )
    require_ordered(
        selection_consume,
        (
            "DRW_select_buffer_read_async_status(readback) != GPU_READBACK_READY",
            "readback->buffer_len == 0",
            "MEM_new_array_uninitialized<uint>",
            "GPU_readback_consume(readback->gpu_readback",
            "GPU_select_buffer_stride_realign(&readback->rect, &readback->rect_clamp, buffer);",
            "MEM_delete(readback);",
            "readback = nullptr;",
        ),
        "selection readback consume",
    )

    selection_cancel = braced_definition(
        select_buffer,
        "void DRW_select_buffer_read_async_cancel(",
        "selection readback cancel",
    )

    query_state = braced_definition(
        select_buffer,
        "struct DRWSelectBufferQueryState",
        "selection query state",
    )
    for needle in (
        "bool session_active = false;",
        "bool failed = false;",
        "bool replay_required = false;",
        "DRWSelectBufferReadback *pending = nullptr;",
        "DRWSelectBufferQueryKey pending_key;",
        "DRWSelectBufferQueryContext pending_context;",
        "Vector<DRWSelectBufferQueryResult> results;",
    ):
        require(needle in query_state, f"selection query state missing {needle!r}")

    query_status = braced_definition(
        select_buffer,
        "eGPUReadbackStatus DRW_select_buffer_query_session_status()",
        "selection query poll",
    )
    require_ordered(
        query_status,
        (
            "if (!g_select_buffer_query.session_active)",
            "if (g_select_buffer_query.failed)",
            "DRW_select_buffer_read_async_status(g_select_buffer_query.pending)",
            "if (status == GPU_READBACK_PENDING)",
            "DRW_select_buffer_read_async_consume(g_select_buffer_query.pending",
            "drw_select_buffer_query_result_from_buffer",
            "result.context = std::move(g_select_buffer_query.pending_context);",
            "g_select_buffer_query.results.append(std::move(result));",
        ),
        "selection query poll",
    )

    query_replay = braced_definition(
        select_buffer,
        "static bool drw_select_buffer_query_replay(",
        "selection query replay",
    )
    for needle in (
        "drw_select_buffer_query_key_equal(result.key, key)",
        "drw_select_buffer_query_context_restore(result.context);",
        "*r_index = result.index;",
        "*r_distance = result.distance;",
        "g_select_buffer_query.replay_required = false;",
    ):
        require(needle in query_replay, f"selection query replay missing {needle!r}")

    query_begin = braced_definition(
        select_buffer,
        "static uint drw_select_buffer_query(",
        "selection query begin/replay",
    )
    require_ordered(
        query_begin,
        (
            "DRW_select_buffer_query_session_status()",
            "drw_select_buffer_query_replay(key, &index, r_distance)",
            "g_select_buffer_query.pending != nullptr",
            "drw_select_buffer_query_key_equal(g_select_buffer_query.pending_key, key)",
            "g_select_buffer_query.replay_required = true;",
            "DRW_select_buffer_read_async(depsgraph, region, v3d, &key.rect);",
            "drw_select_buffer_query_context_capture()",
            "DRW_select_buffer_query_session_status()",
        ),
        "selection query begin/replay",
    )
    require(
        "g_select_buffer_query.replay_required = true;\n"
        "  g_select_buffer_query.pending_key = key;" in query_begin,
        "selection query kick does not latch required replay",
    )

    sample_async = braced_definition(
        select_buffer,
        "uint DRW_select_buffer_sample_point_async(",
        "selection sample async",
    )
    for needle in (
        "DRWSelectBufferQueryKind::Sample",
        "rect.xmax = center[0] + 1;",
        "rect.ymax = center[1] + 1;",
        "drw_select_buffer_query(",
    ):
        require(needle in sample_async, f"selection sample async missing {needle!r}")

    nearest_async = braced_definition(
        select_buffer,
        "uint DRW_select_buffer_find_nearest_to_point_async(",
        "selection nearest async",
    )
    for needle in (
        "DRWSelectBufferQueryKind::Nearest",
        "BLI_rcti_init_pt_radius(&rect, center, *dist);",
        "key.initial_distance = *dist;",
        "drw_select_buffer_query(",
    ):
        require(needle in nearest_async, f"selection nearest async missing {needle!r}")
    require_ordered(
        selection_cancel,
        (
            "GPU_readback_cancel(readback->gpu_readback);",
            "MEM_delete(readback);",
            "readback = nullptr;",
        ),
        "selection readback cancel",
    )
    for needle in (
        "virtual ~GPUReadback() = default;",
        "virtual eGPUReadbackStatus status() = 0;",
        "virtual eGPUReadbackError error() = 0;",
        "virtual size_t size() = 0;",
        "virtual bool consume(void *dst, size_t dst_len) = 0;",
        "gpu_readback_create_ready",
        "gpu_readback_create_failed",
        "gpu_readback_create_transform",
        "GPUReadbackTransform transform",
    ):
        require(needle in readback_private, f"owned result interface missing {needle!r}")

    transform_body = braced_definition(
        readback_impl,
        "GPUReadback *gpu_readback_create_transform(",
        "owned transform factory",
    )
    require_ordered(
        transform_body,
        (
            "source == nullptr || !transform",
            "GPU_readback_cancel(source);",
            "gpu_readback_create_failed(GPU_READBACK_ERROR_INVALID_ARGUMENT",
            "MEM_new<TransformReadback>",
        ),
        "owned transform factory",
    )
    for needle in (
        "GPU_readback_status(source_)",
        "GPU_readback_size(source_) != source_size_",
        "GPU_readback_consume(source_, source_bytes.data(), source_bytes.size())",
        "transform_(source_bytes.data()",
        "GPU_readback_cancel(source_);",
    ):
        require(needle in readback_impl, f"owned transform missing {needle!r}")

    for needle in (
        "GPUReadback *GPU_framebuffer_read_depth_async(",
        "GPUReadback *GPU_framebuffer_read_color_async(",
    ):
        require(needle in framebuffer_header, f"framebuffer async API missing {needle!r}")
        require(needle in framebuffer_frontend, f"framebuffer async frontend missing {needle!r}")
    for needle in (
        "virtual GPUReadback *read_async(GPUFrameBufferBits planes",
        "GPUReadback *FrameBuffer::read_async(",
        "return fb->read_async(GPU_DEPTH_BIT, format, rect, 1, 1);",
        "return fb->read_async(GPU_COLOR_BIT, format, rect, channels, slot);",
    ):
        require(
            needle in framebuffer_private or needle in framebuffer_frontend,
            f"framebuffer owned path missing {needle!r}",
        )
    for needle in (
        "GPUReadback *read_async(GPUFrameBufferBits planes",
        "GPUReadback *WGPUFrameBuffer::read_async(",
        "plan.texture->read_sub_async(plan.mip, plan.layer, plan.format)",
        "gpu_readback_create_transform(",
        "return extract_read_result(layout",
    ):
        require(
            needle in framebuffer_backend_header or needle in framebuffer_backend,
            f"WebGPU framebuffer owned path missing {needle!r}",
        )
    require(
        "GPUReadback *read_sub_async(int mip, int layer, eGPUDataFormat format);"
        in texture_backend_header,
        "WebGPU texture subresource async API missing",
    )
    require_ordered(
        braced_definition(
            texture_backend,
            "GPUReadback *WGPUTexture::read_async(",
            "WebGPU texture async delegate",
        ),
        ("return read_sub_async(mip, -1, format);",),
        "WebGPU texture async delegate",
    )
    for needle in (
        "GPUReadback *WGPUTexture::read_sub_async(",
        "resolve_read_region(mip, layer, resolved)",
        "readback::RequestMode::Exact",
    ):
        require(needle in texture_backend, f"WebGPU subresource ticket missing {needle!r}")

    consume_body = braced_definition(
        readback_impl, "bool GPU_readback_consume(", "owned consume"
    )
    require_ordered(
        consume_body,
        (
            "readback == nullptr || !readback->consume(dst, dst_len)",
            "MEM_delete(readback);",
            "readback = nullptr;",
            "return true;",
        ),
        "owned consume",
    )
    cancel_body = braced_definition(
        readback_impl, "void GPU_readback_cancel(", "owned cancel"
    )
    require_ordered(
        cancel_body,
        ("if (readback != nullptr)", "MEM_delete(readback);", "readback = nullptr;"),
        "owned cancel",
    )

    require(
        "GPUReadback *GPU_texture_read_async(gpu::Texture *texture" in texture_header,
        "texture async API declaration missing",
    )
    require(
        "GPUReadback *GPU_storagebuf_read_async(gpu::StorageBuf *ssbo);" in storage_header,
        "storage async API declaration missing",
    )
    texture_frontend_body = braced_definition(
        texture_frontend, "GPUReadback *GPU_texture_read_async(", "texture frontend"
    )
    for needle in (
        "texture == nullptr",
        "GPU_TEXTURE_USAGE_HOST_READ",
        "mip_level < 0",
        "!validate_data_format",
        "GPU_READBACK_ERROR_UNSUPPORTED_FORMAT",
        "return texture->read_async(mip_level, data_format);",
    ):
        require(needle in texture_frontend_body, f"texture frontend missing {needle!r}")
    storage_frontend_body = braced_definition(
        storage_frontend, "GPUReadback *GPU_storagebuf_read_async(", "storage frontend"
    )
    require_ordered(
        storage_frontend_body,
        (
            "if (ssbo == nullptr)",
            "GPU_READBACK_ERROR_INVALID_ARGUMENT",
            "return ssbo->read_async();",
        ),
        "storage frontend",
    )

    texture_backend_body = braced_definition(
        texture_backend, "GPUReadback *WGPUTexture::read_sub_async(", "texture backend"
    )
    for needle in (
        "#ifndef __EMSCRIPTEN__",
        "if (layer < 0)",
        "return Texture::read_async(mip, format);",
        "resolve_read_region(mip, layer, resolved)",
        "readback::RequestMode::Exact",
        "ticket == readback::kInvalidTicket",
        "GPU_READBACK_ERROR_CAPACITY_EXCEEDED",
        "MEM_new<WGPUTextureReadback>",
    ):
        require(needle in texture_backend_body, f"texture backend missing {needle!r}")
    storage_backend_body = braced_definition(
        storage_backend,
        "GPUReadback *WGPUStorageBuffer::read_async(",
        "storage backend",
    )
    for needle in (
        "#ifndef __EMSCRIPTEN__",
        "return StorageBuf::read_async();",
        "readback::RequestMode::Exact",
        "ticket == webgpu::readback::kInvalidTicket",
        "GPU_READBACK_ERROR_CAPACITY_EXCEEDED",
        "MEM_new<WGPUStorageBufferReadback>",
    ):
        require(needle in storage_backend_body, f"storage backend missing {needle!r}")

    for needle in (
        "constexpr int GPU_SELECT_ASYNC_PENDING = -2;",
        "void GPU_select_async_session_begin();",
        "eGPUReadbackStatus GPU_select_async_status();",
        "bool GPU_select_async_result_replay(",
    ):
        require(needle in select_api, f"select continuation API missing {needle!r}")
    begin_body = braced_definition(
        select_state,
        "void gpu_select_next_async_readback_begin(",
        "select readback transfer",
    )
    require_ordered(
        begin_body,
        (
            "if (!g_async.session_active)",
            "if (readback == nullptr || g_async.readback != nullptr || g_async.failed)",
            "g_async.pending_key = gpu_select_async_key_from_state();",
            "g_async.select_id_map.extend(select_id_map);",
            "g_async.in_front_map.extend(in_front_map);",
            "g_async.readback = readback;",
        ),
        "select readback transfer",
    )
    status_body = braced_definition(
        select_state, "eGPUReadbackStatus GPU_select_async_status()", "select poll"
    )
    require_ordered(
        status_body,
        (
            "if (status == GPU_READBACK_PENDING)",
            "if (status != GPU_READBACK_READY)",
            "byte_size % sizeof(uint) != 0",
            "GPU_readback_consume(g_async.readback, raw.data(), byte_size)",
            "gpu_select_async_convert",
            "g_async.results.append(std::move(result));",
            "g_async.select_id_map.clear();",
            "g_async.in_front_map.clear();",
        ),
        "select poll",
    )
    replay_body = braced_definition(
        select_state,
        "bool GPU_select_async_result_replay(",
        "select exact-key replay",
    )
    for needle in (
        "GPU_select_async_status() != GPU_READBACK_READY",
        "const GPUSelectAsyncKey key = gpu_select_async_key_create",
        "if (result.key == key)",
        "buffer->storage.extend(result.hits.as_span());",
        "*r_hits = int(result.hits.size());",
    ):
        require(needle in replay_body, f"select replay missing {needle!r}")

    engine_body = braced_definition(select_engine, "void read_result()", "select engine")
    require_ordered(
        engine_body,
        (
            "#ifdef __EMSCRIPTEN__",
            "select_output_buf.read_async()",
            "select_id_map.as_span()",
            "in_front_map.as_span()",
            "return;",
            "#else",
            "select_output_buf.read();",
        ),
        "select engine",
    )
    query_body = braced_definition(view_query, "int view3d_gpu_select_ex(", "view select query")
    require_ordered(
        query_body,
        (
            "#ifdef __EMSCRIPTEN__",
            "GPU_select_async_session_is_active()",
            "GPU_select_async_result_replay(buffer",
            "return hits;",
            "#endif",
        ),
        "view select query",
    )

    editmesh_sample = braced_definition(
        editmesh_select,
        "static uint edbm_select_buffer_sample_point(",
        "edit-mesh sample dispatch",
    )
    require_ordered(
        editmesh_sample,
        (
            "#ifdef __EMSCRIPTEN__",
            "DRW_select_buffer_query_session_is_active()",
            "DRW_select_buffer_sample_point_async(",
            "#endif",
            "DRW_select_buffer_sample_point(",
        ),
        "edit-mesh sample dispatch",
    )
    editmesh_nearest = braced_definition(
        editmesh_select,
        "static uint edbm_select_buffer_find_nearest_to_point(",
        "edit-mesh nearest dispatch",
    )
    require_ordered(
        editmesh_nearest,
        (
            "#ifdef __EMSCRIPTEN__",
            "DRW_select_buffer_query_session_is_active()",
            "DRW_select_buffer_find_nearest_to_point_async(",
            "#endif",
            "DRW_select_buffer_find_nearest_to_point(",
        ),
        "edit-mesh nearest dispatch",
    )
    require(
        editmesh_select.count("edbm_select_buffer_find_nearest_to_point(") == 4,
        "edit-mesh nearest dispatch/caller census differs",
    )
    require(
        editmesh_select.count("edbm_select_buffer_sample_point(") == 2,
        "edit-mesh sample dispatch/caller census differs",
    )
    editmesh_pick = braced_definition(
        editmesh_select, "bool EDBM_select_pick(", "edit-mesh pick"
    )
    require_ordered(
        editmesh_pick,
        (
            "unified_findnearest(&vc, bases",
            "edbm_select_buffer_query_pending_or_failed()",
            "return false;",
            "if (params.sel_op == SEL_OP_SET)",
        ),
        "edit-mesh pending-before-mutation",
    )
    require(
        editmesh_select.count("if (edbm_select_buffer_query_pending_or_failed())") >= 4,
        "edit-mesh query stages do not stop on pending/failure",
    )
    pending_guard = braced_definition(
        editmesh_select,
        "static bool edbm_select_buffer_query_pending_or_failed()",
        "edit-mesh query guard",
    )
    require_ordered(
        pending_guard,
        (
            "DRW_select_buffer_query_session_status()",
            "GPU_READBACK_PENDING",
            "GPU_READBACK_FAILED",
            "DRW_select_buffer_query_session_needs_replay()",
        ),
        "edit-mesh query guard",
    )

    combined_status = braced_definition(
        view_select,
        "static eGPUReadbackStatus view3d_select_async_status()",
        "combined select status",
    )
    for needle in (
        "GPU_select_async_status()",
        "DRW_select_buffer_query_session_status()",
        "GPU_READBACK_FAILED",
        "GPU_READBACK_PENDING",
        "GPU_READBACK_READY",
    ):
        require(needle in combined_status, f"combined select status missing {needle!r}")
    combined_error = braced_definition(
        view_select,
        "static eGPUReadbackError view3d_select_async_error()",
        "combined select error",
    )
    for needle in (
        "GPU_select_async_error()",
        "DRW_select_buffer_query_session_error()",
    ):
        require(needle in combined_error, f"combined select error missing {needle!r}")

    exec_body = braced_definition(
        view_select, "static wmOperatorStatus view3d_select_exec(", "select exec"
    )
    for needle in (
        "view3d_select_async_status();",
        "if (status == GPU_READBACK_PENDING)",
        "return OPERATOR_RUNNING_MODAL;",
        "if (status == GPU_READBACK_FAILED)",
        "view3d_select_async_error()",
        "return OPERATOR_CANCELLED;",
    ):
        require(needle in exec_body, f"select exec missing {needle!r}")
    invoke_body = braced_definition(
        view_select, "static wmOperatorStatus view3d_select_invoke(", "select invoke"
    )
    require_ordered(
        invoke_body,
        (
            "GPU_select_async_session_begin();",
            "DRW_select_buffer_query_session_begin();",
            "view3d_select_exec(C, op);",
            "if (retval == OPERATOR_RUNNING_MODAL)",
            "WM_event_timer_add(",
            "WM_event_add_modal_handler(C, op);",
        ),
        "select invoke",
    )
    modal_body = braced_definition(
        view_select, "static wmOperatorStatus view3d_select_modal(", "select modal"
    )
    for needle in (
        "constexpr int max_tick_count = 240;",
        "view3d_select_async_status();",
        "if (status == GPU_READBACK_PENDING)",
        "view3d_select_exec(C, op);",
        "view3d_select_async_finish(C, op);",
    ):
        require(needle in modal_body, f"select modal missing {needle!r}")
    cancel_body = braced_definition(
        view_select, "static void view3d_select_cancel(", "select cancel"
    )
    require(
        "view3d_select_async_finish(C, op);" in cancel_body,
        "select cancel does not release continuation",
    )
    finish_body = braced_definition(
        view_select,
        "static void view3d_select_async_finish(",
        "select async finish",
    )
    require_ordered(
        finish_body,
        (
            "DRW_select_buffer_query_session_end();",
            "GPU_select_async_session_end();",
        ),
        "select async finish",
    )

    bitmap_state = braced_definition(
        select_buffer, "struct DRWSelectBufferBitmapState", "selection bitmap state"
    )
    for needle in (
        "bool session_active = false;",
        "bool failed = false;",
        "bool replay_required = false;",
        "bool settled = false;",
        "bool result_ready = false;",
        "DRWSelectBufferReadback *pending = nullptr;",
        "DRWSelectBufferBitmapKey pending_key;",
        "DRWSelectBufferQueryContext pending_context;",
        "DRWSelectBufferBitmapResult result;",
    ):
        require(needle in bitmap_state, f"selection bitmap state missing {needle!r}")
    bitmap_transform = braced_definition(
        select_buffer,
        "static bool drw_select_buffer_bitmap_from_ids(",
        "selection bitmap transform",
    )
    for needle in (
        "buf_len != expected_len",
        "context.max_index_drawn_len - 1",
        "DRWSelectBufferBitmapKind::Rect",
        "const uint index = id - 1;",
        "diameter * diameter != int64_t(buf_len)",
        "x * x + y * y < radius_sq",
        "BLI_bitmap_draw_2d_poly_v2i_n(",
        "BLI_BITMAP_TEST(buf_mask, i)",
    ):
        require(needle in bitmap_transform, f"selection bitmap transform missing {needle!r}")
    bitmap_status = braced_definition(
        select_buffer,
        "eGPUReadbackStatus DRW_select_buffer_bitmap_session_status()",
        "selection bitmap poll",
    )
    require_ordered(
        bitmap_status,
        (
            "DRW_select_buffer_read_async_status(g_select_buffer_bitmap.pending)",
            "if (status == GPU_READBACK_PENDING)",
            "if (status != GPU_READBACK_READY)",
            "DRW_select_buffer_read_async_consume(g_select_buffer_bitmap.pending",
            "drw_select_buffer_bitmap_from_ids(",
            "g_select_buffer_bitmap.result = std::move(result);",
            "g_select_buffer_bitmap.result_ready = true;",
        ),
        "selection bitmap poll",
    )
    bitmap_query = braced_definition(
        select_buffer,
        "static uint *drw_select_buffer_bitmap_query(",
        "selection bitmap query",
    )
    require_ordered(
        bitmap_query,
        (
            "drw_select_buffer_bitmap_key_equal(g_select_buffer_bitmap.result.key, key)",
            "drw_select_buffer_query_context_restore(g_select_buffer_bitmap.result.context);",
            "g_select_buffer_bitmap.replay_required = false;",
            "g_select_buffer_bitmap.settled = true;",
            "drw_select_buffer_bitmap_key_equal(g_select_buffer_bitmap.pending_key, key)",
            "g_select_buffer_bitmap.replay_required = true;",
            "DRW_select_buffer_read_async(",
            "drw_select_buffer_query_context_capture();",
        ),
        "selection bitmap query",
    )
    require(
        "  g_select_buffer_bitmap.replay_required = true;\n"
        "  g_select_buffer_bitmap.pending_key = key;" in bitmap_query,
        "selection bitmap initial request lacks replay latch",
    )
    bitmap_end = braced_definition(
        select_buffer,
        "void DRW_select_buffer_bitmap_session_end()",
        "selection bitmap end",
    )
    require_ordered(
        bitmap_end,
        (
            "DRW_select_buffer_read_async_cancel(g_select_buffer_bitmap.pending);",
            "MEM_SAFE_DELETE(g_select_buffer_bitmap.result.bitmap);",
            "g_select_buffer_bitmap = {};",
        ),
        "selection bitmap end",
    )

    for helper_marker, async_call in (
        (
            "static bool editselect_buf_cache_bitmap_from_rect(",
            "DRW_select_buffer_bitmap_from_rect_async(",
        ),
        (
            "static bool editselect_buf_cache_bitmap_from_circle(",
            "DRW_select_buffer_bitmap_from_circle_async(",
        ),
        (
            "static bool editselect_buf_cache_bitmap_from_poly(",
            "DRW_select_buffer_bitmap_from_poly_async(",
        ),
    ):
        helper = braced_definition(view_select, helper_marker, helper_marker)
        require_ordered(
            helper,
            (
                "if (esel->select_bitmap_settled)",
                "DRW_select_buffer_bitmap_session_is_active()",
                async_call,
                "DRW_select_buffer_bitmap_session_status() == GPU_READBACK_READY",
                "!DRW_select_buffer_bitmap_session_needs_replay()",
            ),
            helper_marker,
        )

    for function_marker, helper_marker in (
        ("static bool do_lasso_select_mesh(", "editselect_buf_cache_bitmap_from_poly("),
        ("static bool do_mesh_box_select(", "editselect_buf_cache_bitmap_from_rect("),
        ("static bool mesh_circle_select(", "editselect_buf_cache_bitmap_from_circle("),
    ):
        function = braced_definition(view_select, function_marker, function_marker)
        require_ordered(
            function,
            (
                helper_marker,
                "return false;",
                "if (SEL_OP_USE_PRE_DESELECT(sel_op))",
            ),
            f"{function_marker} pending-before-mutation",
        )

    for kind in ("lasso", "box"):
        invoke = braced_definition(
            view_select,
            f"static wmOperatorStatus view3d_{kind}_select_invoke(",
            f"{kind} invoke",
        )
        require_ordered(
            invoke,
            (
                "view3d_gesture_bitmap_async_eligible(C)",
                "DRW_select_buffer_bitmap_session_begin();",
                f"WM_gesture_{kind}_invoke(C, op, event)",
            ),
            f"{kind} invoke",
        )
        modal = braced_definition(
            view_select,
            f"static wmOperatorStatus view3d_{kind}_select_modal(",
            f"{kind} modal",
        )
        for needle in (
            "DRW_select_buffer_bitmap_session_status() != GPU_READBACK_INVALID",
            "view3d_gesture_bitmap_async_modal(",
            f"WM_gesture_{kind}_modal(C, op, event)",
            "view3d_gesture_bitmap_async_after_gesture(",
        ):
            require(needle in modal, f"{kind} modal missing {needle!r}")

    gesture_poll = braced_definition(
        view_select,
        "static wmOperatorStatus view3d_gesture_bitmap_async_modal(",
        "gesture bitmap poll",
    )
    for needle in (
        "constexpr int max_tick_count = 240;",
        "DRW_select_buffer_bitmap_session_status();",
        "DRW_select_buffer_bitmap_session_needs_replay()",
        "const wmOperatorStatus result = exec(C, op);",
        "view3d_gesture_bitmap_async_data_end(C, op);",
    ):
        require(needle in gesture_poll, f"gesture bitmap poll missing {needle!r}")

    circle_modal = braced_definition(
        view_select,
        "static wmOperatorStatus view3d_circle_select_modal(",
        "circle modal",
    )
    for needle in (
        "constexpr int max_tick_count = 240;",
        "view3d_circle_select_async_event_push(esel, event)",
        "view3d_circle_select_exec(C, op);",
        "while (!esel->async_events.is_empty())",
        "WM_gesture_circle_modal(C, op, &queued)",
        "DRW_select_buffer_bitmap_session_end();",
        "DRW_select_buffer_bitmap_session_begin();",
    ):
        require(needle in circle_modal, f"circle modal missing {needle!r}")
    circle_queue = braced_definition(
        view_select,
        "static bool view3d_circle_select_async_event_push(",
        "circle event queue",
    )
    for needle in (
        "constexpr int max_queued_events = 512;",
        "esel->async_events.size() >= max_queued_events",
        "queued.customdata = nullptr;",
        "esel->async_events.append(queued);",
    ):
        require(needle in circle_queue, f"circle event queue missing {needle!r}")
    circle_exec = braced_definition(
        view_select,
        "static wmOperatorStatus view3d_circle_select_exec(bContext *C",
        "circle exec",
    )
    require_ordered(
        circle_exec,
        (
            "DRW_select_buffer_bitmap_session_needs_replay()",
            "async_esel->async_input_valid",
            "sel_op = async_esel->async_sel_op;",
            "copy_v2_v2_int(mval, async_esel->async_mval);",
            "radius = int(async_esel->async_radius);",
            "view3d_gesture_bitmap_async_waiting()",
            "esel->async_input_valid = true;",
            "editselect_buf_cache_bitmap_clear(esel);",
        ),
        "circle exact-input replay",
    )
    for needle in (
        "ot->invoke = view3d_lasso_select_invoke;",
        "ot->modal = view3d_lasso_select_modal;",
        "ot->cancel = view3d_lasso_select_cancel;",
        "ot->invoke = view3d_box_select_invoke;",
        "ot->modal = view3d_box_select_modal;",
        "ot->cancel = view3d_box_select_cancel;",
        "ot->invoke = view3d_circle_select_invoke;",
        "ot->modal = view3d_circle_select_modal;",
        "ot->cancel = view3d_circle_select_cancel;",
    ):
        require(needle in view_select, f"gesture callback wiring missing {needle!r}")

    cmake_text = sources["source/blender/gpu/CMakeLists.txt"]
    require_ordered(
        cmake_text,
        ("if(WITH_GPU_BACKEND_TESTS)", "tests/readback_test.cc"),
        "readback test registration",
    )
    readback_test = sources["source/blender/gpu/tests/readback_test.cc"]
    for needle in (
        "GPU_TEST(texture_readback_owned_result)",
        "GPU_TEST(framebuffer_readback_owned_region)",
        "GPU_TEST(storage_buffer_readback_owned_result)",
        "GPU_TEST(select_next_async_replay)",
        "GPU_framebuffer_read_color_async(",
        "EXPECT_EQ(GPU_select_async_status(), GPU_READBACK_PENDING);",
    ):
        require(needle in readback_test, f"integrated test missing {needle!r}")

    remaining_sync = {
        "depth_pick": (
            "source/blender/editors/space_view3d/view3d_draw.cc",
            "GPU_framebuffer_read_depth(depth_read_fb",
        ),
        "depth_cache": (
            "source/blender/editors/space_view3d/view3d_draw.cc",
            "GPU_texture_read(depth_tx, GPU_DATA_FLOAT, 0)",
        ),
        "window_capture": (
            "source/blender/windowmanager/intern/wm_draw.cc",
            "GPU_offscreen_read_color(offscreen, GPU_DATA_UBYTE, rect);",
        ),
    }
    for family, (relative, needle) in remaining_sync.items():
        require(needle in sources[relative], f"remaining sync census drifted: {family}")
    require(
        "GPU_framebuffer_read_color(select_id_fb" in select_buffer,
        "native synchronous selection-buffer fallback missing",
    )
    require(
        "WM_window_pixels_read_async(C, win)" in sources[
            "source/blender/editors/screen/screendump.cc"
        ],
        "screenshot async continuation missing",
    )
    for needle in (
        "class EyedropperWindowColorSampleSession",
        "WMWindowPixelsRead *readback_ = nullptr;",
        "ReadbackState state();",
        "bool sample(const int pos[2], float r_col[3]);",
        "EyedropperWindowColorSampleSession *window_session",
    ):
        require(needle in eyedropper_api, f"shared window session API missing {needle!r}")
    for needle in (
        "WM_window_pixels_read_async(C, window)",
        "WM_window_pixels_read_async_status(readback_)",
        "WM_window_pixels_read_async_consume(readback_, size_)",
        "WM_window_pixels_read_async_cancel(readback_);",
        "float(pixel[0]) / 255.0f",
        "EyedropperReadbackSource::Window",
        "constexpr int max_tick_count = 240;",
    ):
        require(needle in eyedropper, f"window sample continuation missing {needle!r}")
    for caller, label in (
        (colorband, "colorband"),
        (grease_pencil, "grease pencil"),
    ):
        for needle in (
            "EyedropperWindowColorSampleSession window_session;",
            "&eye->window_session",
            "constexpr int max_tick_count = 240;",
            "WM_event_timer_add(",
            "eye->window_session.cancel();",
        ):
            require(needle in caller, f"{label} window continuation missing {needle!r}")
    require(
        "WM_window_pixels_read_sample_from_offscreen(C, win, event_xy_win, r_col)"
        not in eyedropper,
        "eyedropper retains synchronous offscreen fallback",
    )
    for needle in (
        "enum class DepthDropperReadbackAction",
        "ViewportDepthPickSession readback_session;",
        "depthdropper_readback_context_matches(C, ddr)",
        "ddr->readback_session.init(region, mval)",
        "ddr->readback_session.sample(ddr->readback_region, co)",
        "ddr->readback_confirm_after = true;",
        "constexpr int max_tick_count = 240;",
    ):
        require(needle in depth_eyedropper, f"depth eyedropper continuation missing {needle!r}")
    require(
        "ED_view3d_autodist(" not in depth_eyedropper and
        "GPU_framebuffer_read_depth(" not in depth_eyedropper,
        "depth eyedropper retains synchronous viewport readback",
    )
    for needle in (
        "enum class ViewOpsDataInitResult",
        "ViewOpsDepthRead *depth_read = nullptr;",
        "const bool allow_async_depth = false);",
    ):
        require(needle in view_navigate_header, f"navigation continuation API missing {needle!r}")
    navigation_pivot = braced_definition(
        view_navigate,
        "static eViewOpsFlag navigate_pivot_get(",
        "ordinary navigation depth kick",
    )
    require_ordered(
        navigation_pivot,
        (
            "allow_async_depth && event != nullptr && event->customdata == nullptr",
            "ViewportDepthPickSession::ReadbackState::Pending",
            "WM_event_timer_add(CTX_wm_manager(C), win, TIMER, 0.01f);",
            "*r_pending = true;",
            "ViewportDepthPickSession::ReadbackState::Ready",
            "read->session.sample(region, r_pivot)",
            "navigate_pivot_fallback(region, v3d, read, r_pivot);",
            "ED_view3d_autodist(",
        ),
        "async ordinary navigation before pinned direct fallback",
    )
    navigation_init = braced_definition(
        view_navigate,
        "ViewOpsDataInitResult ViewOpsData::init_navigation(bContext *C,",
        "ordinary navigation initialization barrier",
    )
    require_ordered(
        navigation_init,
        (
            "const bool resume_async_depth =",
            "if (!resume_async_depth)",
            "this->state_backup();",
            "navigate_pivot_get(",
            "if (pivot_pending)",
            "return ViewOpsDataInitResult::PendingDepth;",
            "rv3d->rflag |= RV3D_NAVIGATING;",
            "return ViewOpsDataInitResult::Ready;",
        ),
        "single stock initialization continuation",
    )
    navigation_modal = braced_definition(
        view_navigate,
        "static wmOperatorStatus view3d_navigation_depth_modal(",
        "ordinary navigation modal continuation",
    )
    require_ordered(
        navigation_modal,
        (
            "view3d_navigation_depth_context_matches(C, vod, read)",
            "read->queued_event = *event;",
            "constexpr int max_tick_count = 240;",
            "read->session.state();",
            "read->session.sample(vod->region, pivot)",
            "read->resolved = true;",
            "vod->init_navigation(",
            "view3d_navigate_modal_fn(C, op, &queued_event)",
        ),
        "bounded navigation settle and replay",
    )
    navigation_utility = braced_definition(
        view_navigate,
        "bool ED_view3d_navigation_do(bContext *C,",
        "embedded navigation utility",
    )
    require(
        "depth_loc_override, false" in navigation_utility,
        "embedded navigation utility can start an unowned depth continuation",
    )
    dolly_invoke = braced_definition(
        view_dolly,
        "static wmOperatorStatus viewdolly_invoke(bContext *C,",
        "direct dolly invoke",
    )
    require_ordered(
        dolly_invoke,
        (
            "viewdolly_offset_lock_check(C, op)",
            "view3d_navigate_invoke_impl(C, op, event, &ViewOpsType_dolly)",
        ),
        "direct dolly owned invoke",
    )
    dolly_modal = braced_definition(
        view_dolly,
        "static wmOperatorStatus viewdolly_modal(bContext *C,",
        "direct dolly modal",
    )
    require_ordered(
        dolly_modal,
        (
            "vod != nullptr && vod->depth_read != nullptr",
            "view3d_navigate_modal_fn(C, op, event)",
            "viewdolly_modal_apply(C, vod, event_code, event->xy)",
        ),
        "direct dolly pending dispatch",
    )
    require(
        "viewops_data_create(" not in view_dolly and
        "/*init_fn*/ viewdolly_invoke_impl," in view_dolly and
        "/*apply_fn*/ viewdolly_modal_apply," in view_dolly,
        "direct dolly generic continuation wiring differs",
    )

    require_ordered(
        depth_api,
        (
            "class ViewportDepthPickSession",
            "bool init(ARegion *region, const int mval[2]);",
            "ReadbackState state();",
            "bool sample(ARegion *region, float r_world_location[3]);",
        ),
        "owned progressive-depth API",
    )
    require_ordered(
        paint_api,
        (
            "enum class PaintProjStrokeResult : int8_t",
            "Complete,",
            "Pending,",
            "Failed,",
            "PaintProjStrokeResult paint_proj_stroke(",
            "PaintProjStrokeResult paint_proj_stroke_readback_poll(",
            "void paint_proj_stroke_done(void *ps_handle_p);",
        ),
        "projection-paint owned API",
    )
    require_ordered(
        paint_projection,
        (
            "struct ProjStrokeHandle",
            "bool is_clone_cursor_pick;",
            "ViewportDepthPickSession clone_cursor_readback;",
            "Scene *clone_cursor_scene = nullptr;",
            "View3D *clone_cursor_view3d = nullptr;",
            "RegionView3D *clone_cursor_region_view = nullptr;",
            "ARegion *clone_cursor_region = nullptr;",
            "wmWindow *clone_cursor_window = nullptr;",
            "float clone_cursor_before[3] = {0.0f, 0.0f, 0.0f};",
            "PaintProjStrokeResult clone_cursor_result = PaintProjStrokeResult::Complete;",
        ),
        "clone-cursor owned state",
    )
    paint_poll = braced_definition(
        paint_projection,
        "PaintProjStrokeResult paint_proj_stroke_readback_poll(",
        "clone-cursor poll",
    )
    require_ordered(
        paint_poll,
        (
            "ps_handle->clone_cursor_readback.state()",
            "ReadbackState::Pending",
            "ReadbackState::Failed",
            "paint_proj_clone_cursor_readback_context_matches(C, ps_handle)",
            "equals_v3v3(ps_handle->clone_cursor_scene->cursor.location,",
            "ps_handle->clone_cursor_before",
            "ps_handle->clone_cursor_readback.sample(",
            "PaintProjStrokeResult::Complete",
            "if (!has_depth)",
            "copy_v3_v3(ps_handle->clone_cursor_scene->cursor.location, cursor);",
        ),
        "settled clone-cursor replay",
    )
    paint_stroke = braced_definition(
        paint_projection,
        "PaintProjStrokeResult paint_proj_stroke(const bContext *C,",
        "projection stroke",
    )
    require_ordered(
        paint_stroke,
        (
            "if (ps_handle->is_clone_cursor_pick)",
            "ED_view3d_depth_override(",
            "copy_v3_v3(ps_handle->clone_cursor_before, scene->cursor.location);",
            "ps_handle->clone_cursor_readback.init(region, mval_i)",
            "PaintProjStrokeResult::Pending",
            "paint_proj_stroke_readback_poll(C, ps_handle)",
            "paint_proj_stroke_ps(",
            "return PaintProjStrokeResult::Complete;",
        ),
        "kick and native-immediate projection stroke",
    )
    require(
        "ED_view3d_autodist(" not in paint_stroke
        and "GPU_framebuffer_read_depth(" not in paint_stroke
        and "GPU_texture_read(" not in paint_stroke,
        "clone-cursor stroke retains synchronous GPU readback",
    )
    require_ordered(
        paint_operator,
        (
            "struct PaintOperation : public PaintModeData",
            "PaintProjStrokeResult readback_result = PaintProjStrokeResult::Complete;",
            "wmTimer *readback_timer = nullptr;",
            "int readback_tick_count = 0;",
            "wmEvent deferred_finish_event = {};",
            "bool finish_deferred = false;",
        ),
        "paint-operator retained state",
    )
    paint_modal = braced_definition(
        paint_operator,
        "static wmOperatorStatus paint_modal(",
        "paint modal",
    )
    require_ordered(
        paint_modal,
        (
            "event->customdata == pop->readback_timer",
            "constexpr int max_tick_count = 240;",
            "if (++pop->readback_tick_count > max_tick_count)",
            "pop->mode->paint_stroke_readback_poll(C, pop->stroke_handle)",
            "PaintProjStrokeResult::Failed",
            "if (pop->finish_deferred)",
            "wmEvent finish_event = pop->deferred_finish_event;",
            "finish_event.customdata = nullptr;",
            "paint_modal_dispatch(C, op, stroke, &finish_event)",
            "pop->readback_result == PaintProjStrokeResult::Pending",
            "stroke->is_finish_event(event)",
            "event->customdata != nullptr",
            "pop->deferred_finish_event = *event;",
            "pop->finish_deferred = true;",
        ),
        "bounded paint finish continuation",
    )
    require(
        paint_modal.count("paint_modal_readback_cancel(") >= 4,
        "paint failure paths do not converge on cancellation",
    )

    return {
        "schema": 1,
        "verdict": "PASS",
        "contracts": {
            "owned_result_api": True,
            "framebuffer_owned_region_api": True,
            "selection_buffer_owned_request": True,
            "webgpu_exact_tickets": True,
            "object_pick_continuation": True,
            "edit_mesh_click_continuation": True,
            "edit_mesh_gesture_continuation": True,
            "window_color_continuation": True,
            "depth_eyedropper_continuation": True,
            "ordinary_navigation_continuation": True,
            "direct_dolly_continuation": True,
            "painting_depth_continuation": True,
            "native_wasm_contract_required": True,
            "live_hardware_receipt": False,
        },
        "remaining_sync_families": sorted(remaining_sync),
        "source_count": len(SOURCE_PATHS),
        "source_sha256": source_digest(sources),
    }


def run_selfcheck(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        (
            "source/blender/gpu/GPU_readback.hh",
            "bool GPU_readback_consume(GPUReadback *&readback",
            "bool GPU_readback_consume(GPUReadback *readback",
            "owner reference",
        ),
        (
            "source/blender/gpu/intern/gpu_readback_private.hh",
            "gpu_readback_create_transform",
            "gpu_readback_create_passthrough",
            "transform factory",
        ),
        (
            "source/blender/gpu/webgpu/wgpu_framebuffer.cc",
            "plan.texture->read_sub_async(plan.mip, plan.layer, plan.format)",
            "plan.texture->read_sub(plan.mip, plan.layer, plan.format, nullptr)",
            "framebuffer async source",
        ),
        (
            "source/blender/gpu/webgpu/wgpu_texture.cc",
            "readback::RequestMode::Exact",
            "readback::RequestMode::Cache",
            "exact texture ticket",
        ),
        (
            "source/blender/draw/engines/select/select_instance.hh",
            "select_output_buf.read_async()",
            "select_output_buf.read()",
            "select async transfer",
        ),
        (
            "source/blender/editors/space_view3d/view3d_view.cc",
            "GPU_select_async_result_replay(buffer",
            "GPU_select_async_result_drop(buffer",
            "exact replay",
        ),
        (
            "source/blender/editors/space_view3d/view3d_select.cc",
            "  /* Fail closed instead of retaining a modal operator forever after device\n"
            "   * loss or an undelivered browser callback (roughly 2.4 seconds at 10 ms). */\n"
            "  constexpr int max_tick_count = 240;",
            "  /* Bound removed. */\n"
            "  constexpr int max_tick_count = 0;",
            "bounded continuation",
        ),
        (
            "source/blender/draw/intern/draw_select_buffer.cc",
            "GPU_framebuffer_read_color(select_id_fb",
            "GPU_framebuffer_read_color_async(select_id_fb",
            "remaining caller census",
        ),
        (
            "source/blender/draw/DRW_select_buffer.hh",
            "uint *DRW_select_buffer_read_async_consume(DRWSelectBufferReadback *&readback",
            "uint *DRW_select_buffer_read_async_consume(DRWSelectBufferReadback *readback",
            "selection request ownership",
        ),
        (
            "source/blender/draw/intern/draw_select_buffer.cc",
            "GPU_framebuffer_read_color_async(",
            "GPU_framebuffer_read_color(",
            "selection async source",
        ),
        (
            "source/blender/draw/intern/draw_select_buffer.cc",
            "GPU_readback_size(readback->gpu_readback) != expected_size",
            "GPU_readback_size(readback->gpu_readback) > expected_size",
            "selection exact size",
        ),
        (
            "source/blender/draw/intern/draw_select_buffer.cc",
            "GPU_select_buffer_stride_realign(&readback->rect, &readback->rect_clamp, buffer);",
            "/* clamped bytes left packed */",
            "selection clamp realignment",
        ),
        (
            "source/blender/draw/intern/draw_select_buffer.cc",
            "GPU_readback_cancel(readback->gpu_readback);\n  MEM_delete(readback);",
            "/* GPU request leaked */\n  MEM_delete(readback);",
            "selection cancellation",
        ),
        (
            "source/blender/draw/intern/draw_select_buffer.cc",
            "drw_select_buffer_query_context_restore(result.context);",
            "/* stale selection context retained */",
            "selection query context restore",
        ),
        (
            "source/blender/draw/intern/draw_select_buffer.cc",
            "drw_select_buffer_query_key_equal(g_select_buffer_query.pending_key, key)",
            "true /* accept query drift */",
            "selection query exact key",
        ),
        (
            "source/blender/draw/intern/draw_select_buffer.cc",
            "  g_select_buffer_query.replay_required = true;\n"
            "  g_select_buffer_query.pending_key = key;",
            "  g_select_buffer_query.replay_required = false;\n"
            "  g_select_buffer_query.pending_key = key;",
            "selection query replay latch",
        ),
        (
            "source/blender/draw/intern/draw_select_buffer.cc",
            "drw_select_buffer_query_context_restore(g_select_buffer_bitmap.result.context);",
            "/* stale bitmap context retained */",
            "selection bitmap context restore",
        ),
        (
            "source/blender/draw/intern/draw_select_buffer.cc",
            "x * x + y * y < radius_sq",
            "x * x + y * y <= radius_sq",
            "selection bitmap strict circle radius",
        ),
        (
            "source/blender/draw/intern/draw_select_buffer.cc",
            "drw_select_buffer_bitmap_key_equal(g_select_buffer_bitmap.pending_key, key)",
            "true /* accept bitmap drift */",
            "selection bitmap exact key",
        ),
        (
            "source/blender/draw/intern/draw_select_buffer.cc",
            "  g_select_buffer_bitmap.replay_required = true;\n"
            "  g_select_buffer_bitmap.pending_key = key;",
            "  g_select_buffer_bitmap.replay_required = false;\n"
            "  g_select_buffer_bitmap.pending_key = key;",
            "selection bitmap replay latch",
        ),
        (
            "source/blender/editors/space_view3d/view3d_select.cc",
            "    if (!editselect_buf_cache_bitmap_from_rect(\n"
            "            esel, vc->depsgraph, vc->region, vc->v3d, rect))\n"
            "    {\n"
            "      return false;\n"
            "    }",
            "    /* Continue before the bitmap settles. */",
            "box pending-before-mutation guard",
        ),
        (
            "source/blender/editors/space_view3d/view3d_select.cc",
            "    sel_op = async_esel->async_sel_op;\n"
            "    copy_v2_v2_int(mval, async_esel->async_mval);\n"
            "    radius = int(async_esel->async_radius);",
            "    /* Replay current rather than producing circle inputs. */",
            "circle exact input replay",
        ),
        (
            "source/blender/editors/space_view3d/view3d_select.cc",
            "constexpr int max_queued_events = 512;",
            "constexpr int max_queued_events = 0;",
            "circle bounded event queue",
        ),
        (
            "source/blender/editors/mesh/editmesh_select.cc",
            "DRW_select_buffer_find_nearest_to_point_async(",
            "DRW_select_buffer_find_nearest_to_point(",
            "edit-mesh nearest continuation",
        ),
        (
            "source/blender/editors/mesh/editmesh_select.cc",
            "bool found = unified_findnearest(&vc, bases, &base_index_active, &eve, &eed, &efa);\n"
            "  if (edbm_select_buffer_query_pending_or_failed())",
            "bool found = unified_findnearest(&vc, bases, &base_index_active, &eve, &eed, &efa);\n"
            "  if (false)",
            "edit-mesh pending guard",
        ),
        (
            "source/blender/editors/space_view3d/view3d_select.cc",
            "DRW_select_buffer_query_session_begin();",
            "/* raw query session omitted */",
            "edit-mesh query session begin",
        ),
        (
            "source/blender/editors/space_view3d/view3d_select.cc",
            "    op->customdata = nullptr;\n  }\n  DRW_select_buffer_query_session_end();",
            "    op->customdata = nullptr;\n  }\n  /* raw query session leaked */",
            "edit-mesh query session end",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
            "WM_window_pixels_read_async(C, window)",
            "WM_window_pixels_read(C, window, size_)",
            "window sample continuation",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_depth.cc",
            "ViewportDepthPickSession readback_session;",
            "int readback_session;",
            "depth eyedropper continuation",
        ),
        (
            "source/blender/editors/space_view3d/view3d_navigate.cc",
            "read->queued_event = *event;",
            "read->queued_event = {};",
            "ordinary navigation continuation",
        ),
        (
            "source/blender/editors/space_view3d/view3d_navigate_view_dolly.cc",
            "view3d_navigate_invoke_impl(C, op, event, &ViewOpsType_dolly)",
            "viewops_data_create(C, event, &ViewOpsType_dolly, false)",
            "direct dolly continuation",
        ),
        (
            "source/blender/editors/sculpt_paint/paint_intern.hh",
            "PaintProjStrokeResult paint_proj_stroke_readback_poll(",
            "void paint_proj_stroke_readback_poll_removed(",
            "painting poll API",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_proj.cc",
            "ViewportDepthPickSession clone_cursor_readback;",
            "int clone_cursor_readback;",
            "painting owned session",
        ),
        (
            "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc",
            "pop->deferred_finish_event = *event;",
            "pop->finish_deferred = true;",
            "painting exact finish replay",
        ),
    )
    for relative, old, new, label in mutations:
        require_once(sources[relative], old, f"selfcheck {label}")
        mutated = dict(sources)
        mutated[relative] = sources[relative].replace(old, new, 1)
        try:
            validate(mutated)
        except VerificationError:
            continue
        raise VerificationError(f"selfcheck mutation accepted: {label}")
    print(
        "M5_ASYNC_READBACK_SOURCE_SELFCHECK_PASS "
        f"mutations={len(mutations)} allocation=zero"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    require(args.selfcheck != (args.output is not None), "choose exactly one of --selfcheck/--output")
    sources = read_sources(args.source_root)
    if args.selfcheck:
        run_selfcheck(sources)
        return 0
    result = validate(sources)
    assert args.output is not None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "M5_ASYNC_READBACK_SOURCE_PASS "
        f"sources={result['source_count']} remaining={len(result['remaining_sync_families'])} "
        f"sha256={result['source_sha256']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as error:
        print(f"M5_ASYNC_READBACK_SOURCE_FAIL {error}", file=__import__("sys").stderr)
        raise SystemExit(1)
