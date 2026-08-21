<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M3.T9 integrated texture Linux reconciliation — 2026-08-21

## Outcome

The canonical in-tree WebGPU texture-format table and RGB-to-RGBA conversion postimages now have
a checkout-relative, device-free native/Wasm parity contract. The native leg reuses pinned Dawn's
target graph; the Wasm leg uses emdawnwebgpu's matching C/C++ value types. Both compile the
shipping `wgpu_texture_format` and `wgpu_data_conversion` sources directly against Blender's real
`TextureFormat` enum instead of substituting the earlier standalone T9.pre mirror. Before
allocating evidence, the driver requires a clean Dawn `36cf1fae` checkout, canonical clean-pin
replay, host CMake 4.0.3, emcc 6.0.5, and Node 22.16.0.

Five contracts cover the evolved shipping behavior:

- the exact 63-row format table, including 41 direct, 13 promoted, three depth, and six compressed
  records plus the complete feature-gate census and deterministic record digest;
- representative WebGPU capability classifications and the renderable implications for every
  table row;
- all five linear/sRGB compatibility pairs in both directions, exact-format views, and rejection
  of undefined, same-size cross-family, and cross-BC-family aliases;
- all 13 promotion plans over 78 patterned pixels, independently checking RGB preservation,
  type-correct opaque alpha bytes, and the allocating/non-allocating entry-point agreement;
- eight invalid and boundary cases covering direct/zero-width plans, undersized inputs, exact
  zero-area conversion, promoted-size arithmetic, and direct-copy behavior.

Root and descendant runs are green at `20260821T202804-552762` and
`20260821T202846-553490`. Native and Node emit identical 426-byte evidence
(`sha256:1b9ae1f406ba`); the seven canonical table/conversion/enum inputs have combined identity
`sha256:33c6e7c9c341`. Both targets finish at locked-Ninja no-work. Wrong-Dawn and wrong-Node
controls reject before evidence allocation (`20260821T202908-553917/553954`). Canonical replay
remains 257 paths at `sha256:e03f140fe3f3`, the existing windowed product is exact no-work
(`20260821T202955-554459`), and final REUSE 6.2.0 is 1,965/1,965 green
(`20260821T203141-556718`).

## Boundary

The contract creates no WebGPU instance, adapter, device, texture, live upload/readback, or M3
receipt. It does not replace the historical live Dawn/Metal T9 proof, and a fresh Linux live
replay remains owned by `M3-LINUX-REPLAY` after s7 exposes an accepted hardware adapter. Required
M3 remains red for the absent strict candidate. Container-backed regression at
`2026-08-21T20:30:52Z` keeps M0 6/6 green and M1–M8 honestly red on their existing strict-manifest,
APPLY/artifact, browser, run-label, and hardware boundaries. No product, upstream/GPU
implementation, receipt, result flag, dependency record, deferral, tolerance, golden, blacklist,
or promise changed.
