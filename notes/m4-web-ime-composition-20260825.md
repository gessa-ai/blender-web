<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 web IME composition — 2026-08-25

## Outcome

Commit `9608169` closes the `ime-dead-keys` deferral. The windowed browser product now enables
Blender's stock `WITH_INPUT_IME` path and advertises `GHOST_kCapabilityInputIME`.

`GHOST_WindowWeb::beginIME()` synchronously asks the browser main thread to focus a hidden
textarea at Blender's requested caret rectangle. DOM `compositionstart`, `compositionupdate`, and
`compositionend` callbacks copy complete UTF-8 text into a bounded 64-slot SPSC queue. The WM
worker drains that queue from `GHOST_SystemWeb::processEvents()` and creates owned
`GHOST_kEventImeCompositionStart`, update/commit, and end events without touching GHOST objects
from the browser thread. End-of-composition restores focus to the visible canvas. Disabled input,
invalid messages, allocation failure, and queue saturation reject without overwriting an earlier
transition; public diagnostics contain counts and byte lengths but no composed text.

## Focused evidence

- The real `PROXY_TO_PTHREAD` GHOST harness rebuilds with IME enabled
  (`20260825T170346-1549390`). Its headed Chromium test proves the advertised capability, caret
  placement, textarea/canvas focus handoff, exact start/update/commit/end order, full Unicode
  payloads at byte offsets 3 and 10, zero drops, disabled rejection, and metadata-only diagnostics
  (`20260825T172731-1575391`). Clipboard, fullscreen, and active pointer-lock browser regressions
  remain green.
- The source contract rejects 21 ownership, atomic-ordering, event-mapping, focus, capability,
  product-configuration, patch, and series mutations. The integrated native/wasm32 pipeline stays
  byte-identical at 5,139 bytes, SHA-256
  `94588fb0021d722055e52e70594f869bb5f3a294afcf378aa843d059fc158ce5`, with source SHA-256
  `5b7c6f8512214f956bae175f76557d063449855c2d152461cf7cb7c71e49879c`
  (`20260825T172130-1568689`).
- The independent canonical freezer and replay bind 20,258 source entries and the refreshed
  2,341,547-byte snapshot at SHA-256
  `347d4aec2a1cf292b14bc37da5eedf2770f3e0ca90c6680afeceb78b59ad8d47`
  (`20260825T172036-1567922`, `20260825T172122-1568564`).

## Product and gate evidence

- The optimized product was reconfigured with the mandated native CPython host tool and
  `WITH_INPUT_IME=ON`, then relinked and ended exact locked no-work
  (`20260825T171015-1554944`, `20260825T171028-1555085`,
  `20260825T172158-1570805`). The baked-runtime contract passes all 21 mutations and binds a
  674,706-byte JavaScript runtime at SHA-256
  `6bcc0dc2264217c0f5091d053b7fd5dbe6e86a84f6a3bd5a726399f6588c5ed5`, 119,026,476-byte
  Wasm at `f0994b912d9f74d5a1c1a49185b912cfafeb3a5f21d28496e165354f006f9d8a`, and unchanged data
  at `09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`
  (`20260825T172245-1571443`). OFF preflight is green (`20260825T172255-1571535`).
- In the real Blender product, Chromium composition renames the active object to
  `BW_IME_鶴_🪶`; Blender's Python Console reads that committed name back through GHOST and the
  browser clipboard. Presentation advances three frames after composition with zero submission
  rejection and zero device loss (`20260825T172736-1575734`).
- Required M4 remains honestly red at the unchanged unsupported hardware binding. The final
  container-backed regression at `2026-08-25T17:28:39Z` keeps M0 6/6 green while M1–M8 retain
  their existing strict receipt, split-product, browser, hardware, and release boundaries. REUSE
  6.2.0 covers 2,561/2,561 files (`20260825T172923-1578400`).

The product interaction uses Chromium's forced fallback software adapter and is explicitly
diagnostic-nonreceipt evidence. It binds no adapter, profile, split product, live receipt, result
promotion, dependency decision, tolerance, golden, blacklist, or promise. The named blocker
remains `no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by
Dawn)`; dzn, Windows Edge, and WSL restart were not attempted.
