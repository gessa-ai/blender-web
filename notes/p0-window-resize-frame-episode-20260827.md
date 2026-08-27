<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-E resize frame-episode binding — 2026-08-27

## Outcome

Commit `f5e1f19` closes a remaining time-of-check/time-of-use hole in the completed-frame barrier's
generation boundary. The first frame-episode candidate sampled the persistent backbuffer texture,
format, extent, and redraw episode through separate calls. Each call entered GHOST's owner callback
lifetime independently, so an `AllowSpontaneous` replacement commit could interleave them. A frame
could adopt the previous texture while carrying the replacement episode, become eligible at the
queue tail, and copy an untouched new backbuffer. That is the rejected round-six candidate's
deterministic 3,458-byte all-black failure shape without a WebGPU validation error.

GHOST now publishes a `BackbufferFrameSnapshot` containing texture, format, extent, and committed
redraw episode under one callback-lifetime execution token. The asynchronous resize callback
records the generation in the same protected commit that replaces the handle and extent.
`WGPUContext::sync_backbuffer()` adopts that snapshot and carries its episode through frame
completion; `begin_frame()` no longer independently resamples global generation. Only a frame
whose adopted snapshot still matches the current episode may schedule the barrier. Offscreen
contexts remain ineligible, and a late commit is retried by the existing bounded redraw episode.

Commit `131b153` closes a separate time-of-observation hole in that diagnostic. The old logger
sampled mutable draw state during the synthetic WindowUpdate used to present a ready barrier; CPU
encoding for that later frame could advance the plans even though its submissions remained queued
behind the barrier. `end_frame()` now stores the exact completed-frame snapshot with the barrier.
It remains available after the 180-tick heartbeat stops, same-episode duplicates cannot overwrite
it, and completion/cancellation clears it. This does not extend drawing or presentation. The
exact-product fallback waits on real episode and uncapped-presentation progress within the same
24-second ceiling as the hardware producer.

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
- The predecessor fails the atomic-snapshot contract at all six adoption fields, the GHOST
  snapshot/lifetime gate, commit publication, and the forbidden frame-start resample
  (`20260827T144747-2130053`). The final source verifier reports 58 checks and rejects 33
  mutations (`20260827T150133-2144314`). Patch 0290 reverse-applies exactly
  (`20260827T145231-2133162`); canonical replay and receipt self-check bind patch SHA-256
  `319c38d205aa2c373b132da26a24db9e4be4c6d90bb9eb143880bc8e1de35c19`
  (`20260827T150133-2144322`, `20260827T150133-2144332`).
- The complete native/wasm32 GPU matrix remains byte-identical
  (`20260827T150133-2144315`). The exact fallback product shrinks and restores at ticks
  `246/524/618`, presents `16/17/18`, episodes `0/1/2`, one barrier present per extent, and 18
  complete/current/contained/VIEW_3D-bound trace rows with zero rejection or device loss
  (`20260827T145651-2139775`). This is software-adapter diagnostic evidence only.
- The locked relink produces this exact CAPTURE generation and the committed runtime state is a
  locked no-op (`20260827T145503-2138195`, `20260827T150215-2146044`).
- CAPTURE preflight, capture-profile self-check, hardware producer 37/17, independent consumer
  2/13, and REUSE 6.2.0 are green (`20260827T145858-2141483`,
  `20260827T145858-2141484`, `20260827T145858-2141489`, `20260827T145858-2141496`,
  `20260827T150133-2144344`). Direct M4 remains red only at its unsupported hardware binding
  (`20260827T150012-2142273`); pinned-container regression restores M0 6/6 and preserves the named
  later receipt/APPLY/hardware/product boundaries (`20260827T150037-2142751`).
- The post-candidate full-screen retry contract binds the ready barrier's synthetic
  `GHOST_kEventWindowUpdate` through Emscripten's `NC_SCREEN | NA_EDITED` notifier before ordinary
  window invalidation. Its six-source verifier reports 65 checks and rejects 36 mutations
  (`20260827T151335-2154130`); the draw-trace self-check and native/wasm32 GPU matrix remain green
  (`20260827T151346-2154200`, `20260827T151346-2154195`). Pinned REUSE 6.2.0 is green
  (`20260827T151420-2155636`). Direct M4 remains hardware-pixel red
  (`20260827T151503-2156629`), while container-backed regression restores M0 6/6 and preserves
  every named later boundary (`20260827T151511-2156708`). Commit `06732e5` changes no runtime byte.
- A fail-first audit proved the present logger sampled mutable live plans after the synthetic
  WindowUpdate had encoded later work behind the ready barrier (`20260827T152459-2163682`,
  `20260827T152504-2163739`). Commit `131b153` captures the draw snapshot at the exact
  `end_frame()` barrier schedule instead. Duplicate same-episode scheduling cannot overwrite it;
  ready exposes it; completion/cancellation clear it. Final source/trace contracts, the 47-mutation
  redraw contract, native/wasm32 GPU matrix, canonical replay/receipt self-check, patch reverse
  check, and REUSE 6.2.0 are green (`20260827T152622-2164145`,
  `20260827T152622-2164146`, `20260827T153031-2168791`,
  `20260827T153025-2168659`, `20260827T153025-2168660`,
  `20260827T153440-2173379`, `20260827T153440-2173384`).
- The locked relink and committed-state no-work are green (`20260827T153109-2170631`,
  `20260827T153627-2175362`). The exact fallback product shrinks/restores at ticks
  `246/526/619`, presents `17/18/19`, episodes `0/1/2`, with one synchronous barrier present and
  one immutable completed-frame trace per extent (`20260827T153238-2171940`). CAPTURE preflight,
  hardware producer 37/17, independent consumer 2/13, and capture-profile self-check are green
  (`20260827T153339-2172604`, `20260827T153339-2172605`,
  `20260827T153339-2172609`, `20260827T153339-2172616`). This is software-adapter diagnostic
  evidence only. Direct M4 remains hardware-pixel red (`20260827T153349-2172765`); pinned-container
  regression restores M0 6/6 while keeping M1-M8 at their named boundaries
  (`20260827T153504-2174213`).

## Relinked CAPTURE generation

- `blender_browser.js`: 707,565 bytes,
  `5b6ed02286fda34d4483734d23e347f3439dad985150463faad82c5f449d5214`
- `blender_browser.wasm`: 120,508,312 bytes,
  `85ff089d4e87589c6b36a63fdaa76e3365ae94c6882cc5549607a3eaeff88b44`
- `blender_browser.wasm.orig`: 119,154,997 bytes,
  `4b279e0e152fb2b0aca77701feac429090f3ae02920457d2e69ca801750d1b64`
- `blender_browser.data`: 168,637,598 bytes,
  `095d0ba748c3cdc2fcd0956def221e0f0d347d41d95e0a150a28670ab1cea24c`
- `blender_browser.split-build.json`: 13,251 bytes,
  `b7d833a30436fba9470f84f4f32e6841ca057b584e2ac23e3d61edf3c9e58672`

## Boundary

P0-E remains open. This candidate may close only after the driver-operated Apple M4 Pro producer
and independent consumer report 10/10 consecutive zero-input shrinks with stable grid, Cube, and
gizmo pixels. No APPLY build, public bundle, tag, profile, receipt, result, tolerance, golden,
blacklist, promise, or launch claim is authorized by the device-free evidence.
