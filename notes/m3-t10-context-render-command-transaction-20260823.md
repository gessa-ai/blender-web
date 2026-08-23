<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 context render command transaction - 2026-08-23

## Outcome

Patch 0217 (`d8d331c`) routes `WGPUContext::blit_color_render`,
`WGPUContext::blit_depth_render`, and `WGPUContext::upload_depth_render` through the shared
checked encoder/pass/finish/submission transaction. A failed command encoder now stops before
render-pass creation, a failed pass stops before dependent draw work, and a failed finished
command buffer stops before queue submission. Each boolean helper returns the transaction result
instead of reporting success after a failed handle.

## Evidence

- The unchanged canonical source fails the exact three-method contract before evidence allocation
  (`20260823T024720-2253013`).
- Root and descendant-CWD native/wasm32 runs pass 19 byte-identical integrated contracts. The
  shared four-case pass transaction rejects encoder, pass, and finished-command-buffer failures
  and submits exactly once on success; all three shipping methods are source-bound to it. Final
  output is 1,896 bytes at SHA-256
  `00ed1b1b4a00bfe8f4edf653129dc6259374de85161d5c7cd5e1ef657d58812e`, with 24 shipping
  inputs at SHA-256
  `04512d960497261df605882b0006634b2a1573f1014a896283e3754b808e6add`
  (`20260823T025418-2258889`, `20260823T025431-2259629`). Ambient Node 22.22.1 is rejected
  before its dedicated output path is created (`20260823T025519-2261478`).
- The canonical freezer and replay retain 257 paths and 20,258 entries. The 1,657,243-byte patch
  is SHA-256 `ed44827e9b6ad7755eaccb3fc03104eb21e0fdab7fa6ea4a12438428e85f4885`; live and
  replay manifests are byte-identical at SHA-256
  `212a7cfcdc9645d780dc8b0793adcc40b455c0697fa5bff5223c448a9ee6ccec`
  (`20260823T025205-2256588`, `20260823T025344-2258257`). Numbered patch 0217 is 3,578
  bytes at SHA-256 `a407631f8938b968c85c65ea1d44c3778ee5d31dfe7bb88ddf7ef6279b87c50d` and
  reverse-applies cleanly.
- The real `blender_browser` recompiles `wgpu_context.cc`, relinks, and ends exact locked-Ninja
  no-work (`20260823T025542-2262079`, `20260823T025622-2262451`). OFF preflight binds the
  resulting 118,074,108-byte primary Wasm (`20260823T025647-2262693`).
- Final REUSE 6.2.0 is green for 2,163/2,163 files (`20260823T030051-2266828`). Required M3
  and container-backed regression were rerun: M0 is 6/6 green, while M1-M8 retain their existing
  strict-receipt, APPLY/product, browser, run-label, hardware, and independent M8 performance
  boundaries at 02:58Z. No gate result was promoted.

## Boundary

This is device-free command-handle proof. It creates no WebGPU instance, adapter, device,
submission, pixel, browser receipt, profile, or split product. Live proof remains blocked by **no
conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**. No result
promotion, dependency decision, deferral, tolerance, golden, blacklist, or milestone promise
changed.
