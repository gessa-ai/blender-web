#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind sparse-orbit evidence to Blender's modal rotate retirement boundary."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRODUCER = ROOT / "sandbox/p0-interaction-stress/rapid_freeze_repro.mjs"
NAVIGATE = ROOT / "upstream/source/blender/editors/space_view3d/view3d_navigate.cc"
SERIES = ROOT / "patches/series"
PATCH = ROOT / "patches/0304-view3d-web-rotate-retirement-diagnostic.patch"


def require_once(source: str, token: str) -> None:
    if source.count(token) != 1:
        raise ValueError(f"expected exactly one {token!r}")


def replace_once(source: str, old: str, new: str) -> str:
    require_once(source, old)
    return source.replace(old, new, 1)


def validate(producer: str, navigate: str, series: str, patch: str) -> None:
    for token in (
        'invokes: read("_bw_view3d_rotate_invoke_count")',
        'confirms: read("_bw_view3d_rotate_confirm_count")',
        'cancels: read("_bw_view3d_rotate_cancel_count")',
        'terminals: read("_bw_view3d_rotate_terminal_count")',
        'active: read("_bw_view3d_rotate_active_count")',
        "view3dRotate: {...current.view3dRotate},",
        "const view3dRotateRetired = (current, baseline, expected) =>",
        "current.view3dRotate.invokes >= baseline.view3dRotate.invokes + expected",
        "current.view3dRotate.confirms >= baseline.view3dRotate.confirms + expected",
        "current.view3dRotate.terminals >= baseline.view3dRotate.terminals + expected",
        "current.view3dRotate.active === baseline.view3dRotate.active",
        "view3dRotateRetired(current, rotateBaseline, expectedRotates)",
        '"action-drain",\n      orbitBeforeClick.sha256,\n      orbitBeforeClick,\n'
        "      isolatedOrbitBaseline,\n      2,",
    ):
        require_once(producer, token)
    if producer.index("view3dRotateRetired(current, rotateBaseline, expectedRotates)") > producer.index(
        "return {...current"
    ):
        raise ValueError("rotate retirement is checked after accepting a drained sample")

    for token in (
        "std::atomic<uint64_t> web_view3d_rotate_invoke_count{0};",
        "std::atomic<uint64_t> web_view3d_rotate_confirm_count{0};",
        "std::atomic<uint64_t> web_view3d_rotate_cancel_count{0};",
        "std::atomic<uint64_t> web_view3d_rotate_terminal_count{0};",
        "std::atomic<uint64_t> web_view3d_rotate_active_count{0};",
        "web_view3d_rotate_confirm_count.fetch_add(1u, std::memory_order_relaxed);",
        "web_view3d_rotate_terminal_count.fetch_add(1u, std::memory_order_release);",
        "web_view3d_rotate_active_count.fetch_sub(1u, std::memory_order_release);",
        'extern "C" EMSCRIPTEN_KEEPALIVE double bw_view3d_rotate_invoke_count(void)',
        'extern "C" EMSCRIPTEN_KEEPALIVE double bw_view3d_rotate_confirm_count(void)',
        'extern "C" EMSCRIPTEN_KEEPALIVE double bw_view3d_rotate_cancel_count(void)',
        'extern "C" EMSCRIPTEN_KEEPALIVE double bw_view3d_rotate_terminal_count(void)',
        'extern "C" EMSCRIPTEN_KEEPALIVE double bw_view3d_rotate_active_count(void)',
        "web_view3d_rotate_invoke_count.fetch_add(1u, std::memory_order_relaxed);",
        "web_view3d_rotate_active_count.fetch_add(1u, std::memory_order_release);",
        "web_view3d_rotate_note_terminal(event_code);",
        "web_view3d_rotate_note_terminal(VIEW_PASS);",
    ):
        require_once(navigate, token)
    if navigate.count("web_view3d_rotate_note_terminal(VIEW_CANCEL);") != 2:
        raise ValueError("rotate cancellation must cover depth and external cancellation")
    if series.count(PATCH.name) != 1:
        raise ValueError("numbered rotate-retirement patch is not active exactly once")
    path = "source/blender/editors/space_view3d/view3d_navigate.cc"
    if patch.count(f"diff --git a/{path} b/{path}") != 1:
        raise ValueError("numbered patch does not bind the navigation source")
    for token in (
        "bw_view3d_rotate_invoke_count",
        "bw_view3d_rotate_confirm_count",
        "bw_view3d_rotate_terminal_count",
        "web_view3d_rotate_note_terminal(event_code)",
    ):
        if token not in patch:
            raise ValueError(f"numbered patch lost {token!r}")


def self_check(producer: str, navigate: str, series: str, patch: str) -> None:
    validate(producer, navigate, series, patch)
    mutations = (
        (replace_once(producer, "view3dRotateRetired(current, rotateBaseline, expectedRotates)", "true"),
         navigate, series, patch),
        (replace_once(producer,
                      "current.view3dRotate.confirms >= baseline.view3dRotate.confirms + expected",
                      "true"), navigate, series, patch),
        (replace_once(producer,
                      "current.view3dRotate.active === baseline.view3dRotate.active",
                      "true"), navigate, series, patch),
        (replace_once(producer,
                      "      isolatedOrbitBaseline,\n      2,",
                      "      orbitBeforeClick,\n      1,"), navigate, series, patch),
        (producer, replace_once(
            navigate,
            "web_view3d_rotate_terminal_count.fetch_add(1u, std::memory_order_release);",
            ""), series, patch),
        (producer, replace_once(
            navigate,
            "web_view3d_rotate_active_count.fetch_sub(1u, std::memory_order_release);",
            ""), series, patch),
        (producer, replace_once(
            navigate,
            "web_view3d_rotate_note_terminal(event_code);",
            ""), series, patch),
        (producer, navigate, series.replace(PATCH.name, "0304-missing.patch", 1), patch),
        (producer, navigate, series, patch.replace(
            "bw_view3d_rotate_confirm_count", "bw_view3d_rotate_lost_count", 1)),
    )
    rejected = 0
    for mutation in mutations:
        try:
            validate(*mutation)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0J_VIEW3D_ROTATE_RETIREMENT_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    producer = PRODUCER.read_text(encoding="utf-8")
    navigate = NAVIGATE.read_text(encoding="utf-8")
    series = SERIES.read_text(encoding="utf-8")
    patch = PATCH.read_text(encoding="utf-8") if PATCH.exists() else ""
    if "--self-check" in __import__("sys").argv[1:]:
        self_check(producer, navigate, series, patch)
    else:
        validate(producer, navigate, series, patch)
        print("P0J_VIEW3D_ROTATE_RETIREMENT_SOURCE_PASS counters=invoke,confirm,cancel,terminal,active")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"P0J_VIEW3D_ROTATE_RETIREMENT_SOURCE_FAIL {error}")
        raise SystemExit(1)
