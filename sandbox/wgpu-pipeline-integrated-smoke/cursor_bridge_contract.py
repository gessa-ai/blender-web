#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind Blender's standard/custom cursor contract to the main-thread canvas bridge."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


EXPECTED_CURSOR_NAMES = (
    "Default",
    "RightArrow",
    "LeftArrow",
    "Info",
    "Destroy",
    "Help",
    "Wait",
    "Text",
    "Crosshair",
    "CrosshairA",
    "CrosshairB",
    "CrosshairC",
    "Pencil",
    "UpArrow",
    "DownArrow",
    "VerticalSplit",
    "HorizontalSplit",
    "Eraser",
    "Knife",
    "Eyedropper",
    "ZoomIn",
    "ZoomOut",
    "Move",
    "NSEWScroll",
    "NSScroll",
    "EWScroll",
    "Stop",
    "UpDown",
    "LeftRight",
    "TopSide",
    "BottomSide",
    "LeftSide",
    "RightSide",
    "TopLeftCorner",
    "TopRightCorner",
    "BottomRightCorner",
    "BottomLeftCorner",
    "Copy",
    "LeftHandle",
    "RightHandle",
    "BothHandles",
    "HandOpen",
    "HandClosed",
    "HandPoint",
    "Blade",
    "Slip",
    "Custom",
)


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


def cursor_names(types_source: str) -> tuple[str, ...]:
    start = types_source.find("enum GHOST_TStandardCursor")
    end = types_source.find("enum GHOST_TKey", start)
    if start < 0 or end < 0:
        raise ValueError("standard cursor enum is missing")
    block = types_source[start:end]
    return tuple(
        re.findall(r"^\s*GHOST_kStandardCursor([A-Za-z0-9]+)(?:\s*=\s*0)?\s*,", block, re.M)
    )


def require_once(source: str, token: str, label: str) -> None:
    count = source.count(token)
    if count != 1:
        raise ValueError(f"expected one {label}, found {count}")


def validate(
    window_source: str,
    window_header: str,
    system_source: str,
    shell_source: str,
    types_source: str,
) -> None:
    names = cursor_names(types_source)
    if names != EXPECTED_CURSOR_NAMES:
        raise ValueError("GHOST standard cursor order differs from the browser mapping contract")

    for declaration in (
        "GHOST_TSuccess hasCursorShape(GHOST_TStandardCursor shape) override;",
        "GHOST_TSuccess setWindowCursorShape(GHOST_TStandardCursor shape) override;",
        "GHOST_TSuccess setWindowCustomCursorShape(const uint8_t *bitmap,",
    ):
        require_once(window_header, declaration, declaration)

    has_shape = method(window_source, "GHOST_TSuccess GHOST_WindowWeb::hasCursorShape(")
    if "GHOST_kStandardCursorFirstCursor" not in has_shape:
        raise ValueError("standard cursor lower bound is not checked")
    if "GHOST_kStandardCursorCustom" not in has_shape:
        raise ValueError("custom cursor sentinel is not excluded")
    if "GHOST_kSuccess" not in has_shape or "GHOST_kFailure" not in has_shape:
        raise ValueError("cursor support query does not report both outcomes")

    set_shape = method(window_source, "GHOST_TSuccess GHOST_WindowWeb::setWindowCursorShape(")
    if "hasCursorShape(shape)" not in set_shape:
        raise ValueError("cursor setter bypasses its advertised support range")
    if "g_cursor_shape.store(int32_t(shape), std::memory_order_relaxed);" not in set_shape:
        raise ValueError("cursor shape is not published to shared wasm memory")
    if "g_cursor_generation.fetch_add(1, std::memory_order_release);" not in set_shape:
        raise ValueError("cursor shape publication has no release generation")

    custom = method(window_source, "GHOST_TSuccess GHOST_WindowWeb::setWindowCustomCursorShape(")
    for token in (
        "kWebCustomCursorMaxDimension = 128",
        "MAIN_THREAD_EM_ASM_INT(",
        "bridge.installCustomCursor(",
        "HEAPU8, $0, $1, $2, $3, $4, $5",
        "g_cursor_shape.store(int32_t(GHOST_kStandardCursorCustom), std::memory_order_relaxed);",
        "g_cursor_generation.fetch_add(1, std::memory_order_release);",
    ):
        source = window_source if token == "kWebCustomCursorMaxDimension = 128" else custom
        if token not in source:
            raise ValueError(f"custom cursor publication is missing: {token}")
    if custom.count("return GHOST_kFailure;") != 2 or custom.count("return GHOST_kSuccess;") != 1:
        raise ValueError("custom cursor must fail both validation/bridge errors and publish one success")
    if window_source.count("g_cursor_generation.fetch_add(1, std::memory_order_release);") != 3:
        raise ValueError("standard/custom/visibility cursor publications must each release a generation")

    visibility = method(window_source, "GHOST_TSuccess GHOST_WindowWeb::setWindowCursorVisibility(")
    if "g_cursor_visible.store(visible ? 1 : 0, std::memory_order_relaxed);" not in visibility:
        raise ValueError("cursor visibility is not published to shared wasm memory")
    if "g_cursor_generation.fetch_add(1, std::memory_order_release);" not in visibility:
        raise ValueError("cursor visibility publication has no release generation")
    if "EM_ASM" in visibility:
        raise ValueError("worker cursor visibility still attempts direct DOM access")

    capabilities = method(system_source, "GHOST_TCapabilityFlag GHOST_SystemWeb::getCapabilities(")
    if "GHOST_kCapabilityCursorRGBA" in capabilities:
        raise ValueError("implemented RGBA cursor capability is still masked")
    if "GHOST_kCapabilityCursorGenerator" not in capabilities:
        raise ValueError("unimplemented cursor generator capability is not masked")

    export_contract = {
        "bw_shell_cursor_generation": (
            "uint32_t", "g_cursor_generation.load(std::memory_order_acquire)"
        ),
        "bw_shell_cursor_shape": (
            "int32_t", "g_cursor_shape.load(std::memory_order_relaxed)"
        ),
        "bw_shell_cursor_visible": (
            "int32_t", "g_cursor_visible.load(std::memory_order_relaxed)"
        ),
    }
    for export_name, (return_type, load) in export_contract.items():
        body = method(
            window_source,
            f"extern \"C\" EMSCRIPTEN_KEEPALIVE {return_type} {export_name}(",
        )
        if load not in body:
            raise ValueError(f"{export_name} does not read the shared cursor state")

    for token in (
        'Object.defineProperty(window, "__bwCursorBridge"',
        'typeof mod._bw_shell_cursor_generation !== "function"',
        'typeof mod._bw_shell_cursor_shape !== "function"',
        'typeof mod._bw_shell_cursor_visible !== "function"',
        "Number(mod._bw_shell_cursor_generation())",
        "Number(mod._bw_shell_cursor_shape())",
        "Number(mod._bw_shell_cursor_visible())",
        "const CSS_CURSOR_BY_GHOST_SHAPE = Object.freeze([",
        "const CUSTOM_CURSOR_SHAPE = CSS_CURSOR_BY_GHOST_SHAPE.length;",
        "const CUSTOM_CURSOR_MAX_DIMENSION = 128;",
        "function installCustomCursor(heap, bitmapPointer, maskPointer, width, height, hotX, hotY)",
        "const bit = 1 << (x & 7);",
        "context.putImageData(image, 0, 0);",
        "customCursorCss = `url(${JSON.stringify(dataUrl)}) ${hotX} ${hotY}, default`;",
        "schema: 2,",
        "installCustomCursor,",
        "mod.canvas && mod.canvas.style ? mod.canvas :",
    ):
        require_once(shell_source, token, token)
    if shell_source.count("window.requestAnimationFrame(frame)") != 2:
        raise ValueError("cursor bridge must seed and continue one animation-frame poll")


def selfcheck(
    window_source: str,
    window_header: str,
    system_source: str,
    shell_source: str,
    types_source: str,
) -> None:
    validate(window_source, window_header, system_source, shell_source, types_source)
    mutations = (
        (
            window_source.replace(
                "g_cursor_shape.store(int32_t(shape), std::memory_order_relaxed);",
                "(void)shape;",
                1,
            ),
            window_header,
            system_source,
            shell_source,
            types_source,
        ),
        (
            window_source.replace(
                "g_cursor_visible.store(visible ? 1 : 0, std::memory_order_relaxed);",
                "(void)visible;",
                1,
            ),
            window_header,
            system_source,
            shell_source,
            types_source,
        ),
        (
            window_source.replace("bridge.installCustomCursor(", "bridge.ignoreCustomCursor(", 1),
            window_header,
            system_source,
            shell_source,
            types_source,
        ),
        (
            window_source.replace(
                "g_cursor_shape.store(int32_t(GHOST_kStandardCursorCustom), std::memory_order_relaxed);",
                "(void)bitmap;",
                1,
            ),
            window_header,
            system_source,
            shell_source,
            types_source,
        ),
        (
            window_source,
            window_header.replace(
                "GHOST_TSuccess setWindowCustomCursorShape(const uint8_t *bitmap,",
                "GHOST_TSuccess ignoreWindowCustomCursorShape(const uint8_t *bitmap,",
                1,
            ),
            system_source,
            shell_source,
            types_source,
        ),
        (
            window_source,
            window_header,
            system_source.replace(
                "GHOST_kCapabilityKeyboardHyperKey | GHOST_kCapabilityCursorGenerator |",
                "GHOST_kCapabilityKeyboardHyperKey | GHOST_kCapabilityCursorRGBA | "
                "GHOST_kCapabilityCursorGenerator |",
                1,
            ),
            shell_source,
            types_source,
        ),
        (
            window_source,
            window_header,
            system_source,
            shell_source.replace("_bw_shell_cursor_generation", "_bw_shell_cursor_epoch", 1),
            types_source,
        ),
        (
            window_source,
            window_header,
            system_source,
            shell_source.replace("function installCustomCursor(", "function ignoreCustomCursor(", 1),
            types_source,
        ),
        (
            window_source,
            window_header,
            system_source,
            shell_source.replace(
                "const CUSTOM_CURSOR_MAX_DIMENSION = 128;",
                "const CUSTOM_CURSOR_MAX_DIMENSION = 129;",
                1,
            ),
            types_source,
        ),
        (
            window_source,
            window_header,
            system_source,
            shell_source.replace(
                "const bit = 1 << (x & 7);",
                "const bit = 1 << (7 - (x & 7));",
                1,
            ),
            types_source,
        ),
        (
            window_source.replace(
                "const int installed = MAIN_THREAD_EM_ASM_INT(",
                "const int installed = EM_ASM_INT(",
                1,
            ),
            window_header,
            system_source,
            shell_source,
            types_source,
        ),
        (
            window_source,
            window_header,
            system_source,
            shell_source,
            types_source.replace("  GHOST_kStandardCursorSlip,", "", 1),
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
    parser.add_argument("window_source", type=Path)
    parser.add_argument("window_header", type=Path)
    parser.add_argument("system_source", type=Path)
    parser.add_argument("shell_source", type=Path)
    parser.add_argument("types_source", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    sources = tuple(path.read_text(encoding="utf-8") for path in (
        args.window_source,
        args.window_header,
        args.system_source,
        args.shell_source,
        args.types_source,
    ))
    if args.selfcheck:
        selfcheck(*sources)
    else:
        validate(*sources)
    print("CURSOR_BRIDGE_SOURCE_CONTRACT PASS standard=46 custom=rgba,xbm max=128 mutations=12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
