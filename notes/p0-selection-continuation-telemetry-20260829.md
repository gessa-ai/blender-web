<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J selection-continuation telemetry — 2026-08-29

## Outcome

The exact slow/sparse freeze producer now records which stage owns a browser viewport-selection
continuation. Numbered patch 0311 exposes read-only counters for GPU sessions, attempts, completed
results, cached-result replays, and failures; a numeric GPU phase distinguishes validation wait,
retry wait/readiness, readback wait, result readiness, and terminal failure. The editor side exposes
modal begin/finish, queued/replayed input, timer progress, and the separate GPU/query/combined
readback statuses. The producer fails closed if any export is absent.

No selection, input, redraw, retry, admission, timeout, or presentation policy changes. This is the
smallest useful discriminator after six Apple candidates reproduced the same frozen pixels without
showing whether validation, mapping, modal teardown, or retained-input replay had stalled.

## Exact software observation

The committed CAPTURE generation completed the filed slow/sparse sequence on the software lane.
The selection continuation began and finished once, made five GPU attempts, completed three result
records, replayed six cached result lookups, and recorded zero failures. The modal timer advanced 10
ticks and ended inactive with zero queued input. Its final GPU/query/combined statuses were
ready/invalid/ready; validation pending returned to zero with zero validation failures. Cube
selection completed in 11,354 ms and the independent recovery orbit retired in 1,860 ms. This is a
diagnostic control, not pixel evidence and not hardware closure
(`ledger/buildlogs/20260829T112348-4110280.log`). One preceding WSLg target-page closure carried
zero page errors and was rejected rather than counted
(`ledger/buildlogs/20260829T112312-4109782.log`).

## Verification

- fail-first and final 11-mutation telemetry contracts:
  `ledger/buildlogs/20260829T110049-4093006.log` and
  `ledger/buildlogs/20260829T111118-4099897.log`
- affected Wasm and native object compiles:
  `ledger/buildlogs/20260829T111222-4101198.log` and
  `ledger/buildlogs/20260829T111222-4101205.log`
- native/wasm32 asynchronous-readback integration:
  `ledger/buildlogs/20260829T111236-4101376.log`
- canonical clean-pin freeze/replay and receipt mutation check:
  `ledger/buildlogs/20260829T112013-4107531.log`,
  `ledger/buildlogs/20260829T112110-4108239.log`, and
  `ledger/buildlogs/20260829T112053-4108041.log`
- pinned capture-profile, hardware-gauntlet, split-runtime, and two-phase source self-checks:
  `ledger/buildlogs/20260829T111749-4105021.log`,
  `ledger/buildlogs/20260829T111749-4105022.log`,
  `ledger/buildlogs/20260829T111749-4105036.log`, and
  `ledger/buildlogs/20260829T111749-4105056.log`
- committed-state relink, locked no-work, CAPTURE preflight, and REUSE 6.2.0:
  `ledger/buildlogs/20260829T112149-4109187.log`,
  `ledger/buildlogs/20260829T112255-4109679.log`,
  `ledger/buildlogs/20260829T112305-4109741.log`, and
  `ledger/buildlogs/20260829T112053-4108038.log`
- required M4 remains red at the unsupported fresh Apple binding; container-backed regression
  restores M0 6/6 and retains every later named boundary:
  `ledger/buildlogs/20260829T112510-4111619.log` and
  `ledger/buildlogs/20260829T112513-4111669.log`

## Exact candidate and closure bar

- implementation commit: `4877574`
- numbered patch SHA-256: `b159efcd0df1`
- `blender_browser.js`: `edda9e8b0dc9` (715,320 bytes)
- `blender_browser.wasm`: `99006ff33063` (120,352,680 bytes)
- `blender_browser.wasm.orig`: `199d4fafb399` (119,003,425 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `306b502cb691` (15,232 bytes)

P0-I/J remain open. The driver must run this exact inventory through 10/10 clean slow/sparse Apple
attempts and the same-generation composed P0-E interaction gauntlet. A frozen run should now expose
its last selection phase and counter boundary directly; a passing run still requires real Cube
selection, two pixel-changing orbits, zero visible artifact, zero fallback, and zero page error. No
hardware receipt, profile, APPLY product, public bundle, tag, result promotion, promise, tolerance,
golden, blacklist, deferral, or launch claim changes on this software evidence.
