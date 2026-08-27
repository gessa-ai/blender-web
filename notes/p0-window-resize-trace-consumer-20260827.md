<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-E resize draw-trace consumer hardening — 2026-08-27

## Outcome

Commit `9f5037e` closes a diagnostic-consumer gap in the P0-E exact-product repro. The baked
episode trace already emitted full `any`, `overlay_background`, and `OCIO_Display` draw plans, but
`live_resize_repro.mjs` parsed only the surface/configured/requested/backbuffer prefix. A run could
therefore pass while re-presenting one retained buffer, while a named pass never encoded again, or
while its direct window target/scissor remained stale.

The consumer now parses every plan and requires, independently for shrink and restore:

- contiguous trace samples and increasing presentation numbers;
- monotonic all/window draw counts which advance before the episode ends;
- the latest plan sequence to equal the all-draw count;
- more than one fresh `overlay_background` and `OCIO_Display` sequence;
- every direct-window plan to target the committed canvas extent; and
- every enabled scissor to remain contained in its actual render target.

Malformed or omitted plan text remains fail-closed through the existing parsed-line/count equality.
This makes patch 0286 capable of distinguishing fresh region encoding from repeated presentation
of a retained buffer without treating presentation logs as pixel evidence.

## Verification

- Fail-first rejected the prefix-only consumer:
  `ledger/buildlogs/20260827T065403-1733087.log`.
- Final eight-source/19-mutation trace contract and JavaScript syntax are green:
  `ledger/buildlogs/20260827T065632-1734891.log` and
  `ledger/buildlogs/20260827T065632-1734892.log`.
- The exact relinked CAPTURE product (`wasm.orig` SHA-256
  `aed9ba633f08b02d5fecaa461713cfbc2fabe880c0aad09ab3b88d037e47863a`) passes shrink and restore
  with ticks `246/497/747`, presents `17/36/54`, episodes `0/1/2`, bounded resize presentations
  `19/18`, and 37 fully parsed rows whose named plans advance, use current direct targets, and keep
  scissors contained: `ledger/buildlogs/20260827T065637-1734939.log`.
- Pinned REUSE 6.2.0 is green:
  `ledger/buildlogs/20260827T070002-1737420.log`.
- Direct M4 remains strictly RED at its pre-existing hardware binding boundary:
  `ledger/buildlogs/20260827T065738-1735540.log`.
- Direct regression retains the named APPLY/browser/tier boundaries:
  `ledger/buildlogs/20260827T065748-1735641.log`.

## Boundary

No C++ or shipping byte changed, so no relink was needed and the CAPTURE hash is unchanged. The
fallback run is diagnostic non-receipt evidence. P0-E remains open until the driver-operated Apple
M4 Pro rig passes 10/10 consecutive zero-input shrinks with full grid, Cube, and gizmo pixels.
No APPLY/public bundle, tag, profile, receipt, result promotion, tolerance, golden, blacklist,
deferral, promise, or launch claim changed.
