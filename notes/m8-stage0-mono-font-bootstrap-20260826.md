<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 Stage-0 mono-font bootstrap — 2026-08-26

## Outcome

The staged pack no longer carries Blender's complete 145,192-byte DejaVu Sans Mono
file on the first-pixel path. Stage 0 carries a deterministic 18,272-byte static
subset; Stage 1 restores the exact pinned source bytes, verifies both generations by
SHA-256, and asks Blender's stock RNA font update to rebuild the complete UI, mono,
and fallback stack once both font bootstraps are restored.

The existing single-font implementation was deliberately generalized to exactly two
known font paths. Duplicate and excess bootstrap rows fail closed, each compact and
restored identity is verified independently, and one bridge acknowledgement reports
the exact restored byte count for both paths.

## Fidelity experiment

The checked-in generator retains source hinting plus the GPOS/GSUB closure. Chromium
compares the exact pinned full font and the subset at 10, 11, 12, 14, 16, and 24 px:
all 95 Basic Latin code points have identical advances and zero changed raster
channels at every size. The complete Basic Latin plus Latin-1 string has identical
width. As with the accepted Inter bootstrap, three rarely used Latin-1
superscript/ordinal glyphs (`U+00AA`, `U+00B3`, and `U+00BA`) retain coverage and
advance but differ in transient subset rasterization. The default English first
frame uses none, and Stage 1 restores the full font before `Assets ready`.

Asset identities:

| generation | bytes | SHA-256 |
|---|---:|---|
| Stage-0 layout-preserving subset | 18,272 | `48af4c490eef98385cc4e4ee96b35b772880f751e72a906ec5b3ba645d57903b` |
| restored Blender DejaVu Sans Mono | 145,192 | `eb072b01f0f06ce11530a90cc11f094c60819d65ed47156540e23198ae149612` |

Pinned FontTools 4.59.2 and Brotli 1.1.0 reproduce both font assets exactly. The
mono recipe is recorded by `ledger/buildlogs/20260827T001541-1420846.log`; the
unchanged Inter recipe reproduced byte-for-byte in
`ledger/buildlogs/20260827T001457-1420449.log`. DejaVu remains under its actual
`Bitstream-Vera` terms, now carried in `LICENSES/Bitstream-Vera.txt`, the REUSE
annotation, dependency inventory, and third-party attribution.

## Browser and loader contracts

The headed raster/identity probe reports zero changed initial pixels between the
monolith and two-bootstrap staged product, both exact compact identities, both exact
restored source identities, and zero page errors
(`ledger/buildlogs/20260827T003339-1435818.log`). The independent real-product
WasmFS run reaches the same monolith/staged startup state, restores both fonts,
acknowledges one font-stack refresh, and exercises trusted console input with no
serious console or page errors (`ledger/buildlogs/20260827T002753-1428974.log`).

The packer contract covers exact offsets, hashes, Stage-0/Stage-1 coverage, and
synthetic missing/duplicate/excess cases. The loader execution contract covers two
exact bootstrap rows, one refresh, restored-byte acknowledgements, recovery, and 29
fail-closed Stage-1 mutations. Provenance, public-bundle, launch-gate, compliance,
and two-root release-freeze consumers require the new asset and its license.

## Critical-wire accounting

Pinned Node 22.16.0 Brotli q11/lgwin-24 measures the new Stage-0 data at 2,230,167
bytes and rewritten preload glue at 61,072 bytes. The prior single-bootstrap control
measured 2,355,452 and 61,005 bytes respectively: data plus glue saves 125,218 bytes.
The four minified public shell-control responses grow by 95 bytes, leaving a net
**125,123-byte** improvement. The prior 14,742,104-byte conservative projection is
therefore approximately **14,616,981 bytes**, 383,019 bytes under the decimal 15 MB
bar before the already-named small compressed-Wasm uncertainty. The exact codec run
is `ledger/buildlogs/20260827T002513-1427079.log`.

## Boundary

No Wasm was relinked, no APPLY product or public bundle was produced, and no adapter,
profile, pixel, performance, milestone, or launch receipt was promoted. The current
CAPTURE generation still needs fresh accepted Apple profiles before APPLY; P0-E and
P0-G retain their hardware-pixel checks. Only an exact APPLY/public-bundle run can
turn this projected payload shape into the <=15-MB receipt, and the independent
<=8-second semantic-interaction bar remains red.
