#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind browser viewport-selection timeout to elapsed time, not timer delivery cadence."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VIEW3D_SELECT = ROOT / "upstream/source/blender/editors/space_view3d/view3d_select.cc"
PATCH = ROOT / "patches/0314-view3d-web-selection-wall-timeout.patch"
SERIES = ROOT / "patches/series"


def require(source: str, token: str, count: int = 1) -> None:
    if source.count(token) != count:
        raise ValueError(f"expected {count} occurrence(s) of {token!r}")


def modal_body(source: str) -> str:
    start = source.index("static wmOperatorStatus view3d_select_modal(")
    end = source.index("static void view3d_select_cancel(", start)
    return source[start:end]


def timed_out(elapsed_seconds: float) -> bool:
    return elapsed_seconds > 30.0


def validate(view3d_select: str, patch: str, series: str) -> None:
    modal = modal_body(view3d_select)
    require(view3d_select, '#include "BLI_time.h"')
    require(view3d_select, "double start_time = BLI_time_now_seconds();")
    require(modal, "constexpr double max_wait_seconds = 30.0;")
    require(
        modal,
        "if ((BLI_time_now_seconds() - data->start_time) > max_wait_seconds) {",
    )
    require(modal, "data->tick_count++;")
    require(modal, "web_view3d_select_modal_tick_count.store(")
    if "max_tick_count" in modal or "data->tick_count >" in modal:
        raise ValueError("selection timeout still depends on delivered timer-event count")

    if timed_out(2.4) or timed_out(29.999) or not timed_out(30.001):
        raise ValueError("wall-clock timeout behavior model differs")

    require(
        patch,
        "diff --git a/source/blender/editors/space_view3d/view3d_select.cc "
        "b/source/blender/editors/space_view3d/view3d_select.cc",
    )
    for token in (
        '+#include "BLI_time.h"',
        "+  double start_time = BLI_time_now_seconds();",
        "+  constexpr double max_wait_seconds = 30.0;",
        "+  if ((BLI_time_now_seconds() - data->start_time) > max_wait_seconds) {",
    ):
        require(patch, token)
    require(series, "0314-view3d-web-selection-wall-timeout.patch")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return source.replace(old, new, 1)


def self_check(view3d_select: str, patch: str, series: str) -> None:
    validate(view3d_select, patch, series)
    mutations = (
        ("source", "double start_time = BLI_time_now_seconds();", "double start_time = 0.0;"),
        ("source", "constexpr double max_wait_seconds = 30.0;", "constexpr int max_tick_count = 240;"),
        (
            "source",
            "if ((BLI_time_now_seconds() - data->start_time) > max_wait_seconds) {",
            "if (data->tick_count > 240) {",
        ),
        ("source", "data->tick_count++;", ""),
        ("patch", '+#include "BLI_time.h"', ""),
        (
            "series",
            "0314-view3d-web-selection-wall-timeout.patch",
            "0314-missing.patch",
        ),
    )
    rejected = 0
    for key, old, new in mutations:
        candidate_source = view3d_select
        candidate_patch = patch
        candidate_series = series
        if key == "source":
            candidate_source = replace_once(candidate_source, old, new)
        elif key == "patch":
            candidate_patch = replace_once(candidate_patch, old, new)
        else:
            candidate_series = replace_once(candidate_series, old, new)
        try:
            validate(candidate_source, candidate_patch, candidate_series)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0J_SELECT_WALL_TIMEOUT_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    view3d_select = VIEW3D_SELECT.read_text()
    patch = PATCH.read_text() if PATCH.exists() else ""
    series = SERIES.read_text()
    try:
        if args.self_check:
            self_check(view3d_select, patch, series)
        else:
            validate(view3d_select, patch, series)
    except (ValueError, OSError) as error:
        print(f"P0J_SELECT_WALL_TIMEOUT_SOURCE_FAIL {error}")
        return 1
    print("P0J_SELECT_WALL_TIMEOUT_SOURCE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
