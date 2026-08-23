<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST window publication transaction - 2026-08-23

## Outcome

Commit `472d9b1` makes a web window valid only when its requested drawing context initializes,
then publishes only a valid window to the active-window slot, HTML callback bridge, window
manager, and initial event queue. A failed WebGPU context is destroyed and returned as null
instead of surviving behind the base class's fallback `GHOST_ContextNone`.

## Diagnosis and implementation

`GHOST_WindowWeb` called `setDrawingContextType()` but ignored its result while `valid_` retained
the default `true`. `GHOST_SystemWeb::createWindow()` then registered and returned the candidate
without checking `getValid()`. This differed from the pinned SDL, X11, Win32, and Wayland GHOST
backends, all of which reject invalid windows before manager publication.

The shared transaction helper now derives validity from the exact context-setter status and
orders null/invalid/valid window publication explicitly. The constructor binds the first half;
the system binds the second and performs every observable side effect only inside the valid
branch. Class 44 in `notes/porting-patterns.md` records the recurring parent-publication pattern.

## Evidence

- The unchanged web window failed the new source contract at its absent transaction include,
  before the fresh evidence directory existed (`20260823T065826-2492630`).
- Root and descendant-CWD native/wasm32 runs pass 24 byte-identical integrated contracts. The
  new contract covers two drawing-context statuses and null/invalid/valid windows; evidence is
  2,559 bytes at SHA-256
  `0e65942cd4b7b9820c5e5f47fa116f215d7899da7a990658adf2fe57d810d56b`, with shipping inputs
  SHA-256 `7baa780d0fb94932cb7b626cd2f297b5889185feaa9ebc679878529bd11b0613`
  (`20260823T065901-2493266`, `20260823T070042-2495795`). Ambient Node 22.22.1 is rejected before
  allocating its requested evidence directory (`20260823T070056-2496640`).
- The real `blender_browser` rebuild completes and the next locked invocation is exact no-work
  (`20260823T065929-2495181`, `20260823T070030-2495703`). OFF preflight binds the resulting
  118,079,789-byte primary Wasm (`20260823T070112-2497274`).
- Required M4 remains red at the unchanged browser binding at 2026-08-23T07:01:48Z. The final
  container-backed regression keeps M0 6/6 green while M1-M8 retain their existing strict
  receipt, split-product, browser, run-label, hardware, and independent M8 performance boundaries
  (`20260823T070144-2498503`).
- Final REUSE 6.2.0 compliance is green for 2,188/2,188 files.

## Boundary

This is device-free initialization and publication proof. It creates no accepted WebGPU adapter,
device, browser capture, pixel receipt, CAPTURE/APPLY profile, split product, or result promotion.
Live pixel proof remains blocked by **no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships
none; Mesa dzn rejected by Dawn)**. No dependency decision, deferral, tolerance, golden,
blacklist, or milestone promise changed.
