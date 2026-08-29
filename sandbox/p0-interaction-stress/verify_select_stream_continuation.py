#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind one-draw WebGPU selection to an ordered stream readback and input continuation."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "upstream/source/blender/draw/intern/DRW_gpu_wrapper.hh"
SELECT_INSTANCE = ROOT / "upstream/source/blender/draw/engines/select/select_instance.hh"
STORAGE = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_storage_buffer.cc"
BUFFER = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_buffer.cc"
VIEW3D_SELECT = ROOT / "upstream/source/blender/editors/space_view3d/view3d_select.cc"
PRODUCER = ROOT / "sandbox/p0-interaction-stress/rapid_freeze_repro.mjs"
PATCH = ROOT / "patches/0305-gpu-webgpu-select-stream-continuation.patch"
SERIES = ROOT / "patches/series"


def require(source: str, token: str, count: int = 1) -> None:
    if source.count(token) != count:
        raise ValueError(f"expected {count} occurrence(s) of {token!r}")


def validate(sources: dict[str, str]) -> None:
    wrapper = sources["wrapper"]
    select_instance = sources["select_instance"]
    storage = sources["storage"]
    buffer = sources["buffer"]
    view3d_select = sources["view3d_select"]
    producer = sources["producer"]
    patch = sources["patch"]
    series = sources["series"]

    for token in (
        "GPUUsageType usage_;",
        ": usage_(usage)",
        "nullptr, usage_, this->name_",
        "nullptr, this->usage_, this->name_",
        "std::swap(a.usage_, b.usage_);",
    ):
        require(wrapper, token)
    require(wrapper, "const GPUUsageType usage = device_only ? GPU_USAGE_DEVICE_ONLY :", 2)
    require(
        select_instance,
        'StorageArrayBuffer<uint> select_output_buf = {"select_output_buf", GPU_USAGE_STREAM};',
    )
    for token in (
        "case GPU_USAGE_STREAM:",
        "usage = webgpu::UsageType::Stream;",
        "if (usage_ == GPU_USAGE_STREAM)",
        "return buffer_.create_transient(ctx->instance_get(),",
    ):
        require(storage, token)
    require(
        storage,
        "ctx->device_get(),\n                                    ctx->queue_scheduler_get(),\n"
        "                                    webgpu::BufferKind::Storage,",
    )
    require(buffer, "const Allocation allocation = allocation_get();", 3)
    if "const Allocation allocation = allocation_cache_.lookup(kAllocationKey);" in buffer:
        raise ValueError("an update/read path still excludes a provisional stream allocation")

    for token in (
        "Vector<wmEvent> queued_events;",
        "static bool view3d_select_async_event_push(",
        "static void view3d_select_async_events_requeue(",
        "for (int64_t index = data->queued_events.size() - 1; index >= 0; index--)",
        "wmEvent *queued = WM_event_add(data->window, &data->queued_events[index]);",
        "BLI_addhead(&data->window->runtime->event_queue, queued);",
        "if (ISTIMER(event->type) || event->customdata != nullptr)",
        'BKE_report(op->reports, RPT_ERROR, "WebGPU selection input queue exceeded its bound");',
    ):
        require(view3d_select, token)
    require(
        view3d_select,
        "static bool view3d_select_async_event_push(View3DSelectAsyncData *data, "
        "const wmEvent *event)\n{\n  constexpr int max_queued_events = 512;",
    )
    require(
        view3d_select,
        "if (ISTIMER(event->type) || event->customdata != nullptr) {\n"
        "      return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n    }",
    )
    if view3d_select.count("view3d_select_async_events_requeue(C, data);") < 5:
        raise ValueError("selection completion/error paths do not all preserve retained input")

    for token in (
        'const stateOnlyDiagnostic = process.env.BW_P0_STATE_ONLY === "1";',
        'throw new Error("BW_P0_STATE_ONLY cannot weaken the Apple pixel diagnostic")',
        "view3dRotateRetired(current, rotateBaseline, expectedRotates)",
        "selectionReadbackFailureLines: consoleLines.filter(",
        "evidence.selectionReadbackFailureLines.length !== 0",
        '"diagnostic-software-fallback-state-only"',
    ):
        require(producer, token)
    require(producer, "/WebGPU selection readback failed/.test(line)", 2)

    for path in (
        "source/blender/draw/intern/DRW_gpu_wrapper.hh",
        "source/blender/draw/engines/select/select_instance.hh",
        "source/blender/gpu/webgpu/wgpu_storage_buffer.cc",
        "source/blender/gpu/webgpu/wgpu_buffer.cc",
        "source/blender/editors/space_view3d/view3d_select.cc",
    ):
        require(patch, f"diff --git a/{path} b/{path}")
    require(
        patch,
        '+  StorageArrayBuffer<uint> select_output_buf = {"select_output_buf", '
        "GPU_USAGE_STREAM};",
    )
    require(
        series,
        "0305-gpu-webgpu-select-stream-continuation.patch",
    )


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return source.replace(old, new, 1)


def replace_first(source: str, old: str, new: str) -> str:
    if old not in source:
        raise ValueError(f"mutation input missing {old!r}")
    return source.replace(old, new, 1)


def self_check(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        ("wrapper", "std::swap(a.usage_, b.usage_);", ""),
        ("select_instance", '"select_output_buf", GPU_USAGE_STREAM', '"select_output_buf"'),
        ("storage", "return buffer_.create_transient(ctx->instance_get(),", "return false && buffer_.create_transient(ctx->instance_get(),"),
        ("buffer", "const Allocation allocation = allocation_get();", "const Allocation allocation = allocation_cache_.lookup(kAllocationKey);"),
        (
            "view3d_select",
            "static bool view3d_select_async_event_push(View3DSelectAsyncData *data, "
            "const wmEvent *event)\n{\n  constexpr int max_queued_events = 512;",
            "static bool view3d_select_async_event_push(View3DSelectAsyncData *data, "
            "const wmEvent *event)\n{\n  constexpr int max_queued_events = 0;",
        ),
        ("view3d_select", "BLI_addhead(&data->window->runtime->event_queue, queued);", "BLI_addtail(&data->window->runtime->event_queue, queued);"),
        (
            "view3d_select",
            "if (ISTIMER(event->type) || event->customdata != nullptr) {\n"
            "      return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n    }",
            "if (ISTIMER(event->type) || event->customdata != nullptr) {\n"
            "      return OPERATOR_RUNNING_MODAL;\n    }",
        ),
        ("producer", 'throw new Error("BW_P0_STATE_ONLY cannot weaken the Apple pixel diagnostic")', ""),
        ("producer", "view3dRotateRetired(current, rotateBaseline, expectedRotates)", "true"),
        ("producer", "evidence.selectionReadbackFailureLines.length !== 0", "false"),
        (
            "patch",
            "diff --git a/source/blender/gpu/webgpu/wgpu_buffer.cc "
            "b/source/blender/gpu/webgpu/wgpu_buffer.cc",
            "",
        ),
        (
            "series",
            "0305-gpu-webgpu-select-stream-continuation.patch",
            "0305-missing.patch",
        ),
    )
    rejected = 0
    for key, old, new in mutations:
        mutated = dict(sources)
        replace = replace_first if key == "buffer" else replace_once
        mutated[key] = replace(mutated[key], old, new)
        try:
            validate(mutated)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0J_SELECT_STREAM_CONTINUATION_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    sources = {
        "wrapper": WRAPPER.read_text(),
        "select_instance": SELECT_INSTANCE.read_text(),
        "storage": STORAGE.read_text(),
        "buffer": BUFFER.read_text(),
        "view3d_select": VIEW3D_SELECT.read_text(),
        "producer": PRODUCER.read_text(),
        "patch": PATCH.read_text(),
        "series": SERIES.read_text(),
    }
    try:
        self_check(sources) if args.self_check else validate(sources)
    except ValueError as error:
        print(f"P0J_SELECT_STREAM_CONTINUATION_SOURCE_FAIL {error}")
        return 1
    if not args.self_check:
        print("P0J_SELECT_STREAM_CONTINUATION_SOURCE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
