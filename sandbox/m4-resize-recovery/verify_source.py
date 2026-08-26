#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail closed unless window backbuffer adoption also refreshes framebuffer extents."""

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


def validate(source: str) -> list[str]:
    errors: list[str] = []
    adopt = "  back->adopt_external(backbuffer, fmt, w, h);"
    if source.count(adopt) != 1:
        errors.append("persistent backbuffer adoption is not unique")
    if source.count(REQUIRED_BLOCK) != 1:
        errors.append("default framebuffer extent synchronization block differs")
    adopt_at = source.find(adopt)
    refresh_at = source.find(REQUIRED_BLOCK)
    endif_at = source.find("#endif", refresh_at)
    if not (adopt_at >= 0 and refresh_at > adopt_at and endif_at > refresh_at):
        errors.append("extent synchronization is not ordered after adoption inside the web guard")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("upstream/source/blender/gpu/webgpu/wgpu_context.cc"),
    )
    args = parser.parse_args()
    source = args.source.read_text(encoding="utf-8")
    errors = validate(source)
    if errors:
        for error in errors:
            print(f"BW_M4_RESIZE_SOURCE_FAIL {error}")
        return 1

    mutations = {
        "back_extent": source.replace("back_left->size_set(w, h);", "back_left->size_set(w, w);", 1),
        "front_extent": source.replace(
            "front_left->size_set(w, h);", "front_left->size_set(h, h);", 1
        ),
        "adoption": source.replace(
            "back->adopt_external(backbuffer, fmt, w, h);",
            "back->adopt_external(backbuffer, fmt, w, w);",
            1,
        ),
    }
    escaped = [name for name, mutant in mutations.items() if not validate(mutant)]
    if escaped:
        print("BW_M4_RESIZE_SOURCE_FAIL mutation escaped: " + ",".join(escaped))
        return 1

    print("BW_M4_RESIZE_SOURCE_PASS checks=3 mutations=3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
