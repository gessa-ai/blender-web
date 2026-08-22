# M3.T10 render-pipeline vertex-alias cache key — 2026-08-21

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0161 closes a deterministic collision in the process-wide WebGPU render-pipeline caches.
The key hashed every alias of a `GPUVertAttr` as one undelimited byte stream, so distinct valid
alias sequences such as `a` + `bc` and `ab` + `c` produced the same key. Alias order and boundaries
affect `build_vertex_plan()` because the first name present in the shader interface selects the
attribute location; returning the cached pipeline for the other sequence can therefore bind a
different vertex layout.

The key now hashes the alias count and a fixed-width length before every name. The framing is
native/wasm32-stable and also represents an unexpected null name explicitly. No cache lifetime,
shader interface, vertex layout, or draw behavior changes when the alias sequence is identical.

The pre-fix contract built two real `GPUVertFormat` objects and stopped only on cache separation
(`ledger/buildlogs/20260822T030844-928386.log`). The first post-fix invocation then failed closed
because the canonical source snapshot still named the pre-fix file
(`ledger/buildlogs/20260822T031034-930411.log`), before any new evidence could be accepted.

## Evidence

- Canonical freeze: `ledger/buildlogs/20260822T031129-930945.log`. The authority remains 257 paths
  and 20,258 manifest entries; its 1,544,330-byte patch is
  `sha256:2b32dfed7921b565c3f17c2e5a32429d724790e4f743681d742134b5d2c9418f`, and the byte-identical
  live/replay manifests are
  `sha256:79e9e8df23b24e625ae2652ae7449c487726378c4683b347d6a939702fdfeb51`.
- Final native/wasm32 pipeline contract: `ledger/buildlogs/20260822T031739-937359.log`. Eight
  contracts include the two collision inputs and emit byte-identical 524-byte output at
  `sha256:41a77824ce3586785fab322202632ea0be17152851ac39669a13e4c1d574400e`; 18 shipping inputs bind at
  `sha256:df05f1a820798fb9d58fcc873dfd45e080d823efe02acf509192553cb61e11e0` against Dawn
  `36cf1fae`, emcc 6.0.5, and Node 22.16.0.
- Independent canonical replay: `ledger/buildlogs/20260822T031343-933529.log`. The real windowed
  product rebuilt and then ended exact locked-Ninja no-work at
  `ledger/buildlogs/20260822T031247-933057.log` and `20260822T031343-933527.log`.
- Exact REUSE 6.2.0 is green for 2,028/2,028 files at
  `ledger/buildlogs/20260822T031806-938130.log`.

## Gate boundary

This contract creates no WebGPU instance, adapter, device, render pipeline, draw, browser receipt,
or result promotion. Live pipeline/pixel proof and the fresh strict M3 receipt remain owned by
`M3-LINUX-REPLAY`, which is blocked by s7's software-only Vulkan adapter. The required M3 scope is
therefore honestly red for the absent fresh strict candidate
(`ledger/buildlogs/20260822T031535-935106.log`). Container-backed regression keeps M0 6/6 green
and M1-M8 red on their existing strict-receipt, APPLY/artifact, browser, run-label, and hardware
boundaries (`ledger/buildlogs/20260822T031543-935190.log`).
