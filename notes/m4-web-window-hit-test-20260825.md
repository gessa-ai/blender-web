<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 web window-under-cursor bounds — 2026-08-25

## Outcome

Commit `e113f1a` closes a false window hit in the single-canvas GHOST system. The previous
`GHOST_SystemWeb::getWindowUnderCursor()` ignored both supplied coordinates and returned the active
canvas window for every point. That contradicted the pinned `GHOST_ISystem.hh` contract, which
requires null when no owned window is under the point, and differed from the base implementation's
client-bounds test.

The web override now rejects a detached window, reads the active window's live logical client
bounds, and returns the window only when `GHOST_Rect::isInside()` accepts the supplied screen point.
This uses the existing web invariant that screen and client coordinates share the canvas origin and
retains GHOST's inclusive boundary semantics.

## Evidence

- Before the source change, the real WasmFS + `PROXY_TO_PTHREAD` browser harness returned mask 15:
  the active/non-empty, left-top, right-bottom, and center checks passed, while all four exterior
  points falsely resolved to the window. The rebuilt final harness returns all eight bits and also
  preserves disposal, callback rebinding, replacement publication, and input delivery
  (`20260825T193345-1707510`).
- An isolated `git archive` of exact commit `e113f1a` passes the pinned-interface/base/web/harness
  contract. All 10 mutations fail closed, covering the null guard, client-bounds acquisition,
  containment predicate, null tail, accepted harness action, every exterior edge, and browser
  verdict (`20260825T193526-1709455`).
- The post-commit integrated native/wasm32 gate remains byte-identical at 5,139 bytes, SHA-256
  `94588fb0021d722055e52e70594f869bb5f3a294afcf378aa843d059fc158ce5`; the new contract is part of
  that gate (`20260825T193358-1707727`).
- The live integration tree contained a pre-existing unstaged first-pixel-settle edit in the same
  source file; it was explicitly excluded from `e113f1a`. With that preserved tree, the optimized
  product relinked and then ended exact no-work (`20260825T192718-1698992`,
  `20260825T192805-1699400`). OFF preflight binds 675,313-byte JavaScript, 119,028,279-byte Wasm,
  and 167,143,248-byte data (`20260825T192842-1699751`).
- The same integration product reaches running `WM_main` on the forced fallback diagnostic, updates
  its title, advances 77 idle ticks, and advances 10 ticks plus one presentation after trusted
  input, with zero rejected present submissions, rejected present transactions, or device loss
  (`20260825T192902-1700666`). This is explicitly diagnostic-nonreceipt evidence.
- Focus reset, fullscreen, clipboard, IME, and custom cursor browser checks stayed green. A
  supplemental headed pointer-lock rerun lost Chromium's X/GPU process during initialization;
  headless Pointer Lock cannot satisfy the relative-motion assertion. It is not acceptance evidence;
  the unchanged 13-mutation pointer-lock contract and the real-product input/presentation diagnostic
  remain green.

## Gate boundary

Pinned REUSE 6.2.0 is green for the final recorded tree at 2,575/2,575 files
(`20260825T193637-1710667`). The required M4 scope remains red only at its unchanged unsupported
hardware binding, and the corrected container-backed regression restores M0 to 6/6 while M1-M8
retain their strict receipt, split-product, browser/hardware, run-label, and release boundaries at
`2026-08-25T19:31:08Z`.

No adapter, device, profile, split product, live receipt, result promotion, dependency decision,
deferral, tolerance, golden, blacklist, or promise changed. Dzn, Windows Edge, and WSL restart were
not attempted. The s7 blocker remains `no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships
none; Mesa dzn rejected by Dawn)`.
