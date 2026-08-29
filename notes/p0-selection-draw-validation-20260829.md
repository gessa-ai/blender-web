<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J selection draw validation — 2026-08-29

## Outcome

A cleared browser selection readback now remains private until every encoded selection batch from
that attempt finishes asynchronous command validation. Patch
`0308-gpu-webgpu-select-draw-validation.patch` closes the fail-open interval left by the synchronous
admission guard: encoding a `Draw*` command is no longer treated as the terminal success verdict.
The relinked CAPTURE product passes the exact slow/sparse software diagnostic with a real Cube
selection and two independently retired orbits. This is a hardware candidate, not P0-I/J closure;
the unchanged Apple 10/10 and same-generation composed gauntlet remain mandatory.

## Gap

Patch 0307 correctly rejected every synchronous pre-encode exit. Browser Dawn reports command
encoding/submission validation later through `PopErrorScope`, however. A selection batch could
therefore encode a real draw, disarm the synchronous guard, and start the ordered output readback
before its command scopes settled. If that later validation rejected, the readback could still map
the output buffer's clear value and publish a false miss.

## Fix

- each browser `G_FLAG_PICKSEL` direct/indirect command publishes one balanced validation ticket;
- the completion records a dedicated failure generation, marks the draw dropped, and publishes one
  retry-readiness edge before releasing that ticket;
- `GPU_select_async_status()` waits for the pending ticket count to reach zero before consuming any
  mapped selection bytes;
- a failure generation newer than the exact attempt cancels its readback and makes the settled
  retry immediately eligible;
- the failure generation is selection-specific, so unrelated UI draw drops cannot discard a valid
  pick; ordinary draws and native builds retain their prior behavior.

## Evidence

- fail-first contract: `ledger/buildlogs/20260829T085823-3995984.log`
- final 8-mutation/3-scenario contract:
  `ledger/buildlogs/20260829T090737-4002328.log`
- touched windowed Wasm objects compile:
  `ledger/buildlogs/20260829T090457-4000349.log`
- native/Wasm async-readback contract is byte-identical:
  `ledger/buildlogs/20260829T091028-4007025.log`
- adjacent stream/retry/admission and integrated WebGPU contracts:
  `ledger/buildlogs/20260829T090545-4000661.log`,
  `ledger/buildlogs/20260829T090612-4001483.log`,
  `ledger/buildlogs/20260829T090624-4001616.log`, and
  `ledger/buildlogs/20260829T090745-4002438.log`
- canonical freeze/replay and self-check:
  `ledger/buildlogs/20260829T091004-4006006.log` and
  `ledger/buildlogs/20260829T091957-4014742.log`
- relink and locked no-work:
  `ledger/buildlogs/20260829T091041-4007261.log` and
  `ledger/buildlogs/20260829T091331-4009350.log`
- exact slow/sparse software diagnostic: first orbit 332 ms, Cube selection 11,875 ms, second
  orbit retired, zero selection-readback/page/lifecycle errors:
  `ledger/buildlogs/20260829T091219-4008020.log`
- CAPTURE product preflight:
  `ledger/buildlogs/20260829T091331-4009349.log`
- final focused contract after patch normalization:
  `ledger/buildlogs/20260829T091957-4014741.log`
- REUSE 6.2.0: `ledger/buildlogs/20260829T092005-4014839.log`
- direct M4 remains honestly RED at its unsupported Apple-receipt binding:
  `ledger/buildlogs/20260829T091653-4011206.log`; the authoritative pinned-container regression
  restores M0 6/6 while retaining the named M1-M8 strict/APPLY/product boundaries:
  `ledger/buildlogs/20260829T091733-4012352.log`

## Candidate identity and closure bar

- source commit: `ad1877b`
- `blender_browser.js`: `3a9cddbe853a` (712,328 bytes)
- `blender_browser.wasm`: `d3742ff34bd2` (120,350,356 bytes)
- `blender_browser.wasm.orig`: `fb5223a06ee9` (119,001,291 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `4ae8d1f5c2b1` (14,448 bytes)

The driver must bind this exact inventory to 10/10 clean slow/sparse Apple runs with real Cube
selection, two pixel-changing orbits, zero visible artifact, and zero selection/page error. The
same generation must then pass the composed P0-E interaction gauntlet. No hardware receipt,
profile, APPLY product, public bundle, tag, result promotion, tolerance, golden, blacklist,
deferral, or launch claim changes on device-free evidence.
