#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the public parity/deferral page from a reproducible source view."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

RESULT_SPECS = (
    ("M0", "Toolchain + native oracle", "ledger/results/m0.json"),
    ("M1", "Core boot + tier-(a) oracle", "ledger/results/m1.json"),
    ("M2", "Dependencies + Python boot", "ledger/results/m2b.json"),
    ("M3", "WebGPU backend", "ledger/results/m3.json"),
    ("M4", "First pixels in a browser tab", "ledger/results/m4.json"),
    ("M5", "Interactive parity", "ledger/results/m5.json"),
    ("M6", "Render parity", "ledger/results/m6.json"),
    ("M7", "Files + staged pipeline", "ledger/results/m7.json"),
    ("M8", "Technical release package", "ledger/results/m8.json"),
)

INPUT_PATHS = (
    "oracle/PIN",
    *(path for _milestone, _name, path in RESULT_SPECS),
    "ledger/deferred.json",
    "ledger/deps.json",
    "notes/gpu-gate-census.md",
    "scripts/public-dashboard.py",
)

PRIVATE_PATTERNS = (
    re.compile(r"(?:^|[\s('`\"])/(?:home|Users|mnt)/", re.IGNORECASE),
    re.compile(r"(?:^|[\s('`\"])/private/", re.IGNORECASE),
    re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
    re.compile(r"(?:^|\s)~/"),
    re.compile(r"\bornith-lab\b", re.IGNORECASE),
    re.compile(r"\bbw-logs\b", re.IGNORECASE),
    re.compile(r"\bpaws\b", re.IGNORECASE),
)


class PublicDataError(RuntimeError):
    """A source value is unsafe or structurally invalid for public output."""


class SourceView:
    """Read files from the worktree, Git index, or an immutable Git revision."""

    def __init__(self, mode: str):
        self.mode = mode

    def read_bytes(self, path: str) -> bytes | None:
        if self.mode == "worktree":
            try:
                return (ROOT / path).read_bytes()
            except OSError:
                return None

        spec = f":{path}" if self.mode == "index" else f"{self.mode}:{path}"
        proc = subprocess.run(
            ["git", "show", spec],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
        return proc.stdout if proc.returncode == 0 else None

    def read_text(self, path: str) -> str | None:
        data = self.read_bytes(path)
        if data is None:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def read_json(self, path: str) -> Any | None:
        text = self.read_text(path)
        if text is None:
            return None
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return None


def public_cell(value: object, *, fallback: str = "unavailable") -> str:
    """Normalize a public table cell and reject private machine metadata."""
    if value is None:
        return fallback
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text:
        return fallback
    for pattern in PRIVATE_PATTERNS:
        if pattern.search(text):
            raise PublicDataError(f"private machine metadata rejected: {pattern.pattern}")
    return text.replace("|", r"\|")


def input_digest(source: SourceView) -> str:
    digest = hashlib.sha256()
    for path in sorted(INPUT_PATHS):
        digest.update(path.encode("utf-8") + b"\0")
        data = source.read_bytes(path)
        digest.update(data if data is not None else b"<unavailable>")
        digest.update(b"\0")
    return digest.hexdigest()


def receipt_row(source: SourceView, milestone: str, name: str, path: str) -> tuple[str, ...]:
    doc = source.read_json(path)
    if not isinstance(doc, dict) or not isinstance(doc.get("checks"), dict):
        return milestone, name, "UNAVAILABLE", "unavailable", "receipt missing", "unavailable"

    checks = doc["checks"]
    valid_checks = {
        str(key): value
        for key, value in checks.items()
        if isinstance(value, dict) and isinstance(value.get("pass"), bool)
    }
    total = len(checks)
    passing = sum(1 for value in valid_checks.values() if value["pass"] is True)
    complete = len(valid_checks) == total and total > 0
    passed = complete and passing == total and doc.get("pass") is True
    status = "PASS" if passed else "FAIL"
    failed = [public_cell(key) for key, value in valid_checks.items() if not value["pass"]]
    if not complete:
        failed.append("malformed check record")
    failure_cell = ", ".join(failed) if failed else "—"
    return (
        milestone,
        name,
        status,
        f"{passing}/{total} ({(100.0 * passing / total):.1f}%)" if total else "0/0 (0.0%)",
        failure_cell,
        public_cell(doc.get("ts")),
    )


def gpu_component_rows(source: SourceView) -> list[tuple[str, str, str]]:
    census = source.read_text("notes/gpu-gate-census.md")
    if census is None:
        return [
            ("Native WebGPU GPU census", "unavailable", "source unavailable"),
            ("Static shader translation", "unavailable", "source unavailable"),
        ]

    census_match = re.search(
        r"(\d+)\s+tests\b.{0,12}?(\d+)\s+PASS\s*/\s*(\d+)\s+FAIL\s*/\s*(\d+)\s+CRASH",
        census,
    )
    shader_match = re.search(r"(\d+)\s*/\s*(\d+)\s+shaders compile", census)
    rows: list[tuple[str, str, str]] = []
    if census_match:
        total, passed, failed, crashed = (int(value) for value in census_match.groups())
        rows.append(
            (
                "Native WebGPU GPU census",
                f"{passed}/{total} ({100.0 * passed / total:.1f}%)",
                f"{failed} fail / {crashed} crash; dispositions remain in the registry",
            )
        )
    else:
        rows.append(("Native WebGPU GPU census", "unavailable", "count not parseable"))
    if shader_match:
        passed, total = (int(value) for value in shader_match.groups())
        rows.append(
            (
                "Static shader translation",
                f"{passed}/{total} ({100.0 * passed / total:.1f}%)",
                f"{total - passed} non-passing; see named deferrals and blacklist evidence",
            )
        )
    else:
        rows.append(("Static shader translation", "unavailable", "count not parseable"))
    return rows


def deferral_rows(source: SourceView) -> tuple[list[dict[str, Any]], dict[str, int]]:
    doc = source.read_json("ledger/deferred.json")
    if not isinstance(doc, dict) or not isinstance(doc.get("deferred"), list):
        return [], {}

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    tally: dict[str, int] = {}
    for raw in doc["deferred"]:
        if not isinstance(raw, dict):
            raise PublicDataError("deferral registry contains a non-object entry")
        for key in ("id", "status", "blocker", "revisit"):
            if raw.get(key) is None or not str(raw[key]).strip():
                raise PublicDataError(f"deferral registry entry is missing {key}")
        row_id = public_cell(raw.get("id"))
        if row_id == "unavailable" or row_id in seen:
            raise PublicDataError(f"deferral registry id missing or duplicated: {row_id}")
        seen.add(row_id)
        status = public_cell(raw.get("status"))
        row = {
            "id": row_id,
            "status": status,
            "milestone": public_cell(raw.get("milestone")),
            "blocker": public_cell(raw.get("blocker")),
            "revisit": public_cell(raw.get("revisit")),
        }
        rows.append(row)
        tally[status] = tally.get(status, 0) + 1
    return rows, tally


def render_dashboard(source: SourceView) -> str:
    pin = public_cell(source.read_text("oracle/PIN"))
    receipts = [receipt_row(source, *spec) for spec in RESULT_SPECS]
    deferrals, tally = deferral_rows(source)

    pass_count = sum(1 for row in receipts if row[2] == "PASS")
    fail_count = sum(1 for row in receipts if row[2] == "FAIL")
    unavailable_count = sum(1 for row in receipts if row[2] == "UNAVAILABLE")

    deps = source.read_json("ledger/deps.json")
    dep_count = (
        len(deps["wasm_built"])
        if isinstance(deps, dict) and isinstance(deps.get("wasm_built"), dict)
        else None
    )

    lines: list[str] = []
    write = lines.append
    write("<!--")
    write("SPDX-FileCopyrightText: 2026 blender-web contributors")
    write("SPDX-License-" + "Identifier: GPL-3.0-or-later")
    write("")
    write("Generated by scripts/public-dashboard.py from committed receipt and ledger inputs.")
    write("Do not edit by hand. Regenerate: scripts/public-dashboard.py --source HEAD")
    write("-->")
    write("")
    write("# Parity and limitations")
    write("")
    write(
        "This is the public, fail-closed proof page for the browser port. It compares the "
        "current committed receipts with the pinned upstream target; missing or malformed "
        "evidence is shown as `UNAVAILABLE`, never inferred from a demo or an older run."
    )
    write("")
    write(f"Pinned upstream: `{pin}`.")
    write("")
    write(
        "The project is an independent derivative work. Not affiliated with, endorsed by, "
        "or sponsored by the Blender Foundation. Blender® is a registered trademark of the "
        "Blender Foundation. [Preferred-form GPL source](https://github.com/gessa-ai/blender-web)."
    )
    write("")
    write("## Current milestone receipts")
    write("")
    write(
        f"**{pass_count} PASS · {fail_count} FAIL · {unavailable_count} UNAVAILABLE.** "
        "A component result does not promote its milestone; only the strict receipt row does."
    )
    write("")
    write("| Milestone | Scope | Status | Passing checks | Non-passing checks | Receipt time (UTC) |")
    write("|---|---|---|---:|---|---|")
    for milestone, name, status, passing, failed, timestamp in receipts:
        write(
            f"| {milestone} | {public_cell(name)} | {status} | {passing} | "
            f"{failed} | {timestamp} |"
        )
    write("")

    write("## Audited component evidence")
    write("")
    write(
        "These measured component counts add detail, but they do not override a red or "
        "unavailable milestone receipt."
    )
    write("")
    write("| Component | Passing | Non-passing / boundary |")
    write("|---|---:|---|")
    for component, passing, boundary in gpu_component_rows(source):
        write(f"| {public_cell(component)} | {public_cell(passing)} | {public_cell(boundary)} |")
    if dep_count is None:
        write("| Cross-built dependency inventory | unavailable | `ledger/deps.json` unavailable |")
    else:
        write(
            f"| Cross-built dependency inventory | {dep_count} recorded | "
            "License and rationale are tracked in `ledger/deps.json` |"
        )
    write("")

    write("## Complete deferral registry")
    write("")
    if deferrals:
        tally_text = ", ".join(f"{status} {count}" for status, count in sorted(tally.items()))
        write(
            f"**{len(deferrals)} registry entries** — {tally_text}. Resolved rows remain "
            "visible as audit history; every active limitation names its blocker and revisit condition."
        )
        write("")
        write("| id | status | scope | named blocker | revisit condition |")
        write("|---|---|---|---|---|")
        for row in deferrals:
            write(
                f"| {row['id']} | {row['status']} | {row['milestone']} | "
                f"{row['blocker']} | {row['revisit']} |"
            )
    else:
        write("**Deferral registry is unavailable.** No absence is interpreted as support.")
    write("")

    write("## Reproducibility")
    write("")
    write("- Generator: `scripts/public-dashboard.py --source HEAD`")
    write("- Receipt sources: `ledger/results/*.json`")
    write("- Limitation source: `ledger/deferred.json`")
    write(f"- Public input SHA-256: `{input_digest(source)}`")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default="HEAD",
        help="source view: worktree, index, or a Git revision (default: HEAD)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "PARITY.md",
        help="generated Markdown path (default: PARITY.md)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if --output differs instead of writing it",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rendered = (render_dashboard(SourceView(args.source)) + "\n").encode("utf-8")
    output = args.output if args.output.is_absolute() else ROOT / args.output

    if args.check:
        try:
            current = output.read_bytes()
        except OSError:
            current = None
        if current != rendered:
            print(f"public dashboard: STALE {output}")
            return 1
        print(f"public dashboard: exact {output}")
        return 0

    output.write_bytes(rendered)
    print(f"public dashboard: wrote {output} ({len(rendered)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
