#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Derive the M7 browser producer allowlist from the M8 finalizer-owned inventory."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sandbox/m8-launch-gate"))
import verify_m8  # noqa: E402

OUT = ROOT / "sandbox/m7-product-gate/bundle-identity.json"


def main() -> int:
    files = list(verify_m8.bundle_files())
    verify_m8.validate_public_split_manifest()
    payload = {
        "schema": "blender-web.m7-bundle-identity.v1",
        "splitManifestSha256": verify_m8.sha256(verify_m8.BUILD / verify_m8.SPLIT_MANIFEST),
        "publicSplitManifestSha256": verify_m8.sha256(
            verify_m8.BUNDLE / verify_m8.BUNDLE_SPLIT_MANIFEST),
        "files": files,
    }
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite immutable bundle identity: {OUT}")
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"M7_BUNDLE_IDENTITY_PASS files={len(files)} out={OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
