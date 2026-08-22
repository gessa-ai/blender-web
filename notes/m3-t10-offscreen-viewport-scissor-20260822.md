<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 WebGPU offscreen viewport/scissor application — 2026-08-22

## Outcome

Patch 0193 makes every ordinary offscreen WebGPU draw apply the viewport and optional scissor
stored by Blender. Audit patch 0201 corrects both rectangles from Blender's bottom origin to
WebGPU's top origin before clipping. The backend's clip-space and readback flips preserve content
orientation and row order, but do not relocate a partial viewport or scissor. Both rectangles
validate before layered clears or render-pass allocation.

## Oracle, diagnosis, and implementation

The pinned native Blender oracle draws a full-screen quad into a 6x5 `GPUOffScreen`. Viewport
`[1, 1, 3, 2]` colors exactly six lower-left-coordinate pixels, and viewport `[1, 0, 4, 4]` with
scissor `[3, 2, 3, 3]` colors exactly their four-pixel intersection. This fixes the coordinate
contract independently of WebGPU implementation assumptions.

`WGPUFrameBuffer::begin_load_pass()` is shared by ordinary window and offscreen draws. Patch 0192
made the window branch validate and apply its state, but the offscreen branch still began a pass
without either `SetViewport()` or `SetScissorRect()`. Dawn therefore used the whole-target default
viewport and ignored Blender's enabled scissor.

`offscreen_viewport_scissor_plan()` now reuses the window helper because every Blender framebuffer
rectangle has the same bottom-origin API contract. The shared framebuffer scissor helper converts
Y as `H - y - height`, clips with widened arithmetic, and commits the plan only after every check
passes. `begin_load_pass()` selects the window or offscreen plan before
`materialize_layered_loadstore_clears()` and `BeginRenderPass()`, then applies the resulting state
to every ordinary pass. Multi-viewport emulation remains owned by `WGPUBatch` and skips this
single-viewport state.

## Verification

- The pinned native oracle passes with the exact six-pixel viewport and four-pixel intersection
  (`20260822T180458-1732161`).
- The unchanged source rejects the missing generalized plan before evidence allocation
  (`20260822T180811-1735064`); its requested evidence directory remains absent.
- Final root and descendant-CWD native/wasm32 executions pass 14 byte-identical contracts
  (`20260822T182502-1750375`, `20260822T181510-1741812`). The new contract covers 21 offscreen
  decisions: 12 accepted and 9 rejected, with five enabled scissors and aggregate clipped area
  113. It exercises the oracle rectangles, signed partial viewports, disabled scissor, partial and
  oversized scissors, empty/outside state, device limits, null input, and integer boundaries.
  This original device-free matrix incorrectly expected raw offscreen Y. Audit patch 0201 replaces
  those expectations with the composed WebGPU-placement/readback invariant; the historical
  receipt proves patch 0193's coverage, not the corrected coordinate result.
  Exact stdout is 1,270 bytes with SHA-256
  `52e812d816a279a9411cd6e32b2b53726d8756a1d29d4a459336595bdaeb7b74`; the bound shipping source
  set has SHA-256 `68ec55ffe336d748f83dd7184ccf4c116a4b177dd4489cc8ccfbbe153c8df7c6`.
- Wrong Node and Dawn identities reject before their requested evidence directories exist
  (`20260822T181608-1742673`, `20260822T181632-1743181`).
- Patch 0193 passes live reverse application plus an isolated reverse/forward byte-exact round
  trip (`20260822T182428-1749362`).
- The canonical freezer retains 20,258 entries. Its 1,616,957-byte patch has SHA-256
  `bc9af849b9e68a550df36c88c7ab63db24e45cd80ebde3ab50f2b322cde66cbd`; live and replay manifests
  are byte-identical at SHA-256
  `6dac71b1f5d0b4437c632f0dcd796ac9fcb34a364e640a42fceb61b529aeb84c`
  (`20260822T181141-1737537`). Canonical-only replay is green (`20260822T181220-1738875`).
- `blender_browser` rebuilds through locked Ninja and then ends exact no-work
  (`20260822T181341-1740204`, `20260822T181451-1741158`). The strict OFF-product preflight passes
  with a 118,060,246-byte primary Wasm (`20260822T181503-1741766`).
- REUSE 6.2.0 reports copyright and license information for all 2,104 files
  (`20260822T182512-1750368`).
- Required M3 remains honestly red for the absent fresh strict candidate
  (`20260822T181703-1743427`). Container-backed regression keeps M0 6/6 green while M1-M8 retain
  their existing strict-receipt, product, browser, run-label, and hardware boundaries
  (`20260822T181714-1743550`).

## Boundary

The device-free contract creates no WebGPU instance, adapter, device, render pass, draw, pixel,
browser receipt, or result promotion. The native oracle binds Blender's offscreen coordinate
semantics but not the WebGPU implementation. Audit patch 0201 therefore remains source-level
proof pending the hardware-gated ordinary-draw/readback pixel case. Framebuffer clear scissoring
is covered separately.
Required M3 remains red, and live WebGPU proof remains owned by `M3-LINUX-REPLAY`, still blocked
by the named s7 hardware-Vulkan/WebGPU condition.
