#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reject cleared WebGPU selection readbacks from draw attempts that dropped work."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SELECT_NEXT = ROOT / "upstream/source/blender/gpu/intern/gpu_select_next.cc"
BUFFER_HH = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_buffer.hh"
BUFFER_CC = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_buffer.cc"
STORAGE = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_storage_buffer.cc"
UNIFORM = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_uniform_buffer.cc"
VERTEX = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_vertex_buffer.cc"
INDEX = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_index_buffer.cc"
BATCH = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_batch.cc"
IMMEDIATE = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_immediate.cc"
BACKEND = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_backend.cc"
FRAMEBUFFER = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_framebuffer.cc"
PATCH = ROOT / "patches/0306-gpu-webgpu-select-draw-retry.patch"
SERIES = ROOT / "patches/series"


def require(source: str, token: str, count: int = 1) -> None:
    if source.count(token) != count:
        raise ValueError(f"expected {count} occurrence(s) of {token!r}")


def validate_source(sources: dict[str, str]) -> None:
    select_next = sources["select_next"]
    buffer_hh = sources["buffer_hh"]
    buffer_cc = sources["buffer_cc"]
    storage = sources["storage"]
    uniform = sources["uniform"]
    vertex = sources["vertex"]
    index = sources["index"]
    batch = sources["batch"]
    immediate = sources["immediate"]
    backend = sources["backend"]
    framebuffer = sources["framebuffer"]
    patch = sources["patch"]
    series = sources["series"]
    for token in (
        '#  include "GHOST_WebDisplayState.hh"',
        "uint64_t draw_drop_generation = 0;",
        "bool retry_pending = false;",
        "uint64_t retry_generation = 0;",
        "g_state.draw_drop_generation = ghost_web::redraw_drop_generation();",
        "if (g_async.retry_pending) {",
        "ghost_web::redraw_retry_generation() <= g_async.retry_generation",
        "ghost_web::redraw_drop_generation() != g_state.draw_drop_generation",
        "g_async.retry_generation = ghost_web::redraw_retry_generation();",
        "g_async.retry_pending = false;",
    ):
        require(select_next, token)
    require(select_next, "g_async.retry_pending = true;", 2)
    require(select_next, "GPU_readback_cancel(readback);", 2)
    require(select_next, "g_async.select_id_map.clear();", 3)
    require(select_next, "g_async.in_front_map.clear();", 3)
    if select_next.index("if (g_async.retry_pending) {") > select_next.index(
        "if (g_async.readback == nullptr) {"
    ):
        raise ValueError("retry readiness is checked after the no-readback terminal verdict")
    if select_next.index(
        "ghost_web::redraw_drop_generation() != g_state.draw_drop_generation"
    ) > select_next.index("g_async.readback = readback;"):
        raise ValueError("a dropped selection draw can still publish its cleared readback")

    require(buffer_hh, "bool create_for_draw_scope(const wgpu::Instance &instance,")
    require(
        buffer_hh,
        "bool create_for_draw_scope(const wgpu::Instance &instance,\n"
        "                             const wgpu::Device &device,\n"
        "                             OrderedQueueScheduler &scheduler,",
    )
    for token in (
        "bool Buffer::create_for_draw_scope(const wgpu::Instance &instance,",
        "if ((G.f & G_FLAG_PICKSEL) != 0) {",
        "return create_transient(",
        "return create_scoped(instance, device, kind, usage, size, initial_data, readable, label);",
    ):
        require(buffer_cc, token)
    require(buffer_cc, '#include "BKE_global.hh"')

    require(storage, "return buffer_.create_for_draw_scope(")
    require(uniform, "return buffer_.create_for_draw_scope(")
    require(vertex, "buffer_.create_for_draw_scope(", 2)
    require(index, "buffer_.create_for_draw_scope(", 2)
    for source, expected_calls in (
        (batch, 7),
        (immediate, 2),
        (backend, 2),
        (framebuffer, 2),
    ):
        require(source, "note_webgpu_draw_drop();", expected_calls)
        require(source, "static void note_webgpu_draw_drop()")
    require(
        batch,
        "shader->fragment_module() == nullptr)\n  {\n    note_webgpu_draw_drop();",
        2,
    )
    require(
        immediate,
        "shader->fragment_module() == nullptr)\n  {\n    note_webgpu_draw_drop();",
    )

    for path in (
        "source/blender/gpu/intern/gpu_select_next.cc",
        "source/blender/gpu/webgpu/wgpu_buffer.hh",
        "source/blender/gpu/webgpu/wgpu_buffer.cc",
        "source/blender/gpu/webgpu/wgpu_storage_buffer.cc",
        "source/blender/gpu/webgpu/wgpu_uniform_buffer.cc",
        "source/blender/gpu/webgpu/wgpu_vertex_buffer.cc",
        "source/blender/gpu/webgpu/wgpu_index_buffer.cc",
        "source/blender/gpu/webgpu/wgpu_batch.cc",
        "source/blender/gpu/webgpu/wgpu_immediate.cc",
        "source/blender/gpu/webgpu/wgpu_backend.cc",
        "source/blender/gpu/webgpu/wgpu_framebuffer.cc",
    ):
        require(patch, f"diff --git a/{path} b/{path}")
    require(series, "0306-gpu-webgpu-select-draw-retry.patch")


@dataclass
class RetryModel:
    retry_pending: bool = False
    retry_generation: int = 0
    readback_pending: bool = False
    canceled_readbacks: int = 0
    published_results: int = 0

    def finish_draw(
        self,
        *,
        drop_before: int,
        drop_after: int,
        retry_generation: int,
    ) -> None:
        if drop_after != drop_before:
            self.canceled_readbacks += 1
            self.readback_pending = False
            self.retry_generation = retry_generation
            self.retry_pending = True
            return
        self.retry_pending = False
        self.readback_pending = True

    def status(self, retry_generation: int) -> str:
        if self.retry_pending:
            return "pending" if retry_generation <= self.retry_generation else "ready-to-retry"
        return "pending" if self.readback_pending else "invalid"

    def settle_readback(self) -> None:
        if not self.readback_pending:
            raise ValueError("a canceled cleared readback became consumable")
        self.readback_pending = False
        self.published_results += 1


def validate_model() -> None:
    model = RetryModel()
    model.finish_draw(drop_before=7, drop_after=8, retry_generation=12)
    if model.status(12) != "pending" or model.canceled_readbacks != 1:
        raise ValueError("a dropped attempt did not wait for a later readiness edge")
    if model.status(13) != "ready-to-retry":
        raise ValueError("a later browser-readiness edge did not release the retry")
    if model.published_results != 0 or model.readback_pending:
        raise ValueError("the cleared first-attempt result was published")

    model.finish_draw(drop_before=8, drop_after=8, retry_generation=13)
    if model.retry_pending or model.status(13) != "pending":
        raise ValueError("a clean retry did not start a real readback")
    model.settle_readback()
    if model.published_results != 1:
        raise ValueError("the clean retry result was not published exactly once")

    genuine_miss = RetryModel()
    genuine_miss.finish_draw(drop_before=21, drop_after=21, retry_generation=30)
    genuine_miss.settle_readback()
    if genuine_miss.canceled_readbacks != 0 or genuine_miss.published_results != 1:
        raise ValueError("a clean empty selection would be mistaken for a dropped draw")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return source.replace(old, new, 1)


def self_check(sources: dict[str, str]) -> None:
    validate_source(sources)
    validate_model()
    mutations = (
        ("select_next", "uint64_t draw_drop_generation = 0;", ""),
        ("select_next", "bool retry_pending = false;", ""),
        (
            "select_next",
            "ghost_web::redraw_retry_generation() <= g_async.retry_generation",
            "ghost_web::redraw_retry_generation() >= g_async.retry_generation",
        ),
        (
            "select_next",
            "ghost_web::redraw_drop_generation() != g_state.draw_drop_generation",
            "ghost_web::redraw_drop_generation() == g_state.draw_drop_generation",
        ),
        (
            "select_next",
            "ghost_web::redraw_drop_generation() != g_state.draw_drop_generation) {\n"
            "    GPU_readback_cancel(readback);",
            "ghost_web::redraw_drop_generation() != g_state.draw_drop_generation) {",
        ),
        ("select_next", "g_async.retry_pending = false;", "g_async.retry_pending = true;"),
        ("buffer_cc", "if ((G.f & G_FLAG_PICKSEL) != 0) {", "if (false) {"),
        ("storage", "return buffer_.create_for_draw_scope(", "return buffer_.create_scoped("),
        ("uniform", "return buffer_.create_for_draw_scope(", "return buffer_.create_scoped("),
        (
            "batch",
            "const wgpu::ComputePipeline pipeline = triangle_fan_index_pipeline(ctx);\n"
            "  if (pipeline == nullptr) {\n"
            "    note_webgpu_draw_drop();",
            "const wgpu::ComputePipeline pipeline = triangle_fan_index_pipeline(ctx);\n"
            "  if (pipeline == nullptr) {",
        ),
        (
            "immediate",
            "shader->fragment_module() == nullptr)\n  {\n    note_webgpu_draw_drop();",
            "shader->fragment_module() == nullptr)\n  {",
        ),
        (
            "patch",
            "diff --git a/source/blender/gpu/intern/gpu_select_next.cc "
            "b/source/blender/gpu/intern/gpu_select_next.cc",
            "",
        ),
        ("series", "0306-gpu-webgpu-select-draw-retry.patch", "0306-missing.patch"),
    )
    rejected = 0
    for key, old, new in mutations:
        candidate = dict(sources)
        candidate[key] = replace_once(candidate[key], old, new)
        try:
            validate_source(candidate)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0J_SELECT_DRAW_RETRY_SELFCHECK_PASS mutations={rejected} scenarios=3")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    try:
        sources = {
            "select_next": SELECT_NEXT.read_text(),
            "buffer_hh": BUFFER_HH.read_text(),
            "buffer_cc": BUFFER_CC.read_text(),
            "storage": STORAGE.read_text(),
            "uniform": UNIFORM.read_text(),
            "vertex": VERTEX.read_text(),
            "index": INDEX.read_text(),
            "batch": BATCH.read_text(),
            "immediate": IMMEDIATE.read_text(),
            "backend": BACKEND.read_text(),
            "framebuffer": FRAMEBUFFER.read_text(),
            "patch": PATCH.read_text(),
            "series": SERIES.read_text(),
        }
        if args.self_check:
            self_check(sources)
        else:
            validate_source(sources)
            validate_model()
            print("P0J_SELECT_DRAW_RETRY_SOURCE_PASS scenarios=3")
    except (OSError, ValueError) as error:
        print(f"P0J_SELECT_DRAW_RETRY_SOURCE_FAIL {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
