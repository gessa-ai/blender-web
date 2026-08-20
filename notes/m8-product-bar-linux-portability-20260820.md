<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 30-second product-bar Linux portability — 2026-08-20

## Outcome

The strict current-bundle product producer is host-portable without changing its
skeptic, own-file, share-route, timing, pixel, offline, or early-diagnostics
contract. It derives the checkout from its own module URL, resolves exact
Playwright 1.61.1 and PNGJS 7.0.0 from documented local roots, requires Node
22.16.0 and an explicit absolute Chrome executable, and selects the shared
Darwin/Linux Chrome identity contract. On Linux that contract remains the exact
canonical ELF plus `dpkg`/APT/keyring identity introduced by the browser-matrix
lane; Darwin keeps its notarized app/team checks.

No browser or product receipt was produced. Ornith-lab still has no installed
canonical Chrome package, exposes only the rejected llvmpipe adapter, and has no
s7-derived APPLY product. Those are required inputs, not portability exceptions.

## Scope

- `sandbox/m8-launch-gate/verify_product_bar.mjs` owns the derived root, pinned
  dependency loader, strict invocation parser, safe canonical receipt path, and
  browser-free self-check. Product inputs and browser identity validate before
  receipt allocation.
- `sandbox/m8-launch-gate/runtime_evidence_selfcheck.mjs` independently rejects
  the retired `/Users/paws` root, a missing host-specific identity contract, and
  unpinned Node/Playwright/PNGJS seams in the product producer.
- `sandbox/m8-launch-gate/README.md` records exact macOS and Linux commands; the
  migration runbook now names performance, soak, and staged capture as the
  remaining M8 producer ports.
- `ledger/deps.json` records Playwright's exact three-package host-tool closure
  and PNGJS, including licenses and npm integrity values. Neither dependency is
  part of the shipped browser payload.

No `upstream/`, product source, browser receipt, GPU profile, adapter identity,
split artifact, tolerance, golden, result flag, deferral, or promise changed.

## Browser-free evidence

- Base self-check from repository root and descendant CWD: 10 positive / 8
  adversarial checks, zero browser launches
  (`20260820T210244-2491738`, `20260820T210244-2491748`).
- Live repo-local dependency loader from root and descendant CWD: 11 positive /
  8 adversarial checks with exact Playwright 1.61.1 and PNGJS 7.0.0, zero browser
  launches (`20260820T210244-2491741`, `20260820T210244-2491759`).
- Shared runtime-evidence adversarial suite from root and descendant CWD: GREEN,
  including all 25 identity/diagnostics negative cases
  (`20260820T210244-2491780`, `20260820T210244-2491800`).
- Browser-matrix producer self-check: GREEN, 9 positive / 4 negative
  (`20260820T210244-2491832`). Producer syntax is also GREEN
  (`20260820T210244-2491736`).
- A real invocation naming `/opt/google/chrome/chrome` fails at the absent
  canonical package before creating `current-product-receipt.json`
  (`20260820T210300-2492001`). This is the expected pre-install failure and does
  not bind a browser or GPU receipt.
- Dependency-ledger JSON, scoped diff hygiene, and REUSE 6.2.0 are GREEN
  (`20260820T210851-2500371`, `20260820T210851-2500370`,
  `20260820T210851-2500369`). Required M8 remains
  honestly RED on its 43 existing strict receipt/split/compliance prerequisites
  (`20260820T210619-2496338`). Container-backed regression restores M0 6/6 GREEN
  and leaves M1-M8 RED on the existing strict receipt, artifact, split-product,
  hardware, and run-label gates (`20260820T210748-2498261`).
