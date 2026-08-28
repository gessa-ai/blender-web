#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind float buffer-texture readback latency to pending intent and redraw."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERTEX = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_vertex_buffer.cc"
BUFFER_HEADER = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_buffer.hh"
BUFFER_SOURCE = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_buffer.cc"
READBACK_HEADER = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_readback.hh"
READBACK_SOURCE = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_readback.cc"
CONTEXT_HEADER = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_context.hh"
CONTEXT_SOURCE = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_context.cc"
SHADER_SOURCE = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_shader.cc"
SERIES = ROOT / "patches/series"
PATCH = ROOT / "patches/0301-gpu-webgpu-buffer-texture-readback-readiness.patch"


def method(source: str, signature: str) -> str:
    if source.count(signature) != 1:
        raise ValueError(f"method boundary is not unique: {signature}")
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated method: {signature}")


def validate(
    vertex: str,
    buffer_header: str,
    buffer_source: str,
    readback_header: str,
    readback_source: str,
    context_header: str,
    context_source: str,
    shader_source: str,
    series: str,
    patch: str,
) -> None:
    bind = method(vertex, "void WGPUVertexBuffer::bind_as_texture(uint binding)")
    ordered = (
        "bool source_pending = false;",
        "size_used_get(),",
        "&source_pending);",
        "if (source.empty())",
    )
    for marker in ordered:
        if marker not in bind:
            raise ValueError(f"buffer-texture readback path lost {marker}")
    offsets = [bind.index(marker) for marker in ordered]
    if offsets != sorted(offsets):
        raise ValueError("readback pending intent is recorded outside the empty-read order")
    empty_start = bind.index("if (source.empty())")
    empty_block = bind[empty_start : bind.index("const GPUVertAttr", empty_start)]
    if empty_block.count("ctx->buffer_ssbo_bind(") != 1:
        raise ValueError("empty expanded-source read does not publish exactly one bind intent")
    for marker in (
        "WGPUContext::BufferSSBOBindKind::Sampler,",
        "nullptr,",
        "source_pending);",
    ):
        if marker not in empty_block:
            raise ValueError(f"empty expanded-source bind lost {marker}")

    for marker in (
        "size_t size,\n                            bool *r_pending = nullptr) const;",
        "bool *r_pending) const",
        "*r_pending = false;",
        "const readback::Ticket ticket = readback::kick_buffer(",
        "readback::RequestMode::Cache,\n        r_pending != nullptr);",
        "readback::ticket_status(ticket) == readback::TicketStatus::Pending",
    ):
        source = buffer_header if marker.endswith("nullptr) const;") else buffer_source
        if marker not in source:
            raise ValueError(f"buffer readback pending-state contract lost {marker}")

    for marker in (
        "RequestMode mode = RequestMode::Cache,\n                   bool redraw_on_ready = false);",
        "bool redraw_on_ready = false;",
        "pending->redraw_on_ready = pending->redraw_on_ready || redraw_on_ready;",
    ):
        source = readback_header if marker.endswith("false);") else readback_source
        if marker not in source:
            raise ValueError(f"readback redraw-owner contract lost {marker}")

    completion = method(
        readback_source,
        "void complete_pending(const std::shared_ptr<Pending> &pending,",
    )
    if completion.count("request_webgpu_redraw_retry();") != 1:
        raise ValueError("cache readback settlement does not publish exactly one redraw edge")
    for marker in (
        "pending->mode == RequestMode::Cache",
        "record.status = TicketStatus::Ready;",
        "publish_cache_redraw = pending->redraw_on_ready;",
    ):
        if marker not in completion:
            raise ValueError(f"cache readback readiness lost {marker}")
    if completion.index("record.status = TicketStatus::Ready;") >= completion.index(
        "publish_cache_redraw = pending->redraw_on_ready;"
    ):
        raise ValueError("cache redraw is published before successful readback readiness")

    for marker in (
        "bool pending_external = false;",
        "bool pending_external = false)",
        "pending_dependency, pending_external, kind, ++storage_bind_serial_",
    ):
        if context_header.count(marker) != 1:
            raise ValueError(f"bound-buffer external-pending contract lost {marker}")
    for marker in (
        "bool pending_external;",
        "record.pending_dependency,\n        record.pending_external",
        "item.second.pending_external ||",
    ):
        if context_source.count(marker) != 1:
            raise ValueError(f"bind-group external-pending assembly lost {marker}")
    predicate = context_source.index("item.second.pending_external ||")
    invalid = context_source.index("if (!buffer.valid())", predicate)
    if predicate >= invalid:
        raise ValueError("external pending state is checked after final-buffer validity")
    pending_block = context_source[predicate:invalid]
    for marker in ("claimed.insert(b);", "r_pending_bindings.push_back(b);", "continue;"):
        if marker not in pending_block:
            raise ValueError(f"external readback wait is not classified Pending: {marker}")

    completeness = method(shader_source, "bool WGPUShader::bind_group_entries_complete(")
    for marker in (
        "static std::unordered_set<std::string> pending_log_signatures;",
        "pending_log_signatures.size() < 128u",
        "pending_log_signatures.insert(signature).second",
        "[bw] WGPUWeb-bind-pending shader=%s surviving=%s assembled=%s pending=%s",
    ):
        if completeness.count(marker) != 1:
            raise ValueError(f"pending bind-group diagnostic lost {marker}")
    pending_status = completeness.index("BindGroupBindingStatus::Pending")
    pending_diagnostic = completeness.index("WGPUWeb-bind-pending", pending_status)
    pending_return = completeness.index("return false;", pending_diagnostic)
    if not pending_status < pending_diagnostic < pending_return:
        raise ValueError("pending bind-group diagnostic is outside the deferred-draw verdict")

    if series.count(PATCH.name) != 1:
        raise ValueError("numbered readback-readiness patch is not present exactly once")
    for path in (
        "source/blender/gpu/webgpu/wgpu_vertex_buffer.cc",
        "source/blender/gpu/webgpu/wgpu_buffer.hh",
        "source/blender/gpu/webgpu/wgpu_buffer.cc",
        "source/blender/gpu/webgpu/wgpu_readback.hh",
        "source/blender/gpu/webgpu/wgpu_readback.cc",
        "source/blender/gpu/webgpu/wgpu_context.hh",
        "source/blender/gpu/webgpu/wgpu_context.cc",
        "source/blender/gpu/webgpu/wgpu_shader.cc",
    ):
        if patch.count(f"diff --git a/{path} b/{path}") != 1:
            raise ValueError(f"numbered patch does not bind {path}")
    for marker in (
        "source_pending",
        "bool publish_cache_redraw = false;",
        "pending_external",
        "request_webgpu_redraw_retry",
        "WGPUWeb-bind-pending",
    ):
        if marker not in patch:
            raise ValueError(f"numbered patch lost {marker}")


def self_check(values: tuple[str, ...]) -> None:
    validate(*values)
    mutations: list[tuple[str, ...]] = []
    markers = (
        (0, "bool source_pending = false;"),
        (0, "source_pending);"),
        (1, "bool *r_pending = nullptr"),
        (2, "*r_pending = false;"),
        (2, "const readback::Ticket ticket = readback::kick_buffer("),
        (2, "readback::ticket_status(ticket) == readback::TicketStatus::Pending"),
        (3, "bool redraw_on_ready = false"),
        (4, "request_webgpu_redraw_retry();"),
        (4, "publish_cache_redraw = pending->redraw_on_ready;"),
        (5, "bool pending_external = false;"),
        (5, "bool pending_external = false)"),
        (6, "record.pending_dependency,\n        record.pending_external"),
        (6, "item.second.pending_external ||"),
        (7, "WGPUWeb-bind-pending shader=%s"),
        (8, PATCH.name),
        (9, "bool publish_cache_redraw = false;"),
    )
    for index, marker in markers:
        mutated = list(values)
        mutated[index] = mutated[index].replace(marker, "", 1)
        mutations.append(tuple(mutated))
    rejected = 0
    for mutation in mutations:
        try:
            validate(*mutation)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0I_BUFFER_TEXTURE_READBACK_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    values = (
        VERTEX.read_text(encoding="utf-8"),
        BUFFER_HEADER.read_text(encoding="utf-8"),
        BUFFER_SOURCE.read_text(encoding="utf-8"),
        READBACK_HEADER.read_text(encoding="utf-8"),
        READBACK_SOURCE.read_text(encoding="utf-8"),
        CONTEXT_HEADER.read_text(encoding="utf-8"),
        CONTEXT_SOURCE.read_text(encoding="utf-8"),
        SHADER_SOURCE.read_text(encoding="utf-8"),
        SERIES.read_text(encoding="utf-8"),
        PATCH.read_text(encoding="utf-8") if PATCH.exists() else "",
    )
    if args.self_check:
        self_check(values)
    else:
        validate(*values)
        print("P0I_BUFFER_TEXTURE_READBACK_SOURCE_PASS paths=8 patch=0301")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"P0I_BUFFER_TEXTURE_READBACK_SOURCE_FAIL {error}")
        raise SystemExit(1)
