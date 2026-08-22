<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T6 WebGPU storage-copy range validation — 2026-08-22

## Outcome

Patch 0175 makes `WGPUStorageBuffer::copy_sub` reject zero-sized, misaligned, and
out-of-allocation vertex-to-storage copies before creating a command encoder. The source and
destination offsets plus the copy size must all be four-byte aligned, and both half-open spans
must fit their actual WebGPU buffer allocations.

## Diagnosis and implementation

The shared `webgpu::Buffer` update/read paths already validated alignment and used
subtraction-form containment, but the storage-buffer copy path called
`CommandEncoder::CopyBufferToBuffer` directly with unchecked frontend values. Pinned Dawn's
`ValidateB2BCopyAlignment` requires all three values to be four-byte aligned, and its buffer-copy
validation rejects either span outside the allocation.

`buffer_copy_range_valid` now centralizes that complete decision at
`upstream/source/blender/gpu/webgpu/wgpu_common.hh:84`. The shipping copy path applies it to the
source and destination allocation sizes before encoder creation at
`upstream/source/blender/gpu/webgpu/wgpu_storage_buffer.cc:193`.

## Evidence

- The unchanged production source fails the new exact contract at the absent helper
  (`20260822T092135-1261027`).
- Final root and descendant-CWD native/wasm32 runs pass 11 contracts byte-identically at 849
  bytes, SHA-256 `62552bf3931e4c36ad2f7d573f0eeb362b1917f751c482d50b857c87598c1359`.
  The nine new cases cover exact-end copies, zero size, each alignment field, both allocation
  boundaries, and a wrapped `SIZE_MAX` source range; source SHA-256 is
  `b5dda0b359f94b61ee0166694823942f7cccdefc6dbc3abda32b0c7859a1a7c8`
  (`20260822T092423-1263347`, `20260822T092446-1264085`).
- Canonical freeze/replay retains 257 paths and 20,258 entries. The canonical patch is 1,566,747
  bytes at SHA-256 `1afab3a4d7580eed99f3e116aba85c19329db1e142558130045f1652135a4ece`;
  live/replay manifests are byte-identical at SHA-256
  `7dd618da9d864ec352165ec5bd1856f99046f7d47e3310c5002b367c734f1f4f`
  (`20260822T092757-1267463`).
- The optimized windowed product rebuilds through locked Ninja and ends exact no-work
  (`20260822T092514-1264610`, `20260822T092616-1265943`).
- REUSE 6.2.0 reports copyright and license information for all 2,059 files
  (`20260822T092907-1268696`).
- Required M3 remains honestly red for the absent complete strict candidate. Docker-backed
  regression keeps M0 6/6 green while M1-M8 retain their existing strict-receipt, product,
  browser, run-label, and hardware boundaries (`2026-08-22T09:26:37Z`).

## Boundary

The contract creates no WebGPU instance, adapter, device, buffer, command, browser receipt, or
result promotion. Live copy execution remains owned by `M3-LINUX-REPLAY`, still blocked by the
named s7 software-adapter condition.
