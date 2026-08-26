#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Verify the exact WSL2 hardware-WebGPU deferral boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "ledger/deferred.json"
NOTE = ROOT / "notes/s7-wsl2-hardware-blocker-20260822.md"
TRUTH_NOTE = ROOT / "notes/m8-deferral-registry-completeness-20260826.md"
BLOCKER = (
    "no conformant hardware Vulkan ICD in WSL2 "
    "(NVIDIA ships none; Mesa dzn rejected by Dawn)"
)
EXPECTED = {
    "wsl2-hardware-webgpu-m3": "M3",
    "wsl2-hardware-webgpu-m4": "M4",
    "wsl2-hardware-webgpu-m5": "M5",
    "wsl2-hardware-webgpu-m6-gpu": "M6",
    "wsl2-hardware-webgpu-m7": "M7",
    "wsl2-hardware-webgpu-m8": "M8",
}


def fail(message: str) -> None:
    raise SystemExit(f"S7_DEFERRAL_CONTRACT_FAIL {message}")


def main() -> None:
    try:
        document = json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"ledger={error}")
    rows = document.get("deferred") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        fail("missing-deferred-array")

    by_id: dict[str, dict[str, object]] = {}
    for number, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            fail(f"invalid-row={number}")
        row_id = row["id"]
        if row_id in by_id:
            fail(f"duplicate-id={row_id}")
        by_id[row_id] = row

    found = set(by_id).intersection(EXPECTED)
    if found != set(EXPECTED):
        fail(f"hardware-row-set={','.join(sorted(found)) or 'none'}")
    for row_id, milestone in EXPECTED.items():
        row = by_id[row_id]
        if row.get("status") != "deferred":
            fail(f"status={row_id}")
        if row.get("milestone") != milestone:
            fail(f"milestone={row_id}")
        if row.get("blocker") != BLOCKER:
            fail(f"blocker={row_id}")
        evidence = str(row.get("evidence", ""))
        if NOTE.relative_to(ROOT).as_posix() not in evidence:
            fail(f"evidence={row_id}")
        if TRUTH_NOTE.relative_to(ROOT).as_posix() not in evidence:
            fail(f"truth-evidence={row_id}")
        revisit = str(row.get("revisit", ""))
        if "driver-operated Apple M4 Pro" not in revisit:
            fail(f"revisit={row_id}")
        impact = str(row.get("impact", ""))
        for token in (
            "on this WSL2 host",
            "driver-operated conformant Apple M4 Pro",
            "project receipt",
        ):
            if token not in impact:
                fail(f"impact={row_id}:{token}")
        stale = (impact + "\n" + revisit).lower()
        if "normal host reboot" in stale or "windows-side edge" in stale:
            fail(f"stale-revisit={row_id}")

    if "27/27" not in str(by_id["wsl2-hardware-webgpu-m6-gpu"].get("impact", "")):
        fail("m6-cpu-boundary")
    if "m8-wasm-15mb-bar" not in str(by_id["wsl2-hardware-webgpu-m8"].get("impact", "")):
        fail("m8-independent-blocker")

    try:
        note = NOTE.read_text(encoding="utf-8")
    except OSError as error:
        fail(f"note={error}")
    required_note_tokens = (
        "RequestAdapter failed: No supported adapters",
        "vulkan-1-x64.dll",
        "/usr/lib/wsl/drivers",
        "driver-operated Apple M4 Pro",
        "strict CAPTURE split generation",
        "Windows-side Edge plan is closed",
        "retry this path or restart WSL/Windows",
        "binds no receipt, profile, or split product",
    )
    missing = [token for token in required_note_tokens if token not in note]
    if missing:
        fail(f"note-token={missing[0]}")
    if "A conformant path is staged for later through Windows-side Edge" in note:
        fail("stale-reboot-path")

    blocker_sha = hashlib.sha256(BLOCKER.encode()).hexdigest()[:12]
    print(
        "S7_DEFERRAL_CONTRACT_PASS "
        f"rows={len(EXPECTED)} tiers={','.join(EXPECTED.values())} "
        f"blocker_sha256={blocker_sha}"
    )


if __name__ == "__main__":
    main()
