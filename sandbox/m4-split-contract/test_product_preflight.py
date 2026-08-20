#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/windowed-product-preflight.py"
SPEC = importlib.util.spec_from_file_location("windowed_product_preflight", SCRIPT)
assert SPEC and SPEC.loader
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


class ProductPreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="bw-product-preflight-")
        self.build = Path(self.temp.name) / "build"
        self.bin = self.build / "bin"
        self.bin.mkdir(parents=True)
        self.write("blender_browser.js", b"js")
        self.write("blender_browser.data", b"data")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, name: str, data: bytes) -> Path:
        path = self.bin / name
        path.write_bytes(data)
        return path

    def cache(self, mode: str) -> None:
        (self.build / "CMakeCache.txt").write_text(
            f"BLENDER_WEB_WASM_SPLIT_MODE:STRING={mode}\n", encoding="utf-8"
        )

    def row(self, path: Path) -> dict[str, object]:
        value = PREFLIGHT.identity(path)
        return {"path": str(path.resolve()), **value}

    def manifest(self, value: dict[str, object]) -> None:
        (self.bin / "blender_browser.split-build.json").write_text(
            json.dumps({"schema": 1, "verdict": "PASS", **value}), encoding="utf-8"
        )

    def test_off_is_valid_development_shape_but_not_gate_product(self) -> None:
        self.cache("OFF")
        self.write("blender_browser.wasm", b"off-primary")
        self.assertIn("mode=OFF", PREFLIGHT.validate(self.build, "off"))
        with self.assertRaises(PREFLIGHT.ModeBlocked):
            PREFLIGHT.validate(self.build, "apply")

    def test_capture_is_strict_nonshipping_shape(self) -> None:
        self.cache("CAPTURE")
        wasm = self.write("blender_browser.wasm", b"instrumented")
        original = self.write("blender_browser.wasm.orig", b"original")
        js = self.bin / "blender_browser.js"
        self.manifest({
            "mode": "capture",
            "instrumented": self.row(wasm),
            "original": self.row(original),
            "js": self.row(js),
            "inventory_policy": {"capture_artifact_is_not_shippable": True},
        })
        self.assertIn("mode=CAPTURE", PREFLIGHT.validate(self.build, "capture"))

    def test_apply_binds_exact_primary_deferred_and_original(self) -> None:
        self.cache("APPLY")
        primary = self.write("blender_browser.wasm", b"primary")
        deferred = self.write("blender_browser.deferred.wasm", b"deferred")
        original = self.write("blender_browser.wasm.orig", b"original")
        js = self.bin / "blender_browser.js"
        rows = {
            "primary": {"role": "primary", "filename": primary.name, **self.row(primary)},
            "deferred": {"role": "deferred", "filename": deferred.name, **self.row(deferred)},
            "original_build_only": {
                "role": "original_build_only", "filename": original.name, **self.row(original)
            },
        }
        self.manifest({
            "mode": "apply",
            "primary": self.row(primary),
            "secondary": self.row(deferred),
            "original": self.row(original),
            "js": self.row(js),
            "profile_receipt": {
                "schema": "blender-web.wasm-split-profile-union.v2", "status": "PASS"
            },
            "controller_closure": {"verdict": "PASS"},
            "inventory_policy": {
                "bundle_roles": ["primary", "deferred"],
                "build_only_roles": ["original_build_only"],
            },
            "wasm_inventory": list(rows.values()),
        })
        self.assertIn("mode=APPLY", PREFLIGHT.validate(self.build, "apply"))
        deferred.write_bytes(b"tampered")
        with self.assertRaisesRegex(PREFLIGHT.PreflightError, "SHA-256 drift"):
            PREFLIGHT.validate(self.build, "apply")

    def test_off_rejects_a_stale_deferred_shard(self) -> None:
        self.cache("OFF")
        self.write("blender_browser.wasm", b"off-primary")
        self.write("blender_browser.deferred.wasm", b"stale")
        with self.assertRaisesRegex(PREFLIGHT.PreflightError, "artifact set mismatch"):
            PREFLIGHT.validate(self.build, "off")


if __name__ == "__main__":
    unittest.main()
