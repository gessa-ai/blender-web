<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T9 WebGPU texture allocation-limit validation - 2026-08-22

## Outcome

Patch 0177 makes texture creation reject physical extents, array-layer counts, and mip counts
outside the live WebGPU device limits before `Device::CreateTexture`. This prevents Dawn's
non-null validation-error texture from being retained as a valid Blender allocation.

## Diagnosis and implementation

Pinned Dawn checks 1D width, 2D width/height and array layers, 3D width/height/depth, and the
dimension-derived maximum mip count in
`build-dawn/dawn/src/dawn/native/Texture.cpp:288`. Its public creation entry point converts a
validation failure into a non-null error texture in
`build-dawn/dawn/src/dawn/native/Device.cpp:1522`. The former WebGPU backend checked only for a
null return.

`texture_allocation_supported` now mirrors that limit matrix as a pure device-free helper in
`upstream/source/blender/gpu/webgpu/wgpu_common.hh:99`. `WGPUTexture::allocate` obtains the live
device limits and requires the helper before its sole `CreateTexture` call at
`upstream/source/blender/gpu/webgpu/wgpu_texture.cc:780`. Physical 1D-array and cube allocations
remain represented by their existing WebGPU 2D-array descriptors, so the predicate evaluates the
actual descriptor rather than the logical Blender enum.

## Evidence

- The unchanged source fails exactly at the absent allocation-limit wiring before evidence
  allocation (`20260822T100051-1295822`).
- Final root and unrelated-CWD native/wasm32 runs pass 13 contracts byte-identically. The 26 new
  cases cover zero and exact limits, every over-limit axis, array layers, 1D mip rejection,
  maximum 2D/3D mip chains, and NPOT mip boundaries. Output is 1,116 bytes at SHA-256
  `babfd1617edc9b8e7f9b7e123ccd427ec031ce8c655178bb43518ab5ca8c3893`, with source SHA-256
  `448a4419d01d101b1307226396934558aa140c950e2d1d879bf6aab097c9c3f3`
  (`20260822T100559-1300436`, `20260822T100733-1302508`).
- The canonical freezer and independent replay retain 257 paths and 20,258 entries. The canonical
  patch is 1,569,723 bytes at SHA-256
  `42fd53158a55c78a3e8c8ba9a3014dbf505c931302d652620bdee704ab3b15fd`; live/replay manifests
  are byte-identical at SHA-256
  `6615aed1077016c70a1d0ca0e7bfa3309e48121fdfe47e60cd226be600deca9a`
  (`20260822T100351-1297998`, `20260822T100452-1299398`).
- The optimized windowed product rebuilds and then reports exact locked-Ninja no-work
  (`20260822T100643-1301314`, `20260822T100726-1302458`).
- REUSE 6.2.0 reports copyright and license information for all 2,063 files
  (`20260822T100907-1303720`).
- Required M3 remains red only for the absent fresh strict candidate
  (`20260822T101013-1305232`). Container-backed regression restores M0 to 6/6 green while
  M1-M8 retain their existing strict-receipt, product, browser, run-label, and hardware
  boundaries (`20260822T101020-1305344`).

## Boundary

The contract creates no WebGPU instance, adapter, device, texture, browser receipt, or result
promotion. Live texture allocation remains owned by `M3-LINUX-REPLAY`, still blocked by the named
s7 software-adapter condition.
