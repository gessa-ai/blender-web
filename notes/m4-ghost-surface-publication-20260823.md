<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 GHOST surface publication — 2026-08-23

## Outcome

Implementation commit `0b8c500` closes audit R6's surface-less window publication finding. The
pre-main WM worker now validates the transferred canvas, WebGPU canvas configuration, acquired
surface texture, and initial persistent backbuffer before invoking Blender's synchronous main.
`GHOST_ContextWGPUWeb` imports only that complete bundle for a presentable window; any partial
stage returns `GHOST_kFailure`, so the existing window transaction destroys the candidate before
callback, manager, active-window, or event publication. Offscreen contexts select an explicit
device-only mode whose success makes no surface claim.

## Diagnosis and implementation

The old synchronous constructor imported a pre-acquired device, treated canvas/surface setup as
best effort, and returned success before the initial backbuffer's browser error scopes settled.
That was irreducibly asynchronous under the no-JSPI/no-Asyncify ADR-006 profile: after main starts,
the PROXY_TO_PTHREAD worker cannot block on its own promise callbacks.

The existing ADR-007 pre-main worker interval is the truthful wait boundary. It now records six
exact presentation states, validates configuration and backbuffer creation under validation,
out-of-memory, and internal scopes, destroys a rejected provisional backbuffer, and publishes no
surface field until the complete bundle is ready. The C++ context imports those already-validated
objects through emdawnwebgpu's object table. Its asynchronous harness path now settles readiness
only after backbuffer creation and surface configuration scopes complete; later resize
configuration remains pending and blocks presentation until accepted.

## Evidence

- The unchanged source fails before evidence allocation at the missing drawing-context status
  boundary (`20260823T153331-2990491`). Ambient Node v25.1.0 is rejected before its requested
  evidence directory exists (`20260823T154419-3000356`).
- Final root and descendant-CWD runs pass 32 byte-identical native/wasm32 integrated contracts at
  3,789 bytes, SHA-256 `92188b63787c`, with shipping inputs SHA-256 `db73221a2e3d`
  (`20260823T154115-2997134`, `20260823T155339-3009436`). The new 13-case C++ table accepts only
  explicit device-only state or a complete presentable bundle. A pinned Node 22.16.0 mock adds
  seven exact pre-main cases covering missing device/canvas/surface, configuration rejection,
  non-null-error and null backbuffers, cleanup, one-time entry forwarding, and complete
  publication.
- Canonical clean-pin replay remains green for 257 paths and 216 active patches at SHA-256
  `dff11e4bc854`. The real `blender_browser` rebuild and exact locked no-work check are green
  (`20260823T155359-3010505`, `20260823T155442-3010964`). OFF preflight binds the 655,489-byte JS,
  118,703,388-byte primary Wasm, and 167,143,248-byte data payload
  (`20260823T155448-3010995`).
- Required M4 remains red at the unchanged unsupported browser binding. The pinned-container
  regression restores M0 to 6/6 green while M1-M8 retain their existing strict-receipt,
  split-product, browser, run-label, hardware, and release boundaries
  (`20260823T155236-3008312`, ledger timestamp `2026-08-23T15:52:39Z`).
- Final REUSE 6.2.0 compliance, including this audit note, is green for 2,218/2,218 files
  (`20260823T155848-3013994`).

## Boundary

This is device-free state-machine, JavaScript-mock, source, compile, and link proof. It creates no
accepted hardware adapter, browser surface/pixel receipt, profile, split product, or milestone
receipt. No result promotion, dependency decision, new deferral, tolerance, golden, blacklist, or
promise changed. The live boundary remains deferred by the named blocker: no conformant hardware
Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). This iteration did not retry
dzn or the staged post-reboot Windows path.
