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
