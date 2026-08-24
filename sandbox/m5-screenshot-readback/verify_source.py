#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail-closed source contract for the stock screenshot async continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SOURCE_PATHS = (
    "source/blender/gpu/GPU_readback.hh",
    "source/blender/gpu/GPU_texture.hh",
    "source/blender/windowmanager/WM_api.hh",
    "source/blender/windowmanager/intern/wm_draw.cc",
    "source/blender/editors/screen/screendump.cc",
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
    api = sources["source/blender/windowmanager/WM_api.hh"]
    draw = sources["source/blender/windowmanager/intern/wm_draw.cc"]
    screenshot = sources["source/blender/editors/screen/screendump.cc"]
    texture_api = sources["source/blender/gpu/GPU_texture.hh"]
    readback_api = sources["source/blender/gpu/GPU_readback.hh"]

    for needle in (
        "struct WMWindowPixelsRead;",
        "enum class WMWindowPixelsReadStatus",
        "WM_window_pixels_read_async(bContext *C, wmWindow *win)",
        "WM_window_pixels_read_async_status(WMWindowPixelsRead *readback)",
        "WM_window_pixels_read_async_consume(WMWindowPixelsRead *&readback",
        "WM_window_pixels_read_async_cancel(WMWindowPixelsRead *&readback)",
    ):
        require(needle in api, f"WM owned-capture API missing {needle!r}")

    capture_state = braced_definition(draw, "struct WMWindowPixelsRead", "capture state")
    for needle in (
        "GPUOffScreen *offscreen = nullptr;",
        "GPUReadback *readback = nullptr;",
        "std::vector<uint8_t> native_bytes;",
        "size_t expected_size = 0;",
    ):
        require(needle in capture_state, f"capture state missing {needle!r}")

    begin = braced_definition(
        draw, "WMWindowPixelsRead *WM_window_pixels_read_async(", "capture begin"
    )
    require_ordered(
        begin,
        (
            "wm_window_pixels_read_size(win_size, expected_size)",
            "GPU_TEXTURE_USAGE_SHADER_READ | GPU_TEXTURE_USAGE_HOST_READ",
            "GPU_offscreen_bind(offscreen, false);",
            "wm_draw_window_onscreen(C, win, -1);",
            "GPU_offscreen_unbind(offscreen, false);",
            "#ifdef __EMSCRIPTEN__",
            "GPU_texture_read_async(",
            "GPU_DATA_UBYTE",
            "#else",
            "GPU_offscreen_read_color(offscreen, GPU_DATA_UBYTE",
            "#endif",
        ),
        "capture begin",
    )

    status = braced_definition(
        draw,
        "WMWindowPixelsReadStatus WM_window_pixels_read_async_status(",
        "capture status",
    )
    require_ordered(
        status,
        (
            "GPU_readback_status(readback->readback)",
            "GPU_READBACK_PENDING",
            "GPU_READBACK_READY",
            "GPU_readback_size(readback->readback) != readback->expected_size",
            "wm_window_pixels_read_offscreen_release(readback);",
            "WMWindowPixelsReadStatus::Ready",
        ),
        "capture status",
    )

    consume = braced_definition(
        draw,
        "uint8_t *WM_window_pixels_read_async_consume(",
        "capture consume",
    )
    require_ordered(
        consume,
        (
            "WM_window_pixels_read_async_status(readback) != WMWindowPixelsReadStatus::Ready",
            "MEM_new_array_uninitialized<uint8_t>",
            "GPU_readback_consume(readback->readback, pixels, readback->expected_size)",
            "#ifdef __EMSCRIPTEN__",
            "wm_window_pixels_read_flip_rows(pixels, readback->size);",
            "#endif",
            "WM_window_pixels_read_async_cancel(readback);",
        ),
        "capture consume",
    )
    cancel = braced_definition(
        draw,
        "void WM_window_pixels_read_async_cancel(",
        "capture cancel",
    )
    require_ordered(
        cancel,
        (
            "GPU_readback_cancel(readback->readback);",
            "wm_window_pixels_read_offscreen_release(readback);",
            "MEM_delete(readback);",
            "readback = nullptr;",
        ),
        "capture cancel",
    )

    data = braced_definition(screenshot, "struct ScreenshotData", "screenshot data")
    for needle in (
        "WMWindowPixelsRead *readback = nullptr;",
        "wmTimer *readback_timer = nullptr;",
        "wmWindow *readback_timer_window = nullptr;",
        "int readback_tick_count = 0;",
    ):
        require(needle in data, f"screenshot state missing {needle!r}")

    create = braced_definition(
        screenshot, "static int screenshot_data_create(", "screenshot create"
    )
    require_ordered(
        create,
        (
            "WM_redraw_windows(C);",
            "WM_window_pixels_read_async(C, win);",
            "op->customdata = scd;",
        ),
        "screenshot create",
    )
    require(
        "WM_window_pixels_read(C, win" not in create,
        "screenshot create retains synchronous window read",
    )

    free = braced_definition(
        screenshot, "static void screenshot_data_free(", "screenshot free"
    )
    require_ordered(
        free,
        (
            "WM_event_timer_remove(",
            "scd->readback_timer = nullptr;",
            "WM_window_pixels_read_async_cancel(scd->readback);",
            "MEM_delete(scd);",
            "op->customdata = nullptr;",
        ),
        "screenshot cleanup",
    )

    exec_body = braced_definition(
        screenshot, "static wmOperatorStatus screenshot_exec(", "screenshot exec"
    )
    require_ordered(
        exec_body,
        (
            "WM_window_pixels_read_async_status(scd->readback)",
            "WMWindowPixelsReadStatus::Pending",
            "WM_event_timer_add(",
            "WM_event_add_modal_handler(C, op);",
            "return OPERATOR_RUNNING_MODAL;",
            "WMWindowPixelsReadStatus::Ready",
            "WM_window_pixels_read_async_consume(",
            "scd->dumprect = dumprect;",
        ),
        "screenshot exec continuation",
    )
    require(
        "WM_window_pixels_read(C, win" not in exec_body,
        "screenshot exec retains synchronous window read",
    )

    invoke = braced_definition(
        screenshot, "static wmOperatorStatus screenshot_invoke(", "screenshot invoke"
    )
    require_ordered(
        invoke,
        (
            "screenshot_data_create(C, op, area)",
            "RNA_struct_property_is_set(op->ptr, \"filepath\")",
            "return screenshot_exec(C, op);",
            "WM_event_add_fileselect(C, op);",
        ),
        "capture-before-file-selector",
    )

    modal = braced_definition(
        screenshot, "static wmOperatorStatus screenshot_modal(", "screenshot modal"
    )
    require_ordered(
        modal,
        (
            "event->type != TIMER",
            "event->customdata != scd->readback_timer",
            "constexpr int max_tick_count = 240;",
            "WM_window_pixels_read_async_status(scd->readback)",
            "WMWindowPixelsReadStatus::Pending",
            "scd->readback_tick_count++",
            "screenshot_data_free(C, op);",
            "return OPERATOR_CANCELLED;",
            "return screenshot_exec(C, op);",
        ),
        "bounded screenshot modal",
    )
    registration = braced_definition(
        screenshot, "static void screen_screenshot_impl(", "operator registration"
    )
    require(
        "ot->modal = screenshot_modal;" in registration,
        "screenshot modal callback is not registered",
    )

    for text, needle, label in (
        (texture_api, "GPU_texture_read_async(gpu::Texture *texture", "texture async API"),
        (readback_api, "bool GPU_readback_consume(GPUReadback *&readback", "owned consume API"),
    ):
        require(needle in text, f"{label} missing")

    return {
        "schema": 1,
        "verdict": "PASS",
        "contracts": {
            "exact_owned_capture": True,
            "pending_survives_file_selector": True,
            "bounded_modal_poll": True,
            "cancel_before_offscreen_release": True,
            "native_immediate_completion": True,
            "live_hardware_receipt": False,
        },
        "retired_sync_family": "screenshot_operator",
        "remaining_sync_family_count": 5,
        "source_count": len(SOURCE_PATHS),
        "source_sha256": source_digest(sources),
    }


def run_selfcheck(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        (
            "source/blender/windowmanager/intern/wm_draw.cc",
            "GPU_TEXTURE_USAGE_SHADER_READ | GPU_TEXTURE_USAGE_HOST_READ",
            "GPU_TEXTURE_USAGE_SHADER_READ",
            "host-read usage",
        ),
        (
            "source/blender/windowmanager/intern/wm_draw.cc",
            "GPU_readback_size(readback->readback) != readback->expected_size",
            "GPU_readback_size(readback->readback) < readback->expected_size",
            "exact byte size",
        ),
        (
            "source/blender/windowmanager/intern/wm_draw.cc",
            "wm_window_pixels_read_flip_rows(pixels, readback->size);",
            "/* row orientation omitted */",
            "row orientation",
        ),
        (
            "source/blender/windowmanager/intern/wm_draw.cc",
            "GPU_readback_cancel(readback->readback);",
            "/* pending request leaked */",
            "cancel order",
        ),
        (
            "source/blender/editors/screen/screendump.cc",
            "WM_window_pixels_read_async(C, win);",
            "WM_window_pixels_read(C, win, dumprect_size);",
            "async capture",
        ),
        (
            "source/blender/editors/screen/screendump.cc",
            "constexpr int max_tick_count = 240;",
            "constexpr int max_tick_count = -1;",
            "bounded continuation",
        ),
        (
            "source/blender/editors/screen/screendump.cc",
            "WM_event_add_modal_handler(C, op);",
            "/* modal owner omitted */",
            "modal ownership",
        ),
        (
            "source/blender/editors/screen/screendump.cc",
            "WM_window_pixels_read_async_cancel(scd->readback);",
            "/* capture not canceled */",
            "operator cancel",
        ),
    )
    for relative, old, new, label in mutations:
        require_once(sources[relative], old, f"selfcheck {label}")
        mutated = dict(sources)
        mutated[relative] = sources[relative].replace(old, new, 1)
        try:
            validate(mutated)
        except VerificationError:
            continue
        raise VerificationError(f"selfcheck mutation accepted: {label}")
    print(
        "M5_SCREENSHOT_READBACK_SOURCE_SELFCHECK_PASS "
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
        "M5_SCREENSHOT_READBACK_SOURCE_PASS "
        f"files={result['source_count']} remaining=5 sha256={result['source_sha256']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as error:
        print(f"M5_SCREENSHOT_READBACK_SOURCE_FAIL {error}")
        raise SystemExit(1)
