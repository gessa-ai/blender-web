<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU staging resource scope R8 — 2026-08-24

## Outcome

Implementation commit `412e10b` and patch 0247 close R8's unscoped large-upload staging
allocation. `Buffer::update_allocation()` now reserves the shared transient resource gate before
creating its mapped staging buffer. The dependent command ticket is reserved behind that gate, so
a non-null validation, out-of-memory, or internal error object poisons only the current frame epoch
and cancels submission. The retained payload remains retryable in a later clean epoch.

## Evidence

- The unchanged backend fails the new extracted behavior contract: its non-null staging error
  object is created outside every implementation scope and increments the uncaptured-error counter
  (`20260824T031833-3656732`).
- Final root and descendant-CWD native/wasm32 runs pass 20 byte-identical integrated contracts,
  including 13 large-buffer cases with six creation/encoding scope callbacks before the dependent
  command, same-epoch cancellation, zero uncaptured errors, and exact retained-byte retry. Evidence
  is 1,863 bytes at SHA-256
  `d87546f844bd7ed26dd90627afae9d8966be997760fcfd80a91f8f54b725e112`; shipping inputs are
  SHA-256 `97d3b98c7865d3143044dc5b572cb34d1237c6524a2854b8ae2a84a05b2a2b99`
  (`20260824T032838-3668707`, `20260824T032856-3669584`). Ambient Node 25.1.0 is rejected before
  its requested evidence path exists (`20260824T032637-3665905`).
- The pinned Dawn control builds and passes on
  `llvmpipe (LLVM 21.1.8, 256 bits)`, including its real non-null transient-buffer error object,
  while emitting `SOFTWARE_CONTROL_NON_RECEIPT` (`20260824T032325-3663566`,
  `20260824T032336-3663664`). It binds no M3/M4 receipt.
- Patch 0247 is 837 bytes at SHA-256
  `2289fd160fcf90e99ef19205b308e68baf00dc6f1c8d1c6eee1727e9738c4e62` and passes an isolated
  reverse/forward exact-byte round trip (`20260824T032953-3670591`). The canonical freezer and
  replay retain 257 paths and 20,258 entries at patch SHA-256
  `b71513bc33c94987d3629a94d7f642d790a101e7624bf8a81f926fcff64cfa49` and manifest SHA-256
  `161ddc65dd37103d6930c9c0f00333c374072e1486d593616ed324e5579c5f1f`
  (`20260824T032046-3659399`, `20260824T032451-3664109`).
- The real optimized `blender_browser` target rebuilds and ends locked no-work
  (`20260824T032512-3664303`, `20260824T032555-3665534`). OFF preflight binds a 657,928-byte
  JavaScript file, 118,772,391-byte Wasm, and 167,143,248-byte data file
  (`20260824T032620-3665760`).
- Required M3 remains honestly red only for the absent fresh strict candidate
  (`20260824T032725-3666717`). Container-backed regression restores M0 to 6/6 green while M1-M8
  retain their existing strict-receipt, split-product, browser, run-label, hardware, and release
  boundaries (`20260824T032735-3666821`). No result was promoted.
- Final REUSE 6.2.0 compliance is green for all 2,252 tracked files
  (`20260824T033123-3671928`).

## Boundary

This is device-free CPU/source and compile/link proof. It creates no accepted hardware adapter,
browser/pixel receipt, profile, split product, result promotion, dependency decision, new
deferral, tolerance, golden, blacklist, or milestone promise. Mesa dzn and the staged Windows path
were not attempted, and WSL was not restarted. Live proof remains deferred by the named blocker:
no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn).
