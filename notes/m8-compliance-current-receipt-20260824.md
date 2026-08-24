<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 current technical-compliance receipt refresh

## Outcome

The browser-free M8 compliance producer was replayed against the current ornith-lab checkout with
the exact repository-local REUSE 6.2.0 executable. All nine technical package facts pass and REUSE
covers 2,283/2,283 files. The independent consumer and technical-receipt mutation contracts remain
green. A real `harness/run.sh --scope m8` invocation moves from 25 to 23 technical failures: both
tracked-input and Git-history compliance-staleness failures disappear.

The four external-policy facts remain explicitly false and non-blocking in this technical receipt:
the public disclaimer, OpenSubdiv compatibility judgment, public source-code URL, and coordinated
history-policy repair. No local run manufactured those decisions.

## Evidence

- Exact-tool resolver self-check: `ledger/buildlogs/20260824T112042-4095731.log`.
- Current-tree producer: `ledger/buildlogs/20260824T112047-4095782.log`.
- Independent consumer and receipt-contract suites:
  `ledger/buildlogs/20260824T112059-4095902.log` and
  `ledger/buildlogs/20260824T112059-4095903.log`.
- Pinned-container regression: `ledger/buildlogs/20260824T112126-4097197.log`; M0 returns to 6/6
  green while the overall command remains honestly nonzero for the existing M1-M8 boundaries.
- Post-regression producer: `ledger/buildlogs/20260824T112214-4098153.log`; the resulting scoped M8
  result at `2026-08-24T11:22:24Z` reports 23 technical failures and contains neither compliance
  staleness diagnostic.

The receipt lives under the ignored `sandbox/m8-launch-gate/artifacts/` evidence tree. It is
regenerated after this tracked record lands so its repository-input and reachable-history digests
bind the record commit as well.

## Boundaries

M8 remains RED on the existing APPLY split product, browser/runtime, aggregate milestone, and
30-second product receipts. This refresh creates no adapter, browser, pixel, profile, split product,
deployment, policy sign-off, deferral, result promotion, tolerance, golden, blacklist, or promise.
The WSL2 hardware blocker remains unchanged and dzn, Windows interop, and WSL restart paths were not
attempted.
