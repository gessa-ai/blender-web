<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T3 native Float32Filterable parity — 2026-08-22

## Outcome

Patch 0167 adds `Float32Filterable` to the native GHOST WebGPU device request when,
and only when, Dawn's adapter exposes it. The browser path already requests every
adapter-supported feature. Without the native request, the device could not use
filtering samplers with R32Float, RG32Float, or RGBA32Float even on an adapter that
advertised the capability, despite the WebGPU format table carrying that exact gate.

This iteration keeps `upstream/` read-only. The patch is applied only to an isolated
T3 stage, where the real `GHOST_ContextWGPU.cc` candidate compiles against Dawn at
`36cf1fae0cd8a81a4fb4580751648b80b2e6255c`. Canonical composition and the real
windowed product build are deliberately left as the next integration task.

## Experiment and device-free contract

The unchanged canonical source failed the direct precondition at the missing guarded
request (`ledger/buildlogs/20260822T052130-1050181.log`). The corrected T3 verifier:

- reverse-checks the already integrated platform patch 0149;
- applies 0167 only inside a temporary source tree;
- extracts the exact eight guard/request pairs from the staged shipping method;
- compiles that selector and the complete staged GHOST context through locked Ninja; and
- exhausts all 256 adapter-feature masks, preserving source order and requesting exactly
  the supported subset.

Five malformed-selector controls cover a missing Float32 request, mismatched guard and
request, duplicate request, injected side effect, and ambiguous extraction boundary. With
the positive fixture, the extractor self-check reports six cases
(`ledger/buildlogs/20260822T052448-1052451.log`). The final real-source build and 256-mask
contract are green (`ledger/buildlogs/20260822T052451-1052555.log`).

The unchanged canonical authority still replays exactly from the clean pin: 144 active
numbered patches, 257 canonical paths, and canonical SHA-256 prefix `31832021c9d7`
(`ledger/buildlogs/20260822T052650-1054438.log`). Exact REUSE 6.2.0 is green for
2,044/2,044 files (`ledger/buildlogs/20260822T052841-1056910.log`).

## Hardware boundary

The live control still identifies only Vulkan adapter type 3, llvmpipe, and exits through
the exact software rejection without a T3 receipt
(`ledger/buildlogs/20260822T052512-1052782.log`). The canonical GHOST source remained at
SHA-256 `58b6136c6f5f9171c540318ee1f7033ae2de207abdf0237faa69a60e5db3da5f`
before and after every staged build. No real accepted adapter, device, texture, pipeline,
draw, browser receipt, result promotion, dependency decision, deferral, tolerance, golden,
or blacklist was created or changed.

The required M3 scope remains red only for the absent fresh strict candidate
(`ledger/buildlogs/20260822T052729-1054898.log`). Container-backed regression restores M0
to 6/6 green and leaves M1-M8 red at their existing strict-receipt/artifact/browser/run-label/
hardware boundaries (`ledger/buildlogs/20260822T052732-1054944.log`).
