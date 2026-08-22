#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract the canonical WebGPU point-restart cleanup for a device-free contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


START = "void WGPUIndexBuffer::strip_restart_indices()"
END = "\n\n}  // namespace blender::gpu"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    if source.count(START) != 1 or source.count(END) != 1:
        raise RuntimeError("canonical index-strip method boundaries are not unique")
    start = source.index(START)
    end = source.index(END, start)
    method = source[start:end].rstrip() + "\n"
    if method.count("{") != method.count("}") or not method.endswith("}\n"):
        raise RuntimeError("canonical index-strip method is structurally incomplete")
    required = (
        "uint32_t write_index = 0;",
        "indices[read_index] != RESTART_INDEX",
        "index_len_ = write_index;",
    )
    missing = [needle for needle in required if needle not in method]
    if missing:
        raise RuntimeError(f"canonical index-strip method lost required structure: {missing}")

    payload = (
        "/* Generated from canonical wgpu_index_buffer.cc; do not edit. */\n" + method
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
        print(f"INDEX_STRIP_EXTRACT_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
