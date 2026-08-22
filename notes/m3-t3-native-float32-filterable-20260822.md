<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T3 native Float32Filterable parity — 2026-08-22

## Outcome

Patch 0167 adds `Float32Filterable` to the native GHOST WebGPU device request when,
and only when, Dawn's adapter exposes it. The browser path already requests every
adapter-supported feature. Without the native request, the device could not use
filtering samplers with R32Float, RG32Float, or RGBA32Float even on an adapter that
advertised the capability, despite the WebGPU format table carrying that exact gate.

The initial proof applied the patch only to an isolated T3 stage, where the real
`GHOST_ContextWGPU.cc` candidate compiled against Dawn at
`36cf1fae0cd8a81a4fb4580751648b80b2e6255c`. The integration follow-up composes that
verified postimage into the canonical source authority, switches the T3 driver to
reverse-check it, and compiles and links the real windowed product.

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

The initial unchanged canonical authority replayed exactly from the clean pin: 144 active
numbered patches, 257 canonical paths, and canonical SHA-256 prefix `31832021c9d7`
(`ledger/buildlogs/20260822T052650-1054438.log`). Exact REUSE 6.2.0 is green for
2,044/2,044 files (`ledger/buildlogs/20260822T052841-1056910.log`).

## Canonical integration follow-up

A fresh pre-integration run reproduced the isolated forward-apply build contract
(`ledger/buildlogs/20260822T053402-1061536.log`). The canonical freezer then composed
the exact postimage while retaining 257 paths and 20,258 manifest entries. The squashed
patch is 1,548,304 bytes with SHA-256
`0b4aa138e5b81f791c4336da87f28343d3609501ec9e872b053aafb7603e2b41`; its live and
replay manifests are byte-identical at SHA-256
`780ae03f7f03ac4d45ab0bdd5cef18024e8bd084ad2dd2143e0ec53406e9d4cd`
(`ledger/buildlogs/20260822T053437-1061794.log`). Canonical replay independently passes
from the clean pin (`ledger/buildlogs/20260822T053749-1065139.log`).

The T3 driver now reverse-checks both 0149 and 0167 before extracting the eight optional
feature selectors. Its parser/mutation self-check and real-source build are green
(`ledger/buildlogs/20260822T053644-1063658.log`,
`ledger/buildlogs/20260822T053644-1063744.log`). The real `blender_browser` target rebuilt
and linked, then reported exact locked-Ninja no-work
(`ledger/buildlogs/20260822T053654-1063900.log`,
`ledger/buildlogs/20260822T053749-1065110.log`). Shell syntax and exact REUSE 6.2.0 are
green for 2,044/2,044 files (`ledger/buildlogs/20260822T053848-1066446.log`,
`ledger/buildlogs/20260822T053846-1066380.log`).

## Hardware boundary

The live control still identifies only Vulkan adapter type 3, llvmpipe, and exits through
the exact software rejection without a T3 receipt
(`ledger/buildlogs/20260822T053753-1065221.log`). The integrated canonical GHOST source is
SHA-256 `2e4dabb554504c5c10bb5ae403726b3a6adadab584f238dc8158e78258db399f`, and 0167
reverse-checks exactly. No real accepted adapter, device, texture, pipeline, draw, browser
receipt, result promotion, dependency decision, deferral, tolerance, golden, or blacklist
was created or changed.

The required M3 scope remains red only for the absent fresh strict candidate
(`ledger/buildlogs/20260822T053824-1065516.log`). Container-backed regression keeps M0 at
6/6 green and leaves M1-M8 red at their existing strict-receipt/artifact/browser/run-label/
hardware boundaries (`ledger/buildlogs/20260822T053824-1065562.log`).
