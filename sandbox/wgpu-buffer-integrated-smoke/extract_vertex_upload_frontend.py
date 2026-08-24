#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract the shipping VBO mutation/upload methods for a device-free contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


METHODS = (
    (
        "frontend attribute mutation",
        "void GPU_vertbuf_attr_set(VertBuf *verts, uint a_idx, uint v_idx, const void *data)",
        "\n\nvoid GPU_vertbuf_attr_fill(",
        "void frontend_attr_set(VertexFrontendHarness *verts, uint a_idx, uint v_idx, const void *data)",
        (
            "verts->flag |= GPU_VERTBUF_DATA_DIRTY;",
            "memcpy(verts->data<uchar>().data() + a->offset + v_idx * format->stride",
        ),
    ),
    (
        "WebGPU initial upload",
        "void WGPUVertexBuffer::upload_data()",
        "\n\nvoid WGPUVertexBuffer::update_sub(",
        "void VertexFrontendHarness::upload_data()",
        (
            "if (flag & GPU_VERTBUF_DATA_DIRTY)",
            "buffer_texture_buffer_dirty_ = true;",
            "upload_transaction_.started()",
            "upload_transaction_.reset()",
            "flag &= ~GPU_VERTBUF_DATA_DIRTY;",
        ),
    ),
    (
        "WebGPU float buffer-texture bind",
        "void WGPUVertexBuffer::bind_as_texture(uint binding)",
        "\n\nvoid WGPUVertexBuffer::wrap_handle(",
        "void VertexFrontendHarness::bind_as_texture(uint binding)",
        (
            "buffer_texture_upload_transaction_.started()",
            "buffer_texture_upload_transaction_.reset()",
            "buffer_texture_buffer_dirty_ = false;",
            "expanded.data()",
            "buffer_texture_upload_transaction_",
        ),
    ),
)


def extract(
    source: str,
    label: str,
    start_marker: str,
    end_marker: str,
    replacement: str,
    required: tuple[str, ...],
) -> str:
    if source.count(start_marker) != 1 or source.count(end_marker) != 1:
        raise RuntimeError(f"canonical {label} method boundaries are not unique")
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    method = source[start:end].rstrip() + "\n"
    if method.count("{") != method.count("}") or not method.endswith("}\n"):
        raise RuntimeError(f"canonical {label} method is structurally incomplete")
    missing = [needle for needle in required if needle not in method]
    if missing:
        raise RuntimeError(f"canonical {label} method lost required structure: {missing}")
    return method.replace(start_marker, replacement, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend-source", required=True, type=Path)
    parser.add_argument("--webgpu-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    frontend_source = args.frontend_source.read_text(encoding="utf-8")
    webgpu_source = args.webgpu_source.read_text(encoding="utf-8")
    sources = (frontend_source, webgpu_source, webgpu_source)
    methods = [extract(source, *spec) for source, spec in zip(sources, METHODS, strict=True)]
    payload = (
        "/* Generated from canonical vertex frontend/WebGPU methods; do not edit. */\n"
        "namespace blender::gpu::vertex_generation_contract {\n"
        + "\n".join(methods)
        + "}  // namespace blender::gpu::vertex_generation_contract\n"
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
        print(f"VERTEX_UPLOAD_FRONTEND_EXTRACT_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
