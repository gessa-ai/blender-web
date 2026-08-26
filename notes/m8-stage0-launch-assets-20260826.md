<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-0 launch-asset staging — 2026-08-26

## Outcome

Commit `5169fa6` moves 283 explicitly measured browser-cold launch assets to Stage 1: 72 Blender
Python sources, 57 Python-package support files, 12 authoring/reference files, and 142 lazy toolbar
icons. This is staged loading, not a feature cut. The production loader restores every deferred
byte after first pixels, while new or unmeasured script, package, and icon paths remain in Stage 0
by default.

The optimized CAPTURE Wasm is unchanged: `.wasm.orig` remains 119,142,918 bytes at
`c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`.

## Measured closure and corrected boundary

The real monolith browser census observed 501 loaded-module entries backed by 442 unique files.
The stable default toolbar cache contained exactly ten of the 152 runtime `.dat` icons, leaving
142 measured-cold icons for Stage 1
(`ledger/buildlogs/20260826T133315-854742.log` and
`ledger/buildlogs/20260826T135719-872051.log`).

The first broad candidate failed the strengthened browser A/B in two useful ways:

- `_bl_rna_utils/data_path.py` was required by the trusted N-panel interaction, so it and its
  package initializer remain in Stage 0.
- Deferring DejaVu Sans Mono let the initial UI boot but broke Console font initialization after
  Stage 1, so both Inter and the mono font remain in Stage 0.

That fail-first evidence is `ledger/buildlogs/20260826T135500-869958.log`. The final classifier
uses four exact allowlists rather than directory complements; synthetic future script, package,
and icon paths are contractually kept in Stage 0. The complete contract passes 568
classifications, five positive packing cases, and ten negative manifest cases
(`ledger/buildlogs/20260826T140201-875676.log`).

## Exact size result

Against the unchanged 167,143,248-byte CAPTURE data payload, the partition becomes:

| bucket | files | raw bytes |
|---|---:|---:|
| Stage 0 keep | 478 | 13,116,655 |
| Stage 1 defer | 2,963 | 152,238,870 |
| drop | 1 | 1,787,723 |

Pinned Node 22.16.0 Brotli-q11 produces a 2,595,374-byte Stage-0 data stream and 76,803-byte
rewritten glue. With the unchanged 12,418,419-byte provisional split primary, projected critical
wire falls from 15,437,581 to **15,090,596 bytes**, a **346,985-byte reduction**. It remains
honestly **90,596 bytes over** LAUNCH.md's 15,000,000-byte bar.

Canonical packing is recorded in `ledger/buildlogs/20260826T140218-875825.log`; the exact q11
measurement is `ledger/buildlogs/20260826T140420-877959.log`.

## Runtime and release evidence

- The real monolith/candidate browser A/B preserves version, enabled add-ons, editor areas,
  default objects, active keymap structure, the ten-icon default toolbar cache, trusted N-panel
  input, and tick/present progress before Stage 1. It proves 23 representative cold placeholders
  plus 15 byte-exact hot files. Stage 1 restores all 2,963 files / 152,238,870 bytes, then exercises
  lazy Blender imports, Requests metadata, the CA bundle, four deferred toolbar icons, and a live
  Console area using the retained mono font with zero serious console errors or page errors
  (`ledger/buildlogs/20260826T140227-875965.log`).
- Canonical staged provenance, the strict M8 consumer, JavaScript syntax, technical compliance,
  REUSE 6.2.0, and container-backed M0 regression are green
  (`ledger/buildlogs/20260826T140511-879067.log`,
  `ledger/buildlogs/20260826T140511-879068.log`,
  `ledger/buildlogs/20260826T140201-875677.log`,
  `ledger/buildlogs/20260826T140736-881101.log`,
  `ledger/buildlogs/20260826T140536-879325.log`, and
  `ledger/buildlogs/20260826T140743-881217.log`).

The browser A/B uses a fallback software adapter and binds no semantic-pixel or hardware receipt.
No build-tree artifact, accepted profile, APPLY product, public bundle, result promotion,
tolerance, golden, blacklist, dependency, deferral, or promise changed. The 90,596-byte budget
remainder, accepted Apple profiles, the hash-bound APPLY relink, and semantic hardware pixels for
the staged product remain mandatory.
