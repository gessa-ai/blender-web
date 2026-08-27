<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M6 EEVEE hardware-adapter receipt guard — 2026-08-27

## Outcome

The physical-F12 EEVEE acceptance path can no longer produce an accepted row on an absent,
fallback, masked, CPU, or named software WebGPU adapter. Before this change the producer recorded
WebGPU device limits but did not classify the adapter; its matrix documentation claimed that the
migration s7 preflight supplied this boundary, although no such check ran in the EEVEE producer or
consumer.

The producer now probes `navigator.gpu` on the same COOP/COEP origin before OPFS seeding or render
work. It prefers the current WebGPU location, `adapter.info.isFallbackAdapter`, and uses the legacy
adapter field only when the current field is absent. The resulting
`hardware-webgpu-adapter-v1` receipt rejects absent fallback status and unmasked software tokens,
and manifest schema v5 makes an accepted adapter a required assertion.

Matrix result and provenance schema v2 independently validate every v5 row, recompute the software
identity from the reported adapter information, and require one identical accepted adapter across
the selected run. The final M6 closeout verifier repeats the same checks against both aggregate
provenance and all 30 row manifests. Superseded v4/v1 evidence cannot satisfy the current gate.

## Device-free evidence

- The EEVEE matrix self-check generated and syntax-checked 30 portable row drivers, ran all 30
  canonical driver self-checks, and launched zero browsers. Its fixtures cover the real Apple
  receipt shape (`vendor=apple`, `architecture=metal-3`, blank device/description), the current
  `GPUAdapterInfo.isFallbackAdapter` location, the legacy fallback, explicit fallback, absent
  fallback status, absent adapter, and SwiftShader rejection. Log:
  `ledger/buildlogs/20260827T041847-1606694.log`.
- The final Python verifier accepts the same real-receipt shape and rejects isolated fallback,
  missing-status, masked-identity, reported-software, and unreported-SwiftShader mutations. Log:
  `ledger/buildlogs/20260827T041850-1607285.log`.
- The authoritative pinned-oracle regression restores M0 to 6/6 and leaves M1–M8 red at their
  existing strict receipt, APPLY-product, browser, and run-label boundaries. In particular, M6
  currently stops at its already-missing Cycles suite run label before it can consume any EEVEE
  matrix. Log: `ledger/buildlogs/20260827T041950-1608028.log`.

No browser, adapter, EEVEE pixel result, profile, split/APPLY artifact, receipt, tolerance, golden,
blacklist, or milestone result was produced or promoted. A fresh conformant-hardware 30-row EEVEE
matrix remains required for M6.
