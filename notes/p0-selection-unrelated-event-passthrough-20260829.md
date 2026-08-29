# P0-I/J pending-selection unrelated-event pass-through — 2026-08-29

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Browser viewport selection used the wrong Blender modal return for events owned by other handlers.
The branch comment said unrelated timer/custom events should keep flowing, but it returned
`OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH`. The pinned event system maps that exact pair to
`WM_HANDLER_BREAK | WM_HANDLER_MODAL`; later handlers therefore never saw those events while the
asynchronous WebGPU pick remained active. Bare `OPERATOR_PASS_THROUGH` maps to
`WM_HANDLER_CONTINUE`, leaves the selection modal installed, and matches the already-corrected
navigation route.

Patch 0317 changes only this Emscripten-only return. The hard selection timeout, retained
state-changing-input FIFO, navigation routing, selection retry/readback policy, and native behavior
are unchanged.

## Verification

- Fail-first source contract: `ledger/buildlogs/20260829T164325-145082.log`.
- Final focused navigation/unrelated-event and stream-continuation mutation contracts:
  `ledger/buildlogs/20260829T164534-146658.log` and
  `ledger/buildlogs/20260829T164534-146659.log`.
- Adjacent sync-stage, input-drain, wall-timeout, same-turn-map, draw retry/admission/validation,
  readback-lifecycle, and continuation-telemetry contracts are green at
  `ledger/buildlogs/20260829T164501-145759.log`,
  `ledger/buildlogs/20260829T164501-145766.log`,
  `ledger/buildlogs/20260829T164501-145775.log`,
  `ledger/buildlogs/20260829T164501-145784.log`, and
  `ledger/buildlogs/20260829T165302-152373.log` through
  `ledger/buildlogs/20260829T165302-152398.log`.
- The affected Wasm object compiled at `ledger/buildlogs/20260829T164443-145642.log`.
- The regenerated 20,258-path canonical freezer/replay and receipt self-check are green at
  `ledger/buildlogs/20260829T164718-147557.log` and
  `ledger/buildlogs/20260829T164810-148692.log`/`148687.log`; canonical patch SHA-256 is
  `6a6ebea1252e41f5817fb87f32c6a51e229cf6e07509c4c22037e02183a317c6`.
- Locked CAPTURE relink, no-work, and preflight are green at
  `ledger/buildlogs/20260829T164841-148919.log` and
  `ledger/buildlogs/20260829T164944-149401.log`/`149403.log`.
- One WSLg page closed externally with an empty page-error census and was rejected
  (`ledger/buildlogs/20260829T165011-149607.log`). The clean isolated-X slow/sparse product run
  exercised a pending selection, passed the isolated navigation orbit directly, completed five
  selection loops, selected exactly Cube, and retired with zero selection/page/lifecycle errors
  (`ledger/buildlogs/20260829T165109-150875.log`).
- REUSE 6.2.0 is green for 2,820/2,820 files at
  `ledger/buildlogs/20260829T165302-152371.log`.

## Exact candidate and boundary

Implementation commit is `a3dd47b`. The relinked CAPTURE inventory is JS
`bba3f480bb3b`, Wasm `bdb08116bbc4`, `.wasm.orig` `04b01d73e0a5` (119,031,221 bytes), data
`095d0ba748c3`, and split manifest `07c42f24e174`.

This is a device-free candidate, not P0-I/J closure. Direct M4 remains red at the unchanged Apple
pixel-binding boundary, and later tiers retain their named strict/APPLY/product blockers. The
driver must still pass the exact slow/sparse Apple series 10/10 and the same-generation P0-E and
zero-artifact interaction gauntlet before P0-I/J can close.
