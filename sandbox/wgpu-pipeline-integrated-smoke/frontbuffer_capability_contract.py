#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind GHOST-web capabilities to its asynchronous front-buffer readback contract."""

from __future__ import annotations

import argparse
from pathlib import Path


CAPABILITIES_MARKER = "GHOST_TCapabilityFlag GHOST_SystemWeb::getCapabilities() const"
WINDOW_SAMPLE_MARKER = "bool WM_window_pixels_read_sample("
EYEDROPPER_SAMPLE_MARKER = "bool eyedropper_color_sample_fl("
TEXTURE_READ_MARKER = "void WGPUTexture::read_sub("
FRONTBUFFER_CAPABILITY = "GHOST_kCapabilityGPUReadFrontBuffer"
WM_FRONTBUFFER_CAPABILITY = "WM_CAPABILITY_GPU_FRONT_BUFFER_READ"


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


def require_once(source: str, token: str, reason: str) -> None:
    count = source.count(token)
    if count != 1:
        raise ValueError(f"{reason}: expected one {token!r}, found {count}")


def validate(system: str, wm_draw: str, eyedropper: str, texture: str) -> None:
    capabilities = method(system, CAPABILITIES_MARKER)
    if "~(" not in capabilities:
        raise ValueError("GHOST-web capability exclusion mask is missing")
    exclusions = capabilities[capabilities.index("~(") :]
    require_once(
        exclusions,
        FRONTBUFFER_CAPABILITY,
        "browser backend still advertises synchronous front-buffer reads",
    )
    for implemented in ("GHOST_kCapabilityInputIME", "GHOST_kCapabilityCursorRGBA"):
        if implemented in exclusions:
            raise ValueError(f"implemented capability is incorrectly masked: {implemented}")

    window_sample = method(wm_draw, WINDOW_SAMPLE_MARKER)
    require_once(
        window_sample,
        WM_FRONTBUFFER_CAPABILITY,
        "stock window sample is no longer capability-routed",
    )
    for token in (
        "WM_window_pixels_read_sample_from_frontbuffer",
        "return true;",
        "return WM_window_pixels_read_sample_from_offscreen",
    ):
        require_once(window_sample, token, "stock window sample contract changed")

    eyedropper_sample = method(eyedropper, EYEDROPPER_SAMPLE_MARKER)
    try:
        window_area_sample = eyedropper_sample[
            eyedropper_sample.index("/* Other areas within a Blender window. */") :
            eyedropper_sample.index("/* Outside the Blender window")
        ]
    except ValueError as error:
        raise ValueError("eyedropper window-area branch is missing") from error
    for token in (
        f"(WM_capabilities_flag() & {WM_FRONTBUFFER_CAPABILITY}) != 0",
        "window_session->init(C, win)",
        "ReadbackState::Pending",
        "window_session->sample(event_xy_win, r_col)",
    ):
        require_once(window_area_sample, token, "eyedropper async fallback changed")

    texture_read = method(texture, TEXTURE_READ_MARKER)
    try:
        browser_read = texture_read[
            texture_read.index("#ifdef __EMSCRIPTEN__") : texture_read.index("#else")
        ]
    except ValueError as error:
        raise ValueError("texture read lacks a distinct Emscripten async arm") from error
    for token in (
        "std::vector<uint8_t> device_data(layout.device_data_size);",
        "readback::take_settled",
        "readback::kick_texture",
        "convert_device_to_host",
    ):
        require_once(browser_read, token, "browser synchronous readback model changed")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input is not unique: {old!r}")
    return source.replace(old, new, 1)


def mutate_method(source: str, marker: str, old: str, new: str) -> str:
    original = method(source, marker)
    changed = replace_once(original, old, new)
    return source.replace(original, changed, 1)


def selfcheck(system: str, wm_draw: str, eyedropper: str, texture: str) -> None:
    validate(system, wm_draw, eyedropper, texture)
    mutations = (
        (
            replace_once(system, FRONTBUFFER_CAPABILITY, "GHOST_kCapabilityCursorWarp"),
            wm_draw,
            eyedropper,
            texture,
        ),
        (
            system.replace(
                "GHOST_kCapabilityWindowDecorationStyles |",
                "GHOST_kCapabilityInputIME | GHOST_kCapabilityWindowDecorationStyles |",
                1,
            ),
            wm_draw,
            eyedropper,
            texture,
        ),
        (
            system,
            mutate_method(
                wm_draw,
                WINDOW_SAMPLE_MARKER,
                WM_FRONTBUFFER_CAPABILITY,
                "WM_CAPABILITY_CURSOR_WARP",
            ),
            eyedropper,
            texture,
        ),
        (
            system,
            wm_draw,
            mutate_method(
                eyedropper,
                EYEDROPPER_SAMPLE_MARKER,
                "window_session->init(C, win)",
                "window_session == nullptr",
            ),
            texture,
        ),
        (
            system,
            wm_draw,
            eyedropper,
            mutate_method(
                texture,
                TEXTURE_READ_MARKER,
                "readback::take_settled",
                "readback::state",
            ),
        ),
        (
            system,
            wm_draw,
            eyedropper,
            mutate_method(
                texture,
                TEXTURE_READ_MARKER,
                "std::vector<uint8_t> device_data(layout.device_data_size);\n"
                "    const readback::TextureRegion",
                "std::vector<uint8_t> device_data;\n"
                "    const readback::TextureRegion",
            ),
        ),
    )
    for index, mutation in enumerate(mutations, start=1):
        try:
            validate(*mutation)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("system_source", type=Path)
    parser.add_argument("wm_draw_source", type=Path)
    parser.add_argument("eyedropper_source", type=Path)
    parser.add_argument("texture_source", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    sources = tuple(
        path.read_text(encoding="utf-8")
        for path in (
            args.system_source,
            args.wm_draw_source,
            args.eyedropper_source,
            args.texture_source,
        )
    )
    if args.selfcheck:
        selfcheck(*sources)
    else:
        validate(*sources)
    print(
        "FRONTBUFFER_CAPABILITY_CONTRACT PASS cases=3 mutations=6 "
        "web-route=owned-async"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
