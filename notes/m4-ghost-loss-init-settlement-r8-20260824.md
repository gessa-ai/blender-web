<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST loss/init settlement R8 — 2026-08-24

## Outcome

Implementation commit `8d7565d` closes the R8 fallback-initialization deadlock. A fallback
device-lost callback now retains only callback-owned device state and the shared owner-lifetime
gate, publishes loss before serialized owner delivery, and routes one idempotent terminal
transition through the live owner. That transition clears pending initialization work and GPU
handles, then settles the ready callback once with failure.

## Diagnosis and implementation

The prior device-lost callback only marked `device_state_`. When loss arrived during backbuffer
creation or surface configuration, the corresponding completion observed terminal state and
returned before clearing `backbuffer_pending_` or calling `completeInitialization(false)`. No later
public boundary was guaranteed, while startup waited on that callback.

`fallback_device_loss_notify()` now owns the callback-safe ordering: mark shared terminal state,
then enter `OwnerCallbackLifetime`. The production descriptor callback captures that shared state
and gate, never a raw `GHOST_ContextWGPUWeb`. `propagateDeviceLoss()` remains the single serialized,
idempotent cleanup boundary and performs failed initialization settlement only after cancellation,
pending-flag cleanup, and handle release. A device-free production-shaped probe covers independent
loss during backbuffer creation and configuration, duplicate loss, rejected late completion, exact
one-shot failure delivery, and cleared pending state.

## Evidence

- The unchanged source rejects before evidence allocation at the absent owner-gated loss route
  (`20260824T022214-3601568`).
- Final root and descendant native-ASan/wasm32 focused runs pass both pending-stage cases, duplicate
  loss, late-delivery rejection, existing owner concurrency/lifetime cases, and the unsafe ASan
  control (`20260824T024115-3620831`, `20260824T024428-3624671`).
- Canonical integrated native/wasm32 parity remains 4,813 byte-identical bytes at SHA-256
  `f54305f5871b930543386b5ea28a620c02f99248baf6a980cab574ae6630d1b9`, with shipping inputs
  SHA-256 `ad3d8526f6513213f3ee00293935eacb8dfd8fb96ffe3ca6bf2de6a4e66c5755`
  (`20260824T024121-3621439`, `20260824T024428-3624676`).
- The exact selectively staged context compiles through emdawnwebgpu, independently of the
  pre-existing unstaged fallback-limit hunk (`20260824T024356-3624371`), and the complete standalone
  emdawn harness compiles (`20260824T024428-3624684`).
- The real optimized `blender_browser` rebuild and locked no-work check are green
  (`20260824T024136-3622560`, `20260824T024219-3622973`). OFF preflight binds the 657,928-byte
  JavaScript, 118,765,616-byte Wasm, and 167,143,248-byte data product
  (`20260824T024532-3626256`). Canonical replay retains 257 paths and 223 active patches at
  SHA-256 `2b7df81dec14` (`20260824T024532-3626257`).
- Required M4 remains honestly red at the unchanged unsupported browser binding. Container-backed
  regression restores M0 to 6/6 green while M1–M8 retain their existing strict-receipt,
  split-product, browser, run-label, hardware, and release boundaries.
- Final REUSE 6.2.0 compliance is green for all 2,249 tracked files
  (`20260824T024649-3627568`).

## Boundary

This is device-free lifecycle and product-build proof. It creates no accepted adapter, browser or
pixel receipt, profile, split product, result promotion, dependency decision, deferral, tolerance,
golden, blacklist, or promise. Mesa dzn and the staged Windows route were not attempted, and WSL
was not restarted. Live proof remains deferred by the named blocker: no conformant hardware Vulkan
ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn).
