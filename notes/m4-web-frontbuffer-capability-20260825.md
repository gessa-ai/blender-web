<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 web front-buffer capability — 2026-08-25

## Outcome

Commit `c9502ee` stops GHOST-web from advertising synchronous front-buffer reads. The browser
WebGPU implementation cannot satisfy that contract: its compatibility `read_sub()` arm kicks an
owned request and can consume it only after a later event-loop turn. Blender's stock
`WM_window_pixels_read_sample()` treats the capability-selected front-buffer call as immediate
success, so the old flag accepted the deterministic interim buffer and bypassed the pending/ready
window-color continuation.

The backend now masks only `GHOST_kCapabilityGPUReadFrontBuffer`. Native backends retain their
existing behavior; browser eyedroppers and window capture select the already-verified owned async
paths. No data path, tolerance, adapter classifier, or receipt boundary changed.

## Evidence

- The fail-first contract rejects the predecessor because the Web exclusion mask omits the flag
  (`20260825T185424-1664418`). Final verification binds the GHOST mask, Blender's exact
  flag-controlled synchronous branch, the eyedropper pending/settled fallback, and the
  Emscripten kick/take implementation; all six mutations fail closed
  (`20260825T185532-1664911`).
- The full integrated pipeline/GHOST matrix passes the new contract and remains native/wasm32
  byte-identical at 5,139 bytes, SHA-256 `94588fb0021d`, with source SHA-256
  `f35115b36b8e` (`20260825T185701-1666469`).
- Locked Ninja recompiles the real `GHOST_SystemWeb.cc` product object and relinks
  `blender_browser`, then ends exact no-work (`20260825T185556-1665154` /
  `20260825T185642-1666304`). Strict OFF preflight is green
  (`20260825T185751-1668102`). The artifacts are 675,313-byte JavaScript at SHA-256
  `b466be26eb40`, 119,028,151-byte Wasm at `a750fc5d654e`, and 167,143,248-byte data at
  `09e58a25849e`.
- The same product reaches sustained WM progress on Chromium's explicitly nonreceipt fallback
  adapter. Trusted input advances three ticks and one presentation in 26 ms with zero rejected
  presentation submissions, rejected presentation transactions, or device loss
  (`20260825T185826-1668403`).
- Required M4 remains honestly red only at the unsupported strict hardware binding
  (`20260825T185902-1669706`). The authoritative pinned-container regression restores M0 to 6/6
  green while M1-M8 retain their existing strict manifest, split-product, browser, hardware, and
  release boundaries (`20260825T185929-1670186`). Final REUSE 6.2.0 covers 2,571/2,571 files
  (`20260825T190311-1673296`).

No adapter, device, profile, split product, accepted receipt, result promotion, dependency
decision, deferral, tolerance, golden, blacklist, or promise changed. dzn and Windows were not
attempted, WSL was not restarted, and the named s7 blocker remains `no conformant hardware Vulkan
ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`.
