#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser-free adversarial selfchecks for M8 receipt-only contracts."""

from __future__ import annotations

import tempfile
from pathlib import Path

import make_staged_receipt
import verify_m8


PRIMARY = {
    "filename": "blender_browser.wasm",
    "role": "primary",
    "sha256": "a" * 64,
    "critical": True,
}
DEFERRED = {
    "filename": "blender_browser.deferred.wasm",
    "role": "deferred",
    "sha256": "b" * 64,
    "critical": False,
}
CONTRACT = {"shipped_wasm": [PRIMARY, DEFERRED]}


def request(url: str, at_ms: int) -> dict[str, object]:
    return {"url": url, "path": url.split("?", 1)[0], "at_ms": at_ms}


def phase_selfcheck() -> tuple[int, int]:
    expected = make_staged_receipt.expected_shard_requests(CONTRACT)
    positive = {
        "semantic_interaction_ms": 100,
        "expected_shard_requests": expected,
        "wasm_requests": [
            request("/bin/blender_browser.wasm", 10),
            request(f"/bin/blender_browser.deferred.wasm?sha256={'b' * 64}", 101),
        ],
    }
    assert make_staged_receipt.phase_request_failures(positive, CONTRACT) == []
    negatives = [
        {**positive, "wasm_requests": positive["wasm_requests"][:1]},
        {**positive, "wasm_requests": [positive["wasm_requests"][0],
                                       request(f"/bin/blender_browser.deferred.wasm?sha256={'b' * 64}", 100)]},
        {**positive, "wasm_requests": [positive["wasm_requests"][0],
                                       request("/bin/blender_browser.deferred.wasm", 101)]},
        {**positive, "wasm_requests": [*positive["wasm_requests"],
                                       request("/bin/blender_browser.wasm", 12)]},
        {**positive, "wasm_requests": [request("/bin/blender_browser.wasm", 101),
                                       positive["wasm_requests"][1]]},
        {**positive, "expected_shard_requests": []},
    ]
    for mutated in negatives:
        assert make_staged_receipt.phase_request_failures(mutated, CONTRACT), mutated
    return 1, len(negatives)


def exact_receipt_inventory_selfcheck() -> tuple[int, int]:
    with tempfile.TemporaryDirectory(
            prefix=".m8-receipt-selfcheck-", dir=verify_m8.SELF) as temporary:
        root = Path(temporary)
        (root / "a").write_bytes(b"a")
        recorded = {"a": verify_m8.identity(root / "a")}
        failures: list[str] = []
        verify_m8.receipt_matches_files({"files": recorded}, "files", root, ("a",), failures)
        assert failures == []
        failures = []
        verify_m8.receipt_matches_files(
            {"files": {**recorded, "unlisted": {"bytes": 0, "sha256": "0" * 64}}},
            "files", root, ("a",), failures,
        )
        assert any("inventory differs" in failure for failure in failures)
    return 1, 1


def generated_input_exclusion_selfcheck() -> tuple[int, int]:
    assert b"ledger/results/m8.json" in verify_m8.GENERATED_INPUT_PATHS
    assert b"reports/dashboard.md" in verify_m8.GENERATED_INPUT_PATHS
    negatives = (
        b"ledger/results/m0.json",
        b"ledger/results/m7.json",
        b"harness/run.sh",
        b"sandbox/m8-launch-gate/verify_m8.py",
    )
    for path in negatives:
        assert path not in verify_m8.GENERATED_INPUT_PATHS
        assert not path.startswith(verify_m8.GENERATED_INPUT_PREFIXES)
    return 2, len(negatives)


if __name__ == "__main__":
    positives = negatives = 0
    for positive, negative in (
            phase_selfcheck(), exact_receipt_inventory_selfcheck(),
            generated_input_exclusion_selfcheck()):
        positives += positive
        negatives += negative
    print(f"M8_TECHNICAL_RECEIPT_SELFCHECK_PASS positive={positives} negative={negatives}")
