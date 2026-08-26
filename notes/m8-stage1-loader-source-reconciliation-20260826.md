<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-1 loader source reconciliation — 2026-08-26

## Outcome

Commit `ba0ceee` makes committed state reproduce the Stage-1 loader bytes used by the current
staged-product checks. The public bundle now retains visible `Downloading assets`,
`Installing assets`, and `Assets ready` phase/MB progress, streaming byte accounting, and exact
oversize/short-read rejection from a clean ref. Public `?stage1=manual` and `?gate=` query values
cannot suppress the loader or its progress overlay because both controls require the development
shell's capability marker. A trusted Playwright `addInitScript` global remains available to the
measurement rig, and the legacy boot-timing producer now uses that path instead of a public query.

This is source reconciliation and regression coverage, not a new split generation. The current
CAPTURE `.wasm.orig` remains 119,142,918 bytes at SHA-256
`c9dbae361ec105441176124ce718b3227c1dcc17cee83742eb22254bfa67f962`.

## Evidence

- The committed predecessor fails first because the public `?stage1=manual` query still disables
  loading (`ledger/buildlogs/20260826T144847-916022.log`).
- The post-commit pinned-Node execution contract passes the existing boot-shell 3/6 matrix plus
  seven Stage-1 behavior cases and eight mutations. It covers public/development/trusted controls,
  visible accessible progress, streamed and fallback downloads, exact writes, HTTP failure,
  oversize rejection, short-read rejection, and two trusted timing contexts
  (`ledger/buildlogs/20260826T145458-922623.log`).
- Loader and timing-producer syntax checks pass
  (`ledger/buildlogs/20260826T145117-917830.log` and
  `ledger/buildlogs/20260826T145117-917829.log`).
- Public hardening, staged assembly, independent provenance, transport, and CAPTURE producer
  self-checks are green (`ledger/buildlogs/20260826T145152-918157.log`,
  `20260826T145152-918158.log`, `20260826T145152-918172.log`,
  `20260826T145152-918186.log`, and `20260826T145152-918200.log`).
- The M8 consumer, both source-freeze contracts, final M0-M6 hermetic contract, and REUSE 6.2.0
  are green (`ledger/buildlogs/20260826T145252-918764.log`,
  `20260826T145252-918765.log`, `20260826T145252-918770.log`,
  `20260826T145252-918780.log`, and `20260826T145634-923980.log`).
- Required M8 remains honestly red at its unchanged 25 APPLY/browser/product/tier boundaries
  (`ledger/buildlogs/20260826T145333-921290.log`). Container-backed regression restores M0 to
  6/6 green and preserves the existing M1-M8 boundaries
  (`ledger/buildlogs/20260826T145340-921344.log`).

## Boundary

No public bundle was assembled and no browser, adapter, Apple profile, APPLY artifact, hardware
receipt, result promotion, promise, tolerance, golden, blacklist, dependency, or deferral changed.
P0-E idle resize pixels and both P0-F CAPTURE scenarios still require the driver-operated Apple
rig. Accepted hash-bound profiles remain mandatory before the APPLY relink and public-bundle
browser attack.
