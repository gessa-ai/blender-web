<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 native texture-readback command transaction - 2026-08-23

## Outcome

Patch 0222 (`f134090`) routes the native synchronous `WGPUTexture::read_sub` copy through the
shared checked command transaction. A failed command encoder or finished command buffer now returns
before queue submission and before the staging buffer is mapped. The Emscripten asynchronous ticket
path is unchanged.

## Evidence

- The unchanged canonical method fails the exact checked-copy source contract before evidence
  allocation (`20260823T041221-2337042`).
- Root and descendant-CWD native/wasm32 runs pass 19 byte-identical integrated contracts. The
  shared four-case transaction proves encoder failure stops before copy, callback failure discards
  recorded work, finished-buffer failure stops before submission, and success submits exactly once;
  the new method-body check binds that transaction before `MapAsync`. Output remains 1,918 bytes at
  SHA-256 `59d7376aa84833ab4adc4633960b068fcc44e65252515ba643408561d306aa78`,
  with 25 shipping inputs at SHA-256
  `c60bd9b06db3200f1733ac7ea124c3c0e85c323c92b6785723947b0fa301506a`
  (`20260823T041441-2339617`, `20260823T041452-2340345`). Ambient Node 25.1.0 is rejected
  before its dedicated evidence path is created (`20260823T041520-2342041`).
- The canonical freezer and replay retain 257 paths and 20,258 entries. The 1,658,717-byte patch is
  SHA-256 `17ffa01592e83b2c4a0087b8283d53921e5b3ce621dfb86f722ed88957d95f09`,
  and the live/replay manifests are byte-identical at SHA-256
  `b492f9f3fc9e379765564f2e610033b3975c7d3726904f048f4239b274971915`
  (`20260823T041415-2339225`, `20260823T041827-2345851`). Numbered patch 0222 is 860 bytes at
  SHA-256 `6fe632a5e64cd7a3758f8f40794e241df6f50091ddf8962052b5a31737de4433` and
  reverse-applies cleanly from the live postimage.
- The real `blender_browser` recompiles `wgpu_texture.cc`, relinks, and ends exact locked-Ninja
  no-work (`20260823T041548-2342708`, `20260823T041629-2343129`). OFF preflight binds the
  118,075,593-byte primary Wasm (`20260823T041659-2343407`).
- Final REUSE 6.2.0 is green for 2,173/2,173 files (`20260823T042203-2347985`). Required M3 remains red
  only for the absent strict candidate; final container-backed regression restores M0 6/6 green
  while M1-M8 retain their existing strict-receipt, split-product, browser, run-label, hardware,
  and independent M8 performance boundaries (`2026-08-23T04:17:39Z`).

## Boundary

This is device-free command-handle proof. It creates no WebGPU instance, accepted adapter, device,
copy, submission, mapping, pixel, browser receipt, profile, or split product. Live proof remains
blocked by **no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by
Dawn)**. No result promotion, dependency decision, deferral, tolerance, golden, blacklist, or
milestone promise changed.
