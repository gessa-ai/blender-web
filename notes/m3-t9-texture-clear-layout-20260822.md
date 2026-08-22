<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T9 WebGPU texture clear-layout validation - 2026-08-22

## Outcome

Patch 0180 makes non-renderable texture clears resolve every row, sample, and byte product before
allocating replicated host texels. Layouts that overflow native/wasm32 `size_t` or WebGPU's
uint32 `bytesPerRow` now fail before allocation or `Queue::WriteTexture`.

## Diagnosis and implementation

Texture allocation already checked each physical dimension against the live adapter limit, but
that does not prove that their product fits host address space. The fallback clear at
`upstream/source/blender/gpu/webgpu/wgpu_texture.cc:2049` formed `width * height * depth` and then
multiplied by the device texel size without overflow checks. On wasm32 the wrapped allocation
could therefore be smaller than the unchanged copy extent passed to Dawn. The pinned Vulkan
backend uses a resource clear command at `upstream/source/blender/gpu/vulkan/vk_texture.cc:129`
and never forms this host product.

The WebGPU fallback now reuses the atomic `TextureUploadLayout` decision from
`upstream/source/blender/gpu/webgpu/wgpu_common.hh:184` before allocation. Its checked sample
count, device-data size, and row pitch drive texel replication and the final copy descriptor at
`upstream/source/blender/gpu/webgpu/wgpu_texture.cc:2056`.

## Evidence

- The unchanged canonical source rejects the new contract at the absent clear-layout wiring
  before build or evidence allocation (`20260822T112422-1369170`).
- Root and descendant-CWD native/wasm32 runs pass 16 contracts byte-identically. The new contract
  covers three exact layouts and three zero, uint32-row-overflow, or full-product-overflow cases.
  Output is 1,456 bytes at SHA-256
  `84daaec61a9b39132a78ff0d4618303f1601f02f69bb015507a00aad20ae614a`, with source
  SHA-256 `501b41fa8d6d06d6683caac5b3603480cdf06bca139bef21d334bf72a2bf4afd`
  (`20260822T112820-1372689`, `20260822T112853-1373500`).
- A wrong-Dawn identity rejects before creating its requested evidence directory
  (`20260822T112904-1373982`).
- The canonical freezer and independent replay retain 257 paths and 20,258 entries. The canonical
  patch is 1,575,846 bytes at SHA-256
  `787d9817bf6b6e5c00496fdd720429b592a9af304d286c25d01ecebbc6e97a7d`; live/replay manifests
  are byte-identical at SHA-256
  `4310652613440ab11c15b38e3507053d56192664073148c67eac4e7f7b22440a`
  (`20260822T112650-1371021`).
- `blender_browser` recompiles the affected WebGPU edge, links, and then reports exact locked-Ninja
  no-work (`20260822T112916-1374164`, `20260822T112959-1374600`). OFF-mode product preflight is
  green (`20260822T113034-1375671`).
- REUSE 6.2.0 reports copyright and license information for all 2,069 files
  (`20260822T113345-1378490`).
- Required M3 remains red for the absent fresh strict candidate. Container-backed regression keeps
  M0 at 6/6 green while M1-M8 retain their existing strict-receipt, product, browser, run-label,
  and hardware boundaries (`2026-08-22T11:31:15Z`).

## Boundary

The contract creates no WebGPU instance, adapter, device, texture, clear, browser receipt, or
result promotion. Live clear validation remains owned by `M3-LINUX-REPLAY`, still blocked by the
named s7 software-adapter condition.
