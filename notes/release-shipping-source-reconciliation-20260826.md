<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Shipping source reconciliation (2026-08-26)

## Outcome

The four runtime source files called out by the release audit are now clean direct inputs at HEAD.
The optimized CAPTURE product was already built from these bytes, so this reconciliation changes
repository history rather than the product artifact:

- `410e7ad` commits the exact ten adapter-supported device limits in the WM-worker preinit and
  standalone GHOST fallback paths.
- `559b106` commits the accepted M7 bridge behavior: persistent post-open polling,
  user-activation-safe FSA save, bounded scene inspection, and an integrity-checked share-scene
  allowlist.
- `5426e76` commits byte-level loader progress text.

No unrelated dirty ledger, configuration, sandbox, receipt, or generated-artifact path was staged.

## Verification

- The four-path committed-state check is green: `20260826T075215-539044`.
- The pinned Node 22.16.0 preinit contract and exact ten-limit source contract are green:
  `20260826T075215-539045` and `20260826T075215-539049`.
- M7 receipt/source mutations and the pinned browser-producer self-check are green:
  `20260826T075215-539056` and `20260826T075215-539069`.
- Locked `build-wasm-windowed-opt` `blender_browser` is exact Ninja no-work:
  `20260826T075150-538847`.
- REUSE 6.2.0 is green: `20260826T075226-539281`.
- The required M8 scope remains honestly red at its existing 25 APPLY/browser/aggregate boundaries:
  `20260826T075251-539434`.
- Container-backed regression restores M0 6/6 and leaves M1-M8 at their existing strict red
  boundaries: `20260826T075332-539969`.

No hardware adapter, Apple profile, APPLY product, browser receipt, result promotion, tolerance,
golden, blacklist, or promise changed.
