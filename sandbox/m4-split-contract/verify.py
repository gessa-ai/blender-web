#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify the stock Emscripten split-link artifact boundary used by M4."""

from __future__ import annotations

from pathlib import Path


HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"


def require(name: str, present: bool) -> None:
    path = BUILD / name
    if path.is_file() != present:
        state = "present" if path.is_file() else "missing"
        expected = "present" if present else "missing"
        raise SystemExit(f"SPLIT_CONTRACT_FAIL {name}: {state}, expected {expected}")


def main() -> None:
    for name in ("off.js", "off.wasm", "capture.js", "capture.wasm", "capture.wasm.orig"):
        require(name, True)
    for name in ("off.wasm.orig", "off.deferred.wasm", "capture.deferred.wasm"):
        require(name, False)
    print(
        "SPLIT_CONTRACT_PASS off=js+wasm split-module=js+wasm+orig "
        "deferred=apply-finalizer-only"
    )


if __name__ == "__main__":
    main()
