#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail closed unless resize draws and presentation use one coherent queue boundary."""

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

PRESENT_QUEUE_REGISTRATION = """  wgpu_ghost->setPresentQueueEnqueue(
      [this](WGPUGhostContext::QueuedPresent present) {
        queue_scheduler_.enqueue(std::move(present));
      });
"""

PRESENT_QUEUE_CLEAR = """  if (ghost_context_ != nullptr) {
    static_cast<WGPUGhostContext *>(ghost_context_)->setPresentQueueEnqueue({});
  }
"""


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

    if context_source.count(PRESENT_QUEUE_REGISTRATION) != 1:
        errors.append("browser presentation is not registered with the backend queue")
    if context_source.count(PRESENT_QUEUE_CLEAR) != 1:
        errors.append("browser presentation queue registration is not cleared on teardown")
    constructor_at = context_source.find("WGPUContext::WGPUContext(")
    registration_at = context_source.find(PRESENT_QUEUE_REGISTRATION)
    destructor_at = context_source.find("WGPUContext::~WGPUContext()")
    clear_at = context_source.find(PRESENT_QUEUE_CLEAR)
    free_at = context_source.find("  free_resources();", destructor_at)
    if not (
        constructor_at >= 0
        and registration_at > constructor_at
        and registration_at < destructor_at
    ):
        errors.append("presentation queue registration is outside the context constructor")
    if not (destructor_at >= 0 and clear_at > destructor_at and clear_at < free_at):
        errors.append("presentation queue registration survives backend resource teardown")

    for marker in (
        "using PresentCompletion = std::function<void(bool success)>;",
        "using QueuedPresent = std::function<void(PresentCompletion on_complete)>;",
        "using PresentQueueEnqueue = std::function<void(QueuedPresent present)>;",
        "void setPresentQueueEnqueue(PresentQueueEnqueue enqueue);",
        "PresentQueueEnqueue present_queue_enqueue_;",
        "bool presentBackbuffer(PresentCompletion on_complete = {});",
    ):
        if ghost_header.count(marker) != 1:
            errors.append(f"GHOST queued-present interface differs: {marker}")

    swap_start = ghost_source.find("GHOST_TSuccess GHOST_ContextWGPUWeb::swapBufferRelease()")
    swap_end = ghost_source.find(
        "GHOST_TSuccess GHOST_ContextWGPUWeb::activateDrawingContext()", swap_start
    )
    swap_release = ghost_source[swap_start:swap_end]
    queued_start = swap_release.find("if (present_queue_enqueue_) {")
    queued_swap = swap_release[queued_start:]
    queued_swap_markers = (
        "if (present_queue_enqueue_) {",
        "present_queue_enqueue_(",
        "started = owner.presentBackbuffer(settle);",
        "return GHOST_kSuccess;",
        "return presentBackbuffer() ? GHOST_kSuccess : GHOST_kFailure;",
    )
    positions = [queued_swap.find(marker) for marker in queued_swap_markers]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        errors.append("GHOST swap does not queue present before its immediate fallback")
    for marker in (
        "void GHOST_ContextWGPUWeb::setPresentQueueEnqueue(PresentQueueEnqueue enqueue)",
        "bool GHOST_ContextWGPUWeb::presentBackbuffer(PresentCompletion on_complete)",
        "on_complete(committed);",
    ):
        if ghost_source.count(marker) != 1:
            errors.append(f"GHOST queued-present implementation differs: {marker}")
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
        "present_registration": context_source.replace(PRESENT_QUEUE_REGISTRATION, "", 1),
        "present_clear": context_source.replace(PRESENT_QUEUE_CLEAR, "", 1),
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
        "queued_present": ghost_source.replace(
            "if (present_queue_enqueue_) {", "if (false) {", 1
        ),
        "queued_completion": ghost_source.replace("on_complete(committed);", "", 1),
        "queued_setter": ghost_source.replace(
            "void GHOST_ContextWGPUWeb::setPresentQueueEnqueue(PresentQueueEnqueue enqueue)",
            "void GHOST_ContextWGPUWeb::disabledPresentQueueEnqueue(PresentQueueEnqueue enqueue)",
            1,
        ),
    }
    ghost_header_mutations = {
        "queued_alias": ghost_header.replace(
            "using PresentQueueEnqueue = std::function<void(QueuedPresent present)>;", "", 1
        ),
        "queued_member": ghost_header.replace("PresentQueueEnqueue present_queue_enqueue_;", "", 1),
        "queued_signature": ghost_header.replace(
            "bool presentBackbuffer(PresentCompletion on_complete = {});",
            "bool presentBackbuffer();",
            1,
        ),
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

    print("BW_M4_RESIZE_SOURCE_PASS sources=4 checks=14 mutations=14")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
