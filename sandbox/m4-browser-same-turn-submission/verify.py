#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail closed unless browser WebGPU queue mutations happen in their calling turn."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_common.hh"
GHOST = ROOT / "platform_web/ghost/GHOST_ContextWGPUWeb.cc"
SYSTEM = ROOT / "platform_web/ghost/GHOST_SystemWeb.cc"
DISPLAY = ROOT / "platform_web/ghost/GHOST_WebDisplayState.hh"
PATCH = ROOT / "patches/0295-gpu-webgpu-browser-same-turn-submission.patch"
SERIES = ROOT / "patches/series"


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def require_once(source: str, token: str, label: str) -> None:
    count = source.count(token)
    require(count == 1, f"{label}: count={count} token={token!r}")


def function(source: str, marker: str) -> str:
    start = source.find(marker)
    require(start >= 0, f"missing function {marker!r}")
    opening = source.find("{", start)
    require(opening >= 0, f"missing body {marker!r}")
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ContractError(f"unterminated function {marker!r}")


def browser_branch(body: str, label: str) -> str:
    start = body.find("#ifdef __EMSCRIPTEN__")
    end = body.find("#else", start)
    require(0 <= start < end, f"{label}: browser/native split missing")
    require(body.find("#endif", end) > end, f"{label}: browser/native split unterminated")
    return body[start:end]


def native_branch(body: str, label: str) -> str:
    start = body.find("#else")
    end = body.find("#endif", start)
    require(0 <= start < end, f"{label}: native branch missing")
    return body[start:end]


def ordered(source: str, tokens: tuple[str, ...], label: str) -> None:
    for token in tokens:
        require_once(source, token, label)
    offsets = tuple(source.index(token) for token in tokens)
    require(offsets == tuple(sorted(offsets)), f"{label}: ordering differs")


def validate(sources: dict[str, str]) -> None:
    common = sources["common"]
    ghost = sources["ghost"]
    system = sources["system"]
    display = sources["display"]
    patch = sources["patch"]
    series = sources["series"]

    command = function(common, "inline void command_encode_submit_scoped(")
    command_browser = browser_branch(command, "command transaction")
    ordered(
        command_browser,
        (
            "(void)scheduler;\n  webgpu_error_scopes_push(device);",
            "auto encoder = device.CreateCommandEncoder();",
            "command_buffer = encoder.Finish();",
            "const bool submitted = handles_valid && queue != nullptr;",
            "if (submitted) {\n    webgpu_error_scopes_push(device);",
            "queue.Submit(1, &command_buffer);",
            "operation_label.empty() ? \"\" : operation_label + \" submission\"",
            "webgpu_error_scopes_pop(instance, device, encode_label, std::move(settle));",
        ),
        "same-turn command submission",
    )
    require(
        "scheduler.reserve()" not in command_browser and "scheduler.enqueue(" not in command_browser,
        "browser command transaction still waits on the ordered scheduler",
    )
    command_native = native_branch(command, "command transaction")
    ordered(
        command_native,
        (
            "OrderedQueueScheduler::Ticket ticket = scheduler.reserve();",
            "webgpu_error_scopes_pop(\n      instance,",
            "ticket.resolve(",
            "queue.Submit(1, &command_buffer);",
        ),
        "native validation-ordered transaction",
    )
    require(
        command_native.count("webgpu_error_scopes_push(device);") == 2 and
        command_native.count("webgpu_error_scopes_pop(") == 2,
        "native command scopes no longer bracket encode and submit",
    )

    write_buffer = function(common, "inline void queue_write_buffer_scoped(")
    write_buffer_browser = browser_branch(write_buffer, "buffer write")
    ordered(
        write_buffer_browser,
        (
            "(void)scheduler;",
            "if (queue == nullptr || buffer == nullptr || bytes.empty())",
            "webgpu_error_scopes_push(device);",
            "queue.WriteBuffer(buffer, offset, bytes.data(), bytes.size());",
            "webgpu_error_scopes_pop(instance, device, operation_label",
        ),
        "same-turn buffer write",
    )
    require("scheduler.enqueue(" not in write_buffer_browser, "browser buffer write is deferred")
    require_once(
        native_branch(write_buffer, "buffer write"),
        "scheduler.enqueue(",
        "native buffer write remains ordered",
    )

    write_texture = function(common, "inline void queue_write_texture_scoped(")
    write_texture_browser = browser_branch(write_texture, "texture write")
    ordered(
        write_texture_browser,
        (
            "(void)scheduler;",
            "if (queue == nullptr || destination.texture == nullptr || bytes.empty())",
            "webgpu_error_scopes_push(device);",
            "queue.WriteTexture(&destination, bytes.data(), bytes.size(), &layout, &extent);",
            "webgpu_error_scopes_pop(instance, device, operation_label",
        ),
        "same-turn texture write",
    )
    require("scheduler.enqueue(" not in write_texture_browser, "browser texture write is deferred")
    require_once(
        native_branch(write_texture, "texture write"),
        "scheduler.enqueue(",
        "native texture write remains ordered",
    )

    swap = function(ghost, "GHOST_TSuccess GHOST_ContextWGPUWeb::swapBufferRelease()")
    require_once(
        swap,
        "return presentBackbuffer() ? GHOST_kSuccess : GHOST_kFailure;",
        "ordinary frame synchronous present",
    )
    rejected_seams = (
        "ordinary_frame_present",
        "OrdinaryFramePresent",
        "WGPUWeb-frame-present-barrier",
        "setPresentQueueEnqueue",
        "PresentQueueEnqueue",
        "QueuedPresent",
    )
    for marker in rejected_seams:
        require(
            marker not in ghost and marker not in system and marker not in display,
            f"deferred ordinary-present seam remains reachable: {marker}",
        )

    patch_tokens = (
        "diff --git a/source/blender/gpu/webgpu/wgpu_common.hh",
        "#ifdef __EMSCRIPTEN__",
        "const bool submitted = handles_valid && queue != nullptr;",
        "queue.Submit(1, &command_buffer);",
        "queue.WriteBuffer(buffer, offset, bytes.data(), bytes.size());",
        "queue.WriteTexture(&destination, bytes.data(), bytes.size(), &layout, &extent);",
    )
    for token in patch_tokens:
        require(token in patch, f"numbered patch 0295 missing {token!r}")
    require_once(series, PATCH.name, "numbered patch series")


def mutate_once(source: str, old: str, new: str) -> str:
    require_once(source, old, "mutation anchor")
    return source.replace(old, new, 1)


def selfcheck(sources: dict[str, str]) -> int:
    validate(sources)
    mutations = (
        ("common", "const bool submitted = handles_valid && queue != nullptr;", "const bool submitted = false;"),
        (
            "common",
            "queue.Submit(1, &command_buffer);\n    /* Pop the nested submission scopes",
            "/* submission removed */\n    /* Pop the nested submission scopes",
        ),
        ("common", "webgpu_error_scopes_pop(instance, device, encode_label, std::move(settle));", ""),
        (
            "common",
            "queue.WriteBuffer(buffer, offset, bytes.data(), bytes.size());\n  webgpu_error_scopes_pop(instance",
            "webgpu_error_scopes_pop(instance",
        ),
        (
            "common",
            "queue.WriteTexture(&destination, bytes.data(), bytes.size(), &layout, &extent);\n  webgpu_error_scopes_pop(instance",
            "webgpu_error_scopes_pop(instance",
        ),
        (
            "common",
            "if (queue == nullptr || buffer == nullptr || bytes.empty()) {\n    (*completion)(false);\n    return;",
            "if (false) {\n    (*completion)(false);\n    return;",
        ),
        (
            "common",
            "if (queue == nullptr || destination.texture == nullptr || bytes.empty()) {\n    (*completion)(false);\n    return;",
            "if (false) {\n    (*completion)(false);\n    return;",
        ),
        ("ghost", "return presentBackbuffer() ? GHOST_kSuccess : GHOST_kFailure;", "return GHOST_kSuccess;"),
        ("patch", "queue.Submit(1, &command_buffer);", ""),
        ("patch", "queue.WriteBuffer(buffer, offset, bytes.data(), bytes.size());", ""),
        ("patch", "queue.WriteTexture(&destination, bytes.data(), bytes.size(), &layout, &extent);", ""),
        ("series", PATCH.name, ""),
    )
    rejected = 0
    for name, old, new in mutations:
        changed = dict(sources)
        changed[name] = mutate_once(changed[name], old, new)
        try:
            validate(changed)
        except ContractError:
            rejected += 1
            continue
        raise ContractError(f"mutation survived: {name}:{old!r}")
    return rejected


def load_sources() -> dict[str, str]:
    paths = {
        "common": COMMON,
        "ghost": GHOST,
        "system": SYSTEM,
        "display": DISPLAY,
        "patch": PATCH,
        "series": SERIES,
    }
    return {name: path.read_text(encoding="utf-8") for name, path in paths.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    sources = load_sources()
    rejected = selfcheck(sources) if args.selfcheck else 0
    validate(sources)
    print(
        "M4_BROWSER_SAME_TURN_SUBMISSION_PASS "
        f"sources={len(sources)} negative={rejected} "
        "order=queue-write,command-submit,synchronous-present diagnostics=asynchronous"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        raise SystemExit(f"M4_BROWSER_SAME_TURN_SUBMISSION_FAIL {error}") from error
