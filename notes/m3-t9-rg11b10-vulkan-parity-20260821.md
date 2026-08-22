# M3.T9 RG11B10 Vulkan-conversion parity — 2026-08-21

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Patch 0156 replaces WebGPU's ad-hoc RG11B10 encoder/decoder with the pinned Vulkan backend's
exact `FormatF32`↔`FormatF11`/`FormatF10` conversion policy. The old encoder collapsed NaNs to
zero, encoded positive infinity as a NaN payload, and diverged at underflow/finite-overflow
boundaries; its decoder used a different subnormal policy. The shared conversion module now owns
the implementation, and upload, readback, and clear use the same helpers.

The fail-closed pre-fix contract stopped on the absent parity API at
`ledger/buildlogs/20260822T010723-819680.log`. The final device-free native/wasm32 contract covers
16 encode and 9 decode vectors: signed zero, ordinary values, negative finite values, both
infinities, either-signed NaNs, underflow edges, the first destination-normal exponent, maximum
in-range values, and finite overflow. It checksum-binds the ten production/oracle inputs and all
two pack/one unpack shipping call sites.

## Evidence

- Canonical freeze and isolated replay: `ledger/buildlogs/20260822T011132-823559.log`. The
  257-path / 20,258-entry patch is 1,540,303 bytes at
  `sha256:14f8fdbf157aa4216090d19e26956f2aefee5de81ad243f2ff5d938bc42561f4`; live and replay
  manifests are byte-identical at
  `sha256:5d3d221838941e8cf8c23bd2500cfc645de41d890a8bccfa3f87b356a60b0169`.
  Final canonical-only replay is green at `ledger/buildlogs/20260822T011610-828014.log`.
- Final root and descendant-CWD native/wasm32 contracts:
  `ledger/buildlogs/20260822T011215-824126.log` and
  `ledger/buildlogs/20260822T011526-827460.log`. Output is
  byte-identical at 592 bytes,
  `sha256:5f8dfe8b6058a7e17ea2c8f59581c626a312c6054e8facf7264b0cd6db8009a7`; ten exact inputs hash to
  `sha256:ffce1dd5f4d386319106adebbfbb4dbcf2385e1117bf8f796022af9dedcf18bf` against Dawn
  `36cf1fae`, emcc 6.0.5, and Node 22.16.0.
- The real windowed product rebuilt through locked Ninja and then reached exact no-work:
  `ledger/buildlogs/20260822T011240-824632.log` and
  `ledger/buildlogs/20260822T011610-828013.log`.
- REUSE 6.2.0 is green for 2,018/2,018 files:
  `ledger/buildlogs/20260822T011610-828015.log`.

## Gate boundary

The required M3 scope remains red only for the absent fresh strict candidate
(`ledger/buildlogs/20260822T011341-826008.log`). Container-backed regression keeps M0 6/6 green
and M1-M8 red on their existing strict-receipt/APPLY/artifact/browser/run-label/hardware
boundaries (`ledger/buildlogs/20260822T011403-826230.log`). No instance, adapter, device, texture,
pipeline, browser receipt, result promotion, dependency decision, deferral, tolerance, golden,
blacklist, or promise changed; s7 remains live.
