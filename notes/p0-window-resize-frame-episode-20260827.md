<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-E resize frame-episode binding — 2026-08-27

## Outcome

Commit `5a48bb4` corrects the completed-frame barrier's generation boundary. The rejected
`2f45a8ed62eb` Apple candidate read `redraw_episode_generation()` only in
`WGPUContext::end_frame()`. A replacement backbuffer can commit after a browser frame has already
activated and begun encoding against the previous drawable. That old frame was then mislabeled as
the first complete frame of the new episode; when the barrier became ready, GHOST copied the
untouched replacement backbuffer while the genuine new-extent submissions remained queued behind
it. The deterministic 3,458-byte all-black round-six result follows without a WebGPU validation
error.

The window context now captures the redraw episode at `begin_frame()` and may schedule the resize
barrier only when that frame-start episode still matches the current episode at the queue tail.
Offscreen contexts cannot schedule the window barrier. A late commit is retried by the existing
bounded redraw episode, so the next frame activates and adopts the replacement backbuffer before
it becomes eligible.

The retained draw-plan diagnostic now remains available to a ready barrier after the ordinary
180-tick capture heartbeat has stopped. This does not extend drawing or presentation; it only lets
a slow barrier present emit the already-bounded snapshot. The exact-product fallback diagnostic
waits on real episode and uncapped-presentation progress within the same 24-second ceiling as the
hardware producer instead of freezing evidence at an unrelated six-second delay.

## Evidence

- The predecessor fails the new source contract at the absent frame-start member, capture, window
  guard, and episode match (`20260827T140145-2091510`). The final five-source contract reports 39
  checks and rejects 24 mutations (`20260827T140459-2093330`).
- The redraw-recovery contract rejects 45 mutations, including an always-true frame match, and the
  native/wasm32 integrated GPU suite exercises three frame/current-generation cases alongside all
  scheduler/barrier rejection and supersession paths (`20260827T141700-2103744`).
- Canonical source freeze/replay retains 20,258 entries at patch SHA-256
  `8f59704d0eefbd07c7e4ba9e2d6da3928d9cef7ebd9c96ae1bca988baed1f11a` and manifest SHA-256
  `ade96622e26fdeb866d4fe96c8aab0162af16d68eb41930028fab87cfa3668df`
  (`20260827T140545-2093682`, `20260827T140637-2094835`). Patch 0290 reverse-applies exactly to
  the live source. The optional numbered-history replay remains blocked earlier at the pre-existing
  patch 0016 drift (`20260827T140640-2094834`).
- The relink succeeds through the locked Ninja wrapper (`20260827T141406-2101664`). Its exact
  fallback product shrinks and restores with ticks `246/519/607`, presents `16/17/18`, episodes
  `0/1/2`, one barrier present per extent, 18 complete/current/contained/VIEW_3D-bound trace rows,
  and zero scissor, encode, submit, transaction, or device-loss rejection
  (`20260827T141610-2103171`). This is software-adapter diagnostic evidence only.
- Hardware producer and independent receipt-consumer self-checks, CAPTURE preflight, committed-state
  locked no-work, and REUSE 6.2.0 are green (`20260827T141710-2105032`,
  `20260827T141710-2105051`, `20260827T141929-2107660`, `20260827T141929-2107661`,
  `20260827T141726-2105183`). Container-backed regression restores M0 6/6 while M1-M8 retain their
  named strict profile/APPLY/hardware/product boundaries (`20260827T141818-2105871`).
- A post-handoff fail-first mutation proved the old source verifier allowed
  `WGPUContext::activate()` to omit `sync_backbuffer()` (`20260827T143416-2117985`). The final
  contract binds ordered activation/adoption plus `wm_window_make_drawable()` before frame start
  and rejects 27 mutations across 44 checks (`20260827T143522-2119087`). The native/wasm32
  integrated queue suite remains byte-identical and the eight-source trace contract still rejects
  all 35 mutations (`20260827T143603-2119429`, `20260827T143603-2119434`); REUSE 6.2.0 is green
  (`20260827T143756-2122037`). Direct M4 remains red at its hardware-pixel binding
  (`20260827T143835-2122317`), and the pinned-container regression restores M0 6/6 while preserving
  every later named boundary (`20260827T143913-2122901`). This changed no runtime or CAPTURE
  artifact.

## Relinked CAPTURE generation

- `blender_browser.js`: 707,565 bytes,
  `5b6ed02286fda34d4483734d23e347f3439dad985150463faad82c5f449d5214`
- `blender_browser.wasm`: 120,506,270 bytes,
  `1cfff18d313f6e99f06066d19a974e35165f2b0e6dc8379cd9a0fae9b83ecdac`
- `blender_browser.wasm.orig`: 119,152,955 bytes,
  `6fb76b7f760930385cb6be4b18f828c6fca1cfae02e65ce240e72ae78568cdfa`
  (136,772 defined functions)
- `blender_browser.data`: 168,637,598 bytes,
  `095d0ba748c3cdc2fcd0956def221e0f0d347d41d95e0a150a28670ab1cea24c`
- `blender_browser.split-build.json`: 13,251 bytes,
  `1580fd549bf3b60c5ac6bdae34b8df87a503eec0535836d4f736a97b970a3fc3`

## Boundary

P0-E remains open. This candidate may close only after the driver-operated Apple M4 Pro producer
and independent consumer report 10/10 consecutive zero-input shrinks with stable grid, Cube, and
gizmo pixels. No APPLY build, public bundle, tag, profile, receipt, result, tolerance, golden,
blacklist, promise, or launch claim is authorized by the device-free evidence.
