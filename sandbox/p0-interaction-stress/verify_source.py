#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind the P0-I typed-geometry pending-bind fix to canonical WebGPU source."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERTEX = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_vertex_buffer.cc"
INDEX = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_index_buffer.cc"
SERIES = ROOT / "patches/series"
PATCH = ROOT / "patches/0297-gpu-webgpu-pending-geometry-bind-intent.patch"


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


def validate(vertex: str, index: str, series: str, patch: str) -> None:
    pending_guard = "if (!(buffer_.valid() || buffer_.creation_pending_or_retryable()))"
    bind_call = "ctx->buffer_ssbo_bind("
    for label, source, signature in (
        ("vertex", vertex, "void WGPUVertexBuffer::bind_as_ssbo(uint binding)"),
        ("index", index, "void WGPUIndexBuffer::bind_as_ssbo(uint binding)"),
    ):
        body = method(source, signature)
        for marker in ("upload_data();", pending_guard, bind_call):
            if body.count(marker) != 1:
                raise ValueError(f"{label} pending bind method lost {marker}")
        if not (body.index("upload_data();") < body.index(pending_guard) < body.index(bind_call)):
            raise ValueError(f"{label} records bind intent outside the allocation transaction")
        if "if (!buffer_.valid()) {\n    return;\n  }" in body:
            raise ValueError(f"{label} still drops pending bind intent")

    patch_name = PATCH.name
    if series.count(patch_name) != 1:
        raise ValueError("numbered patch is not present exactly once in patches/series")
    for path in (
        "source/blender/gpu/webgpu/wgpu_vertex_buffer.cc",
        "source/blender/gpu/webgpu/wgpu_index_buffer.cc",
    ):
        if patch.count(f"diff --git a/{path} b/{path}") != 1:
            raise ValueError(f"numbered patch does not bind {path}")
    if patch.count("creation_pending_or_retryable()") != 2:
        raise ValueError("numbered patch does not preserve both pending geometry intents")


def self_check(vertex: str, index: str, series: str, patch: str) -> None:
    validate(vertex, index, series, patch)
    mutations = (
        (vertex.replace(" || buffer_.creation_pending_or_retryable()", "", 1), index, series, patch),
        (vertex, index.replace(" || buffer_.creation_pending_or_retryable()", "", 1), series, patch),
        (vertex.replace("ctx->buffer_ssbo_bind(", "ctx->lost_buffer_ssbo_bind(", 1),
         index, series, patch),
        (vertex, index.replace("ctx->buffer_ssbo_bind(", "ctx->lost_buffer_ssbo_bind(", 1),
         series, patch),
        (vertex, index, series.replace(PATCH.name, "0297-missing.patch", 1), patch),
        (vertex, index, series, patch.replace("creation_pending_or_retryable()", "valid()", 1)),
    )
    rejected = 0
    for mutation in mutations:
        try:
            validate(*mutation)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0I_PENDING_GEOMETRY_BIND_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    vertex = VERTEX.read_text(encoding="utf-8")
    index = INDEX.read_text(encoding="utf-8")
    series = SERIES.read_text(encoding="utf-8")
    patch = PATCH.read_text(encoding="utf-8") if PATCH.exists() else ""
    if args.self_check:
        self_check(vertex, index, series, patch)
    else:
        validate(vertex, index, series, patch)
        print("P0I_PENDING_GEOMETRY_BIND_SOURCE_PASS paths=2 patch=0297")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"P0I_PENDING_GEOMETRY_BIND_SOURCE_FAIL {error}")
        raise SystemExit(1)
