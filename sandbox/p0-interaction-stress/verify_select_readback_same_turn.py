#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Require same-turn browser mapping with joined selection-readback validation."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_common.hh"
READBACK = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_readback.cc"
READBACK_HEADER = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_readback.hh"
TEST = ROOT / "sandbox/wgpu-buffer-integrated-smoke/integrated_buffer_test.cc"
PATCH = ROOT / "patches/0312-gpu-webgpu-select-readback-same-turn-map.patch"
SERIES = ROOT / "patches/series"


def require(source: str, token: str, count: int = 1) -> None:
    if source.count(token) != count:
        raise ValueError(f"expected {count} occurrence(s) of {token!r}")


def require_present(source: str, token: str) -> None:
    if token not in source:
        raise ValueError(f"expected {token!r}")


def braced_body(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated body for {marker!r}")


def validate(sources: dict[str, str]) -> None:
    common = sources["common"]
    readback = sources["readback"]
    header = sources["header"]
    test = sources["test"]
    patch = sources["patch"]
    series = sources["series"]

    helper = braced_body(common, "inline void command_encode_submit_scoped_with_submit(")
    for token in (
        "const auto submission = std::make_shared<SubmittedT>",
        "queue.Submit(1, &command_buffer);\n    (*submission)(true);",
        "queue.Submit(1, &command_buffer);\n              (*submission)(true);",
        "(*submission)(false);",
    ):
        require_present(helper, token)
    wrapper = braced_body(common, "inline void command_encode_submit_scoped(")
    require_present(wrapper, "command_encode_submit_scoped_with_submit(")
    require_present(wrapper, "[](const bool /*submitted*/) {}")

    join = braced_body(readback, "struct PendingCommandMapState")
    for token in (
        "bool submission_known = false;",
        "bool submitted = false;",
        "bool command_done = false;",
        "bool command_valid = false;",
        "bool map_done = false;",
        "bool finalized = false;",
    ):
        require_present(join, token)

    submitted = braced_body(readback, "void pending_command_map_submitted(")
    for token in (
        "state->submission_known = true;",
        "state->submitted = submitted;",
        "pending->staging.MapAsync(",
        "wgpu::CallbackMode::AllowSpontaneous",
        "state->map_done = true;",
        "pending_command_map_maybe_complete(state);",
    ):
        require_present(submitted, token)
    validated = braced_body(readback, "void pending_command_map_validated(")
    require_present(validated, "state->command_valid = valid;")
    require_present(validated, "state->command_done = true;")
    require_present(validated, "pending_command_map_maybe_complete(state);")

    maybe_complete = braced_body(readback, "void pending_command_map_maybe_complete(")
    require_present(
        maybe_complete,
        "!state->submission_known || !state->command_done ||\n"
        "        (state->submitted && !state->map_done)",
    )
    require_present(
        maybe_complete,
        "command_valid ? TicketError::None : TicketError::CommandEncodingFailed",
    )

    kick = braced_body(readback, "Ticket kick_buffer(")
    ordered = (
        "const auto command_map = std::make_shared<PendingCommandMapState>(pending);",
        "webgpu::command_encode_submit_scoped_with_submit(",
        "encoder.CopyBufferToBuffer(handle, offset, staging, 0, copy);",
        "pending_command_map_submitted(command_map, submitted);",
        "pending_command_map_validated(command_map, valid);",
    )
    positions = [kick.find(token) for token in ordered]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise ValueError("buffer readback submit/map/validation ordering changed")
    if "staging.MapAsync(" in kick:
        raise ValueError("buffer MapAsync regressed behind the terminal validation callback")

    for token in (
        "the map is registered in the same calling turn",
        "mapped bytes remain private until both the map and the",
        "command's asynchronous validation scopes settle successfully",
    ):
        require_present(header, token)

    for token in (
        "command_encode_submit_scoped_with_submit(",
        "browser deferred map start is same-turn",
        "native deferred map waits for submission",
        "map_policy=after-submit/browser-same-turn",
    ):
        require_present(test, token)

    for path in (
        "source/blender/gpu/webgpu/wgpu_common.hh",
        "source/blender/gpu/webgpu/wgpu_readback.cc",
        "source/blender/gpu/webgpu/wgpu_readback.hh",
        "source/blender/gpu/webgpu/wgpu_storage_buffer.cc",
        "source/blender/gpu/webgpu/wgpu_texture.cc",
    ):
        require_present(patch, f"diff --git a/{path} b/{path}")
    require(series, "0312-gpu-webgpu-select-readback-same-turn-map.patch")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return source.replace(old, new, 1)


def self_check(sources: dict[str, str]) -> None:
    validate(sources)
    mutations = (
        (
            "common",
            "queue.Submit(1, &command_buffer);\n    (*submission)(true);",
            "(*submission)(true);\n    queue.Submit(1, &command_buffer);",
        ),
        (
            "common",
            "[](const bool /*submitted*/) {}",
            "[](const bool /*submitted*/) { throw 1; }",
        ),
        (
            "readback",
            "state->submission_known = true;",
            "state->submission_known = false;",
        ),
        (
            "readback",
            "state->map_done = true;",
            "state->map_done = false;",
        ),
        (
            "readback",
            "webgpu::command_encode_submit_scoped_with_submit(\n"
            "      instance,",
            "webgpu::command_encode_submit_scoped(\n      instance,",
        ),
        (
            "readback",
            "command_valid ? TicketError::None : TicketError::CommandEncodingFailed",
            "TicketError::None",
        ),
        (
            "header",
            "the map is registered in the same calling turn",
            "the map is eventually registered",
        ),
        (
            "test",
            "browser deferred map start is same-turn",
            "browser deferred map start is delayed",
        ),
        (
            "patch",
            "diff --git a/source/blender/gpu/webgpu/wgpu_readback.cc "
            "b/source/blender/gpu/webgpu/wgpu_readback.cc",
            "",
        ),
        (
            "series",
            "0312-gpu-webgpu-select-readback-same-turn-map.patch",
            "0312-missing.patch",
        ),
    )
    rejected = 0
    for key, old, new in mutations:
        mutated = dict(sources)
        mutated[key] = replace_once(mutated[key], old, new)
        try:
            validate(mutated)
        except (ValueError, KeyError):
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0J_SELECT_READBACK_SAME_TURN_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    sources = {
        "common": COMMON.read_text(),
        "readback": READBACK.read_text(),
        "header": READBACK_HEADER.read_text(),
        "test": TEST.read_text(),
        "patch": PATCH.read_text() if PATCH.exists() else "",
        "series": SERIES.read_text(),
    }
    try:
        self_check(sources) if args.self_check else validate(sources)
    except (ValueError, KeyError) as error:
        print(f"P0J_SELECT_READBACK_SAME_TURN_SOURCE_FAIL {error}")
        return 1
    if not args.self_check:
        print("P0J_SELECT_READBACK_SAME_TURN_SOURCE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
