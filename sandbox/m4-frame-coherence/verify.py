#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0

"""Fail-closed source contract for first-pixel loader coherence."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOOT = ROOT / "platform_web/shell/boot-windowed.js"
MARKER = "FIRST_PIXELS_COUNTER_FALLBACK_V1"


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def require_once(source: str, needle: str, message: str) -> None:
    require(source.count(needle) == 1, f"{message}: count={source.count(needle)}")


def validate(source: str) -> None:
    require_once(source, MARKER, "counter fallback marker drifted")
    require_once(source, "const FIRST_PIXELS_POLL_MS = 100;", "poll interval drifted")
    require_once(source, "const FIRST_PIXELS_POLL_LIMIT = 1200;", "poll bound drifted")
    require_once(
        source,
        "function armFirstPixelsCounterFallback(mod)",
        "counter fallback function drifted",
    )
    require_once(
        source,
        'typeof mod._bw_present_count === "function"',
        "uncapped present export is not required",
    )
    require_once(
        source,
        "const presents = Number(mod._bw_present_count());",
        "present counter is not sampled exactly once",
    )
    require_once(
        source,
        "Number.isFinite(presents) && presents > 0",
        "zero/invalid presentation can dismiss the loader",
    )
    require_once(
        source,
        'noteFirstPixels("present counter")',
        "counter success does not use the first-pixel dismissal path",
    )
    require_once(
        source,
        "if (firstPixels || finished) return;",
        "poll does not retire after success/failure",
    )
    require_once(
        source,
        "firstPixelsPollAttempts >= FIRST_PIXELS_POLL_LIMIT",
        "poll is not bounded",
    )
    require_once(
        source,
        'append("[shell] no successful presentation after " +',
        "timeout does not retain a bounded diagnostic",
    )
    require_once(
        source,
        '"; loader remains visible", "err")',
        "timeout does not fail closed with the loader visible",
    )
    require_once(
        source,
        "firstPixelsPollTimer = setTimeout(poll, FIRST_PIXELS_POLL_MS);",
        "fallback is not a bounded one-shot poll chain",
    )
    require_once(
        source,
        "armFirstPixelsCounterFallback(mod);",
        "counter fallback is not armed after module resolution",
    )
    require('noteFirstPixels("WM_main settle")' not in source,
            "wall-clock WM_main fallback can expose a zero-present canvas")
    require("setInterval(poll" not in source, "unbounded polling interval introduced")

    # Preserve the owner-mandated primary signal and gate-mode behavior.
    require_once(source, 'line.indexOf("presentBackbuffer") !== -1',
                 "primary present marker scan drifted")
    require_once(source, 'noteFirstPixels("presentBackbuffer")',
                 "primary present marker dismissal drifted")
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
        ("presents > 0", "presents >= 0"),
        ('const presents = Number(mod._bw_present_count());',
         'const presents = Number(mod._bw_wm_tick_count());'),
        ('noteFirstPixels("present counter")', 'hideLoader()'),
        ("firstPixels || finished", "firstPixels"),
        ("FIRST_PIXELS_POLL_LIMIT = 1200", "FIRST_PIXELS_POLL_LIMIT = 120000"),
        ("setTimeout(poll, FIRST_PIXELS_POLL_MS)",
         "setInterval(poll, FIRST_PIXELS_POLL_MS)"),
        ("armFirstPixelsCounterFallback(mod);", "void mod;"),
        ('noteFirstPixels("presentBackbuffer")', 'hideLoader()'),
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
        f"negative={rejected} poll_ms=100 poll_limit=1200 source={BOOT.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
