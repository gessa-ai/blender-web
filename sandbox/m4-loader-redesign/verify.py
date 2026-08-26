#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0

"""Device-free contract for the release loader and its local font asset."""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
SHELL = ROOT / "platform_web/shell/windowed.html"
BOOT = ROOT / "platform_web/shell/boot-windowed.js"
FONT = ROOT / "platform_web/shell/fonts/bw-interface-sans.woff2"
FONT_NOTES = ROOT / "platform_web/shell/fonts/README.md"
OFL = ROOT / "LICENSES/OFL-1.1.txt"
SOURCE_URL = "https://github.com/gessa-ai/blender-web"
FONT_SHA256 = "266290448afbfd4c6ce386bbad0b305b478ca2612f665d1b26e5efc4d17e8190"
DISCLAIMER = (
    "Not affiliated with, endorsed by, or sponsored by the Blender Foundation. "
    "Blender® is a registered trademark of the Blender Foundation."
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"M4_LOADER_REDESIGN_FAIL {message}")


def normalize(value: str) -> str:
    return " ".join(value.split())


class ShellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: dict[str, int] = {}
        self.tags: dict[str, str] = {}
        self.attrs: dict[str, dict[str, str]] = {}
        self.text: dict[str, list[str]] = {}
        self.active: list[tuple[str, str]] = []
        self.scripts: list[str] = []
        self.class_counts: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        element_id = values.get("id")
        if element_id:
            self.ids[element_id] = self.ids.get(element_id, 0) + 1
            self.tags[element_id] = tag
            self.attrs[element_id] = values
            self.text.setdefault(element_id, [])
            self.active.append((tag, element_id))
        for class_name in values.get("class", "").split():
            self.class_counts[class_name] = self.class_counts.get(class_name, 0) + 1
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"])

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.active) - 1, -1, -1):
            if self.active[index][0] == tag:
                del self.active[index:]
                break

    def handle_data(self, data: str) -> None:
        for _, element_id in self.active:
            self.text[element_id].append(data)


def main() -> None:
    shell = SHELL.read_text(encoding="utf-8")
    boot = BOOT.read_text(encoding="utf-8")
    parser = ShellParser()
    parser.feed(shell)

    require("background: #17181b" in shell, "loader neutral background missing")
    require('@font-face' in shell and 'url("/fonts/bw-interface-sans.woff2")' in shell,
            "same-origin Inter subset is not wired")
    require(parser.class_counts.get("bw-spinner") == 1, "loader must have one ring spinner")
    require(parser.ids.get("bw-progress") == 1 and parser.ids.get("bw-fill") == 1,
            "loader must have one determinate progress bar")
    require(parser.attrs["bw-progress"].get("role") == "progressbar",
            "progress bar accessibility role missing")
    require(normalize("".join(parser.text.get("bw-pct", []))) == "0%",
            "initial percentage is not explicit")
    require(parser.ids.get("bw-legal-footer") == 1 and
            parser.tags.get("bw-legal-footer") == "footer", "legal footer missing")
    require(parser.ids.get("bw-source-link") == 1 and
            parser.attrs["bw-source-link"].get("href") == SOURCE_URL,
            "GPL source link is absent or incorrect")
    require(normalize("".join(parser.text.get("bw-source-link", []))) == "Source code (GPL)",
            "GPL source link text drifted")
    require(DISCLAIMER in normalize("".join(parser.text.get("bw-legal-footer", []))),
            "standing disclaimer drifted")
    require(parser.ids.get("bw-diag") == 1 and parser.ids.get("state") == 1 and
            parser.ids.get("run") == 1, "hidden diagnostics DOM contract changed")
    require(parser.scripts[:2] == ["/diagnostics-bootstrap.js", "/bin/blender_browser.js"],
            "first-script diagnostics contract changed")

    for old_id in ("bw-native-proof", "bw-offline-proof", "bw-desktop-limit",
                   "bw-source-pending", "bw-license-link"):
        require(parser.ids.get(old_id, 0) == 0, f"retired loader copy remains: {old_id}")
    for retired_copy in ("Runs entirely on your device", "disconnect your network",
                         "Desktop only for this preview", "repository link pending"):
        require(retired_copy not in shell, f"marketing copy remains in loader: {retired_copy}")

    require("bw-indeterminate" not in shell and "bw-indeterminate" not in boot,
            "progress bar still has an indeterminate sweep")
    require('fillEl.style.width = pct + "%";' in boot and
            'pctEl.textContent = pct + "%";' in boot and
            'progressEl.setAttribute("aria-valuenow", String(pct));' in boot,
            "determinate percentage publication is incomplete")
    require('loaderEl.classList.add("bw-hidden")' in boot and
            'loaderEl.classList.add("bw-gone")' in boot,
            "first-pixels loader dismissal contract changed")
    require("body.bw-gate" in shell and "if (GATE && loaderEl)" in boot,
            "gate-mode loader suppression changed")

    require(FONT.is_file() and FONT.stat().st_size < 64 * 1024,
            "local font subset missing or not actually subsetted")
    font_bytes = FONT.read_bytes()
    require(font_bytes[:4] == b"wOF2", "font asset is not WOFF2")
    require(hashlib.sha256(font_bytes).hexdigest() == FONT_SHA256,
            "font subset identity drifted")
    require(FONT_NOTES.is_file() and "upstream/release/datafiles/fonts/Inter.woff2" in
            FONT_NOTES.read_text(encoding="utf-8"), "font derivation notes missing")
    require(OFL.is_file() and "SIL Open Font License 1.1" in
            OFL.read_text(encoding="utf-8"), "OFL-1.1 license text missing")

    required_wires = {
        "sandbox/m8-deploy/make_bundle.sh": "fonts/bw-interface-sans.woff2",
        "sandbox/m8-staged-deploy/make_staged_bundle.sh": "fonts/bw-interface-sans.woff2",
        "sandbox/m8-staged-deploy/stage_provenance.py": "fonts/bw-interface-sans.woff2",
        "sandbox/m8-launch-gate/bundle_identity.mjs": "/fonts/bw-interface-sans.woff2",
        "sandbox/m8-launch-gate/verify_m8.py": "/fonts/bw-interface-sans.woff2",
        "sandbox/m8-deploy/_headers": "Content-Type: font/woff2",
    }
    for relative, marker in required_wires.items():
        require(marker in (ROOT / relative).read_text(encoding="utf-8"),
                f"public bundle font wire missing: {relative}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_normalized = normalize(readme)
    for moved_copy in (
        "Runs entirely on your device — WebAssembly + WebGPU. No server, no streaming.",
        "After first load, disconnect your network and reload.",
        "Desktop only for this preview; current Chrome or Edge is required.",
    ):
        require(moved_copy in readme_normalized,
                f"loader copy was not moved to README: {moved_copy}")
    require(SOURCE_URL in readme, "public source URL is absent from README")

    print(
        "M4_LOADER_REDESIGN_PASS "
        f"font_bytes={len(font_bytes)} font_sha256={hashlib.sha256(font_bytes).hexdigest()[:12]} "
        "spinner=1 progress=1 marketing=0 source=1"
    )


if __name__ == "__main__":
    main()
