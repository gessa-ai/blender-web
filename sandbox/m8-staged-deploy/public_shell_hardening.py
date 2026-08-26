#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministically disable development-only URL hooks in a public shell copy."""

from __future__ import annotations

import argparse
from pathlib import Path
import tempfile


DEVELOPMENT_SEAM = b"const BW_ALLOW_QUERY_DEV_HOOKS = true;"
PUBLIC_SEAM = b"const BW_ALLOW_QUERY_DEV_HOOKS = false;"


def harden_boot_source(source: bytes) -> bytes:
    """Return the exact public variant, rejecting an absent or ambiguous seam."""
    if source.count(DEVELOPMENT_SEAM) != 1:
        raise ValueError("public dev-hook hardening seam is absent or ambiguous")
    if PUBLIC_SEAM in source:
        raise ValueError("development source already contains the public seam")
    hardened = source.replace(DEVELOPMENT_SEAM, PUBLIC_SEAM, 1)
    if hardened.count(PUBLIC_SEAM) != 1 or DEVELOPMENT_SEAM in hardened:
        raise ValueError("public dev-hook hardening postcondition failed")
    return hardened


def selfcheck() -> None:
    prefix = b"before\n"
    suffix = b"\nafter\n"
    source = prefix + DEVELOPMENT_SEAM + suffix
    assert harden_boot_source(source) == prefix + PUBLIC_SEAM + suffix

    rejected = 0
    for invalid in (
        prefix + suffix,
        DEVELOPMENT_SEAM + b"\n" + DEVELOPMENT_SEAM,
        PUBLIC_SEAM,
        DEVELOPMENT_SEAM + b"\n" + PUBLIC_SEAM,
    ):
        try:
            harden_boot_source(invalid)
        except ValueError:
            rejected += 1
        else:
            raise AssertionError("public hardening self-check accepted an invalid seam")

    with tempfile.TemporaryDirectory(prefix="bw-public-shell-") as temporary:
        path = Path(temporary) / "boot-windowed.js"
        path.write_bytes(source)
        original = path.read_bytes()
        path.write_bytes(harden_boot_source(original))
        assert path.read_bytes() == prefix + PUBLIC_SEAM + suffix

    print(f"M8_PUBLIC_SHELL_HARDENING_SELFCHECK_PASS positive=2 negative={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    if args.selfcheck:
        selfcheck()
        return 0
    if args.input is None or args.output is None:
        parser.error("--input and --output are required unless --selfcheck is used")
    source = args.input.read_bytes()
    args.output.write_bytes(harden_boot_source(source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
