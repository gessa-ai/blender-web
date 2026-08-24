<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 async-readback contract reconciliation

## Outcome

The current patched source already contains the public owned-result readback API and the C1
object-pick continuation that the M5 deferral still described as absent. Commit `d58164f` binds
that implementation to a device-free, fail-closed contract instead of promoting it from source
inspection alone. The verifier compiles the real `gpu_readback.cc` and `gpu_select_next.cc` in
native and wasm32 configurations, then requires byte-identical output for owned-result lifetime,
all three asynchronous selection modes, exact-key and repeated-result replay, map ownership, and
failure/cancellation retirement. It also binds the public texture/storage entry points, WebGPU
exact-ticket overrides, select-instance ownership transfer, and the View3D modal
invoke/poll/timeout/cancel path across 20 source files.

The canonical receipt is `PASS`, with source digest
`da6b9a6c92d91d00afc9cdae9e88c23f81c95f21e2a1d0817e297cb5420b20c5` and byte-identical
native/wasm output digest
`33fa7c0aca5fd588219ad3d51b943b83eb9ee8b5381559ae8645d66775ddb092`. Six independent
in-memory mutations all fail closed. The wasm executable's 256 KiB stack is local to this
standalone contract because the test deliberately holds several maximum-size selection buffers;
no product linker setting changed.

## Evidence

- Native Blender test-runner target: `ledger/buildlogs/20260824T130604-73378.log`.
- Pre-commit native/wasm contract and source receipt:
  `ledger/buildlogs/20260824T132336-85884.log`.
- Six-mutation source self-check: `ledger/buildlogs/20260824T132351-86123.log`.
- Real windowed `gpu_tests` plus `blender_browser` build and locked no-work replay:
  `ledger/buildlogs/20260824T132414-86253.log` and
  `ledger/buildlogs/20260824T132426-86392.log`.
- Existing non-split product preflight:
  `ledger/buildlogs/20260824T132426-86393.log`.
- Post-source-commit native/wasm replay: `ledger/buildlogs/20260824T132924-89982.log`.
- Exact repository-local REUSE 6.2.0 coverage, 2,302/2,302 files:
  `ledger/buildlogs/20260824T132534-87615.log`.
- Required M5 scope: `ledger/buildlogs/20260824T132935-90362.log`; it remains honestly red only
  at this invocation's missing `blender_browser.deferred.wasm` complete-product boundary.
- Pinned-container regression: `ledger/buildlogs/20260824T133006-91429.log`; M0 is 6/6 green and
  M1-M8 retain their existing strict-manifest, APPLY, browser, and product boundaries.

## Remaining boundary

This closes only L-B's public owned-result API and L-C/C1's source and device-free contract. Seven
explicit synchronous families remain: legacy selection-buffer read, depth pick, depth cache,
viewport colour sample, WM window capture, WM window colour sample, and the screenshot operator.
They remain under `gpu-sync-readback-windowed` until converted to kick/poll continuations.

The verifier creates no WebGPU instance, adapter, device, browser profile, split product, or live
receipt. Live C1 and aggregate M5 acceptance therefore retain the separate named blocker
`no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)` under
`wsl2-hardware-webgpu-m5`. No dzn, Windows interop, or WSL restart path was attempted.
