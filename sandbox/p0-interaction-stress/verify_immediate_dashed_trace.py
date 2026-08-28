#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind the camera-frame dashed immediate diagnostic to its exact draw stages."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DISPLAY = ROOT / "platform_web/ghost/GHOST_WebDisplayState.hh"
CONTEXT = ROOT / "platform_web/ghost/GHOST_ContextWGPUWeb.cc"
IMMEDIATE = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_immediate.cc"
CAPTURE = ROOT / "sandbox/p0-interaction-stress/capture_diagnostic.mjs"
SERIES = ROOT / "patches/series"
PATCH = ROOT / "patches/0302-gpu-webgpu-immediate-dashed-stage-trace.patch"


def method(source: str, marker: str) -> str:
    if source.count(marker) != 1:
        raise ValueError(f"method boundary is not unique: {marker}")
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated method: {marker}")


def require_once(source: str, marker: str, label: str) -> None:
    if source.count(marker) != 1:
        raise ValueError(f"{label} requires exactly one {marker!r}")


def validate(display: str, context: str, immediate: str, capture: str, series: str, patch: str) -> None:
    for marker in (
        "enum class ImmediateDashedStage : uint8_t {",
        "inline std::atomic<uint64_t>\n    immediate_dashed_stage_counters",
        "inline void note_immediate_dashed_stage(",
        "inline uint64_t immediate_dashed_stage_count(",
    ):
        require_once(display, marker, "display trace state")
    enum_body = method(display, "enum class ImmediateDashedStage : uint8_t")
    expected_stages = (
        "Attempt", "ModuleDeferred", "GeometryDeferred", "TargetDeferred",
        "PipelineDeferred", "VertexDeferred", "BindingDeferred", "LoadDeferred",
        "PassDeferred", "Encoded", "Accepted", "Rejected", "Count",
    )
    positions = []
    for stage in expected_stages:
        require_once(enum_body, stage, "dashed stage enum")
        positions.append(enum_body.index(stage))
    if positions != sorted(positions):
        raise ValueError("dashed stage enum order differs")

    export = method(context, 'extern "C" EMSCRIPTEN_KEEPALIVE double bw_immediate_dashed_stage_count(')
    require_once(export, "ghost_web::immediate_dashed_stage_count(stage)", "browser trace export")

    end = method(immediate, "void WGPUImmediate::end()")
    shader_filter = method(immediate, "static bool is_dashed_diagnostic_shader(")
    require_once(shader_filter, 'shader->name_get() == "gpu_shader_3D_line_dashed_uniform_color"',
                 "exact camera-frame shader filter")
    require_once(end, "is_dashed_diagnostic_shader(shader)", "immediate shader filter use")
    expected_calls = (
        "DashedTraceStage::Attempt",
        "DashedTraceStage::ModuleDeferred",
        "DashedTraceStage::GeometryDeferred",
        "DashedTraceStage::TargetDeferred",
        "DashedTraceStage::PipelineDeferred",
        "DashedTraceStage::VertexDeferred",
        "DashedTraceStage::BindingDeferred",
        "DashedTraceStage::LoadDeferred",
        "DashedTraceStage::PassDeferred",
        "DashedTraceStage::Encoded",
        "DashedTraceStage::Accepted",
        "DashedTraceStage::Rejected",
    )
    for marker in expected_calls:
        count = 2 if marker == "DashedTraceStage::PassDeferred" else 1
        if end.count(marker) != count:
            raise ValueError(f"immediate stage census differs for {marker}")
    if not (
        end.index("DashedTraceStage::Attempt")
        < end.index("DashedTraceStage::ModuleDeferred")
        < end.index("DashedTraceStage::GeometryDeferred")
        < end.index("DashedTraceStage::PipelineDeferred")
        < end.index("DashedTraceStage::BindingDeferred")
        < end.index("DashedTraceStage::Encoded")
        < end.index("DashedTraceStage::Accepted")
    ):
        raise ValueError("immediate dashed stage placement differs")

    if capture.count("_bw_immediate_dashed_stage_count") != 2:
        raise ValueError("capture does not sample the indexed stage witness twice")
    require_once(capture, "immediateDashedStages,", "per-step trace sample")
    require_once(capture, "immediateDashedStages: await page.evaluate(() =>", "product trace sample")

    require_once(series, PATCH.name, "numbered patch series")
    require_once(
        patch,
        "diff --git a/source/blender/gpu/webgpu/wgpu_immediate.cc b/source/blender/gpu/webgpu/wgpu_immediate.cc",
        "numbered patch path",
    )
    for marker in (
        "DashedTraceStage::Attempt",
        "DashedTraceStage::PipelineDeferred",
        "DashedTraceStage::BindingDeferred",
        "DashedTraceStage::Encoded",
        "DashedTraceStage::Rejected",
    ):
        if marker not in patch:
            raise ValueError(f"numbered patch lost {marker}")


def self_check(parts: tuple[str, ...]) -> None:
    validate(*parts)
    display, context, immediate, capture, series, patch = parts
    mutations = (
        (display.replace("ModuleDeferred,", "", 1), context, immediate, capture, series, patch),
        (display, context.replace("immediate_dashed_stage_count(stage)", "present_count()", 1),
         immediate, capture, series, patch),
        (display, context, immediate.replace("DashedTraceStage::PipelineDeferred", "DashedTraceStage::Encoded", 1),
         capture, series, patch),
        (display, context, immediate, capture.replace("_bw_immediate_dashed_stage_count", "_bw_missing_stage_count", 1),
         series, patch),
        (display, context, immediate, capture, series.replace(PATCH.name, "0302-missing.patch", 1), patch),
        (display, context, immediate, capture, series, patch.replace("DashedTraceStage::Rejected", "DashedTraceStage::Accepted", 1)),
    )
    rejected = 0
    for mutation in mutations:
        try:
            validate(*mutation)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0J_IMMEDIATE_DASHED_TRACE_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    parts = (
        DISPLAY.read_text(encoding="utf-8"),
        CONTEXT.read_text(encoding="utf-8"),
        IMMEDIATE.read_text(encoding="utf-8"),
        CAPTURE.read_text(encoding="utf-8"),
        SERIES.read_text(encoding="utf-8"),
        PATCH.read_text(encoding="utf-8") if PATCH.exists() else "",
    )
    if args.self_check:
        self_check(parts)
    else:
        validate(*parts)
        print("P0J_IMMEDIATE_DASHED_TRACE_SOURCE_PASS stages=12 patch=0302")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"P0J_IMMEDIATE_DASHED_TRACE_SOURCE_FAIL {error}")
        raise SystemExit(1)
