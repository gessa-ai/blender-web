<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU bind-group completeness contract — 2026-08-23

## Outcome

Commit `fd04ebb` closes audit R6's bind-group completeness finding. Shader finalization retains
the exact sorted group-0 binding IDs that survive final WGSL. Compute, direct and indirect batch,
multi-viewport, and immediate paths now compare that set with the unique IDs of entries carrying
live resources before any encoder or pass is allocated. A genuinely empty layout can still omit
group 0; required-but-empty, partial, and extra resource sets fail closed. The census includes the
backend-injected push-constant and multi-viewport uniforms.

## Evidence

- The unchanged source fails the new source-bound contract before evidence allocation because it
  has no completeness helper (`20260823T135955-2864289`). Patch 0238 is SHA-256
  `0248fd270da4` and passes isolated forward/reverse plus exact live-byte round trips.
- Final root and descendant-CWD native/wasm32 runs pass 29 byte-identical contracts at 3,257 bytes,
  SHA-256 `a30fce3177dd`, with exact shipping inputs SHA-256 `1a9969d3b704`. The six new cases cover
  genuinely empty, complete, duplicate-assembled, required-but-empty, partial, and extra sets;
  source-order checks bind all six shipping callers ahead of command work
  (`20260823T142414-2909530`, `20260823T142428-2911313`). A wrong Node 22.22.1 fails before evidence
  allocation (`20260823T142024-2905919`).
- An external clean-pin postimage configured and built the real CAPTURE-mode `blender_browser`
  exclusively through locked Ninja, passed product preflight, and ended locked no-work
  (`20260823T140920-2877065`, `20260823T140930-2877135`, `20260823T141621-2900493`,
  `20260823T141633-2900629`). The protected `upstream/` tree was not changed by this iteration.
- The clean-pin freezer/replayer retains 257 paths and 20,258 entries. Its 1,727,970-byte canonical
  patch is SHA-256 `fc7726e91cff`; live and replay manifests are byte-identical at 3,477,334 bytes,
  SHA-256 `371973283067` (`20260823T141703-2900869`). Canonical-only reconstruction independently
  passes against the exact postimage (`20260823T141843-2902578`).
- Required M3 remains red only for the absent fresh strict candidate. Container-backed regression
  keeps M0 6/6 green while M1-M8 retain their existing strict-receipt, split-product, browser,
  run-label, hardware, and release boundaries. REUSE 6.2.0 is green for all tracked files.

## Boundary

This is device-free CPU/source and compile/link proof. It creates no accepted adapter, device,
bind group, pass, draw, pixel, browser receipt, result promotion, or milestone promise. Live
hardware proof remains deferred by the named blocker: no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn). This iteration did not retry dzn or the staged
post-reboot Windows path.
