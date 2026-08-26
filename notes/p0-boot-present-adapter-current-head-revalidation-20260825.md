<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0 boot, presentation, and adapter current-head revalidation — 2026-08-25

## Outcome

The three driver-reported P0 repairs were already committed when this iteration began. Fresh
current-head validation at `b8f1850` proves that they remain composed in the same optimized
windowed product:

- `1fc5986` registers the intercepted cmd:2 canvas through
  `PThread.receiveOffscreenCanvases(d)` before the strict presentation preflight;
- `69307e4` encodes and submits the acquired surface texture synchronously in its event-loop turn,
  then joins the asynchronous encoding and submission scope results before publication; and
- `30fa865`, `fe9ef91`, and `b41258d` prefer the current
  `GPUAdapterInfo.isFallbackAdapter` location, retain the legacy adapter property only as a
  compatibility fallback, and keep unknown/software/fallback identities rejected by receipt
  producers.

The device-free integrated native/wasm32 matrix is byte-identical at 5,305 bytes, SHA-256
`b744698a4eb15c063e7d286527ef512fea62570074ddb5c7a5bb8c549d71b6a3`, including exact same-turn
submission, callback ordering, partial-handle rejection, preinit ordering, and adapter-shape
contracts (`ledger/buildlogs/20260826T013233-147892.log`). The CAPTURE producer passes 14 positive
and 23 negative cases without launching a browser
(`ledger/buildlogs/20260826T013233-147893.log`), and the shared M5-M8 runtime consumer passes its
four positive controls and rejects all 35 mutations
(`ledger/buildlogs/20260826T013233-147896.log`).

## Shipping product

Locked Ninja reports exact no-work for `blender_browser`
(`ledger/buildlogs/20260826T013256-149286.log`). Strict OFF preflight binds the 680,153-byte
JavaScript, 119,035,011-byte Wasm, and 167,143,248-byte data artifacts
(`ledger/buildlogs/20260826T013324-149542.log`), with SHA-256 values
`0d49c2d2937c`, `8ce14cc83646`, and `09e58a25849e`. The built JavaScript contains exactly one early
runtime canvas-registration call, its diagnostic, and the unchanged hard missing-canvas guard
(`ledger/buildlogs/20260826T013717-154099.log`), proving that the post-JS source is baked rather
than inert.

The canonical `/` route serves `windowed.html`. Against Chromium's explicit fallback-software
diagnostic posture, that exact product reaches running Blender, settles startup, advances 78 idle
ticks, and responds to trusted input with nine further ticks and two presentations. It reports
zero stage-1 canvas/import failures, rejected submissions, rejected present transactions, page
errors, or device loss (`ledger/buildlogs/20260826T013406-150695.log`). This directly exercises the
boot plus sustained-presentation definition of working rather than accepting a one-frame paint.

Final REUSE 6.2.0 covers all 2,604/2,604 files, including this record
(`ledger/buildlogs/20260826T013842-155104.log`). Required M4 remains honestly red at the unchanged
unsupported hardware binding (`ledger/buildlogs/20260826T013502-151312.log`), while the final
pinned-container regression restores M0 6/6 green and leaves M1-M8 on their existing strict
boundaries (`ledger/buildlogs/20260826T013547-151922.log`).

## Boundaries

The live run is diagnostic-nonreceipt evidence. No adapter, profile, split product, hardware
receipt, result promotion, dependency, deferral, tolerance, golden, blacklist, or promise changed.
Mesa dzn and Windows Edge were not attempted, WSL was not restarted, and s7 remains blocked by
`no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`.
