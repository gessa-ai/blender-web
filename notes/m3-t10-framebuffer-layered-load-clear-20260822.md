<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 WebGPU framebuffer layered load clear - 2026-08-22

## Outcome

Patch 0184 preserves explicit load-action clears across all selected array layers. A fixed-layer
or one-layer attachment still clears in the first draw pass. An all-layer attachment with more
than one layer is cleared before draw-pass assembly, so the first emulated `(layer, viewport)`
pass cannot consume the action while sibling layers remain stale.

## Diagnosis and implementation

`WGPUFrameBuffer::begin_load_pass()` treated every `GPU_LOADACTION_CLEAR` as a global one-shot.
That is correct for one attached subresource, but WebGPU exposes only one array layer per render
attachment view. The multi-viewport emulation opens many render passes; its first pass cleared
layer zero and changed the shared action to `LOAD`, leaving every later layer untouched. The same
gap existed for an all-layer array attachment drawn without multi-viewport emulation.

The pinned native API probe confirms that a bare array attachment clear covers every layer. This
matches Vulkan's dynamic-rendering path, which raises `layerCount` for all-layer color attachments
at `upstream/source/blender/gpu/vulkan/vk_framebuffer.cc:616` and applies the configured load/store
action at `:649`.

The shared decision at `upstream/source/blender/gpu/webgpu/wgpu_common.hh:336` distinguishes an
invalid selection, a clear that one render pass can cover, and an all-layer clear that must be
materialized. `WGPUFrameBuffer::materialize_layered_loadstore_clears()` at
`upstream/source/blender/gpu/webgpu/wgpu_framebuffer.cc:400` validates every pending clear before
touching an attachment, clears only multi-layer all-layer selections through the already-proven
layered clear path, and then changes those actions to `LOAD`. `begin_load_pass()` invokes it before
render-pass descriptor assembly at `:888`. Existing fixed-layer, one-layer, depth/stencil, and
single-pass behavior remains unchanged.

## Evidence

- The digest-pinned Blender 5.2 native oracle clears and reads all three array layers
  (`20260822T132247-1481639`).
- The unchanged canonical source rejects the new wiring contract before evidence allocation
  (`20260822T132653-1484876`).
- Final root and descendant-CWD runs compile the real framebuffer translation unit through the
  pinned native and wasm32 locked-Ninja graphs and pass 20 byte-identical contracts. Their
  1,995-byte evidence has SHA-256
  `01cda592551cada60a8433fb54b77097ef224aa276a20ce1d6715f515f30065b` and source SHA-256
  `17619f92177101d02d39ed78aff798cea5801d8b4a096fa7325d30a7589624d6`
  (`20260822T133545-1492055`, `20260822T133606-1492838`). The new ten-case contract covers
  fixed, single-layer, multi-layer, zero, out-of-range, and signed-boundary decisions.
- Wrong Dawn and wrong Node identities reject before their requested evidence directories exist
  (`20260822T133656-1494364`, `20260822T133718-1494687`).
- The canonical freezer retains 257 paths and 20,258 entries. The patch is 1,593,916 bytes at
  SHA-256 `9d1a52eac0a957b819b6a30a90791d63ba816216b9018f8d5c65c0cecd5caf2b`;
  live/replay manifests are byte-identical at SHA-256
  `05f324014a6ed39fa243e27e717f1460a747a5e2570c1e765b9d4d882c5dca7f`
  (`20260822T133413-1490140`, `20260822T133509-1491547`,
  `20260822T133509-1491548`). Numbered history remains explicitly diagnostic-only at its
  pre-existing non-replayable entry 0016; the canonical reconstruction authority is green.
- `blender_browser` rebuilds through the locked graph and then reports exact no-work
  (`20260822T133737-1495128`, `20260822T133824-1495537`). The OFF-mode product preflight is green
  (`20260822T133900-1495858`).
- REUSE 6.2.0 is 2,081/2,081 green (`20260822T134151-1499528`). Required M3 remains honestly red for the
  absent fresh strict candidate (`20260822T133936-1496950`); container-backed regression restores
  M0 6/6 while M1-M8 retain the existing strict-receipt/product/browser/run-label/hardware
  boundaries (`20260822T134003-1497348`).

## Boundary

The contract creates no WebGPU instance, adapter, device, framebuffer, render pass, draw, pixel,
browser receipt, or result promotion. Live layered load-clear proof remains owned by
`M3-LINUX-REPLAY`, still blocked by the named s7 software-adapter condition.
