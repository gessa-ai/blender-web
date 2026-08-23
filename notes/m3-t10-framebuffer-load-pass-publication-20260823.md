<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 framebuffer load-pass publication - 2026-08-23

## Outcome

Patch 0225 (`121d696`) makes `WGPUFrameBuffer::begin_load_pass()` publish the result of
`BeginRenderPass()` only after it is non-null. Ordinary viewport and scissor state therefore
cannot be applied to a failed pass before the direct, indirect, or immediate draw caller receives
and checks the factory result.

## Evidence

- The unchanged shipping source fails before compilation or evidence allocation at the missing
  atomic publication guard (`20260823T050509-2390110`).
- Final root and descendant-CWD native/wasm32 runs pass 20 byte-identical integrated contracts at
  2,030 bytes, SHA-256 `5c4c0acc7ef52f5eb01efdd39bf6f1cd6b83e1f953e024de91af2008463aeb7f`.
  Their 25 shipping inputs are SHA-256
  `b050cfc69cb3f2c0936bf3e9ec886f9fec78998d919a7af3c15f9b37f45c67ed`
  (`20260823T050721-2392444`, `20260823T050745-2393342`). Ambient Node 25.1.0 is rejected
  before its requested evidence directory exists (`20260823T050814-2394437`).
- The canonical freezer retains 257 paths and 20,258 live/replay entries. The 1,660,739-byte
  patch is SHA-256 `7827e99f7b6bd2f727ff48084f92e0b991441b4270e26362453eac19e20374a6`,
  and both manifests are SHA-256
  `99e75f39eb7a9376b2595317c31947a2353eea23ea6ae86d90da242bc0d7a35a`
  (`20260823T050622-2391566`). Numbered patch 0225 is 752 bytes at SHA-256
  `01312af379f98b04207543fc8d86f818c66d7107bc957f1037280a6c3ec2fe3c`; isolated
  apply/reverse and live reverse-check are green (`20260823T051312-2399634`). Canonical replay is
  green (`20260823T050953-2396431`).
- The real `blender_browser` recompiles `wgpu_framebuffer.cc`, relinks, and ends exact locked-Ninja
  no-work (`20260823T050853-2395108`, `20260823T050935-2396299`). OFF preflight binds the
  118,076,516-byte primary Wasm (`20260823T050941-2396347`).
- Final REUSE 6.2.0 is green for all 2,179 files (`20260823T051431-2400136`).
- Required M3 remains red only for the absent fresh strict candidate
  (`20260823T051017-2396758`). Final container-backed regression restores M0 6/6 green while
  M1-M8 retain their existing strict-receipt, split-product, browser, run-label, hardware, and
  independent M8 performance boundaries (`20260823T051040-2397154`).

## Boundary

This is device-free pass-publication proof. It creates no WebGPU instance, accepted adapter,
device, render pass, draw, submission, pixel, browser receipt, profile, or split product. Live
proof remains blocked by **no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn
rejected by Dawn)**. No result promotion, dependency decision, deferral, tolerance, golden,
blacklist, or milestone promise changed.
