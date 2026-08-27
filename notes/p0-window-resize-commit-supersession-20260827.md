<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-E resize commit-time barrier supersession — 2026-08-27

## Outcome

Commit `f529943` makes a newer coherent backbuffer commit retire an older scheduled or ready resize-present barrier
before GHOST can present it. The commit returns its monotonic redraw episode, stores that episode
on the replacement backbuffer, and only then performs one mutex-protected stale-barrier
cancellation. Releasing the older barrier before the replacement episode is bound is forbidden:
its completion can drain queued work synchronously.

This closes a runtime gap behind the existing resize-drag model. Previously, a barrier that became
ready just before the replacement commit remained eligible in `swapBufferRelease()`, whose
`presentBackbuffer()` samples the current backbuffer. It could therefore copy the untouched new
texture while attributing the present to the old episode, producing a validation-clean black
frame.

## Evidence

- The fail-first native target rejected the old API because episode publication returned no bound
  generation and exposed no commit-time stale-barrier cancellation
  (`20260827T162142-2209803`).
- The final source contract reports 53 rejected mutations, including absent and misordered
  cancellation (`20260827T162503-2212273`). The focused native behavior target passes 48 cases
  (`20260827T162503-2212272`).
- The full integrated WebGPU suite passes byte-identically on native and wasm32
  (`20260827T162639-2215100`).
- The locked CAPTURE relink passes (`20260827T162656-2217018`). The exact fallback product then
  shrinks and restores at ticks `246/523/617`, presents `17/18/19`, episodes `0/1/2`, with one
  barrier and one immutable completed-frame trace per resized extent and zero rejection/loss
  (`20260827T162824-2217652`). This is diagnostic software-adapter evidence only.
- CAPTURE preflight, Apple producer 42/17 self-check, independent consumer 2/13 self-check, and
  capture-profile self-check are green (`20260827T162920-2218943` through
  `20260827T162920-2218952`).
- The committed source graph is locked no-work (`20260827T163114-2219683`). Direct M4 remains
  hardware-pixel red (`20260827T163121-2219722`); the authoritative pinned-container regression
  restores M0 6/6 while retaining the named M1-M8 receipt/APPLY/hardware/product boundaries
  (`20260827T163137-2220736`).

## Relinked CAPTURE generation

- `blender_browser.js`: 707,565 bytes,
  `5b6ed02286fda34d4483734d23e347f3439dad985150463faad82c5f449d5214`
- `blender_browser.wasm`: 120,508,976 bytes,
  `71bfa062dada224503438803537a8aa1e0f87e1ed6fd93324a699b58ed388065`
- `blender_browser.wasm.orig`: 119,155,652 bytes,
  `fea3977234ce87dda439109d97a1b1d1551b15e3eee6cc1de022bd698df0fdce`
- `blender_browser.data`: 168,637,598 bytes,
  `095d0ba748c3cdc2fcd0956def221e0f0d347d41d95e0a150a28670ab1cea24c`
- `blender_browser.split-build.json`: 13,251 bytes,
  `b45308a7152705c6e58f5860949a0f492d5c4a24ff60792d93945f9843f7f70b`

## Boundary

P0-E remains open. Only the driver-operated Apple M4 Pro producer and independent consumer passing
10/10 consecutive zero-input shrinks with stable grid, Cube, and gizmo pixels can close it. No
APPLY build, public bundle, tag, hardware receipt, result, promise, or launch claim is authorized
by this device-free candidate.
