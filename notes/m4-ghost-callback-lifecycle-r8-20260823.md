<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST callback lifecycle R8 — 2026-08-23

## Outcome

Implementation commit `938ade4` closes two callback-lifecycle defects left after the R7 device-loss
repairs. Context destruction now excludes concurrent browser-completion access before owner storage
is released, and every already-scheduled completion samples the exact imported device-loss signal
instead of waiting for a later public GHOST poll.

## Diagnosis and implementation

`OwnerCallbackLifetime::deliver()` previously performed an atomic check followed by an unprotected
owner dereference. Destruction could clear the atomic and free the context after that check but
before the callback touched the owner. The replacement gate registers active delivery under a
mutex, stops future delivery and clears the owner at invalidation, waits for callbacks on other
threads, and permits a callback that destroys its own context to unwind without deadlocking. All
seven adapter/device, resize/configuration, pipeline, submission, and present completion sites now
route owner access through that one gate; no asynchronous context closure captures `this`.

The imported browser device had a second gap: only owner-side `deviceIsUsable()` sampled the
JavaScript `GPUDevice.lost` record. A completion queued before that poll could still read the stale
active atomic. `DeviceCallbackState` now owns the bound generation and observer, makes a missing,
replaced, or settled record a sticky terminal transition, and is consulted by every completion.
Fallback devices use the same state without an imported observer.

## Evidence

- The unchanged predecessor `d8d83c9` fails before positive evidence with only two of seven owner
  deliveries and no callback-owned imported state (`20260823T231948-3422397`).
- The focused R8 driver passes byte-identical native/wasm32 concurrent-destruction, reentrant
  destruction, delayed-delivery, and imported-loss contracts under em++ 6.0.5 / Node 22.16.0. Its
  unsafe check-then-use control is rejected by AddressSanitizer as a heap use-after-free
  (`20260823T231437-3414653`).
- The canonical render-pipeline integration driver passes its native/wasm32 suite, updated exact
  shipping-source census, pinned-Node preinit matrix, clean-pin source replay, and locked no-work
  checks (`20260823T231638-3418282`).
- The real `blender_browser` target relinks successfully and then reports exact locked Ninja
  no-work (`20260823T231736-3420945`, `20260823T231826-3421396`).
- Final REUSE 6.2.0 is green after adding the focused driver and this record
  (`20260823T232604-3428714`).
- Required M4 remains red only at its unchanged browser-pixel binding
  (`20260823T232428-3426405`). The documented Docker-group recovery restores M0 to 6/6, and the
  final container-backed regression leaves M1-M8 on their existing strict receipt, split-product,
  browser, run-label, hardware, and release boundaries
  (`20260823T232452-3426819`, `20260823T232459-3427535`).

## Boundary

This is device-free lifecycle, source-binding, native/wasm32, ASan, and product compile/link proof.
It creates no accepted hardware adapter, browser surface/pixel receipt, profile, split product, or
milestone receipt. No result promotion, dependency decision, deferral, tolerance, golden,
blacklist, or promise changed. dzn and the staged Windows path were not attempted, and WSL was not
restarted. Live pixels remain deferred by the named blocker: no conformant hardware Vulkan ICD in
WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn).
