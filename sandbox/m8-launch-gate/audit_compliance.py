#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the M8 compliance receipt from the actual repository state."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Mapping

import verify_m8


ROOT = verify_m8.ROOT
OUT = verify_m8.ART / "current-compliance-receipt.json"
REUSE_VERSION = "6.2.0"
REUSE_ENV = "BW_REUSE_BIN"
REUSE_LOCAL_CANDIDATES = (
    ROOT / ".host-tools/reuse-6.2.0/bin/reuse",
    ROOT / ".host-tools/bin/reuse",
)

# The default M8 gate is the locally verifiable technical release package. These
# checks are facts about bytes/source carried by that package. Public branding,
# legal compatibility judgment, publication URLs, and history/disclosure policy
# remain reported below but belong to the optional external launch authority.
TECHNICAL_REQUIRED_CHECKS = (
    "reuse_pass",
    "aggregate_gpl3",
    "derived_headers_complete",
    "license_texts_complete",
    "provenance_complete",
    "notice_authors_complete",
    "third_party_complete",
    "dependency_notices_complete",
    "dependency_registry_consistent",
)
EXTERNAL_POLICY_CHECKS = (
    "public_disclaimer_complete",
    "dependency_compatibility_complete",
    "source_code_link_present",
    "history_policy_complete",
)

STANDARD_LICENSE_SHA256 = {
    "LICENSES/Apache-2.0.txt": "074e6e32c86a4c0ef8b3ed25b721ca23aca83df277cd88106ef7177c354615ff",
    "LICENSES/BSD-3-Clause.txt": "5a93d5831e1297ab10fe643e1a631e83be392896da14ee2951285a79012df69d",
    "LICENSES/Bitstream-Vera.txt": "db77fa1a2796850938b4b0b07ead81d5b2b650029d92da8cfe39f581c3929604",
    "LICENSES/CC0-1.0.txt": "a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499",
    "LICENSES/GPL-2.0-or-later.txt": "aaf135472f81c5b4a0dca9367e5bb5e9750032b5bebe5442b36e4c0a47430df3",
    "LICENSES/GPL-3.0-or-later.txt": "fb981668c18a279e285fc4d83fba1e836cc84dd4daa73c9697d3cfd2d8aca6e0",
    "LICENSES/OFL-1.1.txt": "c1a781a6a032bf00b1bbffc388fd6936bf28a0ded472c263bcff88b181dea456",
}


class ComplianceToolError(RuntimeError):
    """A required host compliance tool is absent or differs from its exact contract."""


def exact_executable(path: Path, label: str) -> Path:
    """Return one absolute, normalized, non-symlink executable or fail closed."""
    if not path.is_absolute() or Path(os.path.normpath(str(path))) != path:
        raise ComplianceToolError(f"{label} path must be absolute and normalized: {path}")
    current = Path(path.anchor)
    try:
        for part in path.parts[1:]:
            current /= part
            if stat.S_ISLNK(current.lstat().st_mode):
                raise ComplianceToolError(f"{label} path contains a symlink: {current}")
        info = path.stat()
    except FileNotFoundError as error:
        raise ComplianceToolError(f"{label} executable is unavailable: {path}") from error
    if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or not os.access(path, os.X_OK):
        raise ComplianceToolError(f"{label} must be a nonempty executable file: {path}")
    if path.resolve() != path:
        raise ComplianceToolError(f"{label} path is not its exact real path: {path}")
    return path


def reuse_identity(path: Path) -> dict[str, object]:
    try:
        version = subprocess.run(
            [str(path), "--version"], cwd=ROOT, capture_output=True, text=True,
            timeout=30, env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ComplianceToolError(f"cannot execute REUSE host tool {path}: {error}") from error
    first_line = version.stdout.splitlines()[0] if version.stdout.splitlines() else ""
    expected = f"reuse, version {REUSE_VERSION}"
    if version.returncode != 0 or first_line != expected:
        detail = (version.stderr or version.stdout).strip().splitlines()
        observed = detail[0] if detail else f"exit {version.returncode}"
        raise ComplianceToolError(
            f"REUSE {REUSE_VERSION} required, got {observed!r} from {path}"
        )
    info = path.stat()
    return {
        "path": str(path),
        "version": REUSE_VERSION,
        "bytes": info.st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def resolve_reuse(
    environ: Mapping[str, str] = os.environ,
    local_candidates: tuple[Path, ...] = REUSE_LOCAL_CANDIDATES,
) -> tuple[Path, dict[str, object]]:
    explicit = environ.get(REUSE_ENV)
    if explicit is not None:
        if not explicit:
            raise ComplianceToolError(f"{REUSE_ENV} must not be empty")
        path = exact_executable(Path(explicit), "REUSE")
        return path, reuse_identity(path)

    candidates = [candidate for candidate in local_candidates if candidate.exists()]
    discovered = shutil.which("reuse", path=environ.get("PATH", ""))
    if discovered:
        candidates.append(Path(discovered))
    failures: list[str] = []
    for candidate in candidates:
        try:
            path = exact_executable(candidate, "REUSE")
            return path, reuse_identity(path)
        except ComplianceToolError as error:
            failures.append(str(error))
    suffix = f" ({'; '.join(failures)})" if failures else ""
    raise ComplianceToolError(
        f"REUSE {REUSE_VERSION} is unavailable; install the repository-local host tool "
        f"or set {REUSE_ENV} to its exact executable{suffix}"
    )


def compliance_tool_selfcheck() -> int:
    positive = 0
    negatives: list[str] = []

    def reject(name: str, action) -> None:
        try:
            action()
        except ComplianceToolError:
            negatives.append(name)
            return
        raise AssertionError(f"compliance tool self-check false green: {name}")

    with tempfile.TemporaryDirectory(prefix="m8-compliance-tool-") as temporary:
        root = Path(temporary).resolve()
        exact = root / "reuse-6.2.0"
        exact.write_text(
            "#!/bin/sh\n"
            "printf 'reuse, version 6.2.0\\n\\nfixture license text\\n'\n",
            encoding="utf-8",
        )
        exact.chmod(0o755)
        path_bin = root / "path-bin"
        path_bin.mkdir()
        path_reuse = path_bin / "reuse"
        path_reuse.write_bytes(exact.read_bytes())
        path_reuse.chmod(0o755)
        wrong = root / "reuse-wrong"
        wrong.write_text("#!/bin/sh\nprintf 'reuse, version 6.1.2\\n'\n", encoding="utf-8")
        wrong.chmod(0o755)
        nonexec = root / "reuse-nonexec"
        nonexec.write_text("fixture\n", encoding="utf-8")
        alias = root / "reuse-alias"
        alias.symlink_to(exact)

        selected, identity = resolve_reuse({REUSE_ENV: str(exact)}, ())
        assert selected == exact and identity["version"] == REUSE_VERSION
        assert identity["sha256"] == hashlib.sha256(exact.read_bytes()).hexdigest()
        positive += 1
        selected, _ = resolve_reuse({"PATH": str(root)}, (exact,))
        assert selected == exact
        positive += 1
        selected, _ = resolve_reuse({"PATH": str(path_bin)}, ())
        assert selected == path_reuse
        positive += 1

        reject("relative_explicit", lambda: resolve_reuse({REUSE_ENV: "reuse"}, ()))
        reject("empty_explicit", lambda: resolve_reuse({REUSE_ENV: ""}, ()))
        reject("missing_explicit", lambda: resolve_reuse({REUSE_ENV: str(root / "missing")}, ()))
        reject("wrong_version", lambda: resolve_reuse({REUSE_ENV: str(wrong)}, ()))
        reject("nonexecutable", lambda: resolve_reuse({REUSE_ENV: str(nonexec)}, ()))
        reject("symlink", lambda: resolve_reuse({REUSE_ENV: str(alias)}, ()))
        reject("absent_default", lambda: resolve_reuse({"PATH": ""}, ()))

    print(
        f"M8_COMPLIANCE_TOOL_SELFCHECK_PASS positive={positive} negative={len(negatives)} "
        f"version={REUSE_VERSION}"
    )
    return 0


def exact_sha256(path: Path, expected: str) -> bool:
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected


def has(path: str, pattern: str) -> bool:
    target = ROOT / path
    return target.is_file() and re.search(pattern, target.read_text(encoding="utf-8"), re.I | re.M) is not None


class _SourceLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.href: str | None = None
        self._candidate: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = dict(attrs)
        self._candidate = values.get("href")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._candidate is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._candidate is None:
            return
        text = " ".join(self._text)
        if re.search(r"source\s+code\s*\(GPL\)", text, re.I) and re.match(
            r"^https://", self._candidate, re.I
        ):
            # The one-click source offer must point to this port, not merely to
            # Blender upstream.
            if "projects.blender.org/blender/blender" not in self._candidate.lower():
                self.href = self._candidate
        self._candidate = None
        self._text = []


def source_code_link() -> str | None:
    path = ROOT / "platform_web/shell/windowed.html"
    if not path.is_file():
        return None
    parser = _SourceLinkParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.href


def derived_header_failures() -> list[str]:
    paths = (
        "patches/blender_web.cmake",
        "patches/platform_wasm.cmake",
        "platform_web/ghost/GHOST_SystemWeb.cc",
        "platform_web/ghost/GHOST_SystemWeb.hh",
        "platform_web/ghost/GHOST_WindowWeb.cc",
        "platform_web/ghost/GHOST_WindowWeb.hh",
        "platform_web/ghost/GHOST_ContextWGPUWeb.cc",
        "platform_web/ghost/GHOST_ContextWGPUWeb.hh",
        "platform_web/ghost/GHOST_EventBridgeWeb.cc",
        "platform_web/ghost/GHOST_EventBridgeWeb.hh",
        "platform_web/ghost/GHOST_KeyMapWeb.hh",
    )
    failures: list[str] = []
    patterns = (
        r"SPDX-FileCopyrightText:.*Blender Authors",
        r"SPDX-FileCopyrightText:\s*2026 blender-web contributors",
        "SPDX-" + r"License-Identifier:\s*GPL-2\.0-or-later",
        r"Ported for the web from",
        r"fbe6228777e7",
    )
    for name in paths:
        path = ROOT / name
        if not path.is_file():
            failures.append(f"{name}: missing")
            continue
        text = path.read_text(encoding="utf-8")[:4096]
        missing = [pattern for pattern in patterns if re.search(pattern, text, re.I | re.M) is None]
        if missing:
            failures.append(f"{name}: missing {', '.join(missing)}")
    return failures


def third_party_mismatches(third_party: str) -> list[str]:
    deps_path = ROOT / "ledger/deps.json"
    try:
        deps = json.loads(deps_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["ledger/deps.json unreadable"]
    rows: list[list[str]] = []
    for line in third_party.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0].lower() not in {"dependency", "---"} \
                and not set(cells[0]) <= {"-", ":", " "}:
            rows.append(cells)
    built = deps.get("wasm_built", {}) if isinstance(deps, dict) else {}
    required = sorted(
        name for name, record in built.items()
        if isinstance(record, dict) and record.get("status") == "ok"
    ) if isinstance(built, dict) else []
    normalize = lambda value: re.sub(r"[^a-z0-9]", "", str(value).lower())
    mismatches: list[str] = []
    for name in required:
        key = normalize(name)
        exact = [row for row in rows if normalize(row[0]) == key]
        candidates = exact or [row for row in rows if key in normalize(row[0])]
        if not candidates:
            mismatches.append(f"{name}: missing row")
            continue
        row = candidates[0]
        record = built[name]
        if normalize(record.get("version", "")) not in normalize(row[1]):
            mismatches.append(f"{name}: version {row[1]!r} != {record.get('version')!r}")
        if normalize(record.get("license", "")) != normalize(row[2]):
            mismatches.append(f"{name}: license {row[2]!r} != {record.get('license')!r}")
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--selfcheck", action="store_true",
        help="run browser/build-free adversarial REUSE host-tool contract checks",
    )
    args = parser.parse_args()
    if args.selfcheck:
        return compliance_tool_selfcheck()
    try:
        reuse_path, reuse_tool = resolve_reuse()
    except ComplianceToolError as error:
        print(f"M8_TECHNICAL_COMPLIANCE_FAIL preflight: {error}")
        return 1
    try:
        reuse = subprocess.run(
            [str(reuse_path), "lint", "-j"], cwd=ROOT, capture_output=True, text=True,
            timeout=300, env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"M8_TECHNICAL_COMPLIANCE_FAIL preflight: REUSE lint failed to execute: {error}")
        return 1
    try:
        reuse_doc = json.loads(reuse.stdout)
    except json.JSONDecodeError:
        reuse_doc = {}
    reuse_summary = reuse_doc.get("summary", {}) if isinstance(reuse_doc, dict) else {}
    used_licenses = reuse_summary.get("used_licenses", []) if isinstance(reuse_summary, dict) else []
    missing_reuse = []
    for row in reuse_doc.get("files", []) if isinstance(reuse_doc, dict) else []:
        if not row.get("copyrights") or not row.get("spdx_expressions"):
            missing_reuse.append(row.get("path", "<unknown>"))
    history = subprocess.run(
        ["git", "log", "--all", "--format=%H%x00%an%x00%ae%x00%B%x00"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    required_licenses = [f"LICENSES/{license_id}.txt" for license_id in used_licenses]
    standard_license_exact = all(
        exact_sha256(ROOT / path, expected)
        for path, expected in STANDARD_LICENSE_SHA256.items()
    )
    provenance = (ROOT / "PROVENANCE.md").read_text(encoding="utf-8") if (ROOT / "PROVENANCE.md").is_file() else ""
    third_party = (ROOT / "THIRD-PARTY.md").read_text(encoding="utf-8") if (ROOT / "THIRD-PARTY.md").is_file() else ""
    provenance_rows = (
        "patches/blender_web.cmake",
        "patches/platform_wasm.cmake",
        "platform_web/ghost/GHOST_SystemWeb.{cc,hh}",
        "platform_web/ghost/GHOST_WindowWeb.{cc,hh}",
        "platform_web/ghost/GHOST_ContextWGPUWeb.{cc,hh}",
        "platform_web/shell/",
        "sandbox/m8-staged-deploy/",
    )
    derived_failures = derived_header_failures()
    third_party_issues = third_party_mismatches(third_party)
    built = json.loads((ROOT / "ledger/deps.json").read_text(encoding="utf-8")).get("wasm_built", {})
    deps_doc = json.loads((ROOT / "ledger/deps.json").read_text(encoding="utf-8"))
    unresolved_compatibility = sorted(
        name for name, row in built.items()
        if isinstance(row, dict) and row.get("status") == "ok" and
        row.get("runtime_linked") is not False and row.get("gpl_compatible") is not True
    )
    opensubdiv_legal_exact = (
        exact_sha256(ROOT / "LICENSES/LicenseRef-OpenSubdiv-TOST-1.0.txt",
                     "9211071ceaea05cec948f44a025ede3030f41506960d68b50e7ddb6edc2abe5b") and
        exact_sha256(ROOT / "THIRD_PARTY_NOTICES/OpenSubdiv-3.7.0-NOTICE.txt",
                     "c9a283f0d3752b74d348a57e1d45e71cf69651ce6cbdce866983e459f6422c7c")
    )
    upstream_consolidated_legal_exact = (
        exact_sha256(ROOT / "upstream/release/license/license.md",
                     "6539df65e78fea926cbd46e45aeae6f6f1a54a48a3414e41236ad1ad4935bb97") and
        exact_sha256(ROOT / "upstream/release/license/licenses.json",
                     "4ee7ecba62e39ee2da7e513537a202bc27ef1b03ce181b443b2cee6fb6fece6c")
    )
    openusd_legal_exact = (
        exact_sha256(ROOT / "lib/wasm/share/licenses/OpenUSD-26.03/LICENSE.txt",
                     "4d6e8e3a9bd0104e10c48e3bc6af2f0976448a70a377d20cef674740f96f4452") and
        exact_sha256(ROOT / "lib/wasm/share/licenses/OpenUSD-26.03/NOTICE.txt",
                     "f6ad9d41f77b1bd8edaecd64bd1e13f4224876b010e2415e308267a84862bc14")
    )
    dependency_registry_consistent = (
        "international" not in deps_doc.get("forced_off", {}) and
        has("patches/blender_web.cmake", r"set\(WITH_INTERNATIONAL\s+ON\s+CACHE")
    )
    source_href = source_code_link()
    history_parts = history.split("\0")
    history_records = [history_parts[index:index + 4]
                       for index in range(0, len(history_parts) - 3, 4)]
    history_bodies = [record[3] for record in history_records]
    ai_names = r"(?:Claude|Anthropic|OpenAI|Codex|ChatGPT|GPT(?:-\d+)?|Copilot|Gemini)"
    ai_trailer_pattern = rf"(?mi)^Co-Authored-By:.*{ai_names}"
    assisted_pattern = rf"(?mi)^Assisted-by:.*{ai_names}"
    ai_coauthor_trailers = sum(len(re.findall(ai_trailer_pattern, body)) for body in history_bodies)
    ai_coauthored_commits = sum(re.search(ai_trailer_pattern, body) is not None for body in history_bodies)
    assisted_trailers = sum(len(re.findall(assisted_pattern, body)) for body in history_bodies)
    ai_disclosed_commits = sum(re.search(ai_names, body, re.I) is not None for body in history_bodies)
    ai_disclosure_without_assisted = sum(
        re.search(ai_names, body, re.I) is not None and re.search(assisted_pattern, body) is None
        for body in history_bodies
    )
    nonhuman_author_pattern = re.compile(rf"{ai_names}|\b(?:bot|automation)\b", re.I)
    nonhuman_author_commits = sum(
        bool(nonhuman_author_pattern.search(record[1]) or nonhuman_author_pattern.search(record[2]))
        for record in history_records
    )
    receipt = {
        "schema": 1,
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "repo_input_digest": verify_m8.repo_input_digest(),
        "git_history_digest": verify_m8.git_history_digest(),
        "reuse_pass": reuse.returncode == 0 and reuse_summary.get("compliant") is True,
        "aggregate_gpl3": has("LICENSE", r"GPL-3\.0-or-later"),
        "derived_headers_complete": not derived_failures,
        "license_texts_complete": standard_license_exact and
                                  all((ROOT / path).is_file() for path in required_licenses),
        "provenance_complete": bool(provenance) and "planned" not in provenance.lower()
                               and all(row in provenance for row in provenance_rows),
        "notice_authors_complete": has("NOTICE", r"Blender Authors") and (ROOT / "AUTHORS").is_file(),
        "public_disclaimer_complete": has("README.md", r"not\s+affiliated with, endorsed by, or sponsored by")
                                      and has("platform_web/shell/windowed.html", r"not\s+affiliated with, endorsed by, or sponsored by")
                                      and has("platform_web/shell/windowed.html", r"registered trademark"),
        "third_party_complete": bool(third_party) and "pending" not in third_party.lower()
                                and not third_party_issues,
        "dependency_compatibility_complete": not unresolved_compatibility,
        "dependency_notices_complete": opensubdiv_legal_exact and
                                       upstream_consolidated_legal_exact and
                                       openusd_legal_exact,
        "dependency_registry_consistent": dependency_registry_consistent,
        "source_code_link_present": source_href is not None,
        "history_policy_complete": ai_coauthored_commits == 0 and
                                   nonhuman_author_commits == 0 and
                                   ai_disclosed_commits > 0 and
                                   ai_disclosure_without_assisted == 0,
        "details": {
            "reuse_summary": reuse_summary,
            "reuse_tool": reuse_tool,
            "reuse_missing_files": missing_reuse[:100],
            "used_license_ids": used_licenses,
            "required_license_texts": required_licenses,
            "standard_license_texts_exact": standard_license_exact,
            "derived_header_failures": derived_failures,
            "third_party_mismatches": third_party_issues,
            "unresolved_dependency_compatibility": unresolved_compatibility,
            "opensubdiv_legal_exact": opensubdiv_legal_exact,
            "upstream_consolidated_legal_exact": upstream_consolidated_legal_exact,
            "openusd_legal_exact": openusd_legal_exact,
            "dependency_registry_consistent": dependency_registry_consistent,
            "source_code_href": source_href,
            "ai_coauthored_commit_count": ai_coauthored_commits,
            "ai_coauthor_trailer_count": ai_coauthor_trailers,
            "assisted_by_trailer_count": assisted_trailers,
            "ai_disclosed_commit_count": ai_disclosed_commits,
            "ai_disclosure_without_assisted_count": ai_disclosure_without_assisted,
            "nonhuman_author_commit_count": nonhuman_author_commits,
            "reuse_stderr": reuse.stderr[-2000:],
        },
    }
    receipt["technical_required_checks"] = list(TECHNICAL_REQUIRED_CHECKS)
    receipt["external_policy_checks"] = list(EXTERNAL_POLICY_CHECKS)
    receipt["technical_release_pass"] = all(
        receipt.get(key) is True for key in TECHNICAL_REQUIRED_CHECKS
    )
    receipt["external_policy_pass"] = all(
        receipt.get(key) is True for key in EXTERNAL_POLICY_CHECKS
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    passed = receipt["technical_release_pass"]
    print(f"M8_TECHNICAL_COMPLIANCE_{'PASS' if passed else 'FAIL'} -> {OUT.relative_to(ROOT)}")
    for key in TECHNICAL_REQUIRED_CHECKS:
        if receipt.get(key) is not True:
            print(" - [technical] " + key)
    for key in EXTERNAL_POLICY_CHECKS:
        if receipt.get(key) is not True:
            print(" - [external-policy, non-blocking] " + key)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
