<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J selection readback lifecycle telemetry — 2026-08-29

## Outcome

Numbered patch 0313 adds a read-only discriminator for the browser exact-buffer readback path used
by viewport selection. The previous evidence exposed one aggregate pending count and the selection
continuation phase, but could not distinguish a request that never submitted from one whose
`MapAsync` callback, command validation, join, or successful payload publication had stopped.

Six monotonic browser-only generations now identify exact buffer request submission, map start,
map completion, validation completion, join completion, and `TicketStatus::Ready` publication. The
counters do not own a ticket and do not advance selection, retry, redraw, timeout, input, or
presentation state. The slow/sparse producer fails closed if any export is absent and samples all
six values at every existing bounded poll.

This is diagnostic infrastructure, not a P0-I/J fix. The driver-operated Apple adapter remains the
authority for the deterministic freeze and zero-artifact pixel bar.

## Fail-first and focused evidence

- fail-first source contract, rejected because the lifecycle exports and producer sampling were
  absent: `ledger/buildlogs/20260829T123625-4165979.log`
- final lifecycle source/mutation contract:
  `ledger/buildlogs/20260829T124018-4168409.log` and
  `ledger/buildlogs/20260829T124345-4171159.log`
- real Emscripten `wgpu_readback.cc` object build:
  `ledger/buildlogs/20260829T124059-4169256.log`
- adjacent same-turn, continuation, rapid-input, and stream-continuation contracts:
  `ledger/buildlogs/20260829T124059-4169260.log`,
  `ledger/buildlogs/20260829T124059-4169264.log`,
  `ledger/buildlogs/20260829T124059-4169257.log`, and
  `ledger/buildlogs/20260829T124059-4169269.log`
- canonical clean-pin freeze/replay and receipt checks:
  `ledger/buildlogs/20260829T124136-4169517.log`,
  `ledger/buildlogs/20260829T124252-4170180.log`, and
  `ledger/buildlogs/20260829T124252-4170187.log`
- integrated native/wasm32 builds and executions:
  `ledger/buildlogs/20260829T124252-4170174.log`,
  `ledger/buildlogs/20260829T124252-4170175.log`,
  `ledger/buildlogs/20260829T124307-4170566.log`, and
  `ledger/buildlogs/20260829T124307-4170567.log`
- REUSE 6.2.0: `ledger/buildlogs/20260829T124534-4171868.log`

Patch 0313 reverse-replays cleanly against the mechanically applied integration source. Its SHA-256
is `03ef9e721e28cb2bd1f320875f371d229b15894323e1c879908adf064942f3c4`.

## Linked-product control

Implementation commit `9a75f6c` relinked the optimized CAPTURE product through locked Ninja
(`ledger/buildlogs/20260829T124629-4172954.log`). The committed-state relink is exact no-work and
the strict CAPTURE inventory passes preflight
(`ledger/buildlogs/20260829T124733-4173458.log` and
`ledger/buildlogs/20260829T124740-4173511.log`). The exact inventory is:

- `blender_browser.js`: `ca977deda74a` (716,512 bytes)
- `blender_browser.wasm`: `beed79935127` (120,379,067 bytes)
- `blender_browser.wasm.orig`: `40a21549d0f1` (119,029,200 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `32bda7e1125f` (15,542 bytes)

The first WSLg control was rejected after an external target-page closure with no page error
(`ledger/buildlogs/20260829T124759-4173647.log`). A fresh isolated-X control completed the exact
slow/sparse sequence (`ledger/buildlogs/20260829T124858-4174835.log`). Before the projected Cube
click, all lifecycle counters remained zero. During the selection drain they progressed through:

- 7,785 ms: submit/map-start/map-complete/validation/join/ready `1/1/0/0/0/0`
- 8,745 ms: `2/2/1/1/1/0`
- 9,077 ms: `2/2/2/2/2/0`
- 9,584 ms: `3/3/2/2/2/0`
- 9,910 ms: `5/5/5/5/5/3`

The three ready publications match the continuation's three GPU results; validation pending
returned to zero, selection completed, Cube became selected, and the following isolated orbit
changed state and pixels. Page-error, lifecycle-error, validation-failure, and selection-readback
failure censuses were empty. This is fallback-adapter diagnostic evidence only.

Direct M4 remains red at the Apple pixel binding
(`ledger/buildlogs/20260829T125003-4175478.log`). The authoritative pinned-oracle regression keeps
M0 green at 6/6 while M1–M8 retain their named strict, hardware, APPLY, and product boundaries
(`ledger/buildlogs/20260829T125121-4176851.log`).

## Closure bar

P0-I/J remain open. The driver must serve this exact inventory and capture the six-counter timeline
through the deterministic slow/sparse Apple repro. Closure still requires 10/10 pixel-changing
runs with real Cube selection, zero visible artifact, zero page error, and the same-generation
composed P0-E gauntlet. No hardware receipt, profile, APPLY/public bundle, tag, result promotion,
promise, tolerance, golden, blacklist, deferral, or launch claim changes on this software evidence.
