# P0-E hardware resize receipt ingestion — 2026-08-27

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Commit `3168ee0` closes the post-capture integrity gap in the P0-E Apple acceptance lane without
changing the pending runtime candidate. The producer now records the byte count and SHA-256 of all
five canonical CAPTURE files plus every retained boot, pre-resize, and shrink PNG. A separate
consumer re-hashes those bytes after evidence returns to this checkout and independently replays
the calibrated VIEW_3D semantic test for all ten attempts.

P0-E remains open. This contract can reject stale or altered evidence, but it cannot replace the
driver-operated Apple M4 Pro run or bind hardware pixels on this WSL2 host.

## Fail-closed boundary

The independent consumer requires:

- schema-v1 `PASS`, exactly 10 ordered attempts, and exactly 30 named PNGs plus `receipt.json`;
- the exact producer source, local CAPTURE JS/Wasm/original/data/manifest, and served generation;
- Node 22.16.0, Playwright 1.61.1, PNGJS 7.0.0, and Chromium 149.0.7827.55;
- an `ACCEPTED` `hardware-webgpu-adapter-v1` record with fallback false and no software token;
- zero post-resize input, page errors, or relevant WebGPU errors on every attempt;
- three consecutive semantic shrink samples inside 24 seconds, with the retained final PNG
  independently decoding below the unchanged `dominantFraction < 0.95` threshold; and
- no missing, extra, symlinked, size-drifted, or hash-drifted evidence file.

The mutation self-check rejects failed/nine-attempt receipts, fallback adapters, post-resize input,
page errors, unstable shrink streaks, threshold drift, stale producer/product/image identities,
changed PNG bytes, a hash-consistent flat shrink frame, and an unexpected inventory file.

## Verification

- Producer self-check: `20260827T131929-2056439`, 32 positive / 17 negative.
- Independent consumer self-check: `20260827T131929-2056447`, 2 positive / 13 negative.
- Resize source/trace and native+Wasm integrated queue contracts:
  `20260827T131750-2053829` / `2053830` / `2053834`.
- CAPTURE unit preflight, exact live-product preflight, and REUSE 6.2.0:
  `20260827T131929-2056422` / `2056427` / `2056420`.
- Direct M4 stays correctly RED for the absent accepted binding:
  `20260827T132000-2056738`.
- Pinned-oracle container regression restores M0 6/6 and retains the named M1-M8 boundaries:
  `20260827T132055-2057559`.

The unchanged CAPTURE identities are JS `5b6ed02286fd`, instrumented Wasm `a8d75b880e2c`,
`.wasm.orig` `2f45a8ed62eb`, data `095d0ba748c3`, and split manifest `4f0cbcbc21bb`.
