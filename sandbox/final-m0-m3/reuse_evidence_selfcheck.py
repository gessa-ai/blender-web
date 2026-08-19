#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hermetically prove strict generated-evidence REUSE annotations."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FINAL_EVIDENCE_ROOTS = (
    "sandbox/final-m0-m3/evidence",
    "sandbox/final-m0-m6/evidence",
)
GENERATED_PATHS = (
    "sandbox/final-m0-m3/evidence/nested-r1/m0/INCOMPLETE",
    "sandbox/final-m0-m3/evidence/nested-r1/m0/container.stdout",
    "sandbox/final-m0-m3/evidence/nested-r1/m0/container.stderr",
    "sandbox/final-m0-m6/evidence/nested-r1/deep/verifier.stdout",
    "sandbox/final-m0-m6/evidence/nested-r1/deep/verifier.stderr",
)
THIRD_PARTY_PATH = "third-party-browser-profile/Cache/data_0"


class SelfcheckError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise SelfcheckError(message)


def run_reuse(root: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    try:
        result = subprocess.run(
            ["reuse", "lint", "-j"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        fail(f"could not execute reuse lint: {error}")
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        fail(f"reuse lint emitted invalid JSON: {error}")
    if not isinstance(document, dict):
        fail("reuse lint JSON is not an object")
    return result, document


def paths_with_complete_cc0(document: dict[str, Any]) -> set[str]:
    complete: set[str] = set()
    rows = document.get("files")
    if not isinstance(rows, list):
        fail("reuse lint JSON lacks a files array")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            fail("reuse lint files array contains a malformed row")
        copyrights = row.get("copyrights")
        expressions = row.get("spdx_expressions")
        if not isinstance(copyrights, list) or not isinstance(expressions, list):
            continue
        if any(
            isinstance(item, dict)
            and item.get("value") == "SPDX-FileCopyrightText: 2026 blender-web contributors"
            and item.get("source") == "REUSE.toml"
            for item in copyrights
        ) and any(
            isinstance(item, dict)
            and item.get("value") == "CC0-1.0"
            and item.get("is_valid") is True
            and item.get("source") == "REUSE.toml"
            for item in expressions
        ):
            complete.add(row["path"])
    return complete


def main() -> int:
    try:
        source_config = ROOT / "REUSE.toml"
        config_text = source_config.read_text(encoding="utf-8")
        for evidence_root in FINAL_EVIDENCE_ROOTS:
            exact = f'"{evidence_root}/**"'
            if config_text.count(exact) != 1:
                fail(f"REUSE.toml must contain exactly one annotation for {evidence_root}/**")
        forbidden = (
            "third-party-browser-profile/**",
            "sandbox/m8-launch-gate/.browsers/**",
            ".m8-browsers/**",
            ".m8-soak-profile/**",
        )
        if any(pattern in config_text for pattern in forbidden):
            fail("REUSE.toml must not annotate browser/profile third-party trees")

        with tempfile.TemporaryDirectory(prefix="reuse-final-evidence-selfcheck-") as name:
            fixture = Path(name)
            shutil.copy2(source_config, fixture / "REUSE.toml")
            licenses = fixture / "LICENSES"
            licenses.mkdir()
            for license_name in ("CC0-1.0.txt",):
                shutil.copy2(ROOT / "LICENSES" / license_name, licenses / license_name)
            for relative in GENERATED_PATHS:
                path = fixture / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"generated fixture: {relative}\n".encode("utf-8"))

            positive, positive_doc = run_reuse(fixture)
            summary = positive_doc.get("summary")
            if (
                positive.returncode != 0
                or not isinstance(summary, dict)
                or summary.get("compliant") is not True
            ):
                fail(
                    "annotated final evidence is not REUSE compliant: "
                    f"rc={positive.returncode} stderr={positive.stderr.strip()!r} "
                    f"non_compliant={positive_doc.get('non_compliant')!r}"
                )
            complete = paths_with_complete_cc0(positive_doc)
            if not set(GENERATED_PATHS) <= complete:
                missing = sorted(set(GENERATED_PATHS) - complete)
                fail(f"generated evidence lacks exact REUSE.toml CC0 coverage: {missing}")

            third_party = fixture / THIRD_PARTY_PATH
            third_party.parent.mkdir(parents=True)
            third_party.write_bytes(b"opaque third-party browser cache bytes\x00\x01")
            negative, negative_doc = run_reuse(fixture)
            negative_summary = negative_doc.get("summary")
            non_compliant = negative_doc.get("non_compliant")
            if (
                negative.returncode == 0
                or not isinstance(negative_summary, dict)
                or negative_summary.get("compliant") is not False
                or not isinstance(non_compliant, dict)
            ):
                fail("unannotated third-party binary did not make REUSE lint fail closed")
            missing_copyright = non_compliant.get("missing_copyright_info")
            missing_license = non_compliant.get("missing_licensing_info")
            reported_third_party = str(third_party.resolve())
            if (
                not isinstance(missing_copyright, list)
                or not isinstance(missing_license, list)
                or reported_third_party not in missing_copyright
                or reported_third_party not in missing_license
            ):
                fail(
                    "negative REUSE result does not identify the third-party binary exactly: "
                    f"{non_compliant!r}"
                )

        print(
            "REUSE_EVIDENCE_SELFCHECK_PASS "
            f"generated={len(GENERATED_PATHS)} third_party_negative=1"
        )
        return 0
    except (SelfcheckError, OSError) as error:
        print(f"REUSE_EVIDENCE_SELFCHECK_FAIL {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
