<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 WebGPU empty-raster load actions — 2026-08-22

## Outcome

Patch 0203 separates malformed raster state from WebGPU-valid empty state. Negative extents,
invalid targets, and device-limit violations still fail atomically. Zero viewports retain their
signed transform, while fully clipped viewports and enabled scissors select the contained
`(0,0,0,0)` scissor accepted by pinned Dawn. An ordinary or multi-viewport draw can therefore
open its render pass, consume pending attachment load clears, and rasterize no fragments.

## Diagnosis and implementation

The pre-fix planner rejected its first legal zero extent before allocating evidence
(`20260822T215407-1952511`). That return occurs before
`WGPUFrameBuffer::materialize_layered_loadstore_clears()` at
`upstream/source/blender/gpu/webgpu/wgpu_framebuffer.cc:1445`, so an explicit
`GPU_LOADACTION_CLEAR` could remain pending and a later framebuffer read could observe stale
pooled texture content.

The shared planner at `upstream/source/blender/gpu/webgpu/wgpu_common.hh:166` now preserves zero
extents and emits an empty intersection without weakening its signed/device-limit checks. The
ordinary framebuffer wrapper at `:233` and `:455` converts a legal fully clipped viewport or
enabled scissor into a contained zero scissor. The WebGPU GPU regression at
`upstream/source/blender/gpu/tests/framebuffer_test.cc:202` binds an explicit green load clear,
submits a normal red fullscreen draw through a zero-width viewport, and reads all four pixels back
as green.

## Verification

- Final native/wasm32 planner evidence covers 28 multi-viewport, 32 window, and 21 offscreen
  boundaries byte-identically at 1,379 bytes, SHA-256
  `e067b3a3de4456092eec165c6cb7f1821d2dfaa0a834f201d37bb51003afaddd`
  (`20260822T220820-1975145`).
- The texture/load-clear source contract, including the exact GPU regression, is byte-identical
  at 2,399 bytes, SHA-256
  `82f2eadcdeb391e1838fe906e6d29ecd962597c1883c8eb3ea62053720106072`
  (`20260822T220834-1976215`). The regression translation unit compiles under wasm32
  (`20260822T220539-1971982`).
- The canonical freeze contains 257 paths and 20,258 entries; patch SHA-256 is
  `23b73e543b308ceb500ddc5dabefd17865e32df987cbd10737b6df107140d710`, and final replay plus
  patch reverse-application are green (`20260822T220559-1972189`,
  `20260822T220941-1979294`, `20260822T220941-1979268`).
- The real `blender_browser` rebuild reaches 47/47 and then exact no-work; OFF artifact preflight
  is green (`20260822T220636-1972750`, `20260822T220806-1974744`,
  `20260822T220815-1975106`). REUSE 6.2.0 is 2,127/2,127 green
  (`20260822T220859-1977455`).
- Required M3 remains red only for the absent fresh strict candidate. Container-backed regression
  keeps M0 6/6 green while M1-M8 retain their separately named receipt/product/browser/run-label
  boundaries.

The optional full numbered-history diagnostic still stops at the pre-existing entry 15/180
(`0016-gpu-webgpu-texture-format-conversion.patch`, `20260822T220144-1965108`); canonical replay
and patch 0203 reversal are the current source authorities. Building the entire optional wasm
GPU-test archive also reaches
unrelated pre-existing death-test portability errors in `texture_view_test.cc` and
`texture_test.cc` (`20260822T220501-1971286`); the new `framebuffer_test.cc` translation unit
itself compiles cleanly.

## Boundary

No WebGPU adapter, device, render pass, draw, pixel, or browser receipt is claimed on ornith-lab.
The live GPU regression remains owned by `M3-LINUX-REPLAY` and s7-blocked because the available
Vulkan adapter is software-only. No result promotion, deferral, tolerance, golden, blacklist, or
milestone promise changed.
