#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract the canonical WebGPU buffer update method for a device-free contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


START = "bool Buffer::update_allocation("
END = "\n\nstd::vector<uint8_t> Buffer::read("


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    if source.count(START) != 1 or source.count(END) != 1:
        raise RuntimeError("canonical buffer-update method boundaries are not unique")
    start = source.index(START)
    end = source.index(END, start)
    method = source[start:end].rstrip() + "\n"
    if method.count("{") != method.count("}") or not method.endswith("}\n"):
        raise RuntimeError("canonical buffer-update method is structurally incomplete")
    required = (
        "kWriteBufferStagingThreshold",
        "allocation_cache_.lookup(kAllocationKey)",
        "pending_updates_->retain(",
        "queue_write_buffer_scoped(context.instance,",
        "wgpu::Buffer staging = context.device.CreateBuffer(&sd);",
        "staging.GetMappedRange(0, size)",
        "command_encode_submit_scoped(context.instance,",
        "staging, 0, allocation.handle, offset, size",
    )
    missing = [needle for needle in required if needle not in method]
    if missing:
        raise RuntimeError(f"canonical buffer-update method lost required structure: {missing}")

    method = method.replace("Buffer::update_allocation(",
                            "BufferUpdateHarness::update_allocation(")
    method = method.replace("bool Buffer::update_sub(",
                            "bool BufferUpdateHarness::update_sub(", 1)
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
        print(f"BUFFER_UPDATE_EXTRACT_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
