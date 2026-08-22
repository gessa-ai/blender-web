# M3.T7 WGSL cache envelope integrity — 2026-08-21

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0162 makes `cache_lookup()` accept one exact WGSL cache envelope. The reader already bound
the magic, format and toolchain salt, bounded all three stage lengths, rejected short reads, and
checksummed the complete payload, but it did not inspect the byte after that payload. A file with
a valid prefix and appended stale or torn bytes therefore returned a cache hit despite the stated
fail-closed corruption contract.

The reader now requires immediate EOF with no stream error before checking the payload hash and
publishing any stage output. The cache format, key, writer, translation policy, and clean-entry
bytes remain unchanged, so no cache salt bump is required. On any trailing byte the caller's
output strings remain untouched and the normal compile path regenerates the entry.

The pre-fix exact-reader contract stored and read a clean three-stage entry, appended one byte,
then stopped because the corrupted entry was still accepted
(`ledger/buildlogs/20260822T032627-944931.log`).

## Evidence

- Canonical freeze: `ledger/buildlogs/20260822T032820-946489.log`. The authority remains 257 paths
  and 20,258 manifest entries; its 1,544,573-byte patch is
  `sha256:2b05464d60d3adde9be154ba4e9051680fdf4c2e81ae052a126bc3016e0f0290`, and the byte-identical
  live/replay manifests are
  `sha256:09eb8a314d51b4bd66e1ced20e91738738fc9a8da5beba9e065cc2e5b8cf626d`.
- Independent canonical replay: `ledger/buildlogs/20260822T032906-947064.log`.
- Final root and checkout-descendant native/wasm32 runs:
  `ledger/buildlogs/20260822T032959-948687.log` and
  `ledger/buildlogs/20260822T033225-951752.log`. Six contracts emit byte-identical 498-byte
  evidence at `sha256:3b99a93342f2462c37daba675e2c3eb68aaf78e97c7e290efff6a267986a048f`;
  the four unchanged cache entries are byte-identical at
  `sha256:d53a808d596448eb6141c7ef4fd307fe8568dd9a89dc42ad56bd4b226176fec8`, and the six exact
  shipping inputs bind at
  `sha256:b23c233e8ed1b2d28258740b563210fe667d2b5988ef56cbc5b40e97ed6d455e` against Dawn
  `36cf1fae`, shaderc v2025.4, emcc 6.0.5, and Node 22.16.0. The first post-fix execution exposed
  and rejected only a stale probe census of five contracts before that count was corrected
  (`ledger/buildlogs/20260822T032916-947602.log`).
- The real windowed product recompiles `wgpu_shader_cache.cc`, relinks, and ends at exact locked-
  Ninja no-work in `ledger/buildlogs/20260822T033022-949209.log` and
  `ledger/buildlogs/20260822T033109-949615.log`.
- Exact REUSE 6.2.0 is green for 2,030/2,030 files at
  `ledger/buildlogs/20260822T033354-953433.log`.

## Gate boundary

The contract creates no WebGPU instance, adapter, device, shader module, pipeline, or browser
receipt. Required M3 therefore remains honestly red for the absent fresh strict candidate
(`ledger/buildlogs/20260822T033152-950811.log`). Container-backed regression keeps M0 6/6 green
and M1–M8 red only on their existing strict-receipt, APPLY/artifact, browser/run-label, and
hardware boundaries (`ledger/buildlogs/20260822T033200-950906.log`). No result is promoted, and
s7's software-only Vulkan adapter remains the live blocker for fresh Linux GPU evidence.
