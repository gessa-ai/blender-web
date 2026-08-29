#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Require fail-closed exact-buffer readback lifecycle telemetry for Apple selection."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
READBACK = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_readback.cc"
PRODUCER = ROOT / "sandbox/p0-interaction-stress/rapid_freeze_repro.mjs"
PATCH = ROOT / "patches/0313-gpu-webgpu-select-readback-lifecycle-telemetry.patch"
SERIES = ROOT / "patches/series"


def require(source: str, token: str, count: int = 1) -> None:
    if source.count(token) != count:
        raise ValueError(f"expected {count} occurrence(s) of {token!r}")


def require_present(source: str, token: str) -> None:
    if token not in source:
        raise ValueError(f"expected {token!r}")


def validate(sources: dict[str, str]) -> None:
    readback = sources["readback"]
    producer = sources["producer"]
    patch = sources["patch"]
    series = sources["series"]

    stages = (
        "submit",
        "map_start",
        "map_complete",
        "validation_complete",
        "join_complete",
        "ready",
    )
    for stage in stages:
        require_present(readback, f"exact_buffer_readback_{stage}_generation")
        require_present(readback, f"bw_exact_buffer_readback_{stage}_count")

    require(
        readback,
        "exact_buffer_readback_submit_generation.fetch_add(1u, std::memory_order_relaxed);",
    )
    require(
        readback,
        "exact_buffer_readback_map_start_generation.fetch_add(1u, std::memory_order_relaxed);",
    )
    require(
        readback,
        "exact_buffer_readback_map_complete_generation.fetch_add(1u,\n"
        "                                                                    std::memory_order_relaxed);",
    )
    require(
        readback,
        "exact_buffer_readback_validation_complete_generation.fetch_add(\n"
        "        1u, std::memory_order_relaxed);",
    )
    require(
        readback,
        "exact_buffer_readback_join_complete_generation.fetch_add(1u, std::memory_order_relaxed);",
    )
    require(
        readback,
        "exact_buffer_readback_ready_generation.fetch_add(1u, std::memory_order_relaxed);",
    )

    submitted = readback.index("void pending_command_map_submitted(")
    map_start = readback.index(
        "exact_buffer_readback_map_start_generation.fetch_add", submitted
    )
    map_call = readback.index("pending->staging.MapAsync(", submitted)
    if map_start > map_call:
        raise ValueError("map-start telemetry is published after MapAsync registration")

    callback = readback.index("state->map_status = status;", map_call)
    map_complete = readback.index(
        "exact_buffer_readback_map_complete_generation.fetch_add", map_call
    )
    if map_complete > callback:
        raise ValueError("map-complete telemetry is published after callback state")

    joined = readback.index("state->finalized = true;", submitted - 2200)
    join_complete = readback.index(
        "exact_buffer_readback_join_complete_generation.fetch_add", joined
    )
    terminal_branch = readback.index("if (!submitted) {", joined)
    if join_complete > terminal_branch:
        raise ValueError("join telemetry does not cover the no-submit terminal path")

    ready_status = readback.index("record.status = TicketStatus::Ready;")
    ready_generation = readback.index(
        "exact_buffer_readback_ready_generation.fetch_add", ready_status
    )
    if ready_generation < ready_status:
        raise ValueError("ready telemetry is published before ticket readiness")

    for token in (
        "selectionReadback: {\n",
        'submits: read("_bw_exact_buffer_readback_submit_count")',
        'mapStarts: read("_bw_exact_buffer_readback_map_start_count")',
        'mapCompletes: read("_bw_exact_buffer_readback_map_complete_count")',
        'validationCompletes: read("_bw_exact_buffer_readback_validation_complete_count")',
        'joinCompletes: read("_bw_exact_buffer_readback_join_complete_count")',
        'ready: read("_bw_exact_buffer_readback_ready_count")',
        "selectionReadback: {...current.selectionReadback}",
        "const classifySelectionReadbackBoundary = (baseline, current) => {",
        "selectionReadbackBoundary: classifySelectionReadbackBoundary(counterBaseline, current)",
        'process.env.BW_P0_READBACK_CLASSIFIER_SELFCHECK === "1"',
        "P0J_SELECTION_READBACK_BOUNDARY_SELFCHECK_PASS cases=9",
        "Object.values(splashDismissed.selectionReadback).every(Number.isFinite)",
    ):
        require_present(producer, token)

    for path in (
        "source/blender/gpu/webgpu/wgpu_readback.cc",
    ):
        require_present(patch, f"diff --git a/{path} b/{path}")
    require(series, "0313-gpu-webgpu-select-readback-lifecycle-telemetry.patch")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return source.replace(old, new, 1)


def self_check(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        (
            "readback",
            "exact_buffer_readback_submit_generation.fetch_add(1u, std::memory_order_relaxed);",
            "exact_buffer_readback_submit_generation.fetch_add(0u, std::memory_order_relaxed);",
        ),
        (
            "readback",
            "exact_buffer_readback_map_start_generation.fetch_add(1u, std::memory_order_relaxed);",
            "exact_buffer_readback_map_start_generation.fetch_add(0u, std::memory_order_relaxed);",
        ),
        (
            "readback",
            "exact_buffer_readback_map_complete_generation.fetch_add(1u,\n"
            "                                                                    std::memory_order_relaxed);",
            "exact_buffer_readback_map_complete_generation.fetch_add(0u,\n"
            "                                                                    std::memory_order_relaxed);",
        ),
        (
            "readback",
            "exact_buffer_readback_join_complete_generation.fetch_add(1u, std::memory_order_relaxed);",
            "exact_buffer_readback_join_complete_generation.fetch_add(0u, std::memory_order_relaxed);",
        ),
        (
            "readback",
            "exact_buffer_readback_ready_generation.fetch_add(1u, std::memory_order_relaxed);",
            "exact_buffer_readback_ready_generation.fetch_add(0u, std::memory_order_relaxed);",
        ),
        (
            "producer",
            "selectionReadback: {...current.selectionReadback}",
            "selectionReadback: {}",
        ),
        (
            "producer",
            "selectionReadbackBoundary: classifySelectionReadbackBoundary(counterBaseline, current)",
            "selectionReadbackBoundary: null",
        ),
        (
            "producer",
            'process.env.BW_P0_READBACK_CLASSIFIER_SELFCHECK === "1"',
            'process.env.BW_P0_READBACK_CLASSIFIER_SELFCHECK === "0"',
        ),
        (
            "producer",
            "Object.values(splashDismissed.selectionReadback).every(Number.isFinite)",
            "true",
        ),
        (
            "patch",
            "diff --git a/source/blender/gpu/webgpu/wgpu_readback.cc "
            "b/source/blender/gpu/webgpu/wgpu_readback.cc",
            "",
        ),
        (
            "series",
            "0313-gpu-webgpu-select-readback-lifecycle-telemetry.patch",
            "0313-missing.patch",
        ),
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
    print(f"P0J_SELECT_READBACK_LIFECYCLE_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    sources = {
        "readback": READBACK.read_text(),
        "producer": PRODUCER.read_text(),
        "patch": PATCH.read_text() if PATCH.exists() else "",
        "series": SERIES.read_text(),
    }
    try:
        self_check(sources) if args.self_check else validate(sources)
    except ValueError as error:
        print(f"P0J_SELECT_READBACK_LIFECYCLE_SOURCE_FAIL {error}")
        return 1
    if not args.self_check:
        print("P0J_SELECT_READBACK_LIFECYCLE_SOURCE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
