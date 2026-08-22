#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract native GHOST's exact optional-feature selector for a device-free contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys


BLOCK_START = "  std::vector<wgpu::FeatureName> required_features;\n"
BLOCK_END = "  device_desc.requiredFeatureCount = required_features.size();"
EXPECTED_FEATURES = (
    "Unorm16TextureFormats",
    "RG11B10UfloatRenderable",
    "Float32Filterable",
    "TextureComponentSwizzle",
    "TextureCompressionBC",
    "Depth32FloatStencil8",
    "TextureFormatsTier1",
    "TextureFormatsTier2",
    "ClipDistances",
    "DualSourceBlending",
)
FEATURE_PAIR = re.compile(
    r"  if \(adapter_\.HasFeature\(wgpu::FeatureName::([A-Za-z0-9_]+)\)\) \{\n"
    r"    required_features\.push_back\(wgpu::FeatureName::([A-Za-z0-9_]+)\);\n"
    r"  \}\n"
)


def extract_payload(source: str) -> bytes:
    for marker in (BLOCK_START, BLOCK_END):
        if source.count(marker) != 1:
            raise RuntimeError(f"optional-feature boundary is not unique: {marker.strip()}")

    start = source.index(BLOCK_START)
    end = source.index(BLOCK_END, start)
    block = source[start:end]
    pairs = FEATURE_PAIR.findall(block)
    if any(guard != request for guard, request in pairs):
        raise RuntimeError(f"optional-feature guard/request mismatch: {pairs}")
    features = tuple(guard for guard, _request in pairs)
    if features != EXPECTED_FEATURES:
        raise RuntimeError(
            "optional-feature census/order mismatch: "
            f"expected={EXPECTED_FEATURES} actual={features}"
        )
    if FEATURE_PAIR.sub("", block) != BLOCK_START:
        raise RuntimeError("optional-feature selector contains unverified statements")

    body = block[len(BLOCK_START) :].replace("adapter_", "adapter")
    return (
        "/* Generated from staged GHOST_ContextWGPU.cc; do not edit. */\n"
        "static std::vector<wgpu::FeatureName> select_optional_features(const Adapter &adapter)\n"
        "{\n"
        "  std::vector<wgpu::FeatureName> required_features;\n"
        f"{body}"
        "  return required_features;\n"
        "}\n"
    ).encode("utf-8")


def selfcheck() -> None:
    pairs = "".join(
        f"  if (adapter_.HasFeature(wgpu::FeatureName::{feature})) {{\n"
        f"    required_features.push_back(wgpu::FeatureName::{feature});\n"
        "  }\n"
        for feature in EXPECTED_FEATURES
    )
    source = "fixture prefix\n" + BLOCK_START + pairs + BLOCK_END + "\nfixture suffix\n"
    payload = extract_payload(source)
    if (
        b"wgpu::FeatureName::Float32Filterable" not in payload
        or b"wgpu::FeatureName::TextureComponentSwizzle" not in payload
        or b"wgpu::FeatureName::TextureCompressionBC" not in payload
    ):
        raise RuntimeError("positive self-check lost a required texture feature")

    swizzle_pair = (
        "  if (adapter_.HasFeature(wgpu::FeatureName::TextureComponentSwizzle)) {\n"
        "    required_features.push_back(wgpu::FeatureName::TextureComponentSwizzle);\n"
        "  }\n"
    )
    bc_pair = (
        "  if (adapter_.HasFeature(wgpu::FeatureName::TextureCompressionBC)) {\n"
        "    required_features.push_back(wgpu::FeatureName::TextureCompressionBC);\n"
        "  }\n"
    )
    mutations = (
        source.replace(swizzle_pair, "", 1),
        source.replace(
            "required_features.push_back(wgpu::FeatureName::TextureComponentSwizzle);",
            "required_features.push_back(wgpu::FeatureName::RG11B10UfloatRenderable);",
            1,
        ),
        source.replace(swizzle_pair, swizzle_pair + swizzle_pair, 1),
        source.replace(bc_pair, "", 1),
        source.replace(
            "required_features.push_back(wgpu::FeatureName::TextureCompressionBC);",
            "required_features.push_back(wgpu::FeatureName::Depth32FloatStencil8);",
            1,
        ),
        source.replace(bc_pair, bc_pair + bc_pair, 1),
        source.replace(swizzle_pair, swizzle_pair + "  audit_side_effect();\n", 1),
        source.replace(BLOCK_END, BLOCK_END + "\n" + BLOCK_END, 1),
    )
    for index, mutation in enumerate(mutations, start=1):
        try:
            extract_payload(mutation)
        except RuntimeError:
            continue
        raise RuntimeError(f"malformed optional-feature mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    if args.selfcheck:
        if args.source is not None or args.output is not None:
            parser.error("--selfcheck does not accept --source or --output")
        selfcheck()
        print("T3 OPTIONAL FEATURE EXTRACTOR SELFCHECK PASS cases=9")
        return 0
    if args.source is None or args.output is None:
        parser.error("--source and --output are required without --selfcheck")

    generated = extract_payload(args.source.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() == generated:
        return 0
    temporary = args.output.with_name(f".{args.output.name}.{os.getpid()}.tmp")
    temporary.write_bytes(generated)
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print(f"T3_OPTIONAL_FEATURE_EXTRACT_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
