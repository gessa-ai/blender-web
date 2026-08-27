<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-E resize trace/layout binding — 2026-08-27

## Outcome

The exact-product resize repro now binds `overlay_background` to Blender's live
`VIEW_3D`/`WINDOW` region instead of comparing every draw target with the browser canvas. This
turns the round-4 trace correction into an executable regression boundary while leaving the
relinked `e3d284c7da0e` hardware candidate byte-identical.

## Contract

The existing Blender Python timer now emits a focused machine-readable layout marker after each
WM relayout. For shrink and restore separately, the consumer selects the latest marker at the
committed window extent and requires every traced `overlay_background` draw to:

- remain an offscreen target;
- match the live `VIEW_3D` `WINDOW` region width and height; and
- cover that region from viewport origin zero.

The same consumer requires `OCIO_Display` to remain a direct full-window draw. This rejects the
proposed `900x547 -> 1100x640` substitution: `900x547` is the correct resized viewport region, not
a stale canvas extent.

## Evidence

- Fail-first missing layout parser: `ledger/buildlogs/20260827T091557-1846705.log`.
- Final 28-mutation trace self-check and 14-mutation resize source contract:
  `ledger/buildlogs/20260827T091934-1849492.log` and
  `ledger/buildlogs/20260827T091934-1849480.log`.
- Pinned Node syntax: `ledger/buildlogs/20260827T091934-1849484.log`.
- Exact relinked fallback product shrink/restore: `ledger/buildlogs/20260827T091755-1848021.log`;
  ticks `266/591/896`, presents `10/23/38`, episodes `0/1/2`, redraw presents `13/15`, eleven
  parsed traces, and zero rejection/loss.
- REUSE 6.2.0: `ledger/buildlogs/20260827T092025-1849896.log`.
- Required container-backed regression at `2026-08-27T09:21:14Z` restores M0 6/6; M4 remains
  honestly red at the exact-generation hardware binding, with the existing M1-M8 boundaries.

This is a diagnostic/semantic contract, not pixel evidence. P0-E remains open until the driver
records 10/10 consecutive Apple hardware shrinks with full idle scene content against the exact
candidate generation.
