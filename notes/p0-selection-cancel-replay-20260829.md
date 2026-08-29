<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J selection external-cancel replay — 2026-08-29

## Outcome

Every terminal path of the browser selection continuation now restores the ordinary-input FIFO
before releasing its timer and GPU sessions. The normal success, Escape, timeout, queue-bound, and
backend-failure paths already did this; the registered WM `cancel` callback did not. Patch
`0310-view3d-web-selection-cancel-replay.patch` adds the missing external-cancel replay while
reusing the existing manager/window identity guard.

This closes one real input-loss seam but does not claim the deterministic Apple freeze is fixed.
The relinked CAPTURE product remains pending the unchanged 10/10 Apple slow/sparse check and the
same-generation P0-E interaction gauntlet.

## Experiment and fix

The exact pre-fix CAPTURE product first passed the isolated software sequence: first orbit, live
projected Cube click, real Cube selection, then an independent recovery orbit. Source teardown
inspection nevertheless found `view3d_select_cancel()` called `view3d_select_async_finish()`
directly. If the WM canceled the operator outside its modal method, every ordinary event retained
while the readback was pending was destroyed with `customdata`.

The fail-first contract required seven replay sites and exact replay-before-finish ordering in the
external cancel callback; the predecessor exposed only six. The fix obtains the existing
`View3DSelectAsyncData`, calls `view3d_select_async_events_requeue()` when present, then runs the
unchanged teardown. That helper already refuses a different manager or window, so cancellation
during context replacement cannot inject events into the replacement UI.

## Evidence

- fail-first exact teardown contract: `20260829T095136-4037442`
- final source and 20-mutation self-check: `20260829T095218-4038331` and
  `20260829T095218-4038348`
- native and Wasm `view3d_select.cc` object compiles: `20260829T095233-4038460` and
  `20260829T095233-4038459`
- canonical freezer, replay, and 18-mutation receipt self-check:
  `20260829T095319-4038858`, `20260829T095418-4040031`, and
  `20260829T095418-4040032`
- CAPTURE relink, locked no-work, and product preflight: `20260829T095448-4040458`,
  `20260829T095614-4041056`, and `20260829T095620-4041143`
- exact post-relink slow/sparse software control: first orbit 430 ms, Cube selection 10,399 ms,
  recovery orbit 2,459 ms, balanced GHOST/WM input, two retired rotates, and zero selection
  fallback/page/lifecycle errors (`20260829T095624-4041202`)
- adjacent retry/admission/validation, Apple producer/gauntlet self-checks, and REUSE 6.2.0:
  `20260829T095745-4042524`, `20260829T095745-4042525`,
  `20260829T095745-4042530`, `20260829T095745-4042539`,
  `20260829T095745-4042547`, and `20260829T095745-4042557`
- direct M4 remains honestly RED at its Apple binding, while pinned-container regression restores
  M0 6/6 and retains the named later boundaries: `20260829T095809-4042718` and
  `20260829T095821-4042857`

The optional numbered-history diagnostic remains independently stale at historical patch 0016;
the accepted canonical source replay is green and contains 305 exact paths.

## Candidate identity and closure bar

- implementation commit: `da29c42`
- `blender_browser.js`: `3a9cddbe853a` (712,328 bytes)
- `blender_browser.wasm`: `a6b48d9b618f` (120,350,792 bytes)
- `blender_browser.wasm.orig`: `63e188ba4232` (119,001,717 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `88b477d8a3e2` (14,448 bytes)

P0-I/J remain open. Closure requires this exact inventory to pass 10/10 clean Apple slow/sparse
runs with real Cube selection, two pixel-changing orbits, no visible artifact, no selection
fallback, and no page error, followed by the same-generation composed P0-E gauntlet. No hardware
receipt, profile, APPLY product, public bundle, tag, result promotion, promise, tolerance, golden,
blacklist, deferral, or launch claim changed.
