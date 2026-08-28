#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail-closed contract for loader dismissal on validated VIEW_3D content."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DISPLAY = ROOT / "platform_web/ghost/GHOST_WebDisplayState.hh"
GHOST_CONTEXT = ROOT / "platform_web/ghost/GHOST_ContextWGPUWeb.cc"
WGPU_CONTEXT = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_context.cc"
FRAMEBUFFER = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_framebuffer.cc"
BOOT = ROOT / "platform_web/shell/boot-windowed.js"
MEASURE = ROOT / "sandbox/m4-frame-coherence/measure_boot.mjs"
PATCH = ROOT / "patches/0294-gpu-webgpu-viewport-content-ready.patch"
SERIES = ROOT / "patches/series"


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def require_once(source: str, token: str, label: str) -> None:
    require(source.count(token) == 1, f"{label}: count={source.count(token)} token={token!r}")


def method(source: str, marker: str) -> str:
    start = source.find(marker)
    require(start >= 0, f"missing method {marker!r}")
    opening = source.find("{", start)
    require(opening >= 0, f"missing body {marker!r}")
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ContractError(f"unterminated method {marker!r}")


def validate(sources: dict[str, str]) -> None:
    display = sources["display"]
    ghost = sources["ghost"]
    wgpu = sources["wgpu"]
    framebuffer = sources["framebuffer"]
    boot = sources["boot"]
    measure = sources["measure"]
    series = sources["series"]

    for token in (
        "OverlayGrid,",
        "RedrawTracePlan grid;",
        "redraw_trace_state.grid = {};",
        "inline bool viewport_content_trace_complete(",
        "inline std::atomic<uint64_t> viewport_content_present_counter{0};",
        "inline uint64_t viewport_content_present_count()",
        "inline bool note_viewport_content_presented(",
    ):
        require_once(display, token, "shared VIEW_3D readiness state")
    require_once(
        display,
        "pass == RedrawTracePass::OverlayGrid",
        "successful grid-plan capture",
    )
    strict = method(display, "inline bool viewport_content_trace_complete(")
    for token in (
        "redraw_present_trace_complete(trace, episode)",
        "trace.grid.sequence > 0u",
        "!trace.grid.window_target",
        "trace.display.sequence > trace.grid.sequence",
    ):
        require_once(strict, token, "strict VIEW_3D frame predicate")
    publish = method(display, "inline bool note_viewport_content_presented(")
    for token in (
        "viewport_content_trace_complete(trace, episode)",
        "viewport_content_present_counter.compare_exchange_strong(",
        "std::memory_order_release",
    ):
        require_once(publish, token, "one-shot VIEW_3D publication")
    recovery = method(display, "inline bool redraw_recovery_tick(")
    require_once(
        recovery,
        "if (viewport_content_present_count() == 0u)",
        "late readiness semantic-trace gate",
    )
    require(
        recovery.count("redraw_trace_begin(episode_generation);") == 2,
        "late readiness/input semantic tracing does not have exactly two rearm paths",
    )
    require_once(
        recovery,
        "if (reopen_trace && viewport_content_present_count() == 0u)",
        "late input semantic-trace gate",
    )

    require_once(
        ghost,
        'extern "C" EMSCRIPTEN_KEEPALIVE double bw_viewport_content_present_count(void)',
        "browser VIEW_3D export",
    )
    initialize = method(ghost, "GHOST_TSuccess GHOST_ContextWGPUWeb::initializeDrawingContext()")
    require_once(
        initialize,
        "backbuffer_redraw_episode_ = ghost_web::request_redraw_episode();",
        "cold-boot semantic trace",
    )
    present = method(ghost, "bool GHOST_ContextWGPUWeb::presentBackbuffer()")
    require_once(
        present,
        "ghost_web::note_viewport_content_presented(redraw_trace, redraw_trace_episode)",
        "validated surface publication",
    )
    publish_at = present.index(
        "ghost_web::note_viewport_content_presented(redraw_trace, redraw_trace_episode)"
    )
    require(present.index("if (!valid)") < publish_at < present.index("ghost_web::note_present();"),
            "VIEW_3D readiness is not published between validation and present accounting")

    end_frame = method(wgpu, "void WGPUContext::end_frame()")
    for token in (
        "const bool viewport_content_pending =",
        "ghost_web::viewport_content_present_count() == 0u;",
        "viewport_content_pending ?",
        "ghost_web::viewport_content_trace_complete(completed_frame, episode) :",
        "ghost_web::redraw_present_trace_complete(completed_frame, episode);",
        "frame_complete &&",
        "ghost_web::schedule_redraw_present_barrier(",
    ):
        require_once(end_frame, token, "queue-tail VIEW_3D admission")

    note = method(framebuffer, "void WGPUFrameBuffer::debug_note_draw(")
    require_once(
        note,
        'std::strcmp(shader_name, "overlay_grid_next") == 0',
        "successful grid draw trace",
    )
    require_once(note, "RedrawTracePass::OverlayGrid", "grid trace classification")

    for token in (
        "VIEWPORT_CONTENT_LOADER_GATE_V1",
        "function armViewportContentGate(mod)",
        'typeof mod._bw_viewport_content_present_count === "function"',
        "const contentPresents = Number(mod._bw_viewport_content_present_count());",
        "Number.isFinite(contentPresents) && contentPresents > 0",
        'noteViewportContentReady("validated VIEW_3D frame")',
        '"; loader remains visible", "err")',
    ):
        require_once(boot, token, "shell VIEW_3D loader gate")
    gate = method(boot, "function armViewportContentGate(mod)")
    require("_bw_present_count" not in gate, "generic presents remain loader-authoritative")
    require('noteViewportContentReady("presentBackbuffer")' not in boot,
            "present log can dismiss the loader")

    for token in (
        'contract: "fallback-boot-frame-coherence-diagnostic-v2"',
        'typeof mod?._bw_viewport_content_present_count === "function" ?',
        "loaderHidden && !(Number(loaderHidden.viewportContentPresents) > 0)",
        'if (!firstViewportContent) failures.push("no validated VIEW_3D content presentation");',
        'if (!loaderHidden) failures.push("loader did not dismiss after validated VIEW_3D content");',
        "if (failures.length !== 0)",
    ):
        require_once(measure, token, "exact-product VIEW_3D diagnostic")

    require(PATCH.is_file(), "numbered patch 0294 is missing")
    require_once(series, PATCH.name, "numbered patch series")


def mutate_once(source: str, old: str, new: str) -> str:
    require_once(source, old, "mutation anchor")
    return source.replace(old, new, 1)


def selfcheck(sources: dict[str, str]) -> int:
    validate(sources)
    mutations = (
        ("display", "trace.grid.sequence > 0u", "true"),
        ("display", "!trace.grid.window_target", "true"),
        ("display", "trace.display.sequence > trace.grid.sequence", "true"),
        ("display", "viewport_content_trace_complete(trace, episode)", "true"),
        ("display", "if (viewport_content_present_count() == 0u)", "if (false)"),
        ("ghost", "backbuffer_redraw_episode_ = ghost_web::request_redraw_episode();",
         "backbuffer_redraw_episode_ = ghost_web::redraw_episode_generation();"),
        ("ghost", "ghost_web::note_viewport_content_presented(redraw_trace, redraw_trace_episode)",
         "false"),
        ("wgpu", "ghost_web::viewport_content_present_count() == 0u;", "false;"),
        ("wgpu", "ghost_web::viewport_content_trace_complete(completed_frame, episode) :",
         "ghost_web::redraw_present_trace_complete(completed_frame, episode) :"),
        ("framebuffer", 'std::strcmp(shader_name, "overlay_grid_next") == 0', "false"),
        ("boot", 'typeof mod._bw_viewport_content_present_count === "function"',
         'typeof mod._bw_present_count === "function"'),
        ("boot", "contentPresents > 0", "contentPresents >= 0"),
        ("measure", 'typeof mod?._bw_viewport_content_present_count === "function" ?',
         'typeof mod?._bw_present_count === "function" ?'),
        ("measure", "if (!firstViewportContent)", "if (false)"),
        ("measure", "loaderHidden && !(Number(loaderHidden.viewportContentPresents) > 0)",
         "false"),
        ("measure", "if (failures.length !== 0)", "if (false)"),
        ("series", PATCH.name, ""),
    )
    rejected = 0
    for name, old, new in mutations:
        changed = dict(sources)
        changed[name] = mutate_once(changed[name], old, new)
        try:
            validate(changed)
        except ContractError:
            rejected += 1
            continue
        raise ContractError(f"mutation survived: {name}:{old!r}")
    return rejected


def load_sources() -> dict[str, str]:
    return {
        "display": DISPLAY.read_text(encoding="utf-8"),
        "ghost": GHOST_CONTEXT.read_text(encoding="utf-8"),
        "wgpu": WGPU_CONTEXT.read_text(encoding="utf-8"),
        "framebuffer": FRAMEBUFFER.read_text(encoding="utf-8"),
        "boot": BOOT.read_text(encoding="utf-8"),
        "measure": MEASURE.read_text(encoding="utf-8"),
        "series": SERIES.read_text(encoding="utf-8"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    sources = load_sources()
    rejected = selfcheck(sources) if args.selfcheck else 0
    validate(sources)
    print(
        "M4_VIEWPORT_CONTENT_LOADER_PASS "
        f"sources={len(sources)} negative={rejected} "
        "signal=overlay-background,grid,display,validated-present"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        raise SystemExit(f"M4_VIEWPORT_CONTENT_LOADER_FAIL {error}") from error
