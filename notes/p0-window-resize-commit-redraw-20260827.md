<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-E coherent resize-commit redraw recovery — 2026-08-27

## Outcome

The CAPTURE product now starts a fresh bounded full-window redraw episode only after an
asynchronously validated replacement surface/backbuffer pair commits. This closes the race left by
`8744f4f`, where a resize-time update could consume the tail of an older episode before the new
extent was drawable and leave either stale overdraw or black pixels indefinitely.

This is implemented and relinked at `8f604ab`, not hardware-closed. The driver-operated Apple M4
Pro must still pass the filed 10/10 consecutive shrink test with full idle scene pixels and zero
intervening input. No APPLY product, public bundle, tag, profile, or receipt was produced.

## Driver evidence and root cause

The exact predecessor CAPTURE generation passed only 5/8 fresh 1280x720 -> 1100x640 attempts on
hardware. Two failures retained a flat old-extent grey overdraw above correctly positioned new-frame
grid/gizmo pixels, and one remained black; all three were stable for 24 seconds with zero WebGPU
rejection or later console activity.

`GHOST_SystemWeb::processEvents()` applied the shell extent, began asynchronous backbuffer/surface
validation, queued `GHOST_kEventWindowSize`, and published an ordinary redraw-readiness generation
in the same tick. `redraw_recovery_tick()` intentionally did not reset an active episode for that
ordinary signal. The resulting update could therefore run against the old persistent backbuffer on
the final tick of a prior episode. `GHOST_ContextWGPUWeb::ensureBackbuffer()` later committed the
coherent replacement inside its error-scope callback but published no invalidation. Whether the
resize happened just before or just after the old ceiling explains the measured mixed outcomes.

The stale grey rectangle was therefore retained old-generation content, not evidence that the
workbench background pass had a deterministic wrong extent or draw order.

## Fix and boundedness

`GHOST_WebDisplayState.hh` now separates two signals:

- shader/pipeline readiness remains an ordinary retry that may rearm a completed episode but never
  extend an active hard ceiling;
- a coherent drawable commit publishes a distinct monotonic episode generation that resets one
  fresh 180-tick budget, requests an immediate `GHOST_kEventWindowUpdate`, and then follows the
  existing 12-tick cadence.

Only `SurfaceResizeResult::Committed`, after the complete surface/backbuffer extent is published,
emits the fresh-episode signal. Rejected and superseded candidates cannot. Window publication
captures the current generation so a replacement window cannot consume stale work. The read-only
`bw_redraw_episode_count` export lets the live regression prove that each actual commit fired; it
does not drive behavior.

## Device-free evidence

- Fail-first native compile: `20260827T042717-1615935` rejects the missing episode API and widened
  recovery contract.
- Final focused behavior: `20260827T042814-1616246` passes 19 cases, including the exact
  final-old-tick/late-commit schedule and both generation wraps.
- Seven-source/39-mutation binding: `20260827T042938-1616723`; final native/Wasm integration matrix:
  `20260827T043342-1621994`.
- Exact fallback product shrink/restore: `20260827T043503-1624562` reports
  `ticks=246/497/748`, `presents=16/34/52`, `episodes=0/1/2`, `redrawPresents=18/18`, and zero
  scissor/encode/submit/transaction/device-loss failures.
- Ten fresh fallback-browser shrink/restore cycles against the relinked artifact all pass the same
  commit-generation boundary: `20260827T044246-1631630` reports `episodes=0/1/2`, 18–19 uncapped
  redraw presentations per resized extent, and zero scissor/encode/submit/transaction/device-loss
  failures in every cycle. This is scheduling stress evidence only; it does not replace the Apple
  semantic-pixel acceptance bar.
- Locked relink and committed-HEAD no-work replay: `20260827T043358-1623430` and
  `20260827T043707-1626482`.
- CAPTURE preflight, producer self-check (`positive=21`, `negative=23`, zero browser launches), and
  two-phase source proof: `20260827T043627-1625578`, `20260827T043627-1625580`, and
  `20260827T043627-1625579`.
- Required M4 remains RED at the absent exact-generation hardware receipt boundary:
  `20260827T043555-1625285`.
- Pinned REUSE 6.2.0 is green at 2,721/2,721 files: `20260827T043831-1627205`.
- Authoritative pinned-container regression restores M0 to 6/6 GREEN while M1–M8 retain their
  existing strict receipt/APPLY/browser/tier boundaries: `20260827T043831-1627206`.

## Relinked CAPTURE identity

RELINKED windowed-opt @ `8f604ab`:

- `blender_browser.js`: 707,565 bytes,
  SHA-256 `5ee75defbb1c23c91a3d81a10af95b501cb828634cfbf2df4dd9934ac56a7e15`;
- `blender_browser.wasm`: 120,498,031 bytes,
  SHA-256 `75f2da8cfd21b6ea4253cb0f2c074b21e37465fa41f1e1b2cbd947be8857951b`;
- `blender_browser.wasm.orig`: 119,144,886 bytes,
  SHA-256 `390062afea7c7117c40640b3259ae7328507c840ada80b62551f33ad992507f2`;
- `blender_browser.data`: 168,637,598 bytes,
  SHA-256 `095d0ba748c3cdc2fcd0956def221e0f0d347d41d95e0a150a28670ab1cea24c`;
- `blender_browser.split-build.json`: 13,251 bytes,
  SHA-256 `d4a41886917e82beff02d10fa53bd1ac8fa4314f1d7b2f09cc5b6ae672780b8f`.

The relink invalidates all earlier hash-bound CAPTURE profiles. Hardware closure requires the
driver's exact automated 10/10 zero-input shrink bar against this generation; only then may fresh
success and terminal profiles authorize APPLY.
