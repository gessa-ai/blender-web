# M3.T10 render-pipeline shader lifetime identity — 2026-08-21

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0160 closes a deterministic stale-cache path in both WebGPU render frontends. The batch
and immediate render-pipeline pools are process-static, but their key previously identified a
shader only by its raw `WGPUShader *`. Guardedalloc can reuse that address after the old shader
dies while its pipeline remains retained, causing the replacement shader to receive the old
modules and layout. The compute-pipeline path already avoided the same lifetime mistake by
keeping its cache on the shader object.

Each `WGPUShader` now receives a monotonic 64-bit identity from a relaxed atomic at construction.
`PipelineInfo` requires both the pointer and that identity, the render-pipeline hash mixes both,
and debug builds require the supplied identity to match the live shader at pool lookup. All
three shipping constructors (direct batch, indirect batch, and immediate) use the guarded form.

The pre-fix contract stopped while constructing a lifetime-aware `PipelineInfo` because the
shipping type had no identity (`ledger/buildlogs/20260822T024742-909766.log`). The first complete
contract exposed only a wasm micro-link isolation issue: retaining the entire pipeline hash also
retained unrelated vertex-format methods (`20260822T025223-913800`). The final contract calls the
exact shipping identity-hash helper and leaves the rest of the device-free pipeline translation
unit section-collected.

## Evidence

- Final native/wasm32 contract: `ledger/buildlogs/20260822T025454-916422.log`. It simulates 4,096
  successive shader lifetimes at one allocator address, obtains 4,096 distinct keys, preserves a
  stable key within one lifetime, and emits byte-identical 447-byte evidence at
  `sha256:7e6f8a247db57ed31fc881b23d7378ccf8907c496177c83576b627ec7e6b7184`. The 16 shipping
  inputs are bound at `sha256:56ab51b4b350e349169beb5c1c90959b16e3d66e597342f71e7a4c308c82f92d`
  against Dawn `36cf1fae`, emcc 6.0.5, and Node 22.16.0.
- Canonical freeze/replay: `ledger/buildlogs/20260822T025404-914998.log`; independent final replay:
  `20260822T025447-916321`. The authority remains 257 paths and 20,258 manifest entries; its
  1,544,126-byte patch is
  `sha256:ce2a91ec82cf62f5115f2bf20267b4d655abf16a0726335114630195bd838048`, with byte-identical
  live/replay manifests at
  `sha256:135586370ee0cff7523b9a6881ce15b4aabea5e4ecaaefddfa767827752713c4`.
- The real windowed wasm product rebuilt `wgpu_shader.cc`, `wgpu_pipeline.cc`, `wgpu_batch.cc`,
  and `wgpu_immediate.cc`, linked, and then reached exact locked-Ninja no-work:
  `ledger/buildlogs/20260822T025530-916993.log` and `20260822T025616-917880.log`.
- REUSE 6.2.0 is green for 2,026/2,026 files:
  `ledger/buildlogs/20260822T025939-921320.log`.

## Gate boundary

The required M3 scope remains red only because no fresh strict candidate can be named without the
s7 hardware adapter (`ledger/buildlogs/20260822T025734-918785.log`). The container-backed
regression restores M0 to 6/6 green and leaves M1-M8 red on their existing strict-receipt,
APPLY/artifact, browser, run-label, and hardware boundaries
(`ledger/buildlogs/20260822T025815-919283.log`). No instance, adapter, device, pipeline, draw,
browser receipt, result promotion, dependency decision, deferral, tolerance, golden, blacklist,
or promise changed; s7 remains live.
