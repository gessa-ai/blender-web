#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed source contract for the owned full-viewport depth-cache request."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PIN = "fbe6228777e7d9afefcd61a413844e790ae75db7"
SOURCE_PATHS = (
    "source/blender/editors/include/ED_view3d.hh",
    "source/blender/editors/space_view3d/view3d_draw.cc",
    "source/blender/gpu/GPU_framebuffer.hh",
    "source/blender/gpu/GPU_readback.hh",
    "source/blender/gpu/GPU_texture.hh",
)


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def require_ordered(text: str, needles: tuple[str, ...], label: str) -> None:
    position = -1
    for needle in needles:
        next_position = text.find(needle, position + 1)
        require(next_position >= 0, f"{label}: missing {needle!r}")
        require(next_position > position, f"{label}: order drifted at {needle!r}")
        position = next_position


def braced_definition(text: str, signature: str, label: str) -> str:
    start = text.find(signature)
    require(start >= 0, f"{label}: signature missing")
    brace = text.find("{", start + len(signature))
    require(brace >= 0, f"{label}: opening brace missing")
    depth = 0
    index = brace
    state = "code"
    while index < len(text):
        char = text[index]
        pair = text[index : index + 2]
        if state == "code":
            if pair == "//":
                state = "line_comment"
                index += 2
                continue
            if pair == "/*":
                state = "block_comment"
                index += 2
                continue
            if char == '"':
                state = "string"
            elif char == "'":
                state = "character"
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        elif state == "line_comment":
            if char == "\n":
                state = "code"
        elif state == "block_comment":
            if pair == "*/":
                state = "code"
                index += 2
                continue
        elif state == "string":
            if char == "\\":
                index += 2
                continue
            if char == '"':
                state = "code"
        elif state == "character":
            if char == "\\":
                index += 2
                continue
            if char == "'":
                state = "code"
        index += 1
    raise ContractError(f"{label}: unbalanced braces")


def load_sources(source_root: Path) -> dict[str, str]:
    sources: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = source_root / relative
        require(path.is_file(), f"source missing: {relative}")
        sources[relative] = path.read_text(encoding="utf-8")
    return sources


def source_digest(sources: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for relative in SOURCE_PATHS:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sources[relative].encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def verify(sources: dict[str, str]) -> dict[str, object]:
    header = sources["source/blender/editors/include/ED_view3d.hh"]
    draw = sources["source/blender/editors/space_view3d/view3d_draw.cc"]
    framebuffer_header = sources["source/blender/gpu/GPU_framebuffer.hh"]
    readback_header = sources["source/blender/gpu/GPU_readback.hh"]
    texture_header = sources["source/blender/gpu/GPU_texture.hh"]

    api = braced_definition(header, "class ViewportDepthCacheSession", "depth-cache API")
    for needle in (
        "enum class ReadbackState",
        "struct Impl;",
        "Impl *impl_ = nullptr;",
        "ViewportDepthCacheSession(const ViewportDepthCacheSession &) = delete;",
        "bool init(ARegion *region);",
        "ReadbackState state();",
        "ViewDepths *take(ARegion *region);",
    ):
        require(needle in api, f"depth-cache API missing {needle!r}")

    impl = braced_definition(
        draw, "struct ViewportDepthCacheSession::Impl", "depth-cache implementation state"
    )
    for needle in (
        "ARegion *region = nullptr;",
        "RegionView3D *region_view = nullptr;",
        "GPUReadback *readback = nullptr;",
        "int region_size[2] = {0, 0};",
        "int texture_size[2] = {0, 0};",
        "float viewinv[4][4] = {};",
        "float winmat[4][4] = {};",
        "size_t expected_size = 0;",
        "ReadbackState readback_state = ReadbackState::Failed;",
    ):
        require(needle in impl, f"depth-cache state missing {needle!r}")

    destructor = braced_definition(
        draw,
        "ViewportDepthCacheSession::~ViewportDepthCacheSession()",
        "depth-cache destructor",
    )
    require_ordered(
        destructor,
        ("if (impl_ != nullptr)", "GPU_readback_cancel(impl_->readback);", "MEM_delete(impl_);"),
        "owned cancellation",
    )

    init = braced_definition(
        draw, "bool ViewportDepthCacheSession::init(ARegion *region)", "depth-cache init"
    )
    require_ordered(
        init,
        (
            "if (impl_ != nullptr)",
            "GPU_readback_cancel(impl_->readback);",
            "region == nullptr || region->regiondata == nullptr",
            "GPUViewport *viewport = WM_draw_region_get_viewport(region);",
            "gpu::Texture *depth_tx =",
            "GPU_texture_width(depth_tx)",
            "texture_width > int(std::numeric_limits<unsigned short>::max())",
            "texture_height > int(std::numeric_limits<unsigned short>::max())",
            "size_t(std::numeric_limits<int>::max()) / height",
            "std::numeric_limits<size_t>::max() / height",
            "std::numeric_limits<size_t>::max() / sizeof(float)",
            "copy_m4_m4(impl->viewinv",
            "copy_m4_m4(impl->winmat",
            "impl->expected_size = width * height * sizeof(float);",
            "impl->readback = GPU_texture_read_async(depth_tx, GPU_DATA_FLOAT, 0);",
            "impl->readback_state = ReadbackState::Pending;",
            "impl_ = impl;",
            "return state() != ReadbackState::Failed;",
        ),
        "exact full-texture request",
    )
    require("GPU_texture_read(depth_tx" not in init, "depth-cache init blocks synchronously")

    state = braced_definition(
        draw,
        "ViewportDepthCacheSession::ReadbackState ViewportDepthCacheSession::state()",
        "depth-cache state poll",
    )
    require_ordered(
        state,
        (
            "GPU_readback_status(impl_->readback)",
            "status == GPU_READBACK_PENDING",
            "status != GPU_READBACK_READY",
            "GPU_readback_size(impl_->readback) != impl_->expected_size",
            "GPU_readback_cancel(impl_->readback);",
            "impl_->readback_state = ReadbackState::Failed;",
            "impl_->readback_state = ReadbackState::Ready;",
        ),
        "terminal size validation",
    )

    take = braced_definition(
        draw,
        "ViewDepths *ViewportDepthCacheSession::take(ARegion *region)",
        "depth-cache transfer",
    )
    for needle in (
        "region != impl_->region",
        "region->regiondata != impl_->region_view",
        "region->winx != impl_->region_size[0]",
        "region->winy != impl_->region_size[1]",
        "!equals_m4m4(static_cast<RegionView3D *>(region->regiondata)->viewinv, impl_->viewinv)",
        "!equals_m4m4(static_cast<RegionView3D *>(region->regiondata)->winmat, impl_->winmat)",
    ):
        require(needle in take, f"producing-view guard missing {needle!r}")
    require_ordered(
        take,
        (
            "ViewDepths *depths = MEM_new_zeroed<ViewDepths>",
            "MEM_new_array_uninitialized<float>(pixel_count",
            "GPU_readback_consume(\n"
            "          impl_->readback, depths->depths, pixel_count * sizeof(float))",
            "depths->depth_range[0] = 0.0;",
            "depths->depth_range[1] = 1.0;",
            "MEM_delete(impl_);",
            "impl_ = nullptr;",
            "return depths;",
        ),
        "one-shot owned transfer",
    )

    for needle in (
        "GPUReadback *GPU_texture_read_async(",
        "GPUReadback *GPU_framebuffer_read_depth_async(",
        "bool GPU_readback_consume(GPUReadback *&readback",
        "void GPU_readback_cancel(GPUReadback *&readback)",
    ):
        require(
            needle in texture_header or needle in framebuffer_header or needle in readback_header,
            f"owned readback dependency missing {needle!r}",
        )

    require(
        "GPU_texture_read(depth_tx, GPU_DATA_FLOAT, 0)" in draw,
        "native synchronous depth-cache fallback missing",
    )

    return {
        "schema": 1,
        "pin": PIN,
        "verdict": "PASS",
        "contracts": {
            "owned_full_viewport_request": True,
            "native_immediate_completion": True,
            "pending_event_loop_settlement": True,
            "exact_byte_count_validation": True,
            "producing_view_guard": True,
            "one_shot_depth_cache_transfer": True,
            "failure_cancellation": True,
            "live_hardware_receipt": False,
        },
        "converted_primitive": "viewport_depth_cache",
        "remaining_sync_families": ["depth_cache", "window_capture"],
        "source_count": len(SOURCE_PATHS),
        "source_sha256": source_digest(sources),
    }


def replace_once(sources: dict[str, str], relative: str, old: str, new: str) -> dict[str, str]:
    mutated = dict(sources)
    require(mutated[relative].count(old) == 1, f"mutation anchor drifted: {old!r}")
    mutated[relative] = mutated[relative].replace(old, new, 1)
    return mutated


def selfcheck(sources: dict[str, str]) -> None:
    header = "source/blender/editors/include/ED_view3d.hh"
    draw = "source/blender/editors/space_view3d/view3d_draw.cc"
    mutations = (
        (header, "class ViewportDepthCacheSession", "class ViewportDepthCacheBlockingSession"),
        (draw, "GPU_texture_read_async(depth_tx, GPU_DATA_FLOAT, 0)",
         "GPU_texture_read(depth_tx, GPU_DATA_FLOAT, 0)"),
        (draw, "texture_width > int(std::numeric_limits<unsigned short>::max())",
         "texture_width > std::numeric_limits<int>::max()"),
        (draw,
         "const size_t height = size_t(texture_height);\n"
         "  if (width > size_t(std::numeric_limits<int>::max()) / height ||\n"
         "      width > std::numeric_limits<size_t>::max() / height ||\n"
         "      width * height > std::numeric_limits<size_t>::max() / sizeof(float))",
         "const size_t height = size_t(texture_height);\n"
         "  if (width > size_t(std::numeric_limits<int>::max()) / height ||\n"
         "      width > std::numeric_limits<size_t>::max() / height ||\n"
         "      width * height > std::numeric_limits<size_t>::max() / 1)"),
        (draw, "status != GPU_READBACK_READY ||\n"
         "      GPU_readback_size(impl_->readback) != impl_->expected_size",
         "status != GPU_READBACK_READY ||\n"
         "      GPU_readback_size(impl_->readback) < impl_->expected_size"),
        (draw,
         "state() != ReadbackState::Ready || region == nullptr || region != impl_->region ||\n"
         "      region->regiondata != impl_->region_view",
         "state() != ReadbackState::Ready || region == nullptr || region != impl_->region ||\n"
         "      false /* no view owner guard */"),
        (draw,
         "state() != ReadbackState::Ready || region == nullptr || region != impl_->region ||\n"
         "      region->regiondata != impl_->region_view || region->winx != impl_->region_size[0] ||\n"
         "      region->winy != impl_->region_size[1] ||\n"
         "      !equals_m4m4(static_cast<RegionView3D *>(region->regiondata)->viewinv, impl_->viewinv) ||\n"
         "      !equals_m4m4(static_cast<RegionView3D *>(region->regiondata)->winmat, impl_->winmat)",
         "state() != ReadbackState::Ready || region == nullptr || region != impl_->region ||\n"
         "      region->regiondata != impl_->region_view || region->winx != impl_->region_size[0] ||\n"
         "      region->winy != impl_->region_size[1] ||\n"
         "      !equals_m4m4(static_cast<RegionView3D *>(region->regiondata)->viewinv, impl_->viewinv) ||\n"
         "      false /* no projection guard */"),
        (draw,
         "GPU_readback_consume(\n"
         "          impl_->readback, depths->depths, pixel_count * sizeof(float))",
         "GPU_readback_consume(\n"
         "          nullptr, depths->depths, pixel_count * sizeof(float))"),
        (draw, "ViewportDepthCacheSession::~ViewportDepthCacheSession()",
         "ViewportDepthCacheSession::~ViewportDepthCacheSessionUnsafe()"),
    )
    for index, (relative, old, new) in enumerate(mutations, 1):
        mutated = replace_once(sources, relative, old, new)
        try:
            verify(mutated)
        except ContractError:
            continue
        raise ContractError(f"mutation {index} did not fail closed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    try:
        sources = load_sources(args.source_root)
        result = verify(sources)
        if args.selfcheck:
            selfcheck(sources)
    except ContractError as exc:
        raise SystemExit(f"M5_DEPTH_CACHE_READBACK_SOURCE_FAIL {exc}") from exc

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "M5_DEPTH_CACHE_READBACK_SOURCE_PASS "
        f"sources={result['source_count']} mutations={9 if args.selfcheck else 0} "
        f"sha256={result['source_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
