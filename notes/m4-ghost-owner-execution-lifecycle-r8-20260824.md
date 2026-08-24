<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST owner-execution lifecycle R8 — 2026-08-24

## Outcome

Implementation commit `9e91146` closes the first critical R8 finding.
The callback gate is now the single reentrant execution boundary for spontaneous browser
completions, stateful public `GHOST_ContextWGPUWeb` methods, and terminal device-loss cleanup.
Destruction closes admission before waiting for active execution, so neither nested nor queued
delivery can enter after teardown starts.

## Diagnosis and implementation

The prior recursive mutex covered only `OwnerCallbackLifetime::deliver()`. A WebGPU completion
could therefore configure or publish fields concurrently with a WM-thread getter, swap, resize, or
device-loss cleanup. `invalidate()` also waited for that mutex before setting `accepting_ = false`,
leaving an active callback free to deliver recursively while a destructor waited.

`OwnerCallbackLifetime::enter()` now returns a move-only execution token that retains the shared
recursive slot. All nine out-of-line owner boundaries and eight inline accessors enter it, while
the existing seven callbacks continue to route through `deliver()`. Terminal cleanup enters the
same slot before clearing GPU state. Invalidation cancels admission first, releases the state lock,
then waits for the execution slot and clears the owner. The context destructor explicitly cancels
before invalidation. Nested same-thread work and callback self-destruction remain reentrant, and a
local shared lifetime keeps the mutex alive until each public-method token releases.

## Evidence

- The unchanged source rejects before evidence allocation because no public owner-execution entry
  exists (`20260824T001712-3475021`).
- Focused root and descendant runs pass byte-identically on native ASan and wasm32, covering
  callback-vs-owner serialization, terminal-cleanup quiescence, active-callback destruction,
  blocked nested/queued late delivery, nested delivery, self-destruction, delayed rejection, and
  the retained unsafe heap-use-after-free control
  (`20260824T002013-3477677`, `20260824T002237-3481212`).
- The canonical integrated driver remains 38 native/wasm32 contracts and 4,813 byte-identical
  output bytes, SHA-256 `f54305f5871b930543386b5ea28a620c02f99248baf6a980cab574ae6630d1b9`,
  with shipping source SHA-256 `f540a56775a449acfd041caedf65388feff771dcdfd4a7eb42cc2c69ef28bf2`
  from root and descendant runs (`20260824T002025-3477839`, `20260824T002244-3481387`).
- The standalone emdawn context compiles, the real `blender_browser` rebuild and locked dry run are
  green, OFF preflight binds 657,928-byte JavaScript, 118,764,223-byte Wasm, and 167,143,248-byte
  data, and canonical replay retains 257 paths / 221 active patches
  (`20260824T002210-3480126`, `20260824T002104-3479538`, `20260824T002155-3479991`,
  `20260824T002223-3481067`, `20260824T002227-3481112`).
- Required M4 remains red at the unchanged unsupported browser binding
  (`20260824T002339-3482744`). Container-backed regression restores M0 to 6/6 green while M1–M8
  retain their existing strict-receipt, split-product, browser, run-label, hardware, and release
  boundaries (`20260824T002403-3483225`).

## Boundary

This is device-free lifecycle, source-binding, native/wasm32, ASan, and product-build proof. It
creates no accepted hardware adapter, browser/pixel receipt, profile, split product, result
promotion, dependency decision, deferral, tolerance, golden, blacklist, or promise. Mesa dzn and
the staged Windows route were not attempted, and WSL was not restarted. Live pixels remain
deferred by the named blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa
dzn rejected by Dawn).
