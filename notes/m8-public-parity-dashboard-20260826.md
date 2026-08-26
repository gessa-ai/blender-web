<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 public parity dashboard — 2026-08-26

## Outcome

Implementation commit `d22c195` adds the public repository proof page
`PARITY.md`. It publishes the current strict M0–M8 receipt status, audited GPU
component counts, the dependency inventory count, and every row in
`ledger/deferred.json` with its named blocker and revisit condition.

The page is intentionally separate from `reports/dashboard.md`. The internal
dashboard retains verbatim fleet activity for operations; the public page does
not ingest `ledger/progress.txt`, evidence paths, receipt details, or mutable
worktree-only result files.

## Reproducibility and privacy contract

`scripts/public-dashboard.py` reads one of three explicit source views:
`worktree`, the Git index, or an immutable Git revision. The committed page was
generated from the index and reproduces byte-for-byte from `HEAD`. It has no
wall-clock generation field or self-referential commit hash. Its source digest
binds the generator, pin, receipts, dependency ledger, deferral ledger, and GPU
census inputs.

The public renderer:

- emits `UNAVAILABLE` for a missing or malformed milestone receipt;
- requires every registry row to have an ID, status, blocker, and revisit
  condition, while preserving legacy absent scope as visible `unavailable`;
- publishes check identifiers but never potentially path-bearing receipt
  details;
- rejects Unix home/private/mount paths, Windows user paths, home-relative
  paths, and the known private host/user tokens; and
- includes the standing source link and Blender Foundation trademark
  disclaimer.

The committed page is 22,124 bytes and binds public input SHA-256
`ba4db8ab0b414d055ededc69759910f1de509d0dac4113dbb9fff8f416a11dfe`.
It contains 53/53 registry IDs exactly once. M8 is visibly `UNAVAILABLE` because
`ledger/results/m8.json` is not committed; the generator does not infer a pass
from the mutable local result.

## Evidence

- Fail-first: the focused verifier stopped at missing
  `scripts/public-dashboard.py` before implementation.
- Staged-index focused contract: 9 receipt rows, 53 deferrals, deterministic
  bytes, missing-source failure closure, private-metadata mutations, and a
  missing-blocker mutation pass (`ledger/buildlogs/20260826T211113-1261468.log`).
- Committed-HEAD focused contract and exact generator check pass
  (`ledger/buildlogs/20260826T211135-1261728.log`).
- REUSE 6.2.0 passes after the committed implementation
  (`ledger/buildlogs/20260826T211135-1261731.log`).
- The authoritative container-backed regression restores M0 6/6 and preserves
  the strict M1–M8 boundaries
  (`ledger/buildlogs/20260826T210920-1258837.log`).
- Refreshed technical compliance passes
  (`ledger/buildlogs/20260826T210938-1259685.log`); M8 then returns to exactly
  its pre-existing 23 APPLY/browser/tier failures
  (`ledger/buildlogs/20260826T210944-1259821.log`).

## Boundary

This closes the repository-hosted parity/deferral proof artifact requested by
LAUNCH.md. It does not claim a deployed standalone dashboard, accepted APPLY
product, fresh Apple profiles, P0-E/P0-G hardware pixels, browser matrix,
performance/soak receipt, M8 pass, or launch readiness. The driver must include
`PARITY.md` and its generator when refreshing the public source snapshot.
