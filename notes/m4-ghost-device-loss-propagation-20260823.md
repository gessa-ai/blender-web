<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST device-loss propagation — 2026-08-23

## Outcome

Implementation commit `2e2f560` closes the imported-device loss gap. The browser worker owns the
native `GPUDevice.lost` promise in the device's creation realm and publishes a monotonic,
generation-bound loss record before publishing the device. GHOST requires that exact record to
remain pending before initialization, swap, surface, and present work. The first missing,
replaced, unknown, or destroyed signal makes the context terminal, disables outstanding
callbacks, clears every GPU handle and pending transaction, and makes later access and swaps fail
closed.

## Diagnosis and implementation

Pinned emdawnwebgpu explicitly rejects `GetLostFuture()` for an imported device, so the C++
context could not truthfully own that device's loss callback. The old worker only logged
`device.lost`; it exposed no state to GHOST. Pinned Dawn also demonstrates why handle truthiness is
insufficient: after forced device loss it can return a non-null error texture that resembles a
presentable acquisition until the independent terminal state is consulted.

`wgpu-preinit-worker.js` now creates one loss record before device publication and updates only
that exact record from its promise, preventing an older device's late callback from poisoning a
replacement generation. The imported C++ path samples the record through API-neutral state
helpers. The fallback device-request path installs a descriptor callback that captures only a
shared atomic state, never `this`, so a late callback cannot dereference a destroyed context.
Terminal propagation is monotonic and clears readiness, surface configuration, pending flags,
pipeline/layout, backbuffer, surface, queue, and device state before any further present work.

## Evidence

- The unchanged shipping source fails the new source-bound contract before evidence allocation
  (`20260823T163105-3044341`). Ambient Node v25.1.0 is independently rejected before its requested
  evidence directory exists (`20260823T164634-3061908`).
- Final root and descendant-CWD runs pass 34 byte-identical native/wasm32 integrated contracts at
  4,101 bytes, SHA-256 `65f442ae62d3`, with shipping inputs SHA-256 `02784e6ebccf`
  (`20260823T163950-3053576`, `20260823T164605-3059912`). A pinned Node 22.16.0 matrix adds 11
  promise-order cases covering pending, pre-entry and post-entry unknown/destroyed loss, plus
  stale callback suppression. The C++ matrix adds 13 generation, terminal-state, apparent-success,
  and callback-lifetime cases.
- The pinned-Dawn build and run are green (`20260823T164020-3054816`,
  `20260823T164024-3054848`). Its llvmpipe software control delivers the real loss callback and
  then returns a non-null post-loss error texture; the shared terminal state blocks it. The output
  remains explicitly `SOFTWARE_CONTROL_NON_RECEIPT`.
- The standalone emdawnwebgpu context compiles (`20260823T164010-3054663`). The real
  `blender_browser` rebuild and exact locked no-work check pass (`20260823T164034-3055004`,
  `20260823T164112-3055357`). OFF preflight binds the 657,910-byte JS, 118,706,255-byte primary
  Wasm, and 167,143,248-byte data payload (`20260823T164116-3055878`).
- Canonical replay retains 257 paths and 216 active patches at SHA-256 `dff11e4bc854`
  (`20260823T164123-3056279`). Required M4 remains red at the unchanged unsupported browser
  binding; container-backed regression at `2026-08-23T16:43:11Z` keeps M0 at 6/6 green while
  M1-M8 retain their strict receipt, product, browser, run-label, hardware, and release boundaries.
- Pre-record REUSE 6.2.0 compliance is green for 2,219/2,219 files
  (`20260823T164238-3056775`).

## Boundary

This is state-machine, JavaScript-mock, compile/link, and software-control proof. It creates no
accepted hardware adapter, browser surface/pixel receipt, profile, split product, or milestone
receipt. No result promotion, dependency decision, new deferral, tolerance, golden, blacklist, or
promise changed. This iteration did not retry dzn, attempt the staged Windows path, or restart WSL.
Live proof remains deferred by the named blocker: no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn).
