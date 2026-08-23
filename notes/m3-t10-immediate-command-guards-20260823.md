<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 immediate-draw command guards - 2026-08-23

## Outcome

Patch 0213 (`2f05b4d`) makes the immediate-mode draw path fail closed at both remaining command
handle boundaries. A null command encoder now stops before framebuffer pass creation, and a null
finished command buffer stops before queue submission. Existing pipeline, render-pass, transient
vertex/index-buffer, and draw behavior is unchanged.

This protects the immediate primitives used by Blender's UI and overlays without changing their
topology, vertex bindings, resource bindings, push constants, draw arguments, or successful
command order.

## Evidence

- The unchanged source fails the exact source-order contract at the absent encoder guard before
  evidence allocation (`20260823T013905-2185511`).
- Final root and descendant-CWD native/wasm32 runs remain byte-identical at 1,773 bytes, SHA-256
  `0f980496bd0627a8e3fedce03260f1cf560d84c9356d889d5945cea95fa029f7`, with shipping-input
  SHA-256 `9a252b3eadf6515a7140a6a0d73d9cab916dedf03bd94824f753b45d9842fb5a`
  (`20260823T014134-2187978`, `20260823T014150-2188754`). The contract requires the encoder guard
  to precede pass creation and the finished-command-buffer guard to precede submission.
- Ambient Node 25 is rejected with no evidence directory allocated
  (`20260823T014219-2189624`).
- The canonical freeze/replay retains 257 paths and 20,258 entries. The 1,656,853-byte patch is
  SHA-256 `76ef74b416cd7a294dbbf8ba87acaa6a32e018fefdebb6f9591c91c50f4e0550`; live and replay
  manifests are byte-identical at SHA-256
  `ba4c7fdba16496efb4e447a6ebd82341adf58e6bd2c73ddc3d04fc6b3868dc76`
  (`20260823T014047-2187423`). Numbered patch 0213 is 685 bytes, SHA-256
  `a20b4a9a38c648a243c7787ea13afbf1f961221bfcce7ebac7be18566465c165`, and reverse-applies
  cleanly (`20260823T014348-2191585`).
- The real `blender_browser` target recompiles only `wgpu_immediate.cc`, `libbf_gpu.a`, and the
  browser link, then reaches exact locked-Ninja no-work (`20260823T014237-2190180`,
  `20260823T014324-2191390`). OFF preflight binds the resulting 118,073,107-byte primary Wasm
  (`20260823T014341-2191535`).
- REUSE 6.2.0 covers 2,155/2,155 files (`20260823T014753-2195800`). Required M3 remains red for
  the absent fresh strict candidate; final container-backed regression at 01:44Z restores M0
  6/6 green while M1-M8 retain their existing strict-receipt, APPLY/product, browser, run-label,
  and hardware boundaries.

## Boundary

This is device-free command-handle proof. It creates no WebGPU instance, adapter, device, pass,
immediate draw, submission, pixel, or browser receipt. Live proof remains blocked by
**no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**.
No result promotion, dependency decision, deferral, tolerance, golden, blacklist, or milestone
promise changed.
