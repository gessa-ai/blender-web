#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify the public non-affiliation shell contract without launching a browser."""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
SHELL = ROOT / "platform_web/shell/windowed.html"
STAGED_VERIFIER = ROOT / "sandbox/m8-staged-deploy/verify_staged.mjs"
DISCLAIMER = "not affiliated with, endorsed by, or sponsored by the Blender Foundation"
TRADEMARK = "Blender® is a registered trademark of the Blender Foundation"
SOURCE_URL = "https://github.com/gessa-ai/blender-web"
README_PROOFS = (
    "Runs entirely on your device — WebAssembly + WebGPU. No server, no streaming.",
    "After first load, disconnect your network and reload.",
    "Desktop only for this preview; current Chrome or Edge is required.",
)
RETIRED_LOADER_IDS = (
    "bw-native-proof", "bw-offline-proof", "bw-desktop-limit",
    "bw-source-pending", "bw-license-link",
)


def normalize(value: str) -> str:
    return " ".join(value.split())


class ShellContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.active: list[tuple[str, str]] = []
        self.counts: dict[str, int] = {}
        self.text: dict[str, list[str]] = {}
        self.tags: dict[str, str] = {}
        self.hrefs: dict[str, str] = {}
        self.scripts: list[str] = []
        self.title_depth = 0
        self.title: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            self.counts[element_id] = self.counts.get(element_id, 0) + 1
            self.tags[element_id] = tag
            self.text.setdefault(element_id, [])
            self.active.append((tag, element_id))
            if values.get("href") is not None:
                self.hrefs[element_id] = values["href"] or ""
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"] or "")
        if tag == "title":
            self.title_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self.title_depth:
            self.title_depth -= 1
        for index in range(len(self.active) - 1, -1, -1):
            if self.active[index][0] == tag:
                del self.active[index:]
                break

    def handle_data(self, data: str) -> None:
        if self.title_depth:
            self.title.append(data)
        for _, element_id in self.active:
            self.text[element_id].append(data)


def validate(readme: str, shell: str, staged_verifier: str) -> list[str]:
    failures: list[str] = []
    readme_text = normalize(readme)
    if DISCLAIMER not in readme_text or TRADEMARK not in readme_text:
        failures.append("readme-disclaimer")
    if any(proof not in readme_text for proof in README_PROOFS) or SOURCE_URL not in readme:
        failures.append("readme-launch-copy")

    parser = ShellContractParser()
    parser.feed(shell)
    if normalize("".join(parser.title)) != "Source-derived WebAssembly editor preview":
        failures.append("independent-title")
    required_ids = ("bw-source-link", "bw-legal-footer")
    for element_id in required_ids:
        if parser.counts.get(element_id) != 1:
            failures.append(f"element-count:{element_id}")
    if parser.tags.get("bw-legal-footer") != "footer":
        failures.append("legal-footer-tag")
    if normalize("".join(parser.text.get("bw-source-link", []))) != "Source code (GPL)":
        failures.append("source-link-text")
    if any(parser.counts.get(element_id, 0) for element_id in RETIRED_LOADER_IDS):
        failures.append("retired-loader-copy")
    legal = normalize("".join(parser.text.get("bw-legal-footer", [])))
    if DISCLAIMER.lower() not in legal.lower() or TRADEMARK not in legal:
        failures.append("shell-disclaimer")
    if parser.hrefs.get("bw-source-link") != SOURCE_URL:
        failures.append("source-link")
    if parser.scripts[:2] != ["/diagnostics-bootstrap.js", "/bin/blender_browser.js"]:
        failures.append("diagnostics-script-order")

    if "/not affiliated with, endorsed by, or sponsored by the Blender Foundation/i" not in staged_verifier:
        failures.append("staged-runtime-disclaimer")
    if "minimal_loader_visible" not in staged_verifier or SOURCE_URL not in staged_verifier:
        failures.append("staged-minimal-loader")
    return failures


def mutate(value: str, old: str, new: str) -> str:
    if value.count(old) != 1:
        raise AssertionError(f"mutation precondition differs: {old!r}")
    return value.replace(old, new, 1)


def main() -> None:
    readme = README.read_text(encoding="utf-8")
    shell = SHELL.read_text(encoding="utf-8")
    staged_verifier = STAGED_VERIFIER.read_text(encoding="utf-8")
    failures = validate(readme, shell, staged_verifier)
    if failures:
        raise SystemExit("M8_PUBLIC_DISCLAIMER_FAIL " + failures[0])

    mutations = (
        (mutate(readme, "endorsed by, or sponsored by", "endorsed by"), shell, staged_verifier),
        (readme, mutate(shell, "endorsed by, or sponsored by", "endorsed by"), staged_verifier),
        (readme, mutate(shell, "Source-derived WebAssembly editor preview", "blender-web"), staged_verifier),
        (mutate(readme, README_PROOFS[0], "Runs in a browser."), shell, staged_verifier),
        (readme, mutate(shell, f'href="{SOURCE_URL}"', 'href="https://example.invalid"'), staged_verifier),
        (readme, mutate(shell,
                        '<script src="/diagnostics-bootstrap.js"></script>\n  <script src="/bin/blender_browser.js"></script>',
                        '<script src="/bin/blender_browser.js"></script>\n  <script src="/diagnostics-bootstrap.js"></script>'),
         staged_verifier),
        (readme, shell,
         mutate(staged_verifier, "endorsed by, or sponsored by", "endorsed by")),
        (readme, mutate(shell, '<footer id="bw-legal-footer">', '<div id="bw-legal-footer">'), staged_verifier),
        (readme, mutate(shell, 'id="bw-source-link"', 'id="bw-source-pending"'), staged_verifier),
        (readme, mutate(shell, "Source code (GPL)</a>", "Source</a>"), staged_verifier),
    )
    for number, candidate in enumerate(mutations, 1):
        if not validate(*candidate):
            raise SystemExit(f"M8_PUBLIC_DISCLAIMER_FAIL mutation={number}")

    source_digest = hashlib.sha256(
        readme.encode() + b"\0" + shell.encode() + b"\0" + staged_verifier.encode()
    ).hexdigest()[:12]
    print(
        "M8_PUBLIC_DISCLAIMER_PASS "
        f"positive=1 negative={len(mutations)} source_sha256={source_digest}"
    )


if __name__ == "__main__":
    main()
