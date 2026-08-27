#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "public-dashboard.py"
PUBLIC_PAGE = ROOT / "PARITY.md"
SOURCE_MODE = os.environ.get("BW_PUBLIC_DASHBOARD_SOURCE", "worktree")


def git_read(path: str) -> bytes:
    if SOURCE_MODE == "worktree":
        return (ROOT / path).read_bytes()
    spec = f":{path}" if SOURCE_MODE == "index" else f"{SOURCE_MODE}:{path}"
    proc = subprocess.run(
        ["git", "show", spec], cwd=ROOT, check=True, capture_output=True
    )
    return proc.stdout


def load_generator():
    spec = importlib.util.spec_from_file_location("public_dashboard", GENERATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import public dashboard generator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def generate(path: Path, source: str = SOURCE_MODE) -> bytes:
    subprocess.run(
        [sys.executable, str(GENERATOR), "--source", source, "--output", str(path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return path.read_bytes()


def main() -> None:
    if not GENERATOR.is_file():
        raise RuntimeError("missing scripts/public-dashboard.py")
    if not PUBLIC_PAGE.is_file():
        raise RuntimeError("missing PARITY.md")

    with tempfile.TemporaryDirectory(prefix="bw-public-dashboard-") as temp_dir:
        first = generate(Path(temp_dir) / "first.md")
        second = generate(Path(temp_dir) / "second.md")
        if first != second:
            raise RuntimeError("public dashboard generation is not byte-deterministic")
        if first != PUBLIC_PAGE.read_bytes():
            raise RuntimeError("PARITY.md differs from generated committed-source output")

        missing = generate(Path(temp_dir) / "missing.md", "refs/heads/bw-missing-public-dashboard")
        if missing.count(b"| UNAVAILABLE |") != 9:
            raise RuntimeError("missing receipt sources do not fail closed as UNAVAILABLE")
        if b"Deferral registry is unavailable" not in missing:
            raise RuntimeError("missing deferral source does not fail closed")

    text = first.decode("utf-8")
    required = (
        "# Parity and limitations",
        "## Current milestone receipts",
        "## Complete deferral registry",
        "fbe6228777e7",
        "https://github.com/gessa-ai/blender-web",
        "Not affiliated with, endorsed by, or sponsored by the Blender Foundation.",
    )
    for marker in required:
        if marker not in text:
            raise RuntimeError(f"public dashboard missing required marker: {marker}")

    staging_markers = (
        "14,689,281 bytes of complete critical wire",
        "310,719 bytes under the size ceiling",
        "exact current non-Wasm/control subtotal is 2,397,124 bytes",
        "12,602,876-byte maximum current primary",
        "136,751 counters while the current b8b2a682ff09 CAPTURE original has 136,754",
        "structurally incompatible with the current relink",
    )
    for marker in staging_markers:
        if marker not in text:
            raise RuntimeError(f"public dashboard has stale staged-product accounting: {marker}")
    for stale in ("14,979,754 bytes", "20,246 bytes under", "14,616,981 bytes",
                  "383,019 bytes under", "at least approximately 14,678,797 bytes",
                  "at most 321,203 bytes under", "failed-receipt profiles"):
        if stale in text:
            raise RuntimeError(f"public dashboard retained superseded staged-product text: {stale}")

    forbidden = (
        r"(?:^|[\s('`\"])/(?:home|Users|mnt)/",
        r"[A-Za-z]:\\Users\\",
        r"(?:^|\s)~/",
        r"\bornith-lab\b",
        r"\bbw-logs\b",
        r"ledger/progress\.txt",
        r"Recent activity",
    )
    for pattern in forbidden:
        if re.search(pattern, text, flags=re.MULTILINE | re.IGNORECASE):
            raise RuntimeError(f"public dashboard leaked forbidden metadata: {pattern}")

    deferred = json.loads(git_read("ledger/deferred.json"))["deferred"]
    for row in deferred:
        line = re.compile(rf"^\| {re.escape(row['id'])} \|", re.MULTILINE)
        if len(line.findall(text)) != 1:
            raise RuntimeError(f"deferral id is not published exactly once: {row['id']}")
    if f"**{len(deferred)} registry entries**" not in text:
        raise RuntimeError("public deferral count does not match ledger")

    for milestone in range(9):
        if not re.search(rf"^\| M{milestone} \|", text, flags=re.MULTILINE):
            raise RuntimeError(f"public receipt table missing M{milestone}")

    readme = git_read("README.md").decode("utf-8")
    if "[PARITY.md](PARITY.md)" not in readme:
        raise RuntimeError("README does not link the public parity page")

    module = load_generator()
    rejected = (
        "/home/alice/private.json",
        "/Users/example/private.json",
        r"C:\Users\example\private.json",
        "/private/tmp/build.log",
        "~/bw-logs/receipt.json",
        "ornith-lab private receipt",
        "paws local checkout",
    )
    for value in rejected:
        try:
            module.public_cell(value)
        except module.PublicDataError:
            pass
        else:
            raise RuntimeError(f"private metadata mutation was accepted: {value}")

    class MissingBlockerSource:
        @staticmethod
        def read_json(_path: str):
            return {
                "deferred": [
                    {
                        "id": "missing-blocker",
                        "status": "deferred",
                        "milestone": "M8",
                        "revisit": "later",
                    }
                ]
            }

    try:
        module.deferral_rows(MissingBlockerSource())
    except module.PublicDataError:
        pass
    else:
        raise RuntimeError("deferral without a named blocker was accepted")

    print(
        "public dashboard: deterministic + 9 receipts + "
        f"{len(deferred)} deferrals + redaction mutations PASS"
    )


if __name__ == "__main__":
    main()
