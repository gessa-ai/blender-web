#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind deferred WebGPU draw readiness to bounded web-window redraw recovery."""

from __future__ import annotations

import argparse
from pathlib import Path


PROCESS_MARKER = "bool GHOST_SystemWeb::processEvents(bool /*waitForEvent*/)"
CREATE_MARKER = "GHOST_IWindow *GHOST_SystemWeb::createWindow("
HELPER_MARKER = "inline bool redraw_recovery_tick("
SHADER_MODULE_MARKER = "bool WGPUShader::ensure_shader_modules("
COMPUTE_PIPELINE_MARKER = "wgpu::ComputePipeline WGPUShader::compute_pipeline("
BIND_GROUP_MARKER = "bool WGPUShader::bind_group_entries_complete("
EXPLICIT_LAYOUT_MARKER = "bool WGPUShader::ensure_explicit_layout("
RENDER_PIPELINE_MARKER = "wgpu::RenderPipeline WGPUPipelinePool::get("


def method(source: str, marker: str) -> str:
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"missing method: {marker}")
    opening = source.find("{", start)
    if opening < 0:
        raise ValueError(f"missing method body: {marker}")
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


def require_count(source: str, token: str, count: int, label: str) -> None:
    if source.count(token) != count:
        raise ValueError(f"{label} requires {count} occurrences of {token!r}")


def validate(
    display_header: str,
    system_header: str,
    system_source: str,
    wm_window_source: str,
    shader_source: str,
    pipeline_source: str,
) -> None:
    helper = method(display_header, HELPER_MARKER)
    for token in (
        "FIRST_PIXEL_SETTLE_TICKS = 180u",
        "FIRST_PIXEL_SETTLE_INTERVAL = 12u",
        "inline std::atomic<uint64_t> redraw_retry_counter{0};",
        "inline std::atomic<uint64_t> redraw_drop_counter{0};",
        "inline void request_redraw_retry()",
        "inline uint64_t redraw_retry_generation()",
        "inline void note_redraw_drop()",
        "inline uint64_t redraw_drop_generation()",
    ):
        require_once(display_header, token, "redraw recovery state")
    for token in (
        "retry_generation != retry_generation_seen",
        "retry_generation_seen = retry_generation;",
        "drop_generation != drop_generation_seen",
        "drop_generation_seen = drop_generation;",
        "heartbeat = 0;",
        "readiness_published || draw_dropped ||",
        "(heartbeat % FIRST_PIXEL_SETTLE_INTERVAL) == 0u",
        "heartbeat++;",
        "return request_update;",
    ):
        require_once(helper, token, "redraw recovery helper")
    require_count(helper, "if (heartbeat >= FIRST_PIXEL_SETTLE_TICKS)", 2,
                  "redraw recovery helper")
    if "present_count" in helper or "present_baseline" in helper:
        raise ValueError("redraw recovery still terminates on presentation count")

    require_once(
        system_header,
        "uint64_t redraw_retry_generation_seen_ = 0;",
        "per-window recovery state",
    )
    require_once(
        system_header,
        "uint64_t redraw_drop_generation_seen_ = 0;",
        "per-window drop state",
    )
    if "redraw_present_baseline_" in system_header:
        raise ValueError("obsolete two-present terminal state remains")

    process = method(system_source, PROCESS_MARKER)
    for token in (
        "ghost_web::redraw_recovery_tick(",
        "ghost_web::redraw_retry_generation()",
        "redraw_retry_generation_seen_",
        "ghost_web::redraw_drop_generation()",
        "redraw_drop_generation_seen_",
        "GHOST_kEventWindowUpdate",
    ):
        require_once(process, token, "processEvents recovery wiring")
    if "GHOST_kEventWindowActivate" in process:
        raise ValueError("redraw recovery injects synthetic activation")

    resize = method(process, "if (ghost_web::poll_pending_backing(nw, nh))")
    resize_retry = "ghost_web::request_redraw_retry();"
    require_once(resize, resize_retry, "browser resize recovery wiring")
    resize_positions = (
        resize.index("window_->reconfigureSurface();"),
        resize.index("GHOST_kEventWindowSize"),
        resize.index(resize_retry),
    )
    if resize_positions != tuple(sorted(resize_positions)):
        raise ValueError("browser resize retry is not published after extent and WM size update")

    creation = method(system_source, CREATE_MARKER)
    generation = "redraw_retry_generation_seen_ = ghost_web::redraw_retry_generation();"
    drop_generation = "redraw_drop_generation_seen_ = ghost_web::redraw_drop_generation();"
    heartbeat = "redraw_heartbeat_ = 0;"
    require_once(creation, generation, "window publication")
    require_once(creation, drop_generation, "window publication")
    require_once(creation, heartbeat, "window publication")
    if max(creation.index(generation), creation.index(drop_generation)) > creation.index(heartbeat):
        raise ValueError("window publication resets ticks before capturing its retry generation")

    update_case = wm_window_source.find("case GHOST_kEventWindowUpdate:")
    case_end = wm_window_source.find("break;", update_case)
    if update_case < 0 or case_end < 0:
        raise ValueError("missing WindowUpdate handler")
    update_handler = wm_window_source[update_case:case_end]
    web_notifier = "WM_event_add_notifier_ex(wm, win, NC_SCREEN | NA_EDITED, nullptr);"
    require_once(update_handler, web_notifier, "Emscripten WindowUpdate handler")
    notifier = update_handler.find(web_notifier)
    if notifier < 0:
        raise ValueError("screen notifier is not inside the WindowUpdate handler")
    emscripten_guard = update_handler.rfind("#ifdef __EMSCRIPTEN__", 0, notifier)
    if emscripten_guard < 0:
        raise ValueError("screen notifier is not Emscripten-only")

    for source, label in ((shader_source, "shader"), (pipeline_source, "pipeline")):
        require_once(source, '#  include "GHOST_WebDisplayState.hh"',
                     f"{label} web recovery include")
        require_once(source, "static void request_webgpu_redraw_retry()",
                     f"{label} recovery adapter")
        require_once(source, "ghost_web::request_redraw_retry();",
                     f"{label} recovery publication")
    require_once(shader_source, "static void note_webgpu_draw_drop()",
                 "shader drop adapter")
    require_once(shader_source, "ghost_web::note_redraw_drop();",
                 "shader drop publication")

    module = method(shader_source, SHADER_MODULE_MARKER)
    compute = method(shader_source, COMPUTE_PIPELINE_MARKER)
    bindings = method(shader_source, BIND_GROUP_MARKER)
    explicit = method(shader_source, EXPLICIT_LAYOUT_MARKER)
    render = method(pipeline_source, RENDER_PIPELINE_MARKER)
    for body, label in (
        (module, "shader-module settlement"),
        (compute, "compute-pipeline settlement"),
        (explicit, "explicit-layout settlement"),
        (render, "render-pipeline settlement"),
    ):
        require_once(body, "if (published != nullptr)", label)
        require_once(body, "request_webgpu_redraw_retry();", label)
    require_once(bindings, "note_webgpu_draw_drop();", "incomplete bind-group drop")
    if bindings.index("note_webgpu_draw_drop();") > bindings.index("CLOG_WARN"):
        raise ValueError("incomplete bind-group retry is published after its diagnostic")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return source.replace(old, new, 1)


def mutate_method(source: str, marker: str, old: str, new: str) -> str:
    original = method(source, marker)
    changed = replace_once(original, old, new)
    return source.replace(original, changed, 1)


def mutate_window_update(source: str, old: str, new: str) -> str:
    start = source.find("case GHOST_kEventWindowUpdate:")
    end = source.find("break;", start)
    if start < 0 or end < 0:
        raise ValueError("missing WindowUpdate handler mutation input")
    original = source[start:end]
    changed = replace_once(original, old, new)
    return source[:start] + changed + source[end:]


def selfcheck(
    display_header: str,
    system_header: str,
    system_source: str,
    wm_window_source: str,
    shader_source: str,
    pipeline_source: str,
) -> None:
    validate(display_header, system_header, system_source, wm_window_source,
             shader_source, pipeline_source)
    mutations = (
        (replace_once(display_header, "FIRST_PIXEL_SETTLE_TICKS = 180u", "FIRST_PIXEL_SETTLE_TICKS = 0u"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "FIRST_PIXEL_SETTLE_INTERVAL = 12u", "FIRST_PIXEL_SETTLE_INTERVAL = 1u"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "inline std::atomic<uint64_t> redraw_retry_counter{0};", ""), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "inline std::atomic<uint64_t> redraw_drop_counter{0};", ""), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "readiness_published ||", "false ||"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "draw_dropped ||", "false ||"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "retry_generation != retry_generation_seen", "false"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (replace_once(display_header, "drop_generation != drop_generation_seen", "false"), system_header, system_source, wm_window_source, shader_source, pipeline_source),
        (display_header, replace_once(system_header, "uint64_t redraw_retry_generation_seen_ = 0;", ""), system_source, wm_window_source, shader_source, pipeline_source),
        (display_header, replace_once(system_header, "uint64_t redraw_drop_generation_seen_ = 0;", ""), system_source, wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "ghost_web::redraw_recovery_tick(", "ghost_web::redraw_recovery_disabled("), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "ghost_web::redraw_drop_generation()", "ghost_web::redraw_drop_generation_disabled()"), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "GHOST_kEventWindowUpdate", "GHOST_kEventWindowActivate"), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "ghost_web::request_redraw_retry();", ""), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, CREATE_MARKER, "redraw_retry_generation_seen_ = ghost_web::redraw_retry_generation();", ""), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, mutate_method(system_source, CREATE_MARKER, "redraw_drop_generation_seen_ = ghost_web::redraw_drop_generation();", ""), wm_window_source, shader_source, pipeline_source),
        (display_header, system_header, system_source, mutate_window_update(wm_window_source, "WM_event_add_notifier_ex(wm, win, NC_SCREEN | NA_EDITED, nullptr);", ""), shader_source, pipeline_source),
        (display_header, system_header, system_source, mutate_window_update(wm_window_source, "#ifdef __EMSCRIPTEN__\n      /* A web surface", "#if 1\n      /* A web surface"), shader_source, pipeline_source),
        (display_header, system_header, system_source, wm_window_source, mutate_method(shader_source, SHADER_MODULE_MARKER, "request_webgpu_redraw_retry();", ""), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, mutate_method(shader_source, COMPUTE_PIPELINE_MARKER, "request_webgpu_redraw_retry();", ""), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, mutate_method(shader_source, BIND_GROUP_MARKER, "note_webgpu_draw_drop();", ""), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, mutate_method(shader_source, EXPLICIT_LAYOUT_MARKER, "request_webgpu_redraw_retry();", ""), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, shader_source, mutate_method(pipeline_source, RENDER_PIPELINE_MARKER, "request_webgpu_redraw_retry();", "")),
        (display_header, system_header, system_source, wm_window_source, replace_once(shader_source, '#  include "GHOST_WebDisplayState.hh"', ""), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, replace_once(shader_source, "ghost_web::note_redraw_drop();", ""), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, shader_source, replace_once(pipeline_source, '#  include "GHOST_WebDisplayState.hh"', "")),
        (display_header, system_header, system_source, wm_window_source, mutate_method(shader_source, SHADER_MODULE_MARKER, "if (published != nullptr)", "if (true)"), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, mutate_method(shader_source, COMPUTE_PIPELINE_MARKER, "if (published != nullptr)", "if (true)"), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, mutate_method(shader_source, EXPLICIT_LAYOUT_MARKER, "if (published != nullptr)", "if (true)"), pipeline_source),
        (display_header, system_header, system_source, wm_window_source, shader_source, mutate_method(pipeline_source, RENDER_PIPELINE_MARKER, "if (published != nullptr)", "if (true)")),
    )
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate(*mutation)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("display_header", type=Path)
    parser.add_argument("system_header", type=Path)
    parser.add_argument("system_source", type=Path)
    parser.add_argument("wm_window_source", type=Path)
    parser.add_argument("shader_source", type=Path)
    parser.add_argument("pipeline_source", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    inputs = tuple(
        path.read_text(encoding="utf-8")
        for path in (
            args.display_header,
            args.system_header,
            args.system_source,
            args.wm_window_source,
            args.shader_source,
            args.pipeline_source,
        )
    )
    if args.selfcheck:
        selfcheck(*inputs)
    else:
        validate(*inputs)
    print("REDRAW_RECOVERY_CONTRACT PASS sources=6 mutations=30 bounded=180 readiness=4 drops=1 resize=rearmed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
