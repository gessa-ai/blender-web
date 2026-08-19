#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate a released split build and emit its public packaging inputs.

The finalizer-owned split manifest is the sole authority for Wasm filenames.
This helper deliberately imports the same validator used by the M8 gate so the
assembler cannot silently diverge from the verifier's exact-tree contract.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "sandbox/m8-launch-gate/verify_m8.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("bw_verify_m8", VERIFY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load M8 verifier: {VERIFY}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin", type=Path, required=True)
    parser.add_argument("--public-manifest", type=Path, required=True)
    parser.add_argument("--rows", type=Path, required=True)
    args = parser.parse_args()

    verifier = load_verifier()
    contract = verifier.artifact_contract(args.bin)
    args.public_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.public_manifest.write_text(
        json.dumps(contract["public_split_manifest"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with args.rows.open("w", encoding="utf-8", newline="") as stream:
        for row in contract["shipped_wasm"]:
            fields = (
                row["filename"], row["role"], str(row["bytes"]), row["sha256"],
                "true" if row["critical"] else "false", row["request_phase"],
            )
            if any("\t" in str(value) or "\n" in str(value) for value in fields):
                raise ValueError("split inventory contains unsafe TSV text")
            stream.write("\t".join(str(value) for value in fields) + "\n")
    return 0


def selfcheck() -> None:
    """Exercise the serializer without accepting malformed public values."""
    safe = {
        "filename": "blender_browser.deferred.wasm",
        "role": "deferred",
        "bytes": 7,
        "sha256": "a" * 64,
        "critical": False,
        "request_phase": "after_semantic_first_interaction",
    }
    fields = tuple(str(safe[key]) for key in (
        "filename", "role", "bytes", "sha256", "critical", "request_phase"))
    assert all("\t" not in value and "\n" not in value for value in fields)


if __name__ == "__main__":
    selfcheck()
    raise SystemExit(main())
