<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 WebGPU multi-viewport scissor validation — 2026-08-22

## Outcome

Patch 0190 preserves Blender's signed multi-viewport raster transform while deriving a separate
unsigned scissor that is contained in the framebuffer. Negative and overshooting rectangles no
longer wrap or invalidate Dawn's command encoder. Direct batch draws and indirect EEVEE shadow
draws use the same atomic plan before beginning each emulated viewport pass.

## Diagnosis and implementation

`WGPUFrameBuffer` stores each viewport as four signed integers. Both multi-viewport paths in
`wgpu_batch.cc` previously sent those values unchanged to `SetViewport` and converted the same
values independently to `uint32_t` for `SetScissorRect`. A negative origin therefore wrapped to a
large unsigned coordinate, while a positive rectangle extending past the framebuffer remained
outside the render area.

Pinned Dawn deliberately accepts bounded negative viewport origins and viewports larger than the
render target. It separately requires the complete unsigned scissor to be contained in the render
area (`build-dawn/dawn/src/dawn/native/RenderPassEncoder.cpp:226-292` and `:299-326`). Clamping the
viewport itself would change the raster transform, so the two rectangles cannot share one clipped
representation.

`viewport_scissor_plan()` in `wgpu_common.hh` now validates positive dimensions, the device's
`maxTextureDimension2D` viewport limit, Dawn's signed viewport bounds, and the framebuffer
intersection with widened arithmetic. It commits output only after every check succeeds. The
original signed origin and dimensions feed `SetViewport`; only the nonempty framebuffer
intersection feeds `SetScissorRect`. Both direct and indirect multi-viewport branches obtain the
exact device limit and use the shared plan before allocating their per-viewport render pass.

## Verification

- The unchanged source rejects the missing `ViewportScissorPlan` before evidence allocation
  (`20260822T162510-1638242`).
- Final root and descendant-working-directory native/wasm32 runs pass twelve byte-identical
  contracts (`20260822T164519-1661803`, `20260822T164115-1658601`). The new census accepts 11/28
  rectangles and rejects 17/28 without changing output, covering negative and partial edges,
  complete clipping, exact framebuffer and viewport bounds, invalid dimensions, device limits,
  `INT_MIN`, and `INT_MAX`. Final stdout is 1,017 bytes with SHA-256
  `3a52bc6aba4e094842d2d82ac037c6eaa69a1f019ed8bcd2ef25c7861d8c3466`; the bound source set has
  SHA-256 `a4139d566702af7819b121aa5edbc1280bb2a589b771038d48cc3b221579156d`.
- A wrong Node identity fails before its requested evidence directory exists
  (`20260822T163511-1651905`).
- The canonical freezer retains 257 paths and 20,258 entries. Its 1,607,884-byte patch has SHA-256
  `462e17b59733c30b665317a140332c0d067741fd286b39695c2e19d191bca4cd`; live and replay
  manifests are byte-identical at SHA-256
  `7060a4003e8b0b91095a1c4eb65a546b3fa31129ba156de936fc3fe44ccec4d6`
  (`20260822T163206-1648578`). Canonical-only verification and reverse application are green
  (`20260822T163527-1652264`, `20260822T164531-1662317`).
- `blender_browser` rebuilds through locked Ninja and then ends exact no-work
  (`20260822T163539-1652386`, `20260822T163829-1654288`). The strict OFF-product preflight passes
  with a 118,057,776-byte primary Wasm (`20260822T163829-1654289`).
- REUSE 6.2.0 reports copyright and license information for all 2,096 files
  (`20260822T164219-1659783`).
- Required M3 remains red for the absent fresh strict candidate. Container-backed regression
  keeps M0 6/6 green while M1-M8 retain their existing strict-receipt, product, browser,
  run-label, and hardware boundaries.

## Boundary

The contract creates no WebGPU instance, adapter, device, buffer, pipeline, render pass, draw,
pixel, browser receipt, or result promotion. It does not bind the software Vulkan adapter. Live
multi-viewport proof remains owned by `M3-LINUX-REPLAY`, still blocked by the named s7
hardware-adapter condition.
