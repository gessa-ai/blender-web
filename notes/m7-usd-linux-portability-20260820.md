<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M7 USD browser-producer portability - 2026-08-20

## Outcome

The current strict M7 USD browser producer now passes its browser-free self-check from the
ornith-lab checkout root and from a descendant working directory. It no longer executes through
the former macOS checkout, shared Playwright tree, or external source-freeze pathname. The M7
gate wrapper and bundle/source checker also derive their checkout locations, so the required M7
scope reaches the real missing-receipt and missing-APPLY boundaries instead of failing on
`/Users/paws`.

This is producer readiness only. No browser was launched, no USD operation was rerun, no output
directory was allocated, and no browser, adapter, split, M7, or milestone receipt was promoted.
The s7 stop-condition remains binding because Chromium exposes only llvmpipe on this host.

## Reproduced defects

- The retained producer failed before validating a label because `createRequire()` named
  `/Users/paws/plushly/game-platform/node_modules`.
- The first required `harness/run.sh --scope m7` stopped at the wrapper's absolute
  `/Users/paws/blender-web/.../verify_m7.py` command, before any product contract ran.

## Repair

- `verify_browser_usd.mjs` derives the checkout, product, and evidence roots from
  `import.meta.url`, independent of the caller's current directory.
- Playwright resolution follows `BW_NODE_MODULES`, `NODE_PATH`, `.m4-node/node_modules`, then
  local `node_modules`; Node 22.16.0 and Playwright 1.61.1 are mandatory.
- Production runs require an explicit canonical source-freeze receipt, a safe immutable label,
  an uncredentialed loopback origin, and an output directory that is one direct child of a
  repository-local evidence root. Inputs are resolved and hash-bound before the label is
  reserved.
- Linux retains headed Chromium and `--enable-unsafe-webgpu` but drops the macOS-only Metal ANGLE
  argument. The existing USD export/import operator and exact triangle-value checks are
  unchanged, as is receipt schema v2.
- The M7 wrapper resolves its own directory, while `verify_m7.py` and
  `verify_bundle_sources.py` derive the checkout from `__file__`.

## Evidence

- Driver syntax: `ledger/buildlogs/20260820T194857-2432182.log`.
- Dependency-free root and descendant self-checks: 13/13, zero browser launches,
  `ledger/buildlogs/20260820T194857-2432183.log` and
  `ledger/buildlogs/20260820T194857-2432187.log`.
- Live-loader root and descendant self-checks: 14/14, Node 22.16.0, Playwright 1.61.1, zero
  browser launches, `ledger/buildlogs/20260820T194857-2432197.log` and
  `ledger/buildlogs/20260820T194857-2432208.log`.
- Node 25 rejection before evidence allocation:
  `ledger/buildlogs/20260820T194920-2432453.log`.
- Gate-wrapper shell syntax and bundle-checker CLI import:
  `ledger/buildlogs/20260820T194259-2426642.log` and
  `ledger/buildlogs/20260820T194259-2426656.log`.
- REUSE 3.3 compliance is GREEN for 1,922/1,922 files:
  `ledger/buildlogs/20260820T194944-2433415.log`.
- Container-backed regression leaves M0 6/6 GREEN, while the required M7 scope reaches the
  intended strict boundary and remains honestly RED 0/1 at `2026-08-20T19:47:20Z`: no current
  staged/files receipts, no APPLY split manifest, and no
  assembled bundle. `ledger/results/m7.json` records all 34 diagnostics.

The aggregate M7 contract self-check still reaches a separate macOS-only fallback-producer check
that invokes `codesign`; porting the branded Firefox/Safari identity lane without weakening its
signature contract is a distinct task. The native USD receipt producer likewise retains its old
host/source-freeze assumptions. Neither was claimed as Linux-ready here.
