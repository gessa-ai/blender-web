<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J browser selection failure teardown — 2026-08-29

## Outcome

Browser selection backend failures no longer populate an operator report. Blender's window manager
opens a popup menu whenever a completed operator owns any report, regardless of severity; that
popup captured the ordinary events which the asynchronous selection continuation had correctly
replayed and made the product look permanently frozen. Patch
`0309-view3d-web-selection-failure-nonmodal.patch` keeps the failure visible through a bounded
console diagnostic, replays retained input, and cancels the failed pick without creating a modal
report surface. Native selection reports are unchanged.

This is a fail-safe around the diagnosed freeze, not permission to accept a failed selection. The
slow/sparse Apple producer now rejects both `WebGPU selection readback failed` and `WebGPU selection
continuation canceled`; any fallback diagnostic still makes the hardware run fail.

## Change

- all seven browser asynchronous selection failure exits use one WM-worker diagnostic helper;
- diagnostics are capped at 16 process-wide lines and flushed immediately;
- queue overflow, timer/readback timeout, particle-depth failure, and initial/modal GPU readback
  failure remain fail-visible without adding anything to `op->reports`;
- native timeout and particle/readback reports retain their existing `BKE_report` behavior;
- the exact slow/sparse producer rejects either bounded browser-failure spelling.

## Evidence

- fail-first source contract: `ledger/buildlogs/20260829T092848-4020484.log`
- final source/producer/patch contract (18-mutation self-check, then normal validation):
  `ledger/buildlogs/20260829T094300-4031397.log` and
  `ledger/buildlogs/20260829T094010-4029747.log`
- one-path numbered patch reverse/forward identity:
  `ledger/buildlogs/20260829T094027-4029853.log`
- exact canonical freezer and clean-pin replay:
  `ledger/buildlogs/20260829T093302-4023405.log` and
  `ledger/buildlogs/20260829T093353-4023869.log`
- native and Wasm editor object compiles:
  `ledger/buildlogs/20260829T093436-4024202.log` and
  `ledger/buildlogs/20260829T093422-4024109.log`
- CAPTURE relink, locked no-work, and product preflight:
  `ledger/buildlogs/20260829T093458-4024982.log`,
  `ledger/buildlogs/20260829T093823-4027442.log`, and
  `ledger/buildlogs/20260829T093823-4027443.log`
- exact slow/sparse software control: first orbit 318 ms, Cube selection 11,933 ms, recovery orbit
  1,933 ms, zero selection-fallback/page/lifecycle errors:
  `ledger/buildlogs/20260829T093658-4026694.log`. The preceding WSLg target-page closure had zero
  page errors and is retained separately at `ledger/buildlogs/20260829T093616-4025587.log`.
- adjacent draw-validation/retry/admission, capture/gauntlet producer self-checks, Node syntax, and
  REUSE 6.2.0 are green:
  `ledger/buildlogs/20260829T093823-4027450.log`,
  `ledger/buildlogs/20260829T093823-4027458.log`,
  `ledger/buildlogs/20260829T093941-4029558.log`,
  `ledger/buildlogs/20260829T094010-4029741.log`,
  `ledger/buildlogs/20260829T094010-4029742.log`,
  `ledger/buildlogs/20260829T093941-4029554.log`, and
  `ledger/buildlogs/20260829T094353-4032167.log`.
- direct M4 remains honestly RED at the Apple pixel binding; the pinned-container regression
  restores M0 6/6 and retains the named later strict/APPLY/product boundaries:
  `ledger/buildlogs/20260829T093857-4027729.log` and
  `ledger/buildlogs/20260829T093930-4028171.log`.

## Candidate identity and closure bar

- `blender_browser.js`: `3a9cddbe853a` (712,328 bytes)
- `blender_browser.wasm`: `0832d06d1d9d` (120,350,773 bytes)
- `blender_browser.wasm.orig`: `c22cc2e373d5` (119,001,697 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `d2e73226d0a2` (14,448 bytes)

P0-I/J remain open. The driver must bind this exact inventory to 10/10 clean slow/sparse Apple
runs with real Cube selection, two pixel-changing orbits, no visible artifact, no selection
fallback, and no page error, then compose the same generation with the P0-E interaction gauntlet.
No hardware receipt, profile, APPLY product, public bundle, tag, result promotion, tolerance,
golden, blacklist, deferral, or launch claim changes on software evidence.
