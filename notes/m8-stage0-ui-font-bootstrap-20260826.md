<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 Stage-0 UI-font bootstrap — 2026-08-26

## Outcome

The staged pack no longer carries Blender's complete 351,132-byte Inter file on the
first-pixel path. Stage 0 carries a deterministic 22,480-byte static subset with the
source shaping closure; Stage 1 restores the exact pinned Inter bytes, verifies both
generations by SHA-256, and asks Blender's stock RNA font update to rebuild its font
stack before reporting `Assets ready`.

This cut also fixes a pre-existing Stage-1 publication defect uncovered by the real
runtime experiment. WasmFS rejects `/tmp` to `/bw` cross-backend renames, so the old
loader downloaded all 152,713,387 bytes and then installed zero. Publication now
temporarily grants owner write/search permission to each pre-created destination
parent, stages a sibling temporary file, atomically renames within that directory,
and restores every original mode on success and failure.

## Fidelity experiment

The first candidate reused the 9,500-byte loading-shell subset. Chromium showed that
its removed GPOS/GSUB tables changed the full Basic-Latin string width, which would
make Blender text visibly reflow when Stage 1 restored the full font. That candidate
was rejected.

The checked-in generator now retains the source layout closure. Against the exact
pinned full Inter file, Chromium renders all 95 Basic Latin code points at 14 px with
identical advance width and **zero changed raster channels**. The complete Basic
Latin plus Latin-1 string also has identical width. Three rarely used Latin-1
superscript/ordinal glyphs (`U+00AA`, `U+00B3`, `U+00BA`) retain coverage and outlines
but differ in static-instance hinting; the default English first frame uses none of
them, and Stage 1 restores the full variable font before `Assets ready`.

Asset identities:

| generation | bytes | SHA-256 |
|---|---:|---|
| Stage-0 layout-preserving subset | 22,480 | `47d56ba06d6380e40f49201b85421b5f8a22bc2b83ed7a257c9ab49fdc66421f` |
| restored Blender Inter | 351,132 | `fb865a5087637ba194b14aef6f0558214f3c4b3ec939e3c0812c66de41036a47` |

The pinned FontTools 4.59.2/Brotli 1.1.0 recipe reproduces the subset exactly
(`ledger/buildlogs/20260826T232946-1380897.log`). The loader source and headed-browser
contracts bind the hash, retained layout features, same-origin load, and Basic-Latin
raster equivalence (`20260826T232745-1379433.log`, `20260826T232745-1379438.log`).

## Real WasmFS publication

The fail-first product run downloaded all 2,964 files but ended with `bytesDone=0`.
Its direct filesystem probe measured `/bw` parents at mode `0555`, proved both the
cross-backend rename and unwritable sibling creation fail, and proved that temporary
`0755` plus same-directory rename works (`ledger/buildlogs/20260826T224434-1348416.log`).

The final same-product run reports:

- 2,964 / 2,964 files and 152,713,387 / 152,713,387 bytes installed;
- 335 unique destination directories made writable and restored;
- Stage-0 subset identity accepted, full Inter identity restored;
- Blender font-refresh acknowledgement with `fontBytes=351132`;
- one attempt, `phase=done`, no loader error, and zero page errors;
- peak file buffer 11,425,316 bytes, peak response chunk 2,097,152 bytes, and
  peak combined transient JS storage 13,522,468 bytes.

The diagnostic receipt is intentionally marked `diagnosticNonreceipt`; its software
adapter produces no semantic product-pixel authority. It binds filesystem, font, and
browser-raster behavior only (`ledger/buildlogs/20260826T232152-1375634.log`,
`sandbox/m8-stage0-ui-font/artifacts/probe-result.json`).

## Critical-wire accounting

Pinned Node 22.16.0 Brotli q11/lgwin-24 measurements compare the full-font Stage-0
control with the final bootstrap:

| critical response | full-font control | bootstrap |
|---|---:|---:|
| Stage-0 data | 2,683,640 | 2,355,452 |
| rewritten preload glue | 61,176 | 61,005 |
| separately requested loader font | 9,504 | 22,484 |
| **total** | **2,754,320** | **2,438,941** |

That is a **315,379-byte** net reduction. The stronger Stage-1 publisher/font contracts
increase the four minified shell-control responses by 1,036 bytes, leaving a net
**314,343-byte** improvement over the prior 15,056,447-byte conservative projection.
The revised projection is approximately **14,742,104 bytes**, 257,896 bytes under the
decimal 15 MB bar, before the already-named small Wasm-delta uncertainty. Exact data,
glue, and font codec logs are `20260826T231823-1373173.log`,
`20260826T231836-1373270.log`, and `20260826T231836-1373289.log`.

## Contracts and boundary

The packer contract covers the bootstrap partition, exact source/asset identities,
Stage-0/Stage-1 coverage, and manifest metadata. The loader execution contract covers
safe unique paths, same-directory publication, permission restoration, both hashes,
the bounded bridge call, streaming limits, recovery, and 27 fail-closed mutations.
The future staged hardware receipt now requires `stage1_bootstrap_restored=true` as
part of `stage1_complete`. Focused provenance and M8 consumer self-checks are green
(`20260826T232147-1375529.log`, `20260826T232147-1375528.log`,
`20260826T233025-1381615.log`, `20260826T233030-1381614.log`).

No Wasm was relinked, no APPLY product or public bundle was produced, and no adapter,
profile, pixel, performance, milestone, or launch receipt was promoted. The current
CAPTURE generation still needs fresh accepted Apple profiles before APPLY; P0-E and
P0-G retain their hardware-pixel checks. Only a full exact APPLY/public-bundle run can
turn the payload projection into the launch receipt.
