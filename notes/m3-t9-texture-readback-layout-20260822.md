<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T9 WebGPU texture readback-layout validation - 2026-08-22

## Outcome

Patch 0179 makes synchronous and asynchronous texture readbacks validate every tight, padded,
device, and host byte product before allocating memory. Readbacks that overflow native/wasm32
`size_t`, cannot fit WebGPU's uint32 row pitches, or exceed the live device `maxBufferSize` now
fail closed.

## Diagnosis and implementation

The asynchronous browser path checked its tight sample products but did not preflight the
256-byte-padded staging allocation. The synchronous path formed its row pitch, staging size, and
host vector sizes with unchecked multiplication. Both paths could therefore allocate host memory
before the readback registry's stricter validation; the native path bypassed that registry and
reached `Device::CreateBuffer` directly. Pinned Dawn rejects an oversized descriptor only in
`build-dawn/dawn/src/dawn/native/Buffer.cpp:409`, after the backend has already formed those
products.

`TextureReadbackLayout` in `upstream/source/blender/gpu/webgpu/wgpu_common.hh:234` now resolves
tight row bytes, 256-byte padding, row/sample counts, device bytes, host bytes, staging bytes, and
the device limit atomically. `read_async` and `read` use the shared result at
`upstream/source/blender/gpu/webgpu/wgpu_texture.cc:2198` and
`upstream/source/blender/gpu/webgpu/wgpu_texture.cc:2283`; neither path allocates before the
preflight.

## Evidence

- The unchanged canonical source rejects the new contract at the absent readback-layout wiring
  before build or evidence allocation (`20260822T105409-1341476`).
- The isolated postimage compiles and passes the native/wasm32 contract before canonical
  composition (`20260822T105921-1344970`).
- Final root and descendant-CWD runs pass 15 contracts byte-identically. The new contract covers
  five accepted exact-limit layouts and ten zero, overflow, or over-limit cases. Output is 1,359
  bytes at SHA-256
  `7fee38a65a57286c980edacbe5906c2a995e3aaf7e8535bba4202e90367534ad`, with source
  SHA-256 `6cc38e7247eb2ab85758e3807d0ae1d50d9add38225bb22a67e7d74379d11f99`
  (`20260822T111121-1357810`, `20260822T111131-1358263`).
- A wrong-Dawn identity rejects before creating its requested evidence directory
  (`20260822T110548-1352792`).
- The canonical freezer and independent replay retain 257 paths and 20,258 entries. The canonical
  patch is 1,575,705 bytes at SHA-256
  `cd182d11abd926430dae921a21422f191f59e897267ad25d78172de64bb749b0`; live/replay manifests
  are byte-identical at SHA-256
  `9917405e1a50fc752a0f1e9b21558b83dc53fa28c89679dfd9bc6533e04cfc26`
  (`20260822T111017-1356815`, `20260822T111106-1357628`).
- The optimized windowed product rebuilds its affected WebGPU edge, links, and then reports exact
  locked-Ninja no-work (`20260822T111153-1358835`, `20260822T111233-1359201`).
- REUSE 6.2.0 reports copyright and license information for all 2,067 files
  (`20260822T111521-1362656`).
- Required M3 remains red only for the absent fresh strict candidate. Container-backed regression
  keeps M0 at 6/6 green while M1-M8 retain their existing strict-receipt, product, browser,
  run-label, and hardware boundaries (`2026-08-22T11:13:07Z`).

## Boundary

The contract creates no WebGPU instance, adapter, device, texture, staging buffer, map callback,
browser receipt, or result promotion. Live readback validation remains owned by
`M3-LINUX-REPLAY`, still blocked by the named s7 software-adapter condition.
