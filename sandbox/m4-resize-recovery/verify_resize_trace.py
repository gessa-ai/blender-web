#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind P0-E's bounded present log to exact WebGPU draw-plan capture."""

from __future__ import annotations

import argparse
from pathlib import Path


def method(source: str, marker: str) -> str:
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"missing method: {marker}")
    opening = source.find("{", start)
    if opening < 0:
        raise ValueError(f"missing body: {marker}")
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated method: {marker}")


def require_once(source: str, token: str, label: str) -> None:
    if source.count(token) != 1:
        raise ValueError(f"{label} requires exactly one {token!r}")


def validate(
    display: str,
    context: str,
    framebuffer_header: str,
    framebuffer: str,
    batch: str,
    immediate: str,
    series: str,
    live: str,
) -> None:
    for token in (
        "enum class RedrawTracePass : uint8_t",
        "struct RedrawTracePlan",
        "struct RedrawTraceSnapshot",
        "inline void redraw_trace_begin(",
        "inline bool redraw_trace_capturing()",
        "inline bool redraw_trace_active(",
        "inline void redraw_trace_finish(",
        "inline void redraw_trace_frame_begin(",
        "inline void redraw_trace_note(",
        "inline RedrawTraceSnapshot redraw_trace_snapshot()",
        "inline bool redraw_present_trace_complete(",
        "inline RedrawTraceSnapshot redraw_present_barrier_ready_trace_snapshot()",
    ):
        require_once(display, token, "shared resize trace")
    for field in (
        "episode_generation",
        "draw_count",
        "window_draw_count",
        "frame_draw_count",
        "frame_offscreen_draw_count",
        "frame_window_draw_count",
        "frame_first_offscreen_sequence",
        "frame_last_window_sequence",
        "background",
        "display",
        "target_width",
        "target_height",
        "viewport_x",
        "viewport_y",
        "viewport_width",
        "viewport_height",
        "scissor_enabled",
        "scissor_x",
        "scissor_y",
        "scissor_width",
        "scissor_height",
    ):
        if field not in display:
            raise ValueError(f"shared resize trace omits {field}")
    request = method(display, "inline uint64_t request_redraw_episode()")
    require_once(request, "redraw_trace_begin(generation);", "episode trace start")
    helper = method(display, "inline bool redraw_recovery_tick(")
    require_once(helper, "redraw_trace_finish(episode_generation);", "bounded trace stop")
    if helper.index("redraw_trace_finish(episode_generation);") > helper.index("return false;"):
        raise ValueError("trace stops after the recovery helper returns")
    frame_begin = method(display, "inline void redraw_trace_frame_begin(")
    for token in (
        "redraw_trace_state.frame_draw_count = 0;",
        "redraw_trace_state.frame_offscreen_draw_count = 0;",
        "redraw_trace_state.frame_window_draw_count = 0;",
        "redraw_trace_state.frame_first_offscreen_sequence = 0;",
        "redraw_trace_state.frame_last_window_sequence = 0;",
    ):
        require_once(frame_begin, token, "frame-local resize trace reset")
    frame_complete = method(display, "inline bool redraw_present_trace_complete(")
    for token in (
        "trace.episode_generation == episode",
        "trace.frame_draw_count >= 2u",
        "trace.frame_offscreen_draw_count > 0u",
        "trace.frame_window_draw_count > 0u",
        "trace.frame_first_offscreen_sequence > 0u",
        "trace.frame_last_window_sequence > trace.frame_first_offscreen_sequence",
        "trace.frame_last_window_sequence == trace.last.sequence",
        "trace.background.sequence > 0u",
        "!trace.background.window_target",
        "trace.display.sequence > trace.background.sequence",
        "trace.display.window_target",
    ):
        require_once(frame_complete, token, "completed resize frame trace")

    require_once(
        framebuffer_header,
        "void debug_note_draw(const char *shader_name) const;",
        "framebuffer trace API",
    )
    note = method(framebuffer, "void WGPUFrameBuffer::debug_note_draw(")
    for token in (
        "#ifdef __EMSCRIPTEN__",
        "ghost_web::redraw_trace_capturing()",
        "load_pass_viewport_plan(draw_viewport)",
        'std::strcmp(shader_name, "overlay_background") == 0',
        'std::strcmp(shader_name, "OCIO_Display") == 0',
        "wctx->is_window_backbuffer(this)",
        "ghost_web::redraw_trace_note(",
        "draw_viewport.viewport.viewport_x",
        "draw_viewport.viewport.viewport_y",
        "draw_viewport.scissor_enabled",
    ):
        require_once(note, token, "framebuffer trace capture")
    if note.index("load_pass_viewport_plan(draw_viewport)") > note.index(
        "ghost_web::redraw_trace_note("
    ):
        raise ValueError("draw trace publishes before resolving viewport/scissor")

    batch_call = "fb->debug_note_draw(shader->name_get().c_str());"
    if batch.count(batch_call) != 4:
        raise ValueError("batch trace does not cover direct/indirect ordinary and layered draws")
    require_once(immediate, batch_call, "immediate trace capture")

    present = method(context, "bool GHOST_ContextWGPUWeb::presentBackbuffer()")
    for token in (
        "ghost_web::redraw_trace_active(redraw_trace_episode)",
        "ghost_web::redraw_trace_snapshot()",
        "ghost_web::redraw_present_barrier_ready_trace_snapshot()",
        "barrier_redraw_trace.episode_generation == barrier_ready_episode",
        "barrier_redraw_trace_available ? barrier_redraw_trace : live_redraw_trace",
        "redraw_trace.episode_generation == redraw_trace_episode",
        "redraw_trace_active || barrier_redraw_trace_available",
        "if (redraw_trace_available && resize_trace_total_samples < 64)",
        "resize_trace_total_samples < 64",
        "resize_trace_episode_samples < 24",
        '"WGPUWeb-resize-trace: episode=%llu sample=%u present=%llu "',
        '"draws=%llu window_draws=%llu surface=%ux%u configured=%ux%u "',
        '"requested=%ux%u backbuffer=%ux%u "',
        '"background=%llu/%d/%dx%d/vp%d,%d,%ux%u/sc%d,%u,%u,%ux%u "',
        '"display=%llu/%d/%dx%d/vp%d,%d,%ux%u/sc%d,%u,%u,%ux%u\\n"',
        "ghost_web::redraw_trace_finish(redraw_trace_episode);",
    ):
        require_once(present, token, "per-present resize trace")
    log_at = present.index('"WGPUWeb-resize-trace: episode=')
    if log_at > present.index("ghost_web::note_present();"):
        raise ValueError("resize trace is emitted after the present counter advances")
    if present.index("if (!valid)") > log_at:
        raise ValueError("resize trace can describe a rejected present")

    swap = method(context, "GHOST_TSuccess GHOST_ContextWGPUWeb::swapBufferRelease()")
    for token in (
        "ghost_web::redraw_present_barrier_ready_trace_snapshot()",
        "ghost_web::redraw_present_trace_complete(completed_frame, episode)",
        "ghost_web::complete_redraw_present_barrier(episode, false);",
        "const bool presented = presentBackbuffer();",
    ):
        require_once(swap, token, "completed resize frame present gate")
    if not (
        swap.index("ghost_web::redraw_present_barrier_ready_trace_snapshot()")
        < swap.index("ghost_web::redraw_present_trace_complete(completed_frame, episode)")
        < swap.index("ghost_web::complete_redraw_present_barrier(episode, false);")
        < swap.index("const bool presented = presentBackbuffer();")
    ):
        raise ValueError("incomplete resize frame trace can reach presentation")

    entry = "0286-gpu-webgpu-resize-draw-trace.patch"
    require_once(series, entry, "numbered trace patch")

    for token in (
        "function parseDrawPlan(token)",
        "function parseResizeLayout(line)",
        "function latestResizeLayout(layouts, extent)",
        "const resizeLayouts = [];",
        "const layout = parseResizeLayout(line);",
        "resizeLayouts.push(layout);",
        "const layout = latestResizeLayout(resizeLayouts, extent);",
        "view3d_window={snapshot[4]}x{snapshot[5]}",
        "any: parseDrawPlan(match[14])",
        "background: parseDrawPlan(match[15])",
        "display: parseDrawPlan(match[16])",
        "function validateResizeTraceEpoch(traces, episode, extent, layout, label)",
        "const RESIZE_COMPLETION_TIMEOUT_MS = 24000;",
        "async function waitForResizeFrame(page, width, height, baseline)",
        "presents > baseline.presents",
        "episodes > baseline.episodes",
        "const shrunk = await waitForResizeFrame(page, 1100, 640, initial);",
        "const restored = await waitForResizeFrame(page, 1280, 720, shrunk);",
        "trace.any.sequence !== trace.draws",
        "trace.background.windowTarget",
        "trace.background.target[0] !== layout.view3dWindow[0]",
        "!trace.display.windowTarget",
        'for (const planName of ["any", "background", "display"])',
        "epoch.length !== 1",
        "was not encoded before the barrier present",
        'line.includes("WGPUWeb-resize-present-barrier:")',
        'line.includes("synchronous-present=1")',
        'line.includes("synchronous-present=0")',
        "counters.resizeBarrierSuccess !== 2",
        "counters.resizeBarrierRejected > 8",
        "counters.resizeBarrier !==\n"
        "      counters.resizeBarrierSuccess + counters.resizeBarrierRejected",
        "single barrier presents differ",
        "barriers=${counters.resizeBarrierSuccess}/${counters.resizeBarrierRejected}",
        "plans=complete,current,contained,view3d-bound",
    ):
        require_once(live, token, "live trace consumer")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation source count differs for {old!r}")
    return source.replace(old, new, 1)


def selfcheck(sources: tuple[str, ...]) -> int:
    validate(*sources)
    mutations: list[tuple[str, str, str]] = [
        ("display", "redraw_trace_begin(generation);", ""),
        ("display", "redraw_trace_finish(episode_generation);", ""),
        (
            "display",
            "redraw_trace_state.frame_draw_count = 0;",
            "redraw_trace_state.frame_draw_count = 1;",
        ),
        (
            "display",
            "trace.frame_offscreen_draw_count > 0u",
            "true",
        ),
        (
            "display",
            "trace.background.sequence > 0u",
            "true",
        ),
        ("display", "inline void redraw_trace_note(", "inline void disabled_trace_note("),
        (
            "context",
            "if (!ghost_web::redraw_present_trace_complete(completed_frame, episode))",
            "if (false)",
        ),
        ("context", "resize_trace_total_samples < 64", "resize_trace_total_samples < 63"),
        ("context", "resize_trace_episode_samples < 24", "resize_trace_episode_samples < 23"),
        (
            "context",
            "barrier_redraw_trace.episode_generation == barrier_ready_episode",
            "false",
        ),
        (
            "context",
            "barrier_redraw_trace_available ? barrier_redraw_trace : live_redraw_trace",
            "live_redraw_trace",
        ),
        ("context", '"WGPUWeb-resize-trace: episode=', '"disabled-resize-trace: episode='),
        ("context", "ghost_web::redraw_trace_finish(redraw_trace_episode);", ""),
        ("framebuffer_header", "void debug_note_draw(const char *shader_name) const;", ""),
        ("framebuffer", 'std::strcmp(shader_name, "overlay_background") == 0', "false"),
        ("framebuffer", 'std::strcmp(shader_name, "OCIO_Display") == 0', "false"),
        (
            "framebuffer",
            "wctx != nullptr && wctx->is_window_backbuffer(this)",
            "false",
        ),
        (
            "framebuffer",
            "if (!load_pass_viewport_plan(draw_viewport)) {\n    return;\n  }\n  "
            "ghost_web::RedrawTracePass",
            "if (false) {\n    return;\n  }\n  ghost_web::RedrawTracePass",
        ),
        ("batch", "fb->debug_note_draw(shader->name_get().c_str());", "",),
        ("immediate", "fb->debug_note_draw(shader->name_get().c_str());", ""),
        ("series", "0286-gpu-webgpu-resize-draw-trace.patch", ""),
        ("live", "function parseDrawPlan(token)", "function disabledDrawPlan(token)"),
        ("live", "function parseResizeLayout(line)", "function disabledResizeLayout(line)"),
        (
            "live",
            "function latestResizeLayout(layouts, extent)",
            "function disabledLatestResizeLayout(layouts, extent)",
        ),
        ("live", "resizeLayouts.push(layout);", ""),
        (
            "live",
            "const layout = latestResizeLayout(resizeLayouts, extent);",
            "const layout = null;",
        ),
        (
            "live",
            "view3d_window={snapshot[4]}x{snapshot[5]}",
            "disabled_region={snapshot[4]}x{snapshot[5]}",
        ),
        ("live", "trace.any.sequence !== trace.draws", "false"),
        ("live", "trace.background.windowTarget", "false"),
        (
            "live",
            "trace.background.target[0] !== layout.view3dWindow[0]",
            "false",
        ),
        ("live", "!trace.display.windowTarget", "false"),
        (
            "live",
            "plans=complete,current,contained,view3d-bound",
            "plans=complete,current,contained",
        ),
        (
            "live",
            "epoch.length !== 1",
            "epoch.length === 0",
        ),
        (
            "live",
            "was not encoded before the barrier present",
            "ignored missing plan",
        ),
        (
            "live",
            "const RESIZE_COMPLETION_TIMEOUT_MS = 24000;",
            "const RESIZE_COMPLETION_TIMEOUT_MS = 60000;",
        ),
        (
            "live",
            "presents > baseline.presents",
            "presents >= baseline.presents",
        ),
        (
            "live",
            "episodes > baseline.episodes",
            "episodes >= baseline.episodes",
        ),
        (
            "live",
            'line.includes("WGPUWeb-resize-present-barrier:")',
            'line.includes("disabled-resize-present-barrier:")',
        ),
        (
            "live",
            'line.includes("synchronous-present=1")',
            'line.includes("synchronous-present=2")',
        ),
        (
            "live",
            'line.includes("synchronous-present=0")',
            'line.includes("synchronous-present=-1")',
        ),
        (
            "live",
            "counters.resizeBarrierSuccess !== 2",
            "false",
        ),
        (
            "live",
            "counters.resizeBarrierRejected > 8",
            "false",
        ),
        (
            "live",
            "counters.resizeBarrierSuccess + counters.resizeBarrierRejected",
            "counters.resizeBarrierSuccess",
        ),
        (
            "live",
            "single barrier presents differ",
            "ignored barrier present count",
        ),
    ]
    names = (
        "display",
        "context",
        "framebuffer_header",
        "framebuffer",
        "batch",
        "immediate",
        "series",
        "live",
    )
    for index, (name, old, new) in enumerate(mutations, start=1):
        changed = list(sources)
        source_index = names.index(name)
        if name == "batch" and old:
            changed[source_index] = changed[source_index].replace(old, new, 1)
        else:
            changed[source_index] = replace_once(changed[source_index], old, new)
        try:
            validate(*changed)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")
    return len(mutations)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    paths = (
        root / "platform_web/ghost/GHOST_WebDisplayState.hh",
        root / "platform_web/ghost/GHOST_ContextWGPUWeb.cc",
        root / "upstream/source/blender/gpu/webgpu/wgpu_framebuffer.hh",
        root / "upstream/source/blender/gpu/webgpu/wgpu_framebuffer.cc",
        root / "upstream/source/blender/gpu/webgpu/wgpu_batch.cc",
        root / "upstream/source/blender/gpu/webgpu/wgpu_immediate.cc",
        root / "patches/series",
        root / "sandbox/m4-resize-recovery/live_resize_repro.mjs",
    )
    sources = tuple(path.read_text(encoding="utf-8") for path in paths)
    mutations = selfcheck(sources) if args.selfcheck else 0
    validate(*sources)
    print(
        "BW_M4_RESIZE_TRACE_PASS "
        f"sources={len(sources)} mutations={mutations} episode=24 global=64 "
        "passes=all,overlay_background,OCIO_Display "
        "consumer=draw-plans layout=view3d-window"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
