#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0

"""Fail-closed source contract for first-pixel loader coherence."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOOT = ROOT / "platform_web/shell/boot-windowed.js"
MARKER = "VIEWPORT_CONTENT_LOADER_GATE_V1"


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def require_once(source: str, needle: str, message: str) -> None:
    require(source.count(needle) == 1, f"{message}: count={source.count(needle)}")


def validate(source: str) -> None:
    require_once(source, MARKER, "counter fallback marker drifted")
    require_once(source, "const VIEWPORT_CONTENT_POLL_MS = 100;", "poll interval drifted")
    require_once(source, "const VIEWPORT_CONTENT_POLL_LIMIT = 1200;", "poll bound drifted")
    require_once(
        source,
        "function armViewportContentGate(mod)",
        "viewport-content gate function drifted",
    )
    require_once(
        source,
        'typeof mod._bw_viewport_content_present_count === "function"',
        "VIEW_3D content export is not required",
    )
    require_once(
        source,
        "const contentPresents = Number(mod._bw_viewport_content_present_count());",
        "VIEW_3D content counter is not sampled exactly once",
    )
    require_once(
        source,
        "Number.isFinite(contentPresents) && contentPresents > 0",
        "zero/invalid VIEW_3D content can dismiss the loader",
    )
    require_once(
        source,
        'noteViewportContentReady("validated VIEW_3D frame")',
        "content success does not use the viewport-ready dismissal path",
    )
    require_once(
        source,
        "if (viewportContentReady || finished) return;",
        "poll does not retire after success/failure",
    )
    require_once(
        source,
        "viewportContentPollAttempts >= VIEWPORT_CONTENT_POLL_LIMIT",
        "poll is not bounded",
    )
    require_once(
        source,
        'append("[shell] no validated VIEW_3D content after " +',
        "timeout does not retain a bounded diagnostic",
    )
    require_once(
        source,
        '"; loader remains visible", "err")',
        "timeout does not fail closed with the loader visible",
    )
    require_once(
        source,
        "viewportContentPollTimer = setTimeout(poll, VIEWPORT_CONTENT_POLL_MS);",
        "fallback is not a bounded one-shot poll chain",
    )
    require_once(
        source,
        "armViewportContentGate(mod);",
        "VIEW_3D content gate is not armed after module resolution",
    )
    require('noteViewportContentReady("WM_main settle")' not in source,
            "wall-clock WM_main fallback can expose a zero-present canvas")
    require("setInterval(poll" not in source, "unbounded polling interval introduced")
    gate_start = source.index("function armViewportContentGate(mod)")
    gate_end = source.index("\n}\n", gate_start) + 3
    gate = source[gate_start:gate_end]
    require("_bw_present_count" not in gate,
            "generic presentation counter can dismiss the loader")
    require('noteViewportContentReady("presentBackbuffer")' not in source,
            "generic present log can dismiss the loader")
    require('line.indexOf("presentBackbuffer") !== -1' not in source,
            "generic present-log scanner remains loader-authoritative")

    # Preserve gate-mode behavior.
    require_once(source, 'loaderEl.classList.add("bw-hidden", "bw-gone")',
                 "gate-mode loader suppression drifted")


def mutate_once(source: str, before: str, after: str) -> str:
    require_once(source, before, f"mutation anchor absent: {before!r}")
    return source.replace(before, after, 1)


def main() -> None:
    source = BOOT.read_text(encoding="utf-8")
    try:
        validate(source)
    except ContractError as error:
        raise SystemExit(f"M4_FRAME_COHERENCE_FAIL {error}") from error

    mutations = [
        ("contentPresents > 0", "contentPresents >= 0"),
        ('const contentPresents = Number(mod._bw_viewport_content_present_count());',
         'const contentPresents = Number(mod._bw_present_count());'),
        ('noteViewportContentReady("validated VIEW_3D frame")', 'hideLoader()'),
        ("viewportContentReady || finished", "viewportContentReady"),
        ("VIEWPORT_CONTENT_POLL_LIMIT = 1200", "VIEWPORT_CONTENT_POLL_LIMIT = 120000"),
        ("setTimeout(poll, VIEWPORT_CONTENT_POLL_MS)",
         "setInterval(poll, VIEWPORT_CONTENT_POLL_MS)"),
        ("armViewportContentGate(mod);", "void mod;"),
        ('typeof mod._bw_viewport_content_present_count === "function"',
         'typeof mod._bw_present_count === "function"'),
    ]
    rejected = 0
    for before, after in mutations:
        mutated = mutate_once(source, before, after)
        try:
            validate(mutated)
        except ContractError:
            rejected += 1
            continue
        raise SystemExit(f"M4_FRAME_COHERENCE_FAIL mutation survived: {before!r}")

    print(
        "M4_FRAME_COHERENCE_PASS "
        f"negative={rejected} poll_ms=100 poll_limit=1200 signal=view3d-content "
        f"source={BOOT.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
