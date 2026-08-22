# M3.T10 zero-stride dummy vertex binding — 2026-08-21

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0159 replaces WebGPU's finite instance-stepped dummy vertex attributes with the
zero-stride binding supported by the pinned Dawn implementation. Missing shader inputs now use
one vertex-stepped slot whose `arrayStride` is zero, so every vertex and instance reads the same
zero value from a 16-byte buffer. This matches Vulkan's constant-attribute plan and removes the
old range-dependent ceiling without creating a device in the focused contract.

The previous comment incorrectly said WebGPU forbids zero stride. The workaround instead used a
64 KiB buffer and advanced it by the dummy format size for every instance. A `Float32x4` dummy
therefore became out of bounds at `firstInstance + instanceCount > 4096`; pinned Dawn's command
validator rejects that draw even though the missing attribute is semantically constant. Dawn's
own `VertexStateTest.StrideZero` accepts the pipeline layout, and both its vertex- and
instance-range validators reduce a zero-stride binding to one fixed attribute-span check.

The pre-fix contract stopped on the absent canonical dummy-binding helper at
`ledger/buildlogs/20260822T022539-890753.log`. The final shared native/wasm32 contract includes
the shipping `wgpu_pipeline.cc` translation unit directly and covers all 32 `shader::Type` rows,
their exact WebGPU formats, zero stride, vertex step mode, source identity, buffer offset, and
shader location.

## Evidence

- Final native/wasm32 contract:
  `ledger/buildlogs/20260822T022944-895058.log`. Both legs emit identical 366-byte evidence at
  `sha256:fa47ab4fe95c1b4f209e3ae0f4a074bf16d15477159abc1a319100df14f47996`; the 15 shipping
  inputs are bound at `sha256:693c846117b4496077a6b5d0dccb915d68c09a8984a348f3ba527a8df3047b08`
  against Dawn `36cf1fae`, emcc 6.0.5, and Node 22.16.0.
- Canonical freeze and isolated replay:
  `ledger/buildlogs/20260822T022756-892683.log` and
  `ledger/buildlogs/20260822T022842-893291.log`. The authority retains 257 paths and 20,258
  manifest entries; its 1,542,552-byte patch is
  `sha256:4ea99ca851aa4c0a1fcfefc5fafd4080d30f0998c0d827e555b5a9ac9022acf1`, and live/replay
  manifests are byte-identical at
  `sha256:b73ea64adf1310f25eefce8cfc04474b35ea99abd460b6b8d012d6aae7d8157c`.
- The real windowed product rebuilt the pipeline/context paths and linked, then reached exact
  locked-Ninja no-work:
  `ledger/buildlogs/20260822T022958-895464.log` and
  `ledger/buildlogs/20260822T023041-895913.log`.
- REUSE 6.2.0 is green for 2,024/2,024 files:
  `ledger/buildlogs/20260822T023516-899646.log`.

## Gate boundary

Required M3 remains red only for the absent fresh strict candidate
(`ledger/buildlogs/20260822T023111-896131.log`). Container-backed regression keeps M0 6/6 green
and M1-M8 red on their existing strict-receipt, APPLY/artifact, browser, run-label, and hardware
boundaries (`ledger/buildlogs/20260822T023116-896215.log`). No instance, adapter, device,
pipeline, draw, browser receipt, result promotion, dependency decision, deferral, tolerance,
golden, blacklist, or promise changed; s7 remains live.
