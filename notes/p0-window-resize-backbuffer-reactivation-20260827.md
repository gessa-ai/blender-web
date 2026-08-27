<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-E window backbuffer reactivation candidate — 2026-08-27

## Outcome

Patch 0287 makes browser WebGPU join Blender's existing Metal per-frame drawable reset. Before a
window draw, `wm_draw_update()` now clears the cached drawable identity for Emscripten WebGPU so
`wm_window_make_drawable()` must reactivate the GPU context. `WGPUContext::activate()` then runs
`sync_backbuffer()` and adopts the latest coherently committed replacement backbuffer before any
region draw is encoded.

This is a materially different candidate from the preceding invalidation fixes. The exact product
was already proving that a resize episode ran and presented about 19 times while Apple hardware
showed the same stale grey rectangle. The missing boundary was between those redraws and the
replaceable window attachment: with one persistent window, `wm_window_make_drawable()` skipped
activation while `windrawable` still named that same window. The WebGPU context therefore had no
guaranteed opportunity to adopt the replacement texture. Blender already forces the same
reactivation for Metal specifically so its latest backbuffer reaches the default framebuffer;
browser WebGPU has the same lifecycle requirement.

This is an implemented candidate, not hardware closure. The CAPTURE product still contains the
bounded draw-plan trace from patch 0286. P0-E remains open until the driver-operated Apple M4 Pro
rig passes 10/10 consecutive fresh-page shrinks from 1280x720 to 1100x640, with zero post-resize
input and full idle grid, Cube, and gizmo pixels. Any failing run must retain the episode trace for
the next diagnosis. No APPLY/public bundle or tag may be cut before that bar passes.

## Contract

`sandbox/m4-resize-recovery/verify_source.py` now binds both sides of the handoff:

- persistent WebGPU backbuffer adoption updates both default framebuffer extent caches;
- the browser-only WebGPU build is included in the per-frame drawable reset;
- native WebGPU is not broadened accidentally; and
- the reset occurs before the window draw loop.

Six isolated mutations cover the two extent caches, external-handle adoption, the WebGPU
condition, the Emscripten scope, and the actual reactivation call.

## Verification

- Fail-first rejected the absent browser WebGPU reactivation:
  `ledger/buildlogs/20260827T063313-1716451.log`.
- The final two-source contract is green with five checks and six mutations:
  `ledger/buildlogs/20260827T063333-1716594.log` and
  `ledger/buildlogs/20260827T063525-1718241.log`.
- Canonical replay is green at 264 patches and canonical snapshot SHA-256
  `efebc388d06e5c4eab0942a7db17b04f89bb803dd5bd14f8f5b5697bab4a8752`:
  `ledger/buildlogs/20260827T063542-1718447.log`.
- The optional numbered-history diagnostic stops at the pre-existing patch 0016 replay conflict,
  before patch 0287; it is not presented as green:
  `ledger/buildlogs/20260827T063525-1718242.log`.
- The locked `wm_draw.cc` product object compile is green:
  `ledger/buildlogs/20260827T063614-1718686.log`.
- Pinned REUSE 6.2.0 is green:
  `ledger/buildlogs/20260827T063642-1718970.log`.
- The repo-wide REUSE repeat after adding this evidence note is also green:
  `ledger/buildlogs/20260827T064730-1727774.log`.
- CAPTURE product preflight, capture-producer self-check, two-phase loader proof, and locked no-work
  replay are green at `20260827T063928-1720838`, `20260827T063928-1720840`,
  `20260827T063928-1720839`, and `20260827T063928-1720845`.
- The exact fallback product completes shrink and restore with ticks `246/497/747`, presents
  `16/34/53`, episodes `0/1/2`, redraw presentations `18/19`, 37 coherent trace rows, and zero
  scissor/encode/submit/transaction/device-loss failures:
  `ledger/buildlogs/20260827T063946-1720997.log`. This is diagnostic non-receipt evidence.
- Strict M4 remains RED at the exact-generation hardware binding boundary
  (`ledger/buildlogs/20260827T064104-1722388.log`). Pinned-container regression restores M0 6/6
  while M1-M8 retain their named strict receipt/APPLY/product boundaries
  (`ledger/buildlogs/20260827T064325-1724306.log`).

## Relinked CAPTURE generation

RELINKED windowed-opt @ `94cccc1` (`ledger/buildlogs/20260827T063747-1720034.log`):

| file | bytes | SHA-256 |
|---|---:|---|
| `blender_browser.js` | 707,565 | `9541470a7ee08e9963276fa2e73b6ddf73a65c5bd3efddc23a4ea67a3c1c33ca` |
| `blender_browser.wasm` | 120,501,395 | `bf09a9f563657ada1511ad8a665503243634b18e478563d8301a3a4f7571da7f` |
| `blender_browser.wasm.orig` | 119,148,240 | `aed9ba633f08b02d5fecaa461713cfbc2fabe880c0aad09ab3b88d037e47863a` |
| `blender_browser.data` | 168,637,598 | `095d0ba748c3cdc2fcd0956def221e0f0d347d41d95e0a150a28670ab1cea24c` |
| `blender_browser.split-build.json` | 13,251 | `6fd6951fa9afdf27d9159274b43fbde31eae17f73241fda21e6f4ad36b415698` |

The relink invalidates all earlier hash-bound profiles. No APPLY/public bundle, profile, hardware
receipt, result promotion, tolerance, golden, blacklist, deferral, tag, or launch claim changed.
