#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract WebGPU's shipping dummy-vertex initializer for a device-free contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


METHOD_START = "wgpu::Buffer WGPUContext::dummy_vertex_buffer()"
METHOD_END = "\n\n/* --- Cross-format colour blit"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    for marker in (METHOD_START, METHOD_END):
        if source.count(marker) != 1:
            raise RuntimeError(f"canonical dummy-vertex boundary is not unique: {marker}")

    method_start = source.index(METHOD_START)
    method_end = source.index(METHOD_END, method_start)
    method = source[method_start:method_end].rstrip()
    required = (
        "if (dummy_vertex_buffer_ == nullptr)",
        "bd.size = 16;",
        "wgpu::BufferUsage::Vertex | wgpu::BufferUsage::CopyDst",
        "dummy_vertex_buffer_ = device_.CreateBuffer(&bd);",
        "return dummy_vertex_buffer_;",
    )
    missing = [needle for needle in required if needle not in method]
    if missing:
        raise RuntimeError(f"canonical dummy-vertex policy lost required structure: {missing}")

    extracted = method.replace("dummy_vertex_buffer_", "context.dummy_vertex_buffer_")
    extracted = extracted.replace("device_", "context.device_")
    extracted = extracted.replace("queue_", "context.queue_")
    extracted = extracted.replace(
        METHOD_START,
        "static wgpu::Buffer dummy_vertex_buffer_for_test(DummyVertexContext &context)",
        1,
    )

    payload = (
        "/* Generated from the canonical wgpu_context.cc; do not edit. */\n"
        + extracted
        + "\n"
    ).encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() == payload:
        return 0
    temporary = args.output.with_name(f".{args.output.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print(f"DUMMY_VERTEX_EXTRACT_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
