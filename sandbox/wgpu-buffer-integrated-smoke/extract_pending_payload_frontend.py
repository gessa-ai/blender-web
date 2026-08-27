#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract the SSBO/UBO pending-payload frontend methods for a device-free contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


METHODS = (
    (
        "storage ensure",
        "bool WGPUStorageBuffer::ensure()",
        "\n\nWGPUStorageBuffer::~WGPUStorageBuffer()",
        ("buffer_.create_scoped(",),
    ),
    (
        "storage update",
        "void WGPUStorageBuffer::update(const void *data)",
        "\n\nvoid WGPUStorageBuffer::clear(uint32_t clear_value)",
        (
            "if (data == nullptr)",
            "const bool allocation_ready = ensure();",
            "buffer_.update_sub(",
            "allocation_ready || buffer_.creation_pending_or_retryable()",
        ),
    ),
    (
        "storage clear",
        "void WGPUStorageBuffer::clear(uint32_t clear_value)",
        "\n\nvoid WGPUStorageBuffer::copy_sub(",
        (
            "const bool allocation_ready = ensure();",
            "buffer_.update_sub(",
            "allocation_ready || buffer_.creation_pending_or_retryable()",
        ),
    ),
    (
        "storage bind",
        "void WGPUStorageBuffer::bind(int slot)",
        "\nvoid WGPUStorageBuffer::unbind()",
        (
            "const bool allocation_ready = ensure();",
            "allocation_ready || buffer_.creation_pending_or_retryable()",
            "ctx->storage_buffer_bind(slot, this);",
        ),
    ),
    (
        "uniform ensure",
        "bool WGPUUniformBuffer::ensure()",
        "\n\nbool WGPUUniformBuffer::ensure_updated()",
        ("buffer_.create_scoped(",),
    ),
    (
        "uniform deferred update",
        "bool WGPUUniformBuffer::ensure_updated()",
        "\n\nvoid WGPUUniformBuffer::update(const void *data)",
        (
            "const bool allocation_ready = ensure();",
            "buffer_.update_sub(",
            "MEM_SAFE_DELETE_VOID(data_);",
        ),
    ),
    (
        "uniform update",
        "void WGPUUniformBuffer::update(const void *data)",
        "\n\nvoid WGPUUniformBuffer::clear_to_zero()",
        (
            "if (data == nullptr)",
            "const bool allocation_ready = ensure();",
            "buffer_.update_sub(",
            "allocation_ready || buffer_.creation_pending_or_retryable()",
        ),
    ),
    (
        "uniform clear",
        "void WGPUUniformBuffer::clear_to_zero()",
        "\n\n/* Record the binding",
        (
            "const bool allocation_ready = ensure();",
            "buffer_.update_sub(",
            "allocation_ready || buffer_.creation_pending_or_retryable()",
        ),
    ),
)


def extract(source: str, label: str, start_marker: str, end_marker: str, required: tuple[str, ...]) -> str:
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
    return method


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-source", required=True, type=Path)
    parser.add_argument("--uniform-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    storage = args.storage_source.read_text(encoding="utf-8")
    uniform = args.uniform_source.read_text(encoding="utf-8")
    methods: list[str] = []
    for index, spec in enumerate(METHODS):
        source = storage if index < 4 else uniform
        methods.append(extract(source, *spec))

    payload = (
        "/* Generated from canonical SSBO/UBO frontend methods; do not edit. */\n"
        + "\n".join(methods)
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
        print(f"PENDING_PAYLOAD_EXTRACT_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
