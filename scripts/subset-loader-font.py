#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build the small, renamed WOFF2 used by the shell and Stage-0 UI bootstrap."""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont


FONTTOOLS_VERSION = "4.59.2"
BROTLI_VERSION = "1.1.0"
SOURCE_SHA256 = "fb865a5087637ba194b14aef6f0558214f3c4b3ec939e3c0812c66de41036a47"
UNICODES = frozenset((*range(0x20, 0x7F), *range(0xA0, 0x100))) - {0xAD}
RENAMED_NAMES = {
    1: "BW Interface Sans",
    2: "Regular",
    3: "4.001;BW;BWInterfaceSans-Regular",
    4: "BW Interface Sans Regular",
    6: "BWInterfaceSans-Regular",
    16: "BW Interface Sans",
    17: "Regular",
    25: "BWInterfaceSans",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_tool_versions() -> None:
    actual = {"fonttools": version("fonttools"), "Brotli": version("Brotli")}
    expected = {"fonttools": FONTTOOLS_VERSION, "Brotli": BROTLI_VERSION}
    if actual != expected:
        raise SystemExit(f"loader font tool version drift: actual={actual} expected={expected}")


def rename_font(font: TTFont) -> None:
    names = font["name"]
    for record in names.names:
        value = RENAMED_NAMES.get(record.nameID)
        if value is None:
            continue
        record.string = value.encode(record.getEncoding())


def build(source: Path, output: Path) -> None:
    require_tool_versions()
    source_digest = sha256(source)
    if source_digest != SOURCE_SHA256:
        raise SystemExit(
            f"loader font source drift: actual={source_digest} expected={SOURCE_SHA256}"
        )

    font = TTFont(source, recalcTimestamp=False)
    axes = {axis.axisTag for axis in font["fvar"].axes}
    if axes != {"opsz", "wght"}:
        raise SystemExit(f"loader font variable axes drift: {sorted(axes)}")
    instantiateVariableFont(
        font, {"opsz": 14.0, "wght": 400.0}, inplace=True, optimize=True,
        updateFontNames=False,
    )

    options = subset.Options()
    options.flavor = "woff2"
    options.hinting = True
    # Retain the source layout closure. Besides making the browser loader's
    # typography faithful, this asset is Blender's transient Stage-0 UI font;
    # dropping GPOS/GSUB causes a visible kerning reflow when Stage 1 restores
    # the complete Inter file.
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.notdef_outline = True
    options.recommended_glyphs = True
    options.recalc_timestamp = False
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=UNICODES)
    subsetter.subset(font)
    rename_font(font)

    cmap = set(font.getBestCmap())
    missing = sorted(UNICODES - cmap)
    if missing:
        raise SystemExit(f"loader font lacks requested code points: {missing}")
    if "fvar" in font:
        raise SystemExit("loader font remains variable after static instancing")

    output.parent.mkdir(parents=True, exist_ok=True)
    font.flavor = "woff2"
    font.recalcTimestamp = False
    font.save(output, reorderTables=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expect-sha256")
    args = parser.parse_args()
    build(args.source, args.output)
    digest = sha256(args.output)
    if args.expect_sha256 and digest != args.expect_sha256:
        args.output.unlink(missing_ok=True)
        raise SystemExit(
            f"loader font output drift: actual={digest} expected={args.expect_sha256}"
        )
    print(f"LOADER_FONT_SUBSET_PASS bytes={args.output.stat().st_size} sha256={digest}")


if __name__ == "__main__":
    main()
