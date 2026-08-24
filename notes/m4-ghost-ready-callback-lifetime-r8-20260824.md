<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST ready-callback lifetime R8 — 2026-08-24

## Outcome

Implementation commit `56f7057` closes the R8 ready-settlement lifetime defect. Before invoking
the user-supplied ready callback, `completeInitialization()` now moves it out of context member
storage and explicitly clears the member. The detached callable is the settlement path's final
owner action, so it may destroy its `GHOST_ContextWGPUWeb` and still finish executing from live
local storage.

## Diagnosis and implementation

The previous code called `on_ready_(success)` directly. A legitimate callback can delete the
context as part of window/bootstrap settlement; that destroys the active `std::function` and its
callable target before `std::function::operator()` returns. Merely avoiding later field access does
not repair that use-after-free because the executing callable itself belonged to the deleted owner.

The focused probe now models the production member-storage path with a stateful ready callable
that deletes its owner and then reads its own callable state. The accepted probe moves and clears
the callback before delivery; the retained direct-member control must be rejected by native
AddressSanitizer. The same accepted contract runs byte-identically under wasm32 and rejects later
delivery through the production owner-lifetime gate.

## Evidence

- The unchanged shipping source rejects before test evidence allocation because the ready callback
  remains in owner storage (`20260824T030238-3640274`).
- The final focused runner passes native-ASan and wasm32 owner/loss/readiness contracts, including
  a self-destroying ready callback, and retains both unsafe owner-race and unsafe member-callback
  ASan rejections (`20260824T030254-3640410`).
- Canonical integrated native/wasm32 parity remains 4,813 byte-identical bytes at SHA-256
  `f54305f5871b930543386b5ea28a620c02f99248baf6a980cab574ae6630d1b9`, with shipping inputs
  SHA-256 `c57f1f4256b7d2d857eb87eb68ba8388e9a652ec939c33032c8dafdf5425c24b`
  (`20260824T030502-3643114`).
- The real optimized `blender_browser` target recompiles the GHOST context and relinks, then the
  locked dry run reports exact no-work (`20260824T030644-3645656`,
  `20260824T030727-3646058`). OFF preflight binds the 657,928-byte JavaScript,
  118,765,454-byte Wasm, and 167,143,248-byte data product (`20260824T030744-3646180`).
- Canonical replay retains 257 paths and 223 active patches at SHA-256 `2b7df81dec14`
  (`20260824T030801-3646390`). The implementation commit contains only the ready-lifetime source
  hunk and focused evidence changes; the pre-existing fallback-limit hunk remains unstaged.
- Required M4 remains honestly red at the unchanged unsupported browser binding
  (`20260824T030857-3648359`). Container-backed regression restores M0 to 6/6 green while M1–M8
  retain their existing strict-receipt, split-product, browser, run-label, hardware, and release
  boundaries (`20260824T030902-3648409`).
- Final REUSE 6.2.0 compliance is green for all 2,250 tracked files
  (`20260824T031153-3651157`).

## Boundary

This is device-free lifecycle and product-build proof. It creates no accepted adapter, browser or
pixel receipt, profile, split product, result promotion, dependency decision, deferral, tolerance,
golden, blacklist, or promise. Mesa dzn and the staged Windows route were not attempted, and WSL
was not restarted. Live proof remains deferred by the named blocker: no conformant hardware Vulkan
ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn).
