#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind rapid retained screenshots to a bounded post-queue liveness decision."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRODUCER = ROOT / "sandbox/p0-interaction-stress/rapid_freeze_repro.mjs"


def require_once(source: str, token: str) -> None:
    if source.count(token) != 1:
        raise ValueError(f"expected exactly one {token!r}")


def validate(source: str) -> None:
    for token in (
        'const hardwareDiagnostic = process.env.BW_P0_RAPID_HARDWARE === "1";',
        'hardwareDiagnostic && process.platform !== "darwin"',
        'const SOFTWARE_ADAPTER_TOKENS = Object.freeze([',
        'typeof info.isFallbackAdapter === "boolean"',
        'adapter.status !== "ACCEPTED"',
        'rapid input hardware adapter rejected: ${adapter.reason}',
        'const waitForPixelChange = async (name, baseline, counterBaseline, timeoutMs = 12000)',
        "current.sha256 !== baseline",
        "current.ticks > counterBaseline.ticks",
        "current.presents > counterBaseline.presents",
        "current.retries > counterBaseline.retries",
        'await page.waitForTimeout(350);',
        'const orbitBeforeClick = steps.find((step) => step.name === "orbit-before-click");',
        'actionDrain = await waitForPixelChange(',
        '"action-drain", orbitBeforeClick.sha256, orbitBeforeClick,',
        '"recovery-orbit", actionDrain.sha256, actionDrain,',
        "retainedActionFramesEqual: new Set(retained).size === 1",
        "failureContext.lastSample = result",
        "steps: failureContext?.steps || []",
        "lastSample: failureContext?.lastSample || null",
        "retained.length === 5 ? new Set(retained).size === 1 : null",
        "eventTail: (failureContext?.consoleLines || [])",
        "actionDrainMs: actionDrain.settleMs",
        "recoveryOrbitMs: steps.at(-1).settleMs",
        "if (pageErrors.length !== 0 || lifecycle.length !== 0)",
    ):
        require_once(source, token)
    if source.index("current.sha256 !== baseline") > source.index("return {...current"):
        raise ValueError("pixel and counter liveness is checked after accepting the sample")
    if source.index('"action-drain", orbitBeforeClick.sha256') > source.index(
        '"recovery-orbit", actionDrain.sha256'
    ):
        raise ValueError("recovery orbit precedes queued-action drain")
    if "retainedActionFramesEqual" not in source or "throw new Error" not in source:
        raise ValueError("producer lost diagnostic retained-frame reporting or fail-closed outcome")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return source.replace(old, new, 1)


def self_check(source: str) -> None:
    validate(source)
    mutations = (
        replace_once(source, 'timeoutMs = 12000', 'timeoutMs = 120000'),
        replace_once(source, "current.sha256 !== baseline", "current.sha256 === baseline"),
        replace_once(
            source,
            "current.ticks > counterBaseline.ticks",
            "current.ticks >= counterBaseline.ticks",
        ),
        replace_once(
            source,
            "current.presents > counterBaseline.presents",
            "current.presents >= counterBaseline.presents",
        ),
        replace_once(
            source,
            "current.retries > counterBaseline.retries",
            "current.retries >= counterBaseline.retries",
        ),
        replace_once(source, "await page.waitForTimeout(350);", "await page.waitForTimeout(0);"),
        replace_once(
            source,
            '"action-drain", orbitBeforeClick.sha256, orbitBeforeClick,',
            '"action-drain", actionDrain.sha256, actionDrain,',
        ),
        replace_once(
            source,
            '"recovery-orbit", actionDrain.sha256, actionDrain,',
            '"recovery-orbit", orbitBeforeClick.sha256, orbitBeforeClick,',
        ),
        replace_once(
            source,
            "if (pageErrors.length !== 0 || lifecycle.length !== 0)",
            "if (pageErrors.length !== 0 && lifecycle.length !== 0)",
        ),
        replace_once(
            source,
            'hardwareDiagnostic && process.platform !== "darwin"',
            'hardwareDiagnostic && process.platform === "darwin"',
        ),
        replace_once(
            source,
            'adapter.status !== "ACCEPTED"',
            'adapter.status === "ACCEPTED"',
        ),
        replace_once(
            source,
            "steps: failureContext?.steps || []",
            "steps: [],",
        ),
        replace_once(
            source,
            "lastSample: failureContext?.lastSample || null",
            "lastSample: null",
        ),
    )
    rejected = 0
    for mutation in mutations:
        try:
            validate(mutation)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")
    print(f"P0J_RAPID_INPUT_DRAIN_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    source = PRODUCER.read_text(encoding="utf-8")
    if args.self_check:
        self_check(source)
    else:
        validate(source)
        print("P0J_RAPID_INPUT_DRAIN_SOURCE_PASS bound_ms=12000 counters=wm,present,retry")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"P0J_RAPID_INPUT_DRAIN_SOURCE_FAIL {error}")
        raise SystemExit(1)
