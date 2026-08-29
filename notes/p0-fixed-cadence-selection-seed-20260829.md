<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J fixed cadence and first-selection shader seed — 2026-08-29

## Outcome

The exact slow/sparse producer now sends the driver's filed tail without waiting for an
intermediate drain: first orbit, projected-Cube click, navigation orbit, transform motion, and
transform confirmation are each sampled after a fixed 650 ms interval. Its evidence records the
five action/sample timestamps. Apple mode fails immediately if the first orbit after `Alt+A` has
not changed pixels and completed through GHOST, WM, and `VIEW3D_OT_rotate` at that boundary. The
independent ten-run consumer rechecks the exact sequence, 650–1,500 ms bounds, monotonic ordering,
pixel transitions, and native input/state contracts. Its synthetic mutation census still requires
early navigation pass-through on Apple hardware; the software control may continue to its terminal
drain so it can distinguish slow completion from a permanent freeze.

Tracing that exact product sequence found the first projected-Cube click blocked in selection sync
stage 80 while selection-enabled overlay shaders synchronously translated on the WebGPU main
context. The cold run emitted 135 translation misses. Injecting those entries made the same path
emit 160 hits, zero misses, and complete selection in 2,360 ms. A bundled-corpus audit found one
additional selectable variant, `overlay_extra_loose_point_selectable`. The committed immutable
pack therefore grows from 100 startup entries to 136 startup-plus-first-selection entries. It is
still content-keyed, checksummed, salt-bound, lower priority than OPFS, and fail-open to ordinary
translation on any mismatch.

The final CAPTURE runtime C++ identity is unchanged: `.wasm.orig` is
`6b0ac5366aefedd32faee379932aedb28e196c52c1b6438fbd587bba8ba29df1` (119,031,283 bytes).
The relink embeds the expanded data pack; `blender_browser.data` is
`db2cc4f50a0a5817fe9aea8d17e3232942f8c99d39eae4429fa6565a72fdb5ea`. The pack itself is
2,179,240 bytes with SHA-256
`b022415106fa12237708d3f1bf7d840b804729fa36bc6883240da7b24c5065ba`.
At Brotli quality 11/window 24, the pack grows from 87,696 to 101,694 bytes: a 13,998-byte
critical-wire cost for the 36 first-selection entries.

This does not close P0-I/J. The isolated software-adapter product control proves the exact first
orbit changes pixels and native rotation at 650 ms, all 36 selectable translations hit the seed,
the retained selection/transform tail eventually retires, and a third post-drain orbit remains
live. It also shows that SwiftShader does not complete the stricter navigation-through-pending-
selection condition at 650 ms and still reports 34 asynchronous module/pipeline draw drops while
those objects settle. The seed removes the synchronous translation misses; it does not manufacture
an async-layout or pixel verdict. Only the driver's Apple 10/10 series plus the same-generation
P0-E and zero-artifact gauntlet can bind closure.

## Evidence

- fail-first missing fixed-cadence contract:
  `ledger/buildlogs/20260829T202053-310934.log`
- cold startup-plus-selection extraction: 135 entries, 135 misses, no page errors:
  `ledger/buildlogs/20260829T204108-324134.log`
- injected-seed A/B: 135 entries, 160 hits, zero misses, selection ready in 2,360 ms:
  `ledger/buildlogs/20260829T204236-324786.log`
- bundled-corpus audit identifying the one remaining selectable entry:
  `ledger/buildlogs/20260829T205153-330587.log`
- final canonical-source replay and fixed-cadence mutation contract:
  `ledger/buildlogs/20260829T205921-336088.log` and
  `ledger/buildlogs/20260829T205921-336089.log`
- deterministic 136-entry pack verification, final locked relink, exact no-work, and CAPTURE
  preflight:
  `ledger/buildlogs/20260829T210856-342144.log`,
  `ledger/buildlogs/20260829T210931-342553.log`,
  `ledger/buildlogs/20260829T211048-343810.log`, and
  `ledger/buildlogs/20260829T211057-343925.log`
- rejected shared-display target closure (empty page-error census; not counted):
  `ledger/buildlogs/20260829T210103-336865.log`
- accepted isolated-X real-product diagnostic: exact 650–652 ms cadence, first-orbit pixel/native
  change, 36 selectable cache hits and zero translation misses, completed selection replay, changed
  Cube location, third retired orbit, and no page errors:
  `ledger/buildlogs/20260829T210325-338444.log`
- final producer 89-mutation, Apple-series 42-negative, syntax, canonical replay, scoped diff, and
  REUSE 2,829/2,829 checks:
  `ledger/buildlogs/20260829T210856-342142.log` through
  `ledger/buildlogs/20260829T210856-342166.log`, and
  `ledger/buildlogs/20260829T211057-343926.log` through
  `ledger/buildlogs/20260829T211057-343931.log`
- direct M4 remains red at its unsupported old binding; authoritative pinned-oracle regression
  restores M0 6/6 and preserves every named M1-M8 strict/APPLY/product boundary:
  `ledger/buildlogs/20260829T211110-344144.log` and
  `ledger/buildlogs/20260829T211151-344684.log`

An eager overlay-module warmup experiment was rejected and fully reverted: although it shortened
one first selection, two of three shared-display runs closed the browser target at first orbit.
Canonical source replay is byte-identical after the revert; no experimental upstream edit remains.
