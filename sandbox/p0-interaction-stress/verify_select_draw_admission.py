#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reject selection results when a valid batch exits before draw encoding."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BATCH = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_batch.cc"
SELECT_NEXT = ROOT / "upstream/source/blender/gpu/intern/gpu_select_next.cc"
PATCH = ROOT / "patches/0307-gpu-webgpu-select-draw-admission.patch"
SERIES = ROOT / "patches/series"


def require(source: str, token: str, count: int = 1) -> None:
    if source.count(token) != count:
        raise ValueError(f"expected {count} occurrence(s) of {token!r}")


def validate_source(batch: str, select_next: str, patch: str, series: str) -> None:
    require(batch, '#include "BKE_global.hh"')
    require(batch, "class SelectionDrawAdmission")
    require(batch, "(G.f & G_FLAG_PICKSEL) != 0")
    require(batch, "note_webgpu_draw_drop();", 6)
    require(batch, '"[bw] WGPUWeb-select-draw-drop shader=%s stage=%s\\n"')
    require(batch, "SelectionDrawAdmission selection_draw_admission(shader);", 2)
    require(batch, 'selection_draw_admission.stage("geometry");', 2)
    require(batch, 'selection_draw_admission.stage("pipeline");', 2)
    require(batch, 'selection_draw_admission.stage("render-pass");', 4)
    require(batch, "selection_draw_admission.admit();", 4)

    direct_start = batch.index("void WGPUBatch::draw(")
    indirect_start = batch.index("void WGPUBatch::multi_draw_indirect(")
    direct = batch[direct_start:indirect_start]
    indirect = batch[indirect_start:]
    for name, body in (("direct", direct), ("indirect", indirect)):
        construct = body.index("SelectionDrawAdmission selection_draw_admission(shader);")
        module_gate = body.index("shader->ensure_shader_modules")
        geometry = body.index('selection_draw_admission.stage("geometry");')
        pipeline = body.index('selection_draw_admission.stage("pipeline");')
        vertex_gate = body.index("vertex_buffer_handles_resolve_if_valid")
        render_pass = body.index('selection_draw_admission.stage("render-pass");')
        bind_gate = body.index("bind_group_entries_complete")
        admit = body.index("selection_draw_admission.admit();")
        if not construct < module_gate < geometry < pipeline < vertex_gate:
            raise ValueError(f"{name} selection guard does not cover module/geometry gates")
        if not vertex_gate < bind_gate < render_pass < admit:
            raise ValueError(f"{name} selection guard is admitted before late draw gates")

    require(
        select_next,
        "ghost_web::redraw_drop_generation() != g_state.draw_drop_generation",
    )
    require(
        patch,
        "diff --git a/source/blender/gpu/webgpu/wgpu_batch.cc "
        "b/source/blender/gpu/webgpu/wgpu_batch.cc",
    )
    require(series, "0307-gpu-webgpu-select-draw-admission.patch")


@dataclass
class AdmissionModel:
    selection: bool
    admitted: bool = False
    drop_generation: int = 0

    def stage_exit(self) -> None:
        if self.selection and not self.admitted:
            self.drop_generation += 1

    def encode(self) -> None:
        self.admitted = True


def validate_model() -> None:
    for stage in ("geometry", "pipeline", "vertex", "binding", "render-pass"):
        attempt = AdmissionModel(selection=True, drop_generation=11)
        attempt.stage_exit()
        if attempt.drop_generation != 12:
            raise ValueError(f"selection {stage} exit did not invalidate the cleared result")

    accepted = AdmissionModel(selection=True, drop_generation=20)
    accepted.encode()
    accepted.stage_exit()
    if accepted.drop_generation != 20:
        raise ValueError("an encoded selection draw was reported as dropped")

    ordinary = AdmissionModel(selection=False, drop_generation=30)
    ordinary.stage_exit()
    if ordinary.drop_generation != 30:
        raise ValueError("ordinary native/browser draws entered the selection-only guard")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) < 1:
        raise ValueError(f"mutation input is absent for {old!r}")
    return source.replace(old, new, 1)


def self_check(batch: str, select_next: str, patch: str, series: str) -> None:
    validate_source(batch, select_next, patch, series)
    validate_model()
    mutations = (
        ("batch", "class SelectionDrawAdmission", "class LostSelectionDrawAdmission"),
        ("batch", "(G.f & G_FLAG_PICKSEL) != 0", "false"),
        (
            "batch",
            'selection_draw_admission.stage("geometry");',
            'selection_draw_admission.stage("late-geometry");',
        ),
        (
            "batch",
            'selection_draw_admission.stage("pipeline");',
            'selection_draw_admission.stage("late-pipeline");',
        ),
        (
            "batch",
            'selection_draw_admission.stage("render-pass");',
            'selection_draw_admission.stage("late-render-pass");',
        ),
        (
            "batch",
            "selection_draw_admission.admit();",
            "selection_draw_admission.stage(\"encoded\");",
        ),
        (
            "select_next",
            "ghost_web::redraw_drop_generation() != g_state.draw_drop_generation",
            "ghost_web::redraw_drop_generation() == g_state.draw_drop_generation",
        ),
        (
            "patch",
            "diff --git a/source/blender/gpu/webgpu/wgpu_batch.cc "
            "b/source/blender/gpu/webgpu/wgpu_batch.cc",
            "",
        ),
        (
            "series",
            "0307-gpu-webgpu-select-draw-admission.patch",
            "0307-missing.patch",
        ),
    )
    sources = {
        "batch": batch,
        "select_next": select_next,
        "patch": patch,
        "series": series,
    }
    rejected = 0
    for key, old, new in mutations:
        candidate = dict(sources)
        candidate[key] = replace_once(candidate[key], old, new)
        try:
            validate_source(
                candidate["batch"],
                candidate["select_next"],
                candidate["patch"],
                candidate["series"],
            )
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0J_SELECT_DRAW_ADMISSION_SELFCHECK_PASS mutations={rejected} scenarios=7")


def main() -> int:
    try:
        batch = BATCH.read_text()
        select_next = SELECT_NEXT.read_text()
        patch = PATCH.read_text()
        series = SERIES.read_text()
        self_check(batch, select_next, patch, series)
    except (OSError, ValueError) as error:
        print(f"P0J_SELECT_DRAW_ADMISSION_FAIL {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
