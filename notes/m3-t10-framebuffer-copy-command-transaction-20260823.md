<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 framebuffer copy command transaction - 2026-08-23

## Outcome

Patch 0220 (`5b98d6c`) routes both direct copy paths in `WGPUFrameBuffer::blit_to` through
the shared checked encoder/finish/submission transaction. A failed encoder now stops before the
two-step stencil bridge or raw texture copy, and a failed finished command buffer stops before
queue submission. Copy geometry, aspect selection, staging layout, and render-based fallback
policy are unchanged.

## Evidence

- The unchanged canonical source fails the exact two-transaction guard before evidence allocation
  (`20260823T033723-2303479`).
- Root and descendant-CWD native/wasm32 runs pass 19 byte-identical integrated contracts. The
  shared three-case copy transaction rejects encoder and finished-command-buffer failures and
  submits exactly once on success; exact method-body checks bind all three shipping copy
  operations to the two guarded paths. Final output is 1,896 bytes at SHA-256
  `00ed1b1b4a00bfe8f4edf653129dc6259374de85161d5c7cd5e1ef657d58812e`, with shipping
  inputs at SHA-256
  `ca05afc10b2684ffd4e7d2c63c6c6acf1a75d278ce5ae41cd6a94a9e4458fc19`
  (`20260823T034036-2306415`, `20260823T034048-2307162`). Ambient Node 22.22.1 is rejected
  before its dedicated output path is created (`20260823T034105-2307984`).
- The canonical freezer and replay retain 257 paths and 20,258 entries. The 1,657,283-byte patch
  is SHA-256 `eb601f0c24f9bbab383142da02f7a2c7ce46263f76e94123a65a0445c7239f48`, and the
  live/replay manifests are byte-identical at SHA-256
  `88d77e83d35787acb775f4f28e1b78b4ff03651af476dfc266317d98df453a34`
  (`20260823T033930-2304997`). Numbered patch 0220 is 1,719 bytes at SHA-256
  `8d83946db34ca1f67f4b8b36ddebd5292dd95b86e26ce797775f10aff9d5c573` and reverse-applies
  cleanly.
- The real `blender_browser` recompiles `wgpu_framebuffer.cc`, relinks, and ends exact locked-Ninja
  no-work (`20260823T034123-2308648`, `20260823T034204-2309022`). OFF preflight binds the
  resulting 118,075,229-byte primary Wasm (`20260823T034213-2309095`).
- Final REUSE 6.2.0 is green for 2,169/2,169 files. Required M3 remains red for the absent strict
  candidate; final container-backed regression at 03:43Z restores M0 6/6 green while M1-M8 retain
  their existing strict-receipt, APPLY/product, browser, run-label, hardware, and independent M8
  performance boundaries. No gate result was promoted.

## Boundary

This is device-free command-handle proof. It creates no WebGPU instance, adapter, device,
submission, pixel, browser receipt, profile, or split product. Live proof remains blocked by **no
conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**. No result
promotion, dependency decision, deferral, tolerance, golden, blacklist, or milestone promise
changed.
