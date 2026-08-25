<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 web capability closure — 2026-08-25

## Outcome

Commit `315a6d6` stops GHOST-web from advertising two platform contracts the browser cannot
satisfy. DOM exposes wheel deltas after the operating system applies its scroll preference, not a
raw physical trackpad direction, and an HTML canvas has no server-owned window frame or decoration.
`GHOST_kCapabilityTrackpadPhysicalDirection` and
`GHOST_kCapabilityWindowDecorationServerSide` are therefore now excluded.

Implemented `GHOST_kCapabilityInputIME` and `GHOST_kCapabilityCursorRGBA` remain advertised. No
input event, window behavior, GPU path, classifier, tolerance, or receipt boundary changed.

## Evidence

- The fail-first three-source contract rejects the predecessor at the absent physical-direction
  exclusion (`20260825T190855-1678884`). The final focused run passes and rejects six independent
  mutations across both unsupported bits, both implemented bits, the DOM wheel event type, and the
  canvas/client bounds identity (`20260825T190941-1679493`). An exact-commit replay of the same
  contract is green after `315a6d6` (`20260825T191550-1687807`).
- The full integrated pipeline/GHOST matrix includes the new contract and remains native/wasm32
  byte-identical at 5,139 bytes, SHA-256 `94588fb0021d`, with source SHA-256
  `61bb3e102e75` (`20260825T191014-1680457`).
- Locked Ninja recompiles the real `GHOST_SystemWeb.cc` product object and relinks
  `blender_browser`, then ends exact no-work (`20260825T191107-1682950` /
  `20260825T191155-1683388`). Strict OFF preflight passes with 675,313-byte JavaScript,
  119,028,150-byte Wasm, and 167,143,248-byte data (`20260825T191217-1683565`); their SHA-256
  prefixes are `b466be26eb40`, `7408d654cfb3`, and `09e58a25849e`.
- The same product reaches sustained WM progress on Chromium's explicitly nonreceipt fallback
  adapter. Trusted input advances ten ticks and two presentations in 122 ms, with zero rejected
  submissions, rejected transactions, stage-1/import failures, or device loss
  (`20260825T191251-1684657`).
- Final REUSE 6.2.0 covers 2,573/2,573 files (`20260825T191649-1688169`). Required M4 remains red at
  its unsupported binding, and authoritative container regression restores M0 6/6 green while
  M1–M8 retain their existing strict receipt, split-product, browser, hardware, and release
  boundaries (`20260825T191458-1686714` / `20260825T191502-1686787`).

No adapter, device, profile, split product, accepted receipt, result promotion, dependency,
deferral, tolerance, golden, blacklist, or promise changed. dzn and Windows were not attempted,
WSL was not restarted, and the named s7 blocker remains `no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn)`.
