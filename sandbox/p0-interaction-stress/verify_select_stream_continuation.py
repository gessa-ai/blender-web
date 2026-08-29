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
NONMODAL_PATCH = ROOT / "patches/0309-view3d-web-selection-failure-nonmodal.patch"
CANCEL_PATCH = ROOT / "patches/0310-view3d-web-selection-cancel-replay.patch"
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
    nonmodal_patch = sources["nonmodal_patch"]
    cancel_patch = sources["cancel_patch"]
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
        "static void view3d_select_async_web_failure_log(",
        "[bw] WebGPU selection continuation canceled: %s\\n",
        "[bw] WebGPU selection readback failed (error %d): %s\\n",
        "for (int64_t index = data->queued_events.size() - 1; index >= 0; index--)",
        "wmEvent *queued = WM_event_add(data->window, &data->queued_events[index]);",
        "BLI_addhead(&data->window->runtime->event_queue, queued);",
        "if (ISTIMER(event->type) || event->customdata != nullptr)",
        'view3d_select_async_web_failure_log("input queue exceeded its bound");',
        'view3d_select_async_web_failure_log("readback timeout");',
    ):
        require(view3d_select, token)
    require(view3d_select, "view3d_select_async_web_failure_log(", 8)
    require(view3d_select, "constexpr int max_log_count = 16;")
    for forbidden in (
        'BKE_report(op->reports, RPT_ERROR, "Unable to retain particle pick depth request");',
        'BKE_report(op->reports, RPT_ERROR, "WebGPU selection input queue exceeded its bound");',
    ):
        if forbidden in view3d_select:
            raise ValueError(f"browser selection failure can still populate modal reports: {forbidden!r}")
    for indent, browser_log, native_report in (
        (
            6,
            'view3d_select_async_web_failure_log("particle depth readback failed");',
            'BKE_report(op->reports, RPT_ERROR, "Particle pick depth readback failed");',
        ),
        (
            4,
            'view3d_select_async_web_failure_log("readback timeout");',
            'BKE_report(op->reports, RPT_ERROR, "Timed out waiting for WebGPU selection readback");',
        ),
        (
            6,
            'view3d_select_async_web_failure_log("particle depth context changed");',
            'BKE_report(op->reports, RPT_ERROR, "Particle pick depth context changed");',
        ),
    ):
        spaces = " " * indent
        require(
            view3d_select,
            f"#ifdef __EMSCRIPTEN__\n{spaces}{browser_log}\n#else\n{spaces}{native_report}\n#endif",
        )
    require(
        view3d_select,
        "static bool view3d_select_async_event_push(View3DSelectAsyncData *data, "
        "const wmEvent *event)\n{\n  constexpr int max_queued_events = 512;",
    )
    require(
        view3d_select,
        "if (ISTIMER(event->type) || event->customdata != nullptr) {\n"
        "      return OPERATOR_PASS_THROUGH;\n    }",
    )
    require(view3d_select, "view3d_select_async_events_requeue(C, data);", 7)
    require(
        view3d_select,
        "static void view3d_select_cancel(bContext *C, wmOperator *op)\n"
        "{\n"
        "#ifdef __EMSCRIPTEN__\n"
        "  View3DSelectAsyncData *data = static_cast<View3DSelectAsyncData *>(op->customdata);\n"
        "  if (data != nullptr) {\n"
        "    view3d_select_async_events_requeue(C, data);\n"
        "  }\n"
        "#endif\n"
        "  view3d_select_async_finish(C, op);\n"
        "}",
    )

    for token in (
        'const stateOnlyDiagnostic = process.env.BW_P0_STATE_ONLY === "1";',
        'throw new Error("BW_P0_STATE_ONLY cannot weaken the Apple pixel diagnostic")',
        "const nativeSelectionReplayComplete = (current, baseline) =>",
        "const selectionContinuationRetired = (current, baseline) =>",
        "from bpy_extras import view3d_utils",
        '"cube_window_xy":[round(region.x+projection.x,3),round(region.y+projection.y,3)]',
        "const nativeCubePagePoint = (current, canvasBox) =>",
        "selectionPoint = nativeCubePagePoint(selectionBaseline, box);",
        "await page.mouse.click(selectionPoint.x, selectionPoint.y);",
        'const selectionPendingWindow = await sample("isolated-selection-pending");',
        'const selectionNavigationWindow = await waitForActionDrain(',
        '"isolated-selection-navigation-passthrough"',
        '"isolated-selection-drain"',
        "current, selectionInputBaseline, {left: 1, middle: 1, keys: 0}",
        "current, selectionWmInputBaseline, {left: 1, middle: 1, keys: 0}",
        "(current) => nativeSelectionReplayComplete(current, selectionBaseline) &&",
        "selectionContinuationRetired(current, selectionBaseline)",
        "selectionComplete: selectionContinuationRetired(selectionDrain, selectionBaseline)",
        "selectionNavigationPassthroughRequired =\n"
        "      selectionPendingWindow.selectionContinuation.gpuSessions >",
        "selectionNavigationPassedThrough =\n",
        "selectionNavigationWindow.selectionContinuation.active === 1",
        "navigationPassedThrough: selectionNavigationPassedThrough",
        "selectionNavigationPassthroughRequired,",
        "\n    selectionNavigationPassedThrough,\n    actionDrainMs:",
        "view3dRotateRetired(current, rotateBaseline, expectedRotates)",
        "selectionReadbackFailureLines: consoleLines.filter(",
        "evidence.selectionReadbackFailureLines.length !== 0",
        '"diagnostic-software-fallback-state-only"',
    ):
        require(producer, token)
    require(producer, "selectionDrainMs: selectionDrain?.settleMs ?? null")
    require(producer, "/WebGPU selection (?:readback failed|continuation canceled)/.test(line)", 2)
    require(
        producer,
        "(current) => nativeSelectionReplayComplete(current, selectionBaseline) &&\n"
        "        selectionContinuationRetired(current, selectionBaseline) &&",
    )
    if not (
        producer.index('"isolated-orbit-drain"')
        < producer.index('"isolated-selection-pending"')
        < producer.index('"isolated-selection-navigation-passthrough"')
        < producer.index('"isolated-selection-drain"')
    ):
        raise ValueError("slow/sparse producer lost orbit -> selection -> live-navigation order")

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
    require(
        nonmodal_patch,
        "diff --git a/source/blender/editors/space_view3d/view3d_select.cc "
        "b/source/blender/editors/space_view3d/view3d_select.cc",
    )
    for token in (
        "+static void view3d_select_async_web_failure_log(",
        '+      view3d_select_async_web_failure_log("particle depth readback failed");',
        '+    view3d_select_async_web_failure_log("readback timeout");',
        '+      view3d_select_async_web_failure_log("modal request", '
        "view3d_select_async_error());",
    ):
        require(nonmodal_patch, token)
    require(series, "0309-view3d-web-selection-failure-nonmodal.patch")
    require(
        cancel_patch,
        "diff --git a/source/blender/editors/space_view3d/view3d_select.cc "
        "b/source/blender/editors/space_view3d/view3d_select.cc",
    )
    for token in (
        "+  View3DSelectAsyncData *data = static_cast<View3DSelectAsyncData *>(op->customdata);",
        "+    view3d_select_async_events_requeue(C, data);",
    ):
        require(cancel_patch, token)
    require(series, "0310-view3d-web-selection-cancel-replay.patch")


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
            "      return OPERATOR_PASS_THROUGH;\n    }",
            "if (ISTIMER(event->type) || event->customdata != nullptr) {\n"
            "      return OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH;\n    }",
        ),
        (
            "view3d_select",
            'view3d_select_async_web_failure_log("input queue exceeded its bound");',
            'BKE_report(op->reports, RPT_ERROR, "WebGPU selection input queue exceeded its bound");',
        ),
        (
            "view3d_select",
            "static void view3d_select_cancel(bContext *C, wmOperator *op)\n"
            "{\n"
            "#ifdef __EMSCRIPTEN__\n"
            "  View3DSelectAsyncData *data = static_cast<View3DSelectAsyncData *>(op->customdata);\n"
            "  if (data != nullptr) {\n"
            "    view3d_select_async_events_requeue(C, data);\n"
            "  }\n"
            "#endif\n"
            "  view3d_select_async_finish(C, op);\n"
            "}",
            "static void view3d_select_cancel(bContext *C, wmOperator *op)\n"
            "{\n"
            "  view3d_select_async_finish(C, op);\n"
            "}",
        ),
        ("producer", 'throw new Error("BW_P0_STATE_ONLY cannot weaken the Apple pixel diagnostic")', ""),
        (
            "producer",
            "selectionPoint = nativeCubePagePoint(selectionBaseline, box);",
            "selectionPoint = center;",
        ),
        (
            "producer",
            '"isolated-selection-navigation-passthrough"',
            '"selection-navigation-bypassed"',
        ),
        (
            "producer",
            "(current) => nativeSelectionReplayComplete(current, selectionBaseline) &&\n"
            "        selectionContinuationRetired(current, selectionBaseline) &&",
            "(current) => true &&\n"
            "        selectionContinuationRetired(current, selectionBaseline) &&",
        ),
        (
            "producer",
            "selectionComplete: selectionContinuationRetired(selectionDrain, selectionBaseline)",
            "selectionComplete: true",
        ),
        (
            "producer",
            "navigationPassedThrough: selectionNavigationPassedThrough",
            "navigationPassedThrough: true",
        ),
        ("producer", "view3dRotateRetired(current, rotateBaseline, expectedRotates)", "true"),
        ("producer", "evidence.selectionReadbackFailureLines.length !== 0", "false"),
        (
            "patch",
            "diff --git a/source/blender/gpu/webgpu/wgpu_buffer.cc "
            "b/source/blender/gpu/webgpu/wgpu_buffer.cc",
            "",
        ),
        (
            "nonmodal_patch",
            "+static void view3d_select_async_web_failure_log(",
            "+static void view3d_select_async_modal_report(",
        ),
        (
            "cancel_patch",
            "+    view3d_select_async_events_requeue(C, data);",
            "+    view3d_select_async_finish(C, op);",
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
        "nonmodal_patch": NONMODAL_PATCH.read_text(),
        "cancel_patch": CANCEL_PATCH.read_text(),
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
