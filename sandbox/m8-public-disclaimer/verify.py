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
PROOFS = {
    "bw-native-proof": (
        "Runs entirely on your device — WebAssembly + WebGPU. No server, no streaming."
    ),
    "bw-offline-proof": "After first load, disconnect your network and reload.",
    "bw-desktop-limit": "Desktop only for this preview · current Chrome or Edge required.",
    "bw-source-pending": "Source code (GPL): repository link pending owner-supplied URL.",
    "bw-license-link": "Licenses and notices",
}


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

    parser = ShellContractParser()
    parser.feed(shell)
    if normalize("".join(parser.title)) != "Source-derived WebAssembly editor preview":
        failures.append("independent-title")
    required_ids = (*PROOFS, "bw-legal-footer")
    for element_id in required_ids:
        if parser.counts.get(element_id) != 1:
            failures.append(f"element-count:{element_id}")
    if parser.tags.get("bw-legal-footer") != "footer":
        failures.append("legal-footer-tag")
    for element_id, expected in PROOFS.items():
        if normalize("".join(parser.text.get(element_id, []))) != expected:
            failures.append(f"element-text:{element_id}")
    legal = normalize("".join(parser.text.get("bw-legal-footer", [])))
    if DISCLAIMER not in legal or TRADEMARK not in legal:
        failures.append("shell-disclaimer")
    if parser.hrefs.get("bw-license-link") != "/legal/THIRD-PARTY.md":
        failures.append("legal-link")
    if parser.scripts[:2] != ["/diagnostics-bootstrap.js", "/bin/blender_browser.js"]:
        failures.append("diagnostics-script-order")

    required_runtime_regex = (
        "/not affiliated with, endorsed by, or sponsored by the Blender Foundation/"
    )
    if required_runtime_regex not in staged_verifier:
        failures.append("staged-runtime-disclaimer")
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
        (readme, mutate(shell, PROOFS["bw-native-proof"], "Runs in a browser."), staged_verifier),
        (readme, mutate(shell, 'href="/legal/THIRD-PARTY.md"', 'href="https://example.invalid"'), staged_verifier),
        (readme, mutate(shell,
                        '<script src="/diagnostics-bootstrap.js"></script>\n  <script src="/bin/blender_browser.js"></script>',
                        '<script src="/bin/blender_browser.js"></script>\n  <script src="/diagnostics-bootstrap.js"></script>'),
         staged_verifier),
        (readme, shell,
         mutate(staged_verifier, "endorsed by, or sponsored by", "endorsed by")),
        (readme, mutate(shell, '<footer id="bw-legal-footer">', '<div id="bw-legal-footer">'), staged_verifier),
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
