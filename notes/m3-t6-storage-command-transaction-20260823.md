<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 storage-buffer command transaction - 2026-08-23

## Outcome

Patch 0216 (`c6dec91`) routes `WGPUStorageBuffer::copy_sub` through the shared checked
encoder/finish/submission helper after its existing source and destination range validation. A
failed encoder now stops before `CopyBufferToBuffer`; a failed finished command buffer stops before
queue submission. Storage-buffer allocation, update, clear, and readback behavior are unchanged.

## Evidence

- The unchanged shipping method fails the exact source contract before evidence allocation
  (`20260823T023458-2240017`).
- Root and descendant-CWD native/wasm32 runs pass 19 byte-identical integrated contracts. The
  shared three-case command transaction covers failed encoder, failed finished command buffer, and
  success; final output is 1,896 bytes at SHA-256
  `00ed1b1b4a00bfe8f4edf653129dc6259374de85161d5c7cd5e1ef657d58812e`, with 24 shipping inputs at
  SHA-256 `373ca971329d419bcdc2b2755ab4668dad11d63e381fed8840d4f22c9ab323eb`
  (`20260823T023506-2240240`, `20260823T023520-2240996`). Ambient Node 22.22.1 is rejected before
  evidence allocation (`20260823T023813-2244644`).
- The canonical freezer and replay retain 257 paths and 20,258 entries. The 1,657,290-byte patch is
  SHA-256 `f42e1c485f6176892ef9eca92dc5ed1fdef0b126b859bf12def0d9c05eaa10fe`; live and replay
  manifests are byte-identical at SHA-256
  `cb2faaa810a32121986199358e583e888dea49cdbdc52ce5fb491065ff286b94`
  (`20260823T023232-2237625`, `20260823T023313-2238192`). Numbered patch 0216 is 872 bytes at
  SHA-256 `eed2d82031c4237d03fd5c9588e53f040ae84dc941c25d1bb3db5e5732372ced` and reverse-applies
  cleanly.
- The real `blender_browser` recompiles the storage-buffer unit, relinks, and ends exact locked
  no-work (`20260823T023548-2241851`, `20260823T023629-2243029`). OFF preflight binds the resulting
  118,073,052-byte primary Wasm (`20260823T023636-2243079`). REUSE 6.2.0 covers 2,160/2,160
  implementation files and 2,161/2,161 after this record was added
  (`20260823T023702-2243340`, `20260823T024142-2248028`).
- Required M3 remains red only for the absent fresh strict candidate (`20260823T023721-2243549`).
  Container-backed regression restores M0 to 6/6 green while M1-M8 retain their existing strict
  receipt, APPLY/product, browser, run-label, hardware, and independent M8 performance boundaries
  (`20260823T023737-2243666`).

## Boundary

This is device-free command-handle proof. It creates no WebGPU instance, adapter, device,
submission, pixel, browser receipt, profile, or split product. Live proof remains blocked by **no
conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**. No result
promotion, dependency decision, deferral, tolerance, golden, blacklist, or milestone promise
changed.
