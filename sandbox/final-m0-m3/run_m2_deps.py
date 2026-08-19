#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Emit strict dependency inventory/compliance evidence from an exact path map."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = Path(__file__).resolve().parent / "evidence"
CANONICAL_SPEC = Path(__file__).resolve().parent / "m2_dependency_inventory.json"
LABEL_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,79}")


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


def resolve(raw: Any, where: str) -> Path:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        fail(f"{where}: invalid POSIX path")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        fail(f"{where}: unsafe path")
    path = ROOT.joinpath(*pure.parts)
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(ROOT)
    except ValueError:
        fail(f"{where}: path escapes repository")
    if path.is_symlink() or not resolved.is_file():
        fail(f"{where}: expected non-symlink file")
    return resolved


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


def require_dependency_notice_source(name: str, ledger_row: dict[str, Any]) -> tuple[str, str]:
    """Require provenance even for skipped, unshipped, or non-runtime rows."""
    notice = ledger_row.get("license_note", ledger_row.get("notes"))
    source = ledger_row.get("source")
    if not isinstance(notice, str) or not notice or not isinstance(source, str) or not source:
        fail(f"dependency notice/source is missing: {name}")
    return notice, source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--freeze-receipt", type=Path, required=True)
    parser.add_argument("--inventory-spec", type=Path, default=CANONICAL_SPEC,
                        help="canonical schema-1 dependency artifact/license map")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if LABEL_RE.fullmatch(args.run_label) is None:
            fail("unsafe run label")
        output = OUTPUT_ROOT / args.run_label / "m2-deps"
        if output.exists() or output.is_symlink():
            fail(f"refusing to overwrite M2-deps attempt: {output}")
        output.mkdir(parents=True)
        incomplete = output / "INCOMPLETE"
        incomplete.write_text("M2-deps inventory in progress\n", encoding="utf-8")
        freeze = json.loads(args.freeze_receipt.read_text(encoding="utf-8"))
        if freeze.get("schema") != 1 or freeze.get("verdict") != "PASS":
            fail("source freeze is not schema-1 PASS")
        if Path(str(freeze.get("source", ""))).resolve() != (ROOT / "upstream").resolve():
            fail("source freeze does not identify the canonical upstream source root")
        freeze_hash = sha256(args.freeze_receipt)
        deps_path = ROOT / "ledger/deps.json"
        ledger = json.loads(deps_path.read_text(encoding="utf-8"))
        built = ledger.get("wasm_built") if isinstance(ledger, dict) else None
        if not isinstance(built, dict) or not built:
            fail("dependency ledger has no wasm_built map")
        spec_path = args.inventory_spec.resolve(strict=True)
        if spec_path != CANONICAL_SPEC.resolve() or args.inventory_spec.is_symlink():
            fail("inventory spec is not the canonical freeze-bound technical input")
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        if not isinstance(spec, dict) or set(spec) != {"schema", "dependencies"} or spec["schema"] != 1:
            fail("inventory spec is not exact schema-1")
        mapped = spec["dependencies"]
        if not isinstance(mapped, dict) or set(mapped) != set(built):
            fail("inventory spec keyset differs from wasm_built ledger")
        dependencies: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        artifact_names: set[str] = set()
        for name in sorted(built):
            ledger_row = built[name]
            item = mapped[name]
            if not isinstance(ledger_row, dict) or not isinstance(item, dict) or set(item) != {
                "runtime_linked", "artifacts", "license_payloads"
            }:
                fail(f"dependency map row malformed: {name}")
            if not isinstance(ledger_row.get("gpl_compatible"), bool):
                fail(f"dependency compatibility is not explicit boolean: {name}")
            if not isinstance(item["runtime_linked"], bool) or not isinstance(item["artifacts"], list):
                fail(f"dependency runtime/artifact classification malformed: {name}")
            artifacts = [resolve(raw, f"{name}.artifacts") for raw in item["artifacts"]]
            if item["runtime_linked"] and not artifacts:
                fail(f"runtime-linked dependency has no artifact: {name}")
            for path in artifacts:
                relative = path.relative_to(ROOT).as_posix()
                if relative in artifact_names:
                    fail(f"dependency artifact assigned more than once: {relative}")
                artifact_names.add(relative)
            payload_raw = item["license_payloads"]
            if not isinstance(payload_raw, list) or not payload_raw:
                fail(f"dependency has no license payload: {name}")
            payloads = [resolve(raw, f"{name}.license_payloads") for raw in payload_raw]
            for path in payloads:
                relative = path.relative_to(ROOT).as_posix()
                if (not relative.startswith("LICENSES/") and "/share/licenses/" not in relative
                        and not relative.startswith("THIRD_PARTY_NOTICES/")
                        and not relative.startswith("upstream/release/license/")
                        and not relative.startswith("lib/wasm/share/doc/")
                        and not relative.startswith("lib/wasm/lib/python3.13/")):
                    fail(f"unapproved dependency license payload path: {relative}")
            if len(payloads) != len(set(payloads)):
                fail(f"duplicate dependency license payload: {name}")
            notice, source = require_dependency_notice_source(name, ledger_row)
            row = {
                "name": name, "version": ledger_row.get("version"),
                "license": ledger_row.get("license"),
                "gpl_compatible": ledger_row["gpl_compatible"],
                "runtime_linked": item["runtime_linked"],
                "notice": notice, "source": source,
                "license_payloads": [ref(path) for path in payloads],
                "artifacts": [ref(path) for path in artifacts],
            }
            dependencies.append(row)
            if ledger_row["gpl_compatible"] is False:
                reason = ledger_row.get("gpl_compatible_note")
                if not isinstance(reason, str) or not reason:
                    fail(f"false compatibility lacks external-policy reason: {name}")
                unresolved.append({
                    "name": name, "license": row["license"], "reason": reason,
                    "license_payloads": row["license_payloads"],
                })
        static_roots = (
            ROOT / "lib/wasm/lib", ROOT / "lib/wasm/shaderc/lib", ROOT / "lib/wasm/tint/lib"
        )
        current_archives = {
            path.relative_to(ROOT).as_posix()
            for directory in static_roots for path in directory.glob("*.a")
            if path.is_file() and not path.is_symlink()
        }
        mapped_archives = {name for name in artifact_names if name.endswith(".a")}
        if mapped_archives != current_archives:
            fail("canonical inventory does not exactly enumerate current non-symlink static archives")
        inventory = output / "inventory.manifest"
        with inventory.open("x", encoding="utf-8") as stream:
            for name in sorted(artifact_names):
                stream.write(name + "\n")
        reuse = subprocess.run(["reuse", "lint", "-j"], cwd=ROOT, text=True,
                               capture_output=True, check=False)
        (output / "reuse.stdout.json").write_text(reuse.stdout, encoding="utf-8")
        (output / "reuse.stderr").write_text(reuse.stderr, encoding="utf-8")
        try:
            reuse_doc = json.loads(reuse.stdout)
        except json.JSONDecodeError:
            reuse_doc = {}
        summary = reuse_doc.get("summary", {}) if isinstance(reuse_doc, dict) else {}
        violations = 0 if summary.get("compliant") is True else 1
        if reuse.returncode != 0 or violations:
            fail(f"REUSE compliance is red rc={reuse.returncode}")
        compliance = write_json(output / "compliance.json", {
            "schema": 1, "verdict": "PASS", "run_label": args.run_label,
            "source_freeze_sha256": freeze_hash, "reuse_exit_code": 0, "violations": 0,
            "deps_ledger_sha256": sha256(deps_path), "inventory_sha256": sha256(inventory),
            "inventory_spec_sha256": sha256(spec_path),
        })
        stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        receipt = write_json(output / "receipt.json", {
            "schema": 1, "verdict": "PASS", "run_label": args.run_label,
            "created_utc": stamp, "source_freeze_sha256": freeze_hash,
            "deps_ledger": ref(deps_path), "inventory_spec": ref(spec_path),
            "inventory_manifest": ref(inventory),
            "compliance_proof": ref(compliance), "unlisted_artifacts": 0,
            "missing_artifacts": 0, "dependencies": dependencies,
            "unresolved_external_policy": unresolved,
            "external_policy_pass": not unresolved,
        })
        incomplete.unlink()
        print("FINAL_M2_DEPS_PASS "
              f"receipt={receipt.relative_to(ROOT)} sha256={sha256(receipt)} "
              f"external_policy_pass={str(not unresolved).lower()} unresolved={len(unresolved)}")
        return 0
    except (RunError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"FINAL_M2_DEPS_FAIL {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
