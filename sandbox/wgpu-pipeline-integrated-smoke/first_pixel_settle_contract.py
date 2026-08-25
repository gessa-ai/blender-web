#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind first-pixel redraw settling to each published web-window epoch."""

from __future__ import annotations

import argparse
from pathlib import Path


PROCESS_MARKER = "bool GHOST_SystemWeb::processEvents(bool /*waitForEvent*/)"
CREATE_MARKER = "GHOST_IWindow *GHOST_SystemWeb::createWindow("
HELPER_MARKER = "inline bool first_pixel_settle_tick("


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


def validate(
    display_header: str,
    system_header: str,
    system_source: str,
    wm_window_source: str,
) -> None:
    helper = method(display_header, HELPER_MARKER)
    for token in (
        "FIRST_PIXEL_SETTLE_PRESENTS = 2u",
        "FIRST_PIXEL_SETTLE_TICKS = 180u",
        "FIRST_PIXEL_SETTLE_INTERVAL = 12u",
    ):
        require_once(display_header, token, "settle constants")
    for token in (
        "present_count - present_baseline",
        ">= FIRST_PIXEL_SETTLE_PRESENTS",
        "heartbeat = FIRST_PIXEL_SETTLE_TICKS;",
        "if (heartbeat >= FIRST_PIXEL_SETTLE_TICKS)",
        "(heartbeat % FIRST_PIXEL_SETTLE_INTERVAL) == 0u",
        "heartbeat++;",
        "return request_update;",
    ):
        require_once(helper, token, "settle helper")

    require_once(
        system_header,
        "uint64_t redraw_present_baseline_ = 0;",
        "per-window settle state",
    )

    process = method(system_source, PROCESS_MARKER)
    for token in (
        "ghost_web::first_pixel_settle_tick(",
        "ghost_web::present_count(), redraw_present_baseline_, redraw_heartbeat_",
        "GHOST_kEventWindowUpdate",
    ):
        require_once(process, token, "processEvents settle wiring")
    if "GHOST_kEventWindowActivate" in process:
        raise ValueError("first-pixel settling still injects synthetic activation")
    if "boot_presents < 2u" in process or "boot_presents >= 2u" in process:
        raise ValueError("first-pixel settling still uses the process-global absolute count")

    creation = method(system_source, CREATE_MARKER)
    baseline = "redraw_present_baseline_ = ghost_web::present_count();"
    heartbeat = "redraw_heartbeat_ = 0;"
    require_once(creation, baseline, "window publication")
    require_once(creation, heartbeat, "window publication")
    if creation.index(baseline) > creation.index(heartbeat):
        raise ValueError("window publication resets ticks before capturing its present epoch")

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
) -> None:
    validate(display_header, system_header, system_source, wm_window_source)
    mutations = (
        (replace_once(display_header, "FIRST_PIXEL_SETTLE_PRESENTS = 2u", "FIRST_PIXEL_SETTLE_PRESENTS = 1u"), system_header, system_source, wm_window_source),
        (replace_once(display_header, "FIRST_PIXEL_SETTLE_TICKS = 180u", "FIRST_PIXEL_SETTLE_TICKS = 0u"), system_header, system_source, wm_window_source),
        (replace_once(display_header, "FIRST_PIXEL_SETTLE_INTERVAL = 12u", "FIRST_PIXEL_SETTLE_INTERVAL = 1u"), system_header, system_source, wm_window_source),
        (replace_once(display_header, "present_count - present_baseline", "present_count"), system_header, system_source, wm_window_source),
        (display_header, replace_once(system_header, "uint64_t redraw_present_baseline_ = 0;", ""), system_source, wm_window_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "ghost_web::first_pixel_settle_tick(", "ghost_web::first_pixel_settle_disabled("), wm_window_source),
        (display_header, system_header, mutate_method(system_source, PROCESS_MARKER, "GHOST_kEventWindowUpdate", "GHOST_kEventWindowActivate"), wm_window_source),
        (display_header, system_header, mutate_method(system_source, CREATE_MARKER, "redraw_present_baseline_ = ghost_web::present_count();", ""), wm_window_source),
        (display_header, system_header, mutate_method(system_source, CREATE_MARKER, "redraw_present_baseline_ = ghost_web::present_count();\n          redraw_heartbeat_ = 0;", "redraw_heartbeat_ = 0;\n          redraw_present_baseline_ = ghost_web::present_count();"), wm_window_source),
        (display_header, system_header, system_source, mutate_window_update(wm_window_source, "WM_event_add_notifier_ex(wm, win, NC_SCREEN | NA_EDITED, nullptr);", "")),
        (display_header, system_header, system_source, mutate_window_update(wm_window_source, "#ifdef __EMSCRIPTEN__\n      /* A web surface", "#if 1\n      /* A web surface")),
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
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    inputs = tuple(
        path.read_text(encoding="utf-8")
        for path in (
            args.display_header,
            args.system_header,
            args.system_source,
            args.wm_window_source,
        )
    )
    if args.selfcheck:
        selfcheck(*inputs)
    else:
        validate(*inputs)
    print("FIRST_PIXEL_SETTLE_CONTRACT PASS cases=4 mutations=11 epoch=per-window")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
