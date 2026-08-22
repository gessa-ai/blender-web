<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T6 WebGPU storage-update padding — 2026-08-22

## Outcome

Patch 0185 stops `WGPUStorageBuffer::update()` from reading beyond Blender's caller-owned
payload when `StorageBuf::usage_size_set()` selects a byte count that is not divisible by four.
Already aligned updates retain the caller pointer. Unaligned updates copy only the logical bytes
into an aligned transfer payload and zero-fill its final one to three bytes.

## Diagnosis and implementation

WebGPU buffer writes require a four-byte transfer size. The old path rounded
`usage_size_in_bytes_` upward and passed that larger size with the original pointer, implicitly
assuming the caller owned the padding. A three-byte heap payload therefore caused Dawn or the
staging path to read four bytes.

The standalone ASan experiment in `sandbox/wgpu-storage-update-padding-repro/` reproduces the
one-byte heap over-read. The shared `BufferUpdatePayload` decision at
`upstream/source/blender/gpu/webgpu/wgpu_common.hh:569` now validates checked alignment and the
actual WebGPU allocation before any copy. It preserves the original pointer for aligned sizes and
owns zero-initialized transfer storage only when padding is required. The shipping storage-buffer
path consumes that exact result at
`upstream/source/blender/gpu/webgpu/wgpu_storage_buffer.cc:160`.

## Evidence

- The ASan minimal repro detects the three-byte-to-four-byte heap over-read
  (`20260822T141029-1520557`).
- The unchanged production source rejects the new exact wiring contract before evidence
  allocation (`20260822T141407-1523399`).
- Final repository-root and descendant-CWD native/wasm32 runs pass 13 byte-identical contracts.
  The ten new cases cover null/zero inputs, logical sizes one through five and eight, an
  under-capacity allocation, and `SIZE_MAX`; they prove two zero-copy aligned paths, four padded
  paths, four atomic rejections, and all 32 transfer bytes. Evidence is 988 bytes at SHA-256
  `56bf5c1a0285988bb5a4dbac446692054d592587a76f65fb7a7e77adf7c1840a`, with source SHA-256
  `261a0ba7e12a50e31ce1f6381026b3c2f69e66b3c485e8854bb2cce7d6d65133`
  (`20260822T142318-1533240`, `20260822T141657-1526321`).
- Wrong Dawn and Node identities reject before their requested evidence directories exist
  (`20260822T141951-1529759`, `20260822T142028-1530313`).
- The canonical freezer retains 257 paths and 20,258 entries. The patch is 1,595,570 bytes at
  SHA-256 `f5e927e5bb33746ba20eb3d20f695dd257268b5bac43053b903b8be89d05c96a`; live/replay
  manifests are byte-identical at SHA-256
  `e380fcae04925859a2d3f3b7133aa07626f3aacbae95c4ae3e34624fc3135424`
  (`20260822T141541-1524625`, `20260822T141621-1525438`).
- `blender_browser` rebuilds through locked Ninja and then reports exact no-work
  (`20260822T141714-1526813`, `20260822T141758-1527249`). The OFF-mode product preflight is
  green (`20260822T141817-1527953`).
- REUSE 6.2.0 reports copyright and license information for all 2,085 files
  (`20260822T142222-1532070`). Required M3 remains red for the absent strict candidate
  (`20260822T141901-1528597`); container-backed regression keeps M0 6/6 green while M1-M8
  retain their existing strict-receipt, product, browser, run-label, and hardware boundaries
  (`20260822T141917-1528750`).

## Boundary

The contract creates no WebGPU instance, adapter, device, buffer, command, browser receipt, or
result promotion. Live storage-update execution remains owned by `M3-LINUX-REPLAY`, still blocked
by the named s7 software-adapter condition.
