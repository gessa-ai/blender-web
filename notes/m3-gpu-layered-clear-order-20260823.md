<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU layered clear ordering contract — 2026-08-23

## Outcome

Commit `b8ce1e7` and patch 0241 close R7's layered framebuffer clear-order defect. Load-pass
preflight now stages and reserves every required all-layer clear before the caller reserves its
dependent direct, indirect, multi-viewport, or immediate draw. An idempotent completion group
holds the shared load-action generation pending until every clear and the draw validate. Clear
failure, draw failure, or cancellation rolls the generation back for retry; a stale completion
cannot consume a replacement bind.

## Evidence

- The unchanged nested-reservation path fails the new scheduler/source contract before evidence
  allocation (`20260823T181103-3135719`). Ambient Node 25.1.0 also rejects before allocating its
  requested evidence directory (`20260823T182411-3149692`).
- Final root and descendant-CWD native/wasm32 runs pass 35 byte-identical integrated contracts,
  including four real-FIFO layered-clear cases covering clean clear-before-draw order, clear
  rejection with dependent cancellation, draw rejection, idempotent completion, and generation
  isolation. Evidence is 4,257 bytes at SHA-256
  `925bb5e46cbbedc7f86fc5ea5cff5c04db6a07d2733236169d7866b260f19602`; shipping inputs are
  SHA-256 `68ff7037af3f333e27fe9e098ff7e633148adfc00af2bb5461793daa066d1c81`
  (`20260823T182109-3145030`, `20260823T182421-3150521`). The broader texture native/wasm32
  suite remains byte-identical at 2,650 bytes SHA-256
  `0631052df84e732385910e2f750b46a193a2a66046b3a00b72a79960c2eef394`
  (`20260823T182328-3148767`).
- Numbered patch 0241 is 16,599 bytes at SHA-256
  `e653e6ac25347fb747b20db5c4b7619dd3fb9d5a1fb4e7f8a0d877a4a4a6e661` and passes isolated
  reverse/forward exact-byte round trip plus patch-aware whitespace checks. The canonical freeze
  retains 257 paths and 20,258 entries; its 1,745,064-byte patch is SHA-256
  `7788a41c1f70e7ba72a1158730e4a02914dce47171f269ed3162453bd3b3e996`, with byte-identical
  3,477,335-byte manifests at SHA-256
  `80d968700706bcba27a0a05a6cbe8e3eb9e2df336617e6f21ee37b29f7c70e90`
  (`20260823T183411-3159673`).
- The real `blender_browser` relinks and ends exact locked no-work
  (`20260823T182457-3151714`, `20260823T182541-3152935`). OFF preflight binds the 657,910-byte JS,
  118,736,483-byte Wasm, and 167,143,248-byte data product. REUSE 6.2.0 is green for all 2,226
  tracked files, including this record (`20260823T183411-3159674`). Required M3 remains red only
  for the absent fresh strict candidate (`20260823T183431-3160005`); final container-backed
  regression keeps M0 6/6 green while M1-M8 retain their existing strict-receipt, product,
  browser, run-label, hardware, and release boundaries (`20260823T183446-3160128`). No gate result
  was promoted.

## Boundary

This is device-free CPU/source and compile/link proof. It creates no accepted hardware adapter,
browser/pixel receipt, profile, split product, result promotion, dependency decision, new
deferral, tolerance, golden, blacklist, or milestone promise. Live hardware proof remains deferred
by the named blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn
rejected by Dawn). This iteration did not retry dzn, attempt the staged Windows path, or restart
WSL.
