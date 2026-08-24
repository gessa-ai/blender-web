#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract WebGPU's shipping sampler descriptor policy for a device-free contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


ADDRESS_START = "static wgpu::AddressMode to_wgpu_address_mode("
SAMPLER_START = "wgpu::Sampler WGPUContext::get_sampler("
DESCRIPTOR_START = "  wgpu::SamplerDescriptor d = {};"
DESCRIPTOR_END = (
    '\n  return sampler_cache_.get_or_create(instance_, device_, key, "sampler creation", [&]() {'
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    for marker in (ADDRESS_START, SAMPLER_START, DESCRIPTOR_START, DESCRIPTOR_END):
        if source.count(marker) != 1:
            raise RuntimeError(f"canonical sampler boundary is not unique: {marker}")

    address_start = source.index(ADDRESS_START)
    sampler_start = source.index(SAMPLER_START, address_start)
    address_helper = source[address_start:sampler_start].rstrip()
    descriptor_start = source.index(DESCRIPTOR_START, sampler_start)
    descriptor_end = source.index(DESCRIPTOR_END, descriptor_start)
    descriptor_body = source[descriptor_start:descriptor_end].rstrip()

    required = (
        "case GPU_SAMPLER_EXTEND_MODE_REPEAT:",
        "d.maxAnisotropy = 1;",
        "state.filtering & GPU_SAMPLER_FILTERING_LINEAR",
        "state.filtering & GPU_SAMPLER_FILTERING_MIPMAP",
        "state.filtering & GPU_SAMPLER_FILTERING_ANISOTROPIC_ENABLE",
        "d.maxAnisotropy = uint16_t(GPU_anisotropic_samples_get(state.filtering));",
    )
    extracted = address_helper + "\n" + descriptor_body
    missing = [needle for needle in required if needle not in extracted]
    if missing:
        raise RuntimeError(f"canonical sampler policy lost required structure: {missing}")

    payload = (
        "/* Generated from the canonical wgpu_context.cc; do not edit. */\n"
        + address_helper
        + "\n\nstatic wgpu::SamplerDescriptor sampler_descriptor_for_test("
        + "const GPUSamplerState &state)\n{\n"
        + descriptor_body
        + "\n  return d;\n}\n"
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
        print(f"SAMPLER_DESCRIPTOR_EXTRACT_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
