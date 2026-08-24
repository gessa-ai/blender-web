<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST callback registration census R9 — 2026-08-24

## Outcome

Implementation commit `2181d34` closes the R9 callback-evidence defect without changing shipping
GHOST or GPU source. The focused analyzer now begins at every literal
`CallbackMode::AllowSpontaneous` registration instead of inferring the asynchronous boundary only
from known owner-delivery spellings.

## Contract

The registration manifest binds all six shipping callsites by enclosing method, exact callee,
mode/callback argument positions, callback form, and count. Three `PopErrorScope` registrations
share the owner-neutral `settle` dispatcher, which retains only its shared result and invokes its
continuation once. Adapter acquisition, fallback device loss, and device acquisition bind directly
to their corresponding owner-affine role lambdas; those roles still must enter the shared lifetime
gate. Every `AllowSpontaneous` token must be one complete mode argument, and every such call must
belong to the manifest.

The retained controls reject dead-text compensation, an implicit capture, a duplicated manifested
callback, and the R9 gap mutation: a new spontaneous `PopErrorScope` callback captures
`owner_alias` after `auto *owner_alias = this` and accesses the context directly. The pre-change
analyzer accepted that exact shape while still reporting eight roles; the registration census now
rejects it.

## Evidence

- The audit's fail-first reproduction is `20260824T084359-3932717`.
- Final root and descendant focused runs compile and execute byte-identical native-ASan/wasm32
  lifecycle matrices, report eight owner roles and six spontaneous registrations, reject all four
  analyzer mutations, and retain both unsafe heap-use-after-free controls
  (`20260824T105107-4065101`, `20260824T105119-4065335`); the post-implementation-commit rerun is
  also green (`20260824T110040-4075071`).
- The canonical integrated native/wasm32 matrix remains byte-identical at 4,813 bytes,
  SHA-256 `f54305f5871b930543386b5ea28a620c02f99248baf6a980cab574ae6630d1b9`, with pinned Dawn
  `36cf1fae`, emcc 6.0.5, and Node 22.16.0 (`20260824T105738-4072097`).
- Canonical replay retains 261 paths and 225 active patches at SHA-256 `cd3eea4e7050`
  (`20260824T105456-4069170`). The real `blender_browser` rebuild completes and a second locked
  invocation plus dry-run are exact no-work (`20260824T105551-4069615`,
  `20260824T105559-4069713`); OFF preflight binds 657,928-byte JavaScript, 118,909,416-byte Wasm,
  and 167,143,248-byte data (`20260824T105607-4069786`).
- Pinned REUSE 6.2.0 is green for all 2,281 files (`20260824T105529-4069467`). Required M4 remains
  honestly red only at the unsupported browser binding (`20260824T105619-4069880`), and the final
  container-backed regression restores M0 to 6/6 green while preserving the existing M1–M8
  strict-receipt, product, browser, run-label, hardware, and release boundaries
  (`20260824T105707-4071180`).

## Boundary

This is device-free source-binding and lifecycle evidence. It creates no adapter, device,
browser/pixel receipt, profile, split product, result promotion, dependency decision, deferral,
tolerance, golden, blacklist, or promise. Mesa dzn and the staged Windows route were not attempted,
WSL was not restarted, and live proof remains deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn).
