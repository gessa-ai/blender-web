<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J selection retry software stability — 2026-08-29

## Outcome

The exact patch-0306 CAPTURE candidate completed ten fresh slow/sparse diagnostic runs on the
WSL2 SwiftShader lane. All ten retired the isolated pre-click orbit, selected exactly Cube through
the trusted projected viewport click, and retired the independent recovery orbit. This exercises
the first-use selection-shader path repeatedly, but it is software-adapter evidence only and does
not close P0-I/J's Apple 10/10 pixel or same-generation gauntlet gates.

The tested product inventory remained exact:

- `blender_browser.js`: `90f60eb449c1`
- `blender_browser.wasm`: `20ad4e454355`
- `blender_browser.wasm.orig`: `5b95408deafe` (full SHA-256
  `5b95408deafe069f67949c9d00954660a1f2041cb057f880e95859e9a81e4b87`)
- `blender_browser.data`: `095d0ba748c3`
- `blender_browser.split-build.json`: `f2c58964c8af`

## Ten completed runs

Across the ten completed product runs:

- isolated first-orbit drain: 317-356 ms (mean 327.3 ms)
- trusted projected-Cube selection drain: 9,944-15,164 ms on cold SwiftShader
  (mean 11,651.2 ms)
- independent recovery-orbit drain: 1,190-2,568 ms (mean 1,858.4 ms)
- every selection window advanced the redraw-readiness generation by exactly 218, semantic
  content presentation by exactly four generations, and 14-21 validated presentations
- every run exercised the same 36 selectable shader-cache misses, then finished with Cube as the
  sole active selection, two invoked/confirmed/terminal rotates, no active rotate, balanced
  callback/WM button counters, cleared held masks, and terminal/admitted/dispatched/presented/
  content-presented generations converged
- aggregate errors: page 0, lifecycle 0, selection-readback 0

Wrapped evidence:

- `ledger/buildlogs/20260829T075637-3942454.log`
- `ledger/buildlogs/20260829T075718-3942996.log`
- `ledger/buildlogs/20260829T075820-3943838.log`
- `ledger/buildlogs/20260829T075901-3944969.log`
- `ledger/buildlogs/20260829T075942-3945437.log`
- `ledger/buildlogs/20260829T080047-3946334.log`
- `ledger/buildlogs/20260829T080128-3947443.log`
- `ledger/buildlogs/20260829T080218-3948265.log`
- `ledger/buildlogs/20260829T080334-3949409.log`
- `ledger/buildlogs/20260829T080451-3950944.log`

Four additional attempts were rejected because WSLg closed the target page during the first-orbit
settle at `rapid_freeze_repro.mjs:445`, before the isolated selection click. Each retained an empty
page-error and selection-error census. They bind no product result and were replaced rather than
counted: `20260829T075759-3943472`, `20260829T080023-3945934`,
`20260829T080310-3948959`, and `20260829T080426-3950496`.

## Remaining gate

The driver must still run this exact inventory through the accepted Apple adapter for 10/10
slow/sparse visual passes, zero artifacts/errors, and the same-generation composed P0-E interaction
gauntlet. No receipt, profile, APPLY product, public bundle, release tag, or launch claim changes.
