<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 texture-copy command transaction - 2026-08-23

## Outcome

Patch 0223 (`ef53318`) keeps the complete `WGPUTexture::copy_to` per-mip loop inside the shared
checked command transaction. A failed command encoder now stops before any mip is resolved or
copied, and a failed finished command buffer stops before queue submission. Compatible mip copies
and incompatible or mismatched mip skips retain their existing order and behavior.

## Evidence

- The unchanged shipping method fails the exact checked multi-mip source contract before evidence
  allocation (`20260823T042634-2352169`).
- Root and descendant-CWD native/wasm32 runs pass 19 byte-identical integrated contracts. The
  shared four-case transaction proves encoder failure stops before copy, callback failure discards
  recorded work, finished-buffer failure stops before submission, and success submits exactly once;
  the method-body check binds the transaction around all five per-mip compatibility decisions and
  their skip before `CopyTextureToTexture`. Output remains 1,918 bytes at SHA-256
  `59d7376aa84833ab4adc4633960b068fcc44e65252515ba643408561d306aa78`, with 25 shipping
  inputs at SHA-256 `1f4c39db7f23a1f7dd7afff663d3de6f37a4bd0a81bce8b9cdda84ffaf7a8e2e`
  (`20260823T043039-2355732`, `20260823T043052-2356499`). Ambient Node 25.1.0 is rejected
  before its dedicated evidence path is created (`20260823T043113-2357342`).
- The canonical freezer and replay retain 257 paths and 20,258 entries. The 1,659,055-byte patch is
  SHA-256 `e64cadcf646c9a53e2e7b744179136ddf6d3642fcaf18ca64d90f596f84f53e8`, and the
  live/replay manifests are byte-identical at SHA-256
  `e643b3a07ea88072522251b77d2a2b70b64c3e3f1014cd7237911f96d84f41dd`
  (`20260823T042959-2354390`). Numbered patch 0223 is 3,830 bytes at SHA-256
  `8b9cdd29a9ac40f0af42203f058bf6a5520e29459daecdece6c6c141289ad8cc` and both
  applies to its isolated preimage and reverse-applies from the live postimage.
- The real `blender_browser` recompiles `wgpu_texture.cc`, relinks, and ends exact locked-Ninja
  no-work (`20260823T043146-2358014`, `20260823T043227-2359159`). OFF preflight binds the
  118,075,905-byte primary Wasm (`20260823T043250-2359370`).
- Final REUSE 6.2.0 is green for 2,175/2,175 files (`20260823T043752-2363922`). Required M3
  remains red only for the absent strict candidate; final container-backed regression leaves M0
  6/6 green while M1-M8 retain their existing strict-receipt, split-product, browser, run-label,
  hardware, and independent M8
  performance boundaries (`2026-08-23T04:34:56Z`).

## Boundary

This is device-free command-handle proof. It creates no WebGPU instance, accepted adapter, device,
copy, submission, pixel, browser receipt, profile, or split product. Live proof remains blocked by
**no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**. No
result promotion, dependency decision, deferral, tolerance, golden, blacklist, or milestone promise
changed.
