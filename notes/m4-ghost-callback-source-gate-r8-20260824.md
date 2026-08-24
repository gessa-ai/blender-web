<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST callback source gate R8 — 2026-08-24

## Outcome

Implementation commit `c36e225` closes the R8 callback-evidence finding without changing shipping
GPU or GHOST code. The focused gate no longer counts raw source strings or uses a narrow raw-owner
capture regex. It lexes the shipping context, treats literals as opaque and comments as absent,
then locates all eight asynchronous owner callback roles by enclosing method, call, argument,
explicit capture list, owner-delivery gate, and callback-time device-state guard.

## Contract

The manifest names adapter acquisition, fallback device loss, device acquisition, backbuffer
creation, surface configuration, present-pipeline creation, present submission, and present
completion. Seven roles must enter the exact retained owner gate; fallback loss must publish shared
terminal state through `fallback_device_loss_notify` before its owner transition. Any other
owner-gate delivery, loss notification, raw `this`, implicit outer capture, or gate/state capture
outside those roles is rejected.

Three in-memory controls bind the analyzer itself. The first replaces a real delivery with an alias
and adds dead comment text, deliberately preserving the retired grep count of seven; the structural
gate rejects it. The other controls replace an explicit outer capture with `[&]` and duplicate the
adapter callback. Both are rejected. A production-shaped device-free callback matrix exercises all
seven ordinary roles while live, delivers fallback loss once, and then rejects every retained role
after loss and after independent owner destruction.

## Evidence

- The retired focused gate passes before hardening (`20260824T033531-3675883`). The new structural
  analyzer and all three mutation controls pass independently (`20260824T034221-3679523`).
- Final root and descendant focused runs are green with byte-identical native-ASan/wasm32 behavior,
  all eight shipping roles, owner/loss/destruction cases, and both retained unsafe heap-use-after-
  free controls (`20260824T034402-3680923`, `20260824T034617-3682722`). A post-commit rerun binds
  the exact `c36e225` tree (`20260824T035130-3689040`).
- Canonical integrated native/wasm32 parity remains 38 contracts and 4,813 bytes at SHA-256
  `f54305f5871b930543386b5ea28a620c02f99248baf6a980cab574ae6630d1b9`, with shipping inputs
  SHA-256 `de3bd539e15900b95b9c0088d1e8aae2ce3fc44ab494ca751c705cf11f25924b`
  (`20260824T034630-3682938`).
- The explicit Dawn helper build-only mode is green (`20260824T034728-3684571`). One earlier
  invocation accidentally selected its default strict hardware mode: compilation completed, the
  software adapter failed the exact hardware transcript gate, no receipt was emitted, and the mode
  was not retried (`20260824T034653-3684185`). Mesa dzn and Windows were not attempted.
- The real `blender_browser` target and locked dry run are exact no-work
  (`20260824T034736-3684729`, `20260824T034739-3684779`). OFF preflight binds the 657,928-byte
  JavaScript, 118,772,391-byte Wasm, and 167,143,248-byte data product
  (`20260824T034801-3685770`).
- Canonical replay retains 257 paths and 224 active patches at SHA-256 `b71513bc33c9`
  (`20260824T034831-3686036`). Final REUSE 6.2.0 is green for all 2,254 files
  (`20260824T035254-3690450`).
- Required M4 remains honestly red only at `browser_pixels` (`20260824T034901-3686370`). Final
  container-backed regression restores M0 to 6/6 green while M1–M8 retain their existing strict-
  receipt, split-product, browser, run-label, hardware, and release boundaries
  (`20260824T034920-3686596`).

## Boundary

This is device-free source-binding and lifecycle evidence. It creates no accepted adapter, device,
browser/pixel receipt, profile, split product, result promotion, dependency decision, deferral,
tolerance, golden, blacklist, or promise. The staged Windows route was not attempted, WSL was not
restarted, and live proof remains deferred by the named blocker: no conformant hardware Vulkan ICD
in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn).
