<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 indexed triangle-fan resource transaction - 2026-08-23

## Outcome

Patch 0212 (`d2c2c16`) makes the indexed triangle-fan expansion fail closed at its remaining
fallible resource boundaries. A null shader module now stops before compute-pipeline creation, and
encoder, compute-pass, or finished-command-buffer failure stops before dependent pass work or queue
submission. The existing bind-group and pipeline guards remain unchanged.

This protects Blender's WebGPU triangle-fan emulation without changing fan topology, index
expansion, restart padding, cache policy, draw arguments, or successful command order.

## Evidence

- The unchanged source fails the exact source-order contract at the absent module guard before
  evidence allocation (`20260823T011857-2160811`).
- Final root and descendant-CWD native/wasm32 runs are byte-identical at 1,773 bytes, SHA-256
  `0f980496bd0627a8e3fedce03260f1cf560d84c9356d889d5945cea95fa029f7`, with shipping-input
  SHA-256 `ce8095f6ddd6fb4ced2cc1ad7ba7bfd0ef403528f9cc50f5d92da8728a052411`
  (`20260823T012757-2171904`, `20260823T012817-2176149`). The four command cases prove encoder
  failure performs no pass work, pass failure performs no body or finish work, failed finish
  performs no submit, and success begins, encodes, ends, finishes, and submits exactly once.
- Ambient Node 25 is rejected with no evidence directory allocated
  (`20260823T012830-2176829`).
- The canonical freeze/replay retains 257 paths and 20,258 entries. The 1,656,768-byte patch is
  SHA-256 `0bf07d3cd1e0bd5bf004a6d7c6b381d4471e3966907203e7d316b060dbcabdff`; live and replay
  manifests are byte-identical at SHA-256
  `2ba000a591c53d511037d3f695656e78e97fb6b1c11ca88befbfe2376f6bce43`
  (`20260823T012045-2162183`, `20260823T012757-2171904`). Numbered patch 0212 is 1,447 bytes,
  SHA-256 `460391d5160de1422d7f935ced0bb324ae9f96d77da165da08d0ce20b3a2d4c9`, and reverse-applies
  cleanly (`20260823T012757-2171910`).
- The real `blender_browser` target recompiles `wgpu_batch.cc`, relinks, and then reaches exact
  locked-Ninja no-work (`20260823T012156-2164884`, `20260823T012237-2165268`). OFF preflight
  binds the resulting 118,073,149-byte primary Wasm (`20260823T012314-2165670`).
- REUSE 6.2.0 covers 2,153/2,153 files (`20260823T013119-2179088`). Required M3 remains red for
  the absent fresh strict candidate (`20260823T012512-2169030`); container-backed regression keeps
  M0 6/6 green while M1-M8 retain their existing strict-receipt, APPLY/product, browser, run-label,
  and hardware boundaries (`20260823T012551-2169577`).

## Boundary

This is device-free command/resource proof. It creates no WebGPU instance, adapter, device,
module, pipeline, pass, fan draw, submission, pixel, or browser receipt. Live proof remains blocked
by **no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**.
No result promotion, dependency decision, deferral, tolerance, golden, blacklist, or milestone
promise changed.
