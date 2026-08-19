#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run and bind the focused native IMB web thread-policy aggregate test."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / "build-native-gpu/bin/tests/blender_test"
BUILD_LOG = ROOT / "ledger/buildlogs/20260814T015655.log"
POLICY_SOURCES = (
    ROOT / "upstream/source/blender/imbuf/intern/web_thread_policy.cc",
    ROOT / "upstream/source/blender/imbuf/intern/openexr/openexr_thread_policy.cpp",
    ROOT / "upstream/source/blender/imbuf/intern/oiio/openimageio_thread_policy.cpp",
)
TEST = ROOT / "upstream/source/blender/imbuf/tests/IMB_web_thread_policy_test.cc"
FILTER = "imbuf_web_thread_policy.ProductionAggregateSequence"


def identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if not args.label or "/" in args.label or args.label in {".", ".."}:
        raise SystemExit("invalid label")
    output = ROOT / "sandbox/m8-wasm-split/image-policy-probe/native-evidence" / args.label
    output.mkdir(parents=True, exist_ok=False)
    required = (BINARY, BUILD_LOG, *POLICY_SOURCES, TEST)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing native aggregate inputs: {missing}")

    command = [str(BINARY), f"--gtest_filter={FILTER}"]
    run = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    (output / "stdout.txt").write_text(run.stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(run.stderr, encoding="utf-8")
    failures: list[str] = []
    exact_markers = (
        f"Google Test filter = {FILTER}",
        f"[ RUN      ] {FILTER}",
        f"[       OK ] {FILTER}",
        "[  PASSED  ] 1 test.",
    )
    if run.returncode != 0:
        failures.append(f"test exit code {run.returncode}")
    for marker in exact_markers:
        if run.stdout.count(marker) != 1:
            failures.append(f"expected exactly one marker: {marker}")
    if "[  FAILED  ]" in run.stdout or "[  SKIPPED ]" in run.stdout:
        failures.append("focused test did not produce a clean one-pass result")

    receipt = {
        "schema": 1,
        "label": args.label,
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "filter": FILTER,
        "command": [str(BINARY.relative_to(ROOT)), f"--gtest_filter={FILTER}"],
        "exitCode": run.returncode,
        "inputs": {
            "binary": identity(BINARY),
            "buildLog": identity(BUILD_LOG),
            "policySources": [identity(path) for path in POLICY_SOURCES],
            "testSource": identity(TEST),
        },
        "stdout": identity(output / "stdout.txt"),
        "stderr": identity(output / "stderr.txt"),
    }
    (output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
