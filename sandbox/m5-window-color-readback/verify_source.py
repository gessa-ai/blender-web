#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail-closed source contract for shared asynchronous window-colour sampling."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SOURCE_PATHS = (
    "source/blender/editors/interface/eyedroppers/eyedropper_intern.hh",
    "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
    "source/blender/editors/interface/eyedroppers/eyedropper_colorband.cc",
    "source/blender/editors/interface/eyedroppers/eyedropper_grease_pencil_color.cc",
    "source/blender/windowmanager/WM_api.hh",
    "source/blender/windowmanager/intern/wm_draw.cc",
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
    brace = text.find("{", start)
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
    api = sources["source/blender/editors/interface/eyedroppers/eyedropper_intern.hh"]
    color = sources["source/blender/editors/interface/eyedroppers/eyedropper_color.cc"]
    colorband = sources[
        "source/blender/editors/interface/eyedroppers/eyedropper_colorband.cc"
    ]
    grease = sources[
        "source/blender/editors/interface/eyedroppers/eyedropper_grease_pencil_color.cc"
    ]
    wm_api = sources["source/blender/windowmanager/WM_api.hh"]
    wm_draw = sources["source/blender/windowmanager/intern/wm_draw.cc"]

    session_class = braced_definition(
        api, "class EyedropperWindowColorSampleSession", "window session class"
    )
    for needle in (
        "enum class ReadbackState",
        "Pending",
        "Ready",
        "Failed",
        "wmWindow *window_ = nullptr;",
        "WMWindowPixelsRead *readback_ = nullptr;",
        "unsigned char *pixels_ = nullptr;",
        "bool init(bContext *C, wmWindow *window);",
        "ReadbackState state();",
        "bool sample(const int pos[2], float r_col[3]);",
        "void cancel();",
    ):
        require(needle in session_class, f"window session class missing {needle!r}")
    require(
        "EyedropperWindowColorSampleSession *window_session" in api,
        "shared sampler does not require an owned window session",
    )

    init = braced_definition(
        color,
        "bool EyedropperWindowColorSampleSession::init(",
        "window session init",
    )
    require_ordered(
        init,
        (
            "window_ == window && state_ != ReadbackState::Failed",
            "cancel();",
            "WM_window_pixels_read_async(C, window)",
            "if (readback_ == nullptr)",
            "state_ = ReadbackState::Failed;",
            "window_ = window;",
            "state_ = ReadbackState::Pending;",
        ),
        "window session init",
    )

    state = braced_definition(
        color,
        "EyedropperWindowColorSampleSession::ReadbackState "
        "EyedropperWindowColorSampleSession::state()",
        "window session state",
    )
    require_ordered(
        state,
        (
            "if (state_ != ReadbackState::Pending)",
            "WM_window_pixels_read_async_status(readback_)",
            "WMWindowPixelsReadStatus::Pending",
            "status != WMWindowPixelsReadStatus::Ready",
            "WM_window_pixels_read_async_cancel(readback_);",
            "state_ = ReadbackState::Failed;",
            "WM_window_pixels_read_async_consume(readback_, size_)",
            "pixels_ == nullptr || size_[0] <= 0 || size_[1] <= 0",
            "state_ = ReadbackState::Ready;",
        ),
        "window session state",
    )

    sample = braced_definition(
        color,
        "bool EyedropperWindowColorSampleSession::sample(",
        "window session sample",
    )
    require_ordered(
        sample,
        (
            "state() != ReadbackState::Ready",
            "uint(pos[0]) >= uint(size_[0])",
            "uint(pos[1]) >= uint(size_[1])",
            "size_t(pos[1]) * size_t(size_[0]) + size_t(pos[0])",
            "float(pixel[0]) / 255.0f",
            "float(pixel[1]) / 255.0f",
            "float(pixel[2]) / 255.0f",
        ),
        "window session sample",
    )
    cancel = braced_definition(
        color,
        "void EyedropperWindowColorSampleSession::cancel()",
        "window session cancel",
    )
    require_ordered(
        cancel,
        (
            "WM_window_pixels_read_async_cancel(readback_);",
            "MEM_SAFE_DELETE(pixels_);",
            "window_ = nullptr;",
            "state_ = ReadbackState::Invalid;",
        ),
        "window session cancel",
    )

    sampling = braced_definition(color, "bool eyedropper_color_sample_fl(", "shared sampling")
    require_ordered(
        sampling,
        (
            "window_session->cancel();",
            "EyedropperReadbackSource::Viewport",
            "WM_CAPABILITY_GPU_FRONT_BUFFER_READ",
            "WM_window_pixels_read_sample(C, win, event_xy_win, r_col)",
            "window_session == nullptr || !window_session->init(C, win)",
            "window_session->state()",
            "ReadbackState::Pending",
            "EyedropperReadbackSource::Window",
            "return false;",
            "window_session->sample(event_xy_win, r_col)",
        ),
        "shared sampling",
    )
    require(
        "WM_window_pixels_read_sample_from_offscreen(C, win, event_xy_win, r_col)"
        not in sampling,
        "shared sampler retains the synchronous offscreen fallback",
    )

    eye_state = braced_definition(color, "struct Eyedropper", "color eyedropper state")
    for needle in (
        "EyedropperWindowColorSampleSession window_session;",
        "wmTimer *readback_timer = nullptr;",
        "EyedropperReadbackSource readback_source",
    ):
        require(needle in eye_state, f"color eyedropper state missing {needle!r}")
    eye_exit = braced_definition(color, "static void eyedropper_exit(", "color eyedropper exit")
    require_ordered(
        eye_exit,
        (
            "WM_event_timer_remove(",
            "MEM_delete(eye->viewport_session);",
            "eye->window_session.cancel();",
            "MEM_delete(eye);",
        ),
        "color eyedropper cleanup",
    )
    eye_modal = braced_definition(color, "static wmOperatorStatus eyedropper_modal(", "color modal")
    for needle in (
        "constexpr int max_tick_count = 240;",
        "EyedropperReadbackSource::Viewport",
        "EyedropperReadbackSource::Window",
        "eye->window_session.state();",
        "eyedropper_color_sample(C, eye, eye->readback_event_xy)",
        "eye->readback_source != EyedropperReadbackSource::None",
        "eye->readback_timer = WM_event_timer_add(",
    ):
        require(needle in eye_modal, f"color modal continuation missing {needle!r}")

    colorband_state = braced_definition(
        colorband, "struct EyedropperColorband {", "colorband state"
    )
    for needle in (
        "EyedropperWindowColorSampleSession window_session;",
        "wmTimer *readback_timer = nullptr;",
        "ColorbandReadbackAction readback_action",
    ):
        require(needle in colorband_state, f"colorband state missing {needle!r}")
    colorband_sample = braced_definition(
        colorband, "static bool eyedropper_colorband_sample_point(", "colorband sample"
    )
    require_ordered(
        colorband_sample,
        (
            "eyedropper_color_sample_fl(C, nullptr, &eye->window_session",
            "return false;",
            "eye->color_buffer.append(col);",
        ),
        "colorband sample",
    )
    require(colorband.count("constexpr int max_tick_count = 240;") == 2,
            "colorband must bound both modal continuations")
    for needle in (
        "ColorbandReadbackAction::GradientFinish",
        "ColorbandReadbackAction::PointSample",
        "eye->readback_timer = WM_event_timer_add(",
        "eye->window_session.cancel();",
    ):
        require(needle in colorband, f"colorband continuation missing {needle!r}")

    grease_state = braced_definition(
        grease, "struct EyedropperGreasePencil", "grease pencil state"
    )
    for needle in (
        "EyedropperWindowColorSampleSession window_session;",
        "wmTimer *readback_timer = nullptr;",
        "int readback_modifier = 0;",
    ):
        require(needle in grease_state, f"grease pencil state missing {needle!r}")
    grease_sample = braced_definition(
        grease,
        "static bool eyedropper_grease_pencil_color_sample(",
        "grease pencil sample",
    )
    require_ordered(
        grease_sample,
        (
            "eyedropper_color_sample_fl(C, nullptr, &eye->window_session",
            "return false;",
            "eye->accum_col += col;",
        ),
        "grease pencil sample",
    )
    for needle in (
        "constexpr int max_tick_count = 240;",
        "eye->window_session.state();",
        "eye->readback_modifier = event->modifier;",
        "eye->readback_timer = WM_event_timer_add(",
        "eye->window_session.cancel();",
    ):
        require(needle in grease, f"grease pencil continuation missing {needle!r}")

    for needle in (
        "WM_window_pixels_read_async(bContext *C, wmWindow *win)",
        "WM_window_pixels_read_async_status(WMWindowPixelsRead *readback)",
        "WM_window_pixels_read_async_consume(WMWindowPixelsRead *&readback",
        "WM_window_pixels_read_async_cancel(WMWindowPixelsRead *&readback)",
    ):
        require(needle in wm_api, f"owned WM snapshot API missing {needle!r}")
    for needle in (
        "GPU_TEXTURE_USAGE_SHADER_READ | GPU_TEXTURE_USAGE_HOST_READ",
        "GPU_texture_read_async(",
        "wm_window_pixels_read_flip_rows",
    ):
        require(needle in wm_draw, f"owned WM snapshot implementation missing {needle!r}")

    return {
        "schema": 1,
        "verdict": "PASS",
        "contracts": {
            "owned_window_snapshot": True,
            "three_modal_consumers": True,
            "exact_pixel_decode": True,
            "bounded_poll": True,
            "cancel_before_owner_release": True,
            "native_immediate_completion": True,
            "live_hardware_receipt": False,
        },
        "retired_sync_family": "window_color_sample",
        "remaining_sync_family_count": 4,
        "source_count": len(SOURCE_PATHS),
        "source_sha256": source_digest(sources),
    }


def run_selfcheck(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_intern.hh",
            "WMWindowPixelsRead *readback_ = nullptr;",
            "WMWindowPixelsRead *readback_ = reinterpret_cast<WMWindowPixelsRead *>(1);",
            "owned request initialization",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
            "WM_window_pixels_read_async(C, window)",
            "WM_window_pixels_read(C, window, size_)",
            "async snapshot",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
            "WM_window_pixels_read_async_consume(readback_, size_)",
            "nullptr",
            "owned consume",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
            "float(pixel[0]) / 255.0f",
            "float(pixel[0])",
            "pixel normalization",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
            "WM_window_pixels_read_async_cancel(readback_);",
            "/* request leaked */",
            "session cancellation",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
            "window_session == nullptr || !window_session->init(C, win)",
            "WM_window_pixels_read_sample_from_offscreen(C, win, event_xy_win, r_col)",
            "sync fallback rejection",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_color.cc",
            "constexpr int max_tick_count = 240;",
            "constexpr int max_tick_count = -1;",
            "color timeout",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_colorband.cc",
            "&eye->window_session, m_xy, col",
            "nullptr, m_xy, col",
            "colorband owner",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_colorband.cc",
            "constexpr int max_tick_count = 240;",
            "constexpr int max_tick_count = -1;",
            "colorband timeout",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_grease_pencil_color.cc",
            "&eye->window_session, m_xy, col",
            "nullptr, m_xy, col",
            "grease pencil owner",
        ),
        (
            "source/blender/editors/interface/eyedroppers/eyedropper_grease_pencil_color.cc",
            "eye->window_session.cancel();",
            "/* session leaked */",
            "grease pencil cleanup",
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
    print(
        "M5_WINDOW_COLOR_READBACK_SOURCE_SELFCHECK_PASS "
        f"mutations={len(mutations)} allocation=zero"
    )


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
        "M5_WINDOW_COLOR_READBACK_SOURCE_PASS "
        f"files={result['source_count']} remaining=4 sha256={result['source_sha256']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as error:
        print(f"M5_WINDOW_COLOR_READBACK_SOURCE_FAIL {error}")
        raise SystemExit(1)
