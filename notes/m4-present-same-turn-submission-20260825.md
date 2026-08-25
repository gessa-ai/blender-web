<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 same-turn surface submission — 2026-08-25

## Outcome

Commit `69307e4` removes a timing-dependent destroyed-surface loop from the shipping
`/windowed.html` path. A complete present command buffer now reaches `Queue::Submit` in the same
browser event-loop turn as `GetCurrentTexture()`. Encoding and submission error scopes still both
settle before the present counter advances, and a null partial handle still reaches no submission.

The software run is diagnostic-only. It proves the product no longer depends on spontaneous error-
scope timing for liveness; it is not a GPU, pixel, profile, split-product, or M4 receipt.

## Root cause

The existing transaction from `ce5eb31` encoded against the transient canvas texture, popped its
encoding scopes, and submitted only from their asynchronous completion. When Chromium delivered
that completion after the acquisition turn yielded, the surface texture was already destroyed.
The current product reproduced repeated `present queue submission rejected` errors for a destroyed
1280x720 BGRA8 texture and could not turn trusted input into a presentation. The old device-free
contract remained green because it deliberately resolved the encoding scope before expecting a
submit; the revised fail-first contract rejects that ordering (`20260825T115802-1237384`).

The repair submits synchronously after all immediate handles are non-null, then pops the nested
submission scopes followed by the encoding scopes. One atomic two-result join retains all command
dependencies and accepts either callback order; either scope failure prevents publication.

## Evidence

- Final native/wasm32 integrated verification is byte-identical at 4,838 bytes,
  SHA-256 `cc651d8eeb1d`, and covers three same-turn submits, both callback orders, each scope
  failure, null handles, and one commit (`20260825T120723-1249660`).
- The independent callback lifecycle/census/ASan suite remains green
  (`20260825T120748-1251292`).
- The real `blender_browser` rebuilt through the locked Ninja wrapper and then ended exact no-work;
  OFF preflight binds the 659,848-byte JavaScript, 119,013,989-byte Wasm, and 167,143,248-byte data
  product (`20260825T120757-1251491`, `20260825T120857-1252318`,
  `20260825T120901-1252357`).
- The final headed COOP/COEP fallback diagnostic reaches `state=running`, advances through idle and
  trusted input, records a new presentation, and reports zero rejected submissions, rejected
  transactions, stage-1/import failures, page errors, or device loss
  (`20260825T120907-1252402`).
- REUSE 6.2.0 remains green (`20260825T121412-1257405`). Required M4 remains honestly red at the
  unchanged unsupported hardware binding, and the container-backed regression restores M0 6/6
  while M1-M8 retain their existing strict boundaries.

`windowed.html` remains the intended native-app product entry point; `/` in `scripts/serve-web.sh`
is the older M4.pre development shell. No adapter, profile, split product, receipt, result
promotion, dependency, deferral, tolerance, golden, blacklist, or promise changed. The external
blocker remains `no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by
Dawn)`; dzn and Windows were not attempted, and WSL was not restarted.
