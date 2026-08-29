<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J selection-validation boundary — 2026-08-29

## Outcome

The slow/sparse Apple discriminator now records the exact asynchronous command-validation boundary
for viewport selection. Every 250 ms sample carries the existing WebGPU draw-drop generation plus
selection-validation pending and failure counters. The producer rejects a served product missing
any export. This changes no selection, redraw, retry, admission, timeout, or presentation policy.

The relinked CAPTURE product exercises the discriminator on the software diagnostic lane: selection
validation peaked at 19 pending tickets, returned to zero with no failures, and the draw-drop
generation advanced from 1,356 to 1,424 before Cube selection completed. Both isolated orbits then
retired with changed native state and pixels. That is useful diagnosis, not hardware closure.

## Evidence

- fail-first source contract: `ledger/buildlogs/20260829T102429-4065895.log`
- final source and 82-mutation self-check:
  `ledger/buildlogs/20260829T103020-4069685.log` and
  `ledger/buildlogs/20260829T103020-4069686.log`
- affected Wasm object compile and exact relink:
  `ledger/buildlogs/20260829T102612-4067160.log` and
  `ledger/buildlogs/20260829T102704-4067515.log`
- exact slow/sparse linked-product control: first orbit 426 ms, Cube selection 15,198 ms, recovery
  orbit 1,378 ms, validation pending peak 19, zero validation failures, zero page/lifecycle errors:
  `ledger/buildlogs/20260829T102856-4068962.log`
- stream/retry/admission/validation and same-generation gauntlet self-checks:
  `ledger/buildlogs/20260829T103020-4069691.log`,
  `ledger/buildlogs/20260829T103020-4069700.log`,
  `ledger/buildlogs/20260829T103020-4069708.log`,
  `ledger/buildlogs/20260829T103020-4069718.log`, and
  `ledger/buildlogs/20260829T103020-4069734.log`
- CAPTURE preflight, locked no-work, and REUSE 6.2.0 (2,800/2,800):
  `ledger/buildlogs/20260829T103049-4070566.log`,
  `ledger/buildlogs/20260829T103049-4070569.log`, and
  `ledger/buildlogs/20260829T103404-4073188.log`
- direct M4 remains RED at the unsupported fresh Apple binding; authoritative container regression
  restores M0 6/6 and retains every later named boundary:
  `ledger/buildlogs/20260829T103124-4070731.log` and
  `ledger/buildlogs/20260829T103217-4071311.log`

## Exact candidate and closure bar

- implementation commit: `e2bac4a`
- `blender_browser.js`: `f7c87b7dcf94` (712,840 bytes)
- `blender_browser.wasm`: `6b856178d0c7` (120,350,983 bytes)
- `blender_browser.wasm.orig`: `0c3eda918085` (119,001,878 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `4768c87eed56` (14,582 bytes)

P0-I/J remain open. The driver must bind this exact inventory to 10/10 clean slow/sparse Apple
runs with real Cube selection, two pixel-changing orbits, no visible artifact, no selection
fallback, and no page error, then pass the same-generation composed P0-E interaction gauntlet. No
hardware receipt, profile, APPLY product, public bundle, tag, result promotion, promise, tolerance,
golden, blacklist, deferral, or launch claim changes on software evidence.
