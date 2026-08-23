<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST device-loss in-flight cancellation — 2026-08-23

## Outcome

Implementation commit `22a5514` closes the fallback device-loss completion window. Pending
backbuffer creation/configuration, present-pipeline creation, queue submission, and present
completion now consult the callback-owned terminal device state before any Configure, handle
publication, Submit, or `note_present()` work. Owner cleanup remains monotonic at the next public
boundary, but no already-scheduled callback can publish work after the loss signal arrives.

## Diagnosis and implementation

The fallback device-lost callback correctly retained only `device_state_`, but it did not clear
`callback_lifetime_`; that owner lifetime is intentionally cleared later by
`propagateDeviceLoss()`. The asynchronous resize, pipeline, and present closures checked only the
still-live owner token, so the interval between the browser loss callback and the next GHOST entry
could configure or publish resources, submit a command buffer, and advance keepalive state.

`device_state_allows_callback_work()` gives every completion a direct acquire-load of the shared
terminal state. The two resize stages gate Configure and coherent backbuffer publication
independently, pipeline publication has its own gate, and present gates both queue submission and
the final present commit. A focused active/lost matrix creates all five closures while the state is
active, signals loss before completion, and requires zero owner-visible work from the lost set.

## Evidence

- The unchanged source fails the new source-bound guard census before evidence allocation
  (`20260823T200037-3245248`). Ambient Node v22.22.1 is independently rejected before its requested
  evidence path exists (`20260823T200322-3251253`).
- Root and descendant-CWD native/wasm32 runs pass 37 byte-identical integrated contracts, including
  ten active/lost in-flight cases, at 4,568 bytes, SHA-256
  `8cadc280ad2d4fa5551b2d45d01482aaeb897d9d6089d054ef3b663bec36d89d`, with shipping inputs
  SHA-256 `1ffc1125a4a78c54a58f6152ad5aab6ee023e9edb39f2249c8496ac4ccf7a7f3`
  (`20260823T200159-3247953`, `20260823T200243-3249229`). Both builds finish with exact no-work
  checks.
- The standalone emdawnwebgpu GHOST context compiles (`20260823T200400-3252415`). The real
  `blender_browser` rebuild and exact locked no-work check pass (`20260823T200413-3252572`,
  `20260823T200500-3253328`). OFF preflight binds the 657,928-byte JavaScript, 118,754,648-byte
  primary Wasm, and 167,143,248-byte data product (`20260823T200521-3253540`).
- Canonical replay retains 257 paths and 220 active patches at SHA-256 `f6c3e3897b13`
  (`20260823T200732-3256290`). Final REUSE 6.2.0 is green for all 2,233 tracked files
  (`20260823T200957-3257961`).
- Required M4 remains red at the unchanged unsupported browser binding. Container-backed
  regression at `2026-08-23T20:07:04Z` keeps M0 at 6/6 green while M1-M8 retain their strict
  receipt, split-product, browser, run-label, hardware, and release boundaries.

## Boundary

This is source-bound state-machine, compile/link, and native/wasm32 parity proof. It creates no
accepted hardware adapter, browser surface/pixel receipt, profile, split product, or milestone
receipt. No result promotion, dependency decision, new deferral, tolerance, golden, blacklist, or
promise changed. This iteration did not retry dzn, attempt the staged Windows path, or restart WSL.
Live proof remains deferred by the named blocker: no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn).
