#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run and emit strict M0 toolchain/container/REUSE evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = Path(__file__).resolve().parent / "evidence"
LABEL_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,79}")
ARTIFACTS = {
    "blender_web_cmake": "patches/blender_web.cmake", "buildwrap": "harness/buildwrap.sh",
    "ci_workflow": ".github/workflows/m0.yml", "deps_ledger": "ledger/deps.json",
    "deferred_ledger": "ledger/deferred.json", "m0_selfcheck": "scripts/m0-selfcheck.py",
    "ninja_locked": "scripts/ninja-locked.sh",
    "oracle_receipt": "scripts/m0-oracle-receipt.py", "oracle_dockerfile": "containers/oracle/Dockerfile",
    "oracle_pin": "oracle/PIN", "oracle_toolchain": "oracle/TOOLCHAIN",
    "oracle_wrapper": "scripts/oracle-container.sh", "native_oracle": "oracle/bpy.sh",
    "reuse_config": "reuse.toml",
}


class RunError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise RunError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ref(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    return {"path": resolved.relative_to(ROOT).as_posix(), "bytes": resolved.stat().st_size,
            "sha256": sha256(resolved)}


def write_json(path: Path, value: Any) -> Path:
    if path.exists() or path.is_symlink():
        fail(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--freeze-receipt", type=Path, required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if LABEL_RE.fullmatch(args.run_label) is None:
            fail("unsafe run label")
        output = OUTPUT_ROOT / args.run_label / "m0"
        if output.exists() or output.is_symlink():
            fail(f"refusing to overwrite M0 attempt: {output}")
        output.mkdir(parents=True)
        incomplete = output / "INCOMPLETE"
        incomplete.write_text("M0 execution in progress\n", encoding="utf-8")
        reuse_selfcheck = subprocess.run(
            [sys.executable, "sandbox/final-m0-m3/reuse_evidence_selfcheck.py"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        (output / "reuse-evidence-selfcheck.stdout").write_text(
            reuse_selfcheck.stdout, encoding="utf-8"
        )
        (output / "reuse-evidence-selfcheck.stderr").write_text(
            reuse_selfcheck.stderr, encoding="utf-8"
        )
        if reuse_selfcheck.returncode != 0:
            fail(f"REUSE evidence selfcheck failed rc={reuse_selfcheck.returncode}")
        freeze = json.loads(args.freeze_receipt.read_text(encoding="utf-8"))
        if freeze.get("schema") != 1 or freeze.get("verdict") != "PASS":
            fail("source freeze is not schema-1 PASS")
        freeze_hash = sha256(args.freeze_receipt)
        static = subprocess.run([sys.executable, "scripts/m0-selfcheck.py"], cwd=ROOT,
                                text=True, capture_output=True, check=False)
        (output / "m0-selfcheck.stdout").write_text(static.stdout, encoding="utf-8")
        (output / "m0-selfcheck.stderr").write_text(static.stderr, encoding="utf-8")
        if static.returncode != 0:
            fail(f"M0 static selfcheck failed rc={static.returncode}")
        container_proof = output / "container.json"
        container = subprocess.run(
            [sys.executable, "scripts/m0-oracle-receipt.py", "--label", args.run_label,
             "--output", str(container_proof)], cwd=ROOT, text=True,
            capture_output=True, check=False,
        )
        (output / "container.stdout").write_text(container.stdout, encoding="utf-8")
        (output / "container.stderr").write_text(container.stderr, encoding="utf-8")
        if container.returncode != 0 or not container_proof.is_file():
            fail(f"M0 oracle container execution failed rc={container.returncode}")
        proof = json.loads(container_proof.read_text(encoding="utf-8"))
        if (proof.get("schema"), proof.get("verdict"), proof.get("run_label"),
                proof.get("exit_code")) != (1, "PASS", args.run_label, 0):
            fail("M0 container proof is not exact PASS")
        image_digest = proof.get("image_digest")
        if not isinstance(image_digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest) is None:
            fail("M0 container is not digest-pinned")
        reuse = subprocess.run(["reuse", "lint", "-j"], cwd=ROOT, text=True,
                               capture_output=True, check=False)
        (output / "reuse.stdout.json").write_text(reuse.stdout, encoding="utf-8")
        (output / "reuse.stderr").write_text(reuse.stderr, encoding="utf-8")
        try:
            reuse_doc = json.loads(reuse.stdout)
        except json.JSONDecodeError:
            reuse_doc = {}
        summary = reuse_doc.get("summary", {}) if isinstance(reuse_doc, dict) else {}
        if reuse.returncode != 0 or summary.get("compliant") is not True:
            fail(f"REUSE lint failed rc={reuse.returncode}")
        reuse_proof = write_json(output / "reuse.json", {
            "schema": 1, "verdict": "PASS", "run_label": args.run_label,
            "source_freeze_sha256": freeze_hash,
            "reuse_config_sha256": sha256(ROOT / "reuse.toml"),
            "exit_code": 0, "violations": 0,
        })
        stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        receipt = write_json(output / "receipt.json", {
            "schema": 1, "verdict": "PASS", "run_label": args.run_label,
            "created_utc": stamp, "source_freeze_sha256": freeze_hash,
            "pins": {
                "blender": {"branch": "blender-v5.2-release", "commit": "fbe6228777e7d9afefcd61a413844e790ae75db7"},
                "emsdk": {"version": "6.0.5", "release_commit": "dbd755b5da399329c2576f6e3dfa7f419f5d8409",
                          "repo_commit": "1ab2e627b1a84567f5284d1baaa5f6be7ccf07de",
                          "compiler_commit": "1db513782be24469589d7cb8a1f1834e9a33f271"},
                "oracle": {"version": "5.2.0", "commit": "fbe6228777e7d9afefcd61a413844e790ae75db7"},
            },
            "artifacts": {name: ref(ROOT / path) for name, path in ARTIFACTS.items()},
            "container": {"image_digest": image_digest, "proof": ref(container_proof)},
            "ci": {"em_cache": True, "ccache": True, "reuse_lint": True,
                   "pinned_actions": True, "static_selfcheck": True, "runtime_check": True},
            "reuse": {"proof": ref(reuse_proof), "exit_code": 0, "violations": 0},
        })
        incomplete.unlink()
        print(f"FINAL_M0_RAW_PASS receipt={receipt.relative_to(ROOT)} sha256={sha256(receipt)}")
        return 0
    except (RunError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"FINAL_M0_RAW_FAIL {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
