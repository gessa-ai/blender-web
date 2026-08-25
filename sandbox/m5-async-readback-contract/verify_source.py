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
    "source/blender/editors/asset/intern/asset_ops.cc",
    "source/blender/editors/include/ED_particle.hh",
    "source/blender/editors/include/ED_view3d.hh",
    "source/blender/editors/curve/editcurve_paint.cc",
    "source/blender/editors/curves/intern/curves_draw.cc",
    "source/blender/editors/gpencil_legacy/annotate_paint.cc",
    "source/blender/editors/mesh/editmesh_select.cc",
    "source/blender/editors/object/object_transform.cc",
    "source/blender/editors/physics/particle_edit.cc",
    "source/blender/editors/sculpt_paint/paint_intern.hh",
    "source/blender/editors/sculpt_paint/mesh/paint_image_proj.cc",
    "source/blender/editors/sculpt_paint/mesh/paint_image_ops_paint.cc",
    "source/blender/editors/screen/screendump.cc",
    "source/blender/editors/space_view3d/view3d_draw.cc",
    "source/blender/editors/space_view3d/view3d_navigate.cc",
    "source/blender/editors/space_view3d/view3d_navigate.hh",
    "source/blender/editors/space_view3d/view3d_navigate_view_ndof.cc",
    "source/blender/editors/space_view3d/view3d_navigate_view_dolly.cc",
    "source/blender/editors/space_view3d/view3d_navigate_zoom_border.cc",
    "source/blender/editors/space_view3d/view3d_select.cc",
    "source/blender/editors/space_view3d/view3d_view.cc",
    "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
    "source/blender/editors/interface/eyedroppers/eyedropper_colorband.cc",
    "source/blender/editors/interface/eyedroppers/eyedropper_depth.cc",
    "source/blender/editors/interface/eyedroppers/eyedropper_grease_pencil_color.cc",
    "source/blender/editors/interface/eyedroppers/eyedropper_intern.hh",
    "source/blender/python/intern/bpy_rna_wm.cc",
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


def braced_definition(text: str, marker: str, label: str, *, last: bool = False) -> str:
    if last:
        require(marker in text, f"{label}: definition marker missing")
        start = text.rindex(marker)
    else:
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
    asset_ops = sources["source/blender/editors/asset/intern/asset_ops.cc"]
    particle_api = sources["source/blender/editors/include/ED_particle.hh"]
    depth_api = sources["source/blender/editors/include/ED_view3d.hh"]
    depth_draw = sources["source/blender/editors/space_view3d/view3d_draw.cc"]
    curve_draw = sources["source/blender/editors/curve/editcurve_paint.cc"]
    curves_draw = sources["source/blender/editors/curves/intern/curves_draw.cc"]
    annotation_draw = sources[
        "source/blender/editors/gpencil_legacy/annotate_paint.cc"
    ]
    editmesh_select = sources["source/blender/editors/mesh/editmesh_select.cc"]
    object_transform = sources["source/blender/editors/object/object_transform.cc"]
    particle_edit = sources["source/blender/editors/physics/particle_edit.cc"]
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
    view_ndof = sources[
        "source/blender/editors/space_view3d/view3d_navigate_view_ndof.cc"
    ]
    view_dolly = sources[
        "source/blender/editors/space_view3d/view3d_navigate_view_dolly.cc"
    ]
    zoom_border = sources[
        "source/blender/editors/space_view3d/view3d_navigate_zoom_border.cc"
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
    python_wm = sources["source/blender/python/intern/bpy_rna_wm.cc"]
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

    require_ordered(
        depth_api,
        (
            "class ViewportDepthCacheSession",
            "bool init(ARegion *region);",
            "ReadbackState state();",
            "ViewDepths *take(ARegion *region);",
            "class ViewportDepthPickSession",
        ),
        "owned depth-cache API",
    )
    depth_cache_init = braced_definition(
        depth_draw,
        "bool ViewportDepthCacheSession::init(ARegion *region)",
        "owned depth-cache request",
    )
    require_ordered(
        depth_cache_init,
        (
            "GPU_viewport_depth_texture(viewport)",
            "std::numeric_limits<unsigned short>::max()",
            "std::numeric_limits<int>::max()",
            "impl->expected_size = width * height * sizeof(float);",
            "GPU_texture_read_async(depth_tx, GPU_DATA_FLOAT, 0)",
            "impl->readback_state = ReadbackState::Pending;",
        ),
        "exact full-viewport depth request",
    )
    depth_cache_take = braced_definition(
        depth_draw,
        "ViewDepths *ViewportDepthCacheSession::take(ARegion *region)",
        "owned depth-cache transfer",
    )
    for needle in (
        "region->regiondata != impl_->region_view",
        "region->winx != impl_->region_size[0]",
        "region->winy != impl_->region_size[1]",
        "equals_m4m4(static_cast<RegionView3D *>(region->regiondata)->viewinv",
        "equals_m4m4(static_cast<RegionView3D *>(region->regiondata)->winmat",
        "GPU_readback_consume(",
        "depths->depth_range[0] = 0.0;",
        "depths->depth_range[1] = 1.0;",
    ):
        require(needle in depth_cache_take, f"owned depth-cache transfer missing {needle!r}")

    require(
        "void ED_view3d_depth_override_prepare(" in depth_api,
        "forced draw-only depth API missing",
    )
    depth_prepare = braced_definition(
        depth_draw,
        "void ED_view3d_depth_override_prepare(",
        "forced draw-only depth implementation",
    )
    require(
        "view3d_depth_override_impl(depsgraph, region, v3d, mode, use_overlay, nullptr, true);"
        in depth_prepare,
        "forced draw-only depth route differs",
    )
    for label, caller in (("curve", curve_draw), ("curves", curves_draw)):
        for needle in (
            "ViewportDepthCacheSession *depth_cache_session;",
            "Vector<wmEvent> *depth_cache_events;",
            "constexpr int max_queued_events = 256;",
            "event->custom != 0",
            "CTX_wm_area(C) == cdd->depth_cache_area",
            "ED_view3d_depth_override_prepare(",
            "ViewportDepthCacheSession::ReadbackState::Pending",
            "constexpr int max_tick_count = 240;",
            "cdd->depth_cache_session->take(cdd->vc.region)",
            "curve_draw_modal_dispatch(C, op, &queued)",
            "ot->cancel = curve_draw_cancel;",
        ):
            require(needle in caller, f"{label} depth-cache continuation missing {needle!r}")
        invoke_marker = (
            "static wmOperatorStatus curve_draw_invoke"
            if label == "curve"
            else "static wmOperatorStatus curves_draw_invoke"
        )
        invoke = braced_definition(caller, invoke_marker, f"{label} draw invoke")
        require("&cdd->depths" not in invoke, f"{label} draw still blocks on a full depth cache")

    for needle in (
        "ViewportDepthCacheSession *depth_cache_session = nullptr;",
        "Vector<wmEvent> *depth_cache_events = nullptr;",
        "bool depth_cache_pending = false;",
        "bool depth_cache_owned = false;",
        "bool depth_cache_resume_apply_event = false;",
        "Vector<AnnotationRecordedStrokePoint> *recorded_stroke_points = nullptr;",
        "int64_t recorded_stroke_index = 0;",
        "bool recorded_stroke_exec = false;",
        "constexpr int max_queued_events = 256;",
        "event->custom != 0",
        "event->customdata != nullptr",
    ):
        require(needle in annotation_draw, f"annotation depth-cache owner missing {needle!r}")
    annotation_begin = braced_definition(
        annotation_draw,
        "static AnnotationDepthCacheState annotation_depth_cache_begin(",
        "annotation depth-cache request",
    )
    require_ordered(
        annotation_begin,
        (
            "annotation_depth_cache_matches(p, mode)",
            "ED_view3d_depth_override_prepare(",
            "MEM_new<ViewportDepthCacheSession>",
            "p->depth_cache_session->init(p->region)",
            "ViewportDepthCacheSession::ReadbackState::Ready",
            "WM_event_timer_add(manager, p->win, TIMER, 0.01f)",
            "p->depth_cache_pending = true;",
        ),
        "annotation exact owned request",
    )
    annotation_poll = braced_definition(
        annotation_draw,
        "static wmOperatorStatus annotation_depth_poll(",
        "annotation bounded settlement",
    )
    require_ordered(
        annotation_poll,
        (
            "annotation_depth_context_matches(C, p)",
            "event->customdata != p->depth_cache_timer",
            "constexpr int max_tick_count = 240;",
            "p->depth_cache_session->state()",
            "annotation_depth_cache_take(p)",
            "const bool resume_apply_event = p->depth_cache_resume_apply_event;",
            "if (p->recorded_stroke_exec)",
            "annotation_recorded_stroke_resume(C, op)",
            "annotation_depth_resume_apply_event(",
            "annotation_draw_modal(C, op",
        ),
        "annotation exact FIFO settlement",
    )
    annotation_modal = braced_definition(
        annotation_draw,
        "static wmOperatorStatus annotation_draw_modal(bContext *C,",
        "annotation modal continuation",
        last=True,
    )
    require_ordered(
        annotation_modal,
        (
            "if (p->depth_cache_pending)",
            "annotation_depth_poll(C, op, event)",
            "annotation_depth_event_requires_cache(p, event)",
            "annotation_depth_cache_defer_event(",
            "annotation_draw_modal_dispatch(C, op, event)",
        ),
        "annotation modal cache barrier",
    )
    annotation_exec = braced_definition(
        annotation_draw,
        "static wmOperatorStatus annotation_draw_exec(",
        "annotation recorded-stroke exec",
    )
    require_ordered(
        annotation_exec,
        (
            "p->depth_cache_owned = true;",
            "p->recorded_stroke_exec = true;",
            "MEM_new<Vector<AnnotationRecordedStrokePoint>>",
            "p->recorded_stroke_points->append(point)",
            "annotation_recorded_stroke_resume(C, op)",
            "WM_event_add_modal_handler(C, op)",
        ),
        "annotation recorded-stroke ownership",
    )
    annotation_recorded_resume = braced_definition(
        annotation_draw,
        "static wmOperatorStatus annotation_recorded_stroke_resume(",
        "annotation recorded-stroke replay",
    )
    require_ordered(
        annotation_recorded_resume,
        (
            "p->recorded_stroke_index < p->recorded_stroke_points->size()",
            "point.is_start && (p->flags & GP_PAINTFLAG_FIRSTRUN) == 0",
            "annotation_recorded_stroke_cache_ensure(C, p, false)",
            "annotation_paint_strokeend(p)",
            "annotation_paint_initstroke(p, p->paintmode, depsgraph)",
            "annotation_recorded_stroke_cache_ensure(C, p, true)",
            "annotation_draw_apply(op, p, depsgraph)",
            "p->recorded_stroke_index++",
            "annotation_draw_exit(C, op)",
        ),
        "annotation recorded-stroke exact replay",
    )
    require(
        annotation_draw.count("ED_view3d_depth_override(") == 0
        and annotation_draw.count("ED_view3d_depth_override_prepare(") == 1,
        "annotation synchronous residual or async prepare census drifted",
    )
    for needle in (
        "ot->exec = annotation_draw_exec;",
        "ot->invoke = annotation_draw_invoke;",
        "ot->modal = annotation_draw_modal;",
        "ot->cancel = annotation_draw_cancel;",
    ):
        require(needle in annotation_draw, f"annotation callback wiring missing {needle!r}")

    for needle in (
        "enum class ParticleEditDepthCacheState",
        "enum class ParticleEditOperationResult",
        "PE_depth_cache_session_create",
        "PE_depth_cache_session_state",
        "PE_circle_select_depth_cache_event_pop",
    ):
        require(needle in particle_api, f"particle-edit public continuation missing {needle!r}")
    require(
        particle_api.count("ParticleEditDepthCacheSession *depth_session") == 3,
        "particle-edit one-shot session API census drifted",
    )
    require(
        "ED_view3d_depth_override(" not in particle_edit
        and particle_edit.count("ED_view3d_depth_override_prepare(") == 1,
        "particle-edit synchronous residual or async prepare census drifted",
    )
    require(
        particle_edit.count("PE_set_view3d_data(") == 7,
        "particle-edit prepare/consume caller census drifted",
    )
    for needle in (
        "ViewportDepthCacheSession readback;",
        "session->consumed = true;",
        "data->depths = session->readback.take(session->region);",
        "XRAY_ENABLED(session->view3d) == session->xray_bypass",
        "struct ParticleLinkedPickData",
        "struct ParticleCircleSelectData",
        "constexpr int max_queued_events = 512",
        "constexpr int max_queued_events = 256",
        "brush_edit_depth_poll",
    ):
        require(needle in particle_edit, f"particle-edit ownership contract missing {needle!r}")
    for needle in (
        "ParticleEditDepthCacheSession *particle_depth_session",
        "View3DGestureAsyncKind::ParticleBox",
        "View3DGestureAsyncKind::ParticleLasso",
        "view3d_particle_gesture_async_modal",
        "struct View3DParticleCircleDirectData",
        "view3d_particle_circle_direct_operators",
    ):
        require(needle in view_select, f"particle-edit caller owner missing {needle!r}")

    particle_producer = braced_definition(
        particle_edit,
        "struct ParticleEditDepthProducerState",
        "particle-edit producer snapshot",
    )
    for needle in (
        "float scene_frame = 0.0f;",
        "unsigned int object_session_uid = 0;",
        "float object_to_world[4][4]{};",
        "float world_to_object[4][4]{};",
        "ParticleEditDepthHash edit_state{};",
        "bool captured = false;",
    ):
        require(needle in particle_producer, f"particle producer snapshot missing {needle!r}")
    particle_edit_hash = braced_definition(
        particle_edit,
        "static bool PE_depth_cache_edit_state_hash(",
        "particle-edit state token",
    )
    for needle in (
        "edit->totpoint",
        "point->totkey",
        "point->flag",
        "PE_depth_cache_hash_bytes(&hash, key->co, sizeof(float[3]));",
        "key->world_co",
        "key->flag",
    ):
        require(needle in particle_edit_hash, f"particle edit-state token missing {needle!r}")
    particle_capture = braced_definition(
        particle_edit,
        "static bool PE_depth_cache_producer_state_capture(",
        "particle-edit producer capture",
    )
    for needle in (
        "BKE_scene_frame_get(session->scene)",
        "session->object->id.session_uid",
        "copy_m4_m4(session->producer_state.object_to_world,",
        "copy_m4_m4(session->producer_state.world_to_object,",
        "PE_depth_cache_edit_state_hash(session->edit, &session->producer_state.edit_state)",
        "session->producer_state.captured = true;",
    ):
        require(needle in particle_capture, f"particle producer capture missing {needle!r}")
    particle_guard = braced_definition(
        particle_edit,
        "static bool PE_depth_cache_producer_state_matches(",
        "particle-edit producer guard",
    )
    for needle in (
        "BKE_scene_frame_get(session->scene) != state.scene_frame",
        "session->object->id.session_uid != state.object_session_uid",
        "std::memcmp(state.object_to_world,",
        "std::memcmp(state.world_to_object,",
        "current_edit_state.low != state.edit_state.low",
        "current_edit_state.high != state.edit_state.high",
    ):
        require(needle in particle_guard, f"particle producer guard missing {needle!r}")
    particle_ready_guard = braced_definition(
        particle_edit,
        "ParticleEditDepthCacheState PE_depth_cache_session_state(",
        "particle-edit ready-state guard",
    )
    require(
        "PE_depth_cache_producer_state_matches(session)" in particle_ready_guard,
        "particle ready-state guard omits same-pointer producer state",
    )
    particle_prepare = braced_definition(
        particle_edit,
        "static ParticleEditDepthCacheState PE_set_view3d_data(",
        "particle-edit prepare/consume",
    )
    require_ordered(
        particle_prepare,
        (
            "PE_depth_cache_producer_state_capture(session)",
            "ED_view3d_depth_override_prepare(",
            "PE_depth_cache_session_state(C, session)",
            "session->readback.take(session->region)",
        ),
        "particle producer snapshot and guard before old-depth transfer",
    )

    axis_producer = braced_definition(
        object_transform,
        "struct XFormAxisProducerObjectState",
        "axis-target producer object snapshot",
    )
    for needle in (
        "unsigned int session_uid = 0;",
        "unsigned int parent_session_uid = 0;",
        "ObjectTfmProtectedChannels transform_channels{};",
        "float object_to_world[4][4]{};",
        "float world_to_object[4][4]{};",
        "float parent_inverse[4][4]{};",
        "float constraint_inverse[4][4]{};",
    ):
        require(needle in axis_producer, f"axis-target producer snapshot missing {needle!r}")
    axis_object_guard = braced_definition(
        object_transform,
        "static bool object_transform_axis_target_depth_producer_object_matches(",
        "axis-target producer object guard",
    )
    for needle in (
        "snapshot.session_uid != ob->id.session_uid",
        "snapshot.parent_session_uid != parent_session_uid",
        "snapshot.data != ob->data",
        "snapshot.rotation_mode != ob->rotmode",
        "&snapshot.transform_channels",
        "std::memcmp(snapshot.object_to_world,",
        "std::memcmp(snapshot.world_to_object,",
        "std::memcmp(snapshot.parent_inverse,",
        "snapshot.constraint_inverse, ob->constinv",
    ):
        require(needle in axis_object_guard, f"axis-target producer guard missing {needle!r}")
    axis_state_guard = braced_definition(
        object_transform,
        "static bool object_transform_axis_target_depth_producer_state_matches(",
        "axis-target producer state guard",
    )
    for needle in (
        "BKE_scene_frame_get(xfd->vc.scene) != xfd->depth_cache_producer_frame",
        "object_transform_axis_target_selected_targets(",
        "current_targets.size() != xfd->depth_cache_producer_objects.size()",
        "object_transform_axis_target_depth_producer_object_matches(",
    ):
        require(needle in axis_state_guard, f"axis-target state guard missing {needle!r}")
    axis_context_guard = braced_definition(
        object_transform,
        "static bool object_transform_axis_target_depth_context_matches(",
        "axis-target context guard",
    )
    require(
        "object_transform_axis_target_depth_producer_state_matches(C, xfd)"
        in axis_context_guard,
        "axis-target context guard does not bind mutable producer state",
    )
    axis_wait = braced_definition(
        object_transform,
        "static bool object_transform_axis_target_depth_wait_begin(",
        "axis-target wait begin",
    )
    require_ordered(
        axis_wait,
        (
            "object_transform_axis_target_depth_producer_state_capture(C, xfd)",
            "WM_event_timer_add(",
            "xfd->depth_cache_pending = true;",
        ),
        "axis-target producer snapshot before suspension",
    )

    native_sync_controls = {
        "window_capture": (
            "source/blender/windowmanager/intern/wm_draw.cc",
            "GPU_offscreen_read_color(offscreen, GPU_DATA_UBYTE, rect);",
        ),
    }
    for family, (relative, needle) in native_sync_controls.items():
        require(needle in sources[relative], f"native sync control drifted: {family}")
    require(
        "WM_window_pixels_read(C, win, dumprect_size)" not in asset_ops,
        "asset-preview operator retains synchronous WM capture",
    )
    for needle in (
        "WMWindowPixelsRead *readback = nullptr;",
        "std::optional<AssetWeakReference> readback_asset_reference;",
        "static bool screenshot_preview_readback_context_matches(",
        "data->readback = WM_window_pixels_read_async(C, win);",
        "WM_window_pixels_read_async_consume(data->readback, dumprect_size)",
        "event->customdata != data->readback_timer",
        "constexpr int max_tick_count = 240;",
        "WM_window_pixels_read_async_cancel(data->readback);",
        "ot->cancel = screenshot_preview_cancel;",
    ):
        require(needle in asset_ops, f"asset-preview continuation missing {needle!r}")
    python_screenshot = braced_definition(
        python_wm,
        "static PyObject *bpy_rna_window_screenshot(",
        "Python Window.screenshot",
    )
    require_once(python_screenshot, "#ifdef __EMSCRIPTEN__", "Python browser policy")
    require_once(python_screenshot, "#else", "Python browser/native branch")
    require_once(python_screenshot, "#endif", "Python browser policy terminator")
    python_prefix, python_guarded = python_screenshot.split("#ifdef __EMSCRIPTEN__", 1)
    python_browser, python_native_guarded = python_guarded.split("#else", 1)
    python_native, python_suffix = python_native_guarded.split("#endif", 1)
    require(
        "Window.screenshot() is not available in background mode" in python_prefix,
        "Python background behavior does not precede browser policy",
    )
    for needle in (
        "PyExc_RuntimeError",
        "Window.screenshot() is unavailable in the browser because WebGPU readback is",
        "asynchronous; use bpy.ops.screen.screenshot() for file capture",
        "return nullptr;",
    ):
        require(needle in python_browser, f"Python browser policy missing {needle!r}")
    require(
        "WM_window_pixels_read" not in python_browser and
        "PyC_MemoryView_FromBufferOwned" not in python_browser,
        "Python browser policy retains synchronous capture or fabricates pixels",
    )
    require(
        python_native.count("WM_window_pixels_read(C, win, dumprect_size)") == 1 and
        "PyC_MemoryView_FromBufferOwned(&info)" in python_native,
        "native Python Window.screenshot contract drifted",
    )
    require(
        python_suffix.strip() == "}",
        "Python browser policy does not terminate with the method",
    )
    require(
        "GPU_framebuffer_read_depth(depth_read_fb" in sources[
            "source/blender/editors/space_view3d/view3d_draw.cc"
        ],
        "native synchronous depth primitive control missing",
    )
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

    require_ordered(
        zoom_border,
        (
            "struct ZoomBorderDepthRead",
            "GPUReadback *readback = nullptr;",
            "rcti rect = {};",
            "float viewinv[4][4] = {};",
            "int smooth_viewtx = 0;",
            "bool zoom_in = true;",
            "bool superseded = false;",
        ),
        "zoom-border owned state",
    )
    zoom_create = braced_definition(
        zoom_border,
        "static ZoomBorderDepthRead *view3d_zoom_border_depth_read_create(",
        "zoom-border depth kick",
    )
    require_ordered(
        zoom_create,
        (
            "WM_operator_properties_border_to_rcti(op, &read->rect);",
            "BLI_rcti_isect(&bounds, &request_rect, &request_rect);",
            "read->rect = request_rect;",
            "GPU_framebuffer_read_depth_async(depth_read_fb",
        ),
        "zoom-border exact owned request",
    )
    require(
        "GPU_framebuffer_read_depth(" not in zoom_create
        and "view3d_depths_rect_create(" not in zoom_create,
        "zoom-border kick retains synchronous readback",
    )
    zoom_modal = braced_definition(
        zoom_border,
        "static wmOperatorStatus view3d_zoom_border_modal(",
        "zoom-border modal continuation",
    )
    require_ordered(
        zoom_modal,
        (
            "WM_gesture_box_modal(C, op, event);",
            "view3d_zoom_border_depth_read_attach(C, op, read, false);",
            "read->superseded",
            "view3d_zoom_border_depth_read_context_matches(C, read)",
            "event->type != TIMER || event->customdata != read->timer",
            "constexpr int max_tick_count = 240;",
            "if (++read->tick_count > max_tick_count)",
            "view3d_zoom_border_depth_read_finish(C, op, read)",
        ),
        "zoom-border gesture handoff",
    )
    for needle in (
        "ot->modal = view3d_zoom_border_modal;",
        "ot->cancel = view3d_zoom_border_cancel;",
    ):
        require(needle in zoom_border, f"zoom-border callback wiring missing {needle!r}")

    require(
        "static float ndof_read_zbuf_rect(" not in view_ndof
        and "view3d_depths_rect_create(region" not in view_ndof,
        "NDOF retains its synchronous rectangle-depth caller",
    )
    require_ordered(
        view_ndof,
        (
            "struct NdofQueuedMotion",
            "struct NdofDepthRead",
            "GPUReadback *readback = nullptr;",
            "wmEvent invoke_event = {};",
            "wmNDOFMotionData invoke_motion = {};",
            "Vector<NdofQueuedMotion> queued_motions;",
            "static NdofDepthRead *ndof_depth_read_create(",
            "GPU_framebuffer_read_depth_async(",
            "static NdofOrbitCenterResult ndof_orbit_center_calc(",
            "return NdofOrbitCenterResult::Pending;",
        ),
        "NDOF owned depth request",
    )
    ndof_modal = braced_definition(
        view_ndof,
        "wmOperatorStatus view3d_ndof_depth_modal(",
        "NDOF depth continuation",
    )
    require_ordered(
        ndof_modal,
        (
            "ndof_depth_context_matches(C, vod, read)",
            "constexpr int max_queued_motions = 256;",
            "read->queued_motions.append(ndof_motion_copy(*event));",
            "event->type != TIMER || event->customdata != read->timer",
            "constexpr int max_tick_count = 240;",
            "ndof_depth_read_consume(read, min_depth_point)",
            "read->resolved = true;",
            "ndof_replay_owned_event(C, op, vod, invoke_event, invoke_motion)",
            "for (int index = 0; index < queued_motions.size(); index++)",
        ),
        "NDOF exact payload FIFO",
    )
    for needle in (
        "NdofDepthRead *ndof_depth_read = nullptr;",
        "bool view3d_ndof_depth_is_pending(const ViewOpsData *vod);",
        "wmOperatorStatus view3d_ndof_depth_modal(bContext *C, wmOperator *op, const wmEvent *event);",
        "void view3d_ndof_depth_cancel(bContext *C, ViewOpsData *vod);",
    ):
        require(needle in view_navigate_header, f"NDOF lifecycle API missing {needle!r}")
    require(
        "return view3d_ndof_depth_modal(C, op, event);" in view_navigate
        and "view3d_ndof_depth_cancel(C, this);" in view_navigate,
        "NDOF lifecycle routing missing",
    )
    require(
        view_ndof.count("ot->modal = view3d_navigate_modal_fn;") == 2
        and view_ndof.count("ot->cancel = view3d_navigate_cancel_fn;") == 2,
        "NDOF operator callback wiring differs",
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
            "zoom_border_continuation": True,
            "ndof_depth_continuation": True,
            "depth_cache_async_primitive": True,
            "curve_draw_depth_cache_continuations": True,
            "annotation_depth_cache_continuation": True,
            "particle_edit_depth_cache_continuation": True,
            "particle_producer_state_guard": True,
            "axis_target_producer_state_guard": True,
            "asset_preview_window_capture_continuation": True,
            "python_window_screenshot_browser_deferral": True,
            "native_wasm_contract_required": True,
            "live_hardware_receipt": False,
        },
        "converted_window_capture_callers": ["asset_preview"],
        "deferred_window_capture_callers": ["python_window_screenshot_memoryview"],
        "remaining_window_capture_callers": [],
        "remaining_sync_families": [],
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
        (
            "source/blender/editors/space_view3d/view3d_navigate_zoom_border.cc",
            "view3d_zoom_border_depth_read_attach(C, op, read, false);",
            "return OPERATOR_CANCELLED;",
            "zoom-border gesture handoff",
        ),
        (
            "source/blender/editors/space_view3d/view3d_navigate_view_ndof.cc",
            "read->queued_motions.append(ndof_motion_copy(*event));",
            "/* queued NDOF motion dropped */",
            "NDOF payload FIFO",
        ),
        (
            "source/blender/editors/space_view3d/view3d_draw.cc",
            "GPU_texture_read_async(depth_tx, GPU_DATA_FLOAT, 0)",
            "GPU_texture_read(depth_tx, GPU_DATA_FLOAT, 0)",
            "depth-cache async primitive",
        ),
        (
            "source/blender/editors/curve/editcurve_paint.cc",
            "ED_view3d_depth_override_prepare(cdd->vc.depsgraph,",
            "ED_view3d_depth_override(cdd->vc.depsgraph,",
            "curve-draw depth-cache continuation",
        ),
        (
            "source/blender/editors/gpencil_legacy/annotate_paint.cc",
            "ED_view3d_depth_override_prepare(",
            "ED_view3d_depth_override_legacy(",
            "annotation depth-cache continuation",
        ),
        (
            "source/blender/editors/gpencil_legacy/annotate_paint.cc",
            "p->recorded_stroke_index++;",
            "p->recorded_stroke_index += 0;",
            "annotation recorded-stroke cursor",
        ),
        (
            "source/blender/editors/physics/particle_edit.cc",
            "ED_view3d_depth_override_prepare(",
            "ED_view3d_depth_override(",
            "particle-edit async prepare",
        ),
        (
            "source/blender/editors/physics/particle_edit.cc",
            "session->consumed = true;",
            "session->consumed = false;",
            "particle-edit one-shot consume",
        ),
        (
            "source/blender/editors/physics/particle_edit.cc",
            "constexpr int max_queued_events = 256",
            "constexpr int max_queued_events = 0",
            "particle-edit brush FIFO bound",
        ),
        (
            "source/blender/editors/physics/particle_edit.cc",
            "BKE_scene_frame_get(session->scene) != state.scene_frame",
            "false",
            "particle-edit same-pointer frame drift",
        ),
        (
            "source/blender/editors/physics/particle_edit.cc",
            "std::memcmp(state.object_to_world,",
            "std::memcmp(state.object_to_world_lost,",
            "particle-edit same-pointer object transform drift",
        ),
        (
            "source/blender/editors/physics/particle_edit.cc",
            "PE_depth_cache_hash_bytes(&hash, key->co, sizeof(float[3]));",
            "PE_depth_cache_hash_bytes(&hash, key->world_co, sizeof(float[3]));",
            "particle-edit same-pointer edit data drift",
        ),
        (
            "source/blender/editors/physics/particle_edit.cc",
            "PE_depth_cache_producer_state_matches(session)",
            "true",
            "particle-edit producer-state ready guard",
        ),
        (
            "source/blender/editors/object/object_transform.cc",
            "BKE_scene_frame_get(xfd->vc.scene) != xfd->depth_cache_producer_frame",
            "false",
            "axis-target same-pointer frame drift",
        ),
        (
            "source/blender/editors/object/object_transform.cc",
            "current_targets.size() != xfd->depth_cache_producer_objects.size()",
            "false",
            "axis-target same-pointer selection drift",
        ),
        (
            "source/blender/editors/object/object_transform.cc",
            "snapshot.session_uid != ob->id.session_uid",
            "false",
            "axis-target selected identity drift",
        ),
        (
            "source/blender/editors/object/object_transform.cc",
            "std::memcmp(snapshot.object_to_world,",
            "std::memcmp(ob->object_to_world().ptr(),",
            "axis-target same-pointer transform drift",
        ),
        (
            "source/blender/editors/space_view3d/view3d_select.cc",
            "struct View3DParticleCircleDirectData",
            "struct LostParticleCircleDirectData",
            "particle-edit direct circle owner",
        ),
        (
            "source/blender/editors/asset/intern/asset_ops.cc",
            "data->readback = WM_window_pixels_read_async(C, win);",
            "data->readback = nullptr;",
            "asset-preview window capture continuation",
        ),
        (
            "source/blender/python/intern/bpy_rna_wm.cc",
            "WM_window_pixels_read(C, win, dumprect_size)",
            "WM_window_pixels_read_async(C, win)",
            "native Python window capture control",
        ),
        (
            "source/blender/python/intern/bpy_rna_wm.cc",
            "#ifdef __EMSCRIPTEN__",
            "#if 0",
            "Python browser policy guard",
        ),
        (
            "source/blender/python/intern/bpy_rna_wm.cc",
            "asynchronous; use bpy.ops.screen.screenshot() for file capture",
            "asynchronous capture unavailable",
            "Python browser policy workaround",
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
