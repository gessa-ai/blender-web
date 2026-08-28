#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind auxiliary WebGPU cache publication to one bounded redraw retry."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTEXT = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_context.cc"
FRAMEBUFFER = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_framebuffer.cc"
BATCH = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_batch.cc"
SERIES = ROOT / "patches/series"
PATCH = ROOT / "patches/0300-gpu-webgpu-auxiliary-cache-redraw-readiness.patch"

HELPER = "static void request_webgpu_redraw_retry()"
CALLBACK = "[](auto published) {"
PUBLISH_GUARD = "if (published != nullptr) {"
REQUEST = "request_webgpu_redraw_retry();"
GHOST_REQUEST = "ghost_web::request_redraw_retry();"


def method(source: str, signature: str) -> str:
    if source.count(signature) != 1:
        raise ValueError(f"method boundary is not unique: {signature}")
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated method: {signature}")


METHODS = (
    ("context", "wgpu::Buffer WGPUContext::dummy_vertex_buffer()", 1),
    ("context", "bool WGPUContext::blit_color_render(", 2),
    ("context", "bool WGPUContext::blit_depth_render(", 2),
    ("context", "bool WGPUContext::upload_depth_render(", 2),
    ("framebuffer", "bool WGPUFrameBuffer::ensure_empty_render_attachment() const", 1),
    ("framebuffer", "bool WGPUFrameBuffer::submit_scissored_color_clear(", 2),
    ("framebuffer", "bool WGPUFrameBuffer::submit_scissored_depth_stencil_clear(", 2),
    ("batch", "static wgpu::ComputePipeline triangle_fan_index_pipeline(WGPUContext &ctx)", 1),
)


def validate(context: str, framebuffer: str, batch: str, series: str, patch: str) -> None:
    sources = {"context": context, "framebuffer": framebuffer, "batch": batch}
    expected_total = sum(expected for _, _, expected in METHODS)

    for label, source in sources.items():
        if source.count(HELPER) != 1:
            raise ValueError(f"{label} redraw helper is not unique")
        if source.count(GHOST_REQUEST) != 1:
            raise ValueError(f"{label} redraw helper does not publish one browser edge")

    actual_total = 0
    for label, signature, expected in METHODS:
        body = method(sources[label], signature)
        cache_calls = body.count(".get_or_create(")
        callbacks = body.count(CALLBACK)
        guards = body.count(PUBLISH_GUARD)
        requests = body.count(REQUEST)
        if (cache_calls, callbacks, guards, requests) != (expected,) * 4:
            raise ValueError(
                f"{signature} cache/readiness coverage differs: "
                f"calls={cache_calls} callbacks={callbacks} guards={guards} "
                f"requests={requests} expected={expected}"
            )
        actual_total += callbacks
    if actual_total != expected_total or expected_total != 13:
        raise ValueError(f"auxiliary cache census differs: {actual_total}/{expected_total}")

    if series.count(PATCH.name) != 1:
        raise ValueError("numbered patch is not present exactly once in patches/series")
    for path in (
        "source/blender/gpu/webgpu/wgpu_context.cc",
        "source/blender/gpu/webgpu/wgpu_framebuffer.cc",
        "source/blender/gpu/webgpu/wgpu_batch.cc",
    ):
        if patch.count(f"diff --git a/{path} b/{path}") != 1:
            raise ValueError(f"numbered patch does not bind {path}")
    patch_counts = {HELPER: 3, CALLBACK: 13, GHOST_REQUEST: 3}
    for marker, expected in patch_counts.items():
        if patch.count(marker) != expected:
            raise ValueError(
                f"numbered patch count differs for {marker}: "
                f"{patch.count(marker)}/{expected}"
            )


def replace_nth(source: str, needle: str, replacement: str, occurrence: int) -> str:
    start = -1
    for _ in range(occurrence + 1):
        start = source.find(needle, start + 1)
        if start < 0:
            raise ValueError(f"cannot mutate occurrence {occurrence} of {needle}")
    return source[:start] + replacement + source[start + len(needle) :]


def self_check(context: str, framebuffer: str, batch: str, series: str, patch: str) -> None:
    validate(context, framebuffer, batch, series, patch)
    mutations: list[tuple[str, str, str, str, str]] = []
    for label, source in (("context", context), ("framebuffer", framebuffer), ("batch", batch)):
        callback_count = source.count(CALLBACK)
        for occurrence in range(callback_count):
            mutated = replace_nth(source, CALLBACK, "[](auto) {", occurrence)
            values = {"context": context, "framebuffer": framebuffer, "batch": batch}
            values[label] = mutated
            mutations.append((values["context"], values["framebuffer"], values["batch"], series, patch))

    mutations.extend(
        (
            (context.replace(GHOST_REQUEST, "", 1), framebuffer, batch, series, patch),
            (context, framebuffer.replace(GHOST_REQUEST, "", 1), batch, series, patch),
            (context, framebuffer, batch.replace(GHOST_REQUEST, "", 1), series, patch),
            (context, framebuffer, batch, series.replace(PATCH.name, "0300-missing.patch", 1), patch),
            (context, framebuffer, batch, series, patch.replace(CALLBACK, "[](auto) {", 1)),
        )
    )
    rejected = 0
    for mutation in mutations:
        try:
            validate(*mutation)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(
        "P0IJ_AUXILIARY_CACHE_REDRAW_SELFCHECK_PASS "
        f"producers=13 mutations={rejected}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    values = (
        CONTEXT.read_text(encoding="utf-8"),
        FRAMEBUFFER.read_text(encoding="utf-8"),
        BATCH.read_text(encoding="utf-8"),
        SERIES.read_text(encoding="utf-8"),
        PATCH.read_text(encoding="utf-8") if PATCH.exists() else "",
    )
    if args.self_check:
        self_check(*values)
    else:
        validate(*values)
        print("P0IJ_AUXILIARY_CACHE_REDRAW_SOURCE_PASS producers=13 patch=0300")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"P0IJ_AUXILIARY_CACHE_REDRAW_SOURCE_FAIL {error}")
        raise SystemExit(1)
