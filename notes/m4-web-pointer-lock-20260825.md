<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 web Pointer Lock cursor grab — 2026-08-25

## Outcome

Commit `b09aa76` replaces `GHOST_WindowWeb::setWindowCursorGrab()`'s unconditional-success no-op
with browser Pointer Lock behavior. Wrap and hide request a lock and accept Emscripten's deferred
user-activation result; disable exits or cancels the request, normal preserves unlocked visible
pointer behavior, and unknown modes fail. Wrap advertises Blender's software cursor while hide
remains invisible.

While a warp-style grab is active, the event bridge consumes `movementX/Y` and advances the
window's virtual cursor with signed-int saturation. Absolute cursor positioning remains
unsupported: `setCursorPosition()` still fails and `CursorWarp` remains absent from the capability
mask. The change therefore enables continuous viewport navigation without claiming browser
absolute-warp behavior.

## Focused evidence

- The pre-fix real harness returned success but never acquired Pointer Lock, timing out at
  `document.pointerLockElement` (`20260825T154928-1476214`). The final shipping-topology harness
  build is `20260825T161243-1501884`.
- Headless Chromium proves wrap entry, relative `(37,-19)` motion, virtual position `(159,83)`,
  invalid-mode rejection, and disable/exit in one complete run (`20260825T161258-1502045`). A
  headed Chromium run independently proves wrap entry and the same relative/virtual motion
  (`20260825T161303-1502214`). The existing four-state fullscreen browser regression remains
  green (`20260825T161309-1502555`).
- The integrated production-source contract covers normal, wrap, hide, disable, deferred entry,
  relative saturation, software-cursor policy, and the intentionally absent absolute-warp
  capability. All 13 mutations fail closed, and native/wasm32 transaction output remains
  byte-identical at 5,139 bytes, SHA-256
  `94588fb0021d722055e52e70594f869bb5f3a294afcf378aa843d059fc158ce5`
  (`20260825T161314-1502931`).

## Product and gate evidence

- Locked Ninja relinks the optimized product and then ends exact no-work
  (`20260825T161333-1504242`, `20260825T161533-1506545`). Strict OFF preflight binds JavaScript
  668,330 bytes/SHA-256 `fa99e4d4b60af292d9036ee319988044b0b164251dd71937f5cb3adb87643e9d`,
  Wasm 119,017,370 bytes/`55561aa94795dbe7ef7cdbd5f36166caa9f4040b37f7e595e942c4f41a8fba81`,
  and data 167,143,248 bytes/`09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`
  (`20260825T161551-1506749`).
- Against that real product, a trusted middle-button drag enters wrap Pointer Lock, advances 28
  WM ticks and three presentations, and reports zero present rejections or device loss
  (`20260825T161500-1506035`). The earlier post-P0 relink liveness run also reaches `WM_main` with
  sustained idle/input progress and zero submission/transaction rejection or device loss
  (`20260825T160120-1489841`).
- The scoped M4 gate remains red only at its unsupported hardware binding
  (`20260825T161634-1507188`). Container-backed regression keeps M0 6/6 green while M1-M8 retain
  their existing strict receipt, split-product, browser, hardware, and release boundaries
  (`20260825T161704-1508377`). Final REUSE 6.2.0 covers 2,551/2,551 files
  (`20260825T162110-1511410`).

The headed product run used the fallback software adapter and is diagnostic-nonreceipt evidence.
It binds no adapter, profile, split product, pixel receipt, result promotion, dependency decision,
deferral, tolerance, golden, blacklist, or promise. Complete lock-to-release is green headlessly;
under headed WSLg, both GHOST disable and direct `document.exitPointerLock()` can close Chromium's
X connection, so headed evidence leaves the acquired lock active. That local browser/display-path
limitation does not weaken any receipt. The named s7 blocker remains `no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`; dzn and Windows were not
attempted, and WSL was not restarted.
