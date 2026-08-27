<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Loader and Stage-0 font subsets

`bw-interface-sans.woff2` is a static Regular subset of Inter 4.001, used by the
browser loading shell and as Blender's transient Stage-0 UI-font bootstrap. Its
canonical input is Blender's pinned, already distributed
`upstream/release/datafiles/fonts/Inter.woff2` at `fbe6228777e7`:

- input SHA-256: `fb865a5087637ba194b14aef6f0558214f3c4b3ec939e3c0812c66de41036a47`
- output SHA-256: `47d56ba06d6380e40f49201b85421b5f8a22bc2b83ed7a257c9ab49fdc66421f`
- output size: 22,480 bytes
- coverage: Basic Latin and Latin-1 Supplement except unencoded soft hyphen
- shaping: the source GPOS/GSUB closure is retained so Stage-0 English UI
  advances and rasterization do not reflow when Stage 1 restores the full font
- tools: FontTools 4.59.2 and Brotli 1.1.0

Regenerate from the repository root with those Python packages on `PYTHONPATH`:

```sh
python3 scripts/subset-loader-font.py \
  upstream/release/datafiles/fonts/Inter.woff2 \
  platform_web/shell/fonts/bw-interface-sans.woff2 \
  --expect-sha256 47d56ba06d6380e40f49201b85421b5f8a22bc2b83ed7a257c9ab49fdc66421f
```

Subsetting makes this a modified font. Its user-facing and internal family name is
therefore `BW Interface Sans`, not the upstream reserved name. The font remains
licensed under OFL-1.1; see `LICENSES/OFL-1.1.txt` and `THIRD-PARTY.md`.

`bw-console-mono.woff2` is a static subset of DejaVu Sans Mono 2.37 used only
as Blender's transient Stage-0 console face. Its canonical input is
`upstream/release/datafiles/fonts/DejaVuSansMono.woff2` at the same Blender pin:

- input SHA-256: `eb072b01f0f06ce11530a90cc11f094c60819d65ed47156540e23198ae149612`
- output SHA-256: `48af4c490eef98385cc4e4ee96b35b772880f751e72a906ec5b3ba645d57903b`
- output size: 18,272 bytes
- coverage: Basic Latin and Latin-1 Supplement except unencoded soft hyphen
- shaping: the source GPOS/GSUB closure and hinting are retained; Chromium
  produces identical Basic Latin advances/raster at 10, 11, 12, 14, 16, and
  24 px and identical Latin-1 advances. Like the accepted Inter bootstrap,
  `U+00AA`, `U+00B3`, and `U+00BA` retain coverage/width but differ in transient
  subset rasterization; the English first frame uses none, and Stage 1 restores
  the exact 145,192-byte source.

Regenerate it with the same pinned tools:

```sh
python3 scripts/subset-loader-font.py \
  upstream/release/datafiles/fonts/DejaVuSansMono.woff2 \
  platform_web/shell/fonts/bw-console-mono.woff2 \
  --kind mono \
  --expect-sha256 48af4c490eef98385cc4e4ee96b35b772880f751e72a906ec5b3ba645d57903b
```

The modified font retains the DejaVu family name, which contains neither
Bitstream/Vera reserved name. It remains under `Bitstream-Vera`; see
`LICENSES/Bitstream-Vera.txt` and `THIRD-PARTY.md`.
