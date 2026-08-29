<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J viewport-selection wall timeout — 2026-08-29

## Outcome

Commit `af966ec` and numbered patch 0314 replace the browser viewport-selection modal's
scheduler-dependent timer-event timeout with a monotonic elapsed-time fail-close. The old guard
assumed that 240 delivered events from a nominal 10 ms timer represented roughly 2.4 seconds.
Browser and worker scheduling can coalesce those events heavily, while a fast host can deliver the
full count before a valid first-use WebGPU pick settles. Event count was therefore neither a
portable duration nor a safe acceptance boundary.

`View3DSelectAsyncData` now records `BLI_time_now_seconds()` when the asynchronous operation starts.
The modal cancels only after more than 30 elapsed seconds. Its tick counter and exported tick
generation remain unchanged as diagnostics. The focused Apple producer still rejects any drain
longer than 12 seconds, so this runtime correction does not relax the hardware acceptance bar; it
only prevents host timer cadence from canceling otherwise valid work prematurely.

This is a hardware candidate, not a closure claim. P0-I/J remain open until the exact linked
inventory passes the driver's Apple 10/10 slow/sparse series and the same-generation P0-E/broader
zero-artifact gauntlet.

## Fail-first and source evidence

- fail-first source contract, before the elapsed-time state and guard existed:
  `ledger/buildlogs/20260829T143128-57129.log`
- final six-mutation wall-timeout self-check and source contract:
  `ledger/buildlogs/20260829T144226-64067.log` and
  `ledger/buildlogs/20260829T143541-59458.log`
- real wasm32 and native `view3d_select.cc` object compiles:
  `ledger/buildlogs/20260829T143310-57637.log` and
  `ledger/buildlogs/20260829T143321-57711.log`
- patch 0314 reverse replay and canonical clean-pin freeze/replay:
  `ledger/buildlogs/20260829T143734-60759.log`,
  `ledger/buildlogs/20260829T143348-58280.log`, and
  `ledger/buildlogs/20260829T143457-59223.log`
- adjacent draw retry/admission/validation, same-turn readback, lifecycle, and retained-stream
  contracts:
  `ledger/buildlogs/20260829T144226-64017.log`,
  `ledger/buildlogs/20260829T144226-64018.log`,
  `ledger/buildlogs/20260829T144226-64023.log`,
  `ledger/buildlogs/20260829T144226-64030.log`,
  `ledger/buildlogs/20260829T144226-64041.log`, and
  `ledger/buildlogs/20260829T144226-64053.log`
- implementation and post-record REUSE 6.2.0 checks:
  `ledger/buildlogs/20260829T143541-59457.log` and
  `ledger/buildlogs/20260829T144455-66251.log`

Patch 0314 has SHA-256
`3980b1b5004b7810cbd08f5e254cd574477d0a14cb5aeb65572cce86a7f6daaa`. The regenerated canonical
preview patch has SHA-256
`b34ba6751c1e309e3b3b430d02e7c36beda4636acff17a5221dceefd1cf0fe87`; its clean-pin receipt records
20,258 live/replay files as byte-identical.

## Linked product and software discriminator

The optimized CAPTURE product was relinked through locked Ninja
(`ledger/buildlogs/20260829T143802-61019.log`), followed by committed-state no-work and strict
CAPTURE preflight checks (`ledger/buildlogs/20260829T143912-61471.log` and
`ledger/buildlogs/20260829T143912-61472.log`). The exact inventory is:

- `blender_browser.js`: `ca977deda74a` (716,512 bytes)
- `blender_browser.wasm`: `da6cead0f577` (120,379,140 bytes)
- `blender_browser.wasm.orig`: `fe1301f99fae` (119,029,274 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `32db3bcc6708` (15,542 bytes)

The exact slow/sparse WSLg control completed against that product
(`ledger/buildlogs/20260829T143934-61606.log`). Selection required five GPU attempts and published
three results; the continuation replayed all ten retained events, returned inactive with no queued
events, selected exactly Cube without moving it, and retired both isolated orbits. The combined
selection/replayed-orbit drain completed in 9,253 ms with nine delivered timer ticks, zero GPU
continuation failures, zero validation failures, and empty selection-readback and page-error
censuses. SwiftShader is a rejected fallback adapter, so this run is diagnostic software evidence
only and binds no pixel or hardware receipt.

## Gate boundary

Direct M4 remains red at `browser_pixels` because there is no accepted same-generation hardware
receipt (`ledger/buildlogs/20260829T144235-64110.log`). The pinned-container regression restores M0
to 6/6 while M1-M8 retain their named strict-receipt, hardware, deferred-Wasm, render, APPLY, and
product boundaries (`ledger/buildlogs/20260829T144245-64210.log`). No hardware receipt, profile,
APPLY/public bundle, tag, result promotion, tolerance, golden, blacklist, deferral, or launch claim
changes on this software evidence.
