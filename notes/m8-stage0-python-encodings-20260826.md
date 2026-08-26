<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-0 Python codec deferral — 2026-08-26

## Outcome

Commit `11a4afd` keeps Python's measured five-file encoding registry/UTF-8 closure in Stage 0
and moves the other 117 codec source files to Stage 1. This is staged loading, not a feature cut:
the production Stage-1 loader restores every source byte, and CP1252, Latin-1, and Shift-JIS are
then importable with exact round-trip behavior.

The optimized CAPTURE Wasm is unchanged: `.wasm.orig` remains 119,142,918 bytes at
`c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`.

## Measured boot closure

The pinned native Blender 5.2 factory startup loads `encodings`, `encodings.aliases`,
`encodings.idna`, `encodings.utf_8`, and `encodings.utf_8_sig`. The exact windowed CAPTURE
generation loads the same closure except for UTF-8-SIG; the partition keeps the union. Neither
runtime loads CP1252, Latin-1, Shift-JIS, or any other deferred codec before the stable main loop.

- Pinned native module census: `ledger/buildlogs/20260826T114856-762928.log`.
- Exact windowed module census: `ledger/buildlogs/20260826T115013-763602.log`.
- The fail-first packer fixture rejects CP1252 incorrectly remaining in Stage 0:
  `ledger/buildlogs/20260826T115211-765342.log`.
- The final 59-classification packer contract is included in the provenance self-check:
  `ledger/buildlogs/20260826T120309-773313.log`.

## Exact size result

Against the unchanged 167,143,248-byte CAPTURE data payload, the partition becomes:

| bucket | files | raw bytes |
|---|---:|---:|
| Stage 0 keep | 1,252 | 19,293,712 |
| Stage 1 defer | 2,189 | 146,061,813 |
| drop | 1 | 1,787,723 |

The codec boundary removes 1,379,799 raw bytes from Stage 0. With pinned Node 22.16.0
Brotli-q11, Stage-0 data falls from 3,748,720 to **3,699,553 bytes** and rewritten glue falls
from 80,933 to **80,383 bytes**. With the unchanged 12,418,419-byte provisional split primary,
projected critical wire falls from 16,248,072 to **16,198,355 bytes**, a **49,717-byte
reduction**. It remains honestly **1,198,355 bytes over** LAUNCH.md's 15,000,000-byte bar.

Canonical packing is recorded in `ledger/buildlogs/20260826T115418-766874.log`; the exact pinned
q11 measurement is `ledger/buildlogs/20260826T120401-775625.log`.

## Runtime and release evidence

- The real monolith/candidate browser A/B uses pinned Node 22.16.0 and the same CAPTURE Wasm.
  Both products preserve Blender version, eight enabled add-ons, four editor areas,
  Camera/Cube/Light, the exact startup encoding-module set, UTF-8 round-trip, WM progress, and
  trusted `N` input. Three representative codecs are nonempty in the monolith and zero-length
  placeholders in Stage 0. Stage 1 restores 2,189 files / 146,061,813 bytes, then CP1252,
  Latin-1, and Shift-JIS import from byte-identical sources and produce their expected encodings
  with zero page or serious-console errors (`ledger/buildlogs/20260826T120401-775628.log`).
- Canonical current-product derivation, provenance self-check, staged assembler self-check,
  release-freeze self-check, compliance-tool self-check, and M8 consumer self-check are green
  (`ledger/buildlogs/20260826T120309-773315.log`,
  `ledger/buildlogs/20260826T120309-773313.log`,
  `ledger/buildlogs/20260826T120309-773314.log`,
  `ledger/buildlogs/20260826T120309-773321.log`,
  `ledger/buildlogs/20260826T120309-773332.log`, and
  `ledger/buildlogs/20260826T120309-773345.log`).

The browser A/B uses a fallback software adapter and binds no semantic-pixel or hardware receipt.
No build-tree artifact, accepted profile, APPLY product, public bundle, result promotion,
tolerance, golden, blacklist, dependency, deferral, or promise changed. Accepted Apple profiles,
the hash-bound APPLY relink, and semantic hardware pixels for the staged product remain mandatory.
