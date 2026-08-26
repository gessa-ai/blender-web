#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser/product-free portability checks for the monolithic deploy diagnostic."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ASSEMBLER = HERE / "make_bundle.sh"
BOOT_VERIFY = HERE / "verify_boot.mjs"
NODE = ROOT / "tools/emsdk/node/22.16.0_64bit/bin/node"


def run(
    args: list[str | Path],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    expected: int = 0,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(value) for value in args],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != expected:
        raise AssertionError(
            f"command returned {result.returncode}, expected {expected}: {args!r}\n"
            f"{result.stdout}"
        )
    return result


class DeployPortabilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_context = tempfile.TemporaryDirectory(prefix="bw-deploy-portability-")
        self.temp = Path(self.temp_context.name)
        self.fake_root = self.temp / "repo"
        self.fake_here = self.fake_root / "sandbox/m8-deploy"
        self.fake_shell = self.fake_root / "platform_web/shell"
        self.fake_here.mkdir(parents=True)
        self.fake_shell.mkdir(parents=True)
        shutil.copy2(ROOT / "GOAL.md", self.fake_root / "GOAL.md")
        shutil.copy2(ASSEMBLER, self.fake_here / ASSEMBLER.name)
        shutil.copy2(HERE / "_headers", self.fake_here / "_headers")
        for name in (
            "windowed.html",
            "diagnostics-bootstrap.js",
            "boot-windowed.js",
            "file-bridge.js",
            "wgpu-preinit-worker.js",
        ):
            shutil.copy2(ROOT / "platform_web/shell" / name, self.fake_shell / name)
        (self.fake_shell / "fonts").mkdir()
        shutil.copy2(
            ROOT / "platform_web/shell/fonts/bw-interface-sans.woff2",
            self.fake_shell / "fonts/bw-interface-sans.woff2",
        )
        self.assembler = self.fake_here / ASSEMBLER.name
        self.assembler.chmod(0o755)
        run(["git", "init", "-q"], cwd=self.fake_root)
        run(["git", "add", "."], cwd=self.fake_root)
        run(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-qm",
                "fixture",
            ],
            cwd=self.fake_root,
        )

        self.binary = self.fake_root / "fixture-bin"
        self.binary.mkdir()
        self.payloads = {
            "blender_browser.js": b"console.log('deploy fixture');\n",
            "blender_browser.wasm": b"\x00asm-deploy-fixture\n",
            "blender_browser.data": b"deploy-data-fixture\n",
        }
        for name, payload in self.payloads.items():
            (self.binary / name).write_bytes(payload)

    def tearDown(self) -> None:
        self.temp_context.cleanup()

    def test_assembly_selfcheck_is_rooted_and_write_free(self) -> None:
        before = sorted(path.name for path in self.temp.iterdir())
        root = run([ASSEMBLER, "--selfcheck"])
        caller = self.temp / "caller"
        caller.mkdir()
        descendant = run([ASSEMBLER, "--selfcheck"], cwd=caller)
        marker = (
            "M8_DEPLOY_ASSEMBLY_SELFCHECK_PASS "
            "root=derived shell_sources=6 writes=0"
        )
        self.assertIn(marker, root.stdout)
        self.assertIn(marker, descendant.stdout)
        self.assertEqual(
            sorted(before + ["caller"]),
            sorted(path.name for path in self.temp.iterdir()),
        )

    def test_copy_bundle_has_current_shell_and_portable_manifest(self) -> None:
        output = self.fake_here / "bundle-copy"
        result = run(
            [self.assembler, "--copy", "--bin", self.binary, "--out", output]
        )
        expected = {
            "BUNDLE_MANIFEST.txt",
            "_headers",
            "boot-windowed.js",
            "diagnostics-bootstrap.js",
            "file-bridge.js",
            "fonts/bw-interface-sans.woff2",
            "index.html",
            "wgpu-preinit-worker.js",
            "bin/blender_browser.data",
            "bin/blender_browser.js",
            "bin/blender_browser.wasm",
        }
        actual = {
            str(path.relative_to(output))
            for path in output.rglob("*")
            if path.is_file()
        }
        self.assertEqual(expected, actual)
        for name, payload in self.payloads.items():
            artifact = output / "bin" / name
            self.assertFalse(artifact.is_symlink())
            self.assertEqual(payload, artifact.read_bytes())
        total = sum(len(payload) for payload in self.payloads.values())
        manifest = (output / "BUNDLE_MANIFEST.txt").read_text(encoding="utf-8")
        self.assertIn("diagnostics-bootstrap.js", manifest)
        self.assertIn("file-bridge.js", manifest)
        self.assertIn(f"payload total (js+wasm+data): {total} bytes", manifest)
        self.assertIn("+00:00", manifest)
        self.assertIn("mode=copy", result.stdout)

    def test_descendant_relative_paths_make_valid_symlinks(self) -> None:
        caller = self.temp / "nested" / "caller"
        caller.mkdir(parents=True)
        output = self.fake_here / "bundle-link"
        relative_bin = os.path.relpath(self.binary, caller)
        relative_output = os.path.relpath(output, caller)
        result = run(
            [
                self.assembler,
                "--bin",
                relative_bin,
                "--out",
                relative_output,
            ],
            cwd=caller,
        )
        for name in ("blender_browser.wasm", "blender_browser.data"):
            artifact = output / "bin" / name
            self.assertTrue(artifact.is_symlink())
            self.assertEqual(self.binary / name, artifact.resolve())
            self.assertEqual(self.payloads[name], artifact.read_bytes())
        self.assertFalse((output / "bin/blender_browser.js").is_symlink())
        self.assertIn("mode=symlink", result.stdout)

    def test_replacement_is_confined_and_missing_input_preserves_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bw-deploy-outside-") as outside_raw:
            outside = Path(outside_raw)
            sentinel = outside / "sentinel"
            sentinel.write_text("keep", encoding="utf-8")
            result = run(
                [self.assembler, "--bin", self.binary, "--out", outside], expected=1
            )
            self.assertIn("--out must be a generated bundle path", result.stdout)
            self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))

        existing = self.fake_here / "bundle-preserved-output"
        existing.mkdir()
        sentinel = existing / "sentinel"
        sentinel.write_text("keep", encoding="utf-8")
        result = run(
            [
                self.assembler,
                "--bin",
                self.fake_root / "missing-bin",
                "--out",
                existing,
            ],
            expected=1,
        )
        self.assertIn("gate build artifact missing", result.stdout)
        self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))

    def test_boot_selfcheck_is_browser_free_from_root_and_descendant(self) -> None:
        self.assertTrue(NODE.is_file(), f"pinned Node is missing: {NODE}")
        clean_env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"BW_NODE_MODULES", "NODE_PATH"}
        }
        root = run([NODE, BOOT_VERIFY, "--selfcheck"], env=clean_env)
        caller = self.temp / "boot-caller"
        caller.mkdir()
        descendant = run(
            [NODE, BOOT_VERIFY, "--selfcheck"], cwd=caller, env=clean_env
        )
        marker = "M8_DEPLOY_BOOT_SELFCHECK_PASS"
        for result in (root, descendant):
            self.assertIn(marker, result.stdout)
            self.assertIn("root=derived", result.stdout)
            self.assertIn("browser_launches=0", result.stdout)
            self.assertIn('browser_args=["--enable-unsafe-webgpu"]', result.stdout)

        for source_path in (ASSEMBLER, BOOT_VERIFY):
            source = source_path.read_text(encoding="utf-8")
            self.assertNotIn("/Users/" + "paws", source)
            self.assertNotIn("/opt/" + "homebrew", source)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DeployPortabilityTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print(
            "M8_DEPLOY_PORTABILITY_TEST_PASS tests=5 assemblies=2 "
            "browser_launches=0"
        )
    raise SystemExit(0 if result.wasSuccessful() else 1)
