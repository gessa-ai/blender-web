<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J selection readback same-turn map — 2026-08-29

## Outcome

Numbered patch 0312 closes a browser-only ordering seam in the asynchronous viewport-selection
continuation. Patch 0295 made command submission synchronous in the JavaScript calling turn, but
`readback::kick_buffer()` still registered `MapAsync` only from the command helper's terminal
completion callback. That callback runs after asynchronous encoding and submission error scopes
settle. A selection copy could therefore be submitted while its staging buffer had no map request
registered in that turn.

The command helper now reports the exact submission edge separately from its later validation
verdict. Buffer readback registers `MapAsync(AllowSpontaneous)` immediately after a real browser
`Queue::Submit`. A small join retains the staging handle and keeps mapped bytes private until both
the map and command validation have completed successfully. A command rejection unmaps any
successful mapping and publishes `CommandEncodingFailed`; no rejected clear buffer can become a
selection result. Native ordering remains validation-before-submit, and existing callers retain
the original compact helper interface.

This is a testable P0-I/J candidate, not hardware closure. Only the driver-operated Apple adapter
can determine whether this was the remaining frozen selection boundary.

## Fail-first and implementation evidence

- fail-first real integrated-buffer compile, rejected specifically because the submit-edge helper
  did not exist: `ledger/buildlogs/20260829T120328-4139242.log`
- native compile and execution:
  `ledger/buildlogs/20260829T120751-4142802.log` and
  `ledger/buildlogs/20260829T120758-4142910.log`
- wasm32 compile and Node execution:
  `ledger/buildlogs/20260829T120803-4142961.log` and
  `ledger/buildlogs/20260829T120810-4143232.log`
- both executions require browser map registration in the submission turn, native mapping after
  ordered submission, and exactly-once completion only after deferred validation callbacks settle
- focused source/mutation contract and adjacent browser same-turn submission contract:
  `ledger/buildlogs/20260829T122308-4157023.log`,
  `ledger/buildlogs/20260829T121315-4147164.log`, and
  `ledger/buildlogs/20260829T121315-4147165.log`
- full integrated WebGPU smoke suite: `ledger/buildlogs/20260829T121617-4150715.log`
- canonical clean-pin freeze, replay, and receipt self-check:
  `ledger/buildlogs/20260829T121348-4148855.log`,
  `ledger/buildlogs/20260829T121611-4150628.log`, and
  `ledger/buildlogs/20260829T121541-4149729.log`

The optional `--numbered-history` replay remains intentionally non-reconstructible at historical
entry 0016, exactly as `patches/series` documents; the canonical patch is the build authority.
Patch 0312 itself reverse/forward replays byte-exactly across all five touched source files.

## Linked-product control

Implementation commit `0931d51` relinked the optimized CAPTURE product through the locked Ninja
wrapper (`ledger/buildlogs/20260829T121722-4152695.log`). Committed-state no-work and strict CAPTURE
inventory checks are green (`ledger/buildlogs/20260829T122333-4157211.log` and
`ledger/buildlogs/20260829T121849-4153993.log`). The exact inventory is:

- `blender_browser.js`: `b9b77d997dbb` (715,320 bytes)
- `blender_browser.wasm`: `bf5bbd4e01ff` (120,378,344 bytes)
- `blender_browser.wasm.orig`: `cddbb3585b90` (119,028,538 bytes)
- `blender_browser.data`: `095d0ba748c3` (168,637,598 bytes)
- `blender_browser.split-build.json`: `22aa714b6ee5` (15,232 bytes)
- numbered patch 0312: `2b542256bec8`

After two rejected external WSLg target closures with zero page errors, the exact slow/sparse
software control completed the filed sequence. The first orbit retired in 323 ms, the real
projected-Cube selection completed in 10,048 ms, and the independent recovery orbit retired in
1,850 ms. The continuation finished at sessions/attempts/results/replays/failures `1/5/3/6/0`,
validation pending returned to zero with no failures, Cube was selected, and page-error and
selection-fallback censuses were empty (`ledger/buildlogs/20260829T122033-4155132.log`). This is
fallback-adapter diagnostic evidence only.

REUSE 6.2.0 is green (`ledger/buildlogs/20260829T122223-4156638.log`). Direct M4 remains honestly
red at its Apple pixel binding (`ledger/buildlogs/20260829T122343-4157274.log`). The authoritative
pinned-container regression restores M0 to 6/6 while M1–M8 retain their named strict, hardware,
APPLY, and product boundaries (`ledger/buildlogs/20260829T122420-4158379.log`).

## Closure bar

P0-I/J remain open. The driver must serve the exact inventory above and pass 10/10 clean Apple
slow/sparse attempts with real Cube selection, two pixel-changing orbits, zero visible artifact,
zero page error, and the same-generation composed P0-E gauntlet. No hardware receipt, profile,
APPLY/public bundle, tag, result promotion, promise, tolerance, golden, blacklist, deferral, or
launch claim changes on this software evidence.
