<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 Pointer Lock outcome lifecycle — 2026-08-25

## Outcome

Commit `32640eb` separates an accepted browser Pointer Lock request from an active lock. A
Wrap/Hide request remains Pending and leaves the actual GHOST grab disabled until the document's
`pointerlockchange` reports that the owned canvas is locked. Relative `movementX/Y` and the Wrap
software cursor are active only in that state. `pointerlockerror`, external loss/Escape, canvas
blur, explicit Disable/Normal, window disposal, and system teardown cancel deferred browser work
and retire GHOST state before later input or deletion.

The document-level change/error listeners run on the WM worker through Emscripten's callback-thread
contract and are removed with the other ten canvas/window listeners. This closes only the outcome
lifecycle; registration-epoch ownership and transactional twelve-listener registration remain the
separate ordered R11 follow-ups.

## Focused evidence

- The predecessor fails the new source contract before evidence allocation because it has no
  outcome-aware `setCursorGrab` override (`20260825T201735-1749728`). The final source contract
  passes pending/active/error/loss/blur/disposal, active-only saturated motion, and 21 fail-closed
  mutations (`20260825T202047-1751793`).
- The real WasmFS/PROXY_TO_PTHREAD harness compiles (`20260825T202212-1753040`) and a headless
  Chromium run proves Pending keeps actual GHOST mode disabled, activation publishes Wrap,
  external loss restores absolute `(44,55)` motion, error and blur cancel, disposal exits the lock,
  and replacement begins inactive (`20260825T202307-1753671`). Existing focus-reset and window
  disposal/replacement browser cases remain green (`20260825T202410-1754261` and
  `20260825T202410-1754262`).
- The integrated matrix passes the 21-mutation Pointer Lock and 19-mutation/twelve-listener window
  lifecycle contracts; native and wasm32 output remains byte-identical at 5,139 bytes,
  SHA-256 `94588fb0021d722055e52e70594f869bb5f3a294afcf378aa843d059fc158ce5`
  (`20260825T202426-1755364`).

## Product and gates

- The optimized `/windowed.html` product relinks and then ends exact no-work
  (`20260825T202545-1757028` and `20260825T202952-1761082`). Strict OFF preflight binds JavaScript
  678,469 bytes/SHA-256 `d4e5b2f890f9`, Wasm 119,029,490 bytes/`44876024f22a`, and data
  167,143,248 bytes/`09e58a25849e` (`20260825T202956-1761134`). `/windowed.html` (and `/` under
  the default development server) remains the intended production entry point. The relink used the
  preserved dirty integration tree; unrelated pre-existing shell, first-pixel-settle, and fallback
  device-limit edits were neither altered nor included in `32640eb`.
- In headed Chromium under Xvfb, the same baked product boots, presents, enters middle-drag Wrap,
  loses the DOM lock externally, reacquires on a second gesture, and releases cleanly. The first
  gesture advances 28 WM ticks/3 presents and recovery advances 35 ticks/3 presents, with zero
  present submission/transaction rejection and zero device loss (`20260825T202903-1759622`). This
  forced fallback-software run is diagnostic-nonreceipt evidence.
- Required M4 remains red only at the unchanged unsupported hardware binding. Container-backed
  regression restores M0 6/6 green while M1–M8 retain their existing strict receipt, artifact,
  hardware, run-label, and release boundaries. Canonical replay and REUSE 6.2.0 are green
  (`20260825T203123-1762740` and `20260825T203516-1765961`).

The run created no adapter, profile, split product, live hardware receipt, result promotion,
dependency decision, deferral, tolerance, golden, blacklist, or promise. Mesa dzn and Windows were
not attempted, WSL was not restarted, and the s7 blocker remains `no conformant hardware Vulkan
ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`.
