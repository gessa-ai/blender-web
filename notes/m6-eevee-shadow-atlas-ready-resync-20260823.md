<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M6 EEVEE shadow-atlas READY resync - 2026-08-23

## Outcome

Patch 0210 makes the resumable EEVEE image-render path rebuild its shadow passes exactly once when
the asynchronous WebGPU atlas allocation becomes ready after the initial sync. The settled atlas
SSBO is now bound before `RenderSamples`; native backends and WebGPU passes that were already bound
do not resync.

This closes a device-free Phase-B control-flow defect. It does not claim a live adapter, shadow
pixel, comparator result, or M6 pass.

## Diagnosis

`Instance::init()` performs `render_sync()` while constructing an image-render instance. When the
tracked WebGPU vertex-buffer allocation was still pending, `ShadowModule::begin_sync()` captured
`webgpu_shadow_atlas_ready_for_sync_ = false`, `ShadowPipeline::sync()` omitted the atlas SSBO, and
the resulting pass stayed non-submittable. The later `AwaitShadowAtlas` READY arm advanced directly
to `RenderSamples`; it never performed the "next shadow sync" promised by the allocation state.
Consequently `ShadowModule::render()` returned before the Phase-B raster/resolve work.

`shadow_atlas_requires_sync()` now exposes only the settled-but-not-synced state through
`ShadowModule` and `Instance`. The READY arm consumes that state with one `render_sync()` before
advancing. The subsequent `begin_sync()` captures readiness and binds the existing atlas buffer.

## Verification

- The unchanged source fails the exact eight-part state/source contract before evidence allocation
  (`20260823T002904-2118791`). Root and descendant-CWD final runs pass
  (`20260823T002948-2119021`, `20260823T003921-2126784`).
- The real `blender_browser` target recompiles the affected EEVEE sources and links in 42 seconds,
  then reaches exact locked no-work (`20260823T003000-2119099`,
  `20260823T003050-2119619`). The primary Wasm is 118,072,826 bytes.
- The canonical freezer and clean-pin replay retain 257 paths and 20,258 manifest entries. The
  1,656,590-byte patch is SHA-256
  `2883b05badb2ec700df8195196dcc199058aea79fd82e04ec07abfd72e8f6339`; live and replay manifests
  are byte-identical at SHA-256
  `f871460b1314cf4c0669af6968324db499322b84f3351320ab0c4926b134f49f`
  (`20260823T003450-2122524`, `20260823T003638-2124166`). Numbered patch 0210 reverse-applies
  cleanly and is SHA-256 `f2cc4d28c6c9ede490bba7b05a00342cffe03a21187493c1bbf98f092d51e662`.
- Final REUSE 6.2.0 is green for 2,149/2,149 files (`20260823T004458-2130476`).
- Required M6 remains red on its existing missing safe Cycles run label
  (`20260823T003728-2124515`). Container-backed regression keeps M0 6/6 green while M1-M8 retain
  the existing strict-receipt, split-product, browser, run-label, and hardware boundaries
  (`20260823T003845-2125725`).

## Boundary

No Vulkan/Chromium retry, WSL restart, adapter, device, atlas allocation, render submission, pixel,
profile, split product, result promotion, deferral change, tolerance, golden, blacklist, or promise
was produced. The four EEVEE shadow-scene goldens remain blocked by **no conformant hardware Vulkan
ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)**.
