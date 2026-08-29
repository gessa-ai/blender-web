#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind the synchronous browser selection loop to a bounded stage discriminator."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRAW_CONTEXT = ROOT / "upstream/source/blender/draw/intern/draw_context.cc"
GPU_SHADER = ROOT / "upstream/source/blender/gpu/intern/gpu_shader.cc"
PRODUCER = ROOT / "sandbox/p0-interaction-stress/rapid_freeze_repro.mjs"
PATCH = ROOT / "patches/0316-gpu-webgpu-select-sync-stage-telemetry.patch"
SERIES = ROOT / "patches/series"


def require(source: str, token: str, count: int = 1) -> None:
    if source.count(token) != count:
        raise ValueError(f"expected {count} occurrence(s) of {token!r}")


def validate(sources: dict[str, str]) -> None:
    draw = sources["draw"]
    gpu_shader = sources["gpu_shader"]
    producer = sources["producer"]
    patch = sources["patch"]
    series = sources["series"]

    for token in (
        "std::atomic<uint64_t> web_select_sync_loop_generation{0};",
        "std::atomic<uint64_t> web_select_sync_complete_generation{0};",
        "std::atomic<uint32_t> web_select_sync_stage{0};",
        "static void web_select_sync_stage_store(const uint32_t stage)",
        "bw_view3d_select_sync_loop_count(void)",
        "bw_view3d_select_sync_stage(void)",
        "bw_view3d_select_sync_complete_count(void)",
        "web_select_sync_loop_generation.fetch_add(1u, std::memory_order_relaxed);",
        "web_select_sync_complete_generation.fetch_add(1u, std::memory_order_release);",
    ):
        require(draw, token)
    for stage in range(1, 24):
        require(draw, f"web_select_sync_stage_store({stage}u);")
    for stage in (*range(80, 93), *range(100, 112)):
        require(draw, f"web_select_sync_stage_store({stage}u);")
    for before, call, after in (
        (80, "instance.init();", 81),
        (82, "view_data_active->manager->begin_sync(this->obact);", 83),
        (84, "instance.begin_sync();", 85),
        (86, "sync(iter_callback);", 87),
        (88, "instance.end_sync();", 89),
        (90, "view_data_active->manager->end_sync();", 91),
        (100, "data->modules_begin_sync();", 101),
        (102, "iter_callback(dupli_handler, extraction);", 103),
        (104, "dupli_handler.extract_all(extraction);", 105),
        (108, "extraction.work_and_wait();", 109),
        (110, "DRW_curves_update(*view_data_active->manager);", 111),
    ):
        before_index = draw.index(f"web_select_sync_stage_store({before}u);")
        call_index = draw.index(call, before_index)
        after_index = draw.index(f"web_select_sync_stage_store({after}u);", call_index)
        if not before_index < call_index < after_index:
            raise ValueError(f"selection sub-stage {before}/{after} no longer brackets {call}")
    stage_1 = draw.index("web_select_sync_stage_store(1u);")
    stage_8 = draw.index("web_select_sync_stage_store(8u);", stage_1)
    init_sync = draw.index("draw_ctx.engines_init_and_sync(", stage_8)
    stage_9 = draw.index("web_select_sync_stage_store(9u);", init_sync)
    stage_16 = draw.index("web_select_sync_stage_store(16u);", stage_9)
    draw_scene = draw.index("draw_ctx.engines_draw_scene();", stage_16)
    stage_17 = draw.index("web_select_sync_stage_store(17u);", draw_scene)
    stage_23 = draw.index("web_select_sync_stage_store(23u);", stage_17)
    if not (stage_1 < stage_8 < init_sync < stage_9 < stage_16 < draw_scene < stage_17 < stage_23):
        raise ValueError("selection stage order no longer brackets init/sync and scene draw")

    for token in (
        "std::atomic<uint32_t> web_select_shader_compile_kind{0};",
        "std::atomic<uint32_t> web_select_shader_compile_stage{0};",
        "bw_select_shader_compile_kind(void)",
        "bw_select_shader_compile_stage(void)",
        'info.name_.compare(info.name_.size() - 11, 11, "_selectable") == 0',
        "web_select_shader_compile_begin(orig_info);",
    ):
        require(gpu_shader, token)
    for stage in range(2, 16):
        require(gpu_shader, f"web_select_shader_compile_stage_store(orig_info, {stage}u);")
    compile_begin = gpu_shader.index("web_select_shader_compile_begin(orig_info);")
    compile_finalize = gpu_shader.index("if (!shader->finalize(&info))", compile_begin)
    if not (
        compile_begin
        < gpu_shader.index("web_select_shader_compile_stage_store(orig_info, 13u);", compile_begin)
        < compile_finalize
        < gpu_shader.index("web_select_shader_compile_stage_store(orig_info, 14u);", compile_finalize)
    ):
        raise ValueError("select shader compile stage no longer brackets backend finalize")

    for token in (
        'syncLoops: read("_bw_view3d_select_sync_loop_count")',
        'completedLoops: read("_bw_view3d_select_sync_complete_count")',
        'syncStage: read("_bw_view3d_select_sync_stage")',
        "selectionSync: {...current.selectionSync},",
        "splashDismissed.selectionSync.syncLoops",
        "splashDismissed.selectionSync.completedLoops",
        "splashDismissed.selectionSync.syncStage",
        "current.selectionSync.syncLoops > baseline.selectionSync.syncLoops",
        "current.selectionSync.completedLoops > baseline.selectionSync.completedLoops",
        'compileKind: read("_bw_select_shader_compile_kind")',
        'compileStage: read("_bw_select_shader_compile_stage")',
        "selectionShader: {...current.selectionShader},",
        "splashDismissed.selectionShader.compileKind",
        "splashDismissed.selectionShader.compileStage",
    ):
        require(producer, token)

    require(
        patch,
        "diff --git a/source/blender/draw/intern/draw_context.cc "
        "b/source/blender/draw/intern/draw_context.cc",
    )
    require(
        patch,
        "diff --git a/source/blender/gpu/intern/gpu_shader.cc "
        "b/source/blender/gpu/intern/gpu_shader.cc",
    )
    require(patch, "+  web_select_sync_stage_store(23u);")
    require(patch, "+  web_select_sync_complete_generation.fetch_add(1u, std::memory_order_release);")
    require(patch, "+  web_select_shader_compile_stage_store(orig_info, 15u);")
    require(series, PATCH.name)


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return source.replace(old, new, 1)


def self_check(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        ("draw", "web_select_sync_stage_store(8u);", "web_select_sync_stage_store(7u);"),
        ("draw", "web_select_sync_stage_store(16u);", ""),
        ("draw", "web_select_sync_stage_store(23u);", ""),
        ("producer", 'syncStage: read("_bw_view3d_select_sync_stage")', "syncStage: 0"),
        (
            "producer",
            "current.selectionSync.completedLoops > baseline.selectionSync.completedLoops",
            "current.selectionSync.completedLoops >= baseline.selectionSync.completedLoops",
        ),
        ("patch", "+  web_select_sync_stage_store(23u);", "+  web_select_sync_stage_store(22u);"),
        ("series", PATCH.name, "0316-missing.patch"),
    )
    rejected = 0
    for key, old, new in mutations:
        mutated = dict(sources)
        mutated[key] = replace_once(mutated[key], old, new)
        try:
            validate(mutated)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0J_SELECT_SYNC_STAGE_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    sources = {
        "draw": DRAW_CONTEXT.read_text(),
        "gpu_shader": GPU_SHADER.read_text(),
        "producer": PRODUCER.read_text(),
        "patch": PATCH.read_text() if PATCH.is_file() else "",
        "series": SERIES.read_text(),
    }
    try:
        self_check(sources) if args.self_check else validate(sources)
    except ValueError as error:
        print(f"P0J_SELECT_SYNC_STAGE_SOURCE_FAIL {error}")
        return 1
    if not args.self_check:
        print("P0J_SELECT_SYNC_STAGE_SOURCE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
