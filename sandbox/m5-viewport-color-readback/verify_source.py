#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail-closed source contract for the View3D viewport-colour continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SOURCE_PATHS = (
    "source/blender/gpu/GPU_readback.hh",
    "source/blender/gpu/GPU_texture.hh",
    "source/blender/gpu/intern/gpu_readback.cc",
    "source/blender/gpu/intern/gpu_texture.cc",
    "source/blender/editors/include/ED_view3d.hh",
    "source/blender/editors/space_view3d/view3d_draw.cc",
    "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
)


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def require_once(text: str, needle: str, label: str) -> None:
    count = text.count(needle)
    require(count == 1, f"{label}: expected one occurrence, found {count}")


def require_ordered(text: str, needles: tuple[str, ...], label: str) -> None:
    offset = 0
    for needle in needles:
        found = text.find(needle, offset)
        require(found >= 0, f"{label}: missing ordered fragment {needle!r}")
        offset = found + len(needle)


def braced_definition(text: str, marker: str, label: str) -> str:
    require_once(text, marker, label)
    start = text.index(marker)
    brace = text.find("{", start + len(marker))
    require(brace >= 0, f"{label}: opening brace missing")
    depth = 0
    index = brace
    state = "code"
    quote = ""
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if state == "line_comment":
            if char == "\n":
                state = "code"
        elif state == "block_comment":
            if char == "*" and next_char == "/":
                state = "code"
                index += 1
        elif state == "string":
            if char == "\\":
                index += 1
            elif char == quote:
                state = "code"
        else:
            if char == "/" and next_char == "/":
                state = "line_comment"
                index += 1
            elif char == "/" and next_char == "*":
                state = "block_comment"
                index += 1
            elif char in ('"', "'"):
                state = "string"
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        index += 1
    raise VerificationError(f"{label}: unterminated definition")


def read_sources(source_root: Path) -> dict[str, str]:
    sources: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = source_root / relative
        require(path.is_file(), f"missing source: {relative}")
        sources[relative] = path.read_text(encoding="utf-8")
    return sources


def source_digest(sources: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for relative in SOURCE_PATHS:
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(sources[relative].encode())
        digest.update(b"\0")
    return digest.hexdigest()


def validate(sources: dict[str, str]) -> dict[str, object]:
    header = sources["source/blender/editors/include/ED_view3d.hh"]
    draw = sources["source/blender/editors/space_view3d/view3d_draw.cc"]
    eyedropper = sources[
        "source/blender/editors/interface/eyedroppers/eyedropper_color.cc"
    ]
    texture_api = sources["source/blender/gpu/GPU_texture.hh"]
    texture_impl = sources["source/blender/gpu/intern/gpu_texture.cc"]
    readback_api = sources["source/blender/gpu/GPU_readback.hh"]
    readback_impl = sources["source/blender/gpu/intern/gpu_readback.cc"]

    session = braced_definition(header, "class ViewportColorSampleSession", "session class")
    for needle in (
        "enum class ReadbackState",
        "Pending",
        "Ready",
        "Failed",
        "GPUReadback *readback = nullptr;",
        "ReadbackState readback_state = ReadbackState::Failed;",
        "ReadbackState state();",
    ):
        require(needle in session, f"session class missing {needle!r}")

    init_body = braced_definition(draw, "bool ViewportColorSampleSession::init(", "session init")
    require_ordered(
        init_body,
        (
            "GPU_texture_copy(tex, color_tex);",
            "GPU_memory_barrier(GPU_BARRIER_TEXTURE_UPDATE);",
            "readback = GPU_texture_read_async(tex, GPU_DATA_HALF_FLOAT, 0);",
            "readback_state = ReadbackState::Pending;",
            "return state() != ReadbackState::Failed;",
        ),
        "session init",
    )
    require(
        "GPU_texture_read(tex, GPU_DATA_HALF_FLOAT, 0)" not in init_body,
        "session init retains synchronous texture read",
    )

    state_body = braced_definition(
        draw, "ViewportColorSampleSession::ReadbackState ViewportColorSampleSession::state(",
        "session state"
    )
    require_ordered(
        state_body,
        (
            "if (readback_state != ReadbackState::Pending)",
            "GPU_readback_status(readback)",
            "if (status == GPU_READBACK_PENDING)",
            "if (status != GPU_READBACK_READY)",
            "GPU_readback_size(readback) != byte_size",
            "MEM_new_array_uninitialized<ushort4>",
            "GPU_readback_consume(readback, result, byte_size)",
            "data = result;",
            "readback_state = ReadbackState::Ready;",
        ),
        "session state",
    )
    require(state_body.count("GPU_readback_cancel(readback);") >= 2,
            "session state does not retire failed ownership")

    sample_body = braced_definition(draw, "bool ViewportColorSampleSession::sample(", "sample")
    require_ordered(
        sample_body,
        ("state() != ReadbackState::Ready", "tex == nullptr || data == nullptr"),
        "sample readiness",
    )
    destructor = braced_definition(
        draw, "ViewportColorSampleSession::~ViewportColorSampleSession(", "destructor"
    )
    require_ordered(
        destructor,
        ("GPU_readback_cancel(readback);", "MEM_delete(data);", "GPU_texture_free(tex);"),
        "destructor ownership order",
    )

    sampling = braced_definition(
        eyedropper, "bool eyedropper_color_sample_fl(", "eyedropper sampling"
    )
    require_ordered(
        sampling,
        (
            "eye->viewport_session->init(region)",
            "ViewportColorSampleSession::ReadbackState::Pending",
            "return false;",
            "ViewportColorSampleSession::ReadbackState::Ready",
            "eye->viewport_session->sample(mval, r_col)",
            "ViewportColorSampleSession::ReadbackState::Failed",
            "MEM_delete(eye->viewport_session);",
            "eye->viewport_session = nullptr;",
            "WM_window_pixels_read_sample(C, win, event_xy_win, r_col)",
        ),
        "eyedropper pending/fallback order",
    )

    eyedropper_state = braced_definition(eyedropper, "struct Eyedropper", "eyedropper state")
    for needle in (
        "wmTimer *viewport_timer = nullptr;",
        "int viewport_event_xy[2] = {};",
        "int viewport_tick_count = 0;",
    ):
        require(needle in eyedropper_state, f"eyedropper state missing {needle!r}")
    exit_body = braced_definition(eyedropper, "static void eyedropper_exit(", "eyedropper exit")
    require_ordered(
        exit_body,
        (
            "WM_event_timer_remove(CTX_wm_manager(C), window, eye->viewport_timer);",
            "eye->viewport_timer = nullptr;",
            "MEM_delete(eye->viewport_session);",
        ),
        "timer/session cleanup",
    )
    sample_wrapper = braced_definition(
        eyedropper, "static bool eyedropper_color_sample(", "sample wrapper"
    )
    require_ordered(
        sample_wrapper,
        ("if (!eyedropper_color_sample_fl(", "return false;", "return true;"),
        "sample result propagation",
    )
    modal = braced_definition(eyedropper, "static wmOperatorStatus eyedropper_modal(", "modal")
    require_ordered(
        modal,
        (
            "event->type == TIMER",
            "constexpr int max_tick_count = 240;",
            "state == ViewportColorSampleSession::ReadbackState::Pending",
            "return OPERATOR_RUNNING_MODAL;",
            "state == ViewportColorSampleSession::ReadbackState::Failed",
            "eyedropper_color_sample(C, eye, eye->viewport_event_xy)",
            "eyedropper_exit(C, op);",
            "case EYE_MODAL_SAMPLE_CONFIRM:",
            "!eyedropper_color_sample(C, eye, event->xy)",
            "ViewportColorSampleSession::ReadbackState::Pending",
            "eye->viewport_event_xy[0] = event->xy[0];",
            "eye->viewport_tick_count = 0;",
            "eye->viewport_timer = WM_event_timer_add(",
            "return OPERATOR_RUNNING_MODAL;",
        ),
        "bounded confirm continuation",
    )

    for text, needle, label in (
        (texture_api, "GPU_texture_read_async(gpu::Texture *texture", "texture async API"),
        (texture_impl, "GPUReadback *Texture::read_async(", "native immediate result"),
        (readback_api, "bool GPU_readback_consume(GPUReadback *&readback", "owned consume API"),
        (readback_impl, "readback = nullptr;", "owned consume retirement"),
    ):
        require(needle in text, f"{label} missing")

    return {
        "schema": 1,
        "verdict": "PASS",
        "contracts": {
            "exact_owned_request": True,
            "pending_skips_sync_fallback": True,
            "native_immediate_completion": True,
            "failure_retryable": True,
            "live_hardware_receipt": False,
        },
        "retired_sync_family": "viewport_color_sample",
        "remaining_sync_family_count": 6,
        "source_count": len(SOURCE_PATHS),
        "source_sha256": source_digest(sources),
    }


def run_selfcheck(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        (
            "source/blender/editors/space_view3d/view3d_draw.cc",
            "GPU_texture_read_async(tex, GPU_DATA_HALF_FLOAT, 0)",
            "GPU_texture_read(tex, GPU_DATA_HALF_FLOAT, 0)",
            "async request",
        ),
        (
            "source/blender/editors/space_view3d/view3d_draw.cc",
            "GPU_readback_size(readback) != byte_size",
            "GPU_readback_size(readback) < byte_size",
            "exact size",
        ),
        (
            "source/blender/editors/space_view3d/view3d_draw.cc",
            "state() != ReadbackState::Ready",
            "state() == ReadbackState::Ready",
            "sample readiness",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
            "ViewportColorSampleSession::ReadbackState::Pending",
            "ViewportColorSampleSession::ReadbackState::Ready",
            "pending short circuit",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
            "if (state == ViewportColorSampleSession::ReadbackState::Failed) {\n"
            "            MEM_delete(eye->viewport_session);\n"
            "            eye->viewport_session = nullptr;",
            "if (state == ViewportColorSampleSession::ReadbackState::Failed) {\n"
            "            MEM_delete(eye->viewport_session);\n"
            "            eye->viewport_session = eye->viewport_session;",
            "failed retry",
        ),
        (
            "source/blender/editors/space_view3d/view3d_draw.cc",
            "ViewportColorSampleSession::~ViewportColorSampleSession()\n"
            "{\n"
            "  GPU_readback_cancel(readback);",
            "ViewportColorSampleSession::~ViewportColorSampleSession()\n"
            "{\n"
            "  /* canceled too late */",
            "cancellation",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
            "constexpr int max_tick_count = 240;",
            "constexpr int max_tick_count = -1;",
            "bounded confirm continuation",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
            "WM_event_timer_remove(CTX_wm_manager(C), window, eye->viewport_timer);",
            "/* leaked viewport timer */",
            "timer cleanup",
        ),
    )
    for relative, old, new, label in mutations:
        require(old in sources[relative], f"selfcheck {label}: mutation source missing")
        mutated = dict(sources)
        mutated[relative] = sources[relative].replace(old, new, 1)
        try:
            validate(mutated)
        except VerificationError:
            continue
        raise VerificationError(f"selfcheck mutation accepted: {label}")
    print(f"M5_VIEWPORT_COLOR_READBACK_SOURCE_SELFCHECK_PASS mutations={len(mutations)} allocation=zero")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    require(args.selfcheck != (args.output is not None), "choose one of --selfcheck/--output")
    sources = read_sources(args.source_root)
    if args.selfcheck:
        run_selfcheck(sources)
        return 0
    result = validate(sources)
    assert args.output is not None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "M5_VIEWPORT_COLOR_READBACK_SOURCE_PASS "
        f"files={result['source_count']} remaining=6 sha256={result['source_sha256']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as error:
        print(f"M5_VIEWPORT_COLOR_READBACK_SOURCE_FAIL {error}")
        raise SystemExit(1)
