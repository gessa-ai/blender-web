# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail-closed source contract for the resumable EEVEE shadow-atlas handoff."""

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "upstream/source/blender/draw/engines/eevee/eevee_engine.cc"
INSTANCE_HH = ROOT / "upstream/source/blender/draw/engines/eevee/eevee_instance.hh"
INSTANCE_CC = ROOT / "upstream/source/blender/draw/engines/eevee/eevee_instance.cc"
SHADOW_HH = ROOT / "upstream/source/blender/draw/engines/eevee/eevee_shadow.hh"
SHADOW_CC = ROOT / "upstream/source/blender/draw/engines/eevee/eevee_shadow.cc"
PIPELINE_CC = ROOT / "upstream/source/blender/draw/engines/eevee/eevee_pipeline.cc"


def body_after(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise AssertionError(f"missing signature: {signature}")
    opening = source.find("{", start + len(signature))
    if opening < 0:
        raise AssertionError(f"missing body: {signature}")
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : index]
    raise AssertionError(f"unterminated body: {signature}")


def ordered(source: str, *needles: str) -> None:
    position = -1
    for needle in needles:
        next_position = source.find(needle, position + 1)
        if next_position < 0:
            raise AssertionError(f"missing ordered token: {needle}")
        position = next_position


def main() -> int:
    engine = ENGINE.read_text()
    instance_hh = INSTANCE_HH.read_text()
    instance_cc = INSTANCE_CC.read_text()
    shadow_hh = SHADOW_HH.read_text()
    shadow_cc = SHADOW_CC.read_text()
    pipeline_cc = PIPELINE_CC.read_text()

    status = body_after(shadow_cc, "ShadowAtlasStatus ShadowModule::shadow_atlas_status()")
    assert "is_device_allocation_pending()" in status
    assert "return ShadowAtlasStatus::Pending;" in status
    ordered(status, "webgpu_shadow_atlas_ready_ =", "do_full_update_ = true;", "return ShadowAtlasStatus::Ready;")

    begin_sync = body_after(shadow_cc, "void ShadowModule::begin_sync()")
    ordered(
        begin_sync,
        "webgpu_shadow_atlas_ready_for_sync_ =",
        "shadow_atlas_status() == ShadowAtlasStatus::Ready",
    )

    pipeline_sync = body_after(pipeline_cc, "void ShadowPipeline::sync()")
    assert "webgpu_shadow_atlas_ready_for_sync_" in pipeline_sync
    assert 'pass.bind_ssbo(SHADOW_ATLAS_BUF_SLOT, inst_.shadows.shadow_atlas_buf_)' in pipeline_sync
    pipeline_render = body_after(pipeline_cc, "void ShadowPipeline::render(View &view)")
    ordered(pipeline_render, "if (!shadow_atlas_bound_)", "return;", "submit(render_ps_, view)")

    assert re.search(r"bool\s+shadow_atlas_requires_sync\(\)\s+const\s*;", shadow_hh)
    requires_sync = body_after(
        shadow_cc, "bool ShadowModule::shadow_atlas_requires_sync() const"
    )
    ordered(
        requires_sync,
        "use_webgpu_shadow_atlas_",
        "webgpu_shadow_atlas_ready_",
        "!webgpu_shadow_atlas_ready_for_sync_",
    )

    assert re.search(r"bool\s+shadow_atlas_requires_sync\(\)\s+const\s*;", instance_hh)
    instance_requires_sync = body_after(
        instance_cc, "bool Instance::shadow_atlas_requires_sync() const"
    )
    assert "return shadows.shadow_atlas_requires_sync();" in instance_requires_sync

    render_step = body_after(engine, "static RenderStepStatus eevee_render_step")
    await_start = render_step.find("case EEVEEImageRenderPhase::AwaitShadowAtlas:")
    render_start = render_step.find("case EEVEEImageRenderPhase::RenderSamples:", await_start)
    assert await_start >= 0 and render_start > await_start
    ready_path = render_step[await_start:render_start]
    ordered(
        ready_path,
        "shadow_atlas_status()",
        "ShadowAtlasStatus::Pending",
        "ShadowAtlasStatus::Failed",
        "shadow_atlas_requires_sync()",
        "render_sync();",
        "EEVEEImageRenderPhase::RenderSamples",
    )
    assert ready_path.count("render_sync();") == 1

    print("EEVEE_SHADOW_ATLAS_RESYNC_CONTRACT PASS cases=8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError) as exc:
        print(f"EEVEE_SHADOW_ATLAS_RESYNC_CONTRACT FAIL {exc}", file=sys.stderr)
        raise SystemExit(1)
