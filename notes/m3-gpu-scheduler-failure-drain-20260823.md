<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 scheduler failure-drain contract — 2026-08-23

## Outcome

Commit `a15900d` and patch 0244 close R7's poisoned-queue recursion and failed-epoch retention
defects. `OrderedQueueScheduler` now has one mutex-protected drain owner: synchronous operation
completion or cancellation releases the active entry back to that owner's loop instead of
recursively starting another drain. Exact queued-reference counts retain a failed epoch while it
is current or still names queued work, then prune it as soon as neither condition remains.

## Evidence

- The unchanged scheduler overflows while canceling the new 100,000-follower stress queue and
  exits `rc=139` (`20260823T201801-3265196`).
- Final root and descendant-CWD native/wasm32 runs pass 38 byte-identical integrated contracts.
  The scheduler slice cancels 100,000 same-epoch followers with zero execution, advances through
  100,000 distinct failed epochs with retained peak 1/final 0, and accepts a clean retry. Evidence
  is 4,813 bytes at SHA-256
  `f54305f5871b930543386b5ea28a620c02f99248baf6a980cab574ae6630d1b9`, with shipping inputs at
  SHA-256 `acb62aa3b3d9d306061fdc5e6efebe06e78d764494fee77d262abb3e88b6ac41`
  (`20260823T202401-3270274`, `20260823T202433-3271720`).
- Pinned Node remains part of the evidence boundary: system Node 22.22.1 is rejected before the
  isolated output path exists (`20260823T202500-3272944`).
- Numbered patch 0244 is 5,035 bytes at SHA-256
  `2aef99e9ec732dc6ab5361ac7ff3f0f610e5329909fc27ba6ec1f88367887070` and passes isolated
  reverse/forward exact-postimage replay (`20260823T202918-3278149`). Canonical freeze/replay
  retains 257 paths and 20,258 entries; its 1,755,214-byte patch is SHA-256
  `c5d2328a83d0ea403971b5fe3fd00ba5670149513db5498a24aba2cdc0e3a318`, with byte-identical
  3,477,335-byte manifests at SHA-256
  `546aabd9adeba5dca1a1d493424418ad6a4af9941cfcf2e4fdfd624b65d13f62`
  (`20260823T202307-3269658`, `20260823T202525-3274635`).
- The real `blender_browser` target rebuilds and ends locked no-work
  (`20260823T202539-3274805`, `20260823T202625-3275187`). OFF preflight binds the 657,928-byte JS,
  118,756,684-byte Wasm, and 167,143,248-byte data product (`20260823T202635-3275308`).
- Final REUSE 6.2.0 is green for all 2,235 files (`20260823T203035-3279423`). Required M3
  remains red only for the absent fresh strict candidate (`20260823T202700-3275506`); final
  container-backed regression restores M0 6/6 green while M1-M8 retain their existing strict
  receipt, split-product, browser, run-label, hardware, and release boundaries
  (`20260823T202729-3275949`). No gate result was promoted.

## Boundary

This is device-free scheduler/source and compile/link proof. It creates no accepted hardware
adapter, browser/pixel receipt, profile, split product, result promotion, dependency decision, new
deferral, tolerance, golden, blacklist, or milestone promise. Live hardware proof remains deferred
by the named blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn
rejected by Dawn). This iteration did not retry dzn, attempt the staged Windows path, or restart
WSL.
