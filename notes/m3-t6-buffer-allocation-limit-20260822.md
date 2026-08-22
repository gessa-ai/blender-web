<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T6 WebGPU buffer allocation-limit validation - 2026-08-22

## Outcome

Patch 0176 makes the shared WebGPU buffer wrapper query the live device limits and reject an
aligned allocation above `maxBufferSize` before changing wrapper state or calling
`Device::CreateBuffer`. Zero-byte Blender buffers retain their existing four-byte sentinel
allocation.

## Diagnosis and implementation

Pinned Dawn rejects a descriptor above the device limit in
`build-dawn/dawn/src/dawn/native/Buffer.cpp:409`, then converts that validation failure into a
non-null `ErrorBuffer` in `build-dawn/dawn/src/dawn/native/Device.cpp:1266`. The former wrapper
checked only alignment overflow and treated non-null as success, so its later users could retain
an unusable buffer handle.

`buffer_allocation_size` now resolves the zero sentinel and checked four-byte alignment without
mutating its output on failure, then compares the result to the device's 64-bit limit at
`upstream/source/blender/gpu/webgpu/wgpu_common.hh:80`. `Buffer::create` requires a valid device,
a successful limit query, and that helper before its first state mutation at
`upstream/source/blender/gpu/webgpu/wgpu_buffer.cc:108`.

## Evidence

- The unchanged production source fails the new contract at the absent allocation helper
  (`20260822T093902-1276322`).
- Final root and unrelated-CWD native/wasm32 runs pass 12 contracts byte-identically. The ten new
  cases cover zero and sub-alignment requests, exact limits, aligned over-limit requests, a zero
  limit, the largest representable aligned size, and alignment overflow. Output is 911 bytes at
  SHA-256 `4e90a16acc349e9c7fe44a6a1563a5cd8fd4d868ea135f017e25a43ea3fd8d98`, with source SHA-256
  `32b9c791d83ae525d9dd473782906d33db4b752c48ffaf7bfdc9b61b66ca3710`
  (`20260822T095008-1286799`, `20260822T095019-1287522`).
- Canonical freeze and independent replay retain 257 paths and 20,258 entries. The canonical
  patch is 1,567,504 bytes at SHA-256
  `886eea5052e492eac6c0658d44872389fd60bf420e89b3aeab7d61138a3253bf`; live/replay manifests
  are byte-identical at SHA-256
  `7ff47d3453e57907bf3143f83b08debd324230c6d37f494b81b1cd68c9d82f67`
  (`20260822T094215-1278619`, `20260822T094309-1279246`).
- The optimized windowed product rebuilds and then reports exact locked-Ninja no-work
  (`20260822T094407-1281427`, `20260822T094503-1281893`).
- REUSE 6.2.0 reports copyright and license information for all 2,061 files
  (`20260822T095043-1288106`).
- Required M3 remains red for the absent fresh strict candidate (`20260822T094752-1284619`).
  Container-backed regression restores M0 to 6/6 green while M1-M8 retain their existing
  strict-receipt, product, browser, run-label, and hardware boundaries
  (`20260822T094757-1284665`).

## Boundary

The contract creates no WebGPU instance, adapter, device, buffer, command, browser receipt, or
result promotion. Live buffer allocation remains owned by `M3-LINUX-REPLAY`, still blocked by
the named s7 software-adapter condition.
