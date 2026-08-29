#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Keep cleared selection readbacks behind asynchronous draw validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DISPLAY = ROOT / "platform_web/ghost/GHOST_WebDisplayState.hh"
BATCH = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_batch.cc"
SELECT_NEXT = ROOT / "upstream/source/blender/gpu/intern/gpu_select_next.cc"
PATCH = ROOT / "patches/0308-gpu-webgpu-select-draw-validation.patch"
SERIES = ROOT / "patches/series"


def require(source: str, token: str, count: int = 1) -> None:
    if source.count(token) != count:
        raise ValueError(f"expected {count} occurrence(s) of {token!r}")


def validate_source(sources: dict[str, str]) -> None:
    display = sources["display"]
    batch = sources["batch"]
    select_next = sources["select_next"]
    patch = sources["patch"]
    series = sources["series"]

    for token in (
        "note_selection_draw_validation_begin()",
        "note_selection_draw_validation_complete(const bool valid)",
        "selection_draw_validation_pending()",
        "selection_draw_validation_failure_generation()",
    ):
        require(display, token)
    require(
        display,
        "inline std::atomic<uint64_t> selection_draw_validation_pending_counter{0};",
    )
    require(
        display,
        "inline std::atomic<uint64_t> selection_draw_validation_failure_counter{0};",
    )
    require(
        display,
        "selection_draw_validation_pending_counter.fetch_add(1u, "
        "std::memory_order_relaxed)",
    )
    require(
        display,
        "selection_draw_validation_pending_counter.fetch_sub(1u, "
        "std::memory_order_release)",
    )
    require(
        display,
        "selection_draw_validation_pending_counter.load(std::memory_order_acquire)",
    )

    require(batch, "validation_completion() const")
    require(batch, "note_selection_draw_validation_begin();")
    require(batch, "note_selection_draw_validation_complete(valid);")
    require(batch, 'stage=validation')
    require(batch, "request_webgpu_redraw_retry();", 2)
    require(batch, "selection_validation_completion", 16)
    require(batch, "selection_draw_admission.validation_completion()", 4)
    require(batch, "selection_validation_completion(valid);", 4)

    for token in (
        "uint64_t readback_draw_validation_failure_generation = 0;",
        "ghost_web::selection_draw_validation_pending() != 0",
        "GPU_readback_cancel(g_async.readback);\n    g_async.select_id_map.clear();",
        "g_async.retry_generation = retry_generation > 0 ? retry_generation - 1u : 0;",
    ):
        require(select_next, token)
    require(select_next, "g_async.readback_draw_validation_failure_generation", 2)
    pending = select_next.index("ghost_web::selection_draw_validation_pending() != 0")
    consume = select_next.index("GPU_readback_consume(g_async.readback")
    if pending > consume:
        raise ValueError("selection readback can be consumed before draw validation settles")
    late_drop = select_next.index(
        "ghost_web::selection_draw_validation_failure_generation() !=\n"
        "          g_async.readback_draw_validation_failure_generation"
    )
    if pending > late_drop or late_drop > consume:
        raise ValueError("late draw rejection is not checked after validation and before consume")

    require(
        patch,
        "diff --git a/source/blender/gpu/intern/gpu_select_next.cc "
        "b/source/blender/gpu/intern/gpu_select_next.cc",
    )
    require(
        patch,
        "diff --git a/source/blender/gpu/webgpu/wgpu_batch.cc "
        "b/source/blender/gpu/webgpu/wgpu_batch.cc",
    )
    require(series, "0308-gpu-webgpu-select-draw-validation.patch")


@dataclass
class ValidationModel:
    drop_generation: int = 7
    retry_generation: int = 11
    pending_validations: int = 0
    readback_pending: bool = False
    readback_drop_generation: int = 0
    retry_pending: bool = False
    consumed: int = 0

    def begin_draw(self) -> None:
        self.pending_validations += 1

    def begin_readback(self) -> None:
        self.readback_pending = True
        self.readback_drop_generation = self.drop_generation

    def complete_draw(self, valid: bool) -> None:
        if self.pending_validations == 0:
            raise ValueError("selection validation completion underflow")
        if not valid:
            self.drop_generation += 1
            self.retry_generation += 1
        self.pending_validations -= 1

    def status(self) -> str:
        if self.pending_validations:
            return "pending-validation"
        if self.readback_pending and self.drop_generation != self.readback_drop_generation:
            self.readback_pending = False
            self.retry_pending = True
            # The rejected validation itself published the edge that makes an exact retry legal.
            self.retry_generation -= 1
            return "ready-to-retry"
        if self.retry_pending:
            return "ready-to-retry"
        return "pending-readback" if self.readback_pending else "invalid"

    def consume(self) -> None:
        if self.status() != "pending-readback":
            raise ValueError("selection consumed before a clean validation/readback boundary")
        self.readback_pending = False
        self.consumed += 1


def validate_model() -> None:
    rejected = ValidationModel()
    rejected.begin_draw()
    rejected.begin_readback()
    if rejected.status() != "pending-validation":
        raise ValueError("readback did not wait for the outstanding selection draw")
    rejected.complete_draw(valid=False)
    if rejected.status() != "ready-to-retry" or rejected.consumed != 0:
        raise ValueError("late validation rejection published the cleared selection result")

    clean = ValidationModel()
    clean.begin_draw()
    clean.begin_readback()
    clean.complete_draw(valid=True)
    clean.consume()
    if clean.consumed != 1:
        raise ValueError("clean validated selection result was not consumable exactly once")

    multi = ValidationModel()
    multi.begin_draw()
    multi.begin_draw()
    multi.begin_readback()
    multi.complete_draw(valid=True)
    if multi.status() != "pending-validation":
        raise ValueError("one of multiple selection validations released readback early")
    multi.complete_draw(valid=True)
    multi.consume()


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) < 1:
        raise ValueError(f"mutation input absent for {old!r}")
    return source.replace(old, new, 1)


def self_check(sources: dict[str, str]) -> None:
    validate_source(sources)
    validate_model()
    mutations = (
        ("display", "note_selection_draw_validation_begin()", "lost_validation_begin()"),
        (
            "display",
            "note_selection_draw_validation_complete(const bool valid)",
            "lost_validation_end(const bool valid)",
        ),
        ("batch", "validation_completion() const", "validation_lost() const"),
        ("batch", 'stage=validation', 'stage=encoded'),
        (
            "select_next",
            "ghost_web::selection_draw_validation_pending() != 0",
            "false",
        ),
        (
            "select_next",
            "ghost_web::selection_draw_validation_failure_generation() !=\n"
            "          g_async.readback_draw_validation_failure_generation",
            "ghost_web::selection_draw_validation_failure_generation() ==\n"
            "          g_async.readback_draw_validation_failure_generation",
        ),
        ("patch", "diff --git a/source/blender/gpu/intern/gpu_select_next.cc", "diff --git a/lost"),
        ("series", "0308-gpu-webgpu-select-draw-validation.patch", "0308-missing.patch"),
    )
    rejected = 0
    survived: list[int] = []
    for mutation_index, (key, old, new) in enumerate(mutations):
        candidate = dict(sources)
        candidate[key] = replace_once(candidate[key], old, new)
        try:
            validate_source(candidate)
        except ValueError:
            rejected += 1
        else:
            survived.append(mutation_index)
    if rejected != len(mutations):
        raise ValueError(
            f"mutation self-check rejected {rejected}/{len(mutations)}; survived={survived}"
        )
    print(f"P0J_SELECT_DRAW_VALIDATION_SELFCHECK_PASS mutations={rejected} scenarios=3")


def main() -> int:
    try:
        sources = {
            "display": DISPLAY.read_text(),
            "batch": BATCH.read_text(),
            "select_next": SELECT_NEXT.read_text(),
            "patch": PATCH.read_text() if PATCH.exists() else "",
            "series": SERIES.read_text(),
        }
        self_check(sources)
    except (OSError, ValueError) as error:
        print(f"P0J_SELECT_DRAW_VALIDATION_FAIL {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
