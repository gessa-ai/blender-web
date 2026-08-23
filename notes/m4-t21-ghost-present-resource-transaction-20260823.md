<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4.T21 GHOST present resource transaction - 2026-08-23

## Outcome

Commit `844e683` makes the browser's persistent-backbuffer compositor fail closed at every
fallible WebGPU handle boundary. Resize publication preserves the last usable texture and extent
until its replacement exists; the reusable bind-group layout and render pipeline publish only as
one complete pair; and each present frame checks both views, its bind group, command encoder,
render pass, and finished command buffer before submission. The first-pixels log and keepalive
counter now advance only after the complete command buffer reaches the queue.

## Diagnosis and implementation

`GHOST_ContextWGPUWeb::ensureBackbuffer()` formerly assigned `CreateTexture()` directly into the
live handle and updated its dimensions unconditionally. A failed resize therefore discarded the
last valid texture, published dimensions for a resource that did not exist, and could not retry
because the surface's equal-size fast path returned first. `ensurePresentPipeline()` similarly
published the bind-group layout before its dependent pipeline existed.

`presentBackbuffer()` then passed unchecked source/target views, a bind group, command encoder,
render pass, and finished command buffer into dependent WebGPU calls. Its diagnostic log was
emitted before those operations, so a failed frame could also masquerade as first pixels and hide
the loader.

The new shipping `GHOST_WGPUTransaction.hh` keeps these three transactions generic and
device-free. The context creates descriptors in callbacks, while the helper owns fail-fast order
and atomic publication. A same-size configure now re-enters the idempotent backbuffer allocator,
allowing a failed resize replacement to retry without reconfiguring the surface.

## Evidence

- The unchanged compositor rejects before compilation or evidence allocation at its missing
  transaction include (`20260823T064245-2477222`).
- Final root and descendant-CWD native/wasm32 runs pass 23 byte-identical integrated contracts.
  The new contract covers 14 cases: two backbuffer replacement outcomes, four pipeline failure
  boundaries plus success, and six frame failure boundaries plus success. Evidence is 2,411 bytes
  at SHA-256 `e790a7db29cb6631810195c4f13c9764242c22815570e614f78aac0e40801e64`;
  shipping inputs are SHA-256
  `12011fd1368ffd85c0bf2e0de97a7863ab44f9308866dfebd86790839d4a1598`
  (`20260823T064348-2478798`, `20260823T064725-2483710`). Ambient Node v22.22.1 is
  rejected before its requested evidence directory exists (`20260823T064713-2483101`).
- The real `blender_browser` rebuilds successfully and then reaches exact locked-Ninja no-work
  (`20260823T064433-2480102`, `20260823T064512-2480424`). OFF preflight binds the resulting
  118,079,738-byte primary Wasm (`20260823T064539-2480675`).
- Final REUSE 6.2.0 is green for 2,187/2,187 files (`20260823T065000-2486242`).
- Required M4 remains red at its unchanged browser binding (`20260823T064623-2481840`). The final
  container-backed regression restores M0 to 6/6 green while M1-M8 retain their existing strict
  receipt, split-product, browser, run-label, hardware, and independent M8 performance boundaries
  (`20260823T064650-2482275`).

## Boundary

This is device-free resource and command-publication proof. It creates no accepted WebGPU
adapter/device, browser capture, pixel receipt, CAPTURE/APPLY profile, split product, or result
promotion. Live present proof remains blocked by **no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn)**. No dependency decision, deferral, tolerance,
golden, blacklist, or milestone promise changed.
