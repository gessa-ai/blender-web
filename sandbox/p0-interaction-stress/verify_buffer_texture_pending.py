#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind the pending buffer-texture intent fix to canonical WebGPU source."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERTEX = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_vertex_buffer.cc"
CONTEXT_HEADER = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_context.hh"
CONTEXT_SOURCE = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_context.cc"
SERIES = ROOT / "patches/series"
PATCH = ROOT / "patches/0298-gpu-webgpu-pending-buffer-texture-bind-intent.patch"


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


def validate(vertex: str, header: str, context: str, series: str, patch: str) -> None:
    body = method(vertex, "void WGPUVertexBuffer::bind_as_texture(uint binding)")
    ordered = (
        "const bool needs_float_expansion =",
        "upload_data();",
        "webgpu::Buffer *binding_buffer = needs_float_expansion ?",
        "if (!buffer_.valid())",
        "if (buffer_.creation_pending_or_retryable())",
        "&buffer_);",
    )
    for marker in ordered:
        if marker not in body:
            raise ValueError(f"buffer-texture bind lost {marker}")
    offsets = [body.index(marker) for marker in ordered]
    if offsets != sorted(offsets):
        raise ValueError("primary pending intent is recorded outside upload order")
    if "upload_data();\n  if (!buffer_.valid()) {\n    return;" in body:
        raise ValueError("buffer-texture bind still drops primary allocation intent")
    if body.count("WGPUContext::BufferSSBOBindKind::Sampler,\n") < 4:
        raise ValueError("buffer-texture pending exits are not dependency-bound")
    if body.count("&buffer_texture_buffer_);") < 3:
        raise ValueError("expanded allocation/update pending exits lost their dependency")

    bound_struct = "const webgpu::Buffer *pending_dependency = nullptr;"
    signature = "const webgpu::Buffer *pending_dependency = nullptr)"
    initializer = "slot, buffer, pending_dependency, kind, ++storage_bind_serial_"
    for marker in (bound_struct, signature, initializer):
        if header.count(marker) != 1:
            raise ValueError(f"bound-buffer dependency contract lost {marker}")

    candidate = "const webgpu::Buffer *pending_dependency;"
    propagation = "record.buffer, record.pending_dependency"
    predicate = "item.second.pending_dependency->creation_pending_or_retryable()"
    for marker in (candidate, propagation, predicate):
        if context.count(marker) != 1:
            raise ValueError(f"bind-group dependency assembly lost {marker}")
    predicate_offset = context.index(predicate)
    invalid_offset = context.index("if (!buffer.valid())", predicate_offset)
    if predicate_offset >= invalid_offset:
        raise ValueError("derived pending dependency is checked after final-buffer validity")
    pending_block = context[predicate_offset:invalid_offset]
    for marker in ("claimed.insert(b);", "r_pending_bindings.push_back(b);", "continue;"):
        if marker not in pending_block:
            raise ValueError(f"derived pending dependency is not classified Pending: {marker}")

    if series.count(PATCH.name) != 1:
        raise ValueError("numbered patch is not present exactly once in patches/series")
    for path in (
        "source/blender/gpu/webgpu/wgpu_vertex_buffer.cc",
        "source/blender/gpu/webgpu/wgpu_context.hh",
        "source/blender/gpu/webgpu/wgpu_context.cc",
    ):
        if patch.count(f"diff --git a/{path} b/{path}") != 1:
            raise ValueError(f"numbered patch does not bind {path}")
    for marker in ("pending_dependency", "needs_float_expansion", "&buffer_texture_buffer_"):
        if marker not in patch:
            raise ValueError(f"numbered patch lost {marker}")


def self_check(vertex: str, header: str, context: str, series: str, patch: str) -> None:
    validate(vertex, header, context, series, patch)
    mutations = (
        (vertex.replace("if (buffer_.creation_pending_or_retryable())", "if (false)", 1),
         header, context, series, patch),
        (vertex.replace("webgpu::Buffer *binding_buffer = needs_float_expansion ?",
                        "webgpu::Buffer *binding_buffer = false ?", 1),
         header, context, series, patch),
        (vertex.replace("&buffer_texture_buffer_);", "nullptr);"),
         header, context, series, patch),
        (vertex, header.replace("const webgpu::Buffer *pending_dependency = nullptr;", "", 1),
         context, series, patch),
        (vertex, header.replace("const webgpu::Buffer *pending_dependency = nullptr)",
                                "const webgpu::Buffer *)", 1),
         context, series, patch),
        (vertex, header.replace("slot, buffer, pending_dependency, kind, ++storage_bind_serial_",
                                "slot, buffer, nullptr, kind, ++storage_bind_serial_", 1),
         context, series, patch),
        (vertex, header, context.replace("record.buffer, record.pending_dependency",
                                         "record.buffer, nullptr", 1),
         series, patch),
        (vertex, header, context.replace(
            "item.second.pending_dependency->creation_pending_or_retryable()", "false", 1),
         series, patch),
        (vertex, header, context, series.replace(PATCH.name, "0298-missing.patch", 1), patch),
        (vertex, header, context, series,
         patch.replace("needs_float_expansion", "lost_float_expansion")),
    )
    rejected = 0
    for mutation in mutations:
        try:
            validate(*mutation)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0I_PENDING_BUFFER_TEXTURE_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    values = (
        VERTEX.read_text(encoding="utf-8"),
        CONTEXT_HEADER.read_text(encoding="utf-8"),
        CONTEXT_SOURCE.read_text(encoding="utf-8"),
        SERIES.read_text(encoding="utf-8"),
        PATCH.read_text(encoding="utf-8") if PATCH.exists() else "",
    )
    if args.self_check:
        self_check(*values)
    else:
        validate(*values)
        print("P0I_PENDING_BUFFER_TEXTURE_SOURCE_PASS paths=3 patch=0298")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"P0I_PENDING_BUFFER_TEXTURE_SOURCE_FAIL {error}")
        raise SystemExit(1)
