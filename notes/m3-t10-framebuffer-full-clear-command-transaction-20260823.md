<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 framebuffer full-clear command transaction - 2026-08-23

## Outcome

Patch 0219 (`b922d87`) routes `WGPUFrameBuffer::submit_clear` and
`WGPUFrameBuffer::clear_attachment_full` through the shared checked
encoder/pass/finish/submission transaction. A failed command encoder now stops before render-pass
creation, a failed pass stops the affected layer loop, and a failed finished command buffer stops
before queue submission. This covers both multi-attachment clears and dedicated single-color-
attachment clears without changing their attachment, layer, or load/store policy.

## Evidence

- The unchanged canonical source fails the exact two-method guard before evidence allocation
  (`20260823T032121-2287288`).
- Root and descendant-CWD native/wasm32 runs pass 19 byte-identical integrated contracts. The
  shared four-case render-pass transaction rejects encoder, pass, and finished-command-buffer
  failures and submits exactly once on success; exact method-body checks bind both shipping full-
  clear paths to it. Final output is 1,896 bytes at SHA-256
  `00ed1b1b4a00bfe8f4edf653129dc6259374de85161d5c7cd5e1ef657d58812e`, with 24 shipping
  inputs at SHA-256
  `a6d1f784655c167ebd218ed3833802ffb45e325b9c3e0ca31047dcff08df7a56`
  (`20260823T032403-2289574`, `20260823T032421-2290399`). Ambient Node 25.1.0 is rejected
  before its dedicated output path is created (`20260823T032442-2291252`).
- The canonical freezer and replay retain 257 paths and 20,258 entries. The 1,657,251-byte patch
  is SHA-256 `59786bf0acfc019522199cefbbc043b63bfdbd5ded39c7182cff5065ca382728`, and live/replay
  manifests are byte-identical at SHA-256
  `17c4939ee9a229cd31182300113f2bdc06658f9785f309f52eb02687305e2c0e`
  (`20260823T032316-2289041`). Numbered patch 0219 is 1,533 bytes at SHA-256
  `8ec66dddc92934bcfc6a83de15e664475e2d6e058c33dfbc228b9c1ec906fc9d` and reverse-applies
  cleanly.
- The real `blender_browser` recompiles `wgpu_framebuffer.cc`, relinks, and ends exact locked-Ninja
  no-work (`20260823T032507-2291977`, `20260823T032547-2293120`). OFF preflight binds the
  resulting 118,074,799-byte primary Wasm (`20260823T032605-2293331`).
- Final REUSE 6.2.0 is green for 2,167/2,167 files (`20260823T033032-2297551`). Required M3 remains
  red for the absent strict candidate; final container-backed regression at 03:27Z keeps M0 6/6
  green while M1-M8 retain their existing strict-receipt, APPLY/product, browser, run-label,
  hardware, and independent M8 performance boundaries. No gate result was promoted.

## Boundary

This is device-free command-handle proof. It creates no WebGPU instance, adapter, device,
submission, pixel, browser receipt, profile, or split product. Live proof remains blocked by **no
conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**. No result
promotion, dependency decision, deferral, tolerance, golden, blacklist, or milestone promise
changed.
