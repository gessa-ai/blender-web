<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T9 WebGPU texture upload-layout validation - 2026-08-22

## Outcome

Patch 0178 makes every uncompressed texture sub-upload validate its physical copy box and all
host/device byte products before allocating conversion storage or reading caller memory. Invalid
widths, undersized source row strides, uint32 WebGPU row overflows, and native/wasm32 `size_t`
overflows now fail closed.

## Diagnosis and implementation

The public `GPU_texture_update_sub` entry point forwards signed offsets/extents without a runtime
range check (`upstream/source/blender/gpu/intern/gpu_texture.cc:531`). The former WebGPU path
formed `sample_count`, allocated `device_data`, and converted caller bytes before resolving the
destination subresource at `upstream/source/blender/gpu/webgpu/wgpu_texture.cc:1482`. Its depth
arm also added signed offsets/extents before casting. Pinned Dawn validates the copy range and
linear layout only inside `QueueBase::ValidateWriteTexture`
(`build-dawn/dawn/src/dawn/native/Queue.cpp:556`), after those host operations have already
happened.

`TextureUploadLayout` in `wgpu_common.hh` now checks row count, sample count, source stride and
last-byte extent, device conversion size, and WebGPU's uint32 `bytesPerRow`. A separate
subtraction-form predicate validates a non-empty physical copy box without addition overflow.
`WGPUTexture::update_sub` resolves both before its depth or ordinary conversion allocations; the
pixel-buffer overload uses the same source-size result before exposing its bytes. Physical
1D-array uploads retain Blender's logical Y-as-layers convention and reject a formerly ignored
non-unit Z extent.

## Evidence

- The unchanged canonical source fails only at the absent upload-layout wiring, before evidence
  allocation (`20260822T102618-1318609`).
- Root and unrelated-CWD native/wasm32 runs pass 14 contracts byte-identically. The new contract
  covers 14 tight/strided/invalid/overflow layouts and 13 exact physical copy-region boundaries.
  Output is 1,251 bytes at SHA-256
  `b31e7d321dfc59899964db8f5ce3b156a0fe66a0604f47dabef14e4916fa4c94`, with source SHA-256
  `98fa5734a2ad7d2d7782d16bdeadfe1de8e55a6fb0eba548535ead5f14ed62d4`
  (`20260822T103411-1324889`, `20260822T103721-1328261`).
- A wrong-Dawn identity rejects before creating its requested evidence directory
  (`20260822T103754-1328845`).
- The canonical freezer and independent replay retain 257 paths and 20,258 entries. The canonical
  patch is 1,574,038 bytes at SHA-256
  `9bdf18537414991749e88d1e86738c234914e19e6f3cbc59cd37fd4c538d9a74`; live/replay manifests
  are byte-identical at SHA-256
  `2a29bdb087d4792af08819eed932a2c20cae1b821aafda3bed0a56416d46395b`
  (`20260822T103300-1322917`, `20260822T104444-1334030`).
- The optimized windowed product rebuilds and then reports exact locked-Ninja no-work
  (`20260822T103437-1325494`, `20260822T103519-1325885`).
- REUSE 6.2.0 reports copyright and license information for all 2,065 files
  (`20260822T103908-1330218`).
- Required M3 remains red only for the absent fresh strict candidate
  (`20260822T103631-1327199`). Container-backed regression keeps M0 at 6/6 green while M1-M8
  retain their named strict-receipt, product, browser, run-label, and hardware boundaries
  (`20260822T103640-1327320`).

## Boundary

The contract creates no WebGPU instance, adapter, device, texture, upload, browser receipt, or
result promotion. Live upload validation remains owned by `M3-LINUX-REPLAY`, still blocked by the
named s7 software-adapter condition.
