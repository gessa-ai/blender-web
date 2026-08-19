#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Adversarial tests for the finalizer's effective Emscripten stack-policy parser."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
FINALIZER = REPO / "scripts/finalize-wasm-split.py"
SPEC = importlib.util.spec_from_file_location("bw_finalize_stack_policy", FINALIZER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def rejected(command: str, label: str) -> None:
    try:
        MODULE.verify_link_stack_policy(command)
    except MODULE.WasmError:
        return
    raise AssertionError(f"{label} was accepted")


def main() -> int:
    # The real link has an earlier 8 MiB base STACK_SIZE; the later WebGPU value wins.
    positive = MODULE.verify_link_stack_policy(
        "em++ a.o -sSTACK_SIZE=8388608 -sDEFAULT_PTHREAD_STACK_SIZE=8388608 "
        "-sSTACK_SIZE=33554432 -o blender_browser.js"
    )
    assert positive == {
        "contract": "proxy-main-32m-ordinary-pthread-8m-v1",
        "stack_size_occurrences": [8388608, 33554432],
        "default_pthread_stack_size_occurrences": [8388608],
        "effective_stack_size": 33554432,
        "effective_default_pthread_stack_size": 8388608,
    }

    # Exercise the separate `-s SETTING=value` spelling as well.
    separate = MODULE.verify_link_stack_policy(
        "em++ a.o -s STACK_SIZE=33554432 -s DEFAULT_PTHREAD_STACK_SIZE=8388608"
    )
    assert separate["effective_stack_size"] == 33554432
    assert separate["effective_default_pthread_stack_size"] == 8388608

    rejected(
        "em++ a.o -sSTACK_SIZE=8388608 -sDEFAULT_PTHREAD_STACK_SIZE=33554432",
        "swapped policy",
    )
    rejected("em++ a.o -sSTACK_SIZE=33554432", "missing pthread default")
    rejected(
        "em++ a.o -sSTACK_SIZE=33554432 -sDEFAULT_PTHREAD_STACK_SIZE=8388608 "
        "-sSTACK_SIZE=8388608",
        "late main-stack override",
    )
    rejected(
        "em++ a.o -sSTACK_SIZE=33554432 -sDEFAULT_PTHREAD_STACK_SIZE=8388608 "
        "-sDEFAULT_PTHREAD_STACK_SIZE=33554432",
        "late pthread-default override",
    )
    rejected(
        "em++ a.o -sSTACK_SIZE=32MB -sDEFAULT_PTHREAD_STACK_SIZE=8388608",
        "non-byte main value",
    )
    print("BW_LINK_STACK_POLICY_TEST PASS positive=2 negatives=5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
