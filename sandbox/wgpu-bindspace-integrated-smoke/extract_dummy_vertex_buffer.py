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
HELPER_START = "template<typename DeviceT> inline auto dummy_vertex_buffer_create(DeviceT &device)"
HELPER_END = "\n\n/** Publish a short-lived WebGPU handle"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--helper-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    for marker in (METHOD_START, METHOD_END):
        if source.count(marker) != 1:
            raise RuntimeError(f"canonical dummy-vertex boundary is not unique: {marker}")

    method_start = source.index(METHOD_START)
    method_end = source.index(METHOD_END, method_start)
    method = source[method_start:method_end].rstrip()
    required_method = (
        "static constexpr uint8_t cache_key = 0;",
        "if (instance_ == nullptr || device_ == nullptr)",
        "return dummy_vertex_buffer_cache_.get_or_create(",
        'instance_, device_, cache_key, "dummy vertex buffer creation", [&]() {',
        "return webgpu::dummy_vertex_buffer_create(device_);",
    )
    missing = [needle for needle in required_method if needle not in method]
    if missing:
        raise RuntimeError(f"canonical dummy-vertex cache policy lost required structure: {missing}")

    helper_source = args.helper_source.read_text(encoding="utf-8")
    for marker in (HELPER_START, HELPER_END):
        if helper_source.count(marker) != 1:
            raise RuntimeError(f"canonical dummy-vertex helper boundary is not unique: {marker}")
    helper_start = helper_source.index(HELPER_START)
    helper_end = helper_source.index(HELPER_END, helper_start)
    helper = helper_source[helper_start:helper_end].rstrip()
    required_helper = (
        "static constexpr float default_attribute[4] = {0.0f, 0.0f, 0.0f, 1.0f};",
        "descriptor.size = sizeof(default_attribute);",
        "descriptor.usage = wgpu::BufferUsage::Vertex | wgpu::BufferUsage::CopyDst;",
        "descriptor.mappedAtCreation = true;",
        "auto candidate = device.CreateBuffer(&descriptor);",
        "void *mapped = candidate.GetMappedRange(0, sizeof(default_attribute));",
        "std::memcpy(mapped, default_attribute, sizeof(default_attribute));",
        "candidate.Unmap();",
    )
    missing = [needle for needle in required_helper if needle not in helper]
    if missing:
        raise RuntimeError(f"canonical dummy-vertex helper lost required structure: {missing}")

    payload = (
        "/* Generated from the canonical wgpu_context.cc and wgpu_common.hh; do not edit. */\n"
        "namespace webgpu {\n"
        + helper
        + "\n}  // namespace webgpu\n\n"
        "static wgpu::Buffer dummy_vertex_buffer_for_test(DummyVertexContext &context)\n"
        "{\n"
        "  if (context.dummy_vertex_buffer_ == nullptr) {\n"
        "    context.dummy_vertex_buffer_ = webgpu::dummy_vertex_buffer_create(context.device_);\n"
        "  }\n"
        "  return context.dummy_vertex_buffer_;\n"
        "}\n"
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
