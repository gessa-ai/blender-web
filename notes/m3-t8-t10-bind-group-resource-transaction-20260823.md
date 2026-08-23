<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 compute/draw bind-group resource transaction - 2026-08-23

## Outcome

Patch 0224 (`259a2e5`) rejects a failed transient bind group before dependent compute, batch,
or immediate pass work. The shared helper publishes only a non-null candidate and preserves the
caller's prior handle on failure. Compute keeps a valid no-bind-group state distinct from a
required group whose creation failed; both direct and indirect dispatch now stop on the latter.
All four ordinary/multi-viewport direct/indirect batch paths and the immediate path likewise stop
before `SetBindGroup` or draw work.

## Evidence

- The unchanged shipping source fails before evidence allocation because the transient-handle
  transaction is absent (`20260823T044608-2371047`).
- Final root and descendant-CWD native/wasm32 runs pass 20 byte-identical integrated contracts.
  The new two-case transaction rejects a null candidate without changing the output and publishes
  one valid candidate; exact source checks bind it to all six bind-group creation sites and both
  compute callers. Output is 2,030 bytes at SHA-256
  `5c4c0acc7ef52f5eb01efdd39bf6f1cd6b83e1f953e024de91af2008463aeb7f`, with 25
  shipping inputs at SHA-256
  `35f69b5d448ca3f70ee489cb2b1846444daa3055d5d4cd29a75461186210ddd1`
  (`20260823T045352-2379996`, `20260823T045005-2375250`). Ambient Node 25.1.0 is rejected
  before its requested evidence directory exists (`20260823T045027-2376074`).
- The canonical freezer retains 257 paths and 20,258 live/replay entries. The 1,660,652-byte
  patch is SHA-256 `bb0e1aedd51b41acb6afaf2d04b7ad761a390bb2ef4bd744ebf15db13c5cf0ae`,
  and both manifests are byte-identical at SHA-256
  `c4730e5a79f852c63e346b3d12e25bb54e6242561b15fcf171241c9646611ae4`
  (`20260823T044820-2372728`). Numbered patch 0224 is 7,144 bytes at SHA-256
  `0493b4aa9ca5eb44a4b2813c672f8a03e42c829cd8106cb37d3644747fee3e00` and both
  applies to its isolated preimage and reverse-applies from the live postimage.
- The real `blender_browser` recompiles `wgpu_backend.cc`, `wgpu_batch.cc`, and
  `wgpu_immediate.cc`, relinks, and ends exact locked-Ninja no-work
  (`20260823T045036-2376636`, `20260823T045119-2377854`). OFF preflight binds the
  118,076,342-byte primary Wasm (`20260823T045139-2378078`).
- Final REUSE 6.2.0 is green for 2,177/2,177 files. Required M3 remains red only for the
  absent strict candidate (`20260823T045219-2378392`); final container-backed regression keeps
  M0 6/6 green while M1-M8 retain their existing strict-receipt, split-product, browser,
  run-label, hardware, and independent M8 performance boundaries (`20260823T045254-2378882`).

## Boundary

This is device-free resource-failure proof. It creates no WebGPU instance, accepted adapter,
device, bind group, pass, dispatch, draw, submission, pixel, browser receipt, profile, or split
product. Live proof remains blocked by **no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships
none; Mesa dzn rejected by Dawn)**. No result promotion, dependency decision, deferral,
tolerance, golden, blacklist, or milestone promise changed.
