#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail closed unless resize adoption and the synchronous window swap stay coherent."""

from __future__ import annotations

import argparse
from pathlib import Path


REQUIRED_BLOCK = """  /* The persistent texture wrapper changes its handle and dimensions in place on resize.
   * FrameBuffer::attachment_set() deliberately ignores an identical wrapper pointer, so the
   * default framebuffers' separately cached width_/height_ would otherwise keep the old surface
   * extent. That stale cache feeds viewport_scissor_plan() even though the render attachment is
   * already the new size, producing an out-of-range scissor and rejecting every draw. Mirror the
   * OpenGL window-context contract and publish the live backing extent on every activation. */
  if (back_left != nullptr) {
    back_left->size_set(w, h);
  }
  if (front_left != nullptr) {
    front_left->size_set(w, h);
  }
"""

REACTIVATION_BLOCK = """#if defined(WITH_METAL_BACKEND) || \\
    (defined(WITH_WEBGPU_BACKEND) && defined(__EMSCRIPTEN__))
  /* Reset drawable to ensure GPU context activation happens at least once per frame if only a
   * single context exists. This is required to ensure the default framebuffer is updated
   * to be the latest backbuffer. */
  wm_window_clear_drawable(wm);
#endif
"""

FORBIDDEN_DEFERRED_PRESENT_MARKERS = (
    "setPresentQueueEnqueue",
    "PresentQueueEnqueue",
    "QueuedPresent",
    "PresentCompletion",
    "present_queue_enqueue_",
)


def validate(
    context_source: str,
    wm_source: str,
    ghost_source: str,
    ghost_header: str,
) -> list[str]:
    errors: list[str] = []
    adopt = "  back->adopt_external(backbuffer, fmt, w, h);"
    if context_source.count(adopt) != 1:
        errors.append("persistent backbuffer adoption is not unique")
    if context_source.count(REQUIRED_BLOCK) != 1:
        errors.append("default framebuffer extent synchronization block differs")
    adopt_at = context_source.find(adopt)
    refresh_at = context_source.find(REQUIRED_BLOCK)
    endif_at = context_source.find("#endif", refresh_at)
    if not (adopt_at >= 0 and refresh_at > adopt_at and endif_at > refresh_at):
        errors.append("extent synchronization is not ordered after adoption inside the web guard")
    if wm_source.count(REACTIVATION_BLOCK) != 1:
        errors.append("browser WebGPU does not reactivate the window context before each draw")
    update_at = wm_source.find("void wm_draw_update(bContext *C)")
    reactivate_at = wm_source.find(REACTIVATION_BLOCK)
    window_loop_at = wm_source.find("  for (wmWindow &win : wm->windows)", update_at)
    if not (update_at >= 0 and update_at < reactivate_at < window_loop_at):
        errors.append("window-context reactivation is not ordered before the draw loop")

    for marker in FORBIDDEN_DEFERRED_PRESENT_MARKERS:
        if marker in context_source or marker in ghost_source or marker in ghost_header:
            errors.append(f"deferred window-present seam remains reachable: {marker}")
    if ghost_header.count("bool presentBackbuffer();") != 1:
        errors.append("GHOST presentBackbuffer is not the synchronous no-callback interface")

    swap_start = ghost_source.find("GHOST_TSuccess GHOST_ContextWGPUWeb::swapBufferRelease()")
    swap_end = ghost_source.find(
        "GHOST_TSuccess GHOST_ContextWGPUWeb::activateDrawingContext()", swap_start
    )
    swap_release = ghost_source[swap_start:swap_end]
    immediate = "return presentBackbuffer() ? GHOST_kSuccess : GHOST_kFailure;"
    if swap_release.count(immediate) != 1:
        errors.append("GHOST swap does not synchronously execute exactly one present")
    device_check = swap_release.find("if (!deviceIsUsable())")
    device_only = swap_release.find(
        "if (mode_ == ghost_web::DrawingContextMode::DeviceOnly)"
    )
    immediate_at = swap_release.find(immediate)
    if not (device_check >= 0 and device_check < device_only < immediate_at):
        errors.append("GHOST synchronous present is outside the validated swap boundary")
    if ghost_source.count("bool GHOST_ContextWGPUWeb::presentBackbuffer()") != 1:
        errors.append("GHOST synchronous present implementation differs")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("upstream/source/blender/gpu/webgpu/wgpu_context.cc"),
    )
    parser.add_argument(
        "--wm-source",
        type=Path,
        default=Path("upstream/source/blender/windowmanager/intern/wm_draw.cc"),
    )
    parser.add_argument(
        "--ghost-source",
        type=Path,
        default=Path("platform_web/ghost/GHOST_ContextWGPUWeb.cc"),
    )
    parser.add_argument(
        "--ghost-header",
        type=Path,
        default=Path("platform_web/ghost/GHOST_ContextWGPUWeb.hh"),
    )
    args = parser.parse_args()
    context_source = args.source.read_text(encoding="utf-8")
    wm_source = args.wm_source.read_text(encoding="utf-8")
    ghost_source = args.ghost_source.read_text(encoding="utf-8")
    ghost_header = args.ghost_header.read_text(encoding="utf-8")
    errors = validate(context_source, wm_source, ghost_source, ghost_header)
    if errors:
        for error in errors:
            print(f"BW_M4_RESIZE_SOURCE_FAIL {error}")
        return 1

    context_mutations = {
        "back_extent": context_source.replace(
            "back_left->size_set(w, h);", "back_left->size_set(w, w);", 1
        ),
        "front_extent": context_source.replace(
            "front_left->size_set(w, h);", "front_left->size_set(h, h);", 1
        ),
        "adoption": context_source.replace(
            "back->adopt_external(backbuffer, fmt, w, h);",
            "back->adopt_external(backbuffer, fmt, w, w);",
            1,
        ),
        "deferred_present_registration": context_source.replace(
            "  instance_ = wgpu_ghost->getInstance();",
            "  wgpu_ghost->setPresentQueueEnqueue([](WGPUGhostContext::QueuedPresent) {});\n"
            "  instance_ = wgpu_ghost->getInstance();",
            1,
        ),
    }
    wm_mutations = {
        "webgpu_reactivation": wm_source.replace(
            "#if defined(WITH_METAL_BACKEND) || \\\n    (defined(WITH_WEBGPU_BACKEND) && defined(__EMSCRIPTEN__))",
            "#ifdef WITH_METAL_BACKEND",
            1,
        ),
        "browser_scope": wm_source.replace(" && defined(__EMSCRIPTEN__)", "", 1),
        "reactivation_call": wm_source.replace("  wm_window_clear_drawable(wm);", "", 1),
    }
    ghost_source_mutations = {
        "present_bypass": ghost_source.replace(
            "return presentBackbuffer() ? GHOST_kSuccess : GHOST_kFailure;",
            "return GHOST_kSuccess;",
            1,
        ),
        "deferred_present_signature": ghost_source.replace(
            "bool GHOST_ContextWGPUWeb::presentBackbuffer()",
            "bool GHOST_ContextWGPUWeb::presentBackbuffer(PresentCompletion on_complete)",
            1,
        ),
    }
    ghost_header_mutations = {
        "deferred_present_alias": ghost_header.replace(
            "  bool presentBackbuffer();",
            "  using PresentCompletion = std::function<void(bool success)>;\n"
            "  bool presentBackbuffer();",
            1,
        ),
        "present_signature": ghost_header.replace("bool presentBackbuffer();", "", 1),
    }
    escaped = [
        name
        for name, mutant in context_mutations.items()
        if not validate(mutant, wm_source, ghost_source, ghost_header)
    ]
    escaped.extend(
        name
        for name, mutant in wm_mutations.items()
        if not validate(context_source, mutant, ghost_source, ghost_header)
    )
    escaped.extend(
        name
        for name, mutant in ghost_source_mutations.items()
        if not validate(context_source, wm_source, mutant, ghost_header)
    )
    escaped.extend(
        name
        for name, mutant in ghost_header_mutations.items()
        if not validate(context_source, wm_source, ghost_source, mutant)
    )
    if escaped:
        print("BW_M4_RESIZE_SOURCE_FAIL mutation escaped: " + ",".join(escaped))
        return 1

    print("BW_M4_RESIZE_SOURCE_PASS sources=4 checks=12 mutations=11")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
