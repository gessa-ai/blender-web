<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 staged-capture Linux portability — 2026-08-20

## Outcome

The current strict staged runtime producer is host-portable without changing its
three-process cold-online, online-warm, and offline-cold lifecycle; exact deferred
shard traffic; service-worker inventory; public-query hardening; trusted viewport
input; PARK..RESUMED state transition; pixel detector; or receipt schema. It derives
the checkout, dependency, and evidence roots from its own module URL, requires Node
22.16.0 plus exact Playwright 1.61.1 and PNGJS 7.0.0, requires an explicit absolute
Chrome executable, and selects the shared canonical browser identity for the actual
Darwin or Linux host.

No browser or staged receipt was produced. A production-shaped Linux invocation
rejects the absent canonical Chrome package before reading product artifacts or
changing evidence. Ornith-lab still exposes only the rejected llvmpipe adapter, so
s7 cannot produce the required APPLY split product or bind a GPU receipt.

## Scope

- `sandbox/m8-staged-deploy/verify_staged.mjs` owns derived paths, exact dependency
  loading, strict invocation parsing, host identity selection, safe evidence output,
  and its browser-free adversarial self-check. The preserved current producer's
  runtime assertions are unchanged outside those portability seams.
- `sandbox/m8-launch-gate/runtime_evidence_selfcheck.mjs` independently rejects the
  retired `/Users/paws` root, missing host-specific identity, and unpinned
  Node/Playwright/PNGJS seams.
- `sandbox/m8-launch-gate/README.md` records exact Linux and Darwin invocation shape;
  `notes/migration-to-ornith-lab.md` records the closed path/module/browser assumptions.

No `upstream/`, product source, browser receipt, GPU profile, adapter identity, split
artifact, runtime detector, budget, result flag, deferral, tolerance, golden, or
promise changed. Existing Playwright/PNGJS host-only dependency records already cover
this producer, so `ledger/deps.json` needed no new entry.

## Browser-free evidence

- Base self-check passes 10 positive / 10 adversarial cases with zero launches
  (`20260820T214809-2541049`).
- Live repo-local dependency checks from repository root and descendant CWD each pass
  11 positive / 10 adversarial cases with exact Playwright 1.61.1 and PNGJS 7.0.0,
  zero launches (`20260820T214809-2541050`, `20260820T214809-2541054`).
- Shared runtime-evidence checks pass from root and descendant CWD, including all 25
  identity/diagnostics negative cases (`20260820T214809-2541064`,
  `20260820T214809-2541076`). The independent M8 consumer and technical receipt
  contract checks are GREEN (`20260820T214809-2541096`,
  `20260820T214809-2541157`).
- The real Linux-shaped missing-package path leaves the existing evidence inventory
  unchanged and fails before product access. This is the expected pre-s7 boundary,
  not a browser or GPU receipt (`20260820T215039-2543084`). Syntax and scoped diff
  hygiene are GREEN (`20260820T215039-2543083`, `20260820T215039-2543095`), and
  REUSE 6.2.0 covers 1,930/1,930 files (`20260820T215039-2543088`).
- Required M8 remains honestly RED on the existing 43 receipt/APPLY/compliance
  prerequisites (`20260820T215100-2543463`). Container-backed regression restores
  M0 6/6 GREEN and leaves M1-M8 RED only on the existing strict receipt, artifact,
  split-product, hardware, and run-label gates (`20260820T215205-2545365`).

## Adjacent findings

Two separate support fixtures remain openly queued: `serve_measure.py --selfcheck`
currently opens the absent APPLY manifest before reaching its fixture, and
`verify_update_transition.mjs` retains a macOS checkout path. Neither is called by
the staged producer self-check or needed to establish this producer-only port; they
are recorded as `M8-STAGED-SUPPORT-LINUX-PORTABILITY` rather than silently folded
into this iteration.
