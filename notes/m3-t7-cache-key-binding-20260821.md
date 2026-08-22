# M3.T7 WGSL cache key binding — 2026-08-21

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0163 binds every persistent WGSL cache envelope to the 128-bit key requested by
`cache_lookup()`. The previous v2 format encoded the magic, format, toolchain salt, bounded stage
lengths, payload checksum, and exact EOF, but the requested key existed only in the filename. A
complete checksummed entry copied from key A to key B's path was therefore accepted as B and could
publish unrelated WGSL.

The v3 writer stores both key words immediately after the salt. The reader verifies them before
reading lengths or allocating stage strings, and any mismatch remains a cache miss with the
caller's outputs untouched. The format and salt bump make every v2 file miss intentionally; the
normal shader translation path regenerates it under v3.

The pre-fix adversarial contract wrote valid A and B entries, copied A byte-for-byte over B, and
then failed only `cache_key_binding` at 6/7 while all six prior contracts passed
(`ledger/buildlogs/20260822T034833-964953.log`).

## Evidence

- Canonical freeze: `ledger/buildlogs/20260822T035148-967596.log`. The authority remains 257 paths
  and 20,258 manifest entries; its 1,545,015-byte patch is
  `sha256:e30a29148fcef0487583c97a49322e44fe1e4888845456cd887f97939be9e428`, and the byte-identical
  live/replay manifests are
  `sha256:17c999a3e9f8e1e5e51446c5dc222781bebf79f98f90da21018086867b2caceb`.
- Independent canonical replay: `ledger/buildlogs/20260822T035240-968236.log`.
- Final root and checkout-descendant native/wasm32 runs:
  `ledger/buildlogs/20260822T035249-968353.log` and
  `ledger/buildlogs/20260822T035320-969889.log`. Seven contracts emit byte-identical 530-byte
  evidence at `sha256:95e2bc8e083e3be836692ede5309386ff681844097d9b0300708ee25a1d4627c`;
  the four v3 cache entries are byte-identical at
  `sha256:657ccdcbc061490458bf269a754e671379d80d0d7ed99bf2f016fc014cce04d2`, and the six exact
  shipping inputs bind at
  `sha256:7a4dfee23cf78d2962738f86e05a5e13c5f5354cdfec186142255f61aab8de65` against Dawn
  `36cf1fae`, shaderc v2025.4, emcc 6.0.5, and Node 22.16.0.
- The real windowed product recompiles `wgpu_shader_cache.cc`, relinks, and ends at exact locked-
  Ninja no-work in `ledger/buildlogs/20260822T035341-970394.log` and
  `ledger/buildlogs/20260822T035423-970731.log`.
- Exact REUSE 6.2.0 is green for 2,032/2,032 files at
  `ledger/buildlogs/20260822T035608-972208.log`.

## Gate boundary

The contract creates no WebGPU instance, adapter, device, shader module, pipeline, or browser
receipt. Required M3 therefore remains honestly red for the absent fresh strict candidate
(`ledger/buildlogs/20260822T035459-971100.log`). Container-backed regression keeps M0 6/6 green
and M1–M8 red only on their existing strict-manifest, APPLY/artifact, browser/run-label, and
hardware boundaries (`ledger/buildlogs/20260822T035505-971197.log`). No result is promoted, and
s7's software-only Vulkan adapter remains the live blocker for fresh Linux GPU evidence.
