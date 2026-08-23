<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST surface failure propagation — 2026-08-23

## Outcome

Implementation commit `33dfe08` closes the post-publication surface-acquisition gap. A presentable
context now requires an optimal or suboptimal `GetCurrentTexture` status with a live texture before
encoding. Timeouts retry the existing configuration, outdated/error states force configuration
retry, lost surfaces recreate from the transferred canvas, and suboptimal frames request
reconfiguration after their accepted transaction settles. `swapBufferRelease()` now returns
failure when no present transaction was scheduled; explicit device-only contexts retain their
intentional success no-op.

## Diagnosis and implementation

The emdawnwebgpu binding catches `GPUCanvasContext.getCurrentTexture()` exceptions and returns the
WebGPU `Error` status with a null texture. The old compositor checked only the handle, returned from
every failed prerequisite without recovery, and then unconditionally returned `GHOST_kSuccess`.
An invalid browser configuration could therefore retry unchanged forever while GHOST reported that
each swap succeeded.

`GHOST_WGPUTransaction.hh` now owns an API-neutral status/action decision table. The shipping
context maps all six pinned WebGPU statuses into that table, refuses malformed success values,
preserves configured state only for a transient timeout, and keeps the current surface texture
alive through the existing validation/submission transaction. The standalone WebGPU harness now
uses the same success-status requirement when deciding whether its acquired texture is drawable.

## Evidence

- The unchanged shipping method fails the new source-bound contract before evidence allocation
  (`20260823T160814-3022099`). Ambient Node v22.22.1 is independently rejected before its requested
  evidence directory exists (`20260823T161255-3029395`).
- Final root and descendant-CWD runs pass 33 byte-identical native/wasm32 integrated contracts at
  3,943 bytes, SHA-256 `875a6fbec6d9`, with shipping inputs SHA-256 `ffc061adaf98`
  (`20260823T160954-3024339`, `20260823T161012-3025754`). The new 12-case matrix covers every
  status, valid and malformed texture presence, two accepted success forms, timeout retry,
  reconfiguration, recreation, and the synchronous present boundary.
- The standalone emdawnwebgpu context compiles (`20260823T161045-3027390`). The real
  `blender_browser` rebuild and exact locked no-work check pass
  (`20260823T161045-3027391`, `20260823T161133-3027924`). OFF preflight binds the 656,493-byte JS,
  118,704,381-byte primary Wasm, and 167,143,248-byte data payload
  (`20260823T161248-3029297`).
- Canonical replay retains 257 paths and 216 active patches at SHA-256 `dff11e4bc854`
  (`20260823T161515-3032495`). Required M4 remains red at the unchanged unsupported browser
  binding; container-backed regression at `2026-08-23T16:13:48Z` restores M0 to 6/6 green while
  M1-M8 retain their strict receipt, product, browser, run-label, hardware, and release boundaries.
- REUSE 6.2.0 compliance is green for 2,219/2,219 files (`20260823T161606-3033236`).

## Boundary

This is device-free status/state-machine, source, compile, and link proof. It creates no accepted
hardware adapter, surface/present/pixel/browser receipt, profile, split product, or milestone
receipt. No result promotion, dependency decision, new deferral, tolerance, golden, blacklist, or
promise changed. This iteration did not retry dzn, attempt the staged Windows path, or restart WSL.
Live proof remains deferred by the named blocker: no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn).
