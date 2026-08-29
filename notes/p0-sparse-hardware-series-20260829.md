<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J exact slow/sparse hardware series — 2026-08-29

## Outcome

Commit `57f9fb0` makes the focused slow/sparse freeze producer usable as the owner's exact Apple
10/10 acceptance instrument. Before this change, an individual hardware run could enforce the
native and pixel verdict but did not immutably bind its run label, browser stack, accepted adapter,
or complete product inventory. Ten JSON files therefore could not prove that ten fresh runs tested
one unchanged candidate.

Hardware mode now requires an immutable run label, an explicit expected `.wasm.orig` SHA-256, an
exclusive output path, and `BLENDER_WEB_BIN`. It pins the sanctioned Node, Playwright, pngjs, and
Chromium versions; accepts only a non-fallback hardware adapter; hashes the JavaScript,
instrumented Wasm, original Wasm, data archive, and split manifest; and requires the local and
served manifests to describe that same generation. The inventory is re-hashed after the browser
run before a pass-only JSON is created with exclusive-create semantics.

`analyze_sparse_hardware_series.py` then requires exactly ten files and independently rechecks the
producer identity, pinned stack, adapter contract, complete product identity, native view and
selection state, retained-FIFO replay, content/pixel verdict, bounded drains, lifecycle/error
censuses, distinct labels/timestamps, and cross-run identity. It cannot turn fallback/software
evidence into a hardware verdict.

This is diagnostic and receipt infrastructure, not a runtime fix. No runtime byte changed and no
relink occurred. P0-I/J remain open until this exact series passes 10/10 on the driver-operated
Apple hardware and the same-generation P0-E/broader acceptance gauntlet is green.

## Fail-first and focused evidence

- missing immutable identity/static contract:
  `ledger/buildlogs/20260829T140518-36489.log`
- missing mandatory output-path contract:
  `ledger/buildlogs/20260829T141053-40648.log`
- missing exact-product self-check path:
  `ledger/buildlogs/20260829T141219-41102.log`
- missing post-run product recheck:
  `ledger/buildlogs/20260829T141538-44990.log`
- final producer source/mutation self-check and JavaScript/Python syntax:
  `ledger/buildlogs/20260829T141550-45701.log` and
  `ledger/buildlogs/20260829T141550-45702.log`
- 19-case series mutation self-check and integrated WebGPU/GHOST matrix:
  `ledger/buildlogs/20260829T141600-45763.log` and
  `ledger/buildlogs/20260829T141600-45762.log`
- REUSE 6.2.0:
  `ledger/buildlogs/20260829T141600-45764.log`
- committed-state REUSE, direct M4, and authoritative container regression:
  `ledger/buildlogs/20260829T141942-49024.log`,
  `ledger/buildlogs/20260829T142006-49179.log`, and
  `ledger/buildlogs/20260829T142015-49259.log`

The direct M4 gate remains red at the named Apple browser-pixel boundary. The container regression
restores M0 6/6 and keeps M1-M8 red at their named strict-receipt, hardware-pixel, deferred-Wasm,
render-suite, APPLY/bundle, and product-receipt boundaries; it does not create a completion claim.

## Exact-product controls

The real CAPTURE inventory self-check passed against `.wasm.orig`
`40a21549d0f1e34066953c1b7a52331d5da4346b6b0f738b9b6fc2314e68f3fb`
(`ledger/buildlogs/20260829T141258-41993.log`). A deliberately wrong expected hash was rejected
before browser interaction (`ledger/buildlogs/20260829T141308-42076.log`).

An unchanged-product slow/sparse software control remained green
(`ledger/buildlogs/20260829T140906-39191.log`). It required retained FIFO replay, retired selection
and the following isolated orbit in 11,383 ms, selected exactly Cube without moving it, and ended
with empty page, lifecycle, readback, and validation failure censuses. Because its adapter is
software/fallback, it is diagnostic evidence only and binds no receipt.

## Pixel-identity consumer hardening

Commit `32678a0` closes a fail-closed gap in the series consumer without changing the producer or
the linked product. The producer already required changed screenshot bytes while draining the
first orbit, navigation through a pending selection, and the replayed transform tail. The
independent series consumer checked only that those SHA-256 fields were well formed, so a mutated
receipt could replace a changing frame hash with its baseline and still pass while native counters
advanced.

The new consumer assertions require three distinct pixel transitions: Deselect All to the first
isolated orbit, the first orbit to navigation through the pending selection, and the first orbit to
the replayed transform result. Synthetic fixtures now give every step an independent image hash,
and three mutations replace each required changed hash with its baseline. The new navigation
mutation failed first at `ledger/buildlogs/20260829T193635-276629.log`; the final 26-negative
self-check and integrated WebGPU/GHOST matrix are green at
`ledger/buildlogs/20260829T193707-277446.log` and
`ledger/buildlogs/20260829T193718-277502.log`. REUSE 6.2.0 is green at
`ledger/buildlogs/20260829T194042-281481.log`.

Direct M4 remains red at the unchanged Apple browser-pixel boundary
(`ledger/buildlogs/20260829T193756-278962.log`). Pinned-oracle regression restores M0 6/6 while
M1-M8 retain their named strict, hardware, APPLY, and product boundaries
(`ledger/buildlogs/20260829T193838-279454.log`). CAPTURE `.wasm.orig` remains `6b0ac5366aef`; no
relink, hardware receipt, result promotion, or P0-I/J closure occurred.

## Failed-attempt evidence retention

The pass-only producer previously printed a failed Apple run's complete boundary timeline only to
stderr. That made the unattended failure easy to summarize but left its designated evidence
directory empty, preventing exact post-run comparison of the selection, GHOST, WM, presentation,
and native-state boundary snapshots. `BW_P0_OUTPUT` remains a PASS-only receipt. A failed browser
attempt now exclusively creates `<BW_P0_OUTPUT>.failure.json`, marked `status=FAIL` and
`evidenceClass=diagnostic-apple-failure`; the ten-file series consumer never accepts that sidecar.

The source contract failed first without this seam at
`ledger/buildlogs/20260829T194849-286197.log`. Final producer mutation and Node syntax checks are
green at `ledger/buildlogs/20260829T194910-287012.log` and
`ledger/buildlogs/20260829T194910-287013.log`. The live failure-path check forced two connection
failures: the first left the PASS path absent and created a parseable failed sidecar, while the
second preserved its exact SHA-256 through exclusive-create rejection
(`ledger/buildlogs/20260829T195201-290044.log`). The adjacent sparse-series, composed-gauntlet,
selection-navigation, and selection-stream mutation checks remain green
(`ledger/buildlogs/20260829T195011-287536.log`, `20260829T195011-287541.log`,
`20260829T195011-287549.log`, and `20260829T195011-287559.log`).

This changes no runtime or product byte. Direct M4 remains honestly red at the Apple pixel binding
(`ledger/buildlogs/20260829T195213-290471.log`), and the pinned-container regression restores M0
6/6 while retaining every named later boundary
(`ledger/buildlogs/20260829T195105-288259.log`). P0-I/J still require the exact current generation
to pass Apple 10/10 plus the same-generation P0-E and zero-artifact gauntlet.
