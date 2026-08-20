<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 performance Linux portability — 2026-08-20

## Outcome

The strict current-bundle performance producer is host-portable without changing
the pinned 1.5 MB/s + 40 ms profile, three-run minimum, 8-second budget, pixel or
semantic-interaction proofs, split-phase requirements, or receipt schema. It derives
the checkout and output roots from its own module URL, resolves exact Playwright
1.61.1 and PNGJS 7.0.0 from documented local roots, requires Node 22.16.0 and an
explicit absolute Chrome executable, and selects both the stable-release API and
shared runtime-identity contract for the actual Darwin/Linux host.

No browser or performance receipt was produced. The real Linux invocation rejects
the absent canonical Chrome package before allocating evidence. Ornith-lab also still
exposes only the rejected llvmpipe adapter, so s7 cannot create the required APPLY
product or bind a GPU receipt.

## Scope

- `sandbox/m8-launch-gate/measure_current.mjs` owns the derived roots, pinned
  dependency loader, strict invocation parser, safe receipt path, platform release
  selector, shared host identity, and browser-free adversarial self-check.
- `sandbox/m8-launch-gate/runtime_evidence_selfcheck.mjs` independently rejects the
  retired `/Users/paws` root, a missing host-specific identity contract, and unpinned
  Node/Playwright/PNGJS seams in the performance producer.
- `sandbox/m8-launch-gate/README.md` records the exact Linux invocation and the
  explicit-host-browser requirement; the migration runbook now leaves soak and staged
  capture as the remaining M8 producer ports.

No `upstream/`, product source, browser receipt, GPU profile, adapter identity, split
artifact, performance budget, detector, result flag, deferral, tolerance, golden, or
promise changed.

## Browser-free evidence

- Syntax is GREEN (`20260820T212348-2516698`).
- Base self-check is 13 positive / 14 adversarial checks with zero browser launches
  (`20260820T212434-2517213`).
- Live repo-local dependency-loader checks from repository root and descendant CWD
  are each 14 positive / 14 adversarial checks with exact Playwright 1.61.1 and
  PNGJS 7.0.0, zero browser launches (`20260820T212434-2517214`,
  `20260820T212434-2517218`).
- Shared runtime-evidence checks pass from repository root and descendant CWD,
  including all 25 identity/diagnostics negative cases
  (`20260820T212434-2517229`, `20260820T211747-2509179`). The independent M8 consumer
  self-check is also GREEN (`20260820T212434-2517239`).
- A real Linux-shaped invocation names `/opt/google/chrome/chrome`, rejects the absent
  canonical package before product access, and leaves `measure_staged-4g.json` absent
  (`20260820T212348-2516699`). This is the expected pre-s7 boundary, not a browser or
  GPU receipt.
- Scoped diff hygiene and REUSE 6.2.0 are GREEN; REUSE covers 1,928/1,928 files
  (`20260820T212434-2517261`, `20260820T212434-2517277`). Required M8 remains honestly
  RED on the same 43 receipt/APPLY/compliance prerequisites (`20260820T212027-2512131`).
  Container-backed regression restores M0 6/6 GREEN and leaves M1-M8 RED only on the
  existing strict receipt, artifact, split-product, hardware, and run-label gates
  (`20260820T212237-2514572`).
