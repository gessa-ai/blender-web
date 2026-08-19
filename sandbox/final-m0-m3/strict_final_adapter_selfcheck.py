#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hermetic adversarial self-check for the strict harness receipt adapter."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import strict_final_adapter as adapter


LABEL = "final-adapter-fixture-r1"


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    path.write_text(payload, encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(root: Path, path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def fixture(root: Path) -> tuple[Path, dict[str, object], dict[str, Path]]:
    receipts = root / "evidence/receipts"
    values = {
        "m0": {"scope": "m0"},
        "m1": {
            "gtests": {
                "blenlib": {"total": 1667, "passed": 1667, "failed": 0, "crashed": 0},
                "bmesh_core": {"total": 1, "passed": 1, "failed": 0, "crashed": 0},
            },
            "main_corpus": {"total": 9, "equal": 9},
            "versioning": {"total": 12, "pass": 10, "oracle_refuse": 2, "equal": 12},
        },
        "m2": {"total": 75, "rows": {f"suite-{number:02d}": {"result": "PASS"} for number in range(75)}},
        "m2_deps": {"scope": "m2_deps"},
        "m3": {
            "gpu_tests": {"total": 197, "passed": 197, "failed": 0, "crashed": 0},
            "draw_webgpu_tests": {"total": 2, "passed": 2, "failed": 0, "crashed": 0},
            "static_shaders": {
                "total": adapter.M3_SHADER_COUNT,
                "passed": adapter.M3_SHADER_COUNT,
                "excluded": 0,
                "failed": 0,
            },
        },
    }
    paths: dict[str, Path] = {}
    for name, value in values.items():
        paths[name] = receipts / f"{name}.json"
        write(paths[name], value)
    manifest = root / f"sandbox/final-m0-m3/evidence/{LABEL}/final-m0-m3.json"
    value: dict[str, object] = {
        "schema": 1,
        "verdict": "PASS",
        "run_label": LABEL,
        "created_utc": "2026-08-15T00:00:01Z",
        "source_tree": "upstream",
        "source_freeze": {},
        "receipts": {name: ref(root, path) for name, path in paths.items()},
    }
    write(manifest, value)
    verifier = root / "sandbox/final-m0-m3/verify.py"
    write(verifier, """#!/usr/bin/env python3
import hashlib,json,os,pathlib,sys
args=sys.argv; manifest=pathlib.Path(args[args.index('--manifest')+1]); value=json.loads(manifest.read_text())
mode=os.environ.get('STRICT_ADAPTER_FIXTURE_MODE','pass')
if mode == 'red': print('fixture red',file=sys.stderr); raise SystemExit(1)
hashes={name: row['sha256'] for name,row in value['receipts'].items()}
if mode == 'hash-mismatch': hashes['m1']='b'*64
print(json.dumps({'schema':1,'verdict':'PASS','run_label':value['run_label'],
 'source_freeze_sha256':'a'*64,'receipt_sha256':hashes,'contracts':{}}))
""")
    verifier.chmod(0o755)
    return manifest, value, paths


def reject(callback, token: str, negatives: list[str]) -> None:
    try:
        callback()
    except adapter.AdapterError:
        negatives.append(token)
    else:
        raise AssertionError(f"negative accepted: {token}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="strict-final-adapter-") as raw:
        root = Path(raw).resolve()
        manifest, value, paths = fixture(root)
        positives = {
            scope: adapter.verify_scope(root, manifest, LABEL, scope, 86400)
            for scope in ("m1", "m2b", "m3")
        }
        negatives: list[str] = []

        m3_original = paths["m3"].read_bytes()
        manifest_original = manifest.read_bytes()
        stale_m3 = json.loads(m3_original)
        stale_m3["gpu_tests"].update({"total": 196, "passed": 196})
        write(paths["m3"], stale_m3)
        stale_manifest = copy.deepcopy(value)
        stale_manifest["receipts"]["m3"] = ref(root, paths["m3"])  # type: ignore[index]
        write(manifest, stale_manifest)
        reject(lambda: adapter.verify_scope(root, manifest, LABEL, "m3", 86400),
               "m3_stale_196_census", negatives)
        paths["m3"].write_bytes(m3_original)
        manifest.write_bytes(manifest_original)

        stale_draw = json.loads(m3_original)
        stale_draw["draw_webgpu_tests"].update({"passed": 1, "failed": 1})
        write(paths["m3"], stale_draw)
        stale_draw_manifest = copy.deepcopy(value)
        stale_draw_manifest["receipts"]["m3"] = ref(root, paths["m3"])  # type: ignore[index]
        write(manifest, stale_draw_manifest)
        reject(lambda: adapter.verify_scope(root, manifest, LABEL, "m3", 86400),
               "m3_draw_webgpu_not_2_pass", negatives)
        paths["m3"].write_bytes(m3_original)
        manifest.write_bytes(manifest_original)

        reject(lambda: adapter.verify_scope(root, manifest, "wrong-label", "m1", 86400),
               "wrong_run_label", negatives)
        outside = root.parent / f"{root.name}-outside.json"
        write(outside, value)
        try:
            reject(lambda: adapter.verify_scope(root, outside, LABEL, "m1", 86400),
                   "manifest_escape", negatives)
        finally:
            outside.unlink()

        real = manifest.with_name("real.json")
        manifest.rename(real)
        manifest.symlink_to(real.name)
        reject(lambda: adapter.verify_scope(root, manifest, LABEL, "m1", 86400),
               "manifest_symlink", negatives)
        manifest.unlink()
        real.rename(manifest)

        original = paths["m1"].read_bytes()
        paths["m1"].write_bytes(original + b" ")
        reject(lambda: adapter.verify_scope(root, manifest, LABEL, "m1", 86400),
               "receipt_byte_tamper", negatives)
        paths["m1"].write_bytes(original)

        mutated = copy.deepcopy(value)
        mutated["receipts"]["unlisted"] = mutated["receipts"]["m1"]  # type: ignore[index]
        write(manifest, mutated)
        reject(lambda: adapter.verify_scope(root, manifest, LABEL, "m1", 86400),
               "extra_receipt_key", negatives)
        write(manifest, value)

        os.environ["STRICT_ADAPTER_FIXTURE_MODE"] = "hash-mismatch"
        reject(lambda: adapter.verify_scope(root, manifest, LABEL, "m1", 86400),
               "verifier_hash_mismatch", negatives)
        os.environ["STRICT_ADAPTER_FIXTURE_MODE"] = "red"
        reject(lambda: adapter.verify_scope(root, manifest, LABEL, "m1", 86400),
               "verifier_red", negatives)
        os.environ.pop("STRICT_ADAPTER_FIXTURE_MODE", None)

        # Exercise the real shell integration in the fixture. Each scope must
        # write one honest green ledger from the same strict candidate without
        # touching any raw tier-b/GPU evidence.
        harness = root / "harness/run.sh"
        harness.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(adapter.ROOT / "harness/run.sh", harness)
        shutil.copy2(Path(adapter.__file__), root / "sandbox/final-m0-m3/strict_final_adapter.py")
        env = os.environ.copy()
        env.update({
            "FINAL_RUN_LABEL": LABEL,
            "FINAL_M0_M3_MANIFEST": os.fspath(manifest),
        })
        ledgers: dict[str, bool] = {}
        for scope in ("m1", "m2b", "m3"):
            result = subprocess.run(
                ["bash", os.fspath(harness), "--scope", scope], cwd=root,
                env=env, text=True, capture_output=True, check=False,
            )
            if result.returncode != 0:
                raise AssertionError(f"harness {scope} did not pass: {result.stdout}{result.stderr}")
            ledger = json.loads((root / f"ledger/results/{scope}.json").read_text())
            ledgers[scope] = ledger.get("scope") == scope and ledger.get("pass") is True
        if not all(ledgers.values()):
            raise AssertionError(f"harness wrote a non-green strict ledger: {ledgers}")

        missing_env = env.copy()
        missing_env.pop("FINAL_M0_M3_MANIFEST")
        red = subprocess.run(
            ["bash", os.fspath(harness), "--scope", "m1"], cwd=root,
            env=missing_env, text=True, capture_output=True, check=False,
        )
        if red.returncode == 0:
            raise AssertionError("harness accepted missing final manifest environment")
        negatives.append("harness_missing_manifest_red")

        print(json.dumps({
            "schema": 1,
            "verdict": "PASS",
            "positive_scopes": sorted(positives),
            "green_harness_ledgers": ledgers,
            "negative": negatives,
        }, sort_keys=True))


if __name__ == "__main__":
    main()
