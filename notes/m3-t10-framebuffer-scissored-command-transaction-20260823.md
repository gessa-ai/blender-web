<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 framebuffer scissored-clear command transaction - 2026-08-23

## Outcome

Patch 0218 (`3a0af60`) routes `WGPUFrameBuffer::submit_scissored_color_clear` and
`WGPUFrameBuffer::submit_scissored_depth_stencil_clear` through the shared checked
encoder/pass/finish/submission transaction. A failed command encoder now stops before render-pass
creation, a failed pass stops before dependent clear work, and a failed finished command buffer
stops before queue submission. Both boolean helpers return the transaction result instead of
reporting success after a failed handle.

## Evidence

- The unchanged canonical source fails the exact two-method contract before evidence allocation
  (`20260823T030703-2271633`).
- Root and descendant-CWD native/wasm32 runs pass 19 byte-identical integrated contracts. The
  shared four-case pass transaction rejects encoder, pass, and finished-command-buffer failures
  and submits exactly once on success; both shipping methods are source-bound to it. Final output
  is 1,896 bytes at SHA-256
  `00ed1b1b4a00bfe8f4edf653129dc6259374de85161d5c7cd5e1ef657d58812e`, with 24 shipping
  inputs at SHA-256
  `c820922bcb05eb8a2e563fd401ada725c0885de63a0a1d371c68a896afe52510`
  (`20260823T031013-2275048`, `20260823T031104-2276773`). Ambient Node 25.1.0 is rejected
  before its dedicated output path is created (`20260823T031124-2277619`).
- The canonical freezer and replay retain 257 paths and 20,258 entries. The 1,657,203-byte patch
  is SHA-256 `8148fa2f8df1bf5eada046a46c6ded602b7903b0ec0cf23242bf247c8481bed5`; live and
  replay manifests are byte-identical at SHA-256
  `b35b6db2c974f5af7550b8be04632fae9f73de2df67dcde7cb3745832bf83f44`
  (`20260823T030906-2274217`, `20260823T031137-2278182`). Numbered patch 0218 is 2,590
  bytes at SHA-256 `8fea13e67854aed9665c5fbf7a789049da41af27e281092e60de4e08a78a3c64` and
  reverse-applies cleanly.
- The real `blender_browser` recompiles `wgpu_framebuffer.cc`, relinks, and ends exact
  locked-Ninja no-work (`20260823T031147-2278282`, `20260823T031230-2278665`). OFF preflight
  binds the resulting 118,074,721-byte primary Wasm (`20260823T031249-2278837`).
- Final REUSE 6.2.0 is green for 2,165/2,165 files (`20260823T031645-2283104`). Required M3
  remains red for the absent strict candidate; final container-backed regression at 03:14Z keeps
  M0 6/6 green while M1-M8 retain their existing strict-receipt, APPLY/product, browser,
  run-label, hardware, and independent M8 performance boundaries. No gate result was promoted.

## Boundary

This is device-free command-handle proof. It creates no WebGPU instance, adapter, device,
submission, pixel, browser receipt, profile, or split product. Live proof remains blocked by **no
conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**. No result
promotion, dependency decision, deferral, tolerance, golden, blacklist, or milestone promise
changed.
