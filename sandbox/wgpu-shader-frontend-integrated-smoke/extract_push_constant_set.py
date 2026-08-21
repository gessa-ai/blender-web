#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract the canonical push-constant packing method for a device-free contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


START = "void WGPUShader::push_constant_set("
END = "\nvoid WGPUShader::uniform_float("


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    if source.count(START) != 1 or source.count(END) != 1:
        raise RuntimeError("canonical push-constant method boundaries are not unique")
    start = source.index(START)
    end = source.index(END, start)
    method = source[start:end].rstrip() + "\n"
    required = (
        "for (const PushConstantSlot &slot : push_constants_)",
        "if (comp_len == 9) {",
        "constexpr uint32_t destination_column_stride = 4u * sizeof(float);",
        "matrix * destination_matrix_stride +",
        "const uint32_t dst_stride = (src_stride + 15u) & ~15u;",
        "push_constants_dirty_ = true;",
    )
    missing = [needle for needle in required if needle not in method]
    if missing:
        raise RuntimeError(f"canonical method lost required structure: {missing}")

    payload = (
        "/* Generated from the canonical wgpu_shader.cc; do not edit. */\n"
        + method
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
        print(f"PUSH_CONSTANT_EXTRACT_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
