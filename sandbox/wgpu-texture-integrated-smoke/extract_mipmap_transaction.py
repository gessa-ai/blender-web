#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract the shipping WebGPU mipmap method for a device-free transaction test."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


START = "void WGPUTexture::generate_mipmap()"
END = "\n\nvoid WGPUTexture::swizzle_set("


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    if source.count(START) != 1 or source.count(END) != 1:
        raise RuntimeError("canonical mipmap method boundaries are not unique")
    start = source.index(START)
    end = source.index(END, start)
    method = source[start:end].rstrip() + "\n"
    if method.count("{") != method.count("}") or not method.endswith("}\n"):
        raise RuntimeError("canonical mipmap method is structurally incomplete")

    required = (
        "device.CreateShaderModule(&module_desc)",
        "device.CreateRenderPipeline(&pipeline_desc)",
        "webgpu::command_encode_submit_scoped(",
        "ctx->queue_scheduler_get()",
        "int(mip - 1), int(layer), TextureViewValidationScope::EnclosingCommand)",
        "int(mip), int(layer), TextureViewValidationScope::EnclosingCommand)",
        "device.CreateBindGroup(&bind_desc)",
        "enc.BeginRenderPass(&pass_desc)",
        '"texture mipmap generation"',
    )
    missing = [needle for needle in required if needle not in method]
    if missing:
        raise RuntimeError(f"canonical mipmap method lost required structure: {missing}")

    method = method.replace(
        START, "void MipmapHarness::generate_mipmap()", 1
    )
    payload = (
        "/* Generated from canonical wgpu_texture.cc; do not edit. */\n"
        "namespace mipmap_contract {\n"
        + method
        + "}  // namespace mipmap_contract\n"
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
        print(f"MIPMAP_TRANSACTION_EXTRACT_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
