#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail-closed source contract for the asset-preview WM capture continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ASSET = Path("source/blender/editors/asset/intern/asset_ops.cc")
PYTHON_WM = Path("source/blender/python/intern/bpy_rna_wm.cc")
WM_API = Path("source/blender/windowmanager/WM_api.hh")
WM_DRAW = Path("source/blender/windowmanager/intern/wm_draw.cc")
PATHS = (ASSET, PYTHON_WM, WM_API, WM_DRAW)


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def require_once(text: str, needle: str, label: str) -> None:
    count = text.count(needle)
    require(count == 1, f"{label}: expected one occurrence, found {count}")


def function_body(text: str, signature: str, *, last: bool = False) -> str:
    if last:
        require(signature in text, f"missing signature: {signature}")
        start = text.rindex(signature)
    else:
        require_once(text, signature, signature)
        start = text.index(signature)
    brace = text.find("{", start + len(signature))
    require(brace >= 0, f"missing function body: {signature}")
    depth = 0
    state = "code"
    quote = ""
    index = brace
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
    raise VerificationError(f"unterminated function body: {signature}")


def require_ordered(text: str, needles: tuple[str, ...], label: str) -> None:
    offset = 0
    for needle in needles:
        found = text.find(needle, offset)
        require(found >= 0, f"{label}: missing ordered token {needle!r}")
        offset = found + len(needle)


def read_sources(root: Path) -> dict[Path, str]:
    sources: dict[Path, str] = {}
    for relative in PATHS:
        path = root / relative
        require(path.is_file(), f"missing source: {relative}")
        sources[relative] = path.read_text(encoding="utf-8")
    return sources


def source_digest(sources: dict[Path, str]) -> str:
    digest = hashlib.sha256()
    for path in PATHS:
        digest.update(str(path).encode())
        digest.update(b"\0")
        digest.update(sources[path].encode())
        digest.update(b"\0")
    return digest.hexdigest()


def validate(sources: dict[Path, str]) -> dict[str, object]:
    asset = sources[ASSET]
    python_wm = sources[PYTHON_WM]
    wm_api = sources[WM_API]
    wm_draw = sources[WM_DRAW]

    for needle in (
        "WM_window_pixels_read_async(bContext *C, wmWindow *win)",
        "WM_window_pixels_read_async_status(WMWindowPixelsRead *readback)",
        "WM_window_pixels_read_async_consume(WMWindowPixelsRead *&readback",
        "WM_window_pixels_read_async_cancel(WMWindowPixelsRead *&readback)",
    ):
        require(needle in wm_api, f"owned WM capture API missing {needle!r}")

    wm_begin = function_body(
        wm_draw, "WMWindowPixelsRead *WM_window_pixels_read_async(",
    )
    require_ordered(
        wm_begin,
        (
            "#ifdef __EMSCRIPTEN__",
            "GPU_texture_read_async(",
            "#else",
            "GPU_offscreen_read_color(offscreen, GPU_DATA_UBYTE",
            "#endif",
        ),
        "native-immediate/browser-owned WM primitive",
    )

    state = function_body(asset, "struct ScreenshotOperatorData")
    for needle in (
        "bool interactive = false;",
        "wmWindow *operator_window = nullptr;",
        "WMWindowPixelsRead *readback = nullptr;",
        "wmTimer *readback_timer = nullptr;",
        "wmWindowManager *readback_manager = nullptr;",
        "wmWindow *readback_window = nullptr;",
        "bScreen *readback_screen = nullptr;",
        "Main *readback_main = nullptr;",
        "std::optional<ID_Type> readback_id_type;",
        "std::optional<AssetWeakReference> readback_asset_reference;",
        "rcti readback_crop = {};",
        "int readback_tick_count = 0;",
    ):
        require(needle in state, f"owned operator state missing {needle!r}")

    require(
        "WM_window_pixels_read(C, win, dumprect_size)" not in asset,
        "asset-preview operator retains synchronous WM capture",
    )
    require(
        python_wm.count("WM_window_pixels_read(C, win, dumprect_size)") == 1,
        "separate synchronous Python screenshot caller census drifted",
    )

    crop = function_body(asset, "static ImBuf *take_screenshot_crop(")
    require_ordered(
        crop,
        (
            "uint8_t *dumprect",
            "dumprect == nullptr",
            "BLI_rcti_is_valid(&safe_rect)",
            "image_buffer->assign_byte_data(dumprect);",
            "IMB_crop(image_buffer",
        ),
        "owned crop",
    )
    require("WM_window_pixels_read" not in crop, "crop helper starts another WM read")

    store = function_body(asset, "static bool screenshot_preview_readback_context_store(")
    require_ordered(
        store,
        (
            "CTX_wm_asset(C)",
            "data->readback_manager = CTX_wm_manager(C);",
            "data->readback_window = CTX_wm_window(C);",
            "data->readback_screen = CTX_wm_screen(C);",
            "data->readback_main = CTX_data_main(C);",
            "data->readback_id_type = asset_handle->get_id_type();",
            "data->readback_asset_reference = asset_handle->make_weak_reference();",
        ),
        "producing context snapshot",
    )

    matches = function_body(asset, "static bool screenshot_preview_readback_context_matches(")
    for needle in (
        "CTX_wm_manager(C) != data->readback_manager",
        "CTX_wm_window(C) != data->readback_window",
        "CTX_wm_screen(C) != data->readback_screen",
        "CTX_data_main(C) != data->readback_main",
        "asset_handle->get_id_type() == *data->readback_id_type",
        "asset_handle->make_weak_reference() == *data->readback_asset_reference",
    ):
        require(needle in matches, f"producing context guard missing {needle!r}")

    apply = function_body(asset, "static wmOperatorStatus screenshot_preview_apply(")
    require_ordered(
        apply,
        (
            "screenshot_preview_readback_context_matches(C, data)",
            "*data->readback_asset_reference",
            "*data->readback_id_type",
            "data->readback_main",
            "bke::asset_edit_id_from_weak_reference(",
            "generate_previewimg_from_buffer(id, image_buffer);",
            "asset::refresh_asset_library_from_asset(C, *asset_handle);",
        ),
        "exact target application",
    )

    poll = function_body(asset, "static wmOperatorStatus screenshot_preview_readback_poll(")
    require_ordered(
        poll,
        (
            "screenshot_preview_readback_context_matches(C, data)",
            "WM_window_pixels_read_async_status(data->readback)",
            "WMWindowPixelsReadStatus::Pending",
            "WM_event_timer_add(",
            "if (!data->interactive)",
            "WM_event_add_modal_handler(C, op);",
            "WMWindowPixelsReadStatus::Ready",
            "WM_window_pixels_read_async_consume(data->readback, dumprect_size)",
            "take_screenshot_crop(dumprect, dumprect_size, data->readback_crop)",
            "screenshot_preview_apply(C, op, image_buffer, data)",
            "screenshot_preview_exit(C, op);",
        ),
        "readback poll",
    )

    execute = function_body(asset, "static wmOperatorStatus screenshot_preview_exec(")
    require_ordered(
        execute,
        (
            "data->readback != nullptr",
            "screenshot_preview_readback_poll(C, op, data)",
            "ED_view3d_draw_offscreen_imbuf(",
            "data->readback_crop = {p1.x, p2.x + 1, p1.y, p2.y + 1};",
            "screenshot_preview_readback_context_store(C, data)",
            "data->readback = WM_window_pixels_read_async(C, win);",
            "screenshot_preview_readback_poll(C, op, data)",
        ),
        "operator execute",
    )
    require(
        execute.count("WM_window_pixels_read_async(C, win)") == 1,
        "operator async capture multiplicity differs",
    )

    modal = function_body(asset, "static wmOperatorStatus screenshot_preview_modal(")
    require_ordered(
        modal,
        (
            "if (data->readback != nullptr)",
            "ELEM(event->type, RIGHTMOUSE, EVT_ESCKEY)",
            "event->type != TIMER || event->customdata != data->readback_timer",
            "constexpr int max_tick_count = 240;",
            "screenshot_preview_readback_context_matches(C, data)",
            "WM_window_pixels_read_async_status(data->readback)",
            "data->readback_tick_count++",
            "screenshot_preview_exec(C, op)",
            "ARegion *region = CTX_wm_region(C);",
        ),
        "bounded identified modal",
    )
    require(
        "screenshot_preview_exec(C, op);\n          screenshot_preview_exit" not in modal,
        "interactive confirmation still exits before pending completion",
    )
    require(
        modal.count("return screenshot_preview_exec(C, op);") == 3,
        "timer/mouse/key confirmation result propagation differs",
    )

    cleanup = function_body(asset, "static void screenshot_preview_exit(", last=True)
    require_ordered(
        cleanup,
        (
            "WM_event_timer_remove(",
            "WM_window_pixels_read_async_cancel(data->readback);",
            "WM_draw_cb_exit(data->operator_window, data->draw_handle);",
            "MEM_delete(data);",
            "op->customdata = nullptr;",
        ),
        "terminal cleanup",
    )
    registration = function_body(asset, "static void ASSET_OT_screenshot_preview(")
    for needle in (
        "ot->invoke = screenshot_preview_invoke;",
        "ot->modal = screenshot_preview_modal;",
        "ot->exec = screenshot_preview_exec;",
        "ot->cancel = screenshot_preview_cancel;",
        '"p1"',
        '"p2"',
        '"force_square"',
    ):
        require(needle in registration, f"operator surface missing {needle!r}")

    return {
        "schema": 1,
        "verdict": "PASS",
        "contracts": {
            "owned_window_capture": True,
            "native_immediate_completion": True,
            "exact_crop_and_target": True,
            "bounded_identified_poll": True,
            "context_drift_rejected": True,
            "terminal_cleanup": True,
            "public_operator_surface_preserved": True,
            "live_hardware_receipt": False,
        },
        "converted_callers": ["asset_preview_window_capture"],
        "remaining_window_capture_callers": ["python_window_screenshot"],
        "mutation_controls": 18,
        "source_count": len(PATHS),
        "source_sha256": source_digest(sources),
    }


MUTATIONS: tuple[tuple[Path, str, str], ...] = (
    (ASSET, "WM_window_pixels_read_async(C, win);", "WM_window_pixels_read(C, win, nullptr);"),
    (ASSET, "rcti readback_crop = {};", "rcti readback_crop_lost = {};"),
    (ASSET, "data->readback_window = CTX_wm_window(C);", "data->readback_window = nullptr;"),
    (ASSET, "data->readback_screen = CTX_wm_screen(C);", "data->readback_screen = nullptr;"),
    (ASSET, "data->readback_main = CTX_data_main(C);", "data->readback_main = nullptr;"),
    (ASSET, "data->readback_id_type = asset_handle->get_id_type();", "data->readback_id_type.reset();"),
    (ASSET, "data->readback_asset_reference = asset_handle->make_weak_reference();", "data->readback_asset_reference.reset();"),
    (ASSET, "CTX_wm_window(C) != data->readback_window", "false"),
    (ASSET, "asset_handle->make_weak_reference() == *data->readback_asset_reference", "true"),
    (ASSET, "if (!data->interactive) {\n        WM_event_add_modal_handler(C, op);", "if (!data->interactive) {\n        /* modal owner omitted */"),
    (ASSET, "constexpr int max_tick_count = 240;", "constexpr int max_tick_count = -1;"),
    (ASSET, "event->customdata != data->readback_timer", "false"),
    (ASSET, "WM_window_pixels_read_async_consume(data->readback, dumprect_size)", "nullptr"),
    (ASSET, "take_screenshot_crop(dumprect, dumprect_size, data->readback_crop)", "nullptr"),
    (ASSET, "WM_window_pixels_read_async_cancel(data->readback);", "/* capture leaked */"),
    (ASSET, "ot->cancel = screenshot_preview_cancel;", "/* external cancel omitted */"),
    (ASSET, "data->drag_end = clamp_point_to_window(screen_space_cursor, win);\n          screenshot_area_transfer_to_rna(op, data);\n          return screenshot_preview_exec(C, op);", "data->drag_end = clamp_point_to_window(screen_space_cursor, win);\n          screenshot_area_transfer_to_rna(op, data);\n          return OPERATOR_FINISHED;"),
    (PYTHON_WM, "WM_window_pixels_read(C, win, dumprect_size)", "WM_window_pixels_read_async(C, win)"),
)


def selfcheck(sources: dict[Path, str]) -> None:
    validate(sources)
    for index, (path, old, new) in enumerate(MUTATIONS, start=1):
        require_once(sources[path], old, f"mutation {index}")
        mutated = dict(sources)
        mutated[path] = sources[path].replace(old, new, 1)
        try:
            validate(mutated)
        except VerificationError:
            continue
        raise VerificationError(f"mutation {index} did not fail closed")
    print(
        "M5_ASSET_PREVIEW_WINDOW_CAPTURE_SOURCE_SELFCHECK_PASS "
        f"mutations={len(MUTATIONS)} allocation=zero"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    require(args.selfcheck or args.output is not None, "request --selfcheck and/or --output")
    sources = read_sources(args.source_root)
    if args.selfcheck:
        selfcheck(sources)
    if args.output is not None:
        result = validate(sources)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            "M5_ASSET_PREVIEW_WINDOW_CAPTURE_SOURCE_PASS "
            f"files={result['source_count']} remaining=1 sha256={result['source_sha256']}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as error:
        print(f"M5_ASSET_PREVIEW_WINDOW_CAPTURE_SOURCE_FAIL {error}")
        raise SystemExit(1)
