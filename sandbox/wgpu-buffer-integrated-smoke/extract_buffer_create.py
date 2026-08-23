#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract the scoped canonical WebGPU buffer creation method for a device-free contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


START = "bool Buffer::create_scoped("
END = "\n\nbool Buffer::update_allocation("


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    if source.count(START) != 1 or source.count(END) != 1:
        raise RuntimeError("canonical scoped buffer-create method boundaries are not unique")
    start = source.index(START)
    end = source.index(END, start)
    method = source[start:end].rstrip() + "\n"
    if method.count("{") != method.count("}") or not method.endswith("}\n"):
        raise RuntimeError("canonical scoped buffer-create method is structurally incomplete")
    required = (
        "instance == nullptr || device == nullptr",
        "pending_updates_->begin(allocated_size)",
        "allocation_cache_.get_or_create(",
        "candidate.handle = device.CreateBuffer(&descriptor);",
        "candidate.handle.GetMappedRange(0, allocated_size)",
        "candidate.size = allocated_size;",
        "pending_updates->replay(",
        "return allocation != nullptr;",
    )
    missing = [needle for needle in required if needle not in method]
    if missing:
        raise RuntimeError(
            f"canonical scoped buffer-create method lost required structure: {missing}"
        )

    method = method.replace(
        "bool Buffer::create_scoped(",
        "bool BufferCreateHarness::create_scoped(",
        1,
    )
    method = method.replace(
        "Buffer::update_allocation(",
        "BufferCreateHarness::update_allocation(",
        1,
    )
    payload = (
        "/* Generated from canonical wgpu_buffer.cc; do not edit. */\n" + method
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
        print(f"BUFFER_CREATE_EXTRACT_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
