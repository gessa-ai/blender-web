#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Adversarial checks for the exact controller wasm-split keep set."""

from __future__ import annotations

import importlib.util
from pathlib import Path


FINALIZER = Path(__file__).resolve().parents[2] / "scripts/finalize-wasm-split.py"
SPEC = importlib.util.spec_from_file_location("finalize_wasm_split", FINALIZER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def expect_fail(label: str, layout: dict[str, object], needle: str) -> None:
    try:
        MODULE.controller_keep_functions(layout)
    except MODULE.WasmError as error:
        if needle not in str(error):
            raise AssertionError(f"{label}: {error!s} lacks {needle!r}") from error
    else:
        raise AssertionError(f"{label}: unexpectedly passed")


def main() -> None:
    imported = 7
    exports = {
        name: imported + ordinal
        for ordinal, name in enumerate(MODULE.SPLIT_CONTROLLER_EXPORTS)
    }
    layout = {
        "imported_function_count": imported,
        "defined_function_count": len(exports) + 3,
        "function_exports": exports,
    }
    result = MODULE.controller_keep_functions(layout)
    expected = [str(ordinal) for ordinal in range(len(exports))]
    if result != {
        "contract": "exact-controller-export-defined-function-keep-set-v1",
        "imported_function_count": imported,
        "defined_function_count": len(exports) + 3,
        "exports": {
            name: str(ordinal)
            for ordinal, name in enumerate(MODULE.SPLIT_CONTROLLER_EXPORTS)
        },
        "functions": expected,
        "function_count": len(expected),
    }:
        raise AssertionError(f"exact keep-set mismatch: {result}")

    duplicate_layout = dict(layout)
    duplicate_exports = dict(exports)
    duplicate_exports[MODULE.SPLIT_CONTROLLER_EXPORTS[-1]] = imported
    duplicate_layout["function_exports"] = duplicate_exports
    duplicate = MODULE.controller_keep_functions(duplicate_layout)
    if duplicate["functions"] != expected[:-1] or duplicate["function_count"] != len(expected) - 1:
        raise AssertionError(f"duplicate defined ordinal was not normalized: {duplicate}")

    missing_layout = dict(layout)
    missing_exports = dict(exports)
    del missing_exports[MODULE.SPLIT_CONTROLLER_EXPORTS[0]]
    missing_layout["function_exports"] = missing_exports
    expect_fail("missing export", missing_layout, "controller exports absent")

    imported_layout = dict(layout)
    imported_exports = dict(exports)
    imported_exports[MODULE.SPLIT_CONTROLLER_EXPORTS[0]] = imported - 1
    imported_layout["function_exports"] = imported_exports
    expect_fail("imported export", imported_layout, "not an original defined function")

    out_of_range_layout = dict(layout)
    out_of_range_exports = dict(exports)
    out_of_range_exports[MODULE.SPLIT_CONTROLLER_EXPORTS[-1]] = (
        imported + int(layout["defined_function_count"])
    )
    out_of_range_layout["function_exports"] = out_of_range_exports
    expect_fail("out-of-range export", out_of_range_layout, "not an original defined function")

    malformed_layout = dict(layout)
    malformed_layout["function_exports"] = []
    expect_fail("malformed exports", malformed_layout, "not a mapping")

    print(
        "controller keep-functions selfcheck: "
        f"positive=2 negative=4 functions={len(expected)} PASS"
    )


if __name__ == "__main__":
    main()
