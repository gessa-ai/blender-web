# M3.F7 indirect indexed-subrange binding parity — 2026-08-21

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0158 closes a second indexed-subrange state split in WebGPU's batch path. Blender's
`GPU_batch_draw_parameter_get()` writes an index buffer's absolute `index_start_get()` and
`index_base_get()` into the GPU-generated `DrawCommandIndexed`; Vulkan therefore binds the
complete parent allocation for indirect draws. WebGPU instead bound the shared parent allocation
at `index_start * index_size`, so `DrawIndexedIndirect` applied the subrange start a second time.

`IndexBindingMode` now makes the two valid encodings explicit. Direct draws bind the subrange byte
window and pass a batch-relative first index. Indirect draws bind offset zero while the generated
command supplies the absolute first index and squeezed-u16 base vertex. The common `bind_geometry`
path fixes both ordinary and multi-viewport indirect draws.

The pre-fix contract stopped on the missing direct/indirect distinction at
`ledger/buildlogs/20260822T015430-864831.log`. The final device-free contract executes Blender's
real `IndexBuf::init()`/`init_subrange()` metadata for a rebased-u16 child and a u32 child. It
requires direct bindings `2 + 65536` and `12 + 0`, indirect bindings `0 + 65536` and `0 + 0`, and
exact-source checks bind the shipping encoder to the pinned CPU and shader command producers.

## Evidence

- Final root and descendant-CWD native/wasm32 runs:
  `ledger/buildlogs/20260822T015921-869481.log` and
  `ledger/buildlogs/20260822T020003-870138.log`. Both emit identical 732-byte evidence at
  `sha256:c35a2ff4a8f627e380a50e72fb886e3c3237691a1357e8f2aecd264d61dfc0dc`, binding 26 source
  inputs at `sha256:e6dfd3748a984a0f04804550c405783b53a6356f9db1b880456cc909b855a71d`
  against Dawn `36cf1fae`, emcc 6.0.5, and Node 22.16.0.
- A wrong Dawn identity rejects before evidence allocation:
  `ledger/buildlogs/20260822T020024-870943.log`.
- Canonical freeze and isolated replay:
  `ledger/buildlogs/20260822T015811-867452.log` and
  `ledger/buildlogs/20260822T020257-873071.log`. The 257-path / 20,258-entry patch is 1,542,075
  bytes at `sha256:a5ee03e943121c11bb48f4c3e79f83adfc2d7c50974ea6262b56b5924917f3e1`;
  live and replay manifests are byte-identical at
  `sha256:4e22dfdd79e6ab956e46d8d51ace0c6fdde8ca7356d88c4a702255f83cf0313b`.
- The real windowed product recompiled the changed batch path, linked, and then reached exact
  locked-Ninja no-work: `ledger/buildlogs/20260822T020035-871096.log` and
  `ledger/buildlogs/20260822T020131-872451.log`.
- REUSE 6.2.0 is green for 2,022/2,022 files:
  `ledger/buildlogs/20260822T020353-874187.log`.

## Gate boundary

Required M3 remains red only for the absent fresh strict candidate
(`ledger/buildlogs/20260822T020207-872636.log`). Container-backed regression keeps M0 6/6 green
and M1-M8 red on their existing strict-receipt, APPLY/artifact, browser, run-label, and hardware
boundaries (`ledger/buildlogs/20260822T020312-873192.log`). No instance, adapter, device, draw,
browser receipt, result promotion, dependency decision, deferral, tolerance, golden, blacklist,
or promise changed; s7 remains live.
