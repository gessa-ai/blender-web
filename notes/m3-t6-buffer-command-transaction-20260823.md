<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 buffer command transaction - 2026-08-23

## Outcome

Patch 0215 (`0760734`) routes both short-lived command sequences in `WGPUBuffer` through the
shared checked encoder/finish/submission helper. A failed encoder now stops the large staged
upload before `CopyBufferToBuffer`; a failed finished command buffer returns failure before queue
submission. Native synchronous readback rejects the same two failures before mapping its staging
buffer. Direct `WriteBuffer` updates and the asynchronous browser readback registry are unchanged.

## Evidence

- The unchanged source fails the exact two-method contract before evidence allocation
  (`20260823T021529-2220265`).
- Root and descendant-CWD native/wasm32 runs pass 19 byte-identical integrated contracts. The new
  three-case transaction covers failed encoder, failed finished command buffer, and success; final
  output is 1,896 bytes at SHA-256
  `00ed1b1b4a00bfe8f4edf653129dc6259374de85161d5c7cd5e1ef657d58812e`, with shipping inputs at
  SHA-256 `f7a6558b0da414125ed95b68a5b5f496a235c0cba3399331ddabfd05be3e10bb`
  (`20260823T021811-2222679`, `20260823T021831-2223707`). Ambient Node 25 is rejected before
  evidence allocation (`20260823T021851-2224519`).
- The canonical freeze/replay retains 257 paths and 20,258 entries. Its 1,657,285-byte patch is
  SHA-256 `93937aa3cf375d7f41583a57b0177c08e21662a7235a76032fb0e2ab418f2151`; live/replay manifests
  are byte-identical at SHA-256
  `f5a79225efd77b4fba65542ddb61bf5b9d1fd7e24f31fdcfc1b41cc194a9e0e0`
  (`20260823T021655-2220947`, `20260823T021804-2222599`). Numbered patch 0215 is 1,534 bytes at
  SHA-256 `fe5f6636d6df42dfb488b80b3a2f0b6588cdd42b994a2c9910602f86c383fc3c` and reverse-applies
  cleanly. The optional complete historical-series diagnostic still stops at the pre-existing
  patch-0016 CMake overlap, before reaching 0215 (`20260823T021743-2222314`).
- The real `blender_browser` rebuild and exact locked no-work check are green
  (`20260823T021912-2225110`, `20260823T021952-2226280`). OFF preflight binds the resulting
  118,073,048-byte primary Wasm (`20260823T022334-2229595`). REUSE 6.2.0 covers 2,158/2,158
  implementation files (`20260823T022031-2226588`) and 2,159/2,159 after this record was added
  (`20260823T022539-2231061`).
- Required M3 remains red for the absent strict candidate. Container-backed regression at
  `2026-08-23T02:21:24Z` restores M0 to 6/6 green while M1-M8 retain their existing strict
  receipt, APPLY/product, browser, run-label, hardware, and independent M8 performance boundaries.

## Boundary

This is device-free command-handle proof. It creates no WebGPU instance, adapter, device,
submission, mapping, pixel, browser receipt, profile, or split product. Live proof remains blocked
by **no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**.
No result promotion, dependency decision, deferral, tolerance, golden, blacklist, or milestone
promise changed.
