#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Emit the path-sanitized public view of the final split-build inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import verify_m8


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out).resolve()
    expected_parent = (verify_m8.BUNDLE / "bin").resolve()
    if output.parent != expected_parent or output.name != "split-build.json":
        raise SystemExit(f"output must be exactly {expected_parent / 'split-build.json'}")
    contract = verify_m8.artifact_contract()
    output.write_text(json.dumps(contract["public_split_manifest"], indent=2) + "\n",
                      encoding="utf-8")
    print(f"public split manifest: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
