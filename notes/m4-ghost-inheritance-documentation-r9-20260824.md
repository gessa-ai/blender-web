<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST inheritance lifecycle documentation R9 — 2026-08-24

## Outcome

Implementation commit `fe1ebb4` closes the R9 contradictory-startup-comment finding. The public
class now owns one canonical lifecycle contract: the shipping windowed path acquires and validates
its mode-specific WebGPU bundle asynchronously on the WM worker before `main()`, then imports it
synchronously from `initializeDrawingContext()` without calling `initAsync()`. The separate
standalone proof path retains callback-driven `initAsync()` acquisition. Both paths retain the
shared owner-lifecycle gate and destruction boundary.

## Contract

`context_lifecycle_doc.py` extracts only the Doxygen block immediately adjacent to the exact
`GHOST_ContextWGPUWeb : public GHOST_Context` declaration. The file preamble may explain why
browser acquisition cannot block, but it may not duplicate either initialization path. The class
block must name both mode-specific acquisition paths, the synchronous import, the standalone ready
callback, the shared `CallbackLifetime` execution gate, and destruction quiescence.

Six in-memory mutations reject wrong inheritance, a shipping call to `initAsync()`, an omitted
standalone path, an omitted owner gate, correct prose moved only into the file preamble, and the
retired one-time-startup-await paragraph appended beside the corrected text. This closes the R9
false positive in which the old gate inspected only the pre-`#pragma once` prefix.

## Evidence

- The unchanged gate incorrectly accepted the contradictory class comment
  (`20260824T110404-4079432`). After the structural gate landed but before the header correction,
  it rejected the duplicated lifecycle text before compiling the native/wasm matrix
  (`20260824T110707-4081212`).
- Exact post-implementation-commit root and descendant runs pass both documented paths, all six
  documentation mutations, all eight callback roles, native-ASan/wasm32 lifecycle parity, and both
  unsafe heap-use-after-free controls (`20260824T111322-4088334`,
  `20260824T111330-4088487`).
- The canonical integrated native/wasm32 pipeline matrix remains byte-identical at 4,813 bytes,
  SHA-256 `f54305f5871b930543386b5ea28a620c02f99248baf6a980cab574ae6630d1b9`, with shipping-input
  SHA-256 `c096cd1d8a15740826b0156f837212da5ae346513e034962687d2afb389fdd28`, pinned Dawn
  `36cf1fae`, emcc 6.0.5, and Node 22.16.0 (`20260824T111211-4086689`).
- Canonical replay retains 261 paths and 225 active patches at SHA-256 `cd3eea4e7050`
  (`20260824T111050-4084151`). The real `blender_browser` rebuilt, then a locked second build and
  dry run were exact no-work (`20260824T110932-4083318`, `20260824T111020-4083794`,
  `20260824T111024-4083844`). OFF preflight binds the unchanged 657,928-byte JavaScript,
  118,909,416-byte Wasm, and 167,143,248-byte data product (`20260824T111029-4083874`).
- Pinned REUSE 6.2.0 is green for all 2,283 files (`20260824T111449-4089798`).
- Required M4 remains honestly red only at the unsupported browser binding
  (`20260824T111118-4085033`). The authoritative container-backed regression restores M0 to 6/6
  green while M1-M8 retain their existing strict-receipt, product, browser, run-label, hardware,
  and release boundaries (`20260824T111142-4085748`).

## Boundary

This is documentation and source-compliance hardening; it changes no GHOST or GPU runtime
behavior. It creates no adapter, device, browser/pixel receipt, profile, split product, result
promotion, dependency decision, deferral, tolerance, golden, blacklist, or promise. Mesa dzn and
the staged Windows route were not attempted, WSL was not restarted, and live proof remains deferred
by the named blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn
rejected by Dawn).
