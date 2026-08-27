#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail closed unless resize draws reactivate and adopt the current window backbuffer."""

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


def validate(context_source: str, wm_source: str) -> list[str]:
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
    args = parser.parse_args()
    context_source = args.source.read_text(encoding="utf-8")
    wm_source = args.wm_source.read_text(encoding="utf-8")
    errors = validate(context_source, wm_source)
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
    escaped = [
        name for name, mutant in context_mutations.items() if not validate(mutant, wm_source)
    ]
    escaped.extend(
        name for name, mutant in wm_mutations.items() if not validate(context_source, mutant)
    )
    if escaped:
        print("BW_M4_RESIZE_SOURCE_FAIL mutation escaped: " + ",".join(escaped))
        return 1

    print("BW_M4_RESIZE_SOURCE_PASS sources=2 checks=5 mutations=6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
