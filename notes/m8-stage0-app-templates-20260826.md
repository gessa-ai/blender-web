<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-0 application-template deferral — 2026-08-26

## Outcome

Commit `0fd49fa` moves the nine factory-unselected application-template files from the
first-pixel payload to Stage 1. The pinned native oracle reports an empty selected template at
`--factory-startup`; the ordinary General startup therefore does not consume the alternate 2D
Animation, Sculpting, Storyboarding, VFX, or Video Editing startup files. Stage 1 restores the
real bytes before those File > New choices are part of the completed product payload.

This is a staged-load reduction, not a feature cut. The template directories and zero-length
placeholder files remain in Stage 0, so the read-only preload tree is complete and the existing
Stage-1 loader can overwrite each placeholder. The packer's end-to-end contract now proves that
an application-template `startup.blend` is absent from Stage-0 bytes, present byte-exactly in
Stage 1, and represented by a placeholder in the rewritten preload manifest.

## Exact size result

Against the unchanged 167,143,248-byte CAPTURE data payload, the partition becomes:

| bucket | files | raw bytes |
|---|---:|---:|
| Stage 0 keep | 2,545 | 28,238,584 |
| Stage 1 defer | 896 | 137,116,941 |
| drop | 1 | 1,787,723 |

The nine moved files total 502,458 raw bytes. With the same Node Brotli-q11 encoder used for the
previous measurement, Stage-0 data falls from 5,615,715 to **5,123,738 bytes** and rewritten glue
falls from 86,662 to **86,578 bytes**. The provisional primary is unchanged at 12,418,419 bytes,
so critical wire falls from 18,120,796 to **17,628,735 bytes**, a 492,061-byte reduction. The
result remains **2,628,735 bytes over** LAUNCH.md's 15 MB bar.

## Evidence and boundaries

- The fail-first classifier contract rejected `keep != defer`; the final 26-classification,
  five-positive, ten-negative packer contract is green
  (`ledger/buildlogs/20260826T101733-677726.log` and `20260826T101815-678093.log`).
- The pinned native Blender 5.2 oracle proves `preferences.app_template == ''` at factory startup
  (`ledger/buildlogs/20260826T102139-680793.log`).
- Exact product packing, four-output provenance replay, assembler self-check, and Python syntax are
  green (`ledger/buildlogs/20260826T101910-678635.log`, `20260826T101929-678779.log`,
  `20260826T101945-678921.log`, `20260826T101929-678778.log`, and
  `20260826T102220-682417.log`).
- The exact Stage-0 candidate reaches the real windowed WM, advances idle ticks, accepts trusted
  input, and presents again with zero submission, transaction, loss, page-error, or incomplete
  bind-group failure on the fallback-software diagnostic adapter
  (`ledger/buildlogs/20260826T101955-679702.log`). This binds no pixel or hardware receipt.
- Exact q11 measurement is recorded in `ledger/buildlogs/20260826T102047-680452.log`; pinned REUSE
  6.2.0 is green in `ledger/buildlogs/20260826T102235-682588.log`.

No build-tree artifact, Wasm, JavaScript runtime, accepted profile, APPLY product, hardware
receipt, result promotion, tolerance, golden, blacklist, dependency, or deferral changed. The
CAPTURE `.wasm.orig` remains SHA-256 `c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`.
Accepted Apple profiles, APPLY, and semantic hardware pixels for the real staged product remain
mandatory.
