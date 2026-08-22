<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 WebGPU window viewport/scissor validation — 2026-08-22

## Outcome

Patch 0192 preserves Blender's signed window-backbuffer viewport while converting its
bottom-origin Y coordinate with widened arithmetic. An enabled frontend scissor is converted and
clipped independently. Both rectangles now validate before layered clears or render-pass
allocation, so malformed or fully clipped state cannot silently become a whole-window draw.

## Diagnosis and implementation

The multi-viewport paths already used `viewport_scissor_plan()`, but the sibling window-direct
path in `WGPUFrameBuffer::begin_load_pass()` still used the older inline policy. It calculated
`fb_h - (y + height)` in signed `int`, clamped the viewport origin, then retained the original
width and height. A viewport `[-10, 5, 20, 10]`, for example, became `[0, 465, 20, 10]`: its
raster transform moved ten pixels instead of retaining the signed origin. Integer-boundary input
could overflow during the bottom-origin conversion. Invalid or empty rectangles were discovered
only after `BeginRenderPass()`, where skipping `SetViewport()` left Dawn's whole-target default.

`window_viewport_scissor_plan()` in `wgpu_common.hh` now:

- converts the viewport's bottom-origin Y in `int64_t` and rejects an unrepresentable result;
- delegates viewport/device-bound validation to the existing signed viewport plan without
  changing the raster transform;
- clips the optional explicit scissor independently to the unsigned framebuffer bounds; and
- commits output only after both rectangles pass.

`begin_load_pass()` obtains the exact device limit and runs that plan before layered load clears,
attachment assembly, or `BeginRenderPass()`. It then supplies the preserved viewport and, only
when enabled, the clipped scissor. Pinned Dawn's viewport and scissor rules remain bound by the
integrated driver (`DynamicStateCommandValidationTests.cpp` and `RenderPassEncoder.cpp`).

## Verification

- The unchanged source rejects the absent plan before evidence allocation
  (`20260822T173214-1702865`); the requested preimage output directory remains absent.
- Final root and descendant-CWD native/wasm32 executions pass 13 byte-identical contracts
  (`20260822T174325-1713957`, `20260822T174341-1714751`). The new contract covers 32
  bottom-origin decisions: 14 accepted
  and 18 rejected, including partial edges, an independent oversized scissor, disabled scissor,
  empty/outside rectangles, device limits, null input, and `INT_MIN`/`INT_MAX`. Exact stdout is
  1,145 bytes with SHA-256 `9fcc0a4a4c69c0655c4a7823b8d529f855e673678ad87da1c01aa80379a01d8c`;
  the 21-input shipping source set has SHA-256
  `47448579c38bdbad7a45ba50f49e47d9df57f15de8146676187da78aadbe3734`.
- A wrong Node identity rejects before its requested evidence directory exists
  (`20260822T173801-1708307`).
- The canonical freezer retains 257 paths and 20,258 entries. The 1,614,748-byte patch has
  SHA-256 `a2c0e04eee74611d05032f496368bd72bf0213a8f0ce900cc8e0910244f192ce`;
  live and replay manifests are byte-identical at SHA-256
  `f28cd079d729ceac9ba7a5a4fcd1a9781f926e4fd31ac8af70194b39ef6432b4`
  (`20260822T173546-1705388`). Canonical-only replay and patch reverse-application are green
  (`20260822T173618-1706667`, `20260822T175051-1720829`).
- `blender_browser` rebuilds through locked Ninja and then ends exact no-work
  (`20260822T173650-1707593`, `20260822T173734-1708005`). The strict OFF-product preflight passes
  with a 118,059,907-byte primary Wasm (`20260822T173747-1708144`).
- REUSE 6.2.0 reports copyright and license information for all 2,100 files
  (`20260822T174418-1716383`).
- Required M3 remains honestly red for the absent fresh strict candidate
  (`20260822T174138-1711968`). Container-backed regression keeps M0 6/6 green while M1-M8 retain
  their existing strict-receipt, product, browser, run-label, and hardware boundaries
  (`20260822T174145-1712032`).

## Boundary

The contract creates no WebGPU instance, adapter, device, buffer, pipeline, render pass, draw,
pixel, browser receipt, or result promotion. Required M3 remains red for the absent fresh strict
candidate, and live window proof remains owned by `M3-LINUX-REPLAY`, still blocked by the named s7
hardware-Vulkan/WebGPU condition.
