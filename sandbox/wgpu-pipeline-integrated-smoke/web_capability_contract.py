#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind browser-only GHOST capability exclusions to the implemented web surface."""

from __future__ import annotations

import argparse
from pathlib import Path


CAPABILITIES_MARKER = "GHOST_TCapabilityFlag GHOST_SystemWeb::getCapabilities() const"
WHEEL_MARKER = "void on_wheel("
WINDOW_BOUNDS_MARKER = "void GHOST_WindowWeb::getWindowBounds("

TRACKPAD_DIRECTION = "GHOST_kCapabilityTrackpadPhysicalDirection"
SERVER_DECORATION = "GHOST_kCapabilityWindowDecorationServerSide"
IMPLEMENTED = ("GHOST_kCapabilityInputIME", "GHOST_kCapabilityCursorRGBA")


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


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input is not unique: {old!r}")
    return source.replace(old, new, 1)


def replace_first_of_two(source: str, old: str, new: str) -> str:
    if source.count(old) != 2:
        raise ValueError(f"mutation input must occur twice: {old!r}")
    return source.replace(old, new, 1)


def validate(system: str, event_bridge: str, window: str) -> None:
    capabilities = method(system, CAPABILITIES_MARKER)
    if "~(" not in capabilities:
        raise ValueError("GHOST-web capability exclusion mask is missing")
    exclusions = capabilities[capabilities.index("~(") :]
    require_once(
        exclusions,
        TRACKPAD_DIRECTION,
        "browser backend falsely promises physical trackpad direction",
    )
    require_once(
        exclusions,
        SERVER_DECORATION,
        "browser backend falsely promises server-side window decorations",
    )
    for implemented in IMPLEMENTED:
        if implemented in exclusions:
            raise ValueError(f"implemented capability is incorrectly masked: {implemented}")

    wheel = method(event_bridge, WHEEL_MARKER)
    if "GHOST_EventTrackpad" in wheel:
        raise ValueError("DOM wheel path unexpectedly claims raw trackpad metadata")
    if wheel.count("GHOST_EventWheel") != 2:
        raise ValueError("DOM wheel path must emit exactly two discrete wheel-axis arms")
    for token in ("e.deltaY > 0.0 ? -1 : 1", "e.deltaX > 0.0 ? 1 : -1"):
        require_once(wheel, token, "DOM wheel direction contract changed")

    bounds = method(window, WINDOW_BOUNDS_MARKER)
    require_once(
        bounds,
        "getClientBounds(bounds);",
        "canvas window unexpectedly gained an independent server frame",
    )


def selfcheck(system: str, event_bridge: str, window: str) -> None:
    validate(system, event_bridge, window)
    mutations = (
        (replace_once(system, TRACKPAD_DIRECTION, "GHOST_kCapabilityCursorWarp"), event_bridge, window),
        (replace_once(system, SERVER_DECORATION, "GHOST_kCapabilityCursorWarp"), event_bridge, window),
        (
            replace_once(
                system,
                "GHOST_kCapabilityWindowDecorationStyles |",
                "GHOST_kCapabilityInputIME | GHOST_kCapabilityWindowDecorationStyles |",
            ),
            event_bridge,
            window,
        ),
        (
            replace_once(
                system,
                "GHOST_kCapabilityKeyboardHyperKey | GHOST_kCapabilityCursorGenerator |",
                "GHOST_kCapabilityKeyboardHyperKey | GHOST_kCapabilityCursorRGBA | "
                "GHOST_kCapabilityCursorGenerator |",
            ),
            event_bridge,
            window,
        ),
        (
            system,
            replace_first_of_two(event_bridge, "GHOST_EventWheel>(", "GHOST_EventTrackpad>("),
            window,
        ),
        (
            system,
            event_bridge,
            replace_once(window, "getClientBounds(bounds);", "bounds = GHOST_Rect();"),
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
    parser.add_argument("event_bridge_source", type=Path)
    parser.add_argument("window_source", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    sources = tuple(
        path.read_text(encoding="utf-8")
        for path in (args.system_source, args.event_bridge_source, args.window_source)
    )
    if args.selfcheck:
        selfcheck(*sources)
    else:
        validate(*sources)
    print(
        "WEB_CAPABILITY_CONTRACT PASS "
        "unsupported=trackpad-physical-direction,server-window-decoration "
        "implemented=ime,cursor-rgba mutations=6"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
