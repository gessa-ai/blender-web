<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 public parity staging freshness — 2026-08-27

## Outcome

Implementation commit `3742064` refreshes the public parity page's staged-product
row from the superseded pre-seed/pre-font projection to the current CAPTURE
generation. `PARITY.md` now reports the approximately 14,742,104-byte complete-wire
projection and 257,896-byte provisional margin after the shader-cache seed and
layout-preserving Stage-0 UI-font bootstrap.

The row remains explicitly partial. It identifies `blender_browser.wasm.orig`
SHA-256 `b8b2a682ff09e5eb80ba125b3fb85cd4fe65193c3eabd577e8a794c9e6a9fda6`, states
that the prior accepted Apple profiles belong to an older CAPTURE generation, and
preserves the small compressed-Wasm-delta uncertainty. Fresh current-generation
Apple success and terminal-error profiles, an exact APPLY relink, complete-wire
measurement, semantic pixels/input, offline behavior, and the <=8 second timing
receipt remain mandatory.

## Fail-closed contract

The dashboard input digest now binds both source evidence notes for the shader seed
and Stage-0 font bootstrap. Its focused verifier requires the current byte total,
margin, Wasm-delta caveat, and profile-generation language; it rejects the old
14,979,754-byte / 20,246-byte figures and obsolete `failed-receipt profiles` text.

The committed page was regenerated from the Git index, not the mutable worktree.
That distinction was exercised directly: the worktree view observed unrelated local
fleet receipt/census residue, while the index view retained the committed 1 PASS / 7
FAIL / 1 UNAVAILABLE receipt state and changed only this task's five scoped files.

## Evidence and boundary

- Committed-HEAD dashboard mutation contract and exact regeneration check:
  `ledger/buildlogs/20260827T000210-1409508.log` and
  `ledger/buildlogs/20260827T000210-1409510.log`.
- Final staged-index dashboard, deferral-registry, S7 honesty, and REUSE contracts:
  `ledger/buildlogs/20260827T000405-1410396.log`,
  `ledger/buildlogs/20260827T000405-1410401.log`,
  `ledger/buildlogs/20260827T000405-1410409.log`, and
  `ledger/buildlogs/20260827T000405-1410397.log`.
- Final technical compliance: `ledger/buildlogs/20260827T000441-1412100.log`.
- The pinned oracle-container regression restores M0 to 6/6 and preserves the
  existing strict M1-M8 boundaries (`ledger/buildlogs/20260827T000432-1410709.log`).
  After compliance refresh, M8 remains RED at its 23 existing
  APPLY/browser/tier failures (`ledger/buildlogs/20260827T000446-1412175.log`).

No APPLY artifact, public bundle, profile, hardware receipt, performance receipt,
milestone result, or launch claim was produced or promoted.
