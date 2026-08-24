<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 asynchronous framebuffer readback primitive

## Outcome

Commit `19accd5` and numbered patch 0251 add owned asynchronous color and depth region reads to
Blender's framebuffer API. Backends that can safely block preserve the existing read contract and
return an immediately ready result. Browser WebGPU resolves the framebuffer's exact mip/layer,
owns one exact texture-read ticket, and waits to apply the established crop, bottom-up row order,
channel extension, and host-format conversion until that ticket settles.

The shared `GPUReadback` transform owns its source request, never retains caller memory, runs its
conversion exactly once, propagates source failures, rejects source-size drift, and cancels pending
source work with its owner. The integrated GPU test binds the requested 2x1 RGB region, source
lifetime, Emscripten Pending state, native immediate state, exact byte count, and invalid-input
failure. This unit is the common primitive needed by legacy selection-buffer and depth
continuations; it does not claim either caller conversion.

## Evidence

- The unchanged source first passed the established contract while reporting five synchronous
  caller families: `ledger/buildlogs/20260824T150350-173186.log`.
- Final fail-closed source verification rejects eight mutations. Native and wasm32 compile the
  actual `gpu_readback.cc` and emit byte-identical 290-byte evidence at
  `a221cc8c1fa08eeaa653e8c8f35801ff25c27f0bd7574a58d521fbe5c9bcfd1c`:
  `ledger/buildlogs/20260824T151831-184570.log`.
- The broader framebuffer/texture contract remains byte-identical across native and wasm32 at
  2,650 bytes, and the pipeline/scheduler contract remains byte-identical at 4,813 bytes:
  `ledger/buildlogs/20260824T151932-186003.log` and
  `ledger/buildlogs/20260824T151956-186925.log`.
- Canonical freeze/replay passes with 20,258 entries, 268 paths, patch SHA-256
  `63f048649949bccebd4d19ac7d83cee9ddb29da69cc7dd4be79f2d11cd576c64`, and manifest SHA-256
  `0278121c9351806818d2b434e98d67242e2fd96015798e2db195033db3785dbe`:
  `ledger/buildlogs/20260824T151703-183298.log` and
  `ledger/buildlogs/20260824T151746-184228.log`.
- The real optimized `blender_browser` relinks and then ends locked-Ninja no-work. OFF preflight
  binds 657,928-byte JavaScript, 118,916,377-byte Wasm, and 167,143,248-byte data:
  `ledger/buildlogs/20260824T152028-188369.log`,
  `ledger/buildlogs/20260824T152208-190384.log`, and
  `ledger/buildlogs/20260824T152220-190549.log`.
- Final REUSE 6.2.0 is green: `ledger/buildlogs/20260824T152727-195449.log`.
- Required M5 remains honestly red only at the missing `blender_browser.deferred.wasm` complete
  product: `ledger/buildlogs/20260824T152411-192207.log`. Container-backed regression restores M0
  to 6/6 green while M1-M8 retain their existing strict receipt, split-product, browser, run-label,
  and release boundaries: `ledger/buildlogs/20260824T152443-192722.log`. The post-regression
  compliance refresh removes the transient stale-receipt failure and leaves M8's unchanged 23
  technical boundaries: `ledger/buildlogs/20260824T152507-193629.log`,
  `ledger/buildlogs/20260824T152511-193661.log`, and
  `ledger/buildlogs/20260824T152516-193817.log`.

## Remaining boundary

Five synchronous caller families remain under `gpu-sync-readback-windowed`: legacy selection
buffer, depth pick, depth cache, WM window capture, and WM window colour sampling. Patch 0251
provides the owned framebuffer primitive but intentionally converts none of those callers.

This work creates no WebGPU adapter/device, browser profile, split product, live receipt, result
promotion, dependency decision, deferral, tolerance, golden, blacklist, or promise. Live C1 and
aggregate M5 acceptance remain separately deferred by the named blocker `no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`. No dzn, Windows interop, or WSL
restart path was attempted.
