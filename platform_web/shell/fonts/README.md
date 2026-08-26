<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Loader font subset

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
