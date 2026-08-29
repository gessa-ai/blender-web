#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Require fail-closed selection continuation phase telemetry for the Apple freeze probe."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SELECT_NEXT = ROOT / "upstream/source/blender/gpu/intern/gpu_select_next.cc"
VIEW3D_SELECT = ROOT / "upstream/source/blender/editors/space_view3d/view3d_select.cc"
PRODUCER = ROOT / "sandbox/p0-interaction-stress/rapid_freeze_repro.mjs"
PATCH = ROOT / "patches/0311-view3d-web-selection-continuation-telemetry.patch"
SERIES = ROOT / "patches/series"


def require(source: str, token: str, count: int = 1) -> None:
    if source.count(token) != count:
        raise ValueError(f"expected {count} occurrence(s) of {token!r}")


def require_present(source: str, token: str) -> None:
    if token not in source:
        raise ValueError(f"expected {token!r}")


def validate(sources: dict[str, str]) -> None:
    select_next = sources["select_next"]
    view3d_select = sources["view3d_select"]
    producer = sources["producer"]
    patch = sources["patch"]
    series = sources["series"]

    for token in (
        "enum class WebSelectAsyncPhase : uint32_t",
        "web_select_async_session_generation",
        "web_select_async_attempt_generation",
        "web_select_async_result_generation",
        "web_select_async_replay_generation",
        "web_select_async_failure_generation",
        "bw_gpu_select_async_phase",
        "bw_gpu_select_async_session_count",
        "bw_gpu_select_async_attempt_count",
        "bw_gpu_select_async_result_count",
        "bw_gpu_select_async_replay_count",
        "bw_gpu_select_async_failure_count",
        "WebSelectAsyncPhase::ValidationPending",
        "WebSelectAsyncPhase::RetryPending",
        "WebSelectAsyncPhase::ReadbackPending",
        "WebSelectAsyncPhase::ResultReady",
        "WebSelectAsyncPhase::Failed",
    ):
        require_present(select_next, token)
    require(select_next, "web_select_async_attempt_generation.fetch_add(", 1)
    require(select_next, "web_select_async_result_generation.fetch_add(", 1)
    require(select_next, "web_select_async_replay_generation.fetch_add(", 1)
    require(select_next, "web_select_async_failure_generation.fetch_add(", 1)

    for token in (
        "web_view3d_select_continuation_begin_count",
        "web_view3d_select_continuation_finish_count",
        "web_view3d_select_replayed_event_count",
        "web_view3d_select_continuation_active",
        "web_view3d_select_queued_event_count",
        "web_view3d_select_modal_tick_count",
        "web_view3d_select_gpu_status",
        "web_view3d_select_query_status",
        "web_view3d_select_combined_status",
        "bw_view3d_select_continuation_begin_count",
        "bw_view3d_select_continuation_finish_count",
        "bw_view3d_select_replayed_event_count",
        "bw_view3d_select_continuation_active",
        "bw_view3d_select_queued_event_count",
        "bw_view3d_select_modal_tick_count",
        "bw_view3d_select_gpu_status",
        "bw_view3d_select_query_status",
        "bw_view3d_select_combined_status",
    ):
        require_present(view3d_select, token)
    require(
        view3d_select,
        "web_view3d_select_queued_event_count.store(\n"
        "      uint32_t(data->queued_events.size()), std::memory_order_release);",
    )
    require(
        view3d_select,
        "web_view3d_select_replayed_event_count.fetch_add(\n"
        "      uint64_t(data->queued_events.size()), std::memory_order_relaxed);",
    )
    require(
        view3d_select,
        "web_view3d_select_modal_tick_count.store(\n"
        "      uint32_t(data->tick_count), std::memory_order_release);",
    )

    for token in (
        "selectionContinuation: {\n",
        'gpuPhase: read("_bw_gpu_select_async_phase")',
        'gpuSessions: read("_bw_gpu_select_async_session_count")',
        'gpuAttempts: read("_bw_gpu_select_async_attempt_count")',
        'gpuResults: read("_bw_gpu_select_async_result_count")',
        'gpuReplays: read("_bw_gpu_select_async_replay_count")',
        'gpuFailures: read("_bw_gpu_select_async_failure_count")',
        'modalBegins: read("_bw_view3d_select_continuation_begin_count")',
        'modalFinishes: read("_bw_view3d_select_continuation_finish_count")',
        'replayedEvents: read("_bw_view3d_select_replayed_event_count")',
        'active: read("_bw_view3d_select_continuation_active")',
        'queuedEvents: read("_bw_view3d_select_queued_event_count")',
        'timerTicks: read("_bw_view3d_select_modal_tick_count")',
        'gpuStatus: read("_bw_view3d_select_gpu_status")',
        'queryStatus: read("_bw_view3d_select_query_status")',
        'combinedStatus: read("_bw_view3d_select_combined_status")',
        "selectionContinuation: {...current.selectionContinuation}",
        "Object.values(splashDismissed.selectionContinuation).every(Number.isFinite)",
    ):
        require(producer, token)

    for path in (
        "source/blender/gpu/intern/gpu_select_next.cc",
        "source/blender/editors/space_view3d/view3d_select.cc",
    ):
        require(patch, f"diff --git a/{path} b/{path}")
    require(series, "0311-view3d-web-selection-continuation-telemetry.patch")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return source.replace(old, new, 1)


def self_check(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        ("select_next", "WebSelectAsyncPhase::ValidationPending", "WebSelectAsyncPhase::Session"),
        ("select_next", "web_select_async_attempt_generation.fetch_add(", "lost_attempt.fetch_add("),
        ("select_next", "web_select_async_result_generation.fetch_add(", "lost_result.fetch_add("),
        ("select_next", "web_select_async_replay_generation.fetch_add(", "lost_replay.fetch_add("),
        ("select_next", "web_select_async_failure_generation.fetch_add(", "lost_failure.fetch_add("),
        (
            "view3d_select",
            "web_view3d_select_replayed_event_count.fetch_add(\n"
            "      uint64_t(data->queued_events.size()), std::memory_order_relaxed);",
            "web_view3d_select_replayed_event_count.fetch_add(\n"
            "      0u, std::memory_order_relaxed);",
        ),
        (
            "view3d_select",
            "web_view3d_select_modal_tick_count.store(\n"
            "      uint32_t(data->tick_count), std::memory_order_release);",
            "web_view3d_select_modal_tick_count.store(\n"
            "      0u, std::memory_order_release);",
        ),
        ("producer", "selectionContinuation: {...current.selectionContinuation}", "selectionContinuation: {}"),
        (
            "producer",
            "Object.values(splashDismissed.selectionContinuation).every(Number.isFinite)",
            "true",
        ),
        (
            "patch",
            "diff --git a/source/blender/gpu/intern/gpu_select_next.cc "
            "b/source/blender/gpu/intern/gpu_select_next.cc",
            "",
        ),
        (
            "series",
            "0311-view3d-web-selection-continuation-telemetry.patch",
            "0311-missing.patch",
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
    print(f"P0J_SELECT_CONTINUATION_TELEMETRY_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    sources = {
        "select_next": SELECT_NEXT.read_text(),
        "view3d_select": VIEW3D_SELECT.read_text(),
        "producer": PRODUCER.read_text(),
        "patch": PATCH.read_text() if PATCH.exists() else "",
        "series": SERIES.read_text(),
    }
    try:
        self_check(sources) if args.self_check else validate(sources)
    except ValueError as error:
        print(f"P0J_SELECT_CONTINUATION_TELEMETRY_SOURCE_FAIL {error}")
        return 1
    if not args.self_check:
        print("P0J_SELECT_CONTINUATION_TELEMETRY_SOURCE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
