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
    "source/blender/draw/engines/select/select_instance.hh",
    "source/blender/draw/intern/draw_select_buffer.cc",
    "source/blender/editors/screen/screendump.cc",
    "source/blender/editors/space_view3d/view3d_draw.cc",
    "source/blender/editors/space_view3d/view3d_select.cc",
    "source/blender/editors/space_view3d/view3d_view.cc",
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
    select_engine = sources["source/blender/draw/engines/select/select_instance.hh"]
    view_select = sources["source/blender/editors/space_view3d/view3d_select.cc"]
    view_query = sources["source/blender/editors/space_view3d/view3d_view.cc"]

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
    exec_body = braced_definition(
        view_select, "static wmOperatorStatus view3d_select_exec(", "select exec"
    )
    for needle in (
        "GPU_select_async_status();",
        "if (status == GPU_READBACK_PENDING)",
        "return OPERATOR_RUNNING_MODAL;",
        "if (status == GPU_READBACK_FAILED)",
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
        "GPU_select_async_status();",
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
        "legacy_select_buffer": (
            "source/blender/draw/intern/draw_select_buffer.cc",
            "GPU_framebuffer_read_color(select_id_fb",
        ),
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
        "window_color_sample": (
            "source/blender/windowmanager/intern/wm_draw.cc",
            "GPU_offscreen_read_color_region(offscreen, GPU_DATA_FLOAT",
        ),
    }
    for family, (relative, needle) in remaining_sync.items():
        require(needle in sources[relative], f"remaining sync census drifted: {family}")
    require(
        "WM_window_pixels_read_async(C, win)" in sources[
            "source/blender/editors/screen/screendump.cc"
        ],
        "screenshot async continuation missing",
    )

    return {
        "schema": 1,
        "verdict": "PASS",
        "contracts": {
            "owned_result_api": True,
            "framebuffer_owned_region_api": True,
            "webgpu_exact_tickets": True,
            "object_pick_continuation": True,
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
            "constexpr int max_tick_count = 240;",
            "constexpr int max_tick_count = 0;",
            "bounded continuation",
        ),
        (
            "source/blender/draw/intern/draw_select_buffer.cc",
            "GPU_framebuffer_read_color(select_id_fb",
            "GPU_framebuffer_read_color_async(select_id_fb",
            "remaining caller census",
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
