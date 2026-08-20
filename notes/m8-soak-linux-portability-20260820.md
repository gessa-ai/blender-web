<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 soak Linux portability — 2026-08-20

## Outcome

The strict current-bundle 30-minute soak producer is host-portable without changing
its full-duration requirement, 30-second sample cadence, 15-second trusted-input
cadence, 5-second stall limit, 10% JS-heap/RSS budgets, pixel-response proof, or
receipt schema. It derives checkout, dependency, evidence, and fresh-profile paths
from its own module URL; requires Node 22.16.0 plus exact Playwright 1.61.1 and PNGJS
7.0.0; and selects the shared canonical Chrome identity and stable-release feed for
the actual Darwin/Linux host.

No browser or soak receipt was produced. A real Linux-shaped invocation rejects the
absent canonical Chrome package before creating the profile or receipt. Ornith-lab
also still exposes only the rejected llvmpipe adapter, so s7 cannot create the APPLY
product or bind a GPU receipt.

## Scope

- `sandbox/m8-launch-gate/soak_current.mjs` owns derived roots, the pinned dependency
  loader, strict full-duration invocation parser, safe receipt/profile paths,
  platform release selector, shared host identity, procps-compatible RSS parsing,
  and the browser-free adversarial self-check.
- `sandbox/m8-launch-gate/runtime_evidence_selfcheck.mjs` independently rejects the
  retired `/Users/paws` root, a missing host-specific identity/release contract, and
  unpinned Node/Playwright/PNGJS seams in the soak producer.
- `ledger/deps.json` records procps `ps` as the Linux host-only RSS census tool.
- `sandbox/m8-launch-gate/README.md` records exact macOS/Linux invocations. The
  migration runbook now leaves staged capture as the remaining M8 producer port.

No `upstream/`, product source, browser receipt, GPU profile, adapter identity, split
artifact, soak budget, detector, result flag, deferral, tolerance, golden, or promise
changed.

## Browser-free evidence

- Syntax is GREEN (`20260820T213412-2526828`).
- Base self-check passes 14 positive / 14 adversarial cases with zero browser
  launches (`20260820T213412-2526829`).
- Live repo-local dependency checks from repository root and descendant CWD each
  pass 15 positive / 14 adversarial cases with exact Playwright 1.61.1 and PNGJS
  7.0.0, zero browser launches (`20260820T213412-2526833`,
  `20260820T213412-2526838`).
- Shared runtime-evidence checks pass from repository root and descendant CWD,
  including all 25 identity/diagnostics negative cases
  (`20260820T213412-2526847`, `20260820T213412-2526856`). The independent M8
  consumer and browser-matrix checks are also GREEN
  (`20260820T213412-2526874`, `20260820T213412-2526898`).
- A production-shaped invocation naming `/opt/google/chrome/chrome` fails at the
  absent canonical package and leaves both `.m8-soak-profile` and
  `current-soak-result.json` absent (`20260820T213427-2527131`). This is the expected
  pre-s7 boundary, not a browser or GPU receipt.
- Dependency-ledger JSON and scoped diff hygiene are GREEN
  (`20260820T213512-2528215`, `20260820T213512-2528216`). REUSE 6.2.0 is GREEN
  across 1,929/1,929 files (`20260820T213912-2532814`).
- Required M8 remains honestly RED on the same 43 receipt/APPLY/compliance
  prerequisites (`20260820T213603-2528829`). Container-backed regression restores
  M0 6/6 GREEN and leaves M1-M8 RED only on the existing strict receipt, artifact,
  split-product, hardware, and run-label gates (`20260820T213727-2531221`).
