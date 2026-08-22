<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M3.T6 point-restart compaction — 2026-08-21

## Outcome

Patch 0154 closes the WebGPU index backend's silent point-list primitive-restart gap.
`IndexBuf::init()` delegates point restart removal to `strip_restart_indices()` before index
squeezing, but the canonical WebGPU override was empty. WebGPU exposes primitive restart only for
strip topologies, so an untouched marker became an out-of-range point index. The new in-place
compaction removes every marker, preserves surviving order, and then lets the shared initializer
perform its existing u16/u32 selection and base-index squeezing.

## Experiment and evidence

The unchanged exact-source contract first compiled both legs and stopped on
`FAIL mixed restart count` (`ledger/buildlogs/20260822T003449-787866.log`). The final driver
extracts the shipping method byte-for-byte, changes only its class qualifier, and executes it
through Blender's real `IndexBuf::init()` without retaining the live-device vtable. Four point
cases remove 9 markers and preserve 9 indices across mixed, all-restart, wide-u32, and rebased-u16
inputs; a second contract binds subrange inheritance and 17 build-on-device u32 indices. Native and
Node 22.16.0 emit the same 692 bytes at SHA-256
`4036a5d36ebf135f60aa1bb3234fd93bb532fd40f74bc198baef486fa8a32a89`, with 20 shipping inputs at
SHA-256 `2620212ed9b618489c46b655c5dc72ac24b785c51e9faf865cc74135b5b37081` and extracted method at
SHA-256 `b81eab30c39d69d6bec7115782551307ef5aeda33c3231bd3fa1bfd3c88f008a`
(`ledger/buildlogs/20260822T004359-797583.log`). A malformed source is rejected before generated
output allocation, and both locked targets end at exact no-work.

The canonical freezer retains 257 paths and 20,258 manifest rows. Its 1,536,412-byte patch is
SHA-256 `28dddfc5aaba843c5ce826d4669645f8a79d4dfe2dd911494c9338e3d2d2d659`, and its live/replay
manifests are byte-identical at SHA-256
`3a2a595ec54ba249861abdccec50ab2b29578fccdd12f9f07aa16fa60bd52489`
(`ledger/buildlogs/20260822T003653-790132.log`). Canonical replay is green
(`ledger/buildlogs/20260822T003736-791532.log`). The real windowed product rebuilt through locked
Ninja and then ended at exact no-work (`ledger/buildlogs/20260822T003805-792275.log`,
`ledger/buildlogs/20260822T003847-792646.log`). Final REUSE 6.2.0 is 2,014/2,014 green
(`ledger/buildlogs/20260822T004254-797084.log`).

## Boundary

This contract creates no WebGPU instance, adapter, device, GPU buffer, upload, draw, pixel
artifact, or receipt. Required M3 remains red for the absent fresh strict candidate; final
container-backed regression at `2026-08-22T00:39:27Z` restores M0 to 6/6 green while M1–M8 retain
their existing strict-receipt, APPLY/artifact, browser/run-label, and s7 hardware boundaries. No
result was promoted and no deferral, tolerance, golden, blacklist, dependency decision, or promise
changed.
